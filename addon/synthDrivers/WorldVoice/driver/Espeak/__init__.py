from threading import Thread
import weakref

from synthDrivers import _espeak
from synthDrivers.espeak import SynthDriver as BaseSynthDriver
from synthDriverHandler import synthDoneSpeaking
from logHandler import log
from synthDrivers.WorldVoice.driver import Voice
from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import DrainProfile, runtime_profile, unverified_drain_support
from ...runtime.segmentHost import LeasedPlayer, NativeRecord, SegmentHost
from ...runtime.session import CancellationView


class _SegmentNative:
	"""Observe errors swallowed by NVDA's native callback/queue boundaries."""

	def __init__(self, driver, native):
		self._driver = weakref.ref(driver)
		self._native = native

	def __getattr__(self, name):
		return getattr(self._native, name)

	def espeak_ng_Cancel(self, *args):
		driver = self._driver()
		if driver is not None and driver._segmentHost.control_error is not None:
			return _espeak.EE_OK
		try:
			return self._native.espeak_ng_Cancel(*args)
		except Exception as error:
			driver = self._driver()
			if driver is not None:
				driver._segmentHost.record_error(driver._segmentHost.current(), error)
			raise

	def espeak_Synth(self, *args):
		driver = self._driver()
		if driver is None:
			return _espeak.EE_OK
		host = driver._segmentHost
		record = host.current()
		if record is None or host.control_error is not None or not record.is_valid():
			return _espeak.EE_OK
		try:
			result = self._native.espeak_Synth(*args)
			if result != _espeak.EE_OK:
				raise RuntimeError("eSpeak synthesis failed with code %s" % result)
			return result
		except Exception as error:
			host.record_error(record, error)
			raise
		finally:
			host.reach(record, "returned")


class _EspeakStrategy:
	"""eSpeak's native queue: NVDA's FIFO with begin and retire markers."""

	barriers = frozenset({"returned", "ended", "idle"})

	def __init__(self, driver):
		self._driver = weakref.ref(driver)

	def submit(self, host, record, commands):
		driver = self._driver()
		# Begin and retirement remain separate queue entries: NVDA stop()
		# removes queued _speak calls but preserves both identity barriers.
		_espeak._execWhenDone(driver._beginSpeech, record, mustBeAsync=True)
		try:
			BaseSynthDriver.speak(driver, commands)
		except Exception as error:
			host.record_error(record, error)
		finally:
			_espeak._execWhenDone(driver._retireSpeech, record, mustBeAsync=True)

	def stop_native(self, host, record):
		self.stop_player(host)

	def stop_player(self, host):
		_espeak.isSpeaking = False
		_espeak.player.stop()


class SynthDriver(BaseSynthDriver):
	"""Add correlated completion without changing NVDA's synthesis queue."""

	def __init__(self):
		self._segmentHost = SegmentHost("eSpeak", _EspeakStrategy(self))
		super().__init__()
		_espeak.player = LeasedPlayer(self._segmentHost, _espeak.player)
		_espeak.espeakDLL = _SegmentNative(self, _espeak.espeakDLL)

	def get_segment_drain_support(self, *, nvda_version=None, audio_mode=None):
		return unverified_drain_support(
			runtime_profile("espeak", nvda_version, audio_mode),
			"callback retirement and physical playback are",
		)

	def speak_segment(
		self,
		commands: SpeechCommands,
		token: CancellationView,
		*,
		context: PlaybackContext,
		on_event: SegmentEventSink,
	):
		self._segmentHost.speak_segment(commands, token, context=context, on_event=on_event)

	def speak(self, speechSequence):
		self._segmentHost.enqueue(speechSequence)

	def _beginSpeech(self, record):
		self._segmentHost.begin(record)
		owner_ref = weakref.ref(self)

		def index_callback(index):
			owner = owner_ref()
			if owner is not None:
				owner._indexFor(record, index)

		_espeak.onIndexReached = index_callback

	def _indexFor(self, record, index):
		# NVDA's onDone lambdas resolve its mutable onIndexReached global.
		# The player lease takes precedence so an old index cannot bind to a
		# successor even if that global was replaced in the meantime.
		host = self._segmentHost
		record = host.callback_record() or record
		with host.consumer(record) as admitted:
			if admitted is None:
				return
			if index is None:
				host.reach(admitted, "ended")
			else:
				super()._onIndexReached(index)

	def _onIndexReached(self, index):
		record = self._segmentHost.current()
		if record is not None:
			self._indexFor(record, index)

	def _retireSpeech(self, record: NativeRecord):
		# FIFO is the proof that NVDA's _speak and the synchronous native
		# callback have returned. Never publish while either is on the stack.
		outcome = self._segmentHost.retire(record)
		if outcome is None or outcome.cancelled:
			return
		if outcome.error is not None:
			_espeak.isSpeaking = False
		Thread(
			target=self._notifyDone,
			args=(record,),
			name="WorldVoice eSpeak completion",
			daemon=True,
		).start()

	def _notifyDone(self, record):
		try:
			if not record.cancelled and not self._segmentHost.terminated:
				synthDoneSpeaking.notify(synth=self)
		except Exception:
			log.error("Error delivering eSpeak completion", exc_info=True)
		finally:
			self._segmentHost.forget(record)

	def cancel(self):
		with self._segmentHost.admission():
			self._segmentHost.cancel()
			if not self._segmentHost.terminated:
				return super().cancel()

	def terminate(self):
		if self._segmentHost.terminate():
			return super().terminate()


class Voice(Voice):
	core = None
	engine = "Espeak"
	drain_profile = DrainProfile()
	synth_driver_class = SynthDriver
