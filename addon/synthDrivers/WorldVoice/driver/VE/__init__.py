import languageHandler
import locale
from synthDriverHandler import LanguageInfo

from .driver import SynthDriver, TtsSetParamList
from .driver import ve2
from .driver.ve2.veTypes import VE_PARAM_LANGUAGE, VE_PARAM_VOICE_OPERATING_POINT, VE_PARAM_WAITFACTOR, VeError
from synthDrivers.WorldVoice.driver import Voice


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
			TtsSetParamList(self.core.getVoiceInstance(self.name), (VE_PARAM_VOICE_OPERATING_POINT, value))()
		except VeError:
			pass

	@property
	def variants(self):
		language = self.core.getParameter(self.core.getVoiceInstance(self.name), VE_PARAM_LANGUAGE, type_=str) # FIXME: store language...
		dbs = ve2.getSpeechDBList(language, self.name)
		return [{
			"id": item,
			"name": item,
		} for item in dbs]

	@property
	def waitfactor(self):
		if self.core:
			try:
				self._waitfactor = int(self.core.getParameter(self.core.getVoiceInstance(self.name), VE_PARAM_WAITFACTOR))
			except (VeError, RuntimeError, TypeError, ValueError):
				pass
		return getattr(self, "_waitfactor", 0)

	@waitfactor.setter
	def waitfactor(self, value):
		waitfactor = int(value)
		if self.core:
			TtsSetParamList(self.core.getVoiceInstance(self.name), (VE_PARAM_WAITFACTOR, waitfactor))()
		self._waitfactor = waitfactor

	@classmethod
	def voices(cls):
		result = []
		if not cls.ready() or not cls.core:
			return result

		try:
			voices = cls.core.availableVoices.values()
		except Exception:
			return result

		for voice in voices:
			localeName = voice.language or "unknown"
			langDescription = languageHandler.getLanguageDescription(localeName)
			if not langDescription:
				if " - " in voice.displayName:
					langDescription = voice.displayName.split(" - ", 1)[1]
				else:
					langDescription = localeName
			name = voice.id
			result.append({
				"id": name,
				"name": name,
				"locale": localeName,
				"language": localeName,
				"langDescription": langDescription,
				"description": "[%s] %s - %s" % (cls.engine, name, langDescription),
				"engine": cls.engine,
			})

		return result
