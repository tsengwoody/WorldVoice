import queue
import threading
import time
from dataclasses import dataclass
from concurrent.futures import Future

from logHandler import log
from synthDriverHandler import synthIndexReached, synthDoneSpeaking, getSynth


# ----------------------------
# Utilities
# ----------------------------

class CancellationToken:
	def __init__(self):
		self._ev = threading.Event()

	def cancel(self):
		self._ev.set()

	def is_cancelled(self):
		return self._ev.is_set()

	def wait(self, timeout=None):
		return self._ev.wait(timeout)


class SpeechFuture(Future):
	"""Future with Promise-style then()."""

	def then(self, fn):
		next_fut = SpeechFuture()

		def _cb(f):
			try:
				if f.cancelled():
					next_fut.cancel()
					return

				res = fn(f)

				# flatten Future
				if isinstance(res, Future):
					res.add_done_callback(
						lambda r: next_fut.set_exception(r.exception())
						if r.exception()
						else next_fut.set_result(r.result())
					)
				else:
					next_fut.set_result(res)

			except Exception as e:
				next_fut.set_exception(e)

		self.add_done_callback(_cb)
		return next_fut


@dataclass
class _Task:
	voiceInstance: object
	run: callable
	wait_done: bool
	future: SpeechFuture
	token: CancellationToken | None = None
	timeout: float | None = None


def IndexReached_notify_forward(synth, index):
	if hasattr(synth, "wv"):
		synthIndexReached.notify(synth=getSynth(), index=index)


def DoneSpeaking_notify_forward(synth):
	if hasattr(synth, "wv"):
		synthDoneSpeaking.notify(synth=getSynth())



# ----------------------------
# SpeechExecutor
# ----------------------------

class TaskManager:

	def __init__(self):
		self._q: queue.Queue[_Task | None] = queue.Queue()
		self._stop = threading.Event()
		self._state_lock = threading.Lock()

		self._current_voice = None
		self._current_token = None
		self._current_done_event = None

		self._thread = threading.Thread(target=self._worker, daemon=True)

		synthDoneSpeaking.register(DoneSpeaking_notify_forward)
		synthDoneSpeaking.register(self._on_done_speaking)
		synthIndexReached.register(IndexReached_notify_forward)

		self._thread.start()

	# ----------------------------
	# Public API
	# ----------------------------

	def add_task(self, voiceInstance, fn, *, token: CancellationToken | None = None):
		fut = SpeechFuture()
		self._q.put(_Task(voiceInstance, fn, False, fut, token))
		return fut

	def add_speak_task(self, voiceInstance, speak_fn, *, token: CancellationToken | None = None, timeout=None):
		fut = SpeechFuture()
		self._q.put(_Task(voiceInstance, speak_fn, True, fut, token, timeout))
		return fut

	def cancel_current(self):
		with self._state_lock:
			token = self._current_token
			voice = self._current_voice
			done = self._current_done_event

		if token:
			token.cancel()

		if voice:
			try:
				voice.stop()
			except Exception:
				log.debug("Failed to stop current voice", exc_info=True)

		if done:
			done.set()

	def cancel(self):
		# cancel active
		self.cancel_current()

		# cancel pending queue
		try:
			while True:
				item = self._q.get_nowait()
				if isinstance(item, _Task):
					item.future.cancel()
				self._q.task_done()
		except queue.Empty:
			pass

	def shutdown(self):
		self.cancel()
		self._stop.set()
		self._q.put(None)
		self._thread.join()

		try:
			synthIndexReached.unregister(IndexReached_notify_forward)
		except Exception:
			pass
		try:
			synthDoneSpeaking.unregister(DoneSpeaking_notify_forward)
		except Exception:
			pass
		try:
			synthDoneSpeaking.unregister(self._on_done_speaking)
		except Exception:
			pass

	# ----------------------------
	# Worker
	# ----------------------------

	def _on_done_speaking(self, synth):
		try:
			if synth != getSynth():
				return
		except Exception:
			return
		with self._state_lock:
			done = self._current_done_event
		if done:
			done.set()

	def _worker(self):
		while not self._stop.is_set():
			task = self._q.get()
			if task is None:
				return
			try:
				self._run_one(task)
			finally:
				self._q.task_done()

	def _run_one(self, task: _Task):

		if task.future.cancelled():
			return

		if task.token and task.token.is_cancelled():
			task.future.cancel()
			return

		with self._state_lock:
			self._current_voice = task.voiceInstance
			self._current_token = task.token

		try:
			# ---------------- normal task ----------------

			if not task.wait_done:
				result = task.run()
				task.future.set_result(result)
				return

			# ---------------- speech task ----------------

			done = threading.Event()

			with self._state_lock:
				self._current_done_event = done

			task.run()

			start = time.monotonic()

			while True:
				if self._stop.is_set():
					task.future.cancel()
					return

				if task.token and task.token.is_cancelled():
					task.future.cancel()
					return

				if task.timeout is not None:
					if time.monotonic() - start > task.timeout:
						task.future.set_exception(TimeoutError("Speech timeout"))
						return

				if done.wait(0.05):
					task.future.set_result(True)
					return

		except Exception as e:
			task.future.set_exception(e)
			log.error("SpeechExecutor task error", exc_info=True)

		finally:
			with self._state_lock:
				self._current_voice = None
				self._current_token = None
				self._current_done_event = None
