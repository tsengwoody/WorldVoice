import languageHandler
import locale

from .driver import SynthDriver
from .driver import TtsSetParamList
from .driver import ttsapi
from .driver.ttsapi.veTypes import VE_PARAM_LANGUAGE, VE_PARAM_VOICE_OPERATING_POINT, VeError
from synthDrivers.WorldVoice.driver import Voice


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
			TtsSetParamList(self.core.getVoiceInstance(self.name), (VE_PARAM_VOICE_OPERATING_POINT, value))()
		except VeError:
			pass
		except BaseException:
			pass

	@property
	def variants(self):
		try:
			language = self.core.getParameter(self.core.getVoiceInstance(self.name), VE_PARAM_LANGUAGE, type_=str) # FIXME: store language...
			dbs = ttsapi.getSpeechDBList(language, self.name)
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
			# Decodes bytes AND strips literal b'...' prefixes if they exist
			def fix(v):
				s = v.decode('utf-8', 'ignore') if isinstance(v, bytes) else str(v)
				return s.strip("b'").strip("'") if (s.startswith("b'") and s.endswith("'")) else s

			v_id = fix(voice.id)
			v_displayName = fix(voice.displayName)
			
			localeName = (voice.language or "unknown")
			localeName = fix(localeName)
			
			langDescription = languageHandler.getLanguageDescription(localeName)
			
			if not langDescription:
				if " - " in v_displayName:
					langDescription = v_displayName.split(" - ", 1)[1]
				else:
					langDescription = localeName
			
			langDescription = fix(langDescription)

			result.append({
				"id": v_id,
				"name": v_id,
				"locale": localeName,
				"language": localeName,
				"langDescription": langDescription,
				"description": "[%s] %s - %s" % (cls.engine, v_id, langDescription),
				"engine": cls.engine,
			})

		return result
