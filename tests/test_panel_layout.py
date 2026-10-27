"""The pure layout rules both settings panels follow (ui/panelLayout.py).

The module imports nothing from the add-on, wx or NVDA, so it is loaded once on its own. The
table tests use the real PIPELINE_SETTINGS; the property tests use synthetic tables.
"""

from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, load_source
from hypothesis import given, strategies as st
from pipeline_harness import load_settings_module

layout = load_source(None, "panel_layout_under_test", WORLDVOICE / "ui/panelLayout.py", register=False)

Q1 = [
	"scope",
	"global_wait_factor",
	"number_language",
	"number_mode",
	"group_size",
	"number_wait_factor",
	"item_wait_factor",
	"sayall_wait_factor",
	"unspaced_script_space_wait_factor",
	"punctuation_pause_enabled",
	"remove_punctuation_characters",
	"punctuation_wait_factor",
	"punctuation_pause_characters",
]
PAUSE_DEPENDENTS = (
	"remove_punctuation_characters",
	"punctuation_wait_factor",
	"punctuation_pause_characters",
)


@pytest.fixture
def table(monkeypatch):
	return load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}}).PIPELINE_SETTINGS


def spec_for(table, key):
	(spec,) = [spec for spec in table if spec.key == key]
	return spec


def test_panel_specs_follow_the_table_per_panel(table):
	assert [spec.key for spec in layout.panelSpecs(table, layout.PIPELINE_PANEL)] == [
		key for key in Q1 if key != "number_language"
	]
	assert [spec.key for spec in layout.panelSpecs(table, layout.VOICE_PANEL)] == [
		key for key in Q1 if key != "scope"
	]


@pytest.mark.parametrize(
	("key", "text"),
	[
		("punctuation_pause_enabled", "Enable punctuation pause control"),
		("number_mode", "Number &mode:"),
		("global_wait_factor", "Global wait factor:"),
		("group_size", "Group size:"),
		("punctuation_pause_characters", "Punctuation pause characters:"),
	],
)
def test_label_text(table, key, text):
	assert layout.labelText(spec_for(table, key)) == text


@pytest.mark.parametrize(("scale", "value", "shown"), [(10, 57, 5), (1, 57, 57)])
def test_to_display(scale, value, shown):
	assert layout.toDisplay(SimpleNamespace(panel_scale=scale), value) == shown


@pytest.mark.parametrize(("scale", "shown", "value"), [(10, 5, 50), (1, 5, 5)])
def test_from_display(scale, shown, value):
	assert layout.fromDisplay(SimpleNamespace(panel_scale=scale), shown) == value


@pytest.mark.parametrize(("value", "index"), [("group", 2), ("roman", 0), (None, 0)])
def test_choice_index(value, index):
	assert layout.choiceIndex(("value", "number", "group"), value) == index


@pytest.mark.parametrize(
	("selection", "value"),
	[(0, "value"), (1, "number"), (2, "group"), (-1, None), (3, None), (8, None)],
)
def test_selected_value(selection, value):
	assert layout.selectedValue(("value", "number", "group"), selection) == value


def test_choice_values(table):
	assert layout.choiceValues(spec_for(table, "scope")) == ("all", "WorldVoice")


def test_controller_keys_of_the_table(table):
	assert layout.controllerKeys(table) == frozenset({"number_mode", "punctuation_pause_enabled"})


@pytest.mark.parametrize("mode", ["none", "value", "number", "group", None])
def test_dependent_states_follow_the_number_mode(table, mode):
	read = {"number_mode": mode, "punctuation_pause_enabled": True}.__getitem__
	group = mode == "group"
	assert layout.dependentStates(table, read) == {
		"group_size": group,
		**dict.fromkeys(PAUSE_DEPENDENTS, True),
	}


@pytest.mark.parametrize("switch", [True, False])
def test_dependent_states_follow_the_switch(table, switch):
	read = {"number_mode": "group", "punctuation_pause_enabled": switch}.__getitem__
	states = layout.dependentStates(table, read)
	assert {key: states[key] for key in PAUSE_DEPENDENTS} == dict.fromkeys(PAUSE_DEPENDENTS, switch)


def test_absent_controllers_leave_every_control_alone(table):
	assert layout.dependentStates(table, lambda key: layout.ABSENT) == {}


def voice(table):
	return layout.panelSpecs(table, layout.VOICE_PANEL)


def test_creation_followers_of_the_table(table):
	assert layout.creationFollowers(voice(table), lambda driver_id: True) == {
		"nummod": ("group_size",),
		"punctuationwaitfactor": ("punctuation_pause_characters",),
	}


def test_creation_followers_skip_an_unlisted_driver(table):
	unlisted = {"nummod", "punctuationwaitfactor"}
	assert layout.creationFollowers(voice(table), lambda driver_id: driver_id not in unlisted) == {
		"numlan": ("group_size",),
		"removepunctuationcharacters": ("punctuation_pause_characters",),
	}


def test_creation_followers_chain_in_table_order():
	specs = [
		SimpleNamespace(key="d", driver_id="d"),
		SimpleNamespace(key="a", driver_id=None),
		SimpleNamespace(key="b", driver_id=None),
		SimpleNamespace(key="e", driver_id="e"),
		SimpleNamespace(key="c", driver_id=None),
	]
	assert layout.creationFollowers(specs, lambda driver_id: True) == {"d": ("a", "b"), "e": ("c",)}


def test_creation_followers_without_an_earlier_listed_driver():
	specs = [
		SimpleNamespace(key="a", driver_id=None),
		SimpleNamespace(key="d", driver_id="d"),
		SimpleNamespace(key="b", driver_id=None),
	]
	assert layout.creationFollowers(specs, lambda driver_id: False) == {None: ("a", "b")}


@pytest.mark.parametrize(
	("key", "pipeline", "voice_name", "driver"),
	[
		("number_mode", "_number_mode_choice", "numberModeList", "nummodList"),
		(
			"global_wait_factor",
			"_global_wait_factor_slider",
			"globalWaitFactorSlider",
			"globalwaitfactorSlider",
		),
		(
			"punctuation_pause_enabled",
			"_punctuation_pause_enabled_checkbox",
			"punctuationPauseEnabledCheckbox",
			"punctuationpauseenabledCheckbox",
		),
		("group_size", "_group_size_spin", "groupSizeSpin", None),
		(
			"punctuation_pause_characters",
			"_punctuation_pause_characters_edit",
			"punctuationPauseCharactersEdit",
			None,
		),
	],
)
def test_attribute_names(table, key, pipeline, voice_name, driver):
	spec = spec_for(table, key)
	assert layout.pipelineAttribute(spec) == pipeline
	assert layout.voiceAttribute(spec) == voice_name
	if driver is not None:
		assert layout.driverAttribute(spec) == driver


# Synthetic tables for the property tests.

CONTROLLER_VALUES = [True, False, "a", "b"]


@st.composite
def tables(draw):
	size = draw(st.integers(min_value=1, max_value=8))
	specs = []
	for index in range(size):
		depends_on = None
		if index and draw(st.booleans()):
			depends_on = (f"k{draw(st.integers(0, index - 1))}", draw(st.sampled_from(CONTROLLER_VALUES)))
		specs.append(
			SimpleNamespace(
				key=f"k{index}",
				driver_id=draw(st.sampled_from([None, f"d{index}"])),
				panels=draw(st.sampled_from([("voice",), ("pipeline",), ("voice", "pipeline")])),
				depends_on=depends_on,
			),
		)
	return specs


@given(specs=tables(), data=st.data())
def test_property_absent_controllers_name_no_dependent(specs, data):
	reads = {
		spec.key: data.draw(st.sampled_from([layout.ABSENT, None, *CONTROLLER_VALUES])) for spec in specs
	}
	states = layout.dependentStates(specs, reads.__getitem__)
	for spec in specs:
		if spec.depends_on is None:
			assert spec.key not in states
			continue
		controller, expected = spec.depends_on
		if reads[controller] is layout.ABSENT:
			assert spec.key not in states
		else:
			assert states[spec.key] is (reads[controller] is not None and reads[controller] == expected)


@given(size=st.integers(0, 5), selection=st.integers(-3, 8))
def test_property_selected_value_is_none_exactly_outside_the_list(size, selection):
	values = [f"v{index}" for index in range(size)]
	result = layout.selectedValue(values, selection)
	assert (result is None) is not (0 <= selection < size)
	if result is not None:
		assert result == values[selection]


@given(specs=tables(), data=st.data())
def test_property_each_entry_follows_the_nearest_earlier_listed_driver(specs, data):
	driver_ids = [spec.driver_id for spec in specs if spec.driver_id is not None]
	listed = data.draw(st.sets(st.sampled_from(driver_ids)) if driver_ids else st.just(set()))
	position = {spec.key: index for index, spec in enumerate(specs)}
	followers = layout.creationFollowers(specs, listed.__contains__)
	# Every entry without a driver setting appears once, in table order within its group.
	assert sorted(key for keys in followers.values() for key in keys) == sorted(
		spec.key for spec in specs if spec.driver_id is None
	)
	for driver_id, keys in followers.items():
		assert list(keys) == sorted(keys, key=position.__getitem__)
		for key in keys:
			earlier = [spec.driver_id for spec in specs[: position[key]] if spec.driver_id in listed]
			assert driver_id == (earlier[-1] if earlier else None)
