"""One builder makes, reads and locates every pipeline control both settings panels show.

The real pipelineControls.py runs against ui_harness's fake wx, with specs from the real table.
"""

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
	_env, _spec, _sizer, control = build(monkeypatch, key, stored)
	assert type(control) is Slider
	assert (control.label, control.value) == (label, shown)
	assert (control.kwargs["minValue"], control.kwargs["maxValue"]) == (0, maximum)


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
