"""NVDA's voice panel under WorldVoice: every control in place, and the pause controls together.

The real VoiceSettingsDialogs.py runs over ui_harness's stand-in for NVDA's VoiceSettingsPanel,
which makes and updates driver controls the way NVDA's AutoSettingsMixin does.
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from nvda_stubs import worldvoice_conf
from ui_harness import (
	BooleanDriverSetting,
	DriverSetting,
	NumericDriverSetting,
	Sizer,
	Spacer,
	fire,
	load_voice_settings_dialogs,
	pipeline_snapshot,
)

SETTINGS = (
	DriverSetting("voice"),
	DriverSetting("variant"),
	NumericDriverSetting("rate"),
	BooleanDriverSetting("rateBoost"),
	NumericDriverSetting("inflection"),
	BooleanDriverSetting("_private"),
	DriverSetting("nummod"),
	NumericDriverSetting("groupwaitfactor"),
	BooleanDriverSetting("punctuationpauseenabled"),
	BooleanDriverSetting("removepunctuationcharacters"),
	NumericDriverSetting("punctuationwaitfactor"),
)


class Driver:
	"""A synth exposing every setting it may support and the ones its current voice supports."""

	def __init__(self, supported, name="WorldVoice", settings=SETTINGS, **values):
		self.name = name
		self.allSupportedSettings = list(settings)
		self.supported = set(supported)
		self.availableVoices = {"eva": SimpleNamespace(id="eva", displayName="Eva")}
		self.availableVariants = {"v1": SimpleNamespace(id="v1", displayName="Variant 1")}
		self.availableNummods = {
			mode: SimpleNamespace(id=mode, displayName=mode) for mode in ("value", "number", "group")
		}
		defaults = {
			"voice": "eva",
			"variant": "v1",
			"rate": 50,
			"rateBoost": False,
			"inflection": 40,
			"_private": False,
			"nummod": "value",
			"groupwaitfactor": 0,
			"punctuationpauseenabled": True,
			"removepunctuationcharacters": False,
			"punctuationwaitfactor": 20,
		}
		for key, value in {**defaults, **values}.items():
			setattr(self, key, value)

	@property
	def supportedSettings(self):
		return [setting for setting in self.allSupportedSettings if setting.id in self.supported]

	def isSupported(self, name):
		return name in self.supported


ALL = {
	"voice",
	"variant",
	"rate",
	"rateBoost",
	"inflection",
	"nummod",
	"groupwaitfactor",
	"punctuationpauseenabled",
	"removepunctuationcharacters",
	"punctuationwaitfactor",
}


def open_panel(monkeypatch, driver, **pipeline):
	env = load_voice_settings_dialogs(monkeypatch, conf=worldvoice_conf(pipeline=pipeline))
	panel = env.module.WorldVoiceVoiceSettingsPanel(driver)
	panel.makeSettings(panel.settingsSizer)
	env.panel = panel
	return env


def shown_ids(panel):
	return [name for name, sizer in panel.sizerDict.items() if panel.settingsSizer.IsShown(sizer)]


def order(panel):
	"""The panel's top-level items, named by driver setting id or control label."""
	names = {id(sizer): name for name, sizer in panel.sizerDict.items()}
	result = []
	for entry in panel.settingsSizer.items:
		if id(entry.item) in names:
			result.append(names[id(entry.item)])
		elif isinstance(entry.item, Spacer):
			result.append("<spacer>")
		else:
			(control,) = entry.item.controls() if isinstance(entry.item, Sizer) else [entry.item]
			result.append(control.label)
	return result


def test_every_setting_gets_a_control_in_standard_order_and_unsupported_ones_are_hidden(monkeypatch):
	env = open_panel(monkeypatch, Driver(ALL - {"rateBoost", "inflection"}))
	panel = env.panel

	assert list(panel.sizerDict) == [
		"voice",
		"variant",
		"rate",
		"rateBoost",
		"inflection",
		"nummod",
		"groupwaitfactor",
		"punctuationpauseenabled",
		"removepunctuationcharacters",
		"punctuationwaitfactor",
	]
	assert shown_ids(panel) == [
		"voice",
		"variant",
		"rate",
		"nummod",
		"groupwaitfactor",
		"punctuationpauseenabled",
		"removepunctuationcharacters",
		"punctuationwaitfactor",
	]
	assert panel.base_calls == ["makeSettings"]


def test_a_voice_switch_shows_its_controls_in_place(monkeypatch):
	driver = Driver(ALL - {"rateBoost", "inflection"})
	panel = open_panel(monkeypatch, driver).panel
	driver.supported = set(ALL)
	driver.inflection = 70

	panel.updateDriverSettings(changedSetting="voice")  # what NVDA runs after the voice changed

	assert shown_ids(panel) == list(panel.sizerDict)
	assert order(panel)[:5] == ["voice", "variant", "rate", "rateBoost", "inflection"]
	assert panel.inflectionSlider.value == 70


def test_a_voice_switch_reloads_the_new_voices_variants(monkeypatch):
	driver = Driver(ALL)
	panel = open_panel(monkeypatch, driver).panel
	driver.availableVariants = {
		"a": SimpleNamespace(id="a", displayName="Alto"),
		"b": SimpleNamespace(id="b", displayName="Bass"),
	}
	driver.variant = "b"

	panel.updateDriverSettings(changedSetting="voice")

	assert panel.variantList.choices == ["Alto", "Bass"]
	assert panel.variantList.selection == 1
	assert [option.id for option in panel._variants] == ["a", "b"]


def test_a_variant_the_new_list_lacks_leaves_no_selection(monkeypatch):
	driver = Driver(ALL)
	panel = open_panel(monkeypatch, driver).panel
	driver.availableVariants = {"a": SimpleNamespace(id="a", displayName="Alto")}
	driver.variant = "gone"

	panel.updateDriverSettings(changedSetting="voice")

	assert panel.variantList.choices == ["Alto"]
	assert panel.variantList.selection == -1


def test_rebuilding_the_driver_controls_updates_values_except_the_changed_setting(monkeypatch):
	driver = Driver(ALL)
	panel = open_panel(monkeypatch, driver).panel
	driver.supported = ALL - {"rateBoost"}
	driver.rate, driver.punctuationpauseenabled = 80, False
	panel.rateBoostCheckbox.SetValue("untouched")

	panel.createDriverSettings(changedSetting="rateBoost")

	assert panel.rateSlider.value == 80
	assert panel.punctuationpauseenabledCheckbox.value is False
	# The setting being changed keeps its control and value even though it is now unsupported.
	assert panel.settingsSizer.IsShown(panel.sizerDict["rateBoost"])
	assert panel.rateBoostCheckbox.value == "untouched"


def test_punctuation_characters_follow_the_wait_factor_slider(monkeypatch):
	env = open_panel(monkeypatch, Driver(ALL), punctuation_pause_characters="。！")
	panel = env.panel

	edit = panel.punctuationPauseCharactersEdit
	assert edit.label == "Punctuation pause characters:"
	assert edit.value == "。！"
	names = order(panel)
	assert names.index("Punctuation pause characters:") == names.index("punctuationwaitfactor") + 1
	# NVDA's own controls stay after the driver controls.
	assert names[-1] == "Automatic language switching (when supported)"
	assert edit.tab_after is panel.punctuationwaitfactorSlider
	assert names.index("Group size:") == names.index("nummod") + 1
	# Each added control has its own helper, so moving its row leaves no spacer behind.
	assert "<spacer>" not in names


def test_group_size_follows_the_number_mode_list(monkeypatch):
	env = open_panel(monkeypatch, Driver(ALL), group_size=5)
	panel = env.panel

	spin = panel.groupSizeSpin
	# NVDA's select-on-focus spin control, as its own Voice panel uses, not a plain wx.SpinCtrl.
	assert type(spin) is env.gui.nvdaControls.SelectOnFocusSpinCtrl is not env.wx.SpinCtrl
	names = order(panel)
	assert names.index("Group size:") == names.index("nummod") + 1
	assert spin.tab_after is panel.nummodList
	assert (spin.label, spin.GetValue(), spin.GetMin(), spin.GetMax()) == ("Group size:", 5, 1, 10)


def pause_controls_enabled(panel):
	return (
		panel.removepunctuationcharactersCheckbox.enabled,
		panel.punctuationwaitfactorSlider.enabled,
		panel.punctuationPauseCharactersEdit.enabled,
	)


@pytest.mark.parametrize("enabled", [True, False])
def test_pause_controls_are_enabled_only_while_pauses_are_enabled(monkeypatch, enabled):
	panel = open_panel(monkeypatch, Driver(ALL, punctuationpauseenabled=enabled)).panel
	assert pause_controls_enabled(panel) == (enabled, enabled, enabled)
	# Disabled, not hidden.
	assert panel.settingsSizer.IsShown(panel.sizerDict["punctuationwaitfactor"])


def test_toggling_pauses_enables_or_disables_the_controls_and_still_saves_the_setting(monkeypatch):
	driver = Driver(ALL, punctuationpauseenabled=True)
	panel = open_panel(monkeypatch, driver).panel
	checkbox = panel.punctuationpauseenabledCheckbox

	checkbox.SetValue(False)
	fire(checkbox, "EVT_CHECKBOX")
	assert pause_controls_enabled(panel) == (False, False, False)
	assert panel.settingsSizer.IsShown(panel.sizerDict["punctuationwaitfactor"])
	# WorldVoice's handler skips the event, so NVDA's own handler still writes the setting.
	assert driver.punctuationpauseenabled is False

	checkbox.SetValue(True)
	fire(checkbox, "EVT_CHECKBOX")
	assert pause_controls_enabled(panel) == (True, True, True)
	assert driver.punctuationpauseenabled is True


def test_a_voice_switch_keeps_the_pause_controls_disabled(monkeypatch):
	panel = open_panel(monkeypatch, Driver(ALL, punctuationpauseenabled=False)).panel

	panel.updateDriverSettings(changedSetting="voice")  # shows every supported control again

	assert pause_controls_enabled(panel) == (False, False, False)
	assert panel.settingsSizer.IsShown(panel.sizerDict["punctuationwaitfactor"])


@pytest.mark.parametrize("enabled", [True, False])
def test_a_voice_switch_after_a_settings_ring_toggle_matches_the_controls_to_the_switch(monkeypatch, enabled):
	driver = Driver(ALL, punctuationpauseenabled=not enabled)
	panel = open_panel(monkeypatch, driver).panel
	driver.punctuationpauseenabled = enabled  # toggled with the settings ring while the dialog is open

	# SetValue on the switch fires no EVT_CHECKBOX, so the panel must apply the state itself.
	panel.updateDriverSettings(changedSetting="voice")

	assert panel.punctuationpauseenabledCheckbox.value is enabled
	assert pause_controls_enabled(panel) == (enabled, enabled, enabled)


def group_controls_enabled(panel):
	return (panel.groupSizeSpin.enabled, panel.groupwaitfactorSlider.enabled)


@pytest.mark.parametrize(("mode", "enabled"), [("value", False), ("number", False), ("group", True)])
def test_group_controls_follow_the_stored_mode_when_the_panel_opens(monkeypatch, mode, enabled):
	panel = open_panel(monkeypatch, Driver(ALL, nummod=mode)).panel
	assert group_controls_enabled(panel) == (enabled, enabled)
	# Disabled, not hidden.
	assert panel.settingsSizer.IsShown(panel.sizerDict["groupwaitfactor"])


def test_choosing_a_mode_updates_the_group_controls_and_still_saves_the_setting(monkeypatch):
	driver = Driver(ALL, nummod="value")
	panel = open_panel(monkeypatch, driver).panel
	choice = panel.nummodList

	choice.Select(2)
	fire(choice, "EVT_CHOICE")
	assert group_controls_enabled(panel) == (True, True)
	# WorldVoice's handler skips the event, so NVDA's own handler still writes the setting.
	assert driver.nummod == "group"

	choice.Select(0)
	fire(choice, "EVT_CHOICE")
	assert group_controls_enabled(panel) == (False, False)
	assert driver.nummod == "value"


@pytest.mark.parametrize("mode", ["group", "value"])
def test_a_voice_switch_after_a_settings_ring_mode_change_matches_the_group_controls(monkeypatch, mode):
	driver = Driver(ALL, nummod="value" if mode == "group" else "group")
	panel = open_panel(monkeypatch, driver).panel
	driver.nummod = mode  # changed with the settings ring while the dialog is open

	# SetSelection on the list fires no EVT_CHOICE, so the panel must apply the state itself.
	panel.updateDriverSettings(changedSetting="voice")

	assert panel.nummodList.selection == ["value", "number", "group"].index(mode)
	enabled = mode == "group"
	assert group_controls_enabled(panel) == (enabled, enabled)


def test_a_mode_missing_from_the_list_counts_as_not_group(monkeypatch):
	# _nummods[-1] is the group entry: a list with no selection must not enable the group controls.
	driver = Driver(ALL, nummod="group")
	panel = open_panel(monkeypatch, driver).panel
	driver.nummod = "gone"

	panel.updateDriverSettings(changedSetting="voice")

	assert panel.nummodList.selection == -1
	assert group_controls_enabled(panel) == (False, False)


OTHER_SETTINGS = (DriverSetting("voice"), NumericDriverSetting("rate"))


def other_synth():
	return Driver({"voice", "rate"}, name="espeak", settings=OTHER_SETTINGS)


def test_another_synth_gets_no_worldvoice_controls(monkeypatch):
	# Decided by the user (2026-10-21): the Speech Pipeline panel is where they are changed then.
	panel = open_panel(monkeypatch, other_synth()).panel

	assert pipeline_snapshot(panel) is None
	assert not hasattr(panel, "punctuationpauseenabledCheckbox")
	assert order(panel) == ["voice", "rate", "Automatic language switching (when supported)"]
	assert panel.groupSizeSpin is None
	assert panel.punctuationPauseCharactersEdit is None


def table_with(env, *entries):
	"""A table of real entries, each (key, changes), so pipeline_settings.get() has every key."""
	by_key = env.settings.PIPELINE_SETTING_BY_KEY
	return tuple(replace(by_key[key], **changes) for key, changes in entries)


def test_a_control_after_a_checkbox_row_lands_after_the_checkbox(monkeypatch):
	settings = (DriverSetting("voice"), BooleanDriverSetting("cni"))
	env = load_voice_settings_dialogs(monkeypatch, conf=worldvoice_conf())
	env.module.PIPELINE_SETTINGS = table_with(
		env,
		("ignore_comma_between_number", {}),
		("punctuation_pause_characters", {"depends_on": None}),
	)
	panel = env.module.WorldVoiceVoiceSettingsPanel(Driver({"voice", "cni"}, settings=settings, cni=False))
	panel.makeSettings(panel.settingsSizer)

	names = order(panel)
	# NVDA adds a checkbox row as the checkbox window itself, not in a sizer.
	assert names.index("Punctuation pause characters:") == names.index("cni") + 1
	assert panel.punctuationPauseCharactersEdit.tab_after is panel.cniCheckbox
	assert "<spacer>" not in names


def test_adjacent_non_driver_controls_keep_table_order(monkeypatch):
	settings = (DriverSetting("voice"), DriverSetting("nummod"))
	env = load_voice_settings_dialogs(monkeypatch, conf=worldvoice_conf())
	env.module.PIPELINE_SETTINGS = table_with(
		env,
		("number_mode", {}),
		("group_size", {"depends_on": None}),
		("punctuation_pause_characters", {"depends_on": None}),
	)
	panel = env.module.WorldVoiceVoiceSettingsPanel(Driver({"voice", "nummod"}, settings=settings))
	panel.makeSettings(panel.settingsSizer)

	names = order(panel)
	start = names.index("nummod")
	assert names[start : start + 3] == ["nummod", "Group size:", "Punctuation pause characters:"]
	assert panel.groupSizeSpin.tab_after is panel.nummodList
	assert panel.punctuationPauseCharactersEdit.tab_after is panel.groupSizeSpin
	assert "<spacer>" not in names


def test_a_rebuild_for_worldvoice_places_the_controls_again(monkeypatch):
	panel = open_panel(monkeypatch, other_synth()).panel
	panel._driver = Driver(ALL)  # the user chose WorldVoice; NVDA rebuilds the panel

	panel.refreshGui()

	names = order(panel)
	assert names.index("Group size:") == names.index("nummod") + 1
	assert names.index("Punctuation pause characters:") == names.index("punctuationwaitfactor") + 1
	assert panel.groupSizeSpin in panel.settingsSizer.controls()
	assert not panel.groupSizeSpin.destroyed


def test_a_rebuild_for_another_synth_drops_the_worldvoice_controls(monkeypatch):
	env = open_panel(monkeypatch, Driver(ALL))
	panel = env.panel
	spin, edit = panel.groupSizeSpin, panel.punctuationPauseCharactersEdit
	spin.SetValue(7)
	panel._driver = other_synth()

	panel.refreshGui()
	panel.onSave()

	assert order(panel) == ["voice", "rate", "Automatic language switching (when supported)"]
	assert (panel.groupSizeSpin, panel.punctuationPauseCharactersEdit) == (None, None)
	assert spin.destroyed and edit.destroyed
	pipeline = env.conf["WorldVoice"]["pipeline"]
	assert (pipeline["group_size"], pipeline["punctuation_pause_characters"]) == (3, "")
	assert panel.base_calls[-1] == "onSave"


def test_saving_after_the_synth_changed_writes_no_pipeline_setting(monkeypatch):
	# The panel may be saved before NVDA rebuilds it for the new synth.
	env = open_panel(monkeypatch, Driver(ALL))
	panel = env.panel
	panel.groupSizeSpin.SetValue(7)
	panel._driver = other_synth()

	panel.onSave()

	assert env.conf["WorldVoice"]["pipeline"]["group_size"] == 3
	assert panel.base_calls[-1] == "onSave"


def test_saving_writes_the_characters_and_keeps_them_after_a_later_cancel(monkeypatch):
	env = open_panel(monkeypatch, Driver(ALL), punctuation_pause_characters=".")
	panel = env.panel
	panel.punctuationPauseCharactersEdit.SetValue(" ,; ")

	panel.onSave()
	panel.onDiscard()

	assert env.conf["WorldVoice"]["pipeline"]["punctuation_pause_characters"] == ",;"
	assert panel.base_calls == ["makeSettings", "onSave", "onDiscard"]


def test_saving_writes_the_group_size_and_keeps_it_after_a_later_cancel(monkeypatch):
	env = open_panel(monkeypatch, Driver(ALL), group_size=3)
	panel = env.panel
	panel.groupSizeSpin.SetValue(7)

	panel.onSave()
	panel.onDiscard()

	assert env.conf["WorldVoice"]["pipeline"]["group_size"] == 7


def test_cancel_without_save_keeps_the_stored_group_size(monkeypatch):
	env = open_panel(monkeypatch, Driver(ALL), group_size=4)
	panel = env.panel
	panel.groupSizeSpin.SetValue(9)

	panel.onDiscard()

	assert env.conf["WorldVoice"]["pipeline"]["group_size"] == 4


def test_another_synth_saves_and_cancels_without_touching_pipeline_settings(monkeypatch):
	env = open_panel(monkeypatch, other_synth())
	panel = env.panel

	panel.onSave()
	env.pipeline_settings.update(item_wait_factor=90)  # changed elsewhere while the panel is open
	panel.onDiscard()

	pipeline = env.conf["WorldVoice"]["pipeline"]
	assert (pipeline["punctuation_pause_characters"], pipeline["group_size"]) == ("", 3)
	assert pipeline["item_wait_factor"] == 90
	assert pipeline_snapshot(panel) is None
	assert panel.base_calls == ["makeSettings", "onSave", "onDiscard"]


def test_a_non_driver_checkbox_controls_its_dependent(monkeypatch):
	settings = (DriverSetting("voice"), BooleanDriverSetting("cni"))
	env = load_voice_settings_dialogs(
		monkeypatch,
		conf=worldvoice_conf(pipeline={"remove_punctuation_characters": False}),
	)
	env.module.PIPELINE_SETTINGS = table_with(
		env,
		("ignore_comma_between_number", {}),
		("remove_punctuation_characters", {"driver_id": None, "depends_on": None}),
		("punctuation_pause_characters", {"depends_on": ("remove_punctuation_characters", True)}),
	)
	panel = env.module.WorldVoiceVoiceSettingsPanel(Driver({"voice", "cni"}, settings=settings, cni=False))
	panel.makeSettings(panel.settingsSizer)
	checkbox, edit = panel.removePunctuationCharactersCheckbox, panel.punctuationPauseCharactersEdit
	assert edit.enabled is False

	checkbox.SetValue(True)
	event = fire(checkbox, "EVT_CHECKBOX")

	assert edit.enabled is True
	assert event.skipped


def test_the_named_rule_and_placement_helpers_are_gone(monkeypatch):
	panel_class = load_voice_settings_dialogs(monkeypatch).module.WorldVoiceVoiceSettingsPanel
	for name in (
		"_bindNumberModeChoice",
		"_onNumberModeChoice",
		"_applyGroupControlsState",
		"_bindPunctuationPauseEnabledToggle",
		"_onPunctuationPauseEnabledToggle",
		"_applyPunctuationPauseControlsState",
		"_addGroupSizeControl",
		"_addPunctuationPauseCharactersControl",
	):
		assert not hasattr(panel_class, name), name


def test_saving_strips_unicode_whitespace_from_the_characters(monkeypatch):
	# U+3000 (ideographic space) and U+00A0 (no-break space) are typed from CJK and other layouts.
	env = open_panel(monkeypatch, Driver(ALL))
	env.panel.punctuationPauseCharactersEdit.SetValue("　。 ！　")

	env.panel.onSave()

	assert env.conf["WorldVoice"]["pipeline"]["punctuation_pause_characters"] == "。 ！"
