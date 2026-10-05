from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable

import config
import languageHandler
from logHandler import log

from .compat.engineAdapter import LegacyEngineAdapter
from .compat.voiceFacade import LegacyVoiceBinding
from .engine import READY_ENGINE_CLASS, EngineType, get_engine_enabled, refresh_ready_engine_classes
from .indexLedger import IndexLedger
from .mainLocalePolicy import EngineConsistency, ParameterConsistency, VoiceConsistency
from .nvdaEventBridge import NvdaEventBridge
from .roles import ConfigRoleRepository
from .runtime.completion import rule_for
from .runtime.models import CompletionContract, EngineCapabilities, VoiceSpec
from .runtime.scheduler import TaskManager
from .runtime.session import EngineSession, PlaybackPort
from .runtime.settings import VoiceEditSession, VoiceSettingsStore
from .voiceCatalog import EMPTY_CATALOG, VoiceCatalog, group_by_primary_locale


@dataclass
class EngineResource:
	"""One opened engine: its adapter, playback session and voice binding."""

	engine: str
	voice_class: type
	adapter: LegacyEngineAdapter
	session: EngineSession
	binding: LegacyVoiceBinding


class VoiceManager(object):
	def __init__(
		self,
		taskManager: TaskManager,
		settings: VoiceSettingsStore,
		bridge: NvdaEventBridge,
		*,
		index_ledger: IndexLedger,
		completion_for: Callable[[type, object], CompletionContract],
		roles: ConfigRoleRepository | None = None,
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
		self.catalog = EMPTY_CATALOG
		self._instanceCache = {}
		self._waitfactor = 0
		self._terminated = False
		try:
			self._init_policies(roles)
			self._initialize()
		except BaseException:
			# Release acquired resources even on KeyboardInterrupt, then re-raise.
			self.terminate(commit=False)
			raise

	def _init_policies(self, roles=None):
		def conf_provider():
			return config.conf

		self.roles = roles or ConfigRoleRepository(conf_provider)
		self.engine_consistency = EngineConsistency(conf_provider)
		self.voice_consistency = VoiceConsistency(conf_provider, self.roles, languageHandler.getLanguage)
		self.parameter_consistency = ParameterConsistency(conf_provider)

	def _initialize(self):
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
		self._defaultVoiceInstance = self.getVoiceInstance(self._getDefaultVoiceSpec().name)

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
		completion = self._completion_for(resource.voice_class, source)
		adapter.configure_completion(completion)
		# Claim ownership before binding, since bind may register then raise.
		self._bridge.bind(source, session.source_id, completion=completion)
		if rule_for(completion).drain_event is not None:
			adapter.configure_segment_events(
				lambda context: self._bridge.segment_sink(source, context),
			)

	def _publish(self, resource: EngineResource) -> None:
		# Only bound, operational resources become visible to resolvers.
		self._sessions[resource.engine] = resource.session
		self._bindings[resource.engine] = resource.binding
		for spec in resource.adapter.list_voices():
			self._specs[spec.name] = spec

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
		return self.catalog.by_name[key]

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
		if name not in self.catalog.voice_infos:
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
		for key in self.catalog.by_name:
			if self.getVoiceCapabilities(key).supports_waitfactor:
				self.settings.ensure(self.getVoiceSpec(key)).update(waitfactor=value)

	def _getDefaultVoiceSpec(self) -> VoiceSpec:
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
		self.parameter_consistency.copy_from(self.settings, baseInstance.name)

	def onVoiceParameterConsistent(self, baseInstance):
		self.previewVoiceParameterConsistent(baseInstance)
		for key in self.settings.keys():
			self.settings.commit(key)

	def onKeepEngineConsistent(self):
		self.roles.prune(self.localeToVoicesMap)

	def onKeepMainLocaleVoiceConsistent(self):
		self.voice_consistency.follow(self.defaultVoiceInstance)

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
		self.catalog = VoiceCatalog.from_specs(self._specs.values())

	@property
	def table(self) -> tuple[VoiceSpec, ...]:
		return self.catalog.table

	@property
	def voiceInfos(self):
		return self.catalog.voice_infos

	@property
	def allLanguages(self):
		return list(self.catalog.all_languages)

	def _visible_table(self):
		return self.engine_consistency.visible(self.table, self._defaultVoiceInstance.engine)

	@property
	def languages(self):
		return sorted(group_by_primary_locale(self._visible_table()))

	@property
	def localeToVoicesMap(self):
		return group_by_primary_locale(self._visible_table())

	@property
	def localesToNamesMap(self):
		return {locale: self.catalog.readable_name(locale) for locale in self.localeToVoicesMap}

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
		return self.roles.voice_for(language)
