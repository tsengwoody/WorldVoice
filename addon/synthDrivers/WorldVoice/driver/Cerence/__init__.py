import languageHandler
import locale

from .driver import SynthDriver
from .driver import TtsSetParamList
from .driver import ttsapi
from .driver.ttsapi.veTypes import VE_PARAM_LANGUAGE, VE_PARAM_VOICE_OPERATING_POINT, VeError
from synthDrivers.WorldVoice.driver import Voice, getVoiceKey


class Voice(Voice):
	core = None
	engine = "Cerence"
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
		except BaseException:
			pass

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
				"name": getVoiceKey(cls.engine, name),
				"locale": localeName,
				"language": localeName,
				"langDescription": langDescription,
				"description": "[%s] %s - %s" % (cls.engine, name, langDescription),
				"engine": "Cerence",
			})

		return result
