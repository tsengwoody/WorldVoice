from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from operator import attrgetter
from typing import Callable, TypeVar, Dict, List
import re

import config
import languageHandler
from logHandler import log
from synthDriverHandler import VoiceInfo

from .engine import EngineType, READY_ENGINE_CLASS, get_engine_enabled, refresh_ready_engine_classes

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


def getPrimaryLocale(locale: str) -> str:
	"""Return the primary language subtag from locale strings like en_US / en-US."""
	if not locale:
		return locale
	return re.split(r"[-_]", locale, maxsplit=1)[0]


def groupVoicesByPrimaryLocale(table: list["VoiceMeta"]) -> dict[str, list[str]]:
	return groupByField(table, "locale", getPrimaryLocale, lambda i: i.name)


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

	def __init__(self, taskManager):
		self.keepMainLocaleEngineConsistent = config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"]
		self.taskManager = taskManager
		refresh_ready_engine_classes(config.conf["WorldVoice"]["engine"])

		enabled = [
			eng for eng in EngineType
			if get_engine_enabled(eng.name, config.conf["WorldVoice"]["engine"])
		]

		self.installEngine = []
		for eng in enabled:
			try:
				cls = READY_ENGINE_CLASS[eng.name]
			except KeyError:
				continue
			try:
				cls.engineOn()
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
		for voiceName, instance in list(self._instanceCache.items()):
			try:
				instance.commit()
			except Exception:
				log.error("voice %s commit error", voiceName, exc_info=True)
			try:
				instance.close()
			except Exception:
				log.error("voice %s close error", voiceName, exc_info=True)

		for item in READY_ENGINE_CLASS.values():
			try:
				item.engineOff()
			except Exception:
				log.error("engine %s off error", getattr(item, "engine", item), exc_info=True)

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

	def _setInstanceWaitfactor(self, voiceName, instance, value):
		if not hasattr(type(instance), "waitfactor"):
			return
		try:
			instance.waitfactor = value
		except Exception:
			log.debugWarning(f"Unable to set waitfactor for voice {voiceName}", exc_info=True)

	@waitfactor.setter
	def waitfactor(self, value):
		self._waitfactor = value
		for voiceName, instance in self._instanceCache.items():
			self._setInstanceWaitfactor(voiceName, instance, value)

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
		cls = READY_ENGINE_CLASS[voiceMeta.engine]
		voiceInstance = cls(
			id=voiceMeta.id,
			name=voiceMeta.name,
			language=voiceMeta.language,
			taskManager=self.taskManager
		)
		voiceInstance.loadParameter()
		self._setInstanceWaitfactor(voiceInstance.name, voiceInstance, self.waitfactor)

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
		_localesToVoices = groupVoicesByPrimaryLocale(table)
		return sorted([l for l in _localesToVoices if len(_localesToVoices[l]) > 0])

	@property
	def languages(self):
		if self.keepMainLocaleEngineConsistent:
			table = [v for v in self.table if v.engine == self._defaultVoiceInstance.engine]
		else:
			table = [v for v in self.table]
		_localesToVoices = groupVoicesByPrimaryLocale(table)
		return sorted([l for l in _localesToVoices if len(_localesToVoices[l]) > 0])

	@property
	def localeToVoicesMap(self):
		if self.keepMainLocaleEngineConsistent:
			table = [v for v in self.table if v.engine == self._defaultVoiceInstance.engine]
		else:
			table = [v for v in self.table]
		return groupVoicesByPrimaryLocale(table)

	@property
	def localesToNamesMap(self):
		if self.keepMainLocaleEngineConsistent:
			table = [v for v in self.table if v.engine == self._defaultVoiceInstance.engine]
		else:
			table = [v for v in self.table]
		_localesToVoices = groupVoicesByPrimaryLocale(table)
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
			if '_' not in language and '-' not in language:
				return voice
			language = getPrimaryLocale(language)
			if language in config.conf["WorldVoice"]["role"]:
				try:
					voice = config.conf["WorldVoice"]["role"][language]['voice']
				except KeyError:
					pass
		return voice

	def _getLocaleReadableName(self, locale_):
		description = languageHandler.getLanguageDescription(locale_)
		return "%s - %s" % (description, locale_) if description else locale_
