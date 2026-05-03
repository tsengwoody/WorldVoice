import languageHandler
import locale
from synthDriverHandler import LanguageInfo

from .driver import SynthDriver, TtsSetParamList
from .driver import ve2
from .driver.ve2.veTypes import VE_PARAM_LANGUAGE, VE_PARAM_VOICE_OPERATING_POINT, VeError
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

		# Helper to ensure we have a clean string
		def clean_str(val):
			# 1. If it's actually bytes, decode it
			if isinstance(val, bytes):
				return val.decode('utf-8', errors='ignore')
			
			# 2. Convert to string
			s = str(val)
			
			# 3. The Brute Force: If the string literally starts with b' and ends with '
			if s.startswith("b'") and s.endswith("'"):
				return s[2:-1] 
				
			return s

		for voice in voices:
			# Decode properties from the voice object
			v_id = clean_str(voice.id)
			v_displayName = clean_str(voice.displayName)
			localeName = clean_str(voice.language or "unknown")
			
			langDescription = languageHandler.getLanguageDescription(localeName)
			
			if not langDescription:
				if " - " in v_displayName:
					langDescription = v_displayName.split(" - ", 1)[1]
				else:
					langDescription = localeName
			
			# Clean the description before formatting
			langDescription = clean_str(langDescription)

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
