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

from ...runtime.barriers import AUDIO_FED, ENGINE_DONE, PLAYED_OUT
from ...runtime.engineControl import ControlFaultPolicy, StopGate, release_newest_first
from ...runtime.playbackWork import DrainProfile, DrainSupport, unverified_drain_support
from ...runtime.segmentHost import LeasedPlayer, NativeStrategy, SegmentHost, SegmentHostSpeaker
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
# Ordinary speech proves what its calls prove (all audio fed, the last call's admitted ENDPROCESS)
# and what its final idle proves (played out). That idle and DONE stay with the inner driver's
# DoneSpeaking, bound to its record at submit (_enqueue). Like every engine's, ordinary speech is
# cancelled through cancel() (the host), never by the request's token.
_ORDINARY_BARRIERS = frozenset({AUDIO_FED, ENGINE_DONE, PLAYED_OUT})


def _stripBytesRepr(text):
	"""Turn a bytes repr like "b'English'" into its text, keeping every letter."""
	if len(text) >= 3 and text.startswith("b'") and text.endswith("'"):
		return text[2:-1]
	return text


class _CerenceInnerNames:
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


class _IdleRoutingPlayer:
	"""Routes only the inner DoneSpeaking idle to `_idlePlayer`, passing the rest to the real player;
	the wrapper's own feeds and stops go through `_CallbackPlayer`.

	A DoneSpeaking keeps the player the inner speak() gave it: _enqueue makes that one bound to
	the record being submitted, so the final idle names its record instead of asking which runs.
	The shared one, bound to no record, idles nothing and publishes no DONE.
	"""

	def __init__(self, player, driver, record=None):
		self._player = player
		self._driver = weakref.ref(driver)
		self._record = record

	def idle(self):
		driver = self._driver()
		if driver is not None:
			return driver._idlePlayer(self._record)
		return None

	def __getattr__(self, name):
		return getattr(self._player, name)


class _CallbackPlayer(LeasedPlayer):
	"""The real player's lease: the native callback's feeds and every wrapper stop.

	A feed is admitted for the current record, which is the one the callback already
	holds; a feed that returns after a cancel is stopped again before the callback
	leaves, and a failed stop latches the control error.
	"""

	def __init__(self, driver, player):
		super().__init__(driver._segmentHost, player, idle_barrier=None)
		self._driver = weakref.ref(driver)

	def _stop_failed(self, error):
		driver = self._driver()
		if driver is None:
			return super()._stop_failed(error)
		driver._failSegmentControl(error)


@dataclass(eq=False)
class _CerenceRequest:
	"""Cerence data carried on a NativeRecord: its speech sequence."""

	commands: object
	# Set on the inner BgThread when its Begin task ran (skipped: never spoken).
	began: bool = False
	skipped: bool = False
	# Whether the record's last native call saw an admitted VE_MSG_ENDPROCESS; overwritten by
	# each call on the BgThread. A record that makes no native call has no tail to flush.
	lastCallEnded: bool = True


@dataclass(eq=False)
class _NativeCall:
	"""One synchronous ve_ttsProcessText2Speech call and its callback admission."""

	record: object
	instance: object
	admitting: bool = True
	# Set by an admitted, valid VE_MSG_ENDPROCESS once its Sonic flush and tail feed finished.
	ended: bool = False


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
					# or native callback-exclusion evidence. The tail is handed
					# over only here, so the call's ENGINE_DONE evidence is set
					# after it, and only while the record is still valid.
					if self._sonicEnabled and self.sonicStream is not None:
						self.sonicStream.flush()
						output = self.sonicStream.readShort()
						if output and driver._recordValid(record):
							self._feedBuf.write(bytes(output))
					if self._feedBuf.tell() and driver._recordValid(record):
						driver._feedCallback(record, self._feedBuf.getvalue())
					self._feedBuf = BytesIO()
					if driver._recordValid(record):
						call.ended = True
				return NUAN_OK if driver._recordValid(record) else NUAN_E_TTS_USERSTOP
		except Exception as error:
			host.record_error(record, error)
			driver._closeAdmission(call)
			log.error("WorldVoice Cerence callback failed", exc_info=True)
			return NUAN_E_TTS_USERSTOP

	def detach(self):
		self._driver = None
		self._player = None
		self.sonicStream = None
		self._feedBuf = BytesIO()


class _CerenceStrategy(NativeStrategy):
	"""Cerence's native queue: the inner BgThread, each record's tasks queued around speak()."""

	barriers = frozenset({AUDIO_FED, ENGINE_DONE, PLAYED_OUT})

	def __init__(self, driver):
		self._driver = weakref.ref(driver)

	def admission_error(self, host):
		driver = self._driver()
		with driver._speechStateLock:
			if driver._terminationRequested:
				return RuntimeError("Cerence driver has terminated")
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
				# idle() waits while the player is paused; a pause after it returned
				# is the scheduler's to hold.
				driver._realPlayer.idle()
			except Exception as error:  # noqa: BLE001 - recorded on the record; the segment fails
				# A failed idle fails only this segment (engineControl's latch rule): stop
				# the player for its successor; only a failed stop latches.
				host.record_error(record, error)
				try:
					driver._stopPlayer()
				except Exception as stopError:  # noqa: BLE001 - latched: the player or engine state is unknown
					driver._failSegmentControl(stopError)
				return
			if driver._recordValid(record):
				host.reach(record, PLAYED_OUT)


class SynthDriver(BaseSynthDriver, SegmentHostSpeaker):
	def __init__(self):
		self._speechStateLock = threading.Condition()
		self._segmentHost = SegmentHost("Cerence", _CerenceStrategy(self))
		self._submitting = None
		self._currentRecord = None
		self._doneOwner = None
		self._nativeCall = None
		self._stopGate = StopGate(self._speechStateLock)
		# Queued records need no drop: _beginRecord abandons them once an error is latched.
		self._controlFault = ControlFaultPolicy(self._segmentHost, self._speechStateLock)
		self._paused = False
		self._pauseRevision = 0
		self._pauses = 0
		self._callbackLocal = _ThreadState()
		self._playerLocal = _ThreadState()
		self._terminationLocal = _ThreadState()
		self._playerClosing = False
		self._terminationRequested = False
		self._terminationCleaning = False
		self._terminationDone = threading.Event()
		self._terminationError = None
		releases = [self._segmentHost.terminate]
		try:
			self._initializeNative(releases)
			self._installGuard()
		except BaseException:
			# VoiceClassAdapter.open gets no core to terminate when the
			# constructor raises: release what was built, newest first.
			release_newest_first(
				releases,
				logger=log,
				message="WorldVoice Cerence initialization cleanup failed",
			)
			raise

	def _initializeNative(self, releases):
		# The inner constructor hardcodes VECallback. Build its resources here
		# so the owned callback is registered before the first ttsapi.open.
		resources = base.getResourcePaths()
		if not resources:
			raise RuntimeError("no resources available")
		ttsapi.initialize(resources)
		releases.append(ttsapi.terminate)
		self._instanceCache = {}
		self._bgQueue = queue.Queue()
		self._bgThread = base.BgThread(self._bgQueue)
		releases.append(self._stopBgThread)
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
		releases.append(self._player.close)
		self._isSilence = threading.Event()
		self._veCallbackHandler = _ContextualCerenceCallback(
			self,
			self._player,
			self._isSilence,
			self._onIndexReached,
		)
		self._veCallback = VE_CBOUTNOTIFY(self._veCallbackHandler)
		self._resources = base.getAvailableResources()
		voices = self.availableVoices
		if not voices:
			raise RuntimeError("no voices available")
		self._voice = next(iter(voices))
		self._normalization = "OFF"
		self._rateBoost = False

	def _stopBgThread(self):
		self._bgQueue.put(None)
		self._bgThread.join()

	def _installGuard(self):
		# The inner stop Event and the callback's player stay as created: the
		# guarded callback decides by record validity and feeds _realPlayer.
		self._realPlayer = self._player
		self._player = _IdleRoutingPlayer(self._realPlayer, self)
		self._leasedPlayer = _CallbackPlayer(self, self._realPlayer)

	def get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport:
		return unverified_drain_support(_PROFILE, "SDK callback quiescence and physical playback are")

	def speak(self, speechSequence):
		with self._speechStateLock:
			if self._terminationRequested:
				raise RuntimeError("Cerence driver has terminated")
		# Like the original add-on's BgThread queue: return once queued.
		self._segmentHost.enqueue(
			speechSequence,
			barriers=_ORDINARY_BARRIERS,
			native=_CerenceRequest(speechSequence),
		)

	def _enqueue(self, record, commands):
		# The inner speak() converts on this thread and queues its native
		# chunks and DoneSpeaking; bracket them with this record's tasks.
		# Host admission (held by enqueue and by cancel) keeps the bracket whole.
		self._bgQueue.put(_Begin(self, record))
		self._submitting = record
		# The inner speak() hands its DoneSpeaking the player it holds: hold one bound to this
		# record meanwhile. Other readers (pause, close) reach the same real player through it.
		player, self._player = self._player, _IdleRoutingPlayer(self._realPlayer, self, record)
		try:
			BaseSynthDriver.speak(self, commands)
		except Exception:
			if record.operation is None:
				# The inner speak() queues its DoneSpeaking last, so this record has no final idle
				# to prove PLAYED_OUT. Undeclare it: the record still runs what was queued and
				# retires as before PLAYED_OUT, while the caller gets the exception. This runs
				# before _Retire is queued, and the BgThread reads barriers only in _Retire (and
				# in a DoneSpeaking, which this record has none of), so no reach races it.
				record.barriers.pop(PLAYED_OUT, None)
			raise
		finally:
			self._player = player
			self._submitting = None
			self._bgQueue.put(_Retire(self, record))

	def _recordValid(self, record):
		# Sealing (retire) does not invalidate the work; callback admission
		# already refuses sealed records.
		return (
			not record.cancelled and record.error is None and (record.work is None or record.work.is_valid())
		)

	def _beginRecord(self, record):
		host = self._segmentHost
		with self._speechStateLock:
			self._speechStateLock.wait_for(lambda: self._stopGate.clear and self._pauses == 0)
			record.native.began = True
			if not self._recordValid(record) or record.abandoned or host.control_error is not None:
				record.native.skipped = True
			else:
				self._currentRecord = record
				host.begin(record)
		if record.native.skipped:
			host.abandon(record)
			return
		self._resetCallbackAudio()

	def _retireRecord(self, record):
		host = self._segmentHost
		if not record.native.skipped:
			if AUDIO_FED in record.barriers and self._recordValid(record):
				host.reach(record, AUDIO_FED)
			# Only the last native call's ENDPROCESS matters: a middle call's tail stays in
			# Sonic and the feed buffer (reset only per record) and goes out with the next call.
			if ENGINE_DONE in record.barriers and self._recordValid(record) and record.native.lastCallEnded:
				host.reach(record, ENGINE_DONE)
			with self._speechStateLock:
				self._speechStateLock.wait_for(lambda: self._stopGate.clear and self._pauses == 0)
			host.retire(record)
			if record.operation is None:
				host.forget(record)
		with self._speechStateLock:
			if self._currentRecord is record:
				self._currentRecord = None
			self._speechStateLock.notify_all()

	def _resetCallbackAudio(self):
		callback = self._veCallbackHandler
		callback._feedBuf = BytesIO()
		if getattr(callback, "_sonicEnabled", False):
			callback.sonicStream = None
			callback._sonicEnabled = False
			callback._sonicInitTried = False

	def _speak(self, voiceInstance, chunks):
		record = self._submitting
		if record is None:
			return
		for piece in split_speech_text_pieces(break_repeated_runs("".join(chunks))):
			self._bgQueue.put(_NativeTask(self, record, voiceInstance, piece))

	def getParameters(self, instance, *idAndTypes):
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
		if record is not self._currentRecord or not self._recordValid(record):
			return
		call = _NativeCall(record, voiceInstance)
		with self._speechStateLock:
			self._speechStateLock.wait_for(lambda: self._stopGate.clear and self._pauses == 0)
			self._nativeCall = call
		invoked = returned = False
		try:
			if self._recordValid(record):
				invoked = True
				result = ProcessText2Speech(voiceInstance, piece)()
				returned = True
				if result == NUAN_E_TTS_USERSTOP and self._recordValid(record):
					raise RuntimeError("Cerence native synthesis returned USERSTOP")
		except Exception as error:
			log.error("WorldVoice Cerence native synthesis failed", exc_info=True)
			host.record_error(record, error)
		finally:
			self._closeAdmission(call)
			# Every callback admitted to this call returns before the next one.
			host.wait_consumers(record)
			if invoked:
				# The BgThread runs a record's tasks in order: the last call to get here before
				# _Retire is the record's last native call. ENGINE_DONE relies on the SDK running
				# callbacks on the calling thread inside the call (a Windows probe of the 32- and
				# 64-bit libraries saw sameThread=True for every call), so an ENDPROCESS after the
				# return is refused and does not count.
				record.native.lastCallEnded = returned and call.ended
			with self._speechStateLock:
				self._speechStateLock.wait_for(lambda: self._stopGate.clear and self._pauses == 0)
				self._nativeCall = None

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
			self._leasedPlayer.feed(data)

	def _idlePlayer(self, record):
		# Called by the inner DoneSpeaking on the worker, for the record its player was bound
		# to at submit. Segments drain on the lifecycle thread; ordinary speech keeps the
		# add-on's final idle, which proves its PLAYED_OUT.
		# The DoneSpeaking publishes its DONE right after this idle, on this thread: name its record
		# for _onIndexReached, even when the idle is skipped below or raises. Set before the segment
		# return as a defence: a segment's DONE is refused by its operation either way today.
		self._doneOwner = record
		if record is None or record.operation is not None:
			return
		# A request that never began (skipped or dropped) fed nothing to wait for; a kept
		# DoneSpeaking of a dropped request runs while its record is not the current one. Such a
		# record is also already invalid (cancel() marked it cancelled), so the identity check
		# is defensive.
		if record is not self._currentRecord or not self._recordValid(record):
			return
		host = self._segmentHost
		with self._playerOperation():
			try:
				self._realPlayer.idle()
			except Exception as error:
				# Fail the record instead of letting it retire silently without PLAYED_OUT. Raised
				# on, so the inner DoneSpeaking publishes no DONE, as before. As in the segment
				# drain (engineControl's latch rule), no control error is latched: retire's stop
				# resets the player, and a failed stop latches.
				host.record_error(record, error)
				raise
			with self._speechStateLock:
				self._speechStateLock.wait_for(
					lambda: (self._pauses == 0 and not self._paused) or not self._recordValid(record),
				)
		# Played out only once the idle returned and any pause ended with the record still valid.
		if self._recordValid(record):
			host.reach(record, PLAYED_OUT)

	@contextmanager
	def _playerOperation(self):
		self._playerLocal.depth += 1
		try:
			yield
		finally:
			self._playerLocal.depth -= 1

	def _failSegmentControl(self, error):
		return self._controlFault.fail(error)

	def _stopPlayer(self):
		# A failed stop leaves the player state unknown: the lease latches it and raises.
		with self._stopGate.hold(), self._playerOperation():
			self._leasedPlayer.stop()

	def cancel(self):
		host = self._segmentHost
		entered = False
		try:
			with host.admission():
				with self._speechStateLock:
					if self._playerClosing:
						return
				host.cancel()
				with self._speechStateLock:
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
			# A failed stop latches through the lease and raises.
			self._leasedPlayer.stop()
		finally:
			if entered:
				with self._speechStateLock:
					self._stopGate.leave()
				self._retirePlayerOperation()

	def _dropQueuedSpeech(self):
		"""Like the add-on's cancel: drop queued speech, keep settings and DoneSpeaking.

		A kept NativeTask of a dropped or cancelled record is a no-op; a kept DoneSpeaking of
		one skips its idle and publishes no DONE (_onIndexReached).

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
		record = self._currentRecord
		if index is None:
			# Only the inner DoneSpeaking publishes DONE, after its idle named its record. Cleared on
			# read as a defence: a DONE without a preceding idle names nothing (every DoneSpeaking
			# idles first today, so no current path tells the difference).
			record, self._doneOwner = self._doneOwner, None
			# Segments never publish DONE. Nor does ordinary speech the host cancelled: a LEGACY_DONE
			# DONE names no request, and cancel() keeps a cancelled request's DoneSpeaking, which may
			# run once the next request already waits on this core. A failed request still releases
			# its DONE waiter, as the add-on's DoneSpeaking does.
			if record is None or record.operation is not None or record.cancelled:
				return
		elif record is None or not self._recordValid(record):
			# An index belongs to the running request; none runs, or it is no longer valid.
			return
		return super()._onIndexReached(index)

	def pause(self, switch):
		host = self._segmentHost
		with self._speechStateLock:
			if self._terminationRequested:
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
					if self._terminationRequested:
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
			self._failSegmentControl(error)
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
				self._leasedPlayer.stop()
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
		reentrant = self._isReentrantTermination()
		with self._speechStateLock:
			first = not self._terminationRequested
			self._terminationRequested = True
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
			self._stopBgThread()
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
