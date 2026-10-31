"""The speech role panel shows each locale's voice and hands the user's edits to its presenter.

The real makeSettings and event handlers run against the fake wx in ui_harness; a recording
presenter stands in for RolePanelPresenter, which has its own tests.
"""

from types import SimpleNamespace

import pytest
from ui_harness import Sizer, TextCtrl, fire, load_settings_dialog, make_panel

VOICES = {
	"en": [("eva", "Eva (OneCore)"), ("tom", "Tom (SAPI5)")],
	"zh": [("mei", "Mei (VE)")],
}


class Presenter:
	def __init__(self, manager, *, speechSection, setMainVoice):
		self.manager = manager
		self.setMainVoice = setMainVoice
		self.calls = []
		self.keepEngine, self.keepVoice, self.keepParameters = True, False, True
		self.assigned = {"en": "tom"}
		self.locale_names = [("en", "English"), ("zh", "Chinese")]
		self.instances = {
			"eva": SimpleNamespace(
				rate=10,
				pitch=20,
				volume=30,
				inflection=40,
				rateBoost=False,
				variant="v1",
			),
			"tom": SimpleNamespace(rate=60, pitch=61, volume=62, inflection=63, rateBoost=True, variant="v2"),
			"mei": SimpleNamespace(rate=1, pitch=2, volume=3, inflection=4, rateBoost=False, variant="gone"),
		}
		self.supported = {"eva": {"inflection", "rateBoost"}, "tom": set(), "mei": set()}

	def locales(self):
		return list(self.locale_names)

	def voices(self, locale):
		return VOICES.get(locale, [])

	def selectedVoice(self, locale):
		return self.assigned.get(locale, "")

	def voice(self, name):
		return self.instances[name]

	def variants(self, name):
		return ["v1", "v2"]

	def capabilities(self, name):
		return self.supported[name]

	# RolePanelPresenter's edits and transaction: recorded, so the tests see what the panel called.
	RECORDED = frozenset(
		{
			"selectVoice",
			"setParameter",
			"setVariant",
			"setEngineConsistency",
			"setVoiceConsistency",
			"setParameterConsistency",
			"discard",
			"close",
			"apply",
		},
	)

	def __getattr__(self, name):
		if name in self.RECORDED:
			return lambda *args: self.calls.append((name, *args))
		raise AttributeError(name)


@pytest.fixture
def ui(monkeypatch):
	manager = SimpleNamespace(name="manager")
	synth = SimpleNamespace(name="WorldVoice", voiceManager=manager)
	env = load_settings_dialog(monkeypatch, synth=synth)
	monkeypatch.setattr(env.panels.role, "RolePanelPresenter", Presenter)
	panel = make_panel(env.module.SpeechRoleSettingsPanel)
	sizer = Sizer()
	panel.makeSettings(sizer)
	panel.postInit()
	return SimpleNamespace(env=env, panel=panel, sizer=sizer, presenter=panel._presenter, synth=synth)


def choose(panel, choice, index):
	choice.Select(index)
	fire(choice, "EVT_CHOICE", panel=panel)


def sliders(panel):
	return [panel._rateSlider, panel._pitchSlider, panel._volumeSlider, panel._inflectionSlider]


def test_panel_for_another_synth_only_says_so(monkeypatch):
	env = load_settings_dialog(monkeypatch, synth=SimpleNamespace(name="espeak"))
	panel = make_panel(env.module.SpeechRoleSettingsPanel)
	sizer = Sizer()

	panel.makeSettings(sizer)
	panel.postInit()
	panel.onDiscard()
	panel.onSave()

	(info,) = sizer.contents()
	assert isinstance(info, TextCtrl)
	assert info.value == "Your current speech synthesizer is not WorldVoice."
	assert panel.disable is True
	assert env.shown == []


def test_setting_the_main_voice_goes_through_nvdas_change_voice(ui):
	# changeVoice also rebuilds the settings ring and loads the voice dictionary (spec §3.6).
	ui.presenter.setMainVoice("eva")
	assert ui.env.voice_changes == [(ui.synth, "eva")]
	assert ui.env.conf["speech"]["WorldVoice"]["voice"] == "eva"


def test_setting_the_main_voice_without_worldvoice_only_writes_the_config(ui):
	ui.env.current[0] = SimpleNamespace(name="espeak")
	ui.presenter.setMainVoice("eva")
	assert ui.env.voice_changes == []
	assert ui.env.conf["speech"]["WorldVoice"]["voice"] == "eva"


def test_opened_panel_shows_locales_and_consistency_flags_with_no_voice_yet(ui):
	panel, presenter = ui.panel, ui.presenter
	assert presenter.manager is ui.synth.voiceManager
	assert panel._localesChoice.choices == ["English", "Chinese"]
	assert panel._localesChoice.focused is True
	# No locale chosen yet: nothing to edit.
	assert panel._voicesChoice.choices == []
	assert not any(slider.enabled for slider in sliders(ui.panel))
	assert panel._rateBoostCheckBox.enabled is False
	assert (
		panel._keepEngineConsistentCheckBox.value,
		panel._keepConsistentCheckBox.value,
		panel._keepParameterConsistentCheckBox.value,
	) == (True, False, True)


def test_choosing_a_locale_shows_its_assigned_voice_and_parameters(ui):
	panel = ui.panel
	choose(panel, panel._localesChoice, 0)

	assert panel._voicesChoice.choices == ["no-select", "Eva (OneCore)", "Tom (SAPI5)"]
	assert panel._voicesChoice.selection == 2
	assert [slider.value for slider in sliders(panel)] == [60, 61, 62, 63]
	assert panel._rateBoostCheckBox.value is True
	assert panel._variantsChoice.choices == ["v1", "v2"]
	assert panel._variantsChoice.selection == 1
	# Tom supports neither inflection nor rate boost.
	assert [slider.enabled for slider in sliders(panel)] == [True, True, True, False]
	assert panel._rateBoostCheckBox.enabled is False
	assert ui.presenter.calls == []


def test_locale_without_an_assignment_selects_no_voice(ui):
	panel = ui.panel
	choose(panel, panel._localesChoice, 1)
	assert panel._voicesChoice.choices == ["no-select", "Mei (VE)"]
	assert panel._voicesChoice.selection == 0
	assert panel._variantsChoice.choices == []
	assert not any(slider.enabled for slider in sliders(panel))


def test_a_stored_voice_the_locale_does_not_list_shows_no_select(ui):
	# For example another engine's role while engine consistency is on: shown, not changed.
	panel = ui.panel
	ui.presenter.assigned["zh"] = "gone"
	choose(panel, panel._localesChoice, 1)
	assert panel._voicesChoice.selection == 0
	assert not any(slider.enabled for slider in sliders(panel))
	assert ui.presenter.calls == []


def test_choosing_a_voice_assigns_it_and_shows_what_it_supports(ui):
	panel = ui.panel
	choose(panel, panel._localesChoice, 0)
	choose(panel, panel._voicesChoice, 1)

	assert ui.presenter.calls == [("selectVoice", "en", "eva")]
	assert [slider.value for slider in sliders(panel)] == [10, 20, 30, 40]
	assert all(slider.enabled for slider in sliders(panel))
	assert panel._rateBoostCheckBox.enabled is True
	assert panel._variantsChoice.selection == 0

	choose(panel, panel._voicesChoice, 0)
	assert ui.presenter.calls[-1] == ("selectVoice", "en", "")
	assert not any(slider.enabled for slider in sliders(panel))


def test_a_stored_variant_the_voice_no_longer_has_selects_the_first(ui):
	panel = ui.panel
	choose(panel, panel._localesChoice, 1)
	choose(panel, panel._voicesChoice, 1)
	assert panel._variantsChoice.selection == 0


def test_parameter_controls_edit_the_selected_voice(ui):
	panel = ui.panel
	choose(panel, panel._localesChoice, 0)
	choose(panel, panel._voicesChoice, 1)
	ui.presenter.calls.clear()

	for control, event, value in (
		(panel._rateSlider, "EVT_SLIDER", 15),
		(panel._pitchSlider, "EVT_SLIDER", 25),
		(panel._volumeSlider, "EVT_SLIDER", 35),
		(panel._inflectionSlider, "EVT_SLIDER", 45),
		(panel._rateBoostCheckBox, "EVT_CHECKBOX", True),
	):
		control.SetValue(value)
		fire(control, event, panel=panel)
	panel._variantsChoice.Select(1)
	fire(panel._variantsChoice, "EVT_CHOICE", panel=panel)

	assert ui.presenter.calls == [
		("setParameter", "eva", "rate", 15),
		("setParameter", "eva", "pitch", 25),
		("setParameter", "eva", "volume", 35),
		("setParameter", "eva", "inflection", 45),
		("setParameter", "eva", "rateBoost", True),
		("setVariant", "eva", "v2"),
	]


def test_parameter_controls_without_a_voice_change_nothing(ui):
	panel = ui.panel
	choose(panel, panel._localesChoice, 1)  # no voice assigned
	panel._rateSlider.SetValue(99)
	fire(panel._rateSlider, "EVT_SLIDER", panel=panel)
	fire(panel._variantsChoice, "EVT_CHOICE", panel=panel)
	assert ui.presenter.calls == []


def test_engine_consistency_reloads_the_locales(ui):
	panel = ui.panel
	ui.presenter.locale_names = [("zh", "Chinese")]
	panel._keepEngineConsistentCheckBox.SetValue(False)
	fire(panel._keepEngineConsistentCheckBox, "EVT_CHECKBOX", panel=panel)

	assert ui.presenter.calls == [("setEngineConsistency", False)]
	assert panel._localesChoice.choices == ["Chinese"]
	assert panel._locales == ["zh"]


def test_voice_and_parameter_consistency_reach_the_presenter(ui):
	panel = ui.panel
	choose(panel, panel._localesChoice, 0)
	panel._keepConsistentCheckBox.SetValue(True)
	fire(panel._keepConsistentCheckBox, "EVT_CHECKBOX", panel=panel)
	ui.presenter.instances["tom"].rate = 77
	panel._keepParameterConsistentCheckBox.SetValue(False)
	fire(panel._keepParameterConsistentCheckBox, "EVT_CHECKBOX", panel=panel)

	assert ui.presenter.calls == [("setVoiceConsistency", True), ("setParameterConsistency", False)]
	# The shown parameters are reread: with consistency off each role has its own.
	assert panel._rateSlider.value == 77


def test_a_failing_handler_reports_the_error_and_reopens_the_dialog(ui):
	panel = ui.panel

	def broken(locale):
		raise RuntimeError("voice table gone")

	ui.presenter.voices = broken
	dialog = SimpleNamespace(cancelled=[])
	dialog.onCancel = dialog.cancelled.append
	panel.top_level_parent = dialog

	panel._localesChoice.Select(0)
	fire(panel._localesChoice, "EVT_CHOICE", panel=panel)  # does not raise

	((message, caption, style),) = ui.env.shown
	assert "Details: voice table gone" in message
	assert caption == "WorldVoice Setting Dialog - Error"
	assert style == ui.env.wx.OK | ui.env.wx.ICON_ERROR
	assert ("error", "Unhandled exception in SpeechRoleSettingsPanel.onLocaleChanged") in ui.env.logged
	# gotErrorCallback: cancel this dialog and open a fresh one of the same type.
	assert dialog.cancelled == [None]
	assert ui.env.wx.called_after == [(ui.env.gui.mainFrame.popupSettingsDialog, (SimpleNamespace,))]


def test_discard_drops_pending_edits_and_errors_stay_in_the_log(ui):
	ui.panel.onDiscard()
	assert ui.presenter.calls == [("discard",)]

	def broken():
		raise RuntimeError("closed")

	ui.presenter.discard = broken
	ui.panel.onDiscard()  # NVDA closes the dialog regardless
	assert [caption for _message, caption, _style in ui.env.shown] == ["WorldVoice Setting Dialog - Error"]


def test_save_applies_the_pending_edits(ui):
	ui.panel.onSave()
	assert ui.presenter.calls == [("apply",)]


def test_a_failed_save_reports_the_error_and_keeps_the_dialog_open(ui):
	def broken():
		raise OSError("disk full")

	ui.presenter.apply = broken
	with pytest.raises(ValueError):  # NVDA keeps its settings dialog open only on ValueError
		ui.panel.onSave()

	((message, caption, style),) = ui.env.shown
	assert message.startswith("An unexpected error occurred while processing your action.")
	assert "Details: disk full" in message
	assert caption == "WorldVoice Setting Dialog - Error"
	assert style == ui.env.wx.OK | ui.env.wx.ICON_ERROR
	assert ("error", "Failed to save voice settings") in ui.env.logged


def test_controls_used_before_choosing_a_locale_change_nothing(ui):
	panel = ui.panel
	fire(panel._voicesChoice, "EVT_CHOICE", panel=panel)
	panel._rateSlider.SetValue(99)
	fire(panel._rateSlider, "EVT_SLIDER", panel=panel)
	assert ui.presenter.calls == []
	assert ui.env.shown == []
