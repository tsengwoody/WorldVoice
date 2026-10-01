from collections import OrderedDict, defaultdict
from collections.abc import Mapping
from dataclasses import replace
from operator import attrgetter
from typing import Callable, TypeVar, Dict, List
import re

import config
import languageHandler
from logHandler import log
from synthDriverHandler import VoiceInfo

from .compat.engineAdapter import LegacyEngineAdapter
from .compat.voiceFacade import LegacyVoiceBinding
from .runtime.models import VoiceSpec, EngineCapabilities, CompletionContract, CompletionMode
from .indexLedger import IndexLedger
from .runtime.session import EngineSession, PlaybackPort
from .runtime.scheduler import TaskManager
from .runtime.settings import VoiceEditSession, VoiceSettingsStore
from .nvdaEventBridge import NvdaEventBridge

from .engine import EngineType, READY_ENGINE_CLASS, get_engine_enabled, refresh_ready_engine_classes

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


def groupByField(
	arrSrc: List[T],
	field: str,
	applyKey: Callable[[str], K],
	applyValue: Callable[[T], V],
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
	return re.split(r"[-_]", locale, maxsplit=1)[0].lower()


def groupVoicesByPrimaryLocale(table: list["VoiceMeta"]) -> dict[str, list[str]]:
	return groupByField(table, "locale", getPrimaryLocale, lambda i: i.name)


def getVoiceKey(engine: str, voiceId: str) -> str:
	return "%s:%s" % (engine, voiceId)


VoiceMeta = VoiceSpec


class VoiceManager(object):
	@classmethod
	def ready(cls):
		return True

	def __init__(
		self,
		taskManager: TaskManager,
		settings: VoiceSettingsStore,
		bridge: NvdaEventBridge,
		*,
		index_ledger: IndexLedger,
		completion_for: Callable[[type, object], CompletionContract],
	):
		self.taskManager = taskManager
		self.settings = settings
		self._bridge = bridge
		self._index_ledger = index_ledger
		self._completion_for = completion_for
		self.installEngine = []
		self._resources = []
		self._sessions = {}
		self._specs = {}
		self._instanceCache = {}
		self._waitfactor = 0
		self._terminated = False
		try:
			self._initialize()
		except BaseException:
			self.terminate(commit=False)
			raise

	def _initialize(self):
		self.keepMainLocaleEngineConsistent = config.conf["WorldVoice"]["autoLanguageSwitching"][
			"KeepMainLocaleEngineConsistent"
		]
		refresh_ready_engine_classes(config.conf["WorldVoice"]["engine"])
		for eng in EngineType:
			if not get_engine_enabled(eng.name, config.conf["WorldVoice"]["engine"]):
				continue
			cls = READY_ENGINE_CLASS.get(eng.name)
			if cls is None:
				continue
			adapter = LegacyEngineAdapter(
				cls,
				self.getVoiceInstance,
				index_ledger=self._index_ledger,
				is_source_owned=lambda source: any(resource[0] is source for resource in self._resources),
			)
			try:
				adapter.open()
			except Exception:
				log.error("engine %s on error", eng.name, exc_info=True)
				continue
			# Retain identities (not equality) for the entire resource lifetime.
			owner = next(
				(resource for resource in self._resources if resource[0] is adapter.notification_source),
				None,
			)
			if owner is not None:
				session = owner[1]
				self._resources.append((adapter.notification_source, session, adapter, cls, False))
				completion = self._resource_completion(cls, adapter.notification_source)
				if completion != session.completion:
					raise ValueError("Aliases of one resource must share a completion contract")
				adapter.configure_completion(session.completion)
			else:
				session = EngineSession(adapter, self.settings)
				self._resources.append((adapter.notification_source, session, adapter, cls, True))
				session.open()
				completion = self._resource_completion(cls, adapter.notification_source)
				adapter.configure_completion(completion)
				# Claim ownership before binding, since bind may register then raise.
				self._bridge.bind(adapter.notification_source, session.source_id, completion=completion)
				if completion.mode in (CompletionMode.DRAIN, CompletionMode.END_INDEX_AND_DRAIN):
					adapter.configure_segment_events(
						lambda context, source=adapter.notification_source: self._bridge.segment_sink(
							source,
							context,
						),
					)
				elif completion.legacy_contextual:
					adapter.configure_legacy_segment_events(
						lambda context, source=adapter.notification_source: self._bridge.legacy_segment_sink(
							source,
							context,
						),
					)
			cls.session = session
			cls._runtime_binding = LegacyVoiceBinding(self.settings, session, self.getVoiceSpec)
			# Only bound, operational resources become visible to resolvers.
			self._sessions[eng.name] = session
			self.installEngine.append(cls)
			for spec in adapter.list_voices():
				self._specs[spec.name] = spec
		self._setVoiceDatas()
		if not self.table:
			raise RuntimeError("No WorldVoice voices are available from enabled speech engines.")
		self._defaultVoiceInstance = self.getVoiceInstance(self._getDefaultVoiceMeta().name)

	def _resource_completion(self, cls, source):
		completion = self._completion_for(cls, source)
		if completion.mode is CompletionMode.LEGACY_DONE and callable(
			getattr(source, "speak_legacy_segment", None),
		):
			completion = replace(completion, legacy_contextual=True)
		return completion

	def terminate(self, *, commit=True):
		if self._terminated:
			return
		self._terminated = True
		# Stop publication before releasing any resources.
		self._sessions.clear()
		if commit:
			for key in self.settings.keys():
				try:
					self.settings.commit(key)
				except Exception:
					log.error("Failed to save voice %s", key, exc_info=True)
		self._instanceCache.clear()
		for source, session, adapter, cls, owns in reversed(self._resources):
			if owns:
				try:
					self._bridge.unbind(session.source_id)
				except Exception:
					log.error("Failed to unbind engine %s", cls.engine, exc_info=True)
				try:
					session.close()
				except Exception:
					log.error("Failed to close engine %s", cls.engine, exc_info=True)
				finally:
					cls.session = None
					cls._runtime_binding = None
			else:
				try:
					adapter.detach_alias()
				except Exception:
					log.error("Failed to detach engine alias %s", cls.engine, exc_info=True)
		self._resources.clear()
		self.installEngine.clear()
		self.taskManager = None

	def resolve_playback(self, key: str) -> PlaybackPort | None:
		spec = self._specs.get(key)
		if spec is None:
			return None
		session = self._sessions.get(spec.engine)
		if session is not None:
			self.settings.ensure(spec)
		return session

	def getVoiceSpec(self, key: str) -> VoiceSpec:
		return self._specs[key]

	def getVoiceCapabilities(self, key: str) -> EngineCapabilities:
		return self._sessions[self.getVoiceSpec(key).engine].capabilities

	def getVoiceVariants(self, key: str) -> tuple[Mapping[str, str], ...]:
		return self._sessions[self.getVoiceSpec(key).engine].variants(key)

	def beginVoiceSettingsEdit(self) -> VoiceEditSession:
		return self.settings.begin_edit()

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
		for key in self._specs:
			if self.getVoiceCapabilities(key).supports_waitfactor:
				self.settings.ensure(self.getVoiceSpec(key)).update(waitfactor=value)

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
		spec = self.getVoiceSpec(voiceName)
		cls = READY_ENGINE_CLASS[spec.engine]
		self.settings.ensure(spec)
		voiceInstance = cls(
			id=spec.id,
			name=spec.name,
			language=spec.language,
			taskManager=self.taskManager,
		)
		voiceInstance.session = self._sessions[spec.engine]
		self._instanceCache[voiceName] = voiceInstance
		return voiceInstance

	def previewVoiceParameterConsistent(self, baseInstance):
		base = self.settings.snapshot(baseInstance.name)
		for key in self.settings.keys():
			self.settings.state(key).update(
				rate=base.rate,
				pitch=base.pitch,
				volume=base.volume,
				inflection=base.inflection,
				rateBoost=base.rateBoost,
			)

	def onVoiceParameterConsistent(self, baseInstance):
		self.previewVoiceParameterConsistent(baseInstance)
		for key in self.settings.keys():
			self.settings.commit(key)

	def onKeepEngineConsistent(self):
		temp = defaultdict(lambda: {})
		for key, value in config.conf["WorldVoice"]["role"].items():
			if isinstance(value, config.AggregatedSection):
				try:
					temp[key]["voice"] = config.conf["WorldVoice"]["role"][key]["voice"]
				except KeyError:
					pass
			else:
				temp[key] = config.conf["WorldVoice"]["role"][key]

		for localelo, data in config.conf["WorldVoice"]["role"].items():
			if isinstance(data, config.AggregatedSection):
				if (localelo not in self.localeToVoicesMap) or (
					"voice" in data and data["voice"] not in self.localeToVoicesMap[localelo]
				):
					try:
						del temp[localelo]
					except KeyError:
						pass
					# log.info(f"locale {localelo} voice {data['voice']} not available")

		config.conf["WorldVoice"]["role"] = temp

	def onKeepMainLocaleVoiceConsistent(self):
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"]:
			locale = (
				self.defaultVoiceInstance.language
				if self.defaultVoiceInstance.language
				else languageHandler.getLanguage()
			)
			locale = getPrimaryLocale(locale)
			if locale not in config.conf["WorldVoice"]["role"]:
				config.conf["WorldVoice"]["role"][locale] = {}
			config.conf["WorldVoice"]["role"][locale]["voice"] = self.defaultVoiceInstance.name

	def reload(self):
		for voiceName, instance in self._instanceCache.items():
			instance.loadParameter()

	def cancel(self):
		if self.taskManager:
			self.taskManager.cancel(self.playback_ports)

	@property
	def playback_ports(self) -> tuple[PlaybackPort, ...]:
		return tuple(dict.fromkeys(self._sessions.values()))

	def _setVoiceDatas(self):
		self.table = sorted(self._specs.values(), key=attrgetter("engine", "language", "name"))
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
				voice = config.conf["WorldVoice"]["role"][language]["voice"]
			except KeyError:
				pass
		if not voice:
			locale = getPrimaryLocale(language)
			if locale in config.conf["WorldVoice"]["role"]:
				try:
					voice = config.conf["WorldVoice"]["role"][locale]["voice"]
				except KeyError:
					pass
		return voice

	def _getLocaleReadableName(self, locale_):
		description = languageHandler.getLanguageDescription(locale_)
		return "%s - %s" % (description, locale_) if description else locale_
