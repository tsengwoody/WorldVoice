from collections import OrderedDict

import languageHandler
import locale
from synthDriverHandler import LanguageInfo

from .driver import SynthDriver, TtsSetParamList
from .driver import ve2
from .driver.ve2.veTypes import VE_PARAM_LANGUAGE, VE_PARAM_VOICE_OPERATING_POINT, VeError
from .. import Voice


class VEVoice(Voice):
	core = None
	engine = "VE"
	synth_driver_class = SynthDriver

	def __init__(self, id, name, taskManager, language=None):
		self.name = name
		self.language = language if language else "unknown"

		super().__init__(id=id, taskManager=taskManager)

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, name):
		self._name = name

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
	def ready(cls):
		return True

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
				"description": "%s - %s" % (name, langDescription),
				"engine": "VE",
			})

		return result
