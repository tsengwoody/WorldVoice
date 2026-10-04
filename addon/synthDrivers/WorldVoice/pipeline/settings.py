from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

import addonHandler
import config
from logHandler import log
from synthDriverHandler import getSynth

addonHandler.initTranslation()


# Maximum pause (in milliseconds) injected after a punctuation mark.
# The pause is intentionally capped so the voice never falls fully silent
# at punctuation, no matter how high the configured factor is.
MAX_PUNCTUATION_WAIT_MS = 500

# Milliseconds of pause per unit of punctuation_wait_factor (0..100),
# so the full slider range maps to 0..500ms on its own, independent of the
# global wait factor. This keeps the punctuation pause audible even when the
# global wait factor is 0.
PUNCTUATION_WAIT_UNIT_MS = 5

# Pair pauses use the same unit scaling as punctuation pauses so that both
# pause families behave consistently and remain audible regardless of the
# global wait factor.
PAIR_WAIT_UNIT_MS = 5


def _floor_to_ten(value: Any) -> int:
	return int(value) // 10 * 10


def _strip(value: Any) -> str:
	return str(value).strip()


@dataclass(frozen=True)
class PipelineSettingSpec:
	"""One pipeline setting: its config key, type, default and synth-setting metadata."""

	key: str
	kind: type
	default: Any
	driver_id: str | None = None
	label: str | None = None
	display_name: str | None = None
	ring: bool = True
	min_step: int = 1
	normalize: Callable[[Any], Any] | None = None

	def convert(self, value: Any) -> Any:
		if self.normalize is not None:
			return self.normalize(value)
		return self.kind(value)

	@property
	def confspec(self) -> str:
		if self.kind is bool:
			return f"boolean(default={str(self.default).lower()})"
		if self.kind is int:
			return f"integer(default={self.default},min=0,max=100)"
		return f'string(default="{self.default}")'


# Synth settings appear in the voice settings dialog in this order.
PIPELINE_SETTINGS: tuple[PipelineSettingSpec, ...] = (
	PipelineSettingSpec(
		"ignore_comma_between_number",
		bool,
		False,
		driver_id="cni",
		label=_("Ignore comma between number"),
		ring=False,
	),
	PipelineSettingSpec(
		"number_mode",
		str,
		"value",
		driver_id="nummod",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Number &Mode"),
		# Translators: Label for a setting in synth settings ring.
		display_name=_("Number Mode"),
	),
	PipelineSettingSpec(
		"global_wait_factor",
		int,
		10,
		driver_id="globalwaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Global wait factor"),
		min_step=10,
		normalize=_floor_to_ten,
	),
	PipelineSettingSpec(
		"number_wait_factor",
		int,
		10,
		driver_id="numberwaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Number wait factor"),
	),
	PipelineSettingSpec(
		"pair_wait_factor",
		int,
		0,
		driver_id="pairwaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Pair wait factor"),
	),
	PipelineSettingSpec(
		"item_wait_factor",
		int,
		10,
		driver_id="itemwaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("item wait factor"),
	),
	PipelineSettingSpec(
		"sayall_wait_factor",
		int,
		10,
		driver_id="sayallwaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Say all wait factor"),
	),
	PipelineSettingSpec(
		"chinesespace_wait_factor",
		int,
		10,
		driver_id="chinesespacewaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Chinese space wait factor"),
	),
	PipelineSettingSpec(
		"punctuation_pause_enabled",
		bool,
		True,
		driver_id="punctuationpauseenabled",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Enable punctuation pause control"),
		# Translators: Label for a setting in synth settings ring.
		display_name=_("Punctuation pauses"),
	),
	PipelineSettingSpec(
		"remove_punctuation_characters",
		bool,
		False,
		driver_id="removepunctuationcharacters",
		label=_("Remove configured punctuation at pause points"),
		display_name=_("Remove punctuation at pause points"),
	),
	PipelineSettingSpec(
		"punctuation_wait_factor",
		int,
		0,
		driver_id="punctuationwaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Punctuation wait factor"),
	),
	PipelineSettingSpec("scope", str, "WorldVoice"),
	PipelineSettingSpec("punctuation_pause_characters", str, "،؛,.;:!؟?…", normalize=_strip),
)

PIPELINE_SETTING_BY_KEY = {spec.key: spec for spec in PIPELINE_SETTINGS}
DEFAULT_PIPELINE_SETTINGS = {spec.key: spec.default for spec in PIPELINE_SETTINGS}
PIPELINE_CONFIG_KEYS = tuple(spec.key for spec in PIPELINE_SETTINGS)
PIPELINE_CONFSPEC = {spec.key: spec.confspec for spec in PIPELINE_SETTINGS}


@dataclass(frozen=True)
class PipelineSettings:
	scope: str
	ignore_comma_between_number: bool
	number_mode: str
	global_wait_factor: int
	number_wait_factor: int
	item_wait_factor: int
	sayall_wait_factor: int
	chinesespace_wait_factor: int
	punctuation_wait_factor: int
	punctuation_pause_enabled: bool
	remove_punctuation_characters: bool
	punctuation_pause_characters: str
	pair_wait_factor: int

	@property
	def global_factor_units(self) -> int:
		return self.global_wait_factor // 10

	def scaled_number_wait(self) -> int:
		return self.global_factor_units * self.number_wait_factor

	def scaled_item_wait(self) -> int:
		return self.global_factor_units * self.item_wait_factor

	def scaled_sayall_wait(self) -> int:
		return self.global_factor_units * self.sayall_wait_factor

	def scaled_chinesespace_wait(self) -> int:
		return self.global_factor_units * self.chinesespace_wait_factor

	def scaled_punctuation_wait(self) -> int:
		return min(
			self.punctuation_wait_factor * PUNCTUATION_WAIT_UNIT_MS,
			MAX_PUNCTUATION_WAIT_MS,
		)

	def scaled_pair_wait(self) -> int:
		return min(
			self.pair_wait_factor * PAIR_WAIT_UNIT_MS,
			MAX_PUNCTUATION_WAIT_MS,
		)

	def effective(self, supports_roles: bool) -> "PipelineSettings":
		"""The settings a synthesizer actually speaks with.

		WorldVoice uses them as stored. Other synthesizers get the pipeline
		only with scope "all"; otherwise every pause and removal is off.
		"""
		if supports_roles:
			return self
		if self.scope != "all":
			return replace(
				self,
				ignore_comma_between_number=False,
				number_wait_factor=0,
				item_wait_factor=0,
				sayall_wait_factor=0,
				chinesespace_wait_factor=0,
				punctuation_wait_factor=0,
				punctuation_pause_enabled=False,
				remove_punctuation_characters=False,
				pair_wait_factor=0,
			)
		return replace(
			self,
			ignore_comma_between_number=bool(self.global_factor_units * self.ignore_comma_between_number),
		)


def _get_value(section: Any, key: str) -> Any:
	try:
		return section.get(key, DEFAULT_PIPELINE_SETTINGS[key])
	except AttributeError:
		try:
			return section[key]
		except KeyError:
			return DEFAULT_PIPELINE_SETTINGS[key]


class ConfigPipelineRepository:
	"""Read and write the pipeline section of the active NVDA configuration profile."""

	def __init__(self, conf_provider: Callable[[], Any] = lambda: config.conf):
		self._conf_provider = conf_provider

	def _section(self) -> Any:
		return self._conf_provider()["WorldVoice"]["pipeline"]

	def load(self) -> PipelineSettings:
		section = self._section()
		return PipelineSettings(
			**{spec.key: spec.convert(_get_value(section, spec.key)) for spec in PIPELINE_SETTINGS},
		)

	def save(self, changes: Mapping[str, Any]) -> None:
		section = self._section()
		for key, value in changes.items():
			section[key] = value


class PipelineSettingsService:
	"""The only reader and writer of pipeline settings; notifies subscribers on change."""

	def __init__(self, repository: ConfigPipelineRepository):
		self._repository = repository
		self._listeners: list[Callable[[PipelineSettings], None]] = []

	def get(self) -> PipelineSettings:
		return self._repository.load()

	def effective(self, supports_roles: bool) -> PipelineSettings:
		return self.get().effective(supports_roles)

	def update(self, **changes: Any) -> PipelineSettings:
		converted = {}
		for key, value in changes.items():
			try:
				spec = PIPELINE_SETTING_BY_KEY[key]
			except KeyError:
				raise KeyError(f"Unknown pipeline setting: {key}") from None
			converted[key] = spec.convert(value)
		current = self.get()
		changed = {key: value for key, value in converted.items() if getattr(current, key) != value}
		if not changed:
			return current
		self._repository.save(changed)
		settings = self.get()
		for listener in tuple(self._listeners):
			try:
				listener(settings)
			except Exception:
				log.error("WorldVoice: pipeline settings listener failed", exc_info=True)
		return settings

	def subscribe(self, listener: Callable[[PipelineSettings], None]) -> None:
		if listener not in self._listeners:
			self._listeners.append(listener)

	def unsubscribe(self, listener: Callable[[PipelineSettings], None]) -> None:
		try:
			self._listeners.remove(listener)
		except ValueError:
			pass


pipeline_settings = PipelineSettingsService(ConfigPipelineRepository())


_last_scope_application: tuple[str, str] | None = None


def _pipeline_section(conf: Any) -> Any:
	return conf["WorldVoice"]["pipeline"]


def load_pipeline_settings(conf: Any = config.conf) -> PipelineSettings:
	return ConfigPipelineRepository(lambda: conf).load()


def save_pipeline_settings(settings: PipelineSettings, conf: Any = config.conf) -> None:
	pipeline = _pipeline_section(conf)
	for key in PIPELINE_CONFIG_KEYS:
		pipeline[key] = getattr(settings, key)


def _runtime_value(synth: Any, public_name: str, private_name: str, fallback: Any) -> Any:
	if hasattr(synth, public_name):
		return getattr(synth, public_name)
	if hasattr(synth, private_name):
		return getattr(synth, private_name)
	return fallback


def get_effective_pipeline_settings(synth: Any | None = None, conf: Any = config.conf) -> PipelineSettings:
	if synth is None:
		try:
			synth = getSynth()
		except Exception:
			synth = None

	settings = load_pipeline_settings(conf)
	if getattr(synth, "name", None) != "WorldVoice":
		return settings.effective(False)

	return PipelineSettings(
		scope=settings.scope,
		ignore_comma_between_number=bool(
			_runtime_value(synth, "cni", "_cni", settings.ignore_comma_between_number),
		),
		number_mode=str(_runtime_value(synth, "nummod", "_nummod", settings.number_mode)),
		global_wait_factor=int(
			_runtime_value(synth, "globalwaitfactor", "_globalwaitfactor", settings.global_wait_factor),
		),
		number_wait_factor=int(
			_runtime_value(synth, "numberwaitfactor", "_numberwaitfactor", settings.number_wait_factor),
		),
		item_wait_factor=int(
			_runtime_value(synth, "itemwaitfactor", "_itemwaitfactor", settings.item_wait_factor),
		),
		sayall_wait_factor=int(
			_runtime_value(synth, "sayallwaitfactor", "_sayallwaitfactor", settings.sayall_wait_factor),
		),
		chinesespace_wait_factor=int(
			_runtime_value(
				synth,
				"chinesespacewaitfactor",
				"_chinesespacewaitfactor",
				settings.chinesespace_wait_factor,
			),
		),
		punctuation_wait_factor=int(
			_runtime_value(
				synth,
				"punctuationwaitfactor",
				"_punctuationwaitfactor",
				settings.punctuation_wait_factor,
			),
		),
		punctuation_pause_enabled=bool(
			_runtime_value(
				synth,
				"punctuationpauseenabled",
				"_punctuationpauseenabled",
				settings.punctuation_pause_enabled,
			),
		),
		remove_punctuation_characters=bool(
			_runtime_value(
				synth,
				"removepunctuationcharacters",
				"_removepunctuationcharacters",
				settings.remove_punctuation_characters,
			),
		),
		punctuation_pause_characters=str(settings.punctuation_pause_characters),
		pair_wait_factor=int(
			_runtime_value(
				synth,
				"pairwaitfactor",
				"_pairwaitfactor",
				settings.pair_wait_factor,
			),
		),
	)


def apply_pipeline_settings_to_synth(synth: Any, settings: PipelineSettings) -> None:
	synth.cni = settings.ignore_comma_between_number
	synth.nummod = settings.number_mode
	synth.globalwaitfactor = settings.global_wait_factor
	synth.numberwaitfactor = settings.number_wait_factor
	synth.itemwaitfactor = settings.item_wait_factor
	synth.sayallwaitfactor = settings.sayall_wait_factor
	synth.chinesespacewaitfactor = settings.chinesespace_wait_factor
	synth.punctuationwaitfactor = settings.punctuation_wait_factor
	synth.punctuationpauseenabled = settings.punctuation_pause_enabled
	synth.removepunctuationcharacters = settings.remove_punctuation_characters
	synth.pairwaitfactor = settings.pair_wait_factor


def apply_pipeline_settings_to_speech_config(settings: PipelineSettings, conf: Any = config.conf) -> None:
	speech_settings = conf["speech"]["WorldVoice"]
	speech_settings["cni"] = settings.ignore_comma_between_number
	speech_settings["nummod"] = settings.number_mode
	speech_settings["globalwaitfactor"] = settings.global_wait_factor
	speech_settings["numberwaitfactor"] = settings.number_wait_factor
	speech_settings["itemwaitfactor"] = settings.item_wait_factor
	speech_settings["sayallwaitfactor"] = settings.sayall_wait_factor
	speech_settings["chinesespacewaitfactor"] = settings.chinesespace_wait_factor
	speech_settings["punctuationwaitfactor"] = settings.punctuation_wait_factor
	speech_settings["punctuationpauseenabled"] = settings.punctuation_pause_enabled
	speech_settings["removepunctuationcharacters"] = settings.remove_punctuation_characters
	speech_settings["pairwaitfactor"] = settings.pair_wait_factor


def _load_scope_functions():
	from . import dynamic_register, order_move_to_start_register, static_register, unregister

	return static_register, dynamic_register, order_move_to_start_register, unregister


def clear_pipeline(
	unregister: Callable[[], None] | None = None,
	reset_scope_application: bool = True,
) -> None:
	global _last_scope_application

	if unregister is None:
		*_, unregister = _load_scope_functions()

	unregister()
	if reset_scope_application:
		_last_scope_application = None


def clear_global_pipeline_scope(
	settings: PipelineSettings,
	unregister: Callable[[], None] | None = None,
) -> None:
	if settings.scope == "all":
		clear_pipeline(unregister=unregister)


def apply_worldvoice_pipeline(
	static_register: Callable[[], None] | None = None,
	order_move_to_start_register: Callable[[], None] | None = None,
) -> None:
	if static_register is None or order_move_to_start_register is None:
		default_static_register, _, default_order_move_to_start_register, _ = _load_scope_functions()
		static_register = static_register or default_static_register
		order_move_to_start_register = order_move_to_start_register or default_order_move_to_start_register

	static_register()
	order_move_to_start_register()


def apply_global_pipeline_scope(
	settings: PipelineSettings,
	current_synth_name: str,
	static_register: Callable[[], None] | None = None,
	dynamic_register: Callable[[], None] | None = None,
	order_move_to_start_register: Callable[[], None] | None = None,
	unregister: Callable[[], None] | None = None,
) -> None:
	global _last_scope_application

	if current_synth_name == "WorldVoice":
		return

	if None in (static_register, dynamic_register, order_move_to_start_register, unregister):
		(
			default_static_register,
			default_dynamic_register,
			default_order_move_to_start_register,
			default_unregister,
		) = _load_scope_functions()
		static_register = static_register or default_static_register
		dynamic_register = dynamic_register or default_dynamic_register
		order_move_to_start_register = order_move_to_start_register or default_order_move_to_start_register
		unregister = unregister or default_unregister

	scope_state = (settings.scope, current_synth_name)
	if scope_state == _last_scope_application:
		return
	_last_scope_application = scope_state

	if settings.scope == "all":
		clear_pipeline(unregister=unregister, reset_scope_application=False)
		static_register()
		dynamic_register()
		order_move_to_start_register()
	elif settings.scope == "WorldVoice":
		clear_pipeline(unregister=unregister, reset_scope_application=False)


def apply_pipeline_after_worldvoice_end(
	settings: PipelineSettings,
	static_register: Callable[[], None] | None = None,
	dynamic_register: Callable[[], None] | None = None,
	order_move_to_start_register: Callable[[], None] | None = None,
	unregister: Callable[[], None] | None = None,
) -> None:
	if None in (static_register, dynamic_register, order_move_to_start_register, unregister):
		(
			default_static_register,
			default_dynamic_register,
			default_order_move_to_start_register,
			default_unregister,
		) = _load_scope_functions()
		static_register = static_register or default_static_register
		dynamic_register = dynamic_register or default_dynamic_register
		order_move_to_start_register = order_move_to_start_register or default_order_move_to_start_register
		unregister = unregister or default_unregister

	if settings.scope == "all":
		clear_pipeline(unregister=unregister)
		static_register()
		dynamic_register()
		order_move_to_start_register()
