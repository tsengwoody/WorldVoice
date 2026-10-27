from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from logHandler import log

from ..bridge.engineAdapter import VoiceClassAdapter
from ..bridge.indexLedger import IndexLedger
from ..bridge.nvdaEvents import NvdaEventBridge
from ..bridge.voiceFacade import VoiceBinding
from ..runtime.completion import rule_for
from ..runtime.models import CompletionContract, EngineCapabilities, VoiceSpec
from ..runtime.scheduler import TaskManager
from ..runtime.session import EngineSession, PlaybackPort
from ..runtime.voiceSettings import VoiceEditSession, VoiceSettingsStore
from .catalog import EMPTY_CATALOG, VoiceCatalog, group_by_primary_locale
from .mainLocalePolicy import EngineConsistency, ParameterConsistency, VoiceConsistency
from .roles import ConfigRoleRepository


@dataclass
class EngineResource:
	"""One opened engine: its adapter, playback session and voice binding."""

	engine: str
	voice_class: type
	adapter: VoiceClassAdapter
	session: EngineSession
	binding: VoiceBinding
	voices: tuple[VoiceSpec, ...] = ()
	published: bool = False


class VoiceManager:
	def __init__(
		self,
		task_manager: TaskManager,
		settings: VoiceSettingsStore,
		bridge: NvdaEventBridge,
		*,
		index_ledger: IndexLedger,
		completion_for: Callable[[type, object], CompletionContract],
		engine_classes: Mapping[str, type],
		conf_provider: Callable[[], Any],
		get_language: Callable[[], str],
		parameter_consistency: ParameterConsistency | None = None,
		roles: ConfigRoleRepository | None = None,
	):
		self.task_manager = task_manager
		self.settings = settings
		self._bridge = bridge
		self._index_ledger = index_ledger
		self._completion_for = completion_for
		self._resources: dict[str, EngineResource] = {}
		self.catalog = EMPTY_CATALOG
		self._instance_cache = {}
		self._waitfactor = 0
		self._terminated = False
		self._default_voice_instance = None
		try:
			self._init_policies(
				conf_provider,
				get_language,
				roles=roles,
				parameter_consistency=parameter_consistency,
			)
			self.settings.set_inheritance(self._inherited_parameters)
			self._initialize(engine_classes)
		except BaseException:
			# Release acquired resources even on KeyboardInterrupt, then re-raise.
			self.terminate(commit=False)
			raise

	def _init_policies(self, conf_provider, get_language, *, roles=None, parameter_consistency=None):
		self._get_language = get_language
		self.roles = roles or ConfigRoleRepository(conf_provider)
		self.engine_consistency = EngineConsistency(conf_provider)
		self.voice_consistency = VoiceConsistency(conf_provider, self.roles, get_language)
		self.parameter_consistency = parameter_consistency or ParameterConsistency(conf_provider)

	def _initialize(self, engine_classes: Mapping[str, type]):
		for name, cls in engine_classes.items():
			resource = self._open_engine(name, cls)
			if resource is None:
				continue
			self._bind(resource)
			self._publish(resource)
		self._set_voice_data()
		if not self.table:
			raise RuntimeError("No WorldVoice voices are available from enabled speech engines.")
		self._default_voice_instance = self.get_voice_instance(self._get_default_voice_spec().name)

	def _open_engine(self, name: str, cls: type) -> EngineResource | None:
		adapter = VoiceClassAdapter(cls, self.get_voice_instance, indexLedger=self._index_ledger)
		try:
			adapter.open()
		except Exception:
			log.error("engine %s on error", name, exc_info=True)
			return None
		session = EngineSession(adapter, self.settings)
		binding = VoiceBinding(self.settings, session, adapter.core)
		resource = EngineResource(name, cls, adapter, session, binding)
		# Claim cleanup before opening: every later step may fail.
		self._resources[name] = resource
		session.open()
		return resource

	def _bind(self, resource: EngineResource) -> None:
		adapter, session = resource.adapter, resource.session
		source = adapter.notificationSource
		completion = self._completion_for(resource.voice_class, source)
		adapter.configureCompletion(completion)
		# Claim ownership before binding, since bind may register then raise.
		self._bridge.bind(source, session.source_id, completion=completion)
		if rule_for(completion).drain_event is not None:
			adapter.configureSegmentEvents(
				lambda context: self._bridge.segmentSink(source, context),
			)

	def _publish(self, resource: EngineResource) -> None:
		# Only bound, operational resources become visible to resolvers.
		resource.voices = resource.adapter.listVoices()
		resource.published = True

	def _published(self, engine: str) -> EngineResource:
		resource = self._resources[engine]
		if not resource.published:
			raise KeyError(engine)
		return resource

	def terminate(self, *, commit=True):
		if self._terminated:
			return
		self._terminated = True
		# Stop publication before releasing any resources.
		for resource in self._resources.values():
			resource.published = False
		if commit:
			for key in self.settings.names():
				try:
					self.settings.commit(key)
				except Exception:
					log.error("Failed to save voice %s", key, exc_info=True)
		self._instance_cache.clear()
		for resource in reversed(list(self._resources.values())):
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
		self.task_manager = None

	def resolve_playback(self, key: str) -> PlaybackPort | None:
		spec = self.catalog.by_name.get(key)
		if spec is None:
			return None
		resource = self._resources.get(spec.engine)
		if resource is None or not resource.published:
			return None
		self.settings.ensure(spec)
		return resource.session

	def get_voice_spec(self, key: str) -> VoiceSpec:
		return self.catalog.by_name[key]

	def get_voice_capabilities(self, key: str) -> EngineCapabilities:
		return self._published(self.get_voice_spec(key).engine).session.capabilities

	def get_voice_variants(self, key: str) -> tuple[Mapping[str, str], ...]:
		return self._published(self.get_voice_spec(key).engine).session.variants(key)

	def begin_voice_settings_edit(self) -> VoiceEditSession:
		return self.settings.begin_edit()

	@property
	def default_voice_instance(self):
		return self._default_voice_instance

	@property
	def default_voice_name(self):
		return self._default_voice_instance.name

	@default_voice_name.setter
	def default_voice_name(self, name):
		if name not in self.catalog.voice_infos:
			# NVDA's SynthDriver.loadSettings repairs the saved voice only when this raises.
			raise LookupError(name)
		self._default_voice_instance = self.get_voice_instance(name)
		self.on_keep_engine_consistent()
		self.on_keep_main_locale_voice_consistent()

	@property
	def waitfactor(self):
		return self._waitfactor

	@waitfactor.setter
	def waitfactor(self, value):
		self._waitfactor = value
		for key in self.catalog.by_name:
			if self.get_voice_capabilities(key).supports_waitfactor:
				self.settings.ensure(self.get_voice_spec(key)).update(waitfactor=value)

	def _get_default_voice_spec(self) -> VoiceSpec:
		lang = self._get_language()
		try:
			return next(v for v in self.table if v.language == lang)
		except StopIteration:
			return self.table[0]

	def get_voice_instance(self, voice_name):
		try:
			instance = self._instance_cache[voice_name]
		except KeyError:
			instance = self._create_voice_instance(voice_name)
		return instance

	def _create_voice_instance(self, voice_name: str):
		spec = self.get_voice_spec(voice_name)
		resource = self._published(spec.engine)
		self.settings.ensure(spec)
		voice_instance = resource.voice_class(spec, resource.binding)
		self._instance_cache[voice_name] = voice_instance
		return voice_instance

	def _inherited_parameters(self, spec: VoiceSpec) -> Mapping[str, Any]:
		"""A loading voice follows the main voice once one exists (the main voice loads first)."""
		main = self._default_voice_instance
		if main is None:
			return {}
		return self.parameter_consistency.inherited(self.settings, main.name)

	def preview_voice_parameter_consistent(self, base_instance):
		self.parameter_consistency.copy_from(self.settings, base_instance.name)

	def on_voice_parameter_consistent(self, base_instance):
		self.preview_voice_parameter_consistent(base_instance)
		for key in self.settings.names():
			self.settings.commit(key)

	def on_keep_engine_consistent(self):
		self.roles.prune(self.locale_to_voices_map)

	def on_keep_main_locale_voice_consistent(self):
		self.voice_consistency.follow(self.default_voice_instance)

	def reload(self):
		for instance in self._instance_cache.values():
			instance.loadParameter()

	def cancel(self):
		if self.task_manager:
			self.task_manager.cancel(self.playback_ports)

	@property
	def playback_ports(self) -> tuple[PlaybackPort, ...]:
		return tuple(resource.session for resource in self._resources.values() if resource.published)

	def _set_voice_data(self):
		self.catalog = VoiceCatalog.from_specs(
			spec for resource in self._resources.values() if resource.published for spec in resource.voices
		)

	@property
	def table(self) -> tuple[VoiceSpec, ...]:
		return self.catalog.table

	@property
	def voice_infos(self):
		return self.catalog.voice_infos

	@property
	def all_languages(self):
		return list(self.catalog.all_languages)

	def _visible_table(self):
		return self.engine_consistency.visible(self.table, self._default_voice_instance.engine)

	@property
	def languages(self):
		return sorted(group_by_primary_locale(self._visible_table()))

	@property
	def locale_to_voices_map(self):
		return group_by_primary_locale(self._visible_table())

	@property
	def locales_to_names_map(self):
		return {locale: self.catalog.readable_name(locale) for locale in self.locale_to_voices_map}

	def get_voice_name_for_language(self, language):
		configured = self._get_configured_voice_name_for_language(language)
		if configured is not None and configured in self.voice_infos:
			return configured
		return self.default_voice_name

	def get_voice_locale_for_language(self, language) -> str | None:
		"""The locale of the voice get_voice_name_for_language picks; None when that voice has no spec."""
		spec = self.catalog.by_name.get(self.get_voice_name_for_language(language))
		return spec.locale if spec is not None else None

	def _get_configured_voice_name_for_language(self, language):
		return self.roles.voice_for(language)
