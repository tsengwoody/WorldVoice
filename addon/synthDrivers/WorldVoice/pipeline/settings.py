from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

import addonHandler
import config
from logHandler import log

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

# Group pauses use the same unit scaling as punctuation pauses so that both
# pause families behave consistently and remain audible regardless of the
# global wait factor.
GROUP_WAIT_UNIT_MS = 5


def _floor_to_ten(value: Any) -> int:
	return int(value) // 10 * 10


def _strip(value: Any) -> str:
	return str(value).strip()


# The Speech Pipeline panel's scope choices: (stored value, label), in display order.
SCOPE_CHOICES: tuple[tuple[str, str], ...] = (
	# Translators: A choice of the Speech Pipeline panel's effect scope: every synthesizer.
	("all", _("All Synthesizers (Global)")),
	# Translators: A choice of the Speech Pipeline panel's effect scope: WorldVoice only.
	("WorldVoice", _("Only WorldVoice Synthesizer")),
)

# The number modes: (stored value, label), in display order.
NUMBER_MODE_CHOICES: tuple[tuple[str, str], ...] = (
	# Translators: A number mode: a number is read as a value, for example "one hundred twenty-three".
	("value", _("value")),
	# Translators: A number mode: the digits of a number are read one by one.
	("number", _("number")),
	# Translators: A number mode: the digits of a number are read in groups of the chosen size, counted from the left.
	("group", _("group")),
)

# The number modes the pipeline knows; any other stored or written mode reads as "value".
NUMBER_MODES: tuple[str, ...] = tuple(value for value, _label in NUMBER_MODE_CHOICES)


def _number_mode(value: Any) -> str:
	mode = str(value)
	return mode if mode in NUMBER_MODES else "value"


@dataclass(frozen=True)
class PipelineSettingSpec:
	"""One pipeline setting: its config key, type, default, synth-setting metadata and panel control."""

	key: str
	kind: type
	default: Any
	driver_id: str | None = None
	label: str | None = None
	display_name: str | None = None
	ring: bool = True
	min_step: int = 1
	normalize: Callable[[Any], Any] | None = None
	# Bounds of an int setting: its confspec range, and the clamp convert applies.
	min_value: int = 0
	max_value: int = 100
	# The panel control: "checkbox", "slider", "choice", "spin" or "text".
	control: str | None = None
	# (stored value, label) pairs of a choice, in display order; None when the driver supplies them.
	choices: tuple[tuple[str, str], ...] | None = None
	# (controller key, value): the control is enabled only while the controller shows that value.
	depends_on: tuple[str, Any] | None = None
	# Where the setting is shown: "voice" (NVDA's Voice panel and the ring) and "pipeline".
	panels: tuple[str, ...] = ("voice", "pipeline")
	# The Speech Pipeline panel's slider shows value // panel_scale and saves shown * panel_scale.
	panel_scale: int = 1
	# False: an ordering-only entry whose value NVDA stores as a driver setting.
	pipeline_config: bool = True

	def convert(self, value: Any) -> Any:
		result = self.normalize(value) if self.normalize is not None else self.kind(value)
		if self.kind is int:
			return min(max(result, self.min_value), self.max_value)
		return result

	@property
	def confspec(self) -> str:
		if self.kind is bool:
			return f"boolean(default={str(self.default).lower()})"
		if self.kind is int:
			return f"integer(default={self.default},min={self.min_value},max={self.max_value})"
		return f'string(default="{self.default}")'


# Every panel and the settings ring show these settings in this order.
PIPELINE_SETTINGS: tuple[PipelineSettingSpec, ...] = (
	PipelineSettingSpec(
		"scope",
		str,
		"WorldVoice",
		control="choice",
		choices=SCOPE_CHOICES,
		panels=("pipeline",),
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Effect scope"),
	),
	PipelineSettingSpec(
		"global_wait_factor",
		int,
		10,
		driver_id="globalwaitfactor",
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Global wait factor"),
		min_step=10,
		normalize=_floor_to_ten,
		control="slider",
		panel_scale=10,
	),
	PipelineSettingSpec(
		"ignore_comma_between_number",
		bool,
		False,
		driver_id="cni",
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Ignore commas between numbers"),
		ring=False,
		control="checkbox",
	),
	PipelineSettingSpec(
		"number_mode",
		str,
		"value",
		driver_id="nummod",
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Number &mode"),
		# Translators: Label for a setting in synth settings ring.
		display_name=_("Number mode"),
		normalize=_number_mode,
		control="choice",
		choices=NUMBER_MODE_CHOICES,
	),
	# Digits per group in group number mode; set in the panels only, so no synth setting.
	PipelineSettingSpec(
		"group_size",
		int,
		3,
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Group size"),
		min_value=1,
		max_value=10,
		control="spin",
		depends_on=("number_mode", "group"),
	),
	PipelineSettingSpec(
		"group_wait_factor",
		int,
		0,
		driver_id="groupwaitfactor",
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Group wait factor"),
		control="slider",
		depends_on=("number_mode", "group"),
	),
	PipelineSettingSpec(
		"number_wait_factor",
		int,
		10,
		driver_id="numberwaitfactor",
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Number wait factor"),
		control="slider",
	),
	PipelineSettingSpec(
		"item_wait_factor",
		int,
		10,
		driver_id="itemwaitfactor",
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Item wait factor"),
		control="slider",
	),
	PipelineSettingSpec(
		"sayall_wait_factor",
		int,
		10,
		driver_id="sayallwaitfactor",
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Say all wait factor"),
		control="slider",
	),
	PipelineSettingSpec(
		"chinesespace_wait_factor",
		int,
		10,
		driver_id="chinesespacewaitfactor",
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Chinese space wait factor"),
		control="slider",
	),
	PipelineSettingSpec(
		"punctuation_pause_enabled",
		bool,
		True,
		driver_id="punctuationpauseenabled",
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Enable punctuation pause control"),
		# Translators: Label for a setting in synth settings ring.
		display_name=_("Punctuation pauses"),
		control="checkbox",
	),
	PipelineSettingSpec(
		"remove_punctuation_characters",
		bool,
		False,
		driver_id="removepunctuationcharacters",
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Remove configured punctuation at pause points"),
		# Translators: Label for a setting in synth settings ring.
		display_name=_("Remove punctuation at pause points"),
		control="checkbox",
		depends_on=("punctuation_pause_enabled", True),
	),
	PipelineSettingSpec(
		"punctuation_wait_factor",
		int,
		0,
		driver_id="punctuationwaitfactor",
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Punctuation wait factor"),
		control="slider",
		depends_on=("punctuation_pause_enabled", True),
	),
	PipelineSettingSpec(
		"punctuation_pause_characters",
		str,
		"",
		# Translators: Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.
		label=_("Punctuation pause characters"),
		normalize=_strip,
		control="text",
		depends_on=("punctuation_pause_enabled", True),
	),
)

# The entries stored in the pipeline config section; ordering-only entries are left out.
PIPELINE_STORED_SETTINGS = tuple(spec for spec in PIPELINE_SETTINGS if spec.pipeline_config)
PIPELINE_SETTING_BY_KEY = {spec.key: spec for spec in PIPELINE_STORED_SETTINGS}
DEFAULT_PIPELINE_SETTINGS = {spec.key: spec.default for spec in PIPELINE_STORED_SETTINGS}
PIPELINE_CONFIG_KEYS = tuple(spec.key for spec in PIPELINE_STORED_SETTINGS)
PIPELINE_CONFSPEC = {spec.key: spec.confspec for spec in PIPELINE_STORED_SETTINGS}


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
	group_wait_factor: int
	group_size: int

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

	def scaled_group_wait(self) -> int:
		return min(
			self.group_wait_factor * GROUP_WAIT_UNIT_MS,
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
				group_wait_factor=0,
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
			**{spec.key: spec.convert(_get_value(section, spec.key)) for spec in PIPELINE_STORED_SETTINGS},
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
