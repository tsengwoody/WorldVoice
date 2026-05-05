from dataclasses import dataclass
from typing import Any, Callable

import config
from synthDriverHandler import getSynth


DEFAULT_PIPELINE_SETTINGS = {
	"scope": "WorldVoice",
	"ignore_comma_between_number": False,
	"number_mode": "value",
	"global_wait_factor": 10,
	"number_wait_factor": 10,
	"item_wait_factor": 10,
	"sayall_wait_factor": 10,
	"chinesespace_wait_factor": 10,
}

PIPELINE_CONFIG_KEYS = (
	"scope",
	"ignore_comma_between_number",
	"number_mode",
	"global_wait_factor",
	"number_wait_factor",
	"item_wait_factor",
	"sayall_wait_factor",
	"chinesespace_wait_factor",
)

_last_scope_application: tuple[str, str] | None = None


@dataclass
class PipelineSettings:
	scope: str
	ignore_comma_between_number: bool
	number_mode: str
	global_wait_factor: int
	number_wait_factor: int
	item_wait_factor: int
	sayall_wait_factor: int
	chinesespace_wait_factor: int

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


def _pipeline_section(conf: Any) -> Any:
	return conf["WorldVoice"]["pipeline"]


def _get_value(section: Any, key: str) -> Any:
	try:
		return section.get(key, DEFAULT_PIPELINE_SETTINGS[key])
	except AttributeError:
		try:
			return section[key]
		except KeyError:
			return DEFAULT_PIPELINE_SETTINGS[key]


def load_pipeline_settings(conf: Any = config.conf) -> PipelineSettings:
	pipeline = _pipeline_section(conf)
	return PipelineSettings(
		scope=str(_get_value(pipeline, "scope")),
		ignore_comma_between_number=bool(_get_value(pipeline, "ignore_comma_between_number")),
		number_mode=str(_get_value(pipeline, "number_mode")),
		global_wait_factor=int(_get_value(pipeline, "global_wait_factor")),
		number_wait_factor=int(_get_value(pipeline, "number_wait_factor")),
		item_wait_factor=int(_get_value(pipeline, "item_wait_factor")),
		sayall_wait_factor=int(_get_value(pipeline, "sayall_wait_factor")),
		chinesespace_wait_factor=int(_get_value(pipeline, "chinesespace_wait_factor")),
	)


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
		if settings.scope != "all":
			settings.ignore_comma_between_number = False
			settings.number_wait_factor = 0
			settings.item_wait_factor = 0
			settings.sayall_wait_factor = 0
			settings.chinesespace_wait_factor = 0
			return settings
		settings.ignore_comma_between_number = bool(
			settings.global_factor_units * settings.ignore_comma_between_number
		)
		return settings

	return PipelineSettings(
		scope=settings.scope,
		ignore_comma_between_number=bool(
			_runtime_value(synth, "cni", "_cni", settings.ignore_comma_between_number)
		),
		number_mode=str(_runtime_value(synth, "nummod", "_nummod", settings.number_mode)),
		global_wait_factor=int(
			_runtime_value(synth, "globalwaitfactor", "_globalwaitfactor", settings.global_wait_factor)
		),
		number_wait_factor=int(
			_runtime_value(synth, "numberwaitfactor", "_numberwaitfactor", settings.number_wait_factor)
		),
		item_wait_factor=int(_runtime_value(synth, "itemwaitfactor", "_itemwaitfactor", settings.item_wait_factor)),
		sayall_wait_factor=int(
			_runtime_value(synth, "sayallwaitfactor", "_sayallwaitfactor", settings.sayall_wait_factor)
		),
		chinesespace_wait_factor=int(
			_runtime_value(
				synth,
				"chinesespacewaitfactor",
				"_chinesespacewaitfactor",
				settings.chinesespace_wait_factor,
			)
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


def apply_pipeline_settings_to_speech_config(settings: PipelineSettings, conf: Any = config.conf) -> None:
	speech_settings = conf["speech"]["WorldVoice"]
	speech_settings["cni"] = settings.ignore_comma_between_number
	speech_settings["nummod"] = settings.number_mode
	speech_settings["globalwaitfactor"] = settings.global_wait_factor
	speech_settings["numberwaitfactor"] = settings.number_wait_factor
	speech_settings["itemwaitfactor"] = settings.item_wait_factor
	speech_settings["sayallwaitfactor"] = settings.sayall_wait_factor
	speech_settings["chinesespacewaitfactor"] = settings.chinesespace_wait_factor


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
