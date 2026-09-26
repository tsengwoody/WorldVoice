import queue
import threading
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
	request: SpeechRequest | None = None
	kind: str = "speech"
	expected_core: object = None


# ----------------------------
# SpeechExecutor
# ----------------------------

class TaskManager:

	def __init__(self, owner=None):
		self.owner = owner
		self._q: queue.Queue[_Task | None] = queue.Queue()
		self._stop = threading.Event()
		self._state_cond = threading.Condition()
		self._delivery_lock = threading.RLock()
		self._epoch = 0
		self._next_request_id = 1
		self._requests = {}
		self._stops_in_flight = 0
		self._current_task = None
		self._current_request = None
		self._current_phase = None
		self._current_done_event = None
		self._current_indexes = set()

		self._thread = threading.Thread(target=self._worker, daemon=True)
		try:
			synthDoneSpeaking.register(self._on_core_done)
			synthIndexReached.register(self._on_core_index)
			self._thread.start()
		except BaseException:
			for event, handler in (
				(synthIndexReached, self._on_core_index),
				(synthDoneSpeaking, self._on_core_done),
			):
				try:
					event.unregister(handler)
				except Exception:
					pass
			raise

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

	def pause_current(self, switch: bool):
		with self._state_cond:
			current = self._current_task
			voice = (current.voiceInstance if current and self._valid_locked(current)
				and self._current_phase in ("starting", "awaiting_done") else None)
		if voice is not None:
			(voice.pause if switch else voice.resume)()

	def cancel(self, voices=()):
		# Resolve voice properties outside the state lock.
		voice_cores = [getattr(voice, "core", None) for voice in voices]
		with self._delivery_lock:
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
			(synthIndexReached, self._on_core_index),
			(synthDoneSpeaking, self._on_core_done),
		):
			try:
				event.unregister(handler)
			except Exception:
				pass

	# ----------------------------
	# Worker
	# ----------------------------

	def _on_core_done(self, synth):
		with self._state_cond:
			current = self._current_task
			if (synth is self.owner or current is None or current.kind != "speech"
				or current.request is not self._current_request
				or synth is not current.expected_core or self._current_phase != "awaiting_done"
				or not self._valid_locked(current)):
				return
			self._current_done_event.set()

	def _on_core_index(self, synth, index):
		with self._state_cond:
			current = self._current_task
			if (synth is self.owner or current is None or current.kind != "speech"
				or current.request is not self._current_request
				or synth is not current.expected_core or self._current_phase != "awaiting_done"
				or self._current_done_event.is_set()
				or not self._valid_locked(current) or index in self._current_indexes):
				return
			self._current_indexes.add(index)
		if getSynth() is self.owner:
			with self._delivery_lock:
				with self._state_cond:
					valid = (self._current_task is current and self._current_phase == "awaiting_done"
						and not self._current_done_event.is_set() and self._valid_locked(current))
				if valid:
					synthIndexReached.notify(synth=self.owner, index=index)

	def _valid_locked(self, task):
		return (not self._stop.is_set() and not task.future.cancelled()
			and not (task.token and task.token.is_cancelled())
			and (task.request is None or (task.request.epoch == self._epoch
				and not task.request.failed)))

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
				self._current_request = task.request
				self._current_phase = "starting"
				self._current_indexes = set()
				if task.wait_done:
					self._current_done_event = threading.Event()
		if not valid:
			task.future.cancel()
			return

		failed = False
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
				if valid and task.wait_done:
					# A core can emit done synchronously from speak().
					self._current_phase = "awaiting_done"
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
			done = self._current_done_event
			while True:
				with self._state_cond:
					valid = self._valid_locked(task)
				if not valid:
					task.future.cancel()
					return
				# Cancellation sets this event; there is no polling timeout.
				done.wait()
				with self._state_cond:
					valid = self._valid_locked(task)
				if not valid:
					task.future.cancel()
					return
				if done.is_set():
					task.future.set_result(True)
					return
		except Exception as e:
			if task.request is not None:
				with self._state_cond:
					if task.request.epoch == self._epoch and not task.token.is_cancelled():
						task.request.failed = True
						task.token.cancel()
						failed = True
			task.future.set_exception(e)
			log.error("SpeechExecutor task error", exc_info=True)
		finally:
			if failed and task.expected_core is not None:
				try:
					task.expected_core.cancel()
				except Exception:
					log.debug("Failed to stop failed core", exc_info=True)
			with self._state_cond:
				self._current_task = None
				self._current_request = None
				self._current_phase = None
				self._current_done_event = None
				self._current_indexes = set()
				notify_done = self._finish_task_locked(task)
			if notify_done and getSynth() is self.owner:
				with self._delivery_lock:
					with self._state_cond:
						valid = task.request.epoch == self._epoch
					if valid:
						synthDoneSpeaking.notify(synth=self.owner)

	def _finish_task_locked(self, task):
		request = task.request
		if request is None:
			return False
		request.remaining -= 1
		if request.remaining == 0:
			self._requests.pop(request.request_id, None)
		if (request.has_speech and not request.done_sent and request.epoch == self._epoch
			and (request.failed or (request.remaining == 0 and not request.token.is_cancelled()))):
			request.done_sent = True
			return True
		return False
