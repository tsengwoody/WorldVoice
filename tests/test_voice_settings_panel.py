"""NVDA's voice panel under WorldVoice: every control in place, and the pause controls together.

The real VoiceSettingsDialogs.py runs over ui_harness's stand-in for NVDA's VoiceSettingsPanel,
which makes and updates driver controls the way NVDA's AutoSettingsMixin does.
"""

from types import SimpleNamespace

import pytest
from nvda_stubs import worldvoice_conf
from ui_harness import (
	BooleanDriverSetting,
	DriverSetting,
	NumericDriverSetting,
	Sizer,
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
	BooleanDriverSetting("punctuationpauseenabled"),
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
		defaults = {
			"voice": "eva",
			"variant": "v1",
			"rate": 50,
			"rateBoost": False,
			"inflection": 40,
			"_private": False,
			"punctuationpauseenabled": True,
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
	"punctuationpauseenabled",
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
		"punctuationpauseenabled",
		"punctuationwaitfactor",
	]
	assert shown_ids(panel) == [
		"voice",
		"variant",
		"rate",
		"punctuationpauseenabled",
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


@pytest.mark.parametrize("enabled", [True, False])
def test_wait_factor_slider_shows_only_while_pauses_are_enabled(monkeypatch, enabled):
	panel = open_panel(monkeypatch, Driver(ALL, punctuationpauseenabled=enabled)).panel
	assert panel.settingsSizer.IsShown(panel.sizerDict["punctuationwaitfactor"]) is enabled


def test_toggling_pauses_shows_or_hides_the_slider_and_still_saves_the_setting(monkeypatch):
	driver = Driver(ALL, punctuationpauseenabled=True)
	panel = open_panel(monkeypatch, driver).panel
	checkbox, slider = panel.punctuationpauseenabledCheckbox, panel.sizerDict["punctuationwaitfactor"]
	layouts = panel.settingsSizer.layouts

	checkbox.SetValue(False)
	fire(checkbox, "EVT_CHECKBOX")
	assert not panel.settingsSizer.IsShown(slider)
	# WorldVoice's handler skips the event, so NVDA's own handler still writes the setting.
	assert driver.punctuationpauseenabled is False
	assert panel.settingsSizer.layouts > layouts

	checkbox.SetValue(True)
	fire(checkbox, "EVT_CHECKBOX")
	assert panel.settingsSizer.IsShown(slider)
	assert driver.punctuationpauseenabled is True


def test_a_synth_without_pause_settings_gets_the_characters_edit_at_the_end(monkeypatch):
	settings = (DriverSetting("voice"), NumericDriverSetting("rate"))
	driver = Driver({"voice", "rate"}, name="espeak", settings=settings)
	env = open_panel(monkeypatch, driver)
	panel = env.panel

	assert pipeline_snapshot(panel) is None
	assert not hasattr(panel, "punctuationpauseenabledCheckbox")
	assert order(panel) == [
		"voice",
		"rate",
		"Automatic language switching (when supported)",
		"Punctuation pause characters:",
	]
	assert panel.punctuationPauseCharactersEdit.tab_after is None


def test_saving_writes_the_characters_and_keeps_them_after_a_later_cancel(monkeypatch):
	env = open_panel(monkeypatch, Driver(ALL), punctuation_pause_characters=".")
	panel = env.panel
	panel.punctuationPauseCharactersEdit.SetValue(" ,; ")

	panel.onSave()
	panel.onDiscard()

	assert env.conf["WorldVoice"]["pipeline"]["punctuation_pause_characters"] == ",;"
	assert panel.base_calls == ["makeSettings", "onSave", "onDiscard"]


def test_another_synth_saves_the_characters_and_cancel_leaves_pipeline_settings_alone(monkeypatch):
	settings = (DriverSetting("voice"), NumericDriverSetting("rate"))
	env = open_panel(monkeypatch, Driver({"voice", "rate"}, name="espeak", settings=settings))
	panel = env.panel
	panel.punctuationPauseCharactersEdit.SetValue("!?")

	panel.onSave()
	env.pipeline_settings.update(item_wait_factor=90)  # changed elsewhere while the panel is open
	panel.onDiscard()

	pipeline = env.conf["WorldVoice"]["pipeline"]
	assert pipeline["punctuation_pause_characters"] == "!?"
	assert pipeline["item_wait_factor"] == 90
	assert pipeline_snapshot(panel) is None
