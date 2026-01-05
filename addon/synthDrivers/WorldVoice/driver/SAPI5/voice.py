from collections import OrderedDict

import languageHandler
import locale

from .driver import SAPI5SynthDriver as SynthDriver
from .. import Voice


class SAPI5Voice(Voice):
	core = None
	engine = "SAPI5"
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
	def variants(self):
		self._variants = []
		return self._variants

	@property
	def variant(self):
		return self._variant

	@variant.setter
	def variant(self, value):
		self._variant = value

	@classmethod
	def ready(cls):
		return True

	@classmethod
	def voices(cls):
		result = []
		if not cls.ready() or not cls.core:
			return result

		voices = OrderedDict()
		v = cls.core._getVoiceTokens()
		# #2629: Iterating uses IEnumVARIANT and GetBestInterface doesn't work on tokens returned by some token enumerators.
		# Therefore, fetch the items by index, as that method explicitly returns the correct interface.
		for i in range(len(v)):
			try:
				ID = v[i].Id
				name = v[i].getattribute('name')
				description = v[i].GetDescription()
				try:
					language = locale.windows_locale[int(v[i].getattribute("language").split(";")[0], 16)]
				except KeyError:
					language = "unknown"
			except COMError:
				log.warning("Could not get the voice info. Skipping...")

			langDescription = languageHandler.getLanguageDescription(language)
			if not langDescription:
				try:
					langDescription = description.split("-")[1]
				except IndexError:
					langDescription = language

			result.append({
				"id": ID,
				"name": name,
				"locale": language,
				"language": language,
				"langDescription": langDescription,
				"description": "%s - %s" % (name, langDescription),
				"engine": "SAPI5",
			})
		return result
