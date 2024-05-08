import config
import globalVars
import languageHandler
from logHandler import log

from . import _languages
from . import _vocalizer
from . import Voice

import math
import os
import threading


class VEVoice(Voice):
	engine = "VE"
	workspace = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace", "VE")

	def __init__(self, id, name, taskManager, language=None):
		self.tts, self.name = _vocalizer.open(name) if name != "default" else _vocalizer.open()

		if not language:
			language = "unknown"
			languages = _vocalizer.getLanguageList()
			languageNamesToLocales = {l.szLanguage.decode(): _languages.getLocaleNameFromTLW(l.szLanguageTLW.decode()) for l in languages}
			for l in languages:
				voices = _vocalizer.getVoiceList(l.szLanguage)
				for voice in voices:
					vename = voice.szVoiceName.decode()
					if self.name == vename:
						language = languageNamesToLocales.get(voice.szLanguage.decode(), "unknown")
						break
		self.language = language

		super().__init__(id=id, taskManager=taskManager)

	@property
	def rate(self):
		rate = self._rate = _vocalizer.getParameter(self.tts, _vocalizer.VE_PARAM_SPEECHRATE, type_=int)
		norm = rate / 100.0
		factor = 25 if norm >= 1 else 50
		return int(round(50 + factor * math.log(norm, 2)))

	@rate.setter
	def rate(self, percent):
		# _vocalizer.setParameter(self.tts, _vocalizer.VE_PARAM_SPEECHRATE, self._rate)
		value = percent
		factor = 25.0 if value >= 50 else 50.0
		norm = 2.0 ** ((value - 50.0) / factor)
		self._rate = value = int(round(norm * 100))
		_vocalizer.setParameter(self.tts, _vocalizer.VE_PARAM_SPEECHRATE, self._rate)

	@property
	def pitch(self):
		norm = self._pitch / 100.0
		factor = 50
		return int(round(50 + factor * math.log(norm, 2)))

	@pitch.setter
	def pitch(self, percent):
		value = percent
		factor = 50.0
		norm = 2.0 ** ((value - 50.0) / factor)
		self._pitch = value = int(round(norm * 100))
		_vocalizer.setParameter(self.tts, _vocalizer.VE_PARAM_PITCH, self._pitch)

	@property
	def volume(self):
		self._volume = _vocalizer.getParameter(self.tts, _vocalizer.VE_PARAM_VOLUME, type_=int)
		return self._volume

	@volume.setter
	def volume(self, percent):
		self._volume = percent
		_vocalizer.setParameter(self.tts, _vocalizer.VE_PARAM_VOLUME, int(self._volume))

	@property
	def variants(self):
		language = _vocalizer.getParameter(self.tts, _vocalizer.VE_PARAM_LANGUAGE, type_=str)
		variants = _vocalizer.getSpeechDBList(language, self.name)
		return [{
			"id": item,
			"name": item,
		} for item in variants]

	@property
	def variant(self):
		# self._variant = _vocalizer.getParameter(self.tts, _vocalizer.VE_PARAM_VOICE_OPERATING_POINT, type_=str)
		return self._variant

	@variant.setter
	def variant(self, value):
		self._variant = value
		_vocalizer.stop()
		_vocalizer.setParameter(self.tts, _vocalizer.VE_PARAM_VOICE_OPERATING_POINT, value)

	@property
	def waitfactor(self):
		self._waitfactor = _vocalizer.getParameter(self.tts, _vocalizer.VE_PARAM_WAITFACTOR, type_=int)
		return self._waitfactor

	@waitfactor.setter
	def waitfactor(self, value):
		self._waitfactor = value
		_vocalizer.setParameter(self.tts, _vocalizer.VE_PARAM_WAITFACTOR, value)

	def speak(self, text):
		try:
			text.encode('utf-8').decode('utf-8')
		except:
			temp = ""
			for c in text:
				try:
					temp += c.encode('utf8').decode('utf8')
				except:
					pass
			text = temp

		temps = ""
		for c in text:
			if ord(c) > 65535:
				c = chr(65535)
			temps += c
		text = temps
		def _speak():
			# _vocalizer.processText2Speech(self.tts, text)
			_vocalizer.speakBlock(self.tts, text)
		self.taskManager.add_dispatch_task((self, _speak),)

	def breaks(self, time):
		maxTime = 6553 if self.variant == "bet2" else 65535
		breakTime = max(1, min(time, maxTime))

		def _breaks():
			threading.Thread(target=_vocalizer.breakBlock, args=(self.tts, breakTime)).start()
			# _vocalizer.breakBlock(self.tts, breakTime)
		self.taskManager.add_dispatch_task((self, _breaks),)

	def stop(self):
		_vocalizer.stopBlock()
		# _vocalizer.stop()

	def pause(self):
		_vocalizer.pause()

	def resume(self):
		_vocalizer.resume()

	def close(self):
		_vocalizer.close(self.tts)

	@classmethod
	def install(cls):
		return os.path.isdir(os.path.join(cls.workspace, 'common'))

	@classmethod
	def ready(cls):
		try:
			with _vocalizer.preOpenVocalizer() as check:
				return check
		except BaseException:
			return False

	@classmethod
	def engineOn(cls, lock):
		try:
			_vocalizer.initialize(lock)
		except _vocalizer.VeError as e:
			if e.code == _vocalizer.VAUTONVDA_ERROR_INVALID:
				log.info("Vocalizer license for NVDA is Invalid")
			elif e.code == _vocalizer.VAUTONVDA_ERROR_DEMO_EXPIRED:
				log.info("Vocalizer demo license for NVDA as expired.")
			raise

	@classmethod
	def engineOff(cls):
		try:
			_vocalizer.terminate()
		except BaseException:
			pass

	@classmethod
	def voices(cls):
		result = []
		if not cls.ready():
			return result

		languages = _vocalizer.getLanguageList()
		languageNamesToLocales = {l.szLanguage.decode(): _languages.getLocaleNameFromTLW(l.szLanguageTLW.decode()) for l in languages}
		for language in languages:
			voices = _vocalizer.getVoiceList(language.szLanguage)
			for voice in voices:
				localeName = languageNamesToLocales.get(voice.szLanguage.decode(), "unknown")
				if not isinstance(localeName, str):
					localeName = "unknown"
				langDescription = languageHandler.getLanguageDescription(localeName)
				if not langDescription:
					langDescription = voice.szLanguage.decode()
				name = voice.szVoiceName.decode()
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

	def loadParameter(self):
		self.waitfactor = config.conf["WorldVoice"]["other"]["WaitFactor"]
		super().loadParameter()
