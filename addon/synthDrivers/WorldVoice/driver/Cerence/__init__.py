import languageHandler
import locale
import threading
import weakref
from contextlib import contextmanager
from ctypes import POINTER, c_char_p, c_size_t, c_void_p, cast, byref, sizeof, string_at
from dataclasses import dataclass
from io import BytesIO
from synthDriverHandler import LanguageInfo
from logHandler import log

from . import driver as base
from .driver import SynthDriver as BaseSynthDriver, TtsSetParamList, ProcessText2Speech as BaseProcessText2Speech
from .driver import ttsapi
from .driver.ttsapi.veTypes import (
	VE_PARAM_LANGUAGE, VE_PARAM_VOICE_OPERATING_POINT, VE_CBOUTNOTIFY,
	VE_OUTDATA, VE_MARKINFO, VE_INTEXT, VE_NORM_TEXT, VE_MSG_OUTBUFREQ, VE_MSG_OUTBUFDONE,
	VE_MSG_ENDPROCESS, VE_MRK_BOOKMARK, NUAN_OK, NUAN_E_TTS_USERSTOP,
)
from synthDrivers.WorldVoice.driver import Voice, getVoiceKey
from synthDrivers.WorldVoice.driver.arabic_text import break_repeated_runs
from synthDrivers.WorldVoice.driver.chunker import split_speech_text_pieces
from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import CallbackGate, DrainSupport, unverified_drain_support
from ...runtime.segmentLifecycle import SegmentLifecycle
from ...runtime.session import CancellationView


_PROFILE = "cerence-ttsapi-0x0520-unverified"
_QUIESCENCE_REASON = (
	"The loaded Cerence ttsapi SDK has no verified callback-exclusion contract after "
	"ve_ttsProcessText2Speech returns; SDK version/build provenance and the "
	"NVDA playback profile are unverified"
)
_RETAINED_CALLBACKS = []


class _SilenceGate(threading.Event):
	def __init__(self):
		super().__init__()
		self._token = None
		self._inside_native_call = False

	def cancelled(self):
		return super().is_set() or self.token_cancelled()

	def token_cancelled(self):
		return bool(self._token and self._token.is_cancelled())

	def is_set(self):
		if not self._inside_native_call:
			log.debug("Cerence callback outside native call")
		return self.cancelled() or not self._inside_native_call

	def isSet(self):
		return self.is_set()

	def clear(self):
		log.debug("Cerence driver clear blocked by WorldVoice guard")

	def begin(self, token):
		self._token = token
		threading.Event.clear(self)


class _GuardedPlayer:
	def __init__(self, real_player, gate, driver=None):
		self._real = real_player
		self._gate = gate
		self._driver = weakref.ref(driver) if driver is not None else None

	def feed(self, *args, **kwargs):
		if self._gate.cancelled():
			return
		try:
			return self._real.feed(*args, **kwargs)
		finally:
			if self._gate.cancelled():
				self._real.stop()

	def idle(self):
		driver = self._driver() if self._driver is not None else None
		if driver is not None:
			return driver._idle_player()
		if not self._gate.cancelled():
			self._real.idle()

	def __getattr__(self, name):
		return getattr(self._real, name)


class _SpeechWork:
	"""One synchronous batch; errors are delivered after callback retirement."""
	def __init__(self, token, playback=None, completion=None):
		self.token = token
		self.playback = playback
		self.completion = completion
		self._lock = threading.Lock()
		self._active = True
		self.error = None
		self.drained = False
		self.operation = None
		self.cancelled = False

	def is_valid(self):
		with self._lock:
			return self._active and self.error is None and not (
				self.token and self.token.is_cancelled())

	def cancel(self):
		with self._lock:
			self._active = False
			self.cancelled = True
		if self.playback is not None:
			self.playback.cancel()
		if self.completion is not None:
			self.completion.set()

	def fault(self, error):
		with self._lock:
			if self.error is None:
				self.error = error


@dataclass
class _NativeWork:
	work: _SpeechWork
	instance: object
	call_token: object = None
	admitting: bool = True
	callbacks: int = 0
	producer: object = None


class _SegmentCallbackLease:
	def __init__(self, gate_lease, producer, lifecycle, work):
		self._gate_lease = gate_lease
		self.producer = producer
		self._lifecycle = lifecycle
		self.work = work

	def close(self):
		try:
			self._gate_lease.close()
		finally:
			self._lifecycle.retire_producer(self.producer)


class ProcessText2Speech(BaseProcessText2Speech):
	def __call__(self):
		# The inner ttsapi function drops the native result. Preserve USERSTOP
		# and native errors at the same synchronous SDK boundary instead.
		text = self._text.encode("utf-8", "replace")
		data = VE_INTEXT()
		data.eTextFormat = VE_NORM_TEXT
		data.cntTextLength = len(text)
		data.szInText = cast(c_char_p(text), c_void_p)
		native = ttsapi.veDll.ve_ttsProcessText2Speech
		# The installed errcheck maps OK and USERSTOP to None. Clone the
		# ctypes callable with its original ABI/argument/result declarations;
		# never remove or replace the shared function's checker, even briefly.
		raw = type(native)(cast(native, c_void_p).value)
		raw.restype = native.restype
		raw.argtypes = native.argtypes
		checker = native.errcheck
		args = (self._instance, byref(data))
		result = raw(*args)
		if checker is not None:
			checker(result, native, args)
		if result not in (NUAN_OK, NUAN_E_TTS_USERSTOP):
			raise RuntimeError(f"Cerence native synthesis failed with result {result}")
		return result


class _LegacyLease:
	"""Preserve legacy compatibility without asserting SDK quiescence."""
	def __init__(self, driver, native):
		self._driver = driver
		self.native = native
		self.work = native.work

	def close(self):
		with self._driver._speechStateLock:
			self.native.callbacks -= 1
			self._driver._speechStateLock.notify_all()


class _ContextualCerenceCallback(base.VECallback):
	"""Constructor-installed native callback; never borrows a later call's work."""
	def __init__(self, driver, player, isSilence, onIndexReached):
		super().__init__(player, isSilence, onIndexReached)
		self._driver = weakref.ref(driver)
		# The base stores a bound method; use a weak trampoline instead.
		self._onIndexReached = self._index
		self._processingLock = threading.Lock()

	def _index(self, index):
		driver = self._driver() if self._driver is not None else None
		if driver is not None:
			driver._onIndexReached(index)

	def __call__(self, instance, userData, message):
		driver = self._driver() if self._driver is not None else None
		if driver is None:
			return NUAN_E_TTS_USERSTOP
		if not driver._guard_installed:
			return super().__call__(instance, userData, message)
		lease, native = driver._admit_callback(instance)
		if lease is None:
			# Legacy ENDPROCESS historically acknowledges cancellation. It
			# cannot flush or clear anything without an admitted call lease.
			if native is not None and native.work.playback is None and (
				message.contents.eMessage == VE_MSG_ENDPROCESS):
				return NUAN_OK
			return NUAN_E_TTS_USERSTOP
		work = lease.work
		driver._callbackLocal.depth = getattr(driver._callbackLocal, "depth", 0) + 1
		try:
			with self._processingLock:
				if not work.is_valid():
					return NUAN_E_TTS_USERSTOP
				message_type = message.contents.eMessage
				if message_type == VE_MSG_OUTBUFREQ:
					data = cast(message.contents.pParam, POINTER(VE_OUTDATA)).contents
					data.pOutPcmBuf = cast(self._pcmBuf, c_void_p)
					data.cntPcmBufLen = base.pcmBufLen
					data.pMrkList = cast(self._markBuf, POINTER(VE_MARKINFO))
					data.cntMrkListLen = base.markBufSize * sizeof(VE_MARKINFO)
				elif message_type == VE_MSG_OUTBUFDONE:
					data = cast(message.contents.pParam, POINTER(VE_OUTDATA)).contents
					if data.cntPcmBufLen > base.pcmBufLen or data.cntMrkListLen > base.markBufSize:
						raise ValueError("Cerence output exceeds allocated PCM/marker buffers")
					if data.cntPcmBufLen:
						if self._ensureSonicStream():
							self.sonicStream.writeShort(data.pOutPcmBuf, data.cntPcmBufLen // 2)
							output = self.sonicStream.readShort()
							if output:
								self._feedBuf.write(bytes(output))
							if self._feedBuf.tell() >= base.pcmBufLen:
								driver._feed_callback(work, self._feedBuf.getvalue(), lease)
								self._feedBuf = BytesIO()
						else:
							driver._feed_callback(work, string_at(data.pOutPcmBuf, data.cntPcmBufLen), lease)
					if not work.is_valid():
						self._feedBuf = BytesIO()
						return NUAN_E_TTS_USERSTOP
					for i in range(int(data.cntMrkListLen)):
						if not work.is_valid():
							return NUAN_E_TTS_USERSTOP
						if data.pMrkList[i].eMrkType == VE_MRK_BOOKMARK:
							self._onIndexReached(int(data.pMrkList[i].szValue))
				elif message_type == VE_MSG_ENDPROCESS:
					# ENDPROCESS flushes this chunk only. It supplies no drain
					# or native callback-exclusion evidence.
					if self._sonicEnabled and self.sonicStream is not None:
						self.sonicStream.flush()
						output = self.sonicStream.readShort()
						if output and work.is_valid():
							self._feedBuf.write(bytes(output))
					if self._feedBuf.tell() and work.is_valid():
						driver._feed_callback(work, self._feedBuf.getvalue(), lease)
					self._feedBuf = BytesIO()
				return NUAN_OK if work.is_valid() else NUAN_E_TTS_USERSTOP
		except Exception as error:
			work.fault(error)
			driver._close_admission(native)
			log.error("WorldVoice Cerence callback failed", exc_info=True)
			return NUAN_E_TTS_USERSTOP
		finally:
			# Retain ownership through the final stop; new work cannot reset
			# the gate or use the player until this lease has exited.
			try:
				if not work.is_valid():
					driver._real_player.stop()
			except Exception as error:
				work.fault(error)
			finally:
				lease.close()
				driver._callbackLocal.depth -= 1

	def detach(self):
		self._driver = None
		self._player = None
		self.sonicStream = None
		self._feedBuf = BytesIO()


class SynthDriver(BaseSynthDriver):
	def __init__(self):
		self._guard_installed = False
		self._speechStateLock = threading.Condition()
		self._speechRunLock = threading.Lock()
		self._segmentGate = CallbackGate()
		self._segmentLifecycle = SegmentLifecycle(self)
		self._currentWork = None
		self._segmentWorks = set()
		self._nativeWork = None
		self._segmentBlockedError = None
		self._legacyUsed = False
		self._stops = 0
		self._paused = False
		self._pauseRevision = 0
		self._pauses = 0
		self._terminated = False
		self._callbackLocal = threading.local()
		self._speechLocal = threading.local()
		self._playerLocal = threading.local()
		self._terminationLocal = threading.local()
		self._playerClosing = False
		self._terminationRequested = False
		self._terminationCleaning = False
		self._terminationDone = threading.Event()
		self._terminationError = None
		self._initialize_native()
		self._install_guard()

	def _initialize_native(self):
		# The inner constructor hardcodes VECallback. Build its resources here
		# so the owned callback is registered before the first ttsapi.open.
		resources = base.getResourcePaths()
		if not resources:
			raise RuntimeError("no resources available")
		ttsapi.initialize(resources)
		self._instanceCache = {}
		try:
			device = base.config.conf["audio"]["outputDevice"]
		except KeyError:
			device = base.config.conf["speech"]["outputDevice"]
		self._player = base.nvwave.WavePlayer(channels=1, samplesPerSec=22050,
			bitsPerSample=16, outputDevice=device)
		self._isSilence = threading.Event()
		self._veCallbackHandler = _ContextualCerenceCallback(self, self._player,
			self._isSilence, self._onIndexReached)
		self._veCallback = VE_CBOUTNOTIFY(self._veCallbackHandler)
		self._resources = base.getAvailableResources()
		self._voice = next(iter(self.availableVoices))
		self._normalization = "OFF"
		self._rateBoost = False

	def _install_guard(self):
		callback = getattr(self, "_veCallbackHandler", None)
		if callback is None or not all(
			hasattr(obj, name)
			for obj, name in (
				(self, "_isSilence"), (self, "_player"),
				(callback, "_isSilence"), (callback, "_player"), (callback, "_feedBuf"),
			)
		):
			log.warning("Cerence cancellation guard unavailable; using original driver")
			return
		original = (self._isSilence, self._player, callback._isSilence, callback._player)
		gate = _SilenceGate()
		player = _GuardedPlayer(self._player, gate, self)
		try:
			self._isSilence = gate
			callback._isSilence = gate
			self._player = player
			callback._player = player
		except Exception:
			restoration_errors = []
			for obj, name, value in (
				(self, "_isSilence", original[0]), (self, "_player", original[1]),
				(callback, "_isSilence", original[2]), (callback, "_player", original[3]),
			):
				try:
					setattr(obj, name, value)
				except Exception as error:
					restoration_errors.append(error)
					log.warning("Cerence cancellation guard restoration failed", exc_info=True)
			log.warning("Cerence cancellation guard installation failed", exc_info=True)
			if restoration_errors:
				raise RuntimeError("Cerence cancellation guard restoration failed") from restoration_errors[0]
			return
		self._real_player = original[1]
		self._guard_installed = True

	@property
	def supportsCancellationToken(self):
		return self._guard_installed

	def get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport:
		if not self._guard_installed:
			return DrainSupport(False, _PROFILE, "Cerence cancellation guard installation is unavailable")
		return unverified_drain_support(_PROFILE, "SDK callback quiescence and physical playback are")

	def _confirm_native_quiescence(self, native):
		# Explicit activation override; retain the callback guard and idle barrier.
		return None

	def speak_segment(self, commands: SpeechCommands, token: CancellationView, *,
		context: PlaybackContext, on_event: SegmentEventSink) -> None:
		completion = threading.Event()
		def deliver(event):
			try:
				on_event(event)
			finally:
				completion.set()
		with self._speechStateLock:
			admission_error = self._segmentBlockedError
			if admission_error is None:
				try:
					operation = self._segmentLifecycle.accept(context, token, deliver)
				except RuntimeError as error:
					admission_error = error
				else:
					work = _SpeechWork(token, operation.work, completion)
					work.operation = operation
					operation._ve_work = work
					operation._ve_natives = []
					self._segmentWorks.add(work)
		if admission_error is not None:
			self._segmentLifecycle.reject_new(context, token, deliver, admission_error)
			self._wait_segment_delivery(completion, token)
			return
		try:
			try:
				self._segmentLifecycle.run(operation, tuple(commands))
			except RuntimeError as error:
				# A prior fatal resource fault rejects before this operation owns
				# native/player state. Preserve this request's original context.
				self._segmentLifecycle.reject_new(context, token, deliver, error.__cause__ or error)
				self._wait_segment_delivery(completion, token)
				return
			if operation._retired and not work.cancelled and not token.is_cancelled():
				self._wait_segment_delivery(completion, token)
		finally:
			with self._speechStateLock:
				self._segmentWorks.discard(work)
			if self._terminationRequested:
				self._finish_termination()

	def _wait_segment_delivery(self, completion, token):
		# A listener may synchronously ask for another segment. The coordinator
		# owns a single delivery thread, so it cannot wait for its own callback.
		if not token.is_cancelled() and threading.current_thread() is not self._segmentLifecycle._delivery_thread:
			while not completion.wait(0.05):
				# External tokens have no notification hook. Poll only while the
				# caller is waiting; direct cancellation sets completion itself.
				if token.is_cancelled():
					return

	# The inner driver still parses settings and splits text. Its synchronous
	# native calls and callback gate form the SDK boundary for this operation.
	def submit_native(self, operation, commands):
		self._run_speech(commands, operation._ve_work)
		if operation._ve_work.error is not None:
			raise operation._ve_work.error

	def request_stop(self, operation):
		with self._speechStateLock:
			self._stops += 1
			self._playerLocal.depth = getattr(self._playerLocal, "depth", 0) + 1
			self._speechStateLock.notify_all()
		try:
			self._real_player.stop()
		finally:
			with self._speechStateLock:
				self._stops -= 1
				self._speechStateLock.notify_all()
			# Contextual teardown belongs to speak_segment after the coordinator
			# retires this operation. Finishing here would wait on our own stop.
			self._playerLocal.depth -= 1

	def wait_native_boundary(self, operation):
		if operation._ve_work.error is not None:
			raise operation._ve_work.error

	def wait_native_retired(self, operation):
		for native in operation._ve_natives:
			if native.call_token is not None:
				self._segmentGate.wait_retired(native.call_token)

	def wait_playback_drained(self, operation):
		work = operation._ve_work
		if work.error is not None:
			raise work.error
		if not work.is_valid():
			return
		self._playerLocal.depth = getattr(self._playerLocal, "depth", 0) + 1
		try:
			self._real_player.idle()
			with self._speechStateLock:
				self._speechStateLock.wait_for(lambda: (
					self._pauses == 0 and not self._paused) or not work.is_valid())
			if work.error is not None:
				raise work.error
			work.drained = work.is_valid() and not self._isSilence.cancelled()
		finally:
			# The owning run clears the resource-busy flag before teardown.
			self._playerLocal.depth -= 1

	def speak(self, speechSequence, cancellationToken=None):
		if not self._guard_installed:
			return super().speak(speechSequence)
		work = _SpeechWork(cancellationToken)
		result = self._run_speech(speechSequence, work)
		if work.error is not None:
			raise work.error
		return result

	def _run_speech(self, commands, work):
		self._speechLocal.depth = getattr(self._speechLocal, "depth", 0) + 1
		try:
			return self._run_speech_locked(commands, work)
		finally:
			self._speechLocal.depth -= 1
			# A notification may request termination while this thread owns
			# the native batch/lease. Close resources only after releasing it.
			if self._terminationRequested and work.operation is None:
				self._finish_termination()

	@contextmanager
	def _speech_run_ownership(self, work):
		# A contextual operation releases the run lock after native submission
		# but still owns the shared native/player resource through its final
		# playback barrier and stop retirement. Ordinary speech waits for that
		# coordinator retirement outside the run lock, because the contextual
		# owner needs the run lock to submit.
		lifecycle = self._segmentLifecycle
		while True:
			if work.operation is None:
				while work.is_valid():
					with lifecycle._condition:
						if not lifecycle._resource_busy:
							break
						# External tokens have no notification hook.
						lifecycle._condition.wait(0.05)
				if not work.is_valid():
					yield False
					return
			with self._speechRunLock:
				if work.operation is None:
					with lifecycle._condition:
						busy = lifecycle._resource_busy
					if busy:
						# A contextual run acquired the resource before this
						# request acquired the run lock. Let it submit first.
						continue
				yield True
				return

	def _run_speech_locked(self, commands, work):
		with self._speech_run_ownership(work) as owned:
			if not owned:
				return
			with self._speechStateLock:
				self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
				if not work.is_valid():
					return
				if not self._guard_installed:
					work.fault(RuntimeError("Cerence cancellation guard installation is unavailable"))
					return
				if self._terminated:
					work.fault(RuntimeError("Cerence driver has terminated"))
					return
				if self._segmentBlockedError is not None:
					work.fault(self._segmentBlockedError)
					return
				if work.playback is not None and self._legacyUsed:
					work.fault(RuntimeError("Legacy Cerence callback lifetimes are unproven; cannot enter correlated mode"))
					return
				self._currentWork = work
				self._legacyUsed |= work.playback is None
				self._isSilence.begin(work.token)
			try:
				self._reset_callback_audio()
				return super().speak(commands)
			except Exception as error:
				work.fault(error)
			finally:
				self._isSilence._inside_native_call = False
				with self._speechStateLock:
					self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
					self._currentWork = None

	def _reset_callback_audio(self):
		callback = self._veCallbackHandler
		callback._feedBuf = BytesIO()
		if getattr(callback, "_sonicEnabled", False):
			callback.sonicStream = None
			callback._sonicEnabled = False
			callback._sonicInitTried = False

	def _speak(self, voiceInstance, chunks):
		if not self._guard_installed:
			return super()._speak(voiceInstance, chunks)
		work = self._currentWork
		if work is None:
			return
		for piece in split_speech_text_pieces(break_repeated_runs("".join(chunks))):
			if not work.is_valid() or self._isSilence.cancelled():
				break
			producer = self._segmentLifecycle.admit_producer(work.operation) if work.operation is not None else None
			call = self._segmentGate.begin_native(work) if work.playback is not None else None
			native = _NativeWork(work, voiceInstance, call, producer=producer)
			if work.operation is not None:
				work.operation._ve_natives.append(native)
			with self._speechStateLock:
				self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
				self._nativeWork = native
				self._isSilence._inside_native_call = True
			invoked = False
			try:
				if work.is_valid():
					invoked = True
					result = ProcessText2Speech(voiceInstance, piece)()
					if result == NUAN_E_TTS_USERSTOP and work.is_valid():
						raise RuntimeError("Cerence native synthesis returned USERSTOP")
			except Exception as error:
				work.fault(error)
			finally:
				self._close_admission(native)
				self._isSilence._inside_native_call = False
				if call is not None:
					try:
						if invoked:
							self._confirm_native_quiescence(native)
						self._segmentGate.finish_native(call)
					except Exception as error:
						work.fault(error)
						self._segmentBlockedError = error
					finally:
						self._segmentGate.wait_retired(call)
				else:
					with self._speechStateLock:
						self._speechStateLock.wait_for(lambda: native.callbacks == 0)
				with self._speechStateLock:
					self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
					if self._segmentBlockedError is None:
						self._nativeWork = None
				if self._segmentBlockedError is not None:
					try:
						self._real_player.stop()
					except Exception as error:
						work.fault(error)
				if producer is not None:
					self._segmentLifecycle.retire_producer(producer)

	def _close_admission(self, native):
		with self._speechStateLock:
			native.admitting = False
		if native.call_token is not None:
			self._segmentGate.close(native.call_token)

	def _admit_callback(self, instance):
		with self._speechStateLock:
			native = self._nativeWork
			if native is None or not native.admitting or not isinstance(
				instance, ttsapi.veTypes.VE_HSAFE) or instance != native.instance:
				return None, None
			if not native.work.is_valid():
				return None, native
			if native.call_token is None:
				native.callbacks += 1
				return _LegacyLease(self, native), native
			lease = self._segmentGate.enter_callback()
			if lease is not None and lease.call_token is not native.call_token:
				lease.close()
				return None, None
			if lease is not None:
				producer = self._segmentLifecycle.admit_producer(native.work.operation, native.producer)
				if producer is None:
					lease.close()
					return None, native
				lease = _SegmentCallbackLease(lease, producer, self._segmentLifecycle, native.work)
			return lease, native

	def _feed_callback(self, work, data, callback_lease=None):
		# The callback lease owns the final stop, including feed failures.
		producer = None
		if work.operation is not None and callback_lease is not None:
			producer = self._segmentLifecycle.admit_producer(work.operation, callback_lease.producer)
		try:
			if work.is_valid():
				self._real_player.feed(data)
		finally:
			if producer is not None:
				self._segmentLifecycle.retire_producer(producer)

	def _idle_player(self):
		work = self._currentWork
		if work is not None and work.operation is not None:
			return
		if self._isSilence.cancelled() or (work is not None and not work.is_valid()):
			return
		self._real_player.idle()
		if work is not None:
			with self._speechStateLock:
				self._speechStateLock.wait_for(lambda: (
					self._pauses == 0 and not self._paused) or not work.is_valid())
				work.drained = work.is_valid() and not self._isSilence.cancelled()

	def cancel(self):
		if not self._guard_installed:
			return super().cancel()
		with self._speechStateLock:
			if self._playerClosing:
				# Another thread sealed termination first, possibly an ordinary
				# request released by the coordinator's terminate. The player is
				# closing, but a contextual caller may still await delivery.
				for pending in self._segmentWorks:
					pending.cancel()
				return
			self._isSilence.set()
			# WavePlayer.stop clears its own pause state. Keep the final idle
			# predicate in sync so fresh speech does not await a stale pause.
			self._paused = False
			self._pauseRevision += 1
			work = self._currentWork
			if work is not None:
				work.cancel()
			for pending in self._segmentWorks:
				pending.cancel()
			operations = tuple(pending.operation for pending in self._segmentWorks
				if pending.operation is not None)
			native = self._nativeWork
			if native is not None:
				native.admitting = False
			self._stops += 1
			self._playerLocal.depth = getattr(self._playerLocal, "depth", 0) + 1
			self._speechStateLock.notify_all()
		if native is not None and native.call_token is not None:
			self._segmentGate.close(native.call_token)
		for operation in operations:
			self._segmentLifecycle.cancel(operation)
		try:
			self._real_player.stop()
		finally:
			with self._speechStateLock:
				self._stops -= 1
				self._speechStateLock.notify_all()
			self._retire_player_operation()

	def _onIndexReached(self, index):
		if not self._guard_installed:
			return super()._onIndexReached(index)
		work = self._currentWork
		if index is None:
			if work is not None and work.playback is not None:
				return
			if self._isSilence.token_cancelled() or (work is not None and work.error is not None):
				return
		elif self._isSilence.cancelled() or (work is not None and not work.is_valid()):
			return
		return super()._onIndexReached(index)

	def pause(self, switch):
		if not self._guard_installed:
			return super().pause(switch)
		with self._speechStateLock:
			if self._terminated:
				raise RuntimeError("Cerence driver has terminated")
			self._paused = switch
			self._pauseRevision += 1
			self._pauses += 1
			self._playerLocal.depth = getattr(self._playerLocal, "depth", 0) + 1
			self._speechStateLock.notify_all()
		try:
			while True:
				with self._speechStateLock:
					self._speechStateLock.wait_for(lambda: self._stops == 0)
					if self._terminated:
						break
					revision, target = self._pauseRevision, self._paused
				# Cancel can stop immediately while this player operation runs.
				# Reapply a newer intent if an old pause took effect after stop.
				super().pause(target)
				with self._speechStateLock:
					if revision == self._pauseRevision:
						break
		except Exception as error:
			with self._speechStateLock:
				# A raised pause/resume may have partially changed the player.
				# Block this core permanently instead of guessing its state.
				if self._segmentBlockedError is None:
					self._segmentBlockedError = error
				if self._currentWork is not None:
					self._currentWork.fault(error)
				for pending in self._segmentWorks:
					pending.fault(error)
				native = self._nativeWork
				if native is not None:
					native.admitting = False
				self._pauseRevision += 1
				self._stops += 1
				self._speechStateLock.notify_all()
			if native is not None and native.call_token is not None:
				self._segmentGate.close(native.call_token)
			try:
				# Release a real idle/feed blocked by the uncertain pause state.
				self._real_player.stop()
			except Exception:
				log.error("WorldVoice pause failure cleanup failed", exc_info=True)
			finally:
				with self._speechStateLock:
					self._stops -= 1
					self._speechStateLock.notify_all()
			raise
		finally:
			with self._speechStateLock:
				# Fresh speech and drain publication wait for real pause/resume
				# retirement, not merely the desired state above.
				self._pauses -= 1
				self._speechStateLock.notify_all()
			self._retire_player_operation()

	def _is_reentrant_termination(self):
		return bool(getattr(self._callbackLocal, "depth", 0) or
			getattr(self._speechLocal, "depth", 0) or
			getattr(self._playerLocal, "depth", 0) or
			getattr(self._terminationLocal, "cleaning", False))

	def _retire_player_operation(self):
		self._playerLocal.depth -= 1
		if self._terminationRequested and not self._is_reentrant_termination():
			self._finish_termination()

	def terminate(self):
		if not self._guard_installed:
			return super().terminate()
		reentrant = self._is_reentrant_termination()
		with self._speechStateLock:
			first = not self._terminationRequested
			self._terminationRequested = True
			self._terminated = True
		if first:
			self._segmentLifecycle.terminate()
			try:
				self.cancel()
			except Exception as error:
				self._terminationError = error
		if reentrant:
			# The caller may own speech, a callback, a player operation or
			# cleanup itself. Its outer owner finishes after retirement.
			return
		self._finish_termination()
		if self._terminationError is not None:
			raise self._terminationError

	def _finish_termination(self):
		if self._is_reentrant_termination():
			return
		with self._speechStateLock:
			first = not self._terminationCleaning
			self._terminationCleaning = True
		if not first:
			self._terminationDone.wait()
			return
		self._terminationLocal.cleaning = True
		try:
			# Keep native/player resources alive until the coordinator retires its stop.
			with self._segmentLifecycle._condition:
				self._segmentLifecycle._condition.wait_for(
					lambda: not self._segmentLifecycle._resource_busy)
			with self._speechRunLock:
				with self._speechStateLock:
					self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
					# Seal atomically with the zero-operation barrier so a late
					# cancel cannot start another stop against closing resources.
					self._playerClosing = True
				callback = self._veCallback
				self._veCallbackHandler.detach()
				# The native destruction API also lacks pointer-lifetime proof.
				_RETAINED_CALLBACKS.append(callback)
				super().terminate()
		except Exception as error:
			if self._terminationError is None:
				self._terminationError = error
			log.error("WorldVoice Cerence termination failed", exc_info=True)
		finally:
			self._terminationLocal.cleaning = False
			self._terminationDone.set()


CancellableSynthDriver = SynthDriver


class Voice(Voice):
	extra_capabilities = frozenset({"waitfactor", "variant"})
	core = None
	engine = "Cerence"
	synth_driver_class = SynthDriver

	def applyEngineSettings(self, core, snapshot):
		instance = core.getVoiceInstance(snapshot.voice_id)
		if getattr(self, "_defaultVariantCore", None) is not core:
			self._defaultVariant = core.getParameter(
				instance, VE_PARAM_VOICE_OPERATING_POINT, type_=str)
			self._defaultVariantCore = core
		if snapshot.variant != "default" and snapshot.variant not in core.availableVariants:
			raise ValueError(f"Unavailable variant: {snapshot.variant}")
		selected = self._defaultVariant if snapshot.variant == "default" else snapshot.variant
		TtsSetParamList(instance, (VE_PARAM_VOICE_OPERATING_POINT, selected))()
		core.waitfactor = snapshot.waitfactor

	@property
	def variants(self):
		try:
			language = self.core.getParameter(self.core.getVoiceInstance(self.id), VE_PARAM_LANGUAGE, type_=str) # FIXME: store language...
			dbs = ttsapi.getSpeechDBList(language, self.id)
			return [{
				"id": item,
				"name": item,
			} for item in dbs]
		except BaseException:
			return []

	@classmethod
	def voices(cls):
		result = []
		if not cls.ready() or not cls.core:
			return result

		try:
			voices = cls.core.availableVoices.values()
		except Exception:
			return result

		def clean(s):
			return s.strip("b'").strip("'") if (s.startswith("b'") and s.endswith("'")) else s

		for voice in voices:
			localeName = voice.language or "unknown"
			langDescription = languageHandler.getLanguageDescription(localeName)
			if not langDescription:
				if " - " in voice.displayName:
					langDescription = voice.displayName.split(" - ", 1)[1]
					langDescription = clean(langDescription)
				else:
					langDescription = localeName
			name = voice.id
			result.append({
				"id": name,
				"name": getVoiceKey(cls.engine, name),
				"locale": localeName,
				"language": localeName,
				"langDescription": langDescription,
				"description": "%s - %s [%s]" % (name, langDescription, cls.engine),
				"engine": "Cerence",
			})

		return result
