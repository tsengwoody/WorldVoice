from dataclasses import dataclass
from threading import Condition, Event, RLock, Thread, local
import weakref

from synthDrivers import _espeak
from synthDrivers.espeak import SynthDriver as BaseSynthDriver
from synthDriverHandler import synthDoneSpeaking
from logHandler import log
from synthDrivers.WorldVoice.driver import Voice
from ...runtime.models import PlaybackContext, PlaybackEvent, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import DrainSupport, PlaybackWork
from ...runtime.session import CancellationView
from ...runtime.segmentLifecycle import SegmentLifecycle


@dataclass(eq=False)
class _NativeSpeech:
	work: PlaybackWork | None
	operation: object | None = None
	retired: Event | None = None
	handoff: Event | None = None
	producer: object | None = None
	cancelled: bool = False
	closed: bool = False
	ended: bool = False
	idle_completed: bool = False
	returned: bool = False
	error: Exception | None = None
	consumers: int = 0

	def is_valid(self):
		return not self.cancelled and not self.closed and (self.work is None or self.work.is_valid())


class _SegmentPlayer:
	"""Retain the original native job around PCM and delayed index callbacks."""

	def __init__(self, driver, player):
		self._driver = weakref.ref(driver)
		self._player = player

	def __getattr__(self, name):
		return getattr(self._player, name)

	def feed(self, data, size=None, onDone=None):
		driver = self._driver()
		if driver is None:
			return
		native = driver._admitConsumer()
		if native is None:
			return
		callback = None
		if onDone is not None:
			def callback():
				owner = self._driver()
				if owner is None or not owner._admitConsumer(native):
					return
				previous = getattr(owner._segmentCallbackLocal, "native", None)
				owner._segmentCallbackLocal.native = native
				try:
					onDone()
				finally:
					owner._segmentCallbackLocal.native = previous
					owner._releaseConsumer(native)
		try:
			return self._player.feed(data, size, callback)
		except Exception as error:
			driver._recordError(native, error)
			raise
		finally:
			try:
				# A feed that was already admitted may queue audio after cancel's
				# stop. Stop it again before the FIFO barrier permits a successor.
				if not native.is_valid():
					self.stop()
			finally:
				driver._releaseConsumer(native)

	def idle(self):
		driver = self._driver()
		if driver is None:
			return
		native = driver._admitConsumer()
		if native is None:
			return
		try:
			result = self._player.idle()
			with driver._segmentCondition:
				native.idle_completed = True
			return result
		except Exception as error:
			driver._recordError(native, error)
			raise
		finally:
			driver._releaseConsumer(native)

	def stop(self):
		try:
			return self._player.stop()
		except Exception as error:
			driver = self._driver()
			if driver is not None:
				driver._recordControlError(error)
			raise


class _SegmentNative:
	"""Observe errors swallowed by NVDA's native callback/queue boundaries."""

	def __init__(self, driver, native):
		self._driver = weakref.ref(driver)
		self._native = native

	def __getattr__(self, name):
		return getattr(self._native, name)

	def espeak_ng_Cancel(self, *args):
		driver = self._driver()
		if driver is not None and driver._segmentControlError is not None:
			return _espeak.EE_OK
		try:
			return self._native.espeak_ng_Cancel(*args)
		except Exception as error:
			driver = self._driver()
			if driver is not None:
				driver._recordError(driver._segmentNative, error)
			raise

	def espeak_Synth(self, *args):
		driver = self._driver()
		if driver is None:
			return _espeak.EE_OK
		with driver._segmentCondition:
			native = driver._segmentNative
			control_error = driver._segmentControlError
		if native is None or control_error is not None or not native.is_valid():
			return _espeak.EE_OK
		try:
			result = self._native.espeak_Synth(*args)
			if result != _espeak.EE_OK:
				raise RuntimeError("eSpeak synthesis failed with code %s" % result)
			return result
		except Exception as error:
			driver._recordError(native, error)
			raise
		finally:
			with driver._segmentCondition:
				native.returned = True


class SynthDriver(BaseSynthDriver):
	"""Add correlated completion without changing NVDA's synthesis queue."""

	def __init__(self):
		self._segmentCondition = Condition(RLock())
		self._segmentAdmission = RLock()
		self._segmentCallbackLocal = local()
		self._segmentNative = None
		self._segmentPending = []
		self._segmentTerminated = False
		self._segmentControlError = None
		self._segmentLifecycle = SegmentLifecycle(self)
		self._segmentOperations = {}
		self._segmentAccepted = set()
		super().__init__()
		_espeak.player = _SegmentPlayer(self, _espeak.player)
		_espeak.espeakDLL = _SegmentNative(self, _espeak.espeakDLL)

	def get_segment_drain_support(self, *, nvda_version=None, audio_mode=None):
		return DrainSupport(True, "espeak/%s/%s" % (nvda_version or "unknown", audio_mode or "unknown"),
			"DRAIN explicitly enabled; callback retirement and physical playback are unverified")

	def speak_segment(self, commands: SpeechCommands, token: CancellationView, *,
			context: PlaybackContext, on_event: SegmentEventSink):
		with self._segmentAdmission:
			if self._segmentTerminated:
				return
			if self._segmentControlError is not None:
				self._segmentLifecycle.reject_new(context, token, on_event, self._segmentControlError)
				return
			def deliver(event):
				self._deliverSpeech(operation, event)
			operation = self._segmentLifecycle.accept(context, token, deliver)
			operation._espeak_sink = on_event
			operation._espeak_cancelled = False
			with self._segmentCondition:
				self._segmentAccepted.add(operation)
		Thread(target=self._runSegment, args=(operation, tuple(commands), deliver),
			name="WorldVoice eSpeak lifecycle", daemon=True).start()

	def _runSegment(self, operation, commands, deliver):
		try:
			self._segmentLifecycle.run(operation, commands)
		except Exception as error:
			self._segmentLifecycle.reject_new(operation.work.context, operation.work.token,
				deliver, self._segmentControlError or error.__cause__ or error)
		finally:
			with self._segmentCondition:
				native = self._segmentOperations.pop(operation, None)
				if operation._espeak_cancelled or operation.work.token.is_cancelled():
					self._segmentAccepted.discard(operation)
			if native is not None:
				native.handoff.set()

	def submit_native(self, operation, commands):
		self._queueSpeech(commands, operation.work, operation)

	def request_stop(self, operation):
		with self._segmentCondition:
			native = self._segmentOperations.get(operation)
			if native is not None:
				native.cancelled = True
				active = native is self._segmentNative
			else:
				active = False
		if active:
			_espeak.isSpeaking = False
			_espeak.player.stop()

	def wait_native_boundary(self, operation):
		with self._segmentCondition:
			native = self._segmentOperations[operation]
		native.retired.wait()
		if native.error is not None:
			self._segmentLifecycle.fail(operation, native.error)

	def wait_native_retired(self, operation):
		return

	def wait_playback_drained(self, operation):
		with self._segmentCondition:
			native = self._segmentOperations.get(operation)
		if native is None:
			return
		if not operation.work.is_valid() or native.error is not None:
			_espeak.isSpeaking = False
			_espeak.player.stop()
			return
		if not (native.returned and native.ended and native.idle_completed):
			self._segmentLifecycle.fail(operation, RuntimeError(
				"eSpeak synthesis retired without its native return, end and player idle barriers"))
			_espeak.isSpeaking = False
			_espeak.player.stop()

	def speak(self, speechSequence):
		self._queueSpeech(speechSequence, None)

	def _queueSpeech(self, commands, work, operation=None):
		native = _NativeSpeech(work, operation=operation,
			retired=Event() if operation is not None else None,
			handoff=Event() if operation is not None else None)
		with self._segmentAdmission:
			if self._segmentTerminated:
				if work is not None:
					work.cancel()
				return
			with self._segmentCondition:
				control_error = self._segmentControlError
				if control_error is not None and work is None:
					raise control_error
				self._segmentPending.append(native)
				if operation is not None:
					self._segmentOperations[operation] = native
					operation._espeak_native = native
			if control_error is not None:
				if operation is not None:
					self._segmentLifecycle.fail(operation, control_error)
					native.retired.set()
				else:
					native.closed = True
					self._dispatchSpeech(native, control_error)
				return
			if operation is not None:
				native.producer = self._segmentLifecycle.admit_producer(operation)
			# Begin and retirement remain separate queue entries: NVDA stop()
			# removes queued _speak calls but preserves both identity barriers.
			_espeak._execWhenDone(self._beginSpeech, native, mustBeAsync=True)
			try:
				super().speak(commands)
			except Exception as error:
				self._recordError(native, error)
			finally:
				_espeak._execWhenDone(self._retireSpeech, native, mustBeAsync=True)

	def _beginSpeech(self, native):
		with self._segmentCondition:
			self._segmentNative = native
		owner_ref = weakref.ref(self)
		def index_callback(index):
			owner = owner_ref()
			if owner is not None:
				owner._indexFor(native, index)
		_espeak.onIndexReached = index_callback

	def _admitConsumer(self, native=None):
		with self._segmentCondition:
			native = native or self._segmentNative
			if native is None or native is not self._segmentNative or not native.is_valid():
				return None
			native.consumers += 1
			return native

	def _releaseConsumer(self, native):
		with self._segmentCondition:
			native.consumers -= 1
			self._segmentCondition.notify_all()

	def _recordError(self, native, error):
		with self._segmentCondition:
			if native is not None and native.error is None:
				native.error = error

	def _recordControlError(self, error):
		# A stop failure does not prove that queued PCM/index callbacks were
		# discarded. Retain the first control error until the driver reloads.
		with self._segmentCondition:
			if self._segmentControlError is None:
				self._segmentControlError = error
			for native in self._segmentPending:
				if native.error is None:
					native.error = self._segmentControlError

	def _indexFor(self, native, index):
		# NVDA's onDone lambdas resolve its mutable onIndexReached global.
		# The player lease takes precedence so an old index cannot bind to a
		# successor even if that global was replaced in the meantime.
		native = getattr(self._segmentCallbackLocal, "native", None) or native
		if not self._admitConsumer(native):
			return
		try:
			if index is None:
				with self._segmentCondition:
					native.ended = True
			else:
				super()._onIndexReached(index)
		finally:
			self._releaseConsumer(native)

	def _onIndexReached(self, index):
		with self._segmentCondition:
			native = self._segmentNative
		if native is not None:
			self._indexFor(native, index)

	def _retireSpeech(self, native):
		# FIFO is the proof that NVDA's _speak and the synchronous native
		# callback have returned. Never publish while either is on the stack.
		with self._segmentCondition:
			valid = native.is_valid()
			native.closed = True
			self._segmentCondition.wait_for(lambda: native.consumers == 0)
			valid = valid and not native.cancelled and (native.work is None or native.work.is_valid())
			if not valid and native in self._segmentPending:
				self._segmentPending.remove(native)
			if self._segmentNative is native:
				self._segmentNative = None
		if native.operation is not None:
			if native.producer is not None:
				self._segmentLifecycle.retire_producer(native.producer)
			native.retired.set()
			# The FIFO worker must retain player ownership until the coordinator
			# has finished the final stop or drain check for this operation.
			native.handoff.wait()
			return
		if not valid:
			_espeak.isSpeaking = False
			# Token-only cancellation can occur after the last feed and skip
			# terminal idle admission. Discard that PCM before FIFO handoff.
			try:
				_espeak.player.stop()
			except Exception:
				# The player proxy latched the error. The cancelled segment stays
				# silent, and queued work cannot enter native synthesis afterward.
				log.error("Error stopping cancelled eSpeak playback", exc_info=True)
			return
		error = native.error
		if error is None and not (native.returned and native.ended and native.idle_completed):
			error = RuntimeError("eSpeak synthesis retired without its native return, end and player idle barriers")
		if error is not None:
			_espeak.isSpeaking = False
			if self._segmentControlError is None:
				try:
					_espeak.player.stop()
				except Exception as stop_error:
					log.error("Error stopping failed eSpeak playback", exc_info=True)
					self._recordError(native, stop_error)
		self._dispatchSpeech(native, error)

	def _dispatchSpeech(self, native, error):
		Thread(target=self._deliverSpeech, args=(native, error), name="WorldVoice eSpeak completion", daemon=True).start()

	def _deliverSpeech(self, native, error):
		event_delivery = isinstance(error, PlaybackEvent)
		try:
			if event_delivery:
				if not native.work.token.is_cancelled() and not native._espeak_cancelled and not self._segmentTerminated:
					native._espeak_sink(error)
				return
			with self._segmentCondition:
				error = error or native.error or self._segmentControlError
			if native.work is not None:
				if error is not None:
					native.work.fail(error)
				else:
					native.work.complete_drained()
			elif not native.cancelled and not self._segmentTerminated:
				synthDoneSpeaking.notify(synth=self)
		except Exception:
			log.error("Error delivering eSpeak completion", exc_info=True)
		finally:
			# Keep work cancellable until publication starts on the delivery
			# thread, including the gap after native FIFO retirement.
			with self._segmentCondition:
				if event_delivery:
					self._segmentAccepted.discard(native)
					bound = getattr(native, "_espeak_native", None)
					if bound in self._segmentPending:
						self._segmentPending.remove(bound)
				elif native in self._segmentPending:
					self._segmentPending.remove(native)

	def _invalidateSpeech(self):
		with self._segmentCondition:
			for operation in tuple(self._segmentAccepted):
				operation._espeak_cancelled = True
				self._segmentLifecycle.cancel(operation)
			for native in self._segmentPending:
				native.cancelled = True
				if native.work is not None and native.operation is None:
					native.work.cancel()

	def cancel(self):
		with self._segmentAdmission:
			self._invalidateSpeech()
			if not self._segmentTerminated:
				return super().cancel()

	def terminate(self):
		with self._segmentAdmission:
			if self._segmentTerminated:
				return
			self._segmentTerminated = True
			self._invalidateSpeech()
			self._segmentLifecycle.terminate()
		return super().terminate()


class Voice(Voice):
	core = None
	engine = "Espeak"
	synth_driver_class = SynthDriver
