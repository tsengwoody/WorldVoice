from collections import OrderedDict, defaultdict
from functools import reduce
import itertools
import math
import operator
import weakref

from autoSettingsUtils.utils import paramToPercent, percentToParam
import comtypes.client
from comtypes import COMError
import config
from enum import IntEnum
import languageHandler
import locale
from logHandler import log
import nvwave
from synthDriverHandler import VoiceInfo

try:
	from synthDriverHandler import getSynth
except:
	from speech import getSynth

from . import _languages
from ._taskManager import TaskManager
from . import _vocalizer
from . import _sapi5
from .dataProcess import groupByField

VOICE_PARAMETERS = [
	("rate", int, 50),
	("pitch", int, 50),
	("volume", int, 50),
	("variant", str, ""),
]

taskManager = None

class Voice(object):
	def loadParameter(self):
		voiceName = self.name
		if voiceName in config.conf["WorldVoice"]["voices"]:
			for p, t, _ in VOICE_PARAMETERS:
				if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]:
					try:
						value = config.conf["speech"][getSynth().name].get(p, None)
					except:
						value = config.conf["WorldVoice"]['voices'][voiceName].get(p, None)
				else:
					value = config.conf["WorldVoice"]['voices'][voiceName].get(p, None)
				if value is None:
					continue
				setattr(self, p, t(value))
		else:
			config.conf["WorldVoice"]["voices"][voiceName] = {}
			for p, t, d in VOICE_PARAMETERS:
				config.conf["WorldVoice"]['voices'][voiceName][p] = t(d)
				setattr(self, p, t(d))

		self.commitRate = self.rate
		self.commitPitch = self.pitch
		self.commitVolume = self.volume

	def commit(self):
		self.commitRate = self.rate
		self.commitPitch = self.pitch
		self.commitVolume = self.volume

		voiceName = self.name
		if voiceName not in config.conf["WorldVoice"]["voices"]:
			config.conf["WorldVoice"]["voices"][voiceName] = {}
		for p, t, _ in VOICE_PARAMETERS:
			config.conf["WorldVoice"]["voices"][voiceName][p] = t(getattr(self, p))

	def rollback(self):
		self.rate = self.commitRate
		self.pitch = self.commitPitch
		self.volume = self.commitVolume

		voiceName = self.name
		if voiceName not in config.conf["WorldVoice"]["voices"]:
			config.conf["WorldVoice"]["voices"][voiceName] = {}
		for p, t, _ in VOICE_PARAMETERS:
			config.conf["WorldVoice"]["voices"][voiceName][p] = t(getattr(self, p))


class VEVoice(Voice):
	def __init__(self, name):
		self.engine = "VE"
		self.tts, self.name = _vocalizer.open(name) if name != "default" else _vocalizer.open()
		self.id = name

		languages = _vocalizer.getLanguageList()
		voiceInfos = []
		self._languageNamesToLocales = {l.szLanguage.decode() : _languages.getLocaleNameFromTLW(l.szLanguageTLW.decode()) for l in languages}
		self._localesToLanguageNames = {v : k for (k, v) in self._languageNamesToLocales.items()}
		for l in languages:
			voices = _vocalizer.getVoiceList(l.szLanguage)
			voiceInfos.extend([self._makeVoiceInfo(v) for v in voices])

		info = None
		for i in voiceInfos:
			if i.id == name:
				info = i
				break

		try:
			self.description = info.displayName
		except AttributeError:
			self.description = None
		try:
			self.language = info.language
		except AttributeError:
			self.language = None

		self.rate = 50
		self.pitch = 50
		self.volume = 50
		self.variant = ""

		self.commitRate = 50
		self.commitPitch = 50
		self.commitVolume = 50

		self.loadParameter()

	def speak(self, text):
		def _speak():
			_vocalizer.processText2Speech(self.tts, text)
		taskManager.add((self, _speak),)

	def breaks(self, time):
		maxTime = 6553 if self.variant == "bet2" else 65535
		breakTime = max(1, min(time, maxTime))
		_vocalizer.processBreak(self.tts, breakTime)

	def stop(self):
		_vocalizer.stop()

	def pause(self):
		_vocalizer.pause()

	def resume(self):
		_vocalizer.resume()

	def close(self):
		_vocalizer.close(self.tts)

	@property
	def rate(self):
		# self._rate = _vocalizer.getParameter(self.tts, _vocalizer.VE_PARAM_SPEECHRATE, type_=int)
		# return paramToPercent(self._rate, _vocalizer.RATE_MIN, _vocalizer.RATE_MAX)
		rate = self._rate = _vocalizer.getParameter(self.tts, _vocalizer.VE_PARAM_SPEECHRATE, type_=int)
		norm = rate / 100.0
		factor = 25 if norm  >= 1 else 50
		return int(round(50 + factor * math.log(norm, 2)))

	@rate.setter
	def rate(self, percent):
		# self._rate = percentToParam(percent, _vocalizer.RATE_MIN, _vocalizer.RATE_MAX)
		# _vocalizer.setParameter(self.tts, _vocalizer.VE_PARAM_SPEECHRATE, self._rate)
		value = percent
		factor = 25.0 if value >= 50 else 50.0
		norm = 2.0 ** ((value - 50.0) / factor)
		self._rate = value = int(round(norm * 100))
		_vocalizer.setParameter(self.tts, _vocalizer.VE_PARAM_SPEECHRATE, self._rate)

	@property
	def pitch(self):
		# self._pitch = _vocalizer.getParameter(self.tts, _vocalizer.VE_PARAM_PITCH, type_=int)
		# return paramToPercent(self._pitch, _vocalizer.PITCH_MIN, _vocalizer.PITCH_MAX)
		norm = self._pitch / 100.0
		factor = 50
		return int(round(50 + factor * math.log(norm, 2)))

	@pitch.setter
	def pitch(self, percent):
		# self._pitch = percentToParam(percent, _vocalizer.PITCH_MIN, _vocalizer.PITCH_MAX)
		# _vocalizer.setParameter(self.tts, _vocalizer.VE_PARAM_PITCH, self._pitch)
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
		self._variants = dbs = _vocalizer.getSpeechDBList(language, self.name)
		return self._variants

	@property
	def variant(self):
		self._variant = _vocalizer.getParameter(self.tts, _vocalizer.VE_PARAM_VOICE_OPERATING_POINT, type_=str)
		return self._variant

	@variant.setter
	def variant(self, value):
		self._variant = value
		_vocalizer.stop()
		_vocalizer.setParameter(self.tts, _vocalizer.VE_PARAM_VOICE_OPERATING_POINT, value)

	@classmethod
	def _makeVoiceInfo(self, v):
		self._languageNamesToLocales = {l.szLanguage.decode() : _languages.getLocaleNameFromTLW(l.szLanguageTLW.decode()) for l in _vocalizer.getLanguageList()}
		localeName = self._languageNamesToLocales.get(v.szLanguage.decode(), None)
		langDescription = None
		# if we have the locale name use the localized language description from windows:
		if localeName is not None:
			langDescription = languageHandler.getLanguageDescription(localeName)
		if not langDescription:
			# For some languages (i.g. scotish english) windows doesn't gives us any description.
			# The synth returned something in english, it is better than nothing.
			langDescription = v.szLanguage.decode()
		name = "%s - %s" % (v.szVoiceName.decode(), langDescription)
		return VoiceInfo(v.szVoiceName.decode(), name, localeName or None)


class SPAudioState(IntEnum):
	# https://docs.microsoft.com/en-us/previous-versions/windows/desktop/ms720596(v=vs.85)
	CLOSED = 0
	STOP = 1
	PAUSE = 2
	RUN = 3


class SpeechVoiceSpeakFlags(IntEnum):
	# https://docs.microsoft.com/en-us/previous-versions/windows/desktop/ms720892(v=vs.85)
	Async = 1
	PurgeBeforeSpeak = 2
	IsXML = 8


class Sapi5Voice(Voice):
	def __init__(self, name):
		self.engine = "SAPI5"
		self.tts, self.ttsAudioStream, self._eventsConnection = _sapi5.open(name) if name != "default" else _sapi5.open()

		self.name = self.tts.voice.getattribute('name')
		self.id = self.tts.voice.Id
		self.description = self.tts.voice.GetDescription()
		try:
			self.language = locale.windows_locale[int(self.tts.voice.getattribute('language').split(';')[0],16)]
		except KeyError:
			self.language=None

	def speak(self, text):
		def _speak():
			_sapi5.processText2Speech(self, text)
		taskManager.add((self, _speak),)

	def stop(self):
		# SAPI5's default means of stopping speech can sometimes lag at end of speech, especially with Win8 / Win 10 Microsoft Voices.
		# Therefore  instruct the underlying audio interface to stop first, before interupting and purging any remaining speech.
		if self.ttsAudioStream:
			self.ttsAudioStream.setState(SPAudioState.STOP, 0)
		self.tts.Speak(None, SpeechVoiceSpeakFlags.Async | SpeechVoiceSpeakFlags.PurgeBeforeSpeak)

		_sapi5.stop()

	def pause(self):
		try:
			# SAPI5's default means of pausing in most cases is either extremely slow
			# (e.g. takes more than half a second) or does not work at all.
			# Therefore instruct the underlying audio interface to pause instead.
			if self.ttsAudioStream:
				self.ttsAudioStream.setState(SPAudioState.PAUSE, 0)
		except:
			pass

	def resume(self):
		try:
			# SAPI5's default means of pausing in most cases is either extremely slow
			# (e.g. takes more than half a second) or does not work at all.
			# Therefore instruct the underlying audio interface to pause instead.
			if self.ttsAudioStream:
				self.ttsAudioStream.setState(SPAudioState.RUN, 0)
		except:
			pass

	def close(self):
		self._eventsConnection = None
		self.tts = None
		self.ttsAudioStream = None

	@property
	def rate(self):
		self._rate = self.tts.Rate
		return (self._rate*5) + 50

	@rate.setter
	def rate(self, percent):
		self._rate = (percent - 50) // 5
		self.tts.Rate = self._rate

	@property
	def pitch(self):
		return (self._pitch + 25)*2

	@pitch.setter
	def pitch(self, percent):
		self._pitch = percent // 2 - 25

	@property
	def volume(self):
		self._volume = self.tts.Volume
		return self._volume

	@volume.setter
	def volume(self, percent):
		self._volume = percent
		self.tts.Volume = self._volume

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


class VoiceManager(object):
	tts = comtypes.client.CreateObject("SAPI.SPVoice")

	@classmethod
	def preOpen(self):
		return _vocalizer.preOpenVocalizer()

	def __init__(self, indexCallback):
		try:
			_vocalizer.initialize(indexCallback)
		except _vocalizer.VeError as e:
			if e.code == _vocalizer.VAUTONVDA_ERROR_INVALID:
				log.info("Vocalizer license for NVDA is Invalid")
			elif e.code == _vocalizer.VAUTONVDA_ERROR_DEMO_EXPIRED:
				log.info("Vocalizer demo license for NVDA as expired.")
			raise

		try:
			_sapi5.initialize()
		except:
			raise

		global taskManager
		taskManager = TaskManager()

		self._createCaches()
		self._defaultVoiceInstance = VEVoice("default")
		self._defaultVoiceInstance.loadParameter()
		log.debug("Created voiceManager instance. Default voice is %s", self._defaultVoiceInstance.name)
		self._instanceCache = {self._defaultVoiceInstance.name : self._defaultVoiceInstance}

		self.sapi5 = Sapi5Voice("Microsoft Hanhan Desktop")
		self.sapi52 = Sapi5Voice("Microsoft David Desktop")

	@property
	def defaultVoiceInstance(self):
		return self._defaultVoiceInstance

	@property
	def defaultVoiceName(self):
		return self._defaultVoiceInstance.name

	def setDefaultVoice(self, voiceName):
		if voiceName not in self._voiceInfos:
			log.debugWarning("Voice not available, using default voice.")
			return
		self._defaultVoiceInstance = self.getVoiceInstance(voiceName)

	def getVoiceInstance(self, voiceName):
		try:
			instance = self._instanceCache[voiceName]
		except KeyError:
			instance = self._createInstance(voiceName)
		return instance

	def _createInstance(self, voiceName):
		if self._voicesToEngines[voiceName] == "VE":
			voiceInstance = VEVoice(voiceName)
		elif self._voicesToEngines[voiceName] == "SAPI5":
			voiceInstance = Sapi5Voice(voiceName)

		self._instanceCache[voiceInstance.name] = voiceInstance
		voiceInstance.loadParameter()
		return self._instanceCache[voiceInstance.name]

	def onVoiceParameterConsistent(self, baseInstance):
		for voiceName, instance in self._instanceCache.items():
			instance.rate = baseInstance.rate
			instance.pitch = baseInstance.pitch
			instance.volume = baseInstance.volume
			instance.commit()

	def reload(self):
		for voiceName, instance in self._instanceCache.items():
			instance.loadParameter()

	def cancel(self):
		taskManager.clear()

	def close(self):
		for voiceName, instance in self._instanceCache.items():
			instance.commit()
			instance.close()
		_vocalizer.terminate()
		_sapi5.terminate()

		global taskManager
		del taskManager
		taskManager = None

	def _createCaches(self):
		""" Create tables and caches to keep information that won't change on the synth. """
		languages = _vocalizer.getLanguageList()
		self._languageNamesToLocales = {l.szLanguage.decode() : _languages.getLocaleNameFromTLW(l.szLanguageTLW.decode()) for l in languages}
		table = []
		for language in languages:
			voices = _vocalizer.getVoiceList(language.szLanguage)
			for voice in voices:
				table.append({
					"name": voice.szVoiceName.decode(),
					"locale": self._languageNamesToLocales.get(voice.szLanguage.decode(), "unknown"),
					"engine": "VE",
				})

		voiceInfos = []
		voices = self.tts.getVoices()
		for i in range(len(voices)):
			try:
				name = voices[i].getattribute('name')
				description = voices[i].GetDescription()
				try:
					language = locale.windows_locale[int(voices[i].getattribute('language').split(';')[0], 16)]
				except KeyError:
					language="unknown"
				table.append({
					"name": name,
					"locale": language,
					"engine": "SAPI5",
				})
			except COMError:
				log.warning("Could not get the voice info. Skipping...")
			voiceInfos.append(VoiceInfo(name, description, language))

		self._localesToVoices = groupByField(table, 'locale', lambda i: i, lambda i: i['name'])
		# For locales with no country (i.g. "en") use all voices from all sub-locales
		locales = sorted(self._localesToVoices, key=self._localeGroupKey)
		for key, locales in itertools.groupby(locales, key=self._localeGroupKey):
			if key not in self._localesToVoices:
				self._localesToVoices[key] = reduce(operator.add, [self._localesToVoices[l] for l in locales])

		self._voicesToEngines = {}
		for item in table:
			self._voicesToEngines[item["name"]] = item["engine"]

		for l in languages:
			voices = _vocalizer.getVoiceList(l.szLanguage)
			voiceInfos.extend([VEVoice._makeVoiceInfo(v) for v in voices])

		log.debug("Voices : %s", self._localesToVoices)
		# Kepp a list with existing voices in VoiceInfo objects.
		# sort voices by language and then voice name
		voiceInfos = sorted(voiceInfos, key=lambda v: (v.language, v.id))
		items = [(v.id, v) for v in voiceInfos]
		self._voiceInfos = OrderedDict(items)

	@property
	def voiceInfos(self):
		return self._voiceInfos

	@property
	def languages(self):
		return self._languageNamesToLocales.values()

	@property
	def localeToVoicesMap(self):
		return self._localesToVoices.copy()

	@property
	def localesToNamesMap(self):
		return {locale: self._getLocaleReadableName(locale) for locale in self._localesToVoices}

	def getVoiceNameForLanguage(self, language):
		configured =  self._getConfiguredVoiceNameForLanguage(language)
		if configured is not None and configured in self.voiceInfos:
			return configured
		voices = self._localesToVoices.get(language, None)
		if voices is None:
			if '_' in language:
				voices = self._localesToVoices.get(language.split('_')[0], None)
		if voices is None:
			return None
		voice = self.defaultVoiceName if self.defaultVoiceName in voices else voices[0]
		return voice

	def getVoiceInstanceForLanguage(self, language):
		voiceName = self.getVoiceNameForLanguage(language)
		if voiceName:
			return self.getVoiceInstance(voiceName)
		return None

	def _getConfiguredVoiceNameForLanguage(self, language):
		if language in config.conf["WorldVoice"]['autoLanguageSwitching']:
			return config.conf["WorldVoice"]['autoLanguageSwitching'][language]['voice']
		return None

	def _localeGroupKey(self, localeName):
		if '_' in localeName:
			return localeName.split('_')[0]
		else:
			return localeName

	def getVoiceLanguage(self, voiceName=None):
		if voiceName is None:
			voiceName = self._defaultVoiceInstance.name
		return self._voiceInfos[voiceName].language

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s - %s" % (description, locale) if description else locale
