from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from operator import attrgetter
from typing import Callable, TypeVar, Dict, List
import re
import time

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
		init_start = time.perf_counter()
		self.keepMainLocaleEngineConsistent = config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"]
		self.taskManager = taskManager

		step_start = time.perf_counter()
		refresh_ready_engine_classes(config.conf["WorldVoice"]["engine"])
		log.debug("WorldVoice init timing: VoiceManager refresh_ready_engine_classes %.3fs", time.perf_counter() - step_start)

		step_start = time.perf_counter()
		enabled = [
			eng for eng in EngineType
			if get_engine_enabled(eng.name, config.conf["WorldVoice"]["engine"])
		]
		log.debug(
			"WorldVoice init timing: VoiceManager enabled engine filter %.3fs (%s)",
			time.perf_counter() - step_start,
			", ".join(eng.name for eng in enabled),
		)

		step_start = time.perf_counter()
		self.installEngine = []
		for eng in enabled:
			try:
				cls = READY_ENGINE_CLASS[eng.name]
			except KeyError:
				log.debug("WorldVoice init timing: VoiceManager engine %s not ready", eng.name)
				continue
			try:
				engine_start = time.perf_counter()
				cls.engineOn()
				log.debug(
					"WorldVoice init timing: VoiceManager eager engineOn %s %.3fs",
					eng.name,
					time.perf_counter() - engine_start,
				)
				self.installEngine.append(cls)
			except Exception as e:
				log.error("engine %s on error: %s", eng.name, e)
		log.debug(
			"WorldVoice init timing: VoiceManager installEngine build %.3fs (%s)",
			time.perf_counter() - step_start,
			", ".join(cls.engine for cls in self.installEngine),
		)

		step_start = time.perf_counter()
		self._setVoiceDatas()
		log.debug("WorldVoice init timing: VoiceManager _setVoiceDatas total %.3fs", time.perf_counter() - step_start)
		if not self.table:
			raise RuntimeError("No WorldVoice voices are available from enabled speech engines.")
		self._instanceCache = {}
		self.waitfactor = 0

		step_start = time.perf_counter()
		default_meta: VoiceMeta = self._getDefaultVoiceMeta()
		log.debug(
			"WorldVoice init timing: VoiceManager default voice select %.3fs (%s/%s)",
			time.perf_counter() - step_start,
			default_meta.engine,
			default_meta.name,
		)

		step_start = time.perf_counter()
		self._defaultVoiceInstance = self.getVoiceInstance(default_meta.name)
		log.debug("WorldVoice init timing: VoiceManager default getVoiceInstance %.3fs", time.perf_counter() - step_start)

		step_start = time.perf_counter()
		self._defaultVoiceInstance.loadParameter()
		log.debug("WorldVoice init timing: VoiceManager default loadParameter %.3fs", time.perf_counter() - step_start)
		log.debug("Created voiceManager instance. Default voice is %s", default_meta.name)
		log.debug("WorldVoice init timing: VoiceManager total %.3fs", time.perf_counter() - init_start)

	def terminate(self):
		for voiceName, instance in self._instanceCache.items():
			instance.commit()
			instance.close()

		for item in READY_ENGINE_CLASS.values():
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
			if ("Cerence" in READY_ENGINE_CLASS and isinstance(instance, READY_ENGINE_CLASS["Cerence"])) or ("VE" in READY_ENGINE_CLASS and isinstance(instance, READY_ENGINE_CLASS["VE"])):
				instance.waitfactor = value

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
		step_start = time.perf_counter()
		voiceInstance = cls(
			id=voiceMeta.id,
			name=voiceMeta.name,
			language=voiceMeta.language,
			taskManager=self.taskManager
		)
		log.debug(
			"WorldVoice init timing: create voice instance %s/%s %.3fs",
			voiceMeta.engine,
			voiceMeta.name,
			time.perf_counter() - step_start,
		)
		step_start = time.perf_counter()
		voiceInstance.loadParameter()
		log.debug(
			"WorldVoice init timing: voice instance loadParameter %s/%s %.3fs",
			voiceMeta.engine,
			voiceMeta.name,
			time.perf_counter() - step_start,
		)
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
			step_start = time.perf_counter()
			voice_count = 0
			for v in cls.voices():
				voice_count += 1
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
			log.debug(
				"WorldVoice init timing: voices discovery %s %.3fs (%d voices)",
				cls.engine,
				time.perf_counter() - step_start,
				voice_count,
			)

		step_start = time.perf_counter()
		self.table.sort(key=attrgetter("engine", "language", "name"))
		log.debug(
			"WorldVoice init timing: voice table sort %.3fs (%d total voices)",
			time.perf_counter() - step_start,
			len(self.table),
		)

		step_start = time.perf_counter()
		voiceInfos = [VoiceInfo(v.name, v.description, v.language) for v in self.table]
		self._voiceInfos = OrderedDict((v.id, v) for v in voiceInfos)
		log.debug("WorldVoice init timing: voiceInfos build %.3fs", time.perf_counter() - step_start)

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
