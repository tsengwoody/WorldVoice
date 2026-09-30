import ctypes
from dataclasses import dataclass
import io
from threading import Condition, Lock, Thread
import wave
import weakref

from synthDrivers import oneCore
from logHandler import log
from synthDriverHandler import synthDoneSpeaking, synthIndexReached

from .driver import OneCoreSynthDriver as BaseOneCoreSynthDriver
from synthDrivers.WorldVoice.driver import Voice
from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import CallbackGate, DrainSupport, PlaybackWork
from ...runtime.session import CancellationView


# Keep the facade first for consumers that load its class independently. The
# correlated subclass replaces this initial class reference below.
SynthDriver = BaseOneCoreSynthDriver


class Voice(Voice):
	core = None
	engine = "OneCore"
	synth_driver_class = SynthDriver

	def applyEngineSettings(self, core, snapshot):
		core.language = snapshot.language

	@classmethod
	def supportedSettings(cls):
		return ['voice', 'rate', 'rateBoost', 'pitch', 'volume', 'useWasapi']


# The reviewed helper can time out of terminate without invalidating the native
# callback. Keep only its detached ctypes trampoline alive for the process
# lifetime; it must not retain the driver, player or captured work graph.
_TERMINATED_CALLBACKS = []


class _DetachableCallback:
	"""Fixed native callback pointer with revocable, weak driver ownership."""

	def __init__(self, driver):
		self._lock = Lock()
		self._driver = weakref.ref(driver)

	def __call__(self, audio, length, markers):
		with self._lock:
			driver_ref = self._driver
			driver = driver_ref() if driver_ref is not None else None
		# An already admitted callback retains its driver only until it exits.
		# detach/terminate never waits for its feed/sync under this lock.
		if driver is not None:
			driver._callback(audio, length, markers)

	def detach(self):
		with self._lock:
			self._driver = None


@dataclass(frozen=True)
class _SpeechJob:
	text: str
	work: PlaybackWork | None


@dataclass(frozen=True)
class _NativeJob:
	job: _SpeechJob
	call_token: object | None


class SynthDriver(BaseOneCoreSynthDriver):
	"""Retain terminal callback ownership and drain each correlated utterance."""

	def __init__(self):
		self._segmentCondition = Condition()
		self._segmentPauseLock = Lock()
		self._segmentGate = CallbackGate()
		self._segmentMode = False
		self._segmentTerminated = False
		self._segmentPaused = False
		self._segmentControlGeneration = 0
		self._segmentControlError = None
		self._segmentStops = 0
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
			return DrainSupport(False, "OneCore", "OneCore native initialization did not provide a live token")
		if self._callbackInst is None:
			return DrainSupport(False, "OneCore", "OneCore terminal callback was not installed")
		for name in ("ocSpeech_initialize", "ocSpeech_speak", "ocSpeech_terminate"):
			if not callable(getattr(self._dll, name, None)):
				return DrainSupport(False, "OneCore", f"OneCore native binding is incomplete: {name}")
		return DrainSupport(True, f"OneCore/{nvda_version}/{audio_mode}",
			"DRAIN enabled by explicit request; loaded native helper provenance is unverified")

	def speak_segment(self, commands: SpeechCommands, token: CancellationView, *,
		context: PlaybackContext, on_event: SegmentEventSink) -> None:
		work = PlaybackWork(context, token, on_event)
		if not work.is_valid():
			return
		try:
			with self._segmentCondition:
				self._checkSegmentAdmission()
			if self.supportsProsodyOptions:
				conv = oneCore._OcSsmlConverter(self.language, self.availableLanguages)
			else:
				conv = oneCore._OcPreAPI5SsmlConverter(
					self.language, self.availableLanguages, self._rate, self._pitch, self._volume)
			job = _SpeechJob(conv.convertToXml(tuple(commands)), work)
			if self._player:
				self._player.open()
			with self._segmentCondition:
				self._checkSegmentAdmission()
				if not self._segmentMode and self._isProcessing:
					raise RuntimeError("Cannot switch to correlated playback while legacy synthesis is active")
				self._segmentMode = True
				self._queuedSpeech.append(job)
			self._processQueue()
		except Exception as error:
			work.fail(error)

	def _checkSegmentAdmission(self):
		# Called under the condition; a control fault requires resource replacement.
		if self._segmentTerminated:
			raise RuntimeError("OneCore driver has terminated")
		if self._segmentControlError is not None:
			raise self._segmentControlError

	def speak(self, speechSequence):
		with self._segmentCondition:
			self._checkSegmentAdmission()
		return super().speak(speechSequence)

	def _queueSpeech(self, item):
		with self._segmentCondition:
			self._checkSegmentAdmission()
			# Legacy text uses the same native ownership and control retirement
			# as legacy text queued after a correlated segment. Keep its original
			# speak conversion and anonymous DONE completion interface.
			self._segmentMode = True
			self._queuedSpeech.append(item)
		self._processQueue()

	def _processQueue(self):
		if not self._segmentMode:
			return super()._processQueue()
		with self._segmentCondition:
			if self._segmentTerminated or self._segmentControlError is not None:
				return
			if self._segmentWorker is None:
				self._segmentWorker = Thread(target=self._runSegmentQueue, name="WorldVoice OneCore", daemon=True)
				self._segmentWorker.start()
			self._segmentCondition.notify_all()

	def _runSegmentQueue(self):
		while True:
			with self._segmentCondition:
				self._segmentCondition.wait_for(lambda: self._segmentTerminated or self._segmentControlError is not None or (
					self._segmentNative is None and self._segmentStops == 0 and bool(self._queuedSpeech)))
				if self._segmentTerminated or self._segmentControlError is not None:
					return
				item = self._queuedSpeech.pop(0)
				if not isinstance(item, tuple):
					job = item if isinstance(item, _SpeechJob) else _SpeechJob(item, None)
					if job.work is not None and not job.work.is_valid():
						continue
					# No predecessor remains: its terminal callback/feeds retired
					# before _segmentNative was cleared. begin_native cannot wait here.
					call = self._segmentGate.begin_native(job.work) if job.work is not None else None
					native = _NativeJob(job, call)
					self._segmentNative = native
					self._wasCancelled = False
					self._isProcessing = True
			try:
				if isinstance(item, tuple):
					func, value = item
					func(self._ocSpeechToken, ctypes.c_double(value))
				else:
					self._dll.ocSpeech_speak(self._ocSpeechToken, native.job.text)
			except Exception as error:
				log.exception("OneCore queued operation failed")
				if not isinstance(item, tuple):
					try:
						if native.job.work is not None:
							native.job.work.fail(error)
						else:
							self._failSegmentControl(error)
					finally:
						self._retireSegmentNative(native)

	def _retireSegmentNative(self, native):
		if native.call_token is not None:
			self._segmentGate.finish_native(native.call_token)
			self._segmentGate.wait_retired(native.call_token)
		with self._segmentCondition:
			if self._segmentNative is native:
				self._segmentNative = None
				self._isProcessing = False
			self._segmentCondition.notify_all()

	def _callback(self, audio, length, markers):
		if not self._segmentMode:
			return super()._callback(audio, length, markers)
		with self._segmentCondition:
			native = self._segmentNative
			control_failed = self._segmentControlError is not None
		if native is None or self._earlyExitCB:
			return
		if control_failed:
			self._retireSegmentNative(native)
			return
		work = native.job.work
		if work is None:
			try:
				super()._callback(audio, length, markers)
				# The parent's callback schedules our worker instead of recursively
				# running its queue. Preserve the parent's legacy queue-empty DONE.
				with self._segmentCondition:
					empty = not self._queuedSpeech and not self._wasCancelled and not self._segmentTerminated
				if empty and self._player:
					self._player.sync()
					with self._segmentCondition:
						self._segmentCondition.wait_for(lambda: not self._segmentPaused
							or self._wasCancelled or self._segmentTerminated)
						empty = not self._queuedSpeech and not self._wasCancelled and not self._segmentTerminated
					if empty:
						self._player.idle()
						with self._segmentCondition:
							self._segmentCondition.wait_for(lambda: not self._segmentPaused
								or self._wasCancelled or self._segmentTerminated)
						if not self._wasCancelled and not self._segmentTerminated:
							synthDoneSpeaking.notify(synth=self)
			except Exception as error:
				log.exception("OneCore legacy playback failed")
				self._failSegmentControl(error)
			finally:
				try:
					# The parent can return from an admitted feed after cancel's
					# stop has run. Keep this native record as legacy admission
					# until a final stop removes anything that feed queued.
					if (self._wasCancelled or self._segmentTerminated) and self._player:
						self._player.stop()
				finally:
					self._retireSegmentNative(native)
			return
		lease = self._segmentGate.enter_callback()
		try:
			if lease is None:
				return  # Consume a cancelled terminal callback without feeding.
			if length == 0:
				raise RuntimeError("OneCore native synthesis returned no WAV (length=0)")
			if length < oneCore.WAVE_HEADER_LENGTH:
				raise ValueError("OneCore WAV header is truncated")
			with wave.open(io.BytesIO(ctypes.string_at(audio, oneCore.WAVE_HEADER_LENGTH)), "rb") as wav:
				self._maybeInitPlayer(wav)
				data_len = wav.getnframes() * wav.getnchannels() * wav.getsampwidth()
				bytes_per_sec = wav.getframerate() * wav.getnchannels() * wav.getsampwidth()
			if data_len > length - oneCore.WAVE_HEADER_LENGTH:
				raise ValueError("OneCore WAV payload is truncated")
			player = self._player
			data = audio + oneCore.WAVE_HEADER_LENGTH
			previous = 0
			for marker in markers.split("|") if markers else ():
				index, position = (int(value) for value in marker.split(":"))
				position = position * bytes_per_sec // oneCore.HUNDRED_NS_PER_SEC
				if not previous <= position <= data_len:
					raise ValueError("OneCore marker offset is outside ordered WAV audio")
				if not self._feedSegment(work, player, data + previous, position - previous,
					lambda index=index: self._segmentIndex(work, index)):
					return
				previous = position
			if not self._feedSegment(work, player, data + previous, data_len - previous):
				return
			player.sync()
			with self._segmentCondition:
				self._segmentCondition.wait_for(lambda: not self._segmentPaused or not work.is_valid())
			work.complete_drained()
		except Exception as error:
			log.exception("OneCore segment playback failed")
			try:
				work.fail(error)
			finally:
				if self._player:
					self._player.stop()
		finally:
			try:
				if lease is not None:
					if not work.is_valid() and self._player:
						self._player.stop()
			finally:
				if lease is not None:
					lease.close()
				self._retireSegmentNative(native)

	def _segmentIndex(self, work, index):
		if work.is_valid():
			synthIndexReached.notify(synth=self, index=index)

	def _feedSegment(self, work, player, address, size, on_done=None):
		if not work.is_valid():
			return False
		# The callback lease is feed admission. It stays alive through this
		# external call and the final stop, preventing a successor's admission.
		try:
			player.feed(ctypes.c_void_p(address), size=size, onDone=on_done)
		finally:
			if not work.is_valid():
				player.stop()
		return work.is_valid()

	def _captureSegmentControlFailure(self, error):
		# Capture while the pause lock is still owned, before cancellation can
		# retire that operation and admit a successor. Delivery happens later.
		with self._segmentCondition:
			if self._segmentControlError is not None:
				return None
			self._segmentControlError = error
			self._segmentControlGeneration += 1
			self._wasCancelled = True
			self._segmentStops += 1
			works = [item.work for item in self._queuedSpeech
				if isinstance(item, _SpeechJob) and item.work is not None]
			legacy = any(isinstance(item, str) for item in self._queuedSpeech)
			if self._segmentNative is not None:
				if self._segmentNative.job.work is not None:
					works.append(self._segmentNative.job.work)
				else:
					legacy = True
			self._queuedSpeech.clear()
			return error, works, legacy

	def _deliverSegmentControlFailure(self, failure):
		if failure is None:
			return
		error, works, legacy = failure
		try:
			# Invalidate contextual work before stop releases its drain wait.
			# Sinks can reenter cancel/terminate, so no driver lock is held.
			for work in works:
				try:
					work.fail(error)
				except Exception:
					log.exception("OneCore control failure delivery failed")
			if self._player:
				try:
					self._player.stop()
				except Exception:
					log.exception("OneCore failed player could not be stopped")
			if legacy and not self._segmentTerminated:
				# Legacy has no failure event; release its speaking wait once.
				try:
					synthDoneSpeaking.notify(synth=self)
				except Exception:
					log.exception("OneCore legacy failure delivery failed")
		finally:
			with self._segmentCondition:
				self._segmentPaused = False
				self._segmentStops -= 1
				self._segmentCondition.notify_all()

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
					if self._segmentPaused and not self._segmentStops:
						self._player.pause(True)
				except Exception as error:
					failure = self._captureSegmentControlFailure(error)
					raise
		except Exception as error:
			self._deliverSegmentControlFailure(failure)
			raise

	def cancel(self):
		with self._segmentCondition:
			self._wasCancelled = True
			self._segmentPaused = False
			self._segmentControlGeneration += 1
			self._segmentStops += 1
			for item in self._queuedSpeech:
				if isinstance(item, _SpeechJob) and item.work is not None:
					item.work.cancel()
			self._queuedSpeech = [item for item in self._queuedSpeech if isinstance(item, tuple)]
			if self._segmentNative is not None and self._segmentNative.job.work is not None:
				self._segmentNative.job.work.cancel()
			self._segmentCondition.notify_all()
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
						if self._segmentControlError is None:
							self._player.pause(False)
						self._player.stop()
		except Exception as error:
			self._failSegmentControl(error)
			raise
		finally:
			with self._segmentCondition:
				self._segmentStops -= 1
				self._segmentCondition.notify_all()

	def pause(self, switch):
		with self._segmentCondition:
			if self._segmentTerminated or self._segmentStops:
				return
			self._checkSegmentAdmission()
			generation = self._segmentControlGeneration
		failure = None
		try:
			with self._segmentPauseLock:
				try:
					with self._segmentCondition:
						if (generation != self._segmentControlGeneration
								or self._segmentTerminated or self._segmentStops):
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
		with self._segmentCondition:
			if self._segmentTerminated:
				return
			self._segmentTerminated = True
			self._earlyExitCB = True
			self._segmentCondition.notify_all()
		self._segmentCallback.detach()
		if self._callbackInst is not None:
			_TERMINATED_CALLBACKS.append(self._callbackInst)
		try:
			self.cancel()
		finally:
			super().terminate()


Voice.synth_driver_class = SynthDriver
