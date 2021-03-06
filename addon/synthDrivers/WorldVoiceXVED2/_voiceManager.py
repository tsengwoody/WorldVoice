#vocalizer/_voiceManager.py
#A part of the vocalizer driver for NVDA (Non Visual Desktop Access)
#Copyright (C) 2012 Rui Batista <ruiandrebatista@gmail.com>
#Copyright (C) 2012 Tiflotecnia, lda. <www.tiflotecnia.com>
#This file is covered by the GNU General Public License.
#See the file GPL.txt for more details.

from collections import OrderedDict, defaultdict
from functools import reduce
import itertools
import math
import operator

from autoSettingsUtils.utils import paramToPercent, percentToParam
import languageHandler
from logHandler import log
from synthDriverHandler import VoiceInfo

from . import _config
from . import _languages
from . import _vocalizer

VOICE_PARAMETERS = [
	(_vocalizer.VE_PARAM_VOICE_OPERATING_POINT, "variant", str),
	(_vocalizer.VE_PARAM_SPEECHRATE, "rate", int),
	(_vocalizer.VE_PARAM_PITCH, "pitch", int),
	(_vocalizer.VE_PARAM_VOLUME, "volume", int),
]

VOICE_PARAMETERS2 = [
	("rate", int),
	("pitch", int),
	("volume", int),
]

# PARAMETERS_TO_UPDATE = [_vocalizer.VE_PARAM_VOLUME, _vocalizer.VE_PARAM_SPEECHRATE, _vocalizer.VE_PARAM_PITCH]
PARAMETERS_TO_UPDATE = [_vocalizer.VE_PARAM_VOLUME, _vocalizer.VE_PARAM_PITCH]


class Voice(object):
	def __init__(self, token, name):
		self.token = token
		self.id = name
		self.name = name

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

		self.rate = 14
		self.pitch = 50
		self.volume = 50

		self.commitRate = 14
		self.commitPitch = 50
		self.commitVolume = 50

	def commit(self):
		self.commitRate = self.rate
		self.commitPitch = self.pitch
		self.commitVolume = self.volume

	def rollback(self):
		self.rate = self.commitRate
		self.pitch = self.commitPitch
		self.volume = self.commitVolume

	@property
	def rate(self):
		self._rate = _vocalizer.getParameter(self.token, _vocalizer.VE_PARAM_SPEECHRATE, type_=int)
		return paramToPercent(self._rate, _vocalizer.RATE_MIN, _vocalizer.RATE_MAX)
		"""rate = self._rate = _vocalizer.getParameter(self.token, _vocalizer.VE_PARAM_SPEECHRATE, type_=int)
		norm = rate / 100.0
		factor = 25 if norm  >= 1 else 50
		return int(round(50 + factor * math.log(norm, 2)))"""

	@rate.setter
	def rate(self, percent):
		self._rate = percentToParam(percent, _vocalizer.RATE_MIN, _vocalizer.RATE_MAX)
		_vocalizer.setParameter(self.token, _vocalizer.VE_PARAM_SPEECHRATE, self._rate)
		"""value = percent
		factor = 25.0 if value >= 50 else 50.0
		norm = 2.0 ** ((value - 50.0) / factor)
		self._rate = value = int(round(norm * 100))
		_vocalizer.setParameter(self.token, _vocalizer.VE_PARAM_SPEECHRATE, self._rate)"""

	@property
	def pitch(self):
		# self._pitch = _vocalizer.getParameter(self.token, _vocalizer.VE_PARAM_PITCH, type_=int)
		# return paramToPercent(self._pitch, _vocalizer.PITCH_MIN, _vocalizer.PITCH_MAX)
		norm = self._pitch / 100.0
		factor = 50
		return int(round(50 + factor * math.log(norm, 2)))

	@pitch.setter
	def pitch(self, percent):
		# self._pitch = percentToParam(percent, _vocalizer.PITCH_MIN, _vocalizer.PITCH_MAX)
		# _vocalizer.setParameter(self.token, _vocalizer.VE_PARAM_PITCH, self._pitch)
		value = percent
		factor = 50.0
		norm = 2.0 ** ((value - 50.0) / factor)
		self._pitch = value = int(round(norm * 100))
		_vocalizer.setParameter(self.token, _vocalizer.VE_PARAM_PITCH, self._pitch)

	@property
	def volume(self):
		self._volume = _vocalizer.getParameter(self.token, _vocalizer.VE_PARAM_VOLUME, type_=int)
		return self._volume

	@volume.setter
	def volume(self, percent):
		self._volume = percent
		_vocalizer.setParameter(self.token, _vocalizer.VE_PARAM_VOLUME, int(self._volume))

	@property
	def variants(self):
		language = _vocalizer.getParameter(self.token, _vocalizer.VE_PARAM_LANGUAGE, type_=str)
		self._variants = dbs = _vocalizer.getSpeechDBList(language, self.name)
		return self._variants

	@property
	def variant(self):
		self._variant = _vocalizer.getParameter(self.token, _vocalizer.VE_PARAM_VOICE_OPERATING_POINT, type_=str)
		return self._variant

	@volume.setter
	def variant(self, value):
		self._variant = value
		_vocalizer.setParameter(self.token, _vocalizer.VE_PARAM_VOICE_OPERATING_POINT, name)

	def _makeVoiceInfo(self, v):
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


class VoiceManager(object):
	def __init__(self):
		_config.load()
		self._createCaches()
		self._defaultInstance, self._defaultVoiceName = _vocalizer.open()
		self._defaultVoiceInstance = Voice(self._defaultInstance, self._defaultVoiceName)
		self.onVoiceLoad(self._defaultVoiceName, self._defaultVoiceInstance)
		log.debug("Created voiceManager instance. Default voice is %s", self._defaultVoiceName)
		self._instanceCache = {self._defaultVoiceName : self._defaultVoiceInstance}

	@property
	def defaultVoiceInstance(self):
		return self._defaultVoiceInstance

	@property
	def defaultVoiceName(self):
		return self._defaultVoiceName

	def setDefaultVoice(self, voiceName):
		if voiceName not in self._voiceInfos:
			log.debugWarning("Voice not available, using default voice.")
			return
		instance = self.getVoiceInstance(voiceName)
		self._defaultVoiceInstance = instance
		self._defaultInstance = instance.token
		self._defaultVoiceName = voiceName

	def getVoiceInstance(self, voiceName):
		try:
			instance = self._instanceCache[voiceName]
		except KeyError:
			instance = self._createInstance(voiceName)
		if self._voiceParametersCount[instance] < self._voiceParametersCount[self._defaultInstance]:
			self._updateParameters(instance.token)
		return instance

	def _createInstance(self, voiceName):
		instance, name = _vocalizer.open(voiceName)
		voiceInstance = Voice(instance, name)
		self._instanceCache[name] = voiceInstance
		self.onVoiceLoad(voiceName, voiceInstance)
		return self._instanceCache[name]

	def close(self):
		for voiceName, instance in self._instanceCache.items():
			self.onVoiceUnload(voiceName, instance)
			_vocalizer.close(instance.token)
		_config.save() # Flush the configuration file

	def _createCaches(self):
		""" Create tables and caches to keep information that won't change on the synth. """
		self._localesToVoices = {}
		self._voiceParametersCount = defaultdict(lambda : 0)
		languages = _vocalizer.getLanguageList()
		voiceInfos = []
		self._languageNamesToLocales = {l.szLanguage.decode() : _languages.getLocaleNameFromTLW(l.szLanguageTLW.decode()) for l in languages}
		self._localesToLanguageNames = {v : k for (k, v) in self._languageNamesToLocales.items()}
		# Keep lists of voices appropriate for each locale.
		# Also collect existing voices for quick listing.
		for l in languages:
			voices = _vocalizer.getVoiceList(l.szLanguage)
			voiceInfos.extend([self._makeVoiceInfo(v) for v in voices])
			voiceNames = [v.szVoiceName.decode() for v in voices]
			self._localesToVoices[self._languageNamesToLocales[l.szLanguage.decode()]] = voiceNames

		# For locales with no country (i.g. "en") use all voices from all sub-locales
		locales = sorted(self._localesToVoices, key=self._localeGroupKey)
		for key, locales in itertools.groupby(locales, key=self._localeGroupKey):
			if key not in self._localesToVoices:
				self._localesToVoices[key] = reduce(operator.add, [self._localesToVoices[l] for l in locales])

		log.debug("Voices : %s", self._localesToVoices)
		# Kepp a list with existing voices in VoiceInfo objects.
		# sort voices by language and then voice name
		voiceInfos = sorted(voiceInfos, key=lambda v: (v.language, v.id))
		items = [(v.id, v) for v in voiceInfos]
		self._voiceInfos = OrderedDict(items)

	def getVoiceParameter(self, instance, param, type_):
		return _vocalizer.getParameter(instance, param, type_=type_)

	def setVoiceParameter(self, instance, param, value):
		_vocalizer.setParameter(instance, param, value)
		if param in PARAMETERS_TO_UPDATE and instance == self._defaultInstance:
			self._voiceParametersCount[instance] += 1

	def _updateParameters(self, instance):
		newParams = [(param, _vocalizer.getParameter(self._defaultInstance, param)) for param in PARAMETERS_TO_UPDATE]
		_vocalizer.setParameters(instance, newParams)
		self._voiceParametersCount[instance] = self._voiceParametersCount[self._defaultInstance]

	@property
	def voiceInfos(self):
		return self._voiceInfos

	@property
	def languages(self):
		return iter(self._localesToLanguageNames)

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
		if language in _config.vocalizerConfig['autoLanguageSwitching']:
			return _config.vocalizerConfig['autoLanguageSwitching'][language]['voice']
		return None

	def onVoiceLoad(self, voiceName, instance):
		""" Restores variant and other settings if available, when a voice is loaded."""

		if voiceName in _config.vocalizerConfig['voices']:
			for p, t in VOICE_PARAMETERS2:
				value = _config.vocalizerConfig['voices'][voiceName].get(p, None)
				if value is None:
					continue
				# p = "commit" + p.capitalize()
				setattr(instance, p, t(value))
			instance.commit()

	def onVoiceUnload(self, voiceName, instance):
		""" Saves variant to be restored for each voice."""

		if voiceName not in _config.vocalizerConfig['voices']:
			_config.vocalizerConfig['voices'][voiceName] = {}

		for p, t in VOICE_PARAMETERS2:
			# p = "commit" + p.capitalize()
			value = t(getattr(instance, p))
			_config.vocalizerConfig['voices'][voiceName][p] = value

	def _localeGroupKey(self, localeName):
		if '_' in localeName:
			return localeName.split('_')[0]
		else:
			return localeName

	def getVoiceLanguage(self, voiceName=None):
		if voiceName is None:
			voiceName = self._defaultVoiceName
		return self._voiceInfos[voiceName].language

	def _makeVoiceInfo(self, v):
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

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s - %s" % (description, locale) if description else locale
