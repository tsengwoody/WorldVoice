"""One builder makes, reads and locates every pipeline control both settings panels show.

The real ui/controls.py runs against ui_harness's fake wx, with specs from the real table.
"""

import sys
from dataclasses import replace

import pytest
from ui_harness import (
	BoxSizerHelper,
	CheckBox,
	Choice,
	SelectOnFocusSpinCtrl,
	SettingsPanel,
	Sizer,
	Slider,
	TextCtrl,
	load_pipeline_controls,
	make_panel,
)


def build(monkeypatch, key, value, **changes):
	env = load_pipeline_controls(monkeypatch)
	spec = replace(env.settings.PIPELINE_SETTING_BY_KEY[key], **changes)
	sizer = Sizer()
	env.parent = parent = make_panel(SettingsPanel)
	control = env.controls.make_control(parent, BoxSizerHelper(parent, sizer=sizer), spec, value)
	return env, spec, sizer, control


def test_a_checkbox_is_added_as_itself_with_its_value(monkeypatch):
	env, _spec, sizer, control = build(monkeypatch, "punctuation_pause_enabled", False)
	assert type(control) is CheckBox
	assert (control.label, control.value) == ("Enable punctuation pause control", False)
	assert sizer.items[0].GetWindow() is control
	# A checkbox is made by the builder itself, so it must be the panel's child like the others.
	assert control.parent is env.parent


@pytest.mark.parametrize(("stored", "selection"), [("all", 0), ("WorldVoice", 1), ("nowhere", 0)])
def test_a_choice_lists_its_labels_and_selects_the_value(monkeypatch, stored, selection):
	_env, _spec, _sizer, control = build(monkeypatch, "scope", stored)
	assert type(control) is Choice
	assert control.label == "Effect scope:"
	assert control.choices == ["All Synthesizers (Global)", "Only WorldVoice Synthesizer"]
	assert control.selection == selection


@pytest.mark.parametrize(
	("key", "stored", "shown", "maximum", "label"),
	[
		("global_wait_factor", 30, 3, 10, "Global wait factor:"),
		("number_wait_factor", 40, 40, 100, "Number wait factor:"),
	],
)
def test_a_slider_shows_the_scaled_value_and_range(monkeypatch, key, stored, shown, maximum, label):
	env, _spec, _sizer, control = build(monkeypatch, key, stored)
	assert type(control) is Slider
	assert (control.label, control.value) == (label, shown)
	assert (control.kwargs["minValue"], control.kwargs["maxValue"]) == (0, maximum)
	assert control.kwargs["style"] == env.controls.wx.SL_HORIZONTAL


def test_a_spin_uses_nvdas_select_on_focus_control(monkeypatch):
	_env, _spec, _sizer, control = build(monkeypatch, "group_size", 4)
	assert type(control) is SelectOnFocusSpinCtrl
	assert control.label == "Group size:"
	assert (control.GetValue(), control.GetMin(), control.GetMax()) == (4, 2, 10)


def test_a_text_edit_holds_the_value(monkeypatch):
	_env, _spec, _sizer, control = build(monkeypatch, "punctuation_pause_characters", "。，")
	assert type(control) is TextCtrl
	assert (control.label, control.value) == ("Punctuation pause characters:", "。，")


def test_an_unknown_control_kind_is_refused(monkeypatch):
	with pytest.raises(ValueError, match="Unknown control for pipeline setting group_size: 'dial'"):
		build(monkeypatch, "group_size", 3, control="dial")


def _set_value(value):
	return lambda control: control.SetValue(value)


def _select(index):
	return lambda control: control.Select(index)


@pytest.mark.parametrize(
	("key", "stored", "change", "saved"),
	[
		("punctuation_pause_enabled", True, _set_value(False), False),
		("punctuation_pause_characters", "", _set_value(" 。 "), " 。 "),
		("global_wait_factor", 10, _set_value(4), 40),
		("group_size", 3, _set_value(7), 7),
		("scope", "all", _select(1), "WorldVoice"),
		("scope", "all", _select(-1), None),
	],
	ids=["checkbox", "text", "scaled slider", "spin", "choice", "choice without selection"],
)
def test_control_value_reads_what_is_saved(monkeypatch, key, stored, change, saved):
	env, spec, _sizer, control = build(monkeypatch, key, stored)
	change(control)
	assert env.controls.control_value(spec, control) == saved


@pytest.mark.parametrize(
	("key", "stored"),
	[("punctuation_pause_enabled", True), ("global_wait_factor", 10)],
)
def test_control_row_is_the_checkbox_or_its_sizer(monkeypatch, key, stored):
	env, spec, sizer, control = build(monkeypatch, key, stored)
	row = env.controls.control_row(control, spec)
	item = sizer.items[0]
	assert row is (item.GetWindow() if spec.control == "checkbox" else item.GetSizer())
	assert row is (control if spec.control == "checkbox" else control.GetContainingSizer())


def test_change_events_cover_the_controller_kinds(monkeypatch):
	env = load_pipeline_controls(monkeypatch)
	assert env.controls.CHANGE_EVENTS == {"checkbox": "EVT_CHECKBOX", "choice": "EVT_CHOICE"}


class Recorder:
	"""A control that records every call; GetSelection and GetCurrentSelection answer separately."""

	def __init__(self, value=None, selection=None, current=None):
		self.calls = []
		self.results = {"GetValue": value, "GetSelection": selection, "GetCurrentSelection": current}

	def __getattr__(self, name):
		def method(*args):
			self.calls.append((name, *args))
			return self.results.get(name)

		return method


def helpers(monkeypatch):
	env = load_pipeline_controls(monkeypatch)
	env.layout = sys.modules["synthDrivers.WorldVoice.ui.panelLayout"]
	env.spec = lambda key: next(spec for spec in env.settings.PIPELINE_SETTINGS if spec.key == key)
	env.specs = env.layout.panel_specs(env.settings.PIPELINE_SETTINGS, env.layout.PIPELINE_PANEL)
	env.recorders = {spec.key: Recorder() for spec in env.specs}
	return env


def names(calls):
	return [name for name, *_args in calls]


PAUSE_DEPENDENTS = (
	"remove_punctuation_characters",
	"punctuation_wait_factor",
	"punctuation_pause_characters",
)
DEPENDENTS = ("group_size", *PAUSE_DEPENDENTS)


@pytest.mark.parametrize(
	("key", "options"),
	[
		("punctuation_pause_enabled", None),
		("number_mode", None),
		("number_mode", ["none", "value", "number", "group"]),
	],
)
def test_read_control_without_a_control_is_absent(monkeypatch, key, options):
	env = helpers(monkeypatch)
	assert env.controls.read_control(env.spec(key), None, options) is env.layout.ABSENT


@pytest.mark.parametrize("checked", [True, False])
def test_read_control_reads_a_checkbox(monkeypatch, checked):
	env = helpers(monkeypatch)
	control = Recorder(value=checked)
	assert env.controls.read_control(env.spec("punctuation_pause_enabled"), control) is checked
	assert control.calls == [("GetValue",)]


@pytest.mark.parametrize(("current", "value"), [(0, "all"), (1, "WorldVoice"), (-1, None)])
def test_read_control_reads_a_table_choice_by_its_current_selection(monkeypatch, current, value):
	env = helpers(monkeypatch)
	control = Recorder(selection=1 - current, current=current)
	assert env.controls.read_control(env.spec("scope"), control) == value
	assert "GetSelection" not in names(control.calls)


@pytest.mark.parametrize(("selection", "value"), [(2, "c"), (-1, None), (3, None)])
def test_read_control_reads_a_driver_choice_from_its_options(monkeypatch, selection, value):
	# No selection (-1) names no option, although Python's list[-1] is the last one.
	env = helpers(monkeypatch)
	control = Recorder(selection=selection, current=0)
	assert env.controls.read_control(env.spec("number_mode"), control, ["a", "b", "c"]) == value
	assert "GetCurrentSelection" not in names(control.calls)


def test_read_control_ignores_driver_options_for_a_checkbox(monkeypatch):
	env = helpers(monkeypatch)
	control = Recorder(value=False, selection=0, current=0)
	assert env.controls.read_control(env.spec("punctuation_pause_enabled"), control, []) is False
	assert control.calls == [("GetValue",)]


def apply(env, read, missing=()):
	env.controls.apply_dependencies(
		env.specs,
		read,
		lambda spec: None if spec.key in missing else env.recorders[spec.key],
	)


@pytest.mark.parametrize(("mode", "pause", "enabled"), [("group", True, True), ("value", False, False)])
def test_apply_dependencies_enables_dependents_from_their_controller(monkeypatch, mode, pause, enabled):
	env = helpers(monkeypatch)
	apply(env, {"number_mode": mode, "punctuation_pause_enabled": pause}.__getitem__)
	for key in DEPENDENTS:
		assert env.recorders[key].calls == [("Enable", enabled)], key


def test_apply_dependencies_leaves_dependents_of_an_absent_controller_alone(monkeypatch):
	env = helpers(monkeypatch)
	apply(env, lambda key: env.layout.ABSENT)
	assert {key: recorder.calls for key, recorder in env.recorders.items() if recorder.calls} == {}


def test_apply_dependencies_counts_no_selection_as_not_expected(monkeypatch):
	env = helpers(monkeypatch)
	apply(env, {"number_mode": None, "punctuation_pause_enabled": True}.__getitem__)
	assert env.recorders["group_size"].calls == [("Enable", False)]


def test_apply_dependencies_skips_a_dependent_without_a_control(monkeypatch):
	env = helpers(monkeypatch)
	apply(
		env,
		{"number_mode": "group", "punctuation_pause_enabled": True}.__getitem__,
		missing={"group_size"},
	)
	assert env.recorders["group_size"].calls == []
	for key in PAUSE_DEPENDENTS:
		assert env.recorders[key].calls == [("Enable", True)], key


def test_apply_dependencies_only_enables_dependents(monkeypatch):
	# Disabled controls keep their values because nothing but Enable is called on them.
	env = helpers(monkeypatch)
	apply(env, {"number_mode": "group", "punctuation_pause_enabled": True}.__getitem__)
	for key, recorder in env.recorders.items():
		if key in DEPENDENTS:
			assert recorder.calls == [("Enable", True)], key
		else:
			assert recorder.calls == [], key
