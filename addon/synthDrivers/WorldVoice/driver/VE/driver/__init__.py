import math
import threading
import unicodedata
import os
from io import BytesIO
from collections import OrderedDict
from ctypes import *

import config
import nvwave
import languageHandler
import addonHandler
import speech
from speech.commands import IndexCommand, CharacterModeCommand, LangChangeCommand, PitchCommand, BreakCommand, SpeechCommand, RateCommand, VolumeCommand
from synthDriverHandler import SynthDriver, LanguageInfo, VoiceInfo, synthIndexReached, synthDoneSpeaking
from autoSettingsUtils.driverSetting import DriverSetting
from autoSettingsUtils.utils import StringParameterInfo
from logHandler import log

from . import ve2
from .ve2.veTypes import *

addonHandler.initTranslation()

BIN_DICT_CONTENT_TYPE = "application/edct-bin-dictionary"
TEXT_RULESET_CONTENT_TYPE = "application/x-vocalizer-rettt+text"
_voiceDicts = {}
_tuningDataDir = os.path.join(os.path.dirname(__file__), "tuningData")

VOICE_PARAMETERS = [
	(VE_PARAM_VOICE_OPERATING_POINT, "variant", str),
	(VE_PARAM_SPEECHRATE, "rate", int),
	(VE_PARAM_PITCH, "pitch", int),
	(VE_PARAM_VOLUME, "volume", int),
	(VE_PARAM_WAITFACTOR, "waitfactor", int),
]

def getResourcePaths():
	resourcePaths = [addon.path for addon in addonHandler.getRunningAddons() if addon.name.startswith("vocalizer-expressive2-voice")]

	user_folder = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))))
	WVW_PATH = os.path.join(user_folder, "WorldVoice-workspace", "VE")
	resourcePaths.append(WVW_PATH)

	programdata = os.getenv("PROGRAMDATA")
	if programdata:
		# Looking for Vocalizer voice data from Freedom Scientific
		for version in ("2.2", "21"):
			path = os.path.join(programdata, "Freedom Scientific", "VocalizerExpressive", version, "languages")
			try:
				if os.listdir(path):
					resourcePaths.append(path)
			except IOError:
				pass
	return resourcePaths

def getAvailableResources():
	resources = OrderedDict()
	for l in ve2.getLanguageList():
		langCode = ve2.getLocaleNameFromTLW(l.szLanguageTLW.decode("utf-8"))
		if langCode is None: # Unknown language, skip it
			continue
		languageInfo = LanguageInfo(langCode)

		if not languageInfo.displayName:
			languageInfo.displayName = l.szLanguage
		resources[languageInfo] = []

		for v in ve2.getVoiceList(l.szLanguage):
			name = f'{v.szVoiceName.decode("utf-8")} - {languageInfo.displayName}'
			voiceInfo = VoiceInfo(v.szVoiceName.decode("utf-8"), name, languageInfo.id or None)
			resources[languageInfo].append(voiceInfo)

	return resources

pcmBufLen = 8192 # 8 Kb
markBufSize = 100

class VECallback(object):

	def __init__(self, player, isSilence, onIndexReached):
		self._player = player
		self._isSilence = isSilence
		self._onIndexReached = onIndexReached
		# allocate PCM and mark buffers
		self._pcmBuf = (c_byte * pcmBufLen)()
		self._markBuf = (VE_MARKINFO * markBufSize)()
		self._feedBuf = BytesIO()
		self._sampleRate = 22050
		self._sonicInitTried = False
		self._sonicEnabled = False
		self._sonicSpeed = 1.0
		self.sonicStream = None

	def _ensureSonicStream(self):
		if self._sonicEnabled:
			return True
		if self._sonicInitTried:
			return False
		self._sonicInitTried = True
		try:
			from synthDrivers._sonic import SonicStream, initialize as sonicInitialize
			sonicInitialize()
			self.sonicStream = SonicStream(self._sampleRate, 1)
			self.sonicStream.speed = self._sonicSpeed
			self._sonicEnabled = True
			return True
		except Exception:
			log.warning("Sonic unavailable in VE; using native speed path.", exc_info=True)
			self.sonicStream = None
			self._sonicEnabled = False
			return False

	def getSpeed(self):
		if self._sonicEnabled and self.sonicStream is not None:
			return float(self.sonicStream.speed)
		return float(self._sonicSpeed)

	def setSpeed(self, speed):
		self._sonicSpeed = float(speed)
		if self._sonicEnabled and self.sonicStream is not None:
			self.sonicStream.speed = self._sonicSpeed

	def __call__(self, instance, userData, message):
		""" Callback to handle assynchronous requests and messages from the synthecizer. """
		try:
			outData = cast(message.contents.pParam, POINTER(VE_OUTDATA))
			messageType = message.contents.eMessage
			if self._isSilence.isSet() and messageType != VE_MSG_ENDPROCESS:
				self._feedBuf = BytesIO()
				return NUAN_E_TTS_USERSTOP
			elif messageType == VE_MSG_OUTBUFREQ:
				# Request for storage to put sound and mark data.
				# Here we fill the pointers to our already allocated buffers (on initialize).
				outData.contents.pOutPcmBuf = cast(self._pcmBuf, c_void_p)
				outData.contents.cntPcmBufLen = c_uint(pcmBufLen)
				outData.contents.pMrkList = cast(self._markBuf, POINTER(VE_MARKINFO))
				outData.contents.cntMrkListLen = c_uint(markBufSize * sizeof(VE_MARKINFO))
			elif messageType == VE_MSG_OUTBUFDONE:
				# Sound data and mark buffers were produced by vocalizer.
				# Send wave data to be played:
				if outData.contents.cntPcmBufLen > 0:
					if self._ensureSonicStream():
						self.sonicStream.writeShort(
							outData.contents.pOutPcmBuf,
							outData.contents.cntPcmBufLen // 2,
						)
						spedArr = self.sonicStream.readShort()
						if spedArr:
							self._feedBuf.write(bytes(spedArr))
						if self._feedBuf.tell() >= pcmBufLen:
							self._player.feed(self._feedBuf.getvalue())
							self._feedBuf = BytesIO()
					else:
						data = string_at(outData.contents.pOutPcmBuf, outData.contents.cntPcmBufLen)
						self._player.feed(data)
				# Make sure that the speech is not interrupted by the user
				if self._isSilence.isSet():
					self._feedBuf = BytesIO()
					return NUAN_E_TTS_USERSTOP
				# And check for bookmarks
				for i in range(int(outData.contents.cntMrkListLen)):
					if outData.contents.pMrkList[i].eMrkType == VE_MRK_BOOKMARK:
						self._onIndexReached(outData.contents.pMrkList[i].ulMrkId)
			elif messageType == VE_MSG_ENDPROCESS:
				if self._sonicEnabled and self.sonicStream is not None:
					self.sonicStream.flush()
					tailArr = self.sonicStream.readShort()
					if tailArr and not self._isSilence.isSet():
						self._feedBuf.write(bytes(tailArr))
				if self._feedBuf.tell() and not self._isSilence.isSet():
					self._player.feed(self._feedBuf.getvalue())
				self._feedBuf = BytesIO()
		except:
			log.error("Vocalizer callback", exc_info=True)
		return NUAN_OK

class ProcessText2Speech(object):

	def __init__(self, instance, text):
		self._instance = instance
		self._text = text

	def __call__(self):
		ve2.processText2Speech(self._instance, self._text)

class TtsSetParamList(object):

	def __init__(self, instance, *idAndValues):
		self._instance = instance
		self._idAndValues = idAndValues

	@property
	def instance(self):
		return self._instance

	@property
	def idAndValues(self):
		return self._idAndValues

	def __call__(self):
		ve2.setParamList(self._instance, *self._idAndValues)

class DoneSpeaking(object):

	def __init__(self, player, onIndexReached):
		self._player = player
		self._onIndexReached = onIndexReached

	def __call__(self):
		self._player.idle()
		self._onIndexReached(None)

class SynthDriver(SynthDriver):
	name = "vocalizer_expressive2"
	description = "Nuance Vocalizer expressive 2.2"

	supportedSettings = [
		SynthDriver.VoiceSetting(),
		SynthDriver.VariantSetting(),
		SynthDriver.RateSetting(),
		SynthDriver.RateBoostSetting(),
		SynthDriver.PitchSetting(),
		SynthDriver.VolumeSetting(),
		DriverSetting("waitfactor", _("&Wait factor"), availableInSettingsRing=True),
		DriverSetting("normalization", _("&Normalization"), availableInSettingsRing=True),
	]
	supportedCommands = {
		IndexCommand,
		CharacterModeCommand,
		LangChangeCommand,
		PitchCommand,
		BreakCommand,
	}
	supportedNotifications = {synthIndexReached, synthDoneSpeaking}

	@classmethod
	def check(cls):
		resources = getResourcePaths()
		if not resources:
			return False
		with ve2.preOpenVocalizer(resources) as success:
			if not success:
				log.debugWarning("Vocalizer not available.", exc_info=True)
			return success

	def __init__(self):
		resources = getResourcePaths()
		if not resources:
			raise RuntimeError("no resources available")
		ve2.initialize(resources)

		self._instanceCache = {}

		try:
			# Audio device used since NVDA 2025.1
			outputDevice = config.conf["audio"]["outputDevice"]
		except KeyError:
			# Older NVDA versions
			outputDevice = config.conf["speech"]["outputDevice"]
		self._player = nvwave.WavePlayer(channels=1, samplesPerSec=22050, bitsPerSample=16, outputDevice=outputDevice)
		self._isSilence = threading.Event()
		self._veCallbackHandler = VECallback(self._player, self._isSilence, self._onIndexReached)
		self._veCallback = VE_CBOUTNOTIFY(self._veCallbackHandler)

		self._resources = getAvailableResources()
		self._voice = list(self.availableVoices.keys())[0]
		self._normalization = "OFF"
		self._rateBoost = False

	def _onVoiceTuning(self, instance, voiceName):
		# Ruleset
		rulesetPath = os.path.join(_tuningDataDir, f"{voiceName.lower()}.rules")
		if os.path.exists(rulesetPath):
			with open(rulesetPath, "rb") as f:
				content = f.read()
			log.debug(f"Loading ruleset from {rulesetPath}")
			try:
				ve2.resourceLoad(TEXT_RULESET_CONTENT_TYPE, content, instance)
			except VeError:
				log.warning(f"Error Loading vocalizer rules from {rulesetPath}", exc_info=True)
		# Load custom dictionary if one exists
		if voiceName not in _voiceDicts:
			dictPath = os.path.join(_tuningDataDir, f"{voiceName.lower()}.dcb")
			if os.path.exists(dictPath):
				with open(dictPath, "rb") as f:
					_voiceDicts[voiceName] = f.read()
					log.debug(f"Loading vocalizer dictionary from {dictPath}")
		if voiceName in _voiceDicts:
			try:
				ve2.resourceLoad(BIN_DICT_CONTENT_TYPE, _voiceDicts[voiceName], instance)
			except VeError:
				log.warning("Error loading Vocalizer dictionary.", exc_info=True)

	def getVoiceInstance(self, voiceName):
		try:
			return self._instanceCache[voiceName]
		except KeyError:
			pass
		instance, name = ve2.open(voiceName, self._veCallback)
		log.debug(f"Created synth instance for voice {name}")
		self._onVoiceTuning(instance, name)
		self._instanceCache[name] = instance
		return instance

	def terminate(self):
		self.cancel()
		try:
			for voiceName, instance in self._instanceCache.items():
				ve2.close(instance)
			self._instanceCache.clear()
			ve2.terminate()
		except RuntimeError:
			log.error("Vocalizer terminate", exc_info=True)
		self._player.close()
		self._veCallback = None

	def speak(self, speechSequence):
		currentInstance = defaultInstance = self.voiceInstance
		currentLanguage = defaultLanguage = self.language
		chunks = []
		hasText = False
		charMode = False

		for command in speechSequence:
			if isinstance(command, str):
				command = command.strip()
				if not command:
					continue
				# If character mode is on use lower case characters
				# Because the synth does not allow to turn off the caps reporting
				if charMode or len(command) == 1:
					command = command.lower()
				# unicode text normalization according to the specified form
				if self._normalization != "OFF":
					command = unicodedata.normalize(self._normalization, command)
				if hasText and not charMode:
					# Previous chunk is the usual text. We need to insert a speech separator
					chunks.append(getattr(speech, "CHUNK_SEPARATOR", "  "))
				# replace the excape character since it is used for parameter changing
				chunks.append(command.replace("\x1b", ""))
				hasText = True
			elif isinstance(command, IndexCommand):
				chunks.append(f"\x1b\\mrk={command.index}\\")
			elif isinstance(command, CharacterModeCommand):
				charMode = command.state
				s = "\x1b\\tn=spell\\" if command.state else "\x1b\\tn=normal\\"
				chunks.append(s)
			elif isinstance(command, LangChangeCommand):
				if command.lang == currentLanguage:
					# Keep on the same voice.
					continue
				if command.lang is None:
					# No language, use default.
					currentInstance = defaultInstance
					currentLanguage = defaultLanguage
					continue
				# Changed language, lets see what we have.
				currentLanguage = command.lang
				newVoiceName = self.getVoiceNameForLanguage(currentLanguage)
				if newVoiceName is None:
					# No voice for this language, use default.
					newInstance = defaultInstance
				else:
					newInstance = self.getVoiceInstance(newVoiceName)
				if newInstance == currentInstance:
					# Same voice, next command.
					continue
				if hasText: # We changed voice, send text we already have to vocalizer.
					self._speak(currentInstance, chunks)
					chunks = []
					hasText = False
				currentInstance = newInstance
			elif isinstance(command, PitchCommand):
				pitch = self.getParameter(currentInstance, VE_PARAM_PITCH)
				pitchOffset = self._percentToParam(command.offset, PITCH_MIN, PITCH_MAX) - PITCH_MIN
				chunks.append(f"\x1b\\pitch={pitch+pitchOffset}\\")
			elif isinstance(command, BreakCommand):
				# Supported range is 1-65535 msec
				breakTime = max(1, min(command.time, 65535))
				chunks.append(f"\x1b\\pause={breakTime}\\")
			# old method
			elif isinstance(command, RateCommand):
				boundedValue = max(0, min(command.newValue, 100))
				factor = 25.0 if boundedValue >= 50 else 50.0
				norm = 2.0 ** ((boundedValue - 50.0) / factor)
				value = int(round(norm * 100))
				chunks.append(f"\x1b\\rate={value}\\")
			elif isinstance(command, PitchCommand):
				boundedValue = max(0, min(command.newValue, 100))
				factor = 50.0
				norm = 2.0 ** ((boundedValue - 50.0) / factor)
				value = int(round(norm * 100))
				chunks.append(f"\x1b\\pitch={value}\\")
			elif isinstance(command, VolumeCommand):
				value = max(0, min(command.newValue, 100))
				chunks.append(f"\x1b\\vol={value}\\")
			elif isinstance(command, SpeechCommand):
				log.debugWarning(f"Unsupported speech command: {command}")
			else:
				log.error(f"Unknown speech: {command}")
		if chunks:
			self._speak(currentInstance, chunks)
		DoneSpeaking(self._player, self._onIndexReached)()

	def _speak(self, voiceInstance, chunks):
		text = "".join(chunks)
		self._isSilence.clear()
		ProcessText2Speech(voiceInstance, text)()

	def cancel(self):
		self._isSilence.set()
		self._player.stop()

	def pause(self, switch):
		self._player.pause(switch)

	def _onIndexReached(self, index):
		if index is not None:
			synthIndexReached.notify(synth=self, index=index)
		else:
			synthDoneSpeaking.notify(synth=self)

	def getParameter(self, instance, paramId, type_=int):
		return self.getParameters(instance, (paramId, type_))[0]

	def getParameters(self, instance, *idAndTypes):
		return ve2.getParamList(instance, *idAndTypes)

	def _get_voiceInstance(self):
		return self.getVoiceInstance(self.voice)

	def _get_volume(self):
		return self.getParameter(self.voiceInstance, VE_PARAM_VOLUME)

	def _set_volume(self, value):
		TtsSetParamList(self.voiceInstance, (VE_PARAM_VOLUME, int(value)))()

	def _get_rate(self):
		if self._rateBoost:
			rate = self._rate = self._veCallbackHandler.getSpeed()
			return self._paramToPercentFloat(rate, 0.5, 6.0)
		else:
			rate = self._rate = self.getParameter(self.voiceInstance, VE_PARAM_SPEECHRATE)
			norm = rate / 100.0
			factor = 25 if norm >= 1 else 50

			return int(round(50 + factor * math.log(norm, 2)))

	def _set_rate(self, value):
		if self._rateBoost:
			self._rate = self._percentToParamFloat(value, 0.5, 6.0)
			TtsSetParamList(self.voiceInstance, (VE_PARAM_SPEECHRATE, 100))()
			self._veCallbackHandler.setSpeed(self._rate)
		else:
			factor = 25.0 if value >= 50 else 50.0
			norm = 2.0 ** ((value - 50.0) / factor)
			self._rate = rate = int(round(norm * 100))
			TtsSetParamList(self.voiceInstance, (VE_PARAM_SPEECHRATE, rate))()
			self._veCallbackHandler.setSpeed(1.0)

	def _get_rateBoost(self):
		return self._rateBoost

	def _set_rateBoost(self, value):
		rate = self.rate
		self._rateBoost = value
		self.rate = rate

	def _get_pitch(self):
		pitch = self.getParameter(self.voiceInstance, VE_PARAM_PITCH)
		norm = pitch / 100.0
		factor = 50
		return int(round(50 + factor * math.log(norm, 2)))

	def _set_pitch(self, value):
		factor = 50.0
		norm = 2.0 ** ((value - 50.0) / factor)
		pitch = int(round(norm * 100))

		TtsSetParamList(self.voiceInstance, (VE_PARAM_PITCH, pitch))()

	def _getAvailableVoices(self):
		voices = []
		for items in self._resources.values():
			voices.extend(items)
		return OrderedDict([(v.id, v) for v in voices])

	def _get_voice(self):
		return self._voice

	def _set_voice(self, voice):
		if voice == self.voice: return
		if voice not in self.availableVoices:
			raise RuntimeError("Unavailable voice: %s" % voice)
		self._voice = voice
		# Available variants are cached by default. As variants maybe different for each voice remove the cached value
		if hasattr(self, "_availableVariants"):
			del self._availableVariants

	def _get_variant(self):
		return self.getParameter(self.voiceInstance, VE_PARAM_VOICE_OPERATING_POINT, type_=str)

	def _set_variant(self, variant):
		if variant == self.variant: return
		if variant not in self.availableVariants:
			log.warning("Unavailable variant: %s" % variant)
			return
		TtsSetParamList(self.voiceInstance, (VE_PARAM_VOICE_OPERATING_POINT, variant))()

	def _getAvailableVariants(self):
		language = self.getParameter(self.voiceInstance, VE_PARAM_LANGUAGE, type_=str) # FIXME: store language...
		dbs = ve2.getSpeechDBList(language, self.voice)
		return OrderedDict([(d, VoiceInfo(d, d)) for d in dbs])

	def _get_waitfactor(self):
		return str(self.getParameter(self.voiceInstance, VE_PARAM_WAITFACTOR))

	def _set_waitfactor(self, value):
		TtsSetParamList(self.voiceInstance, (VE_PARAM_WAITFACTOR, int(value)))()

	def _get_availableWaitfactors(self):
		return OrderedDict([(v, VoiceInfo(v, v)) for v in [str(v) for v in range(WAITFACTOR_MIN, WAITFACTOR_MAX+1)]])

	def _get_language(self):
		return self.availableVoices[self.voice].language

	def _get_availableNormalizations(self):
		values = OrderedDict([("OFF", StringParameterInfo("OFF", _("OFF")))])
		for form in ("NFC", "NFKC", "NFD", "NFKD"):
			values[form] = StringParameterInfo(form, form)
		return values

	def _get_normalization(self):
		return self._normalization

	def _set_normalization(self, value):
		if value in self.availableNormalizations:
			self._normalization = value

	@classmethod
	def _paramToPercentFloat(self, param: float, minVal: float, maxVal: float) -> int:
		if maxVal == minVal:
			return 0
		percent = (param - minVal) / (maxVal - minVal) * 100
		percent = round(max(0.0, min(100.0, percent)))
		return int(percent)

	@classmethod
	def _percentToParamFloat(self, percent: int, minVal: float, maxVal: float) -> float:
		return float(percent) / 100 * (maxVal - minVal) + minVal
