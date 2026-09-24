import languageHandler
import locale
import threading
from synthDriverHandler import LanguageInfo
from logHandler import log

from .driver import SynthDriver, TtsSetParamList
from .driver import ve2
from .driver.ve2.veTypes import VE_PARAM_LANGUAGE, VE_PARAM_VOICE_OPERATING_POINT, VeError
from synthDrivers.WorldVoice.driver import Voice, getVoiceKey


class _SilenceGate(threading.Event):
	def __init__(self):
		super().__init__()
		self._token = None
		self._inside_native_call = False

	def cancelled(self):
		return super().is_set() or bool(self._token and self._token.is_cancelled())

	def is_set(self):
		if not self._inside_native_call:
			log.debug("VE callback outside native call")
		return self.cancelled() or not self._inside_native_call

	def isSet(self):
		return self.is_set()

	def clear(self):
		log.debug("VE driver clear blocked by WorldVoice guard")

	def begin(self, token):
		self._token = token
		threading.Event.clear(self)


class _GuardedPlayer:
	def __init__(self, real_player, gate):
		self._real = real_player
		self._gate = gate

	def feed(self, *args, **kwargs):
		if self._gate.cancelled():
			return
		try:
			return self._real.feed(*args, **kwargs)
		finally:
			if self._gate.cancelled():
				self._real.stop()

	def idle(self):
		if not self._gate.cancelled():
			self._real.idle()

	def __getattr__(self, name):
		return getattr(self._real, name)


class CancellableSynthDriver(SynthDriver):
	def __init__(self):
		self._guard_installed = False
		self._speechStateLock = threading.Lock()
		super().__init__()
		callback = getattr(self, "_veCallbackHandler", None)
		if callback is None or not all(
			hasattr(obj, name)
			for obj, name in (
				(self, "_isSilence"), (self, "_player"),
				(callback, "_isSilence"), (callback, "_player"), (callback, "_feedBuf"),
			)
		):
			log.warning("VE cancellation guard unavailable; using original driver")
			return
		original = (self._isSilence, self._player, callback._isSilence, callback._player)
		gate = _SilenceGate()
		player = _GuardedPlayer(self._player, gate)
		try:
			self._isSilence = gate
			callback._isSilence = gate
			self._player = player
			callback._player = player
		except Exception:
			for obj, name, value in (
				(self, "_isSilence", original[0]), (self, "_player", original[1]),
				(callback, "_isSilence", original[2]), (callback, "_player", original[3]),
			):
				try:
					setattr(obj, name, value)
				except Exception:
					log.warning("VE cancellation guard restoration failed", exc_info=True)
			log.warning("VE cancellation guard installation failed", exc_info=True)
			return
		self._real_player = original[1]
		self._guard_installed = True

	@property
	def supportsCancellationToken(self):
		return self._guard_installed

	def speak(self, speechSequence, cancellationToken=None):
		if not self._guard_installed:
			return super().speak(speechSequence)
		return super().speak(speechSequence)

	def _speak(self, voiceInstance, chunks):
		if not self._guard_installed:
			return super()._speak(voiceInstance, chunks)
		return super()._speak(voiceInstance, chunks)

	def cancel(self):
		if not self._guard_installed:
			return super().cancel()
		return super().cancel()

	def _onIndexReached(self, index):
		if not self._guard_installed:
			return super()._onIndexReached(index)
		return super()._onIndexReached(index)


class Voice(Voice):
	core = None
	engine = "VE"
	synth_driver_class = SynthDriver

	@property
	def variant(self):
		return self._variant

	@variant.setter
	def variant(self, value):
		self._variant = value
		try:
			TtsSetParamList(self.core.getVoiceInstance(self.id), (VE_PARAM_VOICE_OPERATING_POINT, value))()
		except VeError:
			pass

	@property
	def variants(self):
		language = self.core.getParameter(
			self.core.getVoiceInstance(self.id), VE_PARAM_LANGUAGE, type_=str,
		)  # FIXME: store language...
		dbs = ve2.getSpeechDBList(language, self.id)
		return [{
			"id": item,
			"name": item,
		} for item in dbs]

	@property
	def waitfactor(self):
		if self.core:
			self._waitfactor = self.core.waitfactor
		return self._waitfactor

	@waitfactor.setter
	def waitfactor(self, value):
		if self.core:
			self.core.waitfactor = value

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
				"engine": cls.engine,
			})

		return result
