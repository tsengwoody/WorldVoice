import queue
import threading
import weakref
from contextlib import contextmanager
from ctypes import POINTER, byref, c_char_p, c_void_p, cast, sizeof, string_at
from dataclasses import dataclass
from io import BytesIO

import languageHandler
from logHandler import log
from synthDrivers.WorldVoice.driver import Voice as BaseVoice, getVoiceKey
from synthDrivers.WorldVoice.text.arabic import break_repeated_runs
from synthDrivers.WorldVoice.text.chunker import split_speech_text_pieces

from ...runtime.engineControl import StopGate
from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import DrainProfile, DrainSupport, unverified_drain_support
from ...runtime.segmentHost import NativeStrategy, SegmentDrainCore, SegmentHost
from ...runtime.session import CancellationView
from . import driver as base
from .driver import (
	ProcessText2Speech as BaseProcessText2Speech,
	SynthDriver as BaseSynthDriver,
	TtsSetParamList,
	ttsapi,
)
from .driver.ttsapi.veTypes import (
	NUAN_E_TTS_USERSTOP,
	NUAN_OK,
	VE_CBOUTNOTIFY,
	VE_INTEXT,
	VE_MARKINFO,
	VE_MRK_BOOKMARK,
	VE_MSG_ENDPROCESS,
	VE_MSG_OUTBUFDONE,
	VE_MSG_OUTBUFREQ,
	VE_NORM_TEXT,
	VE_OUTDATA,
	VE_PARAM_LANGUAGE,
	VE_PARAM_VOICE_OPERATING_POINT,
)

_PROFILE = "cerence-ttsapi-0x0520-unverified"
_RETAINED_CALLBACKS = []
# Ordinary speech proves no barrier: its idle and DONE stay with the inner
# driver's DoneSpeaking, its failures are recorded errors, and its token is
# the worker's to honour (a token-cancelled request is not a failure).
_ORDINARY_BARRIERS = frozenset()


def _stripBytesRepr(text):
	"""Turn a bytes repr like "b'English'" into its text, keeping every letter."""
	if len(text) >= 3 and text.startswith("b'") and text.endswith("'"):
		return text[2:-1]
	return text


class _CerencePort:
	"""Private names of the vendored inner Cerence driver this wrapper reads, writes or overrides.

	Not used at runtime; tests/test_native_strategy_guards.py pins these lists
	against the inner package, so an update of the vendored driver is checked here.
	"""

	INNER_PRIVATES = frozenset(
		{
			"_bgQueue",
			"_bgThread",
			"_ensureSonicStream",
			"_feedBuf",
			"_instanceCache",
			"_isSilence",
			"_markBuf",
			"_normalization",
			"_pcmBuf",
			"_player",
			"_rateBoost",
			"_resources",
			"_sonicEnabled",
			"_sonicInitTried",
			"_veCallback",
			"_veCallbackHandler",
			"_voice",
		},
	)
	INNER_OVERRIDES = frozenset({"_speak", "_onIndexReached"})


class _ThreadState(threading.local):
	"""Per-thread re-entry state; every thread starts outside callbacks, players and cleanup."""

	depth = 0
	cleaning = False


class _SilenceGate(threading.Event):
	def __init__(self):
		super().__init__()
		self._token = None
		self._insideNativeCall = False

	def cancelled(self):
		return super().is_set() or self.tokenCancelled()

	def tokenCancelled(self):
		return bool(self._token and self._token.is_cancelled())

	def is_set(self):
		if not self._insideNativeCall:
			log.debug("Cerence callback outside native call")
		return self.cancelled() or not self._insideNativeCall

	def isSet(self):
		return self.is_set()

	def clear(self):
		log.debug("Cerence driver clear blocked by WorldVoice guard")

	def begin(self, token):
		self._token = token
		threading.Event.clear(self)


class _GuardedPlayer:
	def __init__(self, realPlayer, gate, driver=None):
		self._real = realPlayer
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
			return driver._idlePlayer()
		if not self._gate.cancelled():
			self._real.idle()

	def __getattr__(self, name):
		return getattr(self._real, name)


@dataclass(eq=False)
class _CerenceRequest:
	"""Cerence data carried on a NativeRecord: its speech sequence and ordinary token."""

	commands: object
	token: object = None
	# Set on the inner BgThread when its Begin task ran (skipped: never spoken).
	began: bool = False
	skipped: bool = False


@dataclass(eq=False)
class _NativeCall:
	"""One synchronous ve_ttsProcessText2Speech call and its callback admission."""

	record: object
	instance: object
	admitting: bool = True


class _RecordTask:
	"""A task for the inner BgThread queue, bound to one NativeRecord."""

	def __init__(self, driver, record):
		self._driver = weakref.ref(driver)
		self.record = record


class _Begin(_RecordTask):
	def __call__(self):
		driver = self._driver()
		if driver is not None:
			driver._beginRecord(self.record)


class _NativeTask(_RecordTask):
	def __init__(self, driver, record, instance, text):
		super().__init__(driver, record)
		self._instance = instance
		self._text = text

	def __call__(self):
		driver = self._driver()
		if driver is not None:
			driver._runNative(self.record, self._instance, self._text)


class _Retire(_RecordTask):
	def __call__(self):
		driver = self._driver()
		if driver is not None:
			driver._retireRecord(self.record)


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
		if not driver._guardInstalled:
			return super().__call__(instance, userData, message)
		with driver._callbackAdmission(instance) as (record, call):
			if record is None:
				# Legacy ENDPROCESS historically acknowledges cancellation. It
				# cannot flush or clear anything without an admitted call.
				if (
					call is not None
					and call.record.operation is None
					and message.contents.eMessage == VE_MSG_ENDPROCESS
				):
					return NUAN_OK
				return NUAN_E_TTS_USERSTOP
			return self._process(driver, record, call, message)

	def _process(self, driver, record, call, message):
		host = driver._segmentHost
		try:
			with self._processingLock:
				if not driver._recordValid(record):
					return NUAN_E_TTS_USERSTOP
				messageType = message.contents.eMessage
				if messageType == VE_MSG_OUTBUFREQ:
					data = cast(message.contents.pParam, POINTER(VE_OUTDATA)).contents
					data.pOutPcmBuf = cast(self._pcmBuf, c_void_p)
					data.cntPcmBufLen = base.pcmBufLen
					data.pMrkList = cast(self._markBuf, POINTER(VE_MARKINFO))
					data.cntMrkListLen = base.markBufSize * sizeof(VE_MARKINFO)
				elif messageType == VE_MSG_OUTBUFDONE:
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
								driver._feedCallback(record, self._feedBuf.getvalue())
								self._feedBuf = BytesIO()
						else:
							driver._feedCallback(record, string_at(data.pOutPcmBuf, data.cntPcmBufLen))
					if not driver._recordValid(record):
						self._feedBuf = BytesIO()
						return NUAN_E_TTS_USERSTOP
					for i in range(int(data.cntMrkListLen)):
						if not driver._recordValid(record):
							return NUAN_E_TTS_USERSTOP
						if data.pMrkList[i].eMrkType == VE_MRK_BOOKMARK:
							self._onIndexReached(int(data.pMrkList[i].szValue))
				elif messageType == VE_MSG_ENDPROCESS:
					# ENDPROCESS flushes this chunk only. It supplies no drain
					# or native callback-exclusion evidence.
					if self._sonicEnabled and self.sonicStream is not None:
						self.sonicStream.flush()
						output = self.sonicStream.readShort()
						if output and driver._recordValid(record):
							self._feedBuf.write(bytes(output))
					if self._feedBuf.tell() and driver._recordValid(record):
						driver._feedCallback(record, self._feedBuf.getvalue())
					self._feedBuf = BytesIO()
				return NUAN_OK if driver._recordValid(record) else NUAN_E_TTS_USERSTOP
		except Exception as error:
			host.record_error(record, error)
			driver._closeAdmission(call)
			log.error("WorldVoice Cerence callback failed", exc_info=True)
			return NUAN_E_TTS_USERSTOP
		finally:
			# The callback keeps its admission through the final stop; the
			# worker cannot start another call until this consumer leaves.
			try:
				if not driver._recordValid(record):
					driver._realPlayer.stop()
			except Exception as error:  # noqa: BLE001 - recorded on the record; the segment fails
				host.record_error(record, error)

	def detach(self):
		self._driver = None
		self._player = None
		self.sonicStream = None
		self._feedBuf = BytesIO()


class _CerenceStrategy(NativeStrategy):
	"""Cerence's native queue: the inner BgThread, each record's tasks queued around speak()."""

	barriers = frozenset({"spoken", "idle"})

	def __init__(self, driver):
		self._driver = weakref.ref(driver)

	def admission_error(self, host):
		driver = self._driver()
		if not driver._guardInstalled:
			return RuntimeError("Cerence cancellation guard installation is unavailable")
		with driver._speechStateLock:
			if driver._terminated:
				return RuntimeError("Cerence driver has terminated")
			if driver._legacyUsed:
				return RuntimeError(
					"Legacy Cerence callback lifetimes are unproven; cannot enter correlated mode",
				)
		return None

	def submit(self, host, record, commands):
		driver = self._driver()
		if record.native is None:
			record.native = _CerenceRequest(commands)
		driver._enqueue(record, record.native.commands)

	def stop_native(self, host, record):
		self._driver()._stopPlayer()

	def stop_player(self, host):
		self._driver()._stopPlayer()

	def drain(self, host, record):
		driver = self._driver()
		with driver._playerOperation():
			try:
				driver._realPlayer.idle()
				with driver._speechStateLock:
					driver._speechStateLock.wait_for(
						lambda: (
							(driver._pauses == 0 and not driver._paused) or not driver._recordValid(record)
						),
					)
			except Exception as error:  # noqa: BLE001 - recorded on the record and latched: later speech is rejected
				# The player state is uncertain after a failed idle: reject successors.
				host.record_error(record, error)
				host.latch_control_error(error)
				return
			if driver._recordValid(record) and not driver._isSilence.cancelled():
				host.reach(record, "idle")


class SynthDriver(BaseSynthDriver, SegmentDrainCore):
	def __init__(self):
		self._guardInstalled = False
		self._speechStateLock = threading.Condition()
		self._segmentHost = SegmentHost("Cerence", _CerenceStrategy(self))
		self._submitting = None
		self._currentRecord = None
		self._doneOwner = None
		self._nativeCall = None
		self._legacyUsed = False
		self._stopGate = StopGate(self._speechStateLock)
		self._paused = False
		self._pauseRevision = 0
		self._pauses = 0
		self._terminated = False
		self._callbackLocal = _ThreadState()
		self._playerLocal = _ThreadState()
		self._terminationLocal = _ThreadState()
		self._playerClosing = False
		self._terminationRequested = False
		self._terminationCleaning = False
		self._terminationDone = threading.Event()
		self._terminationError = None
		self._initializeNative()
		self._installGuard()

	def _initializeNative(self):
		# The inner constructor hardcodes VECallback. Build its resources here
		# so the owned callback is registered before the first ttsapi.open.
		resources = base.getResourcePaths()
		if not resources:
			raise RuntimeError("no resources available")
		ttsapi.initialize(resources)
		self._instanceCache = {}
		self._bgQueue = queue.Queue()
		self._bgThread = base.BgThread(self._bgQueue)
		try:
			device = base.config.conf["audio"]["outputDevice"]
		except KeyError:
			device = base.config.conf["speech"]["outputDevice"]
		self._player = base.nvwave.WavePlayer(
			channels=1,
			samplesPerSec=22050,
			bitsPerSample=16,
			outputDevice=device,
		)
		self._isSilence = threading.Event()
		self._veCallbackHandler = _ContextualCerenceCallback(
			self,
			self._player,
			self._isSilence,
			self._onIndexReached,
		)
		self._veCallback = VE_CBOUTNOTIFY(self._veCallbackHandler)
		self._resources = base.getAvailableResources()
		self._voice = next(iter(self.availableVoices))
		self._normalization = "OFF"
		self._rateBoost = False

	def _installGuard(self):
		callback = getattr(self, "_veCallbackHandler", None)
		if callback is None or not all(
			hasattr(obj, name)
			for obj, name in (
				(self, "_isSilence"),
				(self, "_player"),
				(callback, "_isSilence"),
				(callback, "_player"),
				(callback, "_feedBuf"),
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
			restorationErrors = []
			for obj, name, value in (
				(self, "_isSilence", original[0]),
				(self, "_player", original[1]),
				(callback, "_isSilence", original[2]),
				(callback, "_player", original[3]),
			):
				try:
					setattr(obj, name, value)
				except Exception as error:
					restorationErrors.append(error)
					log.warning("Cerence cancellation guard restoration failed", exc_info=True)
			log.warning("Cerence cancellation guard installation failed", exc_info=True)
			if restorationErrors:
				raise RuntimeError("Cerence cancellation guard restoration failed") from restorationErrors[0]
			return
		self._realPlayer = original[1]
		self._guardInstalled = True

	@property
	def supportsCancellationToken(self):
		return self._guardInstalled

	def get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport:
		if not self._guardInstalled:
			return DrainSupport(False, _PROFILE, "Cerence cancellation guard installation is unavailable")
		return unverified_drain_support(_PROFILE, "SDK callback quiescence and physical playback are")

	def _confirmNativeQuiescence(self, call):
		# Explicit activation override; retain the callback guard and idle barrier.
		return None

	def speak_segment(
		self,
		commands: SpeechCommands,
		token: CancellationView,
		*,
		context: PlaybackContext,
		on_event: SegmentEventSink,
	) -> None:
		self._segmentHost.speak_segment(commands, token, context=context, on_event=on_event)

	def speak(self, speechSequence, cancellationToken=None):
		if not self._guardInstalled:
			return super().speak(speechSequence)
		with self._speechStateLock:
			if self._terminated:
				raise RuntimeError("Cerence driver has terminated")
			# Legacy callback lifetimes are unproven: correlated mode stays off
			# from the moment ordinary speech is requested.
			self._legacyUsed = True
		# Like the original add-on's BgThread queue: return once queued.
		self._segmentHost.enqueue(
			speechSequence,
			barriers=_ORDINARY_BARRIERS,
			native=_CerenceRequest(speechSequence, cancellationToken),
		)

	def _enqueue(self, record, commands):
		# The inner speak() converts on this thread and queues its native
		# chunks and DoneSpeaking; bracket them with this record's tasks.
		# Host admission (held by enqueue and by cancel) keeps the bracket whole.
		self._bgQueue.put(_Begin(self, record))
		self._submitting = record
		try:
			BaseSynthDriver.speak(self, commands)
		finally:
			self._submitting = None
			self._bgQueue.put(_Retire(self, record))

	def _recordValid(self, record):
		# Sealing (retire) does not invalidate the work; callback admission
		# already refuses sealed records.
		token = record.native.token if record.native is not None else None
		return (
			not record.cancelled
			and record.error is None
			and (record.work is None or record.work.is_valid())
			and not (token and token.is_cancelled())
		)

	def _beginRecord(self, record):
		host = self._segmentHost
		with self._speechStateLock:
			self._speechStateLock.wait_for(lambda: self._stopGate.clear and self._pauses == 0)
			record.native.began = True
			self._doneOwner = record
			if not self._recordValid(record) or record.abandoned or host.control_error is not None:
				record.native.skipped = True
			else:
				self._currentRecord = record
				host.begin(record)
				token = record.work.token if record.work is not None else record.native.token
				self._isSilence.begin(token)
		if record.native.skipped:
			host.abandon(record)
			return
		self._resetCallbackAudio()

	def _retireRecord(self, record):
		host = self._segmentHost
		if not record.native.skipped:
			self._isSilence._insideNativeCall = False
			if "spoken" in record.barriers and self._recordValid(record):
				host.reach(record, "spoken")
			with self._speechStateLock:
				self._speechStateLock.wait_for(lambda: self._stopGate.clear and self._pauses == 0)
			host.retire(record)
			if record.operation is None:
				host.forget(record)
		with self._speechStateLock:
			if self._currentRecord is record:
				self._currentRecord = None
			if self._doneOwner is record:
				self._doneOwner = None
			self._isSilence._token = None
			self._speechStateLock.notify_all()

	def _resetCallbackAudio(self):
		callback = self._veCallbackHandler
		callback._feedBuf = BytesIO()
		if getattr(callback, "_sonicEnabled", False):
			callback.sonicStream = None
			callback._sonicEnabled = False
			callback._sonicInitTried = False

	def _speak(self, voiceInstance, chunks):
		if not self._guardInstalled:
			return super()._speak(voiceInstance, chunks)
		record = self._submitting
		if record is None:
			return
		for piece in split_speech_text_pieces(break_repeated_runs("".join(chunks))):
			self._bgQueue.put(_NativeTask(self, record, voiceInstance, piece))

	def getParameters(self, instance, *idAndTypes):
		if not self._guardInstalled:
			return super().getParameters(instance, *idAndTypes)
		# Read pending settings like the inner driver, but without draining and
		# re-putting the queue: that could move a record's Begin behind its Retire.
		with self._bgQueue.mutex:
			tasks = list(self._bgQueue.queue)
		values = [None] * len(idAndTypes)
		for task in tasks:
			if isinstance(task, TtsSetParamList) and task.instance == instance:
				for id, value in task.idAndValues:
					for i, p in enumerate(idAndTypes):
						if id == p[0]:
							values[i] = value
		if None not in values:
			return values
		return ttsapi.getParamList(instance, *idAndTypes)

	def _runNative(self, record, voiceInstance, piece):
		host = self._segmentHost
		if record is not self._currentRecord or not self._recordValid(record) or self._isSilence.cancelled():
			return
		call = _NativeCall(record, voiceInstance)
		with self._speechStateLock:
			self._speechStateLock.wait_for(lambda: self._stopGate.clear and self._pauses == 0)
			self._nativeCall = call
			self._isSilence._insideNativeCall = True
		invoked = False
		try:
			if self._recordValid(record):
				invoked = True
				result = ProcessText2Speech(voiceInstance, piece)()
				if result == NUAN_E_TTS_USERSTOP and self._recordValid(record):
					raise RuntimeError("Cerence native synthesis returned USERSTOP")
		except Exception as error:
			log.error("WorldVoice Cerence native synthesis failed", exc_info=True)
			host.record_error(record, error)
		finally:
			self._closeAdmission(call)
			self._isSilence._insideNativeCall = False
			# Every callback admitted to this call returns before the next one.
			host.wait_consumers(record)
			blocked = None
			if invoked:
				try:
					self._confirmNativeQuiescence(call)
				except Exception as error:  # noqa: BLE001 - recorded on the record and latched: later speech is rejected
					host.record_error(record, error)
					host.latch_control_error(error)
					blocked = error
			with self._speechStateLock:
				self._speechStateLock.wait_for(lambda: self._stopGate.clear and self._pauses == 0)
				if blocked is None:
					self._nativeCall = None
			if blocked is not None:
				try:
					self._realPlayer.stop()
				except Exception as error:  # noqa: BLE001 - recorded on the record; the segment fails
					host.record_error(record, error)

	def _closeAdmission(self, call):
		with self._speechStateLock:
			call.admitting = False

	@contextmanager
	def _callbackAdmission(self, instance):
		host = self._segmentHost
		with self._speechStateLock:
			call = self._nativeCall
			if (
				call is None
				or not call.admitting
				or not isinstance(instance, ttsapi.veTypes.VE_HSAFE)
				or instance != call.instance
			):
				call = None
		if call is None:
			yield None, None
			return
		record = call.record
		with host.consumer(record) as admitted:
			if admitted is None or not self._recordValid(record):
				yield None, call
				return
			self._callbackLocal.depth += 1
			try:
				with host.bound_callback(record):
					yield record, call
			finally:
				self._callbackLocal.depth -= 1

	def _feedCallback(self, record, data):
		if self._recordValid(record):
			self._realPlayer.feed(data)

	def _idlePlayer(self):
		# Called by the inner DoneSpeaking on the worker. Segments drain on the
		# lifecycle thread; ordinary speech keeps the add-on's final idle.
		record = self._currentRecord
		if record is not None and record.operation is not None:
			return
		if self._isSilence.cancelled() or (record is not None and not self._recordValid(record)):
			return
		with self._playerOperation():
			self._realPlayer.idle()
			if record is not None:
				with self._speechStateLock:
					self._speechStateLock.wait_for(
						lambda: (self._pauses == 0 and not self._paused) or not self._recordValid(record),
					)

	@contextmanager
	def _playerOperation(self):
		self._playerLocal.depth += 1
		try:
			yield
		finally:
			self._playerLocal.depth -= 1

	def _stopPlayer(self):
		with self._stopGate.hold():
			try:
				with self._playerOperation():
					self._realPlayer.stop()
			except Exception as error:
				# A failed stop leaves the player state unknown: reject successors.
				self._segmentHost.latch_control_error(error)
				raise

	def cancel(self):
		if not self._guardInstalled:
			return super().cancel()
		host = self._segmentHost
		entered = False
		try:
			with host.admission():
				with self._speechStateLock:
					if self._playerClosing:
						return
				host.cancel()
				with self._speechStateLock:
					self._isSilence.set()
					# WavePlayer.stop clears its own pause state. Keep the final idle
					# predicate in sync so fresh speech does not await a stale pause.
					self._paused = False
					self._pauseRevision += 1
					dropped = self._dropQueuedSpeech()
					call = self._nativeCall
					if call is not None:
						call.admitting = False
					self._stopGate.enter()
					entered = True
					self._playerLocal.depth += 1
					self._speechStateLock.notify_all()
				for record in dropped:
					host.abandon(record)
			try:
				self._realPlayer.stop()
			except Exception as error:
				host.latch_control_error(error)
				raise
		finally:
			if entered:
				with self._speechStateLock:
					self._stopGate.leave()
				self._retirePlayerOperation()

	def _dropQueuedSpeech(self):
		"""Like the add-on's cancel: drop queued speech, keep settings and DONE.

		A kept NativeTask of a dropped or cancelled record is a no-op.

		Unlike it, never join the BgThread: cancel may run on it, on a callback,
		a listener or a lifecycle thread. Returns records that will never begin.
		"""
		tasks = []
		try:
			while True:
				tasks.append(self._bgQueue.get_nowait())
				self._bgQueue.task_done()
		except queue.Empty:
			pass
		queued = {task.record for task in tasks if isinstance(task, _Begin)}
		# Leading tasks belong to the record whose Begin already ran.
		owner = next(
			(task.record for task in tasks if isinstance(task, _Retire) and task.record not in queued),
			None,
		)
		kept, dropped = [], []
		for task in tasks:
			if isinstance(task, _Begin):
				owner = task.record
				dropped.append(task.record)
			elif isinstance(task, _Retire):
				if task.record not in queued:
					kept.append(task)
				owner = None
			elif isinstance(task, base.DoneSpeaking):
				# Segments never publish an anonymous DONE.
				if owner is None or owner.operation is None:
					kept.append(task)
			else:
				kept.append(task)
		for task in kept:
			self._bgQueue.put(task)
		return dropped

	def _onIndexReached(self, index):
		if not self._guardInstalled:
			return super()._onIndexReached(index)
		record = self._currentRecord
		if index is None:
			record = self._doneOwner
			if record is not None and record.operation is not None:
				return
			token = record.native.token if record is not None else None
			# speak() no longer raises, so a failed request still releases its
			# DONE waiter, as the add-on's DoneSpeaking does; only a cancelled
			# token silences it.
			if self._isSilence.tokenCancelled() or (token is not None and token.is_cancelled()):
				return
		elif self._isSilence.cancelled() or (record is not None and not self._recordValid(record)):
			return
		return super()._onIndexReached(index)

	def pause(self, switch):
		if not self._guardInstalled:
			return super().pause(switch)
		host = self._segmentHost
		with self._speechStateLock:
			if self._terminated:
				raise RuntimeError("Cerence driver has terminated")
			self._paused = switch
			self._pauseRevision += 1
			self._pauses += 1
			self._playerLocal.depth += 1
			self._speechStateLock.notify_all()
		try:
			while True:
				with self._speechStateLock:
					self._speechStateLock.wait_for(lambda: self._stopGate.clear)
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
			# A raised pause/resume may have partially changed the player.
			# Block this core permanently instead of guessing its state.
			host.latch_control_error(error)
			with self._speechStateLock:
				record = self._currentRecord
				call = self._nativeCall
				if call is not None:
					call.admitting = False
				self._pauseRevision += 1
				self._stopGate.enter()
				self._speechStateLock.notify_all()
			if record is not None:
				host.record_error(record, error)
			try:
				# Release a real idle/feed blocked by the uncertain pause state.
				self._realPlayer.stop()
			except Exception:
				log.error("WorldVoice pause failure cleanup failed", exc_info=True)
			finally:
				with self._speechStateLock:
					self._stopGate.leave()
			raise
		finally:
			with self._speechStateLock:
				# Fresh speech and drain publication wait for real pause/resume
				# retirement, not merely the desired state above.
				self._pauses -= 1
				self._speechStateLock.notify_all()
			self._retirePlayerOperation()

	def _isReentrantTermination(self):
		return bool(
			self._callbackLocal.depth
			or self._playerLocal.depth
			or self._terminationLocal.cleaning
			or threading.current_thread() is self._bgThread,
		)

	def _retirePlayerOperation(self):
		# A terminate() requested inside this cancel/pause finishes when the
		# operation that owned the player returns, as before the async inner.
		self._playerLocal.depth -= 1
		if self._terminationRequested and not self._isReentrantTermination():
			self._finishTermination()

	def terminate(self):
		if not self._guardInstalled:
			return super().terminate()
		reentrant = self._isReentrantTermination()
		with self._speechStateLock:
			first = not self._terminationRequested
			self._terminationRequested = True
			self._terminated = True
		if first:
			self._segmentHost.terminate()
			try:
				self.cancel()
			except Exception as error:  # noqa: BLE001 - kept and raised once termination finishes
				self._terminationError = error
		if reentrant:
			# The caller owns a callback, a player operation or the BgThread
			# itself; a closer thread finishes once they all retire.
			if first:
				threading.Thread(
					target=self._finishTermination,
					name="WorldVoice Cerence close",
					daemon=True,
				).start()
			return
		self._finishTermination()
		if self._terminationError is not None:
			raise self._terminationError

	def _finishTermination(self):
		with self._speechStateLock:
			first = not self._terminationCleaning
			self._terminationCleaning = True
		if not first:
			self._terminationDone.wait()
			return
		self._terminationLocal.cleaning = True
		try:
			# Let the BgThread finish its current record, then keep native and
			# player resources alive through any stop or pause still running.
			self._bgQueue.put(None)
			self._bgThread.join()
			self._segmentHost.wait_idle()
			with self._speechStateLock:
				self._speechStateLock.wait_for(lambda: self._stopGate.clear and self._pauses == 0)
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


class Voice(BaseVoice):
	extraCapabilities = frozenset({"waitfactor", "variant"})
	engine = "Cerence"
	drainProfile = DrainProfile()
	synthDriverClass = SynthDriver
	# The engine's own default variant, cached on each voice and re-read when its core changes.
	_defaultVariant = None
	_defaultVariantCore = None

	def applyEngineSettings(self, core, snapshot):
		instance = core.getVoiceInstance(snapshot.voice_id)
		if self._defaultVariantCore is not core:
			self._defaultVariant = core.getParameter(
				instance,
				VE_PARAM_VOICE_OPERATING_POINT,
				type_=str,
			)
			self._defaultVariantCore = core
		if snapshot.variant != "default" and snapshot.variant not in core.availableVariants:
			raise ValueError(f"Unavailable variant: {snapshot.variant}")
		selected = self._defaultVariant if snapshot.variant == "default" else snapshot.variant
		# Like every inner setting: applied in order on the BgThread, never
		# beside an in-flight synthesis on the same instance.
		core._bgQueue.put(TtsSetParamList(instance, (VE_PARAM_VOICE_OPERATING_POINT, selected)))
		core.waitfactor = snapshot.waitfactor

	@property
	def variants(self):
		try:
			language = self.core.getParameter(
				self.core.getVoiceInstance(self.id),
				VE_PARAM_LANGUAGE,
				type_=str,
			)  # FIXME: store language...
			dbs = ttsapi.getSpeechDBList(language, self.id)
			return [
				{
					"id": item,
					"name": item,
				}
				for item in dbs
			]
		except Exception:  # noqa: BLE001 - missing speech databases mean no variants
			return []

	@classmethod
	def voiceInfoToMetadata(cls, voice):
		localeName = voice.language or "unknown"
		langDescription = languageHandler.getLanguageDescription(localeName)
		if not langDescription:
			if " - " in voice.displayName:
				langDescription = _stripBytesRepr(voice.displayName.split(" - ", 1)[1])
			else:
				langDescription = localeName
		return {
			"id": voice.id,
			"name": getVoiceKey(cls.engine, voice.id),
			"locale": localeName,
			"language": localeName,
			"langDescription": langDescription,
			"description": f"{voice.id} - {langDescription} [{cls.engine}]",
			"engine": cls.engine,
		}
