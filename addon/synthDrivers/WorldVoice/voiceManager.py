from collections import OrderedDict, defaultdict
import math
import os
import threading

from autoSettingsUtils.utils import paramToPercent, percentToParam
import comtypes.client
from comtypes import COMError
import config
import globalVars
import languageHandler
import locale
from logHandler import log
from synthDriverHandler import VoiceInfo, synthIndexReached, synthDoneSpeaking

try:
	from synthDriverHandler import getSynth
except BaseException:
	from speech import getSynth

from . import _languages
from .taskManager import TaskManager
from . import _vocalizer
from . import _sapi5
from ._sapi5 import SPAudioState, SpeechVoiceSpeakFlags, SapiSink, SpeechVoiceEvents
from . import _aisound

VOICE_PARAMETERS = [
	("rate", int, 50),
	("pitch", int, 50),
	("volume", int, 50),
	("variant", str, ""),
	# ("waitfactor", int, 0),
]

taskManager = None


def joinObjectArray(srcArr1, srcArr2, key):
	mergeArr = []
	for srcObj2 in srcArr2:
		def exist(existObj):
			mergeObj = {}
			if len(existObj) > 0:
				mergeObj = {**existObj[0], **srcObj2}
				mergeArr.append(mergeObj)
		exist(
			list(filter(lambda srcObj1: srcObj1[key] == srcObj2[key], srcArr1))
		)

	return mergeArr


def groupByField(arrSrc, field, applyKey, applyValue):
	temp = {}
	for item in arrSrc:
		key = applyKey(item[field])
		temp[key] = temp[key] if key in temp else []
		temp[key].append(applyValue(item))

	return temp


class Voice(object):
	speaking = threading.Lock()

	def __init__(self):
		self.rate = 50
		self.pitch = 50
		self.volume = 50

		self.variant = ""
		self.waitfactor = 0

		self.commitRate = 50
		self.commitPitch = 50
		self.commitVolume = 50

		self.loadParameter()

	@property
	def rate(self):
		raise NotImplementedError

	@rate.setter
	def rate(self, percent):
		raise NotImplementedError

	@property
	def pitch(self):
		raise NotImplementedError

	@pitch.setter
	def pitch(self, percent):
		raise NotImplementedError

	@property
	def volume(self):
		raise NotImplementedError

	@volume.setter
	def volume(self, percent):
		raise NotImplementedError

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

	@property
	def waitfactor(self):
		return self._waitfactor

	@waitfactor.setter
	def waitfactor(self, value):
		self._waitfactor = value

	def speak(self, text):
		raise NotImplementedError

	def break_(self, time):
		raise NotImplementedError

	def index(self, index):
		raise NotImplementedError

	def stop(self):
		raise NotImplementedError

	def pause(self):
		raise NotImplementedError

	def resume(self):
		raise NotImplementedError

	def close(self):
		raise NotImplementedError

	@classmethod
	def install(cls):
		raise NotImplementedError

	@classmethod
	def ready(cls):
		raise NotImplementedError

	@classmethod
	def engineOn(cls, lock=None, taskManager=None):
		raise NotImplementedError

	@classmethod
	def engineOff(cls):
		raise NotImplementedError

	@classmethod
	def voices(cls):
		raise NotImplementedError

	def loadParameter(self):
		voiceName = self.name
		if voiceName in config.conf["WorldVoice"]["voices"]:
			for p, t, _ in VOICE_PARAMETERS:
				if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]:
					try:
						value = config.conf["speech"][getSynth().name].get(p, None)
					except BaseException:
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
	workspace = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace", "VE")

	def __init__(self, name, language=None):
		self.engine = "VE"
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

		super().__init__()

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
		self._variants = _vocalizer.getSpeechDBList(language, self.name)
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

	@property
	def waitfactor(self):
		self._waitfactor = _vocalizer.getParameter(self.tts, _vocalizer.VE_PARAM_WAITFACTOR, type_=int)
		return self._waitfactor

	@waitfactor.setter
	def waitfactor(self, value):
		self._waitfactor = value
		_vocalizer.setParameter(self.tts, _vocalizer.VE_PARAM_WAITFACTOR, value)

	def speak(self, text):
		def _speak():
			_vocalizer.processText2Speech(self.tts, text)
		taskManager.add_dispatch_task((self, _speak),)

	def breaks(self, time):
		maxTime = 6553 if self.variant == "bet2" else 65535
		breakTime = max(1, min(time, maxTime))

		def _breaks():
			_vocalizer.processBreak(self.tts, breakTime)
		taskManager.add_dispatch_task((self, _breaks),)

	def stop(self):
		_vocalizer.stop()

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
	def engineOn(cls, lock=None, taskManager=None):
		def _onIndexReached(index):
			if index is not None:
				synthIndexReached.notify(synth=getSynth(), index=index)
			else:
				synthDoneSpeaking.notify(synth=getSynth())

		try:
			_vocalizer.initialize(_onIndexReached)
		except _vocalizer.VeError as e:
			if e.code == _vocalizer.VAUTONVDA_ERROR_INVALID:
				log.info("Vocalizer license for NVDA is Invalid")
			elif e.code == _vocalizer.VAUTONVDA_ERROR_DEMO_EXPIRED:
				log.info("Vocalizer demo license for NVDA as expired.")
			raise

		if lock:
			_vocalizer.voiceLock = lock

		if taskManager:
			taskManager.add_listen_queue("VE", _vocalizer.bgQueue)

	@classmethod
	def engineOff(cls):
		_vocalizer.terminate()

		global taskManager
		try:
			taskManager.remove_listen_queue("VE")
		except KeyError:
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
				langDescription = languageHandler.getLanguageDescription(localeName)
				if not langDescription:
					langDescription = voice.szLanguage.decode()
				name = voice.szVoiceName.decode()
				result.append({
					"name": name,
					"locale": localeName,
					"language": localeName,
					"langDescription": langDescription,
					"description": "%s - %s" % (name, langDescription),
					"engine": "VE",
				})

		return result


class Sapi5Voice(Voice):
	def __init__(self, name, language=None):
		self.engine = "SAPI5"
		self.tts, self.ttsAudioStream = _sapi5.open(name) if name != "default" else _sapi5.open()
		self.tts.EventInterests = SpeechVoiceEvents.Bookmark | SpeechVoiceEvents.StartInputStream | SpeechVoiceEvents.EndInputStream
		self._eventsConnection = comtypes.client.GetEvents(self.tts, SapiSink())
		self.name = self.tts.voice.getattribute('name')
		if not language:
			try:
				language = locale.windows_locale[int(self.tts.voice.getattribute('language').split(';')[0], 16)]
			except KeyError:
				language = None
		self.language = language

		super().__init__()

	@property
	def rate(self):
		self._rate = self.tts.Rate
		return (self._rate * 5) + 50

	@rate.setter
	def rate(self, percent):
		self._rate = (percent - 50) // 5
		self.tts.Rate = self._rate

	@property
	def pitch(self):
		return (self._pitch + 25) * 2

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

	@property
	def waitfactor(self):
		return self._waitfactor

	@waitfactor.setter
	def waitfactor(self, value):
		self._waitfactor = value

	def speak(self, text):
		def _speak():
			_sapi5.sapi5Queue.put((self, text),)
		taskManager.add_dispatch_task((self, _speak),)

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
		except BaseException:
			pass

	def resume(self):
		try:
			# SAPI5's default means of pausing in most cases is either extremely slow
			# (e.g. takes more than half a second) or does not work at all.
			# Therefore instruct the underlying audio interface to pause instead.
			if self.ttsAudioStream:
				self.ttsAudioStream.setState(SPAudioState.RUN, 0)
		except BaseException:
			pass

	def close(self):
		self._eventsConnection = None
		self.tts = None
		self.ttsAudioStream = None

	@classmethod
	def install(cls):
		return True

	@classmethod
	def ready(cls):
		return True

	@classmethod
	def engineOn(cls, lock=None, taskManager=None):
		try:
			_sapi5.initialize(getSynth)
		except BaseException:
			raise

		if lock:
			_sapi5.voiceLock = lock

		if taskManager:
			taskManager.add_listen_queue("SAPI5", _sapi5.sapi5Queue)

	@classmethod
	def engineOff(cls):
		_sapi5.terminate()

		global taskManager
		try:
			taskManager.remove_listen_queue("SAPI5")
		except KeyError:
			pass

	@classmethod
	def voices(cls):
		result = []
		if not cls.ready():
			return result

		tts = comtypes.client.CreateObject("SAPI.SPVoice")
		for voice in tts.getVoices():
			try:
				name = voice.getattribute('name')
				description = voice.GetDescription()
				try:
					language = locale.windows_locale[int(voice.getattribute('language').split(';')[0], 16)]
				except KeyError:
					language = "unknown"

				langDescription = languageHandler.getLanguageDescription(language)
				if not langDescription:
					try:
						langDescription = description.split("-")[1]
					except IndexError:
						langDescription = language

				result.append({
					"name": name,
					"locale": language,
					"language": language,
					"langDescription": langDescription,
					"description": "%s - %s" % (name, langDescription),
					"engine": "SAPI5",
				})
			except COMError:
				log.warning("Could not get the voice info. Skipping...")

		return result


class AisoundVoice(Voice):
	workspace = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace", "aisound")

	def __init__(self, name, language=None):
		self.engine = "aisound"
		self.aisound = _aisound.Aisound()
		self.name = name
		self.language = language if language else "unknown"

		super().__init__()

	def rollback(self):
		super().rollback()
		self.active()

	@property
	def inflection(self):
		return paramToPercent(self._inflection, 0, 2)

	@inflection.setter
	def inflection(self, value):
		param = self._inflection = percentToParam(value, 0, 2)
		self.aisound.Configure("style", "%d" % param)

	def active(self):
		if _aisound.lastSpeakInstance == self.aisound:
			return
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
		self.aisound.Configure("voice", param)

	@property
	def rate(self):
		return paramToPercent(self._rate, -32768, 32767)

	@rate.setter
	def rate(self, percent):
		param = self._rate = percentToParam(percent, -32768, 32767)
		self.aisound.Configure("speed", "%d" % param)

	@property
	def pitch(self):
		return paramToPercent(self._pitch, -32768, 32767)

	@pitch.setter
	def pitch(self, percent):
		param = self._pitch = percentToParam(percent, -32768, 32767)
		self.aisound.Configure("pitch", "%d" % param)

	@property
	def volume(self):
		return paramToPercent(self._volume, -32768, 32767)

	@volume.setter
	def volume(self, percent):
		param = self._volume = percentToParam(percent, -32768, 32767)
		self.aisound.Configure("volume", "%d" % param)

	def speak(self, text):
		def _speak():
			_aisound.aisoundQueue.put((self, text, "speak"),)
		taskManager.add_dispatch_task((self, _speak),)

	def stop(self):
		self.aisound.Cancel()

	def pause(self):
		self.aisound.Pause()

	def resume(self):
		self.aisound.Resume()

	def index(self, index):
		def _speak():
			_aisound.aisoundQueue.put((self, index, "speak_index"),)
		taskManager.add_dispatch_task((self, _speak),)

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
	def engineOn(cls, lock=None, taskManager=None):
		try:
			_aisound.initialize(getSynth)
		except BaseException:
			raise

		if lock:
			_aisound.voiceLock = lock

		if taskManager:
			taskManager.add_listen_queue("aisound", _aisound.aisoundQueue)

	@classmethod
	def engineOff(cls):
		_aisound.terminate()

		global taskManager
		try:
			taskManager.remove_listen_queue("aisound")
		except KeyError:
			pass

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
				"name": name,
				"locale": language,
				"language": language,
				"langDescription": langDescription,
				"description": "%s - %s" % (name, langDescription),
				"engine": "aisound",
			})

		return result


class VoiceManager(object):
	voice_class = {
		"VE": VEVoice,
		"SAPI5": Sapi5Voice,
		"aisound": AisoundVoice,
	}

	@classmethod
	def ready(cls):
		result = False
		for item in cls.voice_class.values():
			result |= item.ready()
		return result

	def __init__(self):
		global taskManager
		lock = threading.Lock()
		for item in self.voice_class.values():
			if item.ready():
				item.engineOn(lock, taskManager)

		table = []
		for item in self.voice_class.values():
			table.extend(item.voices())

		taskManager = TaskManager(lock=lock, table=table)
		self.taskManager = taskManager

		self._setVoiceDatas()
		self.engine = 'ALL'

		self._instanceCache = {}
		self.waitfactor = 0

		self._defaultVoiceInstance = self.getVoiceInstance(self.table[0]["name"])
		self._defaultVoiceInstance.loadParameter()
		log.debug("Created voiceManager instance. Default voice is %s", self._defaultVoiceInstance.name)

	def terminate(self):
		for voiceName, instance in self._instanceCache.items():
			instance.commit()
			instance.close()

		for item in self.voice_class.values():
			try:
				item.engineOff()
			except BaseException:
				pass

		global taskManager
		taskManager = None

	@property
	def defaultVoiceInstance(self):
		return self._defaultVoiceInstance

	@property
	def defaultVoiceName(self):
		return self._defaultVoiceInstance.name

	@defaultVoiceName.setter
	def defaultVoiceName(self, name):
		if name not in self._voiceInfos:
			log.debugWarning("Voice not available, using default voice.")
			return
		self._defaultVoiceInstance = self.getVoiceInstance(name)

	@property
	def waitfactor(self):
		return self._waitfactor

	@waitfactor.setter
	def waitfactor(self, value):
		self._waitfactor = value
		for voiceName, instance in self._instanceCache.items():
			instance.waitfactor = value
			instance.commit()

	def getVoiceInstance(self, voiceName):
		try:
			instance = self._instanceCache[voiceName]
		except KeyError:
			instance = self._createVoiceInstance(voiceName)
		return instance

	def _createVoiceInstance(self, voiceName):
		item = list(filter(lambda item: item["name"] == voiceName, self.table))[0]
		voiceInstance = self.voice_class[item["engine"]](name=item["name"], language=item["language"])
		voiceInstance.loadParameter()
		voiceInstance.waitfactor = self.waitfactor

		self._instanceCache[voiceInstance.name] = voiceInstance
		return self._instanceCache[voiceInstance.name]

	def onVoiceParameterConsistent(self, baseInstance):
		for voiceName, instance in self._instanceCache.items():
			instance.rate = baseInstance.rate
			instance.pitch = baseInstance.pitch
			instance.volume = baseInstance.volume
			instance.commit()

	def onKeepEngineConsistent(self):
		temp = defaultdict(lambda: {})
		for key, value in config.conf["WorldVoice"]["autoLanguageSwitching"].items():
			if isinstance(value, config.AggregatedSection):
				try:
					temp[key]['voice'] = config.conf["WorldVoice"]["autoLanguageSwitching"][key]["voice"]
				except KeyError:
					pass
			else:
				temp[key] = config.conf["WorldVoice"]["autoLanguageSwitching"][key]

		for localelo, data in config.conf["WorldVoice"]['autoLanguageSwitching'].items():
			if isinstance(data, config.AggregatedSection):
				if (localelo not in self.localeToVoicesMapEngineFilter) or ('voice' in data and data['voice'] not in self.localeToVoicesMapEngineFilter[localelo]):
					try:
						del temp[localelo]
					except BaseException:
						pass
					try:
						log.info("locale {locale} voice {voice} not available on {engine} engine".format(
							locale=localelo,
							voice=data['voice'],
							engine=self.engine,
						))
					except BaseException:
						pass

		config.conf["WorldVoice"]["autoLanguageSwitching"] = temp
		taskManager.reset_block()

	def reload(self):
		for voiceName, instance in self._instanceCache.items():
			instance.loadParameter()

	def cancel(self):
		taskManager.cancel()
		self._defaultVoiceInstance.stop()
		if self.taskManager and not self.taskManager.block:
			for voiceName, instance in self._instanceCache.items():
				instance.stop()

	def _setVoiceDatas(self):
		self.table = []
		for item in self.voice_class.values():
			self.table.extend(item.voices())
		self.table = sorted(self.table, key=lambda item: (item['engine'], item['language'], item['name']))

		self._localesToVoices = {
			**groupByField(self.table, 'locale', lambda i: i, lambda i: i['name']),
			# For locales with no country (i.g. "en") use all voices from all sub-locales
			**groupByField(self.table, 'locale', lambda i: i.split('_')[0], lambda i: i['name']),
		}

		self._voicesToEngines = {}
		for item in self.table:
			self._voicesToEngines[item["name"]] = item["engine"]

		voiceInfos = []
		for item in self.table:
			voiceInfos.append(VoiceInfo(item["name"], item["description"], item["language"]))

		# Kepp a list with existing voices in VoiceInfo objects.
		self._voiceInfos = OrderedDict([(v.id, v) for v in voiceInfos])

	def _setVoiceDatasEngineFilter(self):
		self.tableEngineFilter = []
		for item in self.voice_class.values():
			self.tableEngineFilter.extend(item.voices())
		self.tableEngineFilter = sorted(self.tableEngineFilter, key=lambda item: (item['engine'], item['language'], item['name']))
		self.tableEngineFilter = list(filter(lambda item: self.engine == 'ALL' or item['engine'] == self.engine, self.tableEngineFilter))

		self._localesToVoicesEngineFilter = {
			**groupByField(self.tableEngineFilter, 'locale', lambda i: i, lambda i: i['name']),
			# For locales with no country (i.g. "en") use all voices from all sub-locales
			**groupByField(self.tableEngineFilter, 'locale', lambda i: i.split('_')[0], lambda i: i['name']),
		}

		self._voicesToEnginesEngineFilter = {}
		for item in self.tableEngineFilter:
			self._voicesToEnginesEngineFilter[item["name"]] = item["engine"]

		voiceInfos = []
		for item in self.tableEngineFilter:
			voiceInfos.append(VoiceInfo(item["name"], item["description"], item["language"]))

		# Kepp a list with existing voices in VoiceInfo objects.
		self._voiceInfosEngineFilter = OrderedDict([(v.id, v) for v in voiceInfos])

	@property
	def engine(self):
		return self._engine

	@engine.setter
	def engine(self, value):
		if value not in ["ALL"] + list(self.voice_class.keys()):
			raise ValueError("engine setted is not valid")
		self._engine = value
		self._setVoiceDatasEngineFilter()

	@property
	def voiceInfos(self):
		return self._voiceInfos

	@property
	def languages(self):
		return sorted([l for l in self._localesToVoices if len(self._localesToVoices[l]) > 0])

	@property
	def localeToVoicesMap(self):
		return self._localesToVoices.copy()

	@property
	def localesToNamesMap(self):
		return {locale: self._getLocaleReadableName(locale) for locale in self._localesToVoices}

	@property
	def languagesEngineFilter(self):
		return sorted([l for l in self._localesToVoicesEngineFilter if len(self._localesToVoicesEngineFilter[l]) > 0])

	@property
	def localeToVoicesMapEngineFilter(self):
		return self._localesToVoicesEngineFilter.copy()

	@property
	def localesToNamesMapEngineFilter(self):
		return {locale: self._getLocaleReadableName(locale) for locale in self._localesToVoicesEngineFilter}

	def getVoiceNameForLanguage(self, language):
		configured = self._getConfiguredVoiceNameForLanguage(language)
		if configured is not None and configured in self.voiceInfos:
			return configured
		voices = self._localesToVoicesEngineFilter.get(language, None)
		if voices is None:
			if '_' in language:
				voices = self._localesToVoicesEngineFilter.get(language.split('_')[0], None)
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
			try:
				voice = config.conf["WorldVoice"]['autoLanguageSwitching'][language]['voice']
				return voice
			except BaseException:
				pass
		return None

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s - %s" % (description, locale) if description else locale
