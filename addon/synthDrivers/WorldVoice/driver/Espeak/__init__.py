import weakref
from threading import Thread

from logHandler import log
from synthDriverHandler import synthDoneSpeaking
from synthDrivers import _espeak
from synthDrivers.espeak import SynthDriver as BaseSynthDriver
from synthDrivers.WorldVoice.driver import Voice as BaseVoice

from ...runtime.barriers import ENGINE_DONE, PLAYED_OUT, SYNTHESIZED
from ...runtime.hostNames import host_names_ready
from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import DrainProfile, DrainSupport, runtime_profile, unverified_drain_support
from ...runtime.segmentHost import LeasedPlayer, NativeRecord, NativeStrategy, SegmentDrainCore, SegmentHost
from ...runtime.session import CancellationView


def _nvdaLabel():
	# Imported here: the NVDA version is read only to name it in a skip log.
	import versionInfo

	return f"NVDA {versionInfo.version}"


class _SegmentNative:
	"""Observe errors swallowed by NVDA's native callback/queue boundaries."""

	def __init__(self, driver, native, ok):
		self._driver = weakref.ref(driver)
		self._native = native
		self._ok = ok

	def __getattr__(self, name):
		return getattr(self._native, name)

	def espeak_ng_Cancel(self, *args):
		driver = self._driver()
		if driver is not None and driver._segmentHost.control_error is not None:
			return self._ok
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
			return self._ok
		host = driver._segmentHost
		record = host.current()
		if record is None or host.control_error is not None or not record.is_valid():
			return self._ok
		try:
			result = self._native.espeak_Synth(*args)
			if result != self._ok:
				raise RuntimeError(f"eSpeak synthesis failed with code {result}")
			return result
		except Exception as error:
			host.record_error(record, error)
			raise
		finally:
			host.reach(record, SYNTHESIZED)


class _EspeakPort:
	"""Every NVDA private the wrapper touches in synthDrivers._espeak.

	NVDA's _espeak.terminate() resets player, espeakDLL and onIndexReached to
	None, so nothing here needs restoring. Voice.ready() checks these names
	against the running NVDA; compare them with NVDA's _espeak.py and espeak.py
	on every NVDA upgrade.
	"""

	# Read or written through the synthDrivers._espeak module.
	NVDA_MODULE_NAMES = frozenset(
		{"EE_OK", "_execWhenDone", "espeakDLL", "isSpeaking", "onIndexReached", "player"},
	)
	# Members of NVDA's synthDrivers.espeak.SynthDriver: none used in place, one overridden.
	NVDA_PRIVATES = frozenset()
	NVDA_OVERRIDES = frozenset({"_onIndexReached"})

	def install(self, host, driver):
		_espeak.player = LeasedPlayer(host, _espeak.player)
		_espeak.espeakDLL = _SegmentNative(driver, _espeak.espeakDLL, _espeak.EE_OK)

	def runWhenDone(self, function, record):
		_espeak._execWhenDone(function, record, mustBeAsync=True)

	def setIndexCallback(self, callback):
		_espeak.onIndexReached = callback

	def markNotSpeaking(self):
		# NVDA's callback clears isSpeaking on its final empty-wav call; a failed
		# utterance never reaches it, so clear it here or the next one is aborted early.
		_espeak.isSpeaking = False

	def stopPlayer(self):
		# As NVDA's stop(): an in-flight callback sees isSpeaking False and aborts
		# synthesis instead of feeding the player after it was stopped.
		_espeak.isSpeaking = False
		_espeak.player.stop()


class _EspeakStrategy(NativeStrategy):
	"""eSpeak's native queue: NVDA's FIFO with begin and retire markers."""

	barriers = frozenset({SYNTHESIZED, ENGINE_DONE, PLAYED_OUT})

	def __init__(self, driver):
		self._driver = weakref.ref(driver)

	def submit(self, host, record, commands):
		driver = self._driver()
		# Begin and retirement remain separate queue entries: NVDA stop()
		# removes queued _speak calls but preserves both identity barriers.
		driver._port.runWhenDone(driver._beginSpeech, record)
		try:
			BaseSynthDriver.speak(driver, commands)
		except Exception as error:  # noqa: BLE001 - recorded on the record; the segment fails
			host.record_error(record, error)
		finally:
			driver._port.runWhenDone(driver._retireSpeech, record)

	def stop_native(self, host, record):
		self.stop_player(host)

	def stop_player(self, host):
		self._driver()._port.stopPlayer()


class SynthDriver(BaseSynthDriver, SegmentDrainCore):
	"""Add correlated completion without changing NVDA's synthesis queue."""

	def __init__(self):
		self._port = _EspeakPort()
		self._segmentHost = SegmentHost("eSpeak", _EspeakStrategy(self))
		super().__init__()
		self._port.install(self._segmentHost, self)

	def get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport:
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
		ownerRef = weakref.ref(self)

		def indexCallback(index):
			owner = ownerRef()
			if owner is not None:
				owner._indexFor(record, index)

		self._port.setIndexCallback(indexCallback)

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
				host.reach(admitted, ENGINE_DONE)
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
			self._port.markNotSpeaking()
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


class Voice(BaseVoice):
	engine = "Espeak"
	drainProfile = DrainProfile()
	synthDriverClass = SynthDriver

	@classmethod
	def ready(cls):
		# Skip the engine, with one log line, when the running NVDA lacks a name the wrapper uses.
		return host_names_ready(
			cls.engine,
			_espeak,
			BaseSynthDriver,
			module_names=_EspeakPort.NVDA_MODULE_NAMES,
			class_names=_EspeakPort.NVDA_PRIVATES | _EspeakPort.NVDA_OVERRIDES,
			host_label=_nvdaLabel,
			logger=log,
		)
