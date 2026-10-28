import ctypes
import io
import wave
import weakref
from dataclasses import dataclass
from threading import Condition, Lock, Thread

from logHandler import log
from synthDriverHandler import synthDoneSpeaking, synthIndexReached
from synthDrivers import oneCore
from synthDrivers.WorldVoice.driver import Voice as BaseVoice

from ...runtime.barriers import AUDIO_FED, PLAYED_OUT
from ...runtime.engineControl import StopGate
from ...runtime.hostNames import host_names_ready
from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import DrainProfile, DrainSupport, runtime_profile, unverified_drain_support
from ...runtime.segmentHost import NativeStrategy, SegmentDrainCore, SegmentHost
from ...runtime.session import CancellationView
from .driver import OneCoreSynthDriver as BaseOneCoreSynthDriver

# The reviewed helper can time out of terminate without invalidating the native
# callback. Keep only its detached ctypes trampoline alive for the process
# lifetime; it must not retain the driver, player or captured work graph.
_TERMINATED_CALLBACKS = []

# Ordinary (legacy) text proves only that its callback returned; the parent
# owns its queue-empty sync, idle and DONE.
_ORDINARY_BARRIERS = frozenset({AUDIO_FED})


def _nvdaLabel():
	# Imported here: the NVDA version is read only to name it in a skip log.
	import versionInfo

	return f"NVDA {versionInfo.version}"


class _OneCorePort:
	"""Parent private names (vendored OneCoreSynthDriver and NVDA oneCore) this wrapper uses.

	The worker and native callback re-implement the parent's flow around these,
	so they are used in place. Every listed name is NVDA's; Voice.ready() checks
	them against the running NVDA. Compare these lists with both parents on upgrade.
	"""

	# Read through the synthDrivers.oneCore module (SynthDriver: the class ready() checks).
	NVDA_MODULE_NAMES = frozenset(
		{
			"HUNDRED_NS_PER_SEC",
			"SynthDriver",
			"WAVE_HEADER_LENGTH",
			"_OcPreAPI5SsmlConverter",
			"_OcSsmlConverter",
		},
	)
	# Members of NVDA's oneCore.SynthDriver used in place, and the ones overridden.
	NVDA_PRIVATES = frozenset(
		{
			"_callbackInst",
			"_dll",
			"_earlyExitCB",
			"_isProcessing",
			"_ocSpeechToken",
			"_pitch",
			"_player",
			"_queuedSpeech",
			"_rate",
			"_volume",
			"_wasCancelled",
		},
	)
	NVDA_OVERRIDES = frozenset({"_queueSpeech", "_processQueue", "_callback", "_maybeInitPlayer"})


class _DetachableCallback:
	"""Fixed native callback pointer with revocable, weak driver ownership."""

	def __init__(self, driver):
		self._lock = Lock()
		self._driver = weakref.ref(driver)

	def __call__(self, audio, length, markers):
		with self._lock:
			driverRef = self._driver
			driver = driverRef() if driverRef is not None else None
		# An already admitted callback retains its driver only until it exits.
		# detach/terminate never waits for its feed/sync under this lock.
		if driver is not None:
			with driver._segmentCondition:
				record = driver._segmentNative
			try:
				driver._callback(audio, length, markers)
			finally:
				# Retire callback ownership only after the callback body has
				# returned, including any admitted feed and final stop, then
				# release the worker.
				if record is not None:
					try:
						driver._retireSegmentNative(record)
					finally:
						driver._releaseSegmentWorker(record)

	def detach(self):
		with self._lock:
			self._driver = None


@dataclass(eq=False)
class _OneCoreNative:
	"""OneCore data carried on a NativeRecord: its SSML and callback return."""

	text: str
	called: bool = False


@dataclass(frozen=True)
class _SpeechJob:
	record: object


class _OneCoreStrategy(NativeStrategy):
	"""OneCore's native queue: the parent's _queuedSpeech and the outer worker."""

	barriers = frozenset({AUDIO_FED, PLAYED_OUT})

	def __init__(self, driver):
		self._driver = weakref.ref(driver)

	def admission_error(self, host):
		driver = self._driver()
		with driver._segmentCondition:
			if driver._segmentTerminated:
				return RuntimeError("OneCore driver has terminated")
			if not driver._segmentMode and driver._isProcessing:
				return RuntimeError("Cannot switch to correlated playback while legacy synthesis is active")
		return None

	def prepare(self, host, commands, operation):
		if operation is None:
			# Ordinary text arrives already converted by the parent's speak().
			return commands
		driver = self._driver()
		with driver._segmentCondition:
			driver._checkSegmentAdmission()
		if driver.supportsProsodyOptions:
			conv = oneCore._OcSsmlConverter(driver.language, driver.availableLanguages)
		else:
			conv = oneCore._OcPreAPI5SsmlConverter(
				driver.language,
				driver.availableLanguages,
				driver._rate,
				driver._pitch,
				driver._volume,
			)
		return conv.convertToXml(tuple(commands))

	def submit(self, host, record, text):
		driver = self._driver()
		with driver._segmentCondition:
			driver._checkSegmentAdmission()
			record.native = _OneCoreNative(text)
			driver._segmentMode = True
			driver._queuedSpeech.append(_SpeechJob(record))
		driver._processQueue()

	def stop_native(self, host, record):
		player = self._driver()._player
		if player:
			player.stop()

	def stop_player(self, host):
		player = self._driver()._player
		if player:
			player.stop()

	def drain(self, host, record):
		driver = self._driver()
		player = driver._player
		if player:
			try:
				player.sync()
				with driver._segmentCondition:
					driver._segmentCondition.wait_for(
						lambda: not driver._segmentPaused or not record.work.is_valid(),
					)
			except Exception as error:  # noqa: BLE001 - recorded on the record and latched: later speech is rejected
				host.record_error(record, error)
				driver._failSegmentControl(error)
				return
		# sync() is not idle(): it does not close the continuous segment.
		host.reach(record, PLAYED_OUT)


class SynthDriver(BaseOneCoreSynthDriver, SegmentDrainCore):
	"""Retain terminal callback ownership and drain each correlated utterance."""

	def __init__(self):
		self._segmentHost = SegmentHost("OneCore", _OneCoreStrategy(self))
		self._segmentCondition = Condition()
		self._segmentPauseLock = Lock()
		self._segmentMode = False
		self._segmentTerminated = False
		self._segmentPaused = False
		self._segmentControlGeneration = 0
		self._stopGate = StopGate(self._segmentCondition)
		self._segmentWorker = None
		self._segmentNative = None
		self._segmentCallback = _DetachableCallback(self)
		# The parent installs CFUNCTYPE(self._callback) once. Intercept only
		# that instance lookup; its native pointer owns the trampoline rather
		# than a bound method retaining this whole driver.
		self._callback = self._segmentCallback
		try:
			super().__init__()
		finally:
			del self._callback

	def get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport:
		if self._segmentTerminated or not self._ocSpeechToken or not self._ocSpeechToken.value:
			return DrainSupport(
				False,
				"OneCore",
				"OneCore native initialization did not provide a live token",
			)
		if self._callbackInst is None:
			return DrainSupport(False, "OneCore", "OneCore terminal callback was not installed")
		for name in ("ocSpeech_initialize", "ocSpeech_speak", "ocSpeech_terminate"):
			if not callable(getattr(self._dll, name, None)):
				return DrainSupport(False, "OneCore", f"OneCore native binding is incomplete: {name}")
		return unverified_drain_support(
			runtime_profile("OneCore", nvda_version, audio_mode),
			"loaded native helper provenance is",
		)

	def speak_segment(
		self,
		commands: SpeechCommands,
		token: CancellationView,
		*,
		context: PlaybackContext,
		on_event: SegmentEventSink,
	) -> None:
		self._segmentHost.speak_segment(commands, token, context=context, on_event=on_event)

	def _checkSegmentAdmission(self):
		# Called under the condition; a control fault requires resource replacement.
		if self._segmentTerminated:
			raise RuntimeError("OneCore driver has terminated")
		controlError = self._segmentHost.control_error
		if controlError is not None:
			raise controlError

	def speak(self, speechSequence):
		with self._segmentCondition:
			self._checkSegmentAdmission()
		return super().speak(speechSequence)

	def _queueSpeech(self, item):
		with self._segmentCondition:
			self._checkSegmentAdmission()
		# Legacy text uses the same native ownership and control retirement as
		# a correlated segment, keeping its original conversion and anonymous
		# DONE completion interface.
		self._segmentHost.enqueue(item, barriers=_ORDINARY_BARRIERS)

	def _processQueue(self):
		if not self._segmentMode:
			return super()._processQueue()
		with self._segmentCondition:
			if self._segmentTerminated or self._segmentHost.control_error is not None:
				return
			if self._segmentWorker is None:
				self._segmentWorker = Thread(
					target=self._runSegmentQueue,
					name="WorldVoice OneCore",
					daemon=True,
				)
				self._segmentWorker.start()
			self._segmentCondition.notify_all()

	def _runSegmentQueue(self):
		host = self._segmentHost
		while True:
			with self._segmentCondition:
				self._segmentCondition.wait_for(
					lambda: (
						self._segmentTerminated
						or host.control_error is not None
						or (self._segmentNative is None and self._stopGate.clear and bool(self._queuedSpeech))
					),
				)
				if self._segmentTerminated or host.control_error is not None:
					return
				item = self._queuedSpeech.pop(0)
				if isinstance(item, tuple):
					record = None
				else:
					record = item.record
					if not record.is_valid():
						host.abandon(record)
						continue
					self._segmentNative = record
					host.begin(record)
					self._wasCancelled = False
					self._isProcessing = True
			if record is None:
				func, value = item
				try:
					func(self._ocSpeechToken, ctypes.c_double(value))
				except Exception:
					# As on master: a failed setting is logged; speech continues.
					log.error("OneCore setting change failed", exc_info=True)
				continue
			self._speakRecord(record)

	def _speakRecord(self, record):
		host = self._segmentHost
		skipped = False
		try:
			try:
				if self._player:
					self._player.open()
			except Exception as error:
				host.record_error(record, error)
				if record.operation is not None:
					# Under a drain contract the player state is now unknown: latch.
					self._failSegmentControl(error)
				else:
					# Ordinary speech skips only this sentence; the next one opens the
					# player again. It still completes below, or its speaking wait hangs.
					log.error(
						"OneCore could not open the audio player; skipping this sentence",
						exc_info=True,
					)
					skipped = True
				self._releaseSegmentWorker(record)
			else:
				if not record.is_valid():
					self._releaseSegmentWorker(record)
				else:
					try:
						self._dll.ocSpeech_speak(self._ocSpeechToken, record.native.text)
					except Exception as error:
						log.error("OneCore queued operation failed", exc_info=True)
						host.record_error(record, error)
						# Like a failed player open: ordinary speech skips only this
						# sentence and still completes; a segment fails with its error.
						skipped = record.operation is None
						self._releaseSegmentWorker(record)
			with self._segmentCondition:
				# The native callback returns once per call, even when cancelled.
				self._segmentCondition.wait_for(lambda: record.native.called or self._segmentTerminated)
				called = record.native.called
			if not called:
				host.abandon(record)
				return
			host.retire(record)
			if record.operation is None:
				host.forget(record)
				if skipped:
					self._completeSkippedSentence()
		finally:
			with self._segmentCondition:
				if self._segmentNative is record:
					self._segmentNative = None
					self._isProcessing = False
				self._segmentCondition.notify_all()

	def _completeSkippedSentence(self):
		# As the legacy callback does after the last sentence: DONE once nothing is queued.
		with self._segmentCondition:
			last = not self._queuedSpeech and not self._wasCancelled and not self._segmentTerminated
		if last:
			try:
				synthDoneSpeaking.notify(synth=self)
			except Exception:
				log.error("OneCore completion of a skipped sentence failed", exc_info=True)

	def _retireSegmentNative(self, record):
		# The callback has returned: no further native callback enters this record.
		self._segmentHost.close(record)

	def _releaseSegmentWorker(self, record):
		with self._segmentCondition:
			record.native.called = True
			self._segmentCondition.notify_all()

	def _callback(self, audio, length, markers):
		if not self._segmentMode:
			return super()._callback(audio, length, markers)
		host = self._segmentHost
		with self._segmentCondition:
			record = self._segmentNative
		controlFailed = host.control_error is not None
		if record is None or self._earlyExitCB:
			return
		if controlFailed:
			return
		if record.operation is None:
			self._legacyCallback(record, audio, length, markers)
			return
		with host.consumer(record) as admitted:
			if admitted is None:
				return  # Consume a cancelled terminal callback without feeding.
			with host.bound_callback(record):
				self._segmentPlayback(record, audio, length, markers)

	def _segmentPlayback(self, record, audio, length, markers):
		host = self._segmentHost
		try:
			if length == 0:
				raise RuntimeError("OneCore native synthesis returned no WAV (length=0)")
			if length < oneCore.WAVE_HEADER_LENGTH:
				raise ValueError("OneCore WAV header is truncated")
			with wave.open(io.BytesIO(ctypes.string_at(audio, oneCore.WAVE_HEADER_LENGTH)), "rb") as wav:
				self._maybeInitPlayer(wav)
				dataLen = wav.getnframes() * wav.getnchannels() * wav.getsampwidth()
				bytesPerSec = wav.getframerate() * wav.getnchannels() * wav.getsampwidth()
			if dataLen > length - oneCore.WAVE_HEADER_LENGTH:
				raise ValueError("OneCore WAV payload is truncated")
			player = self._player
			data = audio + oneCore.WAVE_HEADER_LENGTH
			previous = 0
			for marker in markers.split("|") if markers else ():
				index, position = (int(value) for value in marker.split(":"))
				position = position * bytesPerSec // oneCore.HUNDRED_NS_PER_SEC
				if not previous <= position <= dataLen:
					raise ValueError("OneCore marker offset is outside ordered WAV audio")
				if not self._feedSegment(
					record,
					player,
					data + previous,
					position - previous,
					lambda index=index: self._segmentIndex(record, index),
				):
					return
				previous = position
			if not self._feedSegment(record, player, data + previous, dataLen - previous):
				return
			# Also OneCore's only terminal notification; there is no ENGINE_DONE.
			host.reach(record, AUDIO_FED)
		except Exception as error:
			log.error("OneCore segment playback failed", exc_info=True)
			host.record_error(record, error)
			if self._player:
				self._player.stop()
		finally:
			if not record.is_valid() and self._player:
				self._player.stop()

	def _legacyCallback(self, record, audio, length, markers):
		try:
			super()._callback(audio, length, markers)
			self._segmentHost.reach(record, AUDIO_FED)
			# The parent's callback schedules our worker instead of recursively
			# running its queue. Preserve the parent's legacy queue-empty DONE.
			with self._segmentCondition:
				empty = not self._queuedSpeech and not self._wasCancelled and not self._segmentTerminated
			if empty and self._player:
				self._player.sync()
				with self._segmentCondition:
					self._segmentCondition.wait_for(
						lambda: not self._segmentPaused or self._wasCancelled or self._segmentTerminated,
					)
					empty = not self._queuedSpeech and not self._wasCancelled and not self._segmentTerminated
				if empty:
					self._player.idle()
					with self._segmentCondition:
						self._segmentCondition.wait_for(
							lambda: not self._segmentPaused or self._wasCancelled or self._segmentTerminated,
						)
					if not self._wasCancelled and not self._segmentTerminated:
						synthDoneSpeaking.notify(synth=self)
		except Exception as error:
			log.error("OneCore legacy playback failed", exc_info=True)
			self._failSegmentControl(error)
		finally:
			# The parent can return from an admitted feed after cancel's stop has
			# run. Keep this record current until a final stop removes anything
			# that feed queued.
			if (self._wasCancelled or self._segmentTerminated) and self._player:
				self._player.stop()

	def _segmentIndex(self, record, index):
		if record.work.is_valid():
			synthIndexReached.notify(synth=self, index=index)

	def _feedSegment(self, record, player, address, size, onDone=None):
		if not record.is_valid():
			return False
		try:
			player.feed(ctypes.c_void_p(address), size=size, onDone=onDone)
		finally:
			if not record.is_valid():
				player.stop()
		return record.is_valid()

	def _captureSegmentControlFailure(self, error):
		# Capture while the pause lock is still owned, before cancellation can
		# retire that operation and admit a successor. Delivery happens later.
		host = self._segmentHost
		with self._segmentCondition:
			if host.control_error is not None:
				return None
			host.latch_control_error(error)
			self._segmentControlGeneration += 1
			self._wasCancelled = True
			self._stopGate.enter()
			dropped = [item.record for item in self._queuedSpeech if isinstance(item, _SpeechJob)]
			legacy = any(record.operation is None for record in dropped) or (
				self._segmentNative is not None and self._segmentNative.operation is None
			)
			self._queuedSpeech.clear()
			self._segmentCondition.notify_all()
			return error, dropped, legacy

	def _deliverSegmentControlFailure(self, failure):
		if failure is None:
			return
		_error, dropped, legacy = failure
		try:
			# Queued records never reach the worker; they fail with the latched error.
			for record in dropped:
				self._segmentHost.abandon(record)
			if self._player:
				try:
					self._player.stop()
				except Exception:
					log.error("OneCore failed player could not be stopped", exc_info=True)
			if legacy and not self._segmentTerminated:
				# Legacy has no failure event; release its speaking wait once.
				try:
					synthDoneSpeaking.notify(synth=self)
				except Exception:
					log.error("OneCore legacy failure delivery failed", exc_info=True)
		finally:
			with self._segmentCondition:
				self._segmentPaused = False
				self._stopGate.leave()

	def _failSegmentControl(self, error):
		self._deliverSegmentControlFailure(self._captureSegmentControlFailure(error))

	def _maybeInitPlayer(self, wav):
		failure = None
		try:
			with self._segmentPauseLock:
				try:
					with self._segmentCondition:
						self._checkSegmentAdmission()
					super()._maybeInitPlayer(wav)
					if self._segmentPaused and self._stopGate.clear:
						self._player.pause(True)
				except Exception as error:
					failure = self._captureSegmentControlFailure(error)
					raise
		except Exception:
			self._deliverSegmentControlFailure(failure)
			raise

	def cancel(self):
		host = self._segmentHost
		with self._stopGate.hold():
			with host.admission():
				host.cancel()
				with self._segmentCondition:
					self._wasCancelled = True
					self._segmentPaused = False
					self._segmentControlGeneration += 1
					dropped = [item.record for item in self._queuedSpeech if isinstance(item, _SpeechJob)]
					# Settings changes keep their queue position.
					self._queuedSpeech = [item for item in self._queuedSpeech if isinstance(item, tuple)]
					self._segmentCondition.notify_all()
				# Queued records never reach the worker.
				for record in dropped:
					host.abandon(record)
			try:
				try:
					if self._player:
						self._player.stop()
				finally:
					# Stop first to release callback/player waits. Keep cancellation
					# admission reserved until every older control operation exits;
					# then undo a late pause before letting a successor use the player.
					with self._segmentPauseLock:
						if self._player:
							if host.control_error is None:
								self._player.pause(False)
							self._player.stop()
			except Exception as error:
				self._failSegmentControl(error)
				raise

	def pause(self, switch):
		with self._segmentCondition:
			if self._segmentTerminated or not self._stopGate.clear:
				return
			self._checkSegmentAdmission()
			generation = self._segmentControlGeneration
		failure = None
		try:
			with self._segmentPauseLock:
				try:
					with self._segmentCondition:
						if (
							generation != self._segmentControlGeneration
							or self._segmentTerminated
							or not self._stopGate.clear
						):
							return
						self._checkSegmentAdmission()
						if switch:
							self._segmentPaused = True
					super().pause(switch)
					if not switch:
						with self._segmentCondition:
							self._segmentPaused = False
							self._segmentCondition.notify_all()
				except Exception as error:
					failure = self._captureSegmentControlFailure(error)
					raise
		except Exception:
			self._deliverSegmentControlFailure(failure)
			raise

	def terminate(self):
		host = self._segmentHost
		with host.admission():
			with self._segmentCondition:
				if self._segmentTerminated:
					return
			# Silence work already accepted before any of it can observe the
			# terminated flag and fail; no segment is accepted in between.
			host.cancel()
			with self._segmentCondition:
				self._segmentTerminated = True
				self._earlyExitCB = True
				self._segmentCondition.notify_all()
		self._segmentCallback.detach()
		if self._callbackInst is not None:
			_TERMINATED_CALLBACKS.append(self._callbackInst)
		try:
			self.cancel()
		finally:
			self._segmentHost.terminate()
			super().terminate()


class Voice(BaseVoice):
	engine = "OneCore"
	drainProfile = DrainProfile(wasapi_dependent=True)
	synthDriverClass = SynthDriver

	def applyEngineSettings(self, core, snapshot):
		core.language = snapshot.language

	@classmethod
	def ready(cls):
		# Skip the engine, with one log line, when the running NVDA lacks a name the wrapper uses.
		return host_names_ready(
			cls.engine,
			oneCore,
			oneCore.SynthDriver,
			module_names=_OneCorePort.NVDA_MODULE_NAMES,
			class_names=_OneCorePort.NVDA_PRIVATES | _OneCorePort.NVDA_OVERRIDES,
			host_label=_nvdaLabel,
			logger=log,
		)

	@classmethod
	def supportedSettings(cls):
		return ["voice", "rate", "rateBoost", "pitch", "volume", "useWasapi"]
