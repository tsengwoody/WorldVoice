#vocalizer/__init__.py
#A part of the vocalizer driver for NVDA (Non Visual Desktop Access)
#Copyright (C) 2012 Rui Batista <ruiandrebatista@gmail.com>
#Copyright (C) 2012 Tiflotecnia, lda. <www.tiflotecnia.com>
#Copyright (C) 2019 Leonard de Ruijter (Babbage B.V.) <leonard@babbage.com>
#This file is covered by the GNU General Public License.
#See the file GPL.txt for more details.

from collections import OrderedDict
import math
import operator
import wx

import addonHandler
import config
from synthDriverHandler import SynthDriver as BaseDriver, VoiceInfo, synthIndexReached, synthDoneSpeaking
import languageHandler
from logHandler import log
import speech
from . import _languages
from . import _vocalizer
from . import _veTypes
from ._voiceManager import VoiceManager

from . import languageDetection
from . import _config

driverVersion = addonHandler.getCodeAddon().manifest['version']
synthVersion = "1.1.1" # It would be great if the synth reported that...

voiceModelNames = {"full_vssq5f22" : "Premium High",
	"full_155mrf22" : "Premium",
	"dri80_1175mrf22" : "Plus",
	"dri40_155mrf22" : "Standard",
	"bet3" : "Compact"}

voiceOperatingPointNames = {"full_vssq5f22" : "Premium High",
	"full_155mrf22" : "Premium",
	"dri80_1175mrf22" : "Plus",
	"dri40_155mrf22" : "Standard",
	"bet3" : "Compact"}


class SynthDriver(BaseDriver):
	name = "MultipleWorldVoice"
	description = "Multiple World-Voice"
	supportedSettings = [
		BaseDriver.VoiceSetting(),
		BaseDriver.VariantSetting(),
		BaseDriver.RateSetting(),
		BaseDriver.PitchSetting(),
		BaseDriver.VolumeSetting(),
	]
	supportedCommands = {
		speech.IndexCommand,
		speech.CharacterModeCommand,
		speech.LangChangeCommand,
		speech.BreakCommand,
		speech.PitchCommand,
		speech.RateCommand,
		speech.VolumeCommand,
	}
	supportedNotifications = {synthIndexReached, synthDoneSpeaking}

	@classmethod
	def check(cls):
		synth = speech.getSynth()
		if synth and synth.name == cls.name:
			return True # Synth is running so is available.
		try:
			_vocalizer.preInitialize()
			return True
		except:
			log.debugWarning("Vocalizer not available.", exc_info=True)
			return False
		finally:
			try:
				_vocalizer.postTerminate()
			except _vocalizer.VeError:
				log.debugWarning("Error terminating vocalizer", exc_info=True)

	def __init__(self):
		self._veRate = 100
		self._vePitch = 100
		_config.load()

		# Initialize the driver
		try:
			_vocalizer.initialize(self._onIndexReached)
			log.debug("Vocalizer info: %s" % self._info())
		except _vocalizer.VeError as e:
			if e.code == _vocalizer.VAUTONVDA_ERROR_INVALID:
				log.info("Vocalizer license for NVDA is Invalid")
			elif e.code == _vocalizer.VAUTONVDA_ERROR_DEMO_EXPIRED:
				log.info("Vocalizer demo license for NVDA as expired.")
			raise
		self._voiceManager = VoiceManager()
		# Patch speech.speak and store a reference to the real speak function.
		self._realSpeakFunc = speech.speak
		self._realSpellingFunc = speech.speakSpelling
		speech.speak = self.patchedSpeak
		speech.speakSpelling = self.patchedSpeakSpelling
		self._languageDetector = languageDetection.LanguageDetector(self._voiceManager.languages)


	def _onIndexReached(self, index):
		if index is not None:
			synthIndexReached.notify(synth=self, index=index)
		else:
			synthDoneSpeaking.notify(synth=self)

	def terminate(self):
		speech.speak = self._realSpeakFunc
		speech.speakSpelling = self._realSpellingFunc
		try:
			self.cancel()
			self._voiceManager.close()
			_vocalizer.terminate()
		except RuntimeError:
			log.error("Vocalizer terminate", exc_info=True)


	def speak(self, speechSequence):
		voiceInstance = defaultInstance = self._voiceManager.defaultVoiceInstance
		currentLanguage = defaultLanguage = self.language
		chunks = []
		charMode = False
		for command in speechSequence:
			if isinstance(command, str):
				# If character mode is on use lower case characters
				# Because the synth does not allow to turn off the caps reporting
				if charMode:
					command = command.lower()
				# replace the escape character since it is used for parameter changing
				chunks.append(command.replace('\x1b', ''))
			elif isinstance(command, speech.IndexCommand):
				# start and end The spaces here seem to be important
				chunks.append(f" \x1b\\mrk={command.index}\\ ")
			elif isinstance(command, speech.BreakCommand):
				maxTime = 6553 if self.variant == "bet2" else 65535
				breakTime = max(1, min(command.time, maxTime))
				chunks.append(f" \x1b\\pause={breakTime}\\ ")
			elif isinstance(command, speech.RateCommand):
				boundedValue = max(0, min(command.newValue, 100))
				factor = 25.0 if boundedValue >= 50 else 50.0
				norm = 2.0 ** ((boundedValue - 50.0) / factor)
				value = int(round(norm * 100))
				chunks.append(f" \x1b\\rate={value}\\ ")
			elif isinstance(command, speech.PitchCommand):
				boundedValue = max(0, min(command.newValue, 100))
				factor = 50.0
				norm = 2.0 ** ((boundedValue - 50.0) / factor)
				value = int(round(norm * 100))
				chunks.append(f" \x1b\\pitch={value}\\ ")
			elif isinstance(command, speech.VolumeCommand):
				value = max(0, min(command.newValue, 100))
				chunks.append(f" \x1b\\vol={value}\\ ")
			elif isinstance(command, speech.CharacterModeCommand):
				charMode = command.state
				s = " \x1b\\tn=spell\\ " if command.state else " \x1b\\tn=normal\\ "
				chunks.append(s)
			elif isinstance(command, speech.LangChangeCommand):
				if command.lang == currentLanguage:
					# Keep on the same voice.
					continue
				if command.lang is None:
					# No language, use default.
					voiceInstance = defaultInstance
					currentLanguage = defaultLanguage
					continue
				# Changed language, lets see what we have.
				newInstance = self._voiceManager.getVoiceInstanceForLanguage(command.lang)
				currentLanguage = command.lang
				if newInstance is None:
					# No voice for this language, use default.
					newInstance = defaultInstance
				if newInstance == voiceInstance:
					# Same voice, next command.
					continue
				if chunks: # We changed voice, send what we already have to vocalizer.
					_vocalizer.processText2Speech(voiceInstance, "".join(chunks))
					chunks = []
				voiceInstance = newInstance
		if chunks:
			_vocalizer.processText2Speech(voiceInstance, "".join(chunks))

	def patchedSpeak(self, speechSequence, symbolLevel=None, priority=None):
		if config.conf["speech"]["autoLanguageSwitching"] \
			and _config.vocalizerConfig['autoLanguageSwitching']['useUnicodeLanguageDetection']:
			speechSequence = self._languageDetector.add_detected_language_commands(speechSequence)
		self._realSpeakFunc(speechSequence, symbolLevel, priority=priority)

	def patchedSpeakSpelling(self, text, locale=None, useCharacterDescriptions=False, priority=None):
		if config.conf["speech"]["autoLanguageSwitching"] \
			and _config.vocalizerConfig['autoLanguageSwitching']['useUnicodeLanguageDetection']:
				for text, loc in self._languageDetector.process_for_spelling(text, locale):
					self._realSpellingFunc(text, loc, useCharacterDescriptions, priority=priority)
		else:
			self._realSpellingFunc(text, locale, useCharacterDescriptions, priority=priority)

	def cancel(self):
		_vocalizer.stop()

	def pause(self, switch):
		if switch:
			_vocalizer.pause()
		else:
			_vocalizer.resume()

	def _get_volume(self):
		return _vocalizer.getParameter(self._voiceManager.defaultVoiceInstance, _vocalizer.VE_PARAM_VOLUME)

	def _set_volume(self, value):
		self._voiceManager.setVoiceParameter(self._voiceManager.defaultVoiceInstance, _vocalizer.VE_PARAM_VOLUME, int(value))

	# Vocalizer rate goes from 50 (2x slower than normal) 
	# to 400 (4 x faaster than normal).
	# we map 0% to 50, 100 to 50% and 400% to 100%.
	# This is an exponential function of base 2.
	# But we use  a multiplicative factor of 50 on the first half and 25 on the remaining.
	def _get_rate(self):
		self._veRate = _vocalizer.getParameter(self._voiceManager.defaultVoiceInstance, _vocalizer.VE_PARAM_SPEECHRATE)
		norm = self._veRate / 100.0
		factor = 25 if norm  >= 1 else 50
	# Floating point madness...
		return int(round(50 + factor * math.log(norm, 2)))

	def _set_rate(self, value):
		# Simply the inverse of the above, no magic, just plain math.
		factor = 25.0 if value >= 50 else 50.0
		norm = 2.0 ** ((value - 50.0) / factor)
		value = int(round(norm * 100))
		self._voiceManager.setVoiceParameter(self._voiceManager.defaultVoiceInstance, _vocalizer.VE_PARAM_SPEECHRATE, value)
		self._veRate = value

	# Pitch is exponential, but the factor is constant.
	def _get_pitch(self):
		self._vePitch = _vocalizer.getParameter(self._voiceManager.defaultVoiceInstance, _vocalizer.VE_PARAM_PITCH)
		norm = self._vePitch / 100.0
		factor = 50
	# Floating point madness...
		return int(round(50 + factor * math.log(norm, 2)))

	def _set_pitch(self, value):
		# Simply the inverse of the above, no magic, just plain math.
		factor = 50.0
		norm = 2.0 ** ((value - 50.0) / factor)
		value = int(round(norm * 100))
		self._voiceManager.setVoiceParameter(self._voiceManager.defaultVoiceInstance, _vocalizer.VE_PARAM_PITCH, value)
		self._vePitch = value

	def _getAvailableVoices(self):
		return self._voiceManager.voiceInfos

	def _get_voice(self):
		return self._voiceManager.defaultVoiceName

	def _set_voice(self, voiceName):
		if voiceName == self._voiceManager.defaultVoiceName:
			return
		# Stop speech before setting a new voice to avoid voice instances
		# continuing speaking when changing voices for, e.g., say-all
		# See NVDA ticket #3540
		_vocalizer.stop()
		self._voiceManager.setDefaultVoice(voiceName)
		# Available variants are cached by default. As variants maybe different for each voice remove the cached value
		if hasattr(self, '_availableVariants'):
			del self._availableVariants
		# Synchronize with the synth so the parameters
		# we report are not from the previous voice.
		_vocalizer.sync()

	def _get_variant(self):
		return _vocalizer.getParameter(self._voiceManager.defaultVoiceInstance, _veTypes.VE_PARAM_VOICE_OPERATING_POINT, type_=str)

	def _set_variant(self, name):
		try:
			self._voiceManager.setVoiceParameter(self._voiceManager.defaultVoiceInstance, _vocalizer.VE_PARAM_VOICE_OPERATING_POINT, name)
		except _vocalizer.VeError:
			# some models may not be available.
			log.debugWarning("Model not available: %s", name)

	def _getAvailableVariants(self):
		language = _vocalizer.getParameter(self._voiceManager.defaultVoiceInstance, _vocalizer.VE_PARAM_LANGUAGE, type_=str) # FIXME: store language...
		voice = self.voice
		dbs = _vocalizer.getSpeechDBList(language, voice)
		# return OrderedDict([(d, VoiceInfo(d, voiceModelNames[d])) for d in dbs])
		return OrderedDict([(d, VoiceInfo(d, d)) for d in dbs])
	
	def _get_availableLanguages(self):
		return self._voiceManager.languages

	def _get_language(self):
		return self._voiceManager.getVoiceLanguage()

	def _info(self):
		s = [self.description]
		s.append("driver version %s" % driverVersion)
		return ", ".join(s)
