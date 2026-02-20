import languageHandler

from .driver import SynthDriver
from .. import Voice


class AisoundVoice(Voice):
	core = None
	engine = "Aisound"
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
		if not cls.ready():
			return result

		aisounds = [
			{
				"name": "BabyXu",
				"locale": "zh_CN",
			},
			{
				"name": "DaLong",
				"locale": "zh_HK",
			},
			{
				"name": "DonaldDuck",
				"locale": "zh_HK",
			},
			{
				"name": "DuoXu",
				"locale": "zh_CN",
			},
			{
				"name": "JiuXu",
				"locale": "zh_CN",
			},
			{
				"name": "XiaoFeng",
				"locale": "zh_CN",
			},
			{
				"name": "XiaoMei",
				"locale": "zh_HK",
			},
			{
				"name": "XiaoPing",
				"locale": "zh_CN",
			},
			{
				"name": "YanPing",
				"locale": "zh_CN",
			},
		]
		for aisound in aisounds:
			name = aisound["name"]
			language = aisound['locale']
			langDescription = languageHandler.getLanguageDescription(language)
			if not langDescription:
				langDescription = aisound['locale']

			result.append({
				"id": name,
				"name": name,
				"locale": language,
				"language": language,
				"langDescription": langDescription,
				"description": "%s - %s" % (name, langDescription),
				"engine": "Aisound",
			})

		return result
