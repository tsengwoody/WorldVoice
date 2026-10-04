from collections import OrderedDict, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from operator import attrgetter
from typing import Callable, TypeVar, Dict, List
import re

import config
import languageHandler
from logHandler import log
from synthDriverHandler import VoiceInfo

from .compat.engineAdapter import LegacyEngineAdapter
from .compat.voiceFacade import LegacyVoiceBinding
from .runtime.completion import rule_for
from .runtime.models import VoiceSpec, EngineCapabilities, CompletionContract, CompletionMode
from .indexLedger import IndexLedger
from .runtime.session import EngineSession, PlaybackPort
from .runtime.scheduler import TaskManager
from .runtime.settings import VoiceEditSession, VoiceSettingsStore
from .nvdaEventBridge import NvdaEventBridge

from .engine import EngineType, READY_ENGINE_CLASS, get_engine_enabled, refresh_ready_engine_classes


@dataclass
class EngineResource:
	"""One opened engine: its adapter, playback session and voice binding."""

	engine: str
	voice_class: type
	adapter: LegacyEngineAdapter
	session: EngineSession
	binding: LegacyVoiceBinding


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
		self._resources: list[EngineResource] = []
		self._sessions = {}
		self._bindings = {}
		self._specs = {}
		self._instanceCache = {}
		self._waitfactor = 0
		self._terminated = False
		try:
			self._initialize()
		except BaseException:
			# Release acquired resources even on KeyboardInterrupt, then re-raise.
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
			resource = self._open_engine(eng.name, cls)
			if resource is None:
				continue
			self._bind(resource)
			self._publish(resource)
		self._setVoiceDatas()
		if not self.table:
			raise RuntimeError("No WorldVoice voices are available from enabled speech engines.")
		self._defaultVoiceInstance = self.getVoiceInstance(self._getDefaultVoiceMeta().name)

	def _open_engine(self, name: str, cls: type) -> EngineResource | None:
		adapter = LegacyEngineAdapter(cls, self.getVoiceInstance, index_ledger=self._index_ledger)
		try:
			adapter.open()
		except Exception:
			log.error("engine %s on error", name, exc_info=True)
			return None
		session = EngineSession(adapter, self.settings)
		binding = LegacyVoiceBinding(self.settings, session, adapter.core)
		resource = EngineResource(name, cls, adapter, session, binding)
		# Claim cleanup before opening: every later step may fail.
		self._resources.append(resource)
		session.open()
		return resource

	def _bind(self, resource: EngineResource) -> None:
		adapter, session = resource.adapter, resource.session
		source = adapter.notification_source
		completion = self._resource_completion(resource.voice_class, source)
		adapter.configure_completion(completion)
		# Claim ownership before binding, since bind may register then raise.
		self._bridge.bind(source, session.source_id, completion=completion)
		if rule_for(completion).drain_event is not None:
			adapter.configure_segment_events(
				lambda context: self._bridge.segment_sink(source, context),
			)
		elif completion.legacy_contextual:
			adapter.configure_legacy_segment_events(
				lambda context: self._bridge.legacy_segment_sink(source, context),
			)

	def _publish(self, resource: EngineResource) -> None:
		# Only bound, operational resources become visible to resolvers.
		self._sessions[resource.engine] = resource.session
		self._bindings[resource.engine] = resource.binding
		for spec in resource.adapter.list_voices():
			self._specs[spec.name] = spec

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
		self._bindings.clear()
		if commit:
			for key in self.settings.keys():
				try:
					self.settings.commit(key)
				except Exception:
					log.error("Failed to save voice %s", key, exc_info=True)
		self._instanceCache.clear()
		for resource in reversed(self._resources):
			engine = resource.engine
			try:
				self._bridge.unbind(resource.session.source_id)
			except Exception:
				log.error("Failed to unbind engine %s", engine, exc_info=True)
			try:
				resource.session.close()
			except Exception:
				log.error("Failed to close engine %s", engine, exc_info=True)
		self._resources.clear()
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
		voiceInstance = cls(spec, self._bindings[spec.engine], self.taskManager)
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
