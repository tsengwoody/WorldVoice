"""Guard checks for the pipeline settings table.

Every panel and the settings ring are built from PIPELINE_SETTINGS, so an entry that lacks a
field a panel needs, or that names a setting the panels cannot follow, breaks a panel only when
it is opened. Each check below returns one message per problem. The real table must pass every
check, and each check must report a table broken on purpose, so the guard itself is tested.
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, load_definitions
from pipeline_harness import load_settings_module

CONTROLS = {"checkbox", "slider", "choice", "spin", "text"}
# The controls a setting of each kind may use; NVDA makes driver controls from the kind.
KIND_CONTROLS = {bool: {"checkbox"}, int: {"slider", "spin"}, str: {"choice", "text"}}
DRIVER_CONTROLS = {"checkbox", "slider", "choice"}
PANELS = {"voice", "pipeline"}
# Words that keep their capital letter inside a sentence-case label.
PROPER_NOUNS = {"Unicode", "Chinese", "WorldVoice"}


@pytest.fixture
def module(monkeypatch):
	return load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})


def check_unique(specs):
	keys = [spec.key for spec in specs]
	driver_ids = [spec.driver_id for spec in specs if spec.driver_id is not None]
	return [f"duplicate key {key}" for key in sorted({k for k in keys if keys.count(k) > 1})] + [
		f"duplicate driver id {id}" for id in sorted({i for i in driver_ids if driver_ids.count(i) > 1})
	]


def check_control_known(specs):
	return [f"{spec.key}: unknown control {spec.control!r}" for spec in specs if spec.control not in CONTROLS]


def check_control_matches_kind(specs):
	return [
		f"{spec.key}: a {spec.kind.__name__} setting cannot use a {spec.control}"
		for spec in specs
		if spec.control in CONTROLS and spec.control not in KIND_CONTROLS.get(spec.kind, set())
	]


def check_placement(specs):
	problems = []
	for spec in specs:
		if spec.driver_id is not None and spec.control not in DRIVER_CONTROLS:
			problems.append(f"{spec.key}: NVDA makes no {spec.control} for a driver setting")
		if spec.driver_id is None and "voice" in spec.panels and not spec.pipeline_config:
			problems.append(f"{spec.key}: a Voice panel control without a driver setting must be stored")
	return problems


def check_labels_and_panels(specs):
	problems = []
	for spec in specs:
		if not isinstance(spec.label, str) or not spec.label:
			problems.append(f"{spec.key}: no label")
		if not spec.panels or not set(spec.panels) <= PANELS:
			problems.append(f"{spec.key}: panels {spec.panels!r}")
		if spec.driver_id is not None and "voice" not in spec.panels:
			problems.append(f"{spec.key}: a driver setting is always in the Voice panel")
	return problems


def check_choices(specs):
	problems = []
	for spec in specs:
		if spec.control == "choice" and "pipeline" in spec.panels and spec.choices is None:
			problems.append(f"{spec.key}: the Speech Pipeline panel needs its choices")
		if spec.choices is None:
			continue
		values = [value for value, _label in spec.choices]
		if len(set(values)) != len(values):
			problems.append(f"{spec.key}: duplicate choice values")
		if spec.default not in values:
			problems.append(f"{spec.key}: the default {spec.default!r} is not a choice")
	return problems


def check_dependencies(specs):
	position = {spec.key: index for index, spec in enumerate(specs)}
	problems = []
	for index, spec in enumerate(specs):
		if spec.depends_on is None:
			continue
		key, expected = spec.depends_on
		if key not in position:
			problems.append(f"{spec.key}: unknown controller {key}")
			continue
		controller = specs[position[key]]
		if controller.depends_on is not None:
			problems.append(f"{spec.key}: the controller {key} depends on another setting")
		if position[key] >= index:
			problems.append(f"{spec.key}: the controller {key} comes later in the table")
		if not set(spec.panels) <= set(controller.panels):
			problems.append(f"{spec.key}: the controller {key} is missing from a panel")
		if controller.control == "checkbox":
			if not isinstance(expected, bool):
				problems.append(f"{spec.key}: a checkbox controller expects a bool")
		elif controller.control == "choice":
			if controller.choices is None or expected not in [value for value, _label in controller.choices]:
				problems.append(f"{spec.key}: {expected!r} is not a choice of {key}")
		else:
			problems.append(f"{spec.key}: a {controller.control} cannot control other settings")
	return problems


def check_scale(specs):
	problems = []
	for spec in specs:
		scale = spec.panel_scale
		if not isinstance(scale, int) or scale < 1:
			problems.append(f"{spec.key}: panel_scale {scale!r}")
		elif scale != 1 and spec.control != "slider":
			problems.append(f"{spec.key}: only a slider is scaled")
		elif scale != 1 and any(value % scale for value in (spec.min_value, spec.max_value, spec.default)):
			problems.append(f"{spec.key}: bounds and default are not multiples of {scale}")
	return problems


def check_voice_anchor(specs):
	voice = [spec for spec in specs if "voice" in spec.panels]
	if voice and voice[0].driver_id is None:
		return [f"{voice[0].key}: the first Voice panel entry has no driver row to follow"]
	return []


def check_sentence_case(specs):
	problems = []
	for spec in specs:
		for text in (spec.label, spec.display_name):
			if not text:
				continue
			first, *rest = text.replace("&", "").split()
			if not first[0].isupper():
				problems.append(f"{spec.key}: {text!r} does not start with a capital")
			problems.extend(
				f"{spec.key}: {text!r} capitalises {word!r}"
				for word in rest
				if word[0].isupper() and word not in PROPER_NOUNS
			)
	return problems


def check_ordering_only(specs):
	controllers = {spec.depends_on[0] for spec in specs if spec.depends_on is not None}
	problems = []
	for spec in specs:
		if spec.pipeline_config:
			continue
		if spec.driver_id is None:
			problems.append(f"{spec.key}: an ordering-only entry needs the driver setting NVDA stores")
		if "pipeline" in spec.panels:
			problems.append(f"{spec.key}: the Speech Pipeline panel has nothing to store it in")
		if spec.key in controllers:
			problems.append(f"{spec.key}: an ordering-only entry cannot control other settings")
	return problems


CHECKS = [
	check_unique,
	check_control_known,
	check_control_matches_kind,
	check_placement,
	check_labels_and_panels,
	check_choices,
	check_dependencies,
	check_scale,
	check_voice_anchor,
	check_sentence_case,
	check_ordering_only,
]


@pytest.mark.parametrize("check", CHECKS, ids=lambda check: check.__name__)
def test_the_table_passes_every_check(module, check):
	assert check(module.PIPELINE_SETTINGS) == []


def _with(module, key, **changes):
	"""The real table with the entry for key changed."""
	return tuple(replace(spec, **changes) if spec.key == key else spec for spec in module.PIPELINE_SETTINGS)


def _first(module, key):
	"""The real table with the entry for key moved to the front."""
	spec = module.PIPELINE_SETTING_BY_KEY[key]
	return (spec, *(other for other in module.PIPELINE_SETTINGS if other.key != key))


BROKEN = {
	"duplicate key": (
		check_unique,
		lambda m: (*m.PIPELINE_SETTINGS, m.PIPELINE_SETTING_BY_KEY["group_size"]),
	),
	"duplicate driver id": (
		check_unique,
		lambda m: _with(m, "number_wait_factor", driver_id="itemwaitfactor"),
	),
	"no control": (check_control_known, lambda m: _with(m, "group_size", control=None)),
	"bool slider": (
		check_control_matches_kind,
		lambda m: _with(m, "ignore_comma_between_number", control="slider"),
	),
	"driver spin": (check_placement, lambda m: _with(m, "number_wait_factor", control="spin")),
	"unstored voice control": (check_placement, lambda m: _with(m, "group_size", pipeline_config=False)),
	"empty label": (check_labels_and_panels, lambda m: _with(m, "group_size", label="")),
	"unknown panel": (check_labels_and_panels, lambda m: _with(m, "group_size", panels=("other",))),
	"driver outside the Voice panel": (
		check_labels_and_panels,
		lambda m: _with(m, "number_wait_factor", panels=("pipeline",)),
	),
	"choice without choices": (check_choices, lambda m: _with(m, "scope", choices=None)),
	"duplicate choice": (check_choices, lambda m: _with(m, "scope", choices=(("all", "A"), ("all", "B")))),
	"default not a choice": (check_choices, lambda m: _with(m, "scope", default="nowhere")),
	"unknown controller": (
		check_dependencies,
		lambda m: _with(m, "group_size", depends_on=("nothing", "group")),
	),
	"controller depends": (
		check_dependencies,
		lambda m: _with(m, "number_mode", depends_on=("ignore_comma_between_number", True)),
	),
	"controller later": (
		check_dependencies,
		lambda m: _with(m, "group_size", depends_on=("punctuation_pause_enabled", True)),
	),
	"controller missing from a panel": (
		check_dependencies,
		lambda m: _with(m, "number_mode", panels=("voice",)),
	),
	"slider controller": (
		check_dependencies,
		lambda m: _with(m, "group_size", depends_on=("global_wait_factor", 10)),
	),
	"checkbox expects a string": (
		check_dependencies,
		lambda m: _with(m, "punctuation_wait_factor", depends_on=("punctuation_pause_enabled", "yes")),
	),
	"choice expects an unknown value": (
		check_dependencies,
		lambda m: _with(m, "group_size", depends_on=("number_mode", "pair")),
	),
	"zero scale": (check_scale, lambda m: _with(m, "global_wait_factor", panel_scale=0)),
	"scaled checkbox": (check_scale, lambda m: _with(m, "ignore_comma_between_number", panel_scale=10)),
	"bound off the scale": (check_scale, lambda m: _with(m, "global_wait_factor", max_value=95)),
	"first voice entry without a row": (check_voice_anchor, lambda m: _first(m, "group_size")),
	"capital inside a label": (check_sentence_case, lambda m: _with(m, "number_mode", label="Number &Mode")),
	"lower-case ring name": (
		check_sentence_case,
		lambda m: _with(m, "number_mode", display_name="number mode"),
	),
	"ordering-only without a driver setting": (
		check_ordering_only,
		lambda m: _with(m, "number_language", driver_id=None),
	),
	"ordering-only in the Speech Pipeline panel": (
		check_ordering_only,
		lambda m: _with(m, "number_language", panels=("voice", "pipeline")),
	),
	"ordering-only controller": (
		check_ordering_only,
		lambda m: _with(m, "group_size", depends_on=("number_language", "default")),
	),
}


@pytest.mark.parametrize(("check", "make_broken"), BROKEN.values(), ids=BROKEN.keys())
def test_each_check_reports_a_broken_table(module, check, make_broken):
	assert check(make_broken(module)) != []


def test_driver_choices_match_the_driver_options(module):
	# The Voice panel shows NVDA's list from available<Id>s; it must list the table's choices.
	driver = load_definitions(
		WORLDVOICE / "__init__.py",
		["SynthDriver"],
		{
			"_": lambda text: text,
			"NUMBER_MODE_CHOICES": module.NUMBER_MODE_CHOICES,
			"StringParameterInfo": lambda id, name: SimpleNamespace(id=id, name=name),
		},
		members=("_get_availableNummods",),
	)["SynthDriver"]()
	driver_choices = [spec for spec in module.PIPELINE_SETTINGS if spec.driver_id and spec.choices]
	assert [spec.driver_id for spec in driver_choices] == ["nummod"]
	for spec in driver_choices:
		options = getattr(driver, f"_get_available{spec.driver_id.capitalize()}s")()
		assert [(key, info.id, info.name) for key, info in options.items()] == [
			(value, value, label) for value, label in spec.choices
		]
