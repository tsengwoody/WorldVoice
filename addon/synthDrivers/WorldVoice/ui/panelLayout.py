"""The layout rules both settings panels follow, read from the pipeline settings table.

Pure functions over table entries (PipelineSettingSpec, or anything with the same attributes):
no add-on, wx or NVDA import, so tests and mutmut can load this module on its own. Both the
NVDA Voice panel and the Speech Pipeline panel use them, so a rule is written once.
"""

from collections.abc import Callable, Iterable, Sequence
from typing import Any

VOICE_PANEL = "voice"
PIPELINE_PANEL = "pipeline"
# What a panel's read() returns for a controller it has no control for (another synthesizer).
ABSENT = object()

# Attribute suffixes: the Speech Pipeline panel's _<key>_<suffix>, the Voice panel's <camelKey><Suffix>,
# and the names NVDA gives the driver controls it makes (<driver_id>Checkbox|Slider|List).
_PIPELINE_SUFFIXES = {
	"checkbox": "checkbox",
	"choice": "choice",
	"slider": "slider",
	"spin": "spin",
	"text": "edit",
}
_VOICE_SUFFIXES = {
	"checkbox": "Checkbox",
	"choice": "List",
	"slider": "Slider",
	"spin": "Spin",
	"text": "Edit",
}
_DRIVER_SUFFIXES = {"checkbox": "Checkbox", "choice": "List", "slider": "Slider"}


def panel_specs(specs: Iterable[Any], panel: str) -> tuple[Any, ...]:
	"""The entries shown in panel, in table order."""
	return tuple(spec for spec in specs if panel in spec.panels)


def label_text(spec: Any) -> str:
	"""The label of a control WorldVoice makes: a colon follows it except on a checkbox, as in NVDA."""
	return spec.label if spec.control == "checkbox" else f"{spec.label}:"


def to_display(spec: Any, value: int) -> int:
	return value // spec.panel_scale


def from_display(spec: Any, shown: int) -> int:
	return shown * spec.panel_scale


def choice_values(spec: Any) -> tuple[str, ...]:
	return tuple(value for value, _label in spec.choices)


def choice_index(values: Sequence[str], value: Any) -> int:
	"""The index of value; an unknown or missing value selects the first choice."""
	try:
		return list(values).index(value)
	except ValueError:
		return 0


def selected_value(values: Sequence[str], selection: int) -> str | None:
	"""The value at selection; None for no selection (-1) or one outside the list."""
	if 0 <= selection < len(values):
		return values[selection]
	return None


def controller_keys(specs: Iterable[Any]) -> frozenset[str]:
	"""The keys other entries depend on."""
	return frozenset(spec.depends_on[0] for spec in specs if spec.depends_on is not None)


def dependent_states(specs: Iterable[Any], read: Callable[[str], Any]) -> dict[str, bool]:
	"""Whether each dependent control is enabled, from read(controller key).

	A dependent whose controller reads ABSENT is left out, so its control is not touched. No
	selection (None) never equals an expected value.
	"""
	states = {}
	for spec in specs:
		if spec.depends_on is None:
			continue
		controller, expected = spec.depends_on
		value = read(controller)
		if value is ABSENT:
			continue
		states[spec.key] = value is not None and value == expected
	return states


def creation_followers(
	specs: Sequence[Any],
	listed: Callable[[str], bool],
) -> dict[str | None, tuple[str, ...]]:
	"""The Voice panel entries without a driver setting, by the driver setting they are made right after.

	specs are the Voice panel's entries in table order; listed(driver_id) tells whether the panel makes
	a row for that driver setting. Each entry is made right after the row of the nearest earlier entry
	that has one, so a run of these entries follows, in table order, the listed driver setting before
	the run. Key None holds the entries no listed driver setting comes before.
	"""
	followers: dict[str | None, list[str]] = {}
	anchor = None
	for spec in specs:
		if spec.driver_id is None:
			followers.setdefault(anchor, []).append(spec.key)
		elif listed(spec.driver_id):
			anchor = spec.driver_id
	return {driver_id: tuple(keys) for driver_id, keys in followers.items()}


def pipeline_attribute(spec: Any) -> str:
	"""The Speech Pipeline panel's attribute for the control: _<key>_<suffix>."""
	return f"_{spec.key}_{_PIPELINE_SUFFIXES[spec.control]}"


def voice_attribute(spec: Any) -> str:
	"""The Voice panel's attribute for a control WorldVoice makes: <camelKey><Suffix>."""
	first, *rest = spec.key.split("_")
	return first + "".join(word.capitalize() for word in rest) + _VOICE_SUFFIXES[spec.control]


def driver_attribute(spec: Any) -> str:
	"""The attribute NVDA gives the control it makes for a driver setting."""
	return f"{spec.driver_id}{_DRIVER_SUFFIXES[spec.control]}"
