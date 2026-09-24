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
class SpeechRequest:
	request_id: int
	epoch: int
	token: CancellationToken
	tasks: list
	remaining: int = 0
	has_speech: bool = False
	done_sent: bool = False
	failed: bool = False


@dataclass
class _Task:
	voiceInstance: object
	run: callable
	wait_done: bool
	future: SpeechFuture
	token: CancellationToken | None = None
	timeout: float | None = None
	request: SpeechRequest | None = None
	kind: str = "legacy"
	expected_core: object = None


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

	def __init__(self, owner=None):
		self.owner = owner
		self._q: queue.Queue[_Task | None] = queue.Queue()
		self._stop = threading.Event()
		self._state_cond = threading.Condition()
		self._epoch = 0
		self._next_request_id = 1
		self._requests = {}
		self._stops_in_flight = 0
		self._current_task = None
		self._current_phase = None
		self._current_done_event = None

		self._thread = threading.Thread(target=self._worker, daemon=True)
		synthDoneSpeaking.register(DoneSpeaking_notify_forward)
		synthDoneSpeaking.register(self._on_done_speaking)
		synthIndexReached.register(IndexReached_notify_forward)
		self._thread.start()

	# ----------------------------
	# Public API
	# ----------------------------

	def new_request(self) -> SpeechRequest:
		with self._state_cond:
			request = SpeechRequest(self._next_request_id, self._epoch, CancellationToken(), [])
			self._next_request_id += 1
			self._requests[request.request_id] = request
			return request

	def append_speech(self, request, voice, fn):
		with self._state_cond:
			request.has_speech = True
			request.tasks.append(_Task(voice, fn, True, SpeechFuture(), request.token, request=request, kind="speech"))

	def append_break(self, request, voice, seconds):
		def wait_for_break():
			request.token.wait(seconds)

		with self._state_cond:
			request.tasks.append(_Task(
				voice, wait_for_break, False, SpeechFuture(), request.token,
				request=request, kind="break",
			))

	def submit_request(self, request) -> bool:
		with self._state_cond:
			if self._requests.get(request.request_id) is not request:
				return False
			if request.remaining:
				return False
			if request.epoch != self._epoch or request.token.is_cancelled():
				self._requests.pop(request.request_id, None)
				return False
			request.remaining = len(request.tasks)
			if not request.remaining:
				self._requests.pop(request.request_id, None)
				return True
			for task in request.tasks:
				self._q.put(task)
			return True

	# Kept until the caller switches to whole-request submission.
	def _add_legacy_task(self, voiceInstance, fn, wait_done, token=None, timeout=None):
		request = self.new_request()
		if token is not None:
			with self._state_cond:
				request.token = token
		fut = SpeechFuture()
		with self._state_cond:
			request.has_speech = wait_done
			request.tasks.append(_Task(
				voiceInstance, fn, wait_done, fut, request.token, timeout,
				request=request,
			))
		if not self.submit_request(request):
			fut.cancel()
		return fut

	def add_task(self, voiceInstance, fn, *, token: CancellationToken | None = None):
		return self._add_legacy_task(voiceInstance, fn, False, token)

	def add_break_task(self, voiceInstance, seconds: float):
		token = CancellationToken()
		return self.add_task(voiceInstance, lambda: token.wait(seconds), token=token)

	def add_speak_task(self, voiceInstance, speak_fn, *, token: CancellationToken | None = None, timeout=None):
		return self._add_legacy_task(voiceInstance, speak_fn, True, token, timeout)

	def _wake_current_locked(self):
		if self._current_task and self._current_task.token:
			self._current_task.token.cancel()
		if self._current_done_event:
			self._current_done_event.set()
		self._state_cond.notify_all()

	def _ordered_unique_cores_locked(self, voice_cores):
		cores = []
		seen = set()
		current = self._current_task
		if current and self._current_phase in ("starting", "awaiting_done"):
			core = current.expected_core
			if core is not None:
				seen.add(id(core))
				cores.append(core)
		for core in voice_cores:
			if core is not None and id(core) not in seen:
				seen.add(id(core))
				cores.append(core)
		return cores

	def cancel_current(self):
		with self._state_cond:
			current = self._current_task
			self._wake_current_locked()
			core = current.expected_core if current else None
		if core is not None:
			try:
				core.cancel()
			except Exception:
				log.debug("Failed to stop current core", exc_info=True)

	def cancel(self, voices=()):
		# Resolve voice properties outside the state lock.
		voice_cores = [getattr(voice, "core", None) for voice in voices]
		with self._state_cond:
			self._epoch += 1
			for request_id, request in tuple(self._requests.items()):
				request.token.cancel()
				if not request.remaining:
					self._requests.pop(request_id, None)
			self._wake_current_locked()
			cores = self._ordered_unique_cores_locked(voice_cores)
			self._stops_in_flight += 1
		try:
			for core in cores:
				try:
					core.cancel()
				except Exception:
					log.debug("Failed to stop core", exc_info=True)
		finally:
			with self._state_cond:
				self._stops_in_flight -= 1
				self._state_cond.notify_all()

	def shutdown(self):
		self.cancel()
		self._stop.set()
		self._q.put(None)
		self._thread.join()
		for event, handler in (
			(synthIndexReached, IndexReached_notify_forward),
			(synthDoneSpeaking, DoneSpeaking_notify_forward),
			(synthDoneSpeaking, self._on_done_speaking),
		):
			try:
				event.unregister(handler)
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
		with self._state_cond:
			if self._current_done_event:
				self._current_done_event.set()

	def _valid_locked(self, task):
		return (not self._stop.is_set() and not task.future.cancelled()
			and not (task.token and task.token.is_cancelled())
			and (task.request is None or task.request.epoch == self._epoch))

	def _worker(self):
		while not self._stop.is_set():
			task = self._q.get()
			try:
				if task is None:
					return
				self._run_one(task)
			finally:
				self._q.task_done()

	def _run_one(self, task: _Task):
		# Reading the core may run driver code, so do it before taking the lock.
		expected_core = getattr(task.voiceInstance, "core", None)
		with self._state_cond:
			while self._stops_in_flight and not self._stop.is_set():
				self._state_cond.wait()
			valid = self._valid_locked(task)
			if not valid:
				self._finish_task_locked(task)
			else:
				task.expected_core = expected_core
				self._current_task = task
				self._current_phase = "starting"
				if task.wait_done:
					self._current_done_event = threading.Event()
		if not valid:
			task.future.cancel()
			return

		try:
			if task.kind == "speech":
				task.voiceInstance.active()
				with self._state_cond:
					valid = self._valid_locked(task)
				if not valid:
					task.future.cancel()
					return
			# A cancellation during active() or before core entry skips the call.
			with self._state_cond:
				valid = self._valid_locked(task)
			if not valid:
				task.future.cancel()
				return
			result = task.run()
			if task.token and task.token.is_cancelled() and task.wait_done:
				# A non-token-aware speak may return after the first stop call.
				if task.expected_core is not None:
					try:
						task.expected_core.cancel()
					except Exception:
						log.debug("Failed to stop core after speak", exc_info=True)
				task.future.cancel()
				return
			if not task.wait_done:
				if task.token and task.token.is_cancelled():
					task.future.cancel()
				else:
					task.future.set_result(result)
				return
			with self._state_cond:
				self._current_phase = "awaiting_done"
				done = self._current_done_event
			start = time.monotonic()
			while True:
				with self._state_cond:
					valid = self._valid_locked(task)
				if not valid:
					task.future.cancel()
					return
				if task.timeout is not None and time.monotonic() - start > task.timeout:
					if task.request is not None:
						with self._state_cond:
							task.request.failed = True
					task.future.set_exception(TimeoutError("Speech timeout"))
					return
				if done.wait(0.05):
					task.future.set_result(True)
					return
		except Exception as e:
			if task.request is not None:
				with self._state_cond:
					task.request.failed = True
			task.future.set_exception(e)
			log.error("SpeechExecutor task error", exc_info=True)
		finally:
			with self._state_cond:
				self._current_task = None
				self._current_phase = None
				self._current_done_event = None
				self._finish_task_locked(task)

	def _finish_task_locked(self, task):
		request = task.request
		if request is None:
			return
		request.remaining -= 1
		if request.remaining == 0:
			self._requests.pop(request.request_id, None)
