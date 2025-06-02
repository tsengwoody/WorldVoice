from autoSettingsUtils.utils import paramToPercent, percentToParam
import globalVars
import languageHandler

from .driver import _aisound
from .. import Voice

import os


class AisoundVoice(Voice):
	core = None
	workspace = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace", "aisound")
	engine = "Aisound"
	def __init__(self, id, name, taskManager, language=None):
		self.name = name
		self.language = language if language else "unknown"

		super().__init__(id=id, taskManager=taskManager)

	def rollback(self):
		super().rollback()
		self.active()

	@property
	def inflection(self):
		return paramToPercent(self._inflection, 0, 2)

	@inflection.setter
	def inflection(self, value):
		param = self._inflection = percentToParam(value, 0, 2)
		self.core.Configure("style", "%d" % param)

	def active(self):
		if self.core.id == self.id:
			return
		self.core.id = self.id
		self.name = self.name
		self.rate = self.rate
		self.pitch = self.pitch
		self.volume = self.volume

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, name):
		param = self._name = name
		self.core.Configure("voice", param)

	@property
	def rate(self):
		return paramToPercent(self._rate, -32768, 32767)

	@rate.setter
	def rate(self, percent):
		param = self._rate = percentToParam(percent, -32768, 32767)
		self.core.Configure("speed", "%d" % param)

	@property
	def pitch(self):
		return paramToPercent(self._pitch, -32768, 32767)

	@pitch.setter
	def pitch(self, percent):
		param = self._pitch = percentToParam(percent, -32768, 32767)
		self.core.Configure("pitch", "%d" % param)

	@property
	def inflection(self):
		return paramToPercent(self._inflection, 0, 2)

	@inflection.setter
	def inflection(self, percent):
		param = self._inflection = percentToParam(percent, 0, 2)
		self.core.Configure("style", "%d" % param)

	@property
	def volume(self):
		return paramToPercent(self._volume, -32768, 32767)

	@volume.setter
	def volume(self, percent):
		param = self._volume = percentToParam(percent, -32768, 32767)
		self.core.Configure("volume", "%d" % param)

	def speak(self, text):
		def _speak():
			self.active()
			_aisound.speakBlock(self, text, "speak")
		self.taskManager.add_dispatch_task((self, _speak),)

	def stop(self):
		self.core.Cancel()

	def pause(self):
		self.core.Pause()

	def resume(self):
		self.core.Resume()

	def index(self, index):
		def _speak():
			_aisound.speakBlock(self, index, "speak_index")
		self.taskManager.add_dispatch_task((self, _speak),)

	def close(self):
		pass

	@classmethod
	def install(cls):
		workspace_path = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace", "aisound")
		return os.path.isfile(os.path.join(workspace_path, 'aisound.dll'))

	@classmethod
	def ready(cls):
		return os.path.isfile(os.path.join(cls.workspace, 'aisound.dll'))

	@classmethod
	def engineOn(cls):
		if not cls.core:
			cls.core = _aisound.Aisound()

	@classmethod
	def engineOff(cls):
		if cls.core:
			cls.core.terminate()
			cls.core = None

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
