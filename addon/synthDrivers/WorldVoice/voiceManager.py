from collections import OrderedDict, defaultdict
from dataclasses import dataclass
import importlib
from operator import attrgetter
import threading
from typing import Callable, TypeVar, Dict, List

import config
import languageHandler
from logHandler import log
from synthDriverHandler import VoiceInfo

from .taskManager import TaskManager
from .engine import EngineType

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


def groupByField(
		arrSrc: List[T],
		field: str,
		applyKey: Callable[[str], K],
		applyValue: Callable[[T], V]
) -> Dict[K, List[V]]:
	groups: Dict[K, List[V]] = defaultdict(list)
	for item in arrSrc:
		val = getattr(item, field)
		key = applyKey(val)
		groups[key].append(applyValue(item))
	return groups


@dataclass(frozen=True)
class VoiceMeta:
	id: str
	name: str
	description: str
	language: str
	engine: str
	locale: str


class VoiceManager(object):
	@classmethod
	def ready(cls):
		return True

	def __init__(self):
		self.keepMainLocaleEngineConsistent = config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"]
		self.lock = threading.Lock()
		self.taskManager = TaskManager(lock=self.lock)

		enabled = [
			eng for eng in EngineType
			if config.conf["WorldVoice"]["engine"].get(eng.name, False)
		]

		self.voice_classes: Dict[str, type] = self._load_voice_classes(enabled)

		self.installEngine = []
		for eng in enabled:
			cls = self.voice_classes[eng.name]
			try:
				if cls.ready():
					cls.engineOn(self.lock)
					self.installEngine.append(cls)
			except Exception as e:
				log.error("engine %s on error: %s", eng.name, e)

		self._setVoiceDatas()
		self._instanceCache = {}
		self.waitfactor = 0

		default_meta: VoiceMeta = self._getDefaultVoiceMeta()
		self._defaultVoiceInstance = self.getVoiceInstance(default_meta.name)
		self._defaultVoiceInstance.loadParameter()
		log.debug("Created voiceManager instance. Default voice is %s", default_meta.name)

	def terminate(self):
		for voiceName, instance in self._instanceCache.items():
			instance.commit()
			instance.close()

		for item in self.voice_classes.values():
			item.engineOff()

		self.taskManager = None

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
		self.onKeepEngineConsistent()
		self.onKeepMainLocaleVoiceConsistent()

	@property
	def waitfactor(self):
		return self._waitfactor

	@waitfactor.setter
	def waitfactor(self, value):
		self._waitfactor = value
		for voiceName, instance in self._instanceCache.items():
			try:
				if isinstance(instance, self.voice_classes["VE"]):
					instance.waitfactor = value
			except KeyError:
				pass

	def _load_voice_classes(self, engines: List[EngineType]) -> Dict[str, type]:
		"""
		Dynamically import voice classes based on EngineType definitions.
		Returns a dict mapping engine-name (e.g. "VE") to the class object.
		"""
		classes: Dict[str, type] = {}
		for eng in engines:
			module_path = eng.module_path	  # e.g. "voice.VEVoice"
			class_name = eng.class_name	   # e.g. "VEVoice"
			module = importlib.import_module(module_path)
			cls = getattr(module, class_name)
			classes[eng.name] = cls
		return classes

	def _getDefaultVoiceMeta(self) -> VoiceMeta:
		lang = languageHandler.getLanguage()
		try:
			return next(v for v in self.table if v.language == lang)
		except StopIteration:
			return self.table[0]

	def getVoiceInstance(self, voiceName):
		try:
			instance = self._instanceCache[voiceName]
		except KeyError:
			instance = self._createVoiceInstance(voiceName)
		return instance

	def _createVoiceInstance(self, voiceName: str):
		voiceMeta = next(v for v in self.table if v.name == voiceName)
		cls = self.voice_classes[voiceMeta.engine]
		voiceInstance = cls(
			id=voiceMeta.id,
			name=voiceMeta.name,
			language=voiceMeta.language,
			taskManager=self.taskManager
		)
		voiceInstance.loadParameter()
		voiceInstance.waitfactor = self.waitfactor

		self._instanceCache[voiceInstance.name] = voiceInstance
		return voiceInstance

	def onVoiceParameterConsistent(self, baseInstance):
		for voiceName, instance in self._instanceCache.items():
			instance.rate = baseInstance.rate
			instance.pitch = baseInstance.pitch
			instance.volume = baseInstance.volume
			instance.inflection = baseInstance.inflection
			instance.rateBoost = baseInstance.rateBoost
			instance.commit()

	def onKeepEngineConsistent(self):
		temp = defaultdict(lambda: {})
		for key, value in config.conf["WorldVoice"]["role"].items():
			if isinstance(value, config.AggregatedSection):
				try:
					temp[key]['voice'] = config.conf["WorldVoice"]["role"][key]["voice"]
				except KeyError:
					pass
			else:
				temp[key] = config.conf["WorldVoice"]["role"][key]

		for localelo, data in config.conf["WorldVoice"]["role"].items():
			if isinstance(data, config.AggregatedSection):
				if (localelo not in self.localeToVoicesMap) or ('voice' in data and data['voice'] not in self.localeToVoicesMap[localelo]):
					try:
						del temp[localelo]
					except KeyError:
						pass
					# log.info(f"locale {localelo} voice {data['voice']} not available")

		config.conf["WorldVoice"]["role"] = temp

	def onKeepMainLocaleVoiceConsistent(self):
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"]:
			locale = self.defaultVoiceInstance.language if self.defaultVoiceInstance.language else languageHandler.getLanguage()
			if locale not in config.conf["WorldVoice"]["role"]:
				config.conf["WorldVoice"]["role"][locale] = {}
			config.conf["WorldVoice"]["role"][locale]['voice'] = self.defaultVoiceInstance.name
			locale = locale.split("_")[0]
			if locale not in config.conf["WorldVoice"]["role"]:
				config.conf["WorldVoice"]["role"][locale] = {}
			config.conf["WorldVoice"]["role"][locale]['voice'] = self.defaultVoiceInstance.name

	def reload(self):
		for voiceName, instance in self._instanceCache.items():
			instance.loadParameter()

	def cancel(self):
		self._defaultVoiceInstance.stop()
		if self.taskManager:
			self.taskManager.cancel()
			for voiceName, instance in self._instanceCache.items():
				instance.stop()

	def _setVoiceDatas(self):
		self.table: List[VoiceMeta] = []
		for cls in self.installEngine:
			for v in cls.voices():
				try:
					self.table.append(VoiceMeta(
						id=v["id"],
						name=v["name"],
						description=v.get("description", ""),
						language=v["language"],
						engine=v["engine"],
						locale=v.get("locale", v["language"]),
					))
				except KeyError as e:
					log.error("Invalid voice data: missing %s", e)

		self.table.sort(key=attrgetter("engine", "language", "name"))

		voiceInfos = [VoiceInfo(v.name, v.description, v.language) for v in self.table]
		self._voiceInfos = OrderedDict((v.id, v) for v in voiceInfos)

	@property
	def voiceInfos(self):
		return self._voiceInfos

	@property
	def allLanguages(self):
		table = [v for v in self.table]
		_localesToVoices: dict[str, list[str]] = {
			**groupByField(table, 'locale', lambda i: i, lambda i: i.name),
			**groupByField(table, 'locale', lambda i: i.split('_')[0], lambda i: i.name),
		}
		return sorted([l for l in _localesToVoices if len(_localesToVoices[l]) > 0])

	@property
	def languages(self):
		if self.keepMainLocaleEngineConsistent:
			table = [v for v in self.table if v.engine == self._defaultVoiceInstance.engine]
		else:
			table = [v for v in self.table]
		_localesToVoices: dict[str, list[str]] = {
			**groupByField(table, 'locale', lambda i: i, lambda i: i.name),
			**groupByField(table, 'locale', lambda i: i.split('_')[0], lambda i: i.name),
		}
		return sorted([l for l in _localesToVoices if len(_localesToVoices[l]) > 0])

	@property
	def localeToVoicesMap(self):
		if self.keepMainLocaleEngineConsistent:
			table = [v for v in self.table if v.engine == self._defaultVoiceInstance.engine]
		else:
			table = [v for v in self.table]

		_localesToVoices: dict[str, list[str]] = {
			**groupByField(table, 'locale', lambda i: i, lambda i: i.name),
			**groupByField(table, 'locale', lambda i: i.split('_')[0], lambda i: i.name),
		}
		return _localesToVoices

	@property
	def localesToNamesMap(self):
		if self.keepMainLocaleEngineConsistent:
			table = [v for v in self.table if v.engine == self._defaultVoiceInstance.engine]
		else:
			table = [v for v in self.table]

		_localesToVoices: dict[str, list[str]] = {
			**groupByField(table, 'locale', lambda i: i, lambda i: i.name),
			**groupByField(table, 'locale', lambda i: i.split('_')[0], lambda i: i.name),
		}
		return {item: self._getLocaleReadableName(item) for item in _localesToVoices}

	def getVoiceNameForLanguage(self, language):
		configured = self._getConfiguredVoiceNameForLanguage(language)
		if configured is not None and configured in self.voiceInfos:
			return configured
		return self.defaultVoiceName

	def getVoiceInstanceForLanguage(self, language):
		voiceName = self.getVoiceNameForLanguage(language)
		if voiceName:
			return self.getVoiceInstance(voiceName)
		return None

	def _getConfiguredVoiceNameForLanguage(self, language):
		voice = None
		if language in config.conf["WorldVoice"]["role"]:
			try:
				voice = config.conf["WorldVoice"]["role"][language]['voice']
			except KeyError:
				pass
		if not voice:
			if '_' not in language:
				return voice
			language = language.split('_')[0]
			if language in config.conf["WorldVoice"]["role"]:
				try:
					voice = config.conf["WorldVoice"]["role"][language]['voice']
				except KeyError:
					pass
		return voice

	def _getLocaleReadableName(self, locale_):
		description = languageHandler.getLanguageDescription(locale_)
		return "%s - %s" % (description, locale_) if description else locale_
