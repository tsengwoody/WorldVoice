"""The WorldVoice settings panels show the stored settings and save what the user changed.

Each panel's real makeSettings runs against the fake wx in ui_harness, over a fresh WorldVoice
profile and the real pipeline settings service.
"""

from types import SimpleNamespace

import pytest
from nvda_stubs import worldvoice_conf
from pipeline_harness import ORDER
from ui_harness import Sizer, TextCtrl, fire, load_settings_dialog, make_panel


def build(env, name):
	panel = make_panel(getattr(env.module, name))
	sizer = Sizer()
	panel.makeSettings(sizer)
	return panel, sizer


# SpeechPipelinePanel


def pipeline_env(monkeypatch, **stored):
	conf = {**worldvoice_conf(pipeline=stored), "speech": {"WorldVoice": {}}}
	return load_settings_dialog(monkeypatch, conf=conf)


def test_pipeline_panel_shows_the_stored_settings(monkeypatch):
	env = pipeline_env(
		monkeypatch,
		scope="all",
		ignore_comma_between_number=True,
		number_mode="group",
		global_wait_factor=30,
		number_wait_factor=11,
		group_wait_factor=12,
		item_wait_factor=13,
		sayall_wait_factor=14,
		chinesespace_wait_factor=15,
		punctuation_wait_factor=16,
		punctuation_pause_enabled=False,
		remove_punctuation_characters=True,
		punctuation_pause_characters="。，",
	)
	panel, sizer = build(env, "SpeechPipelinePanel")

	assert [control.label for control in sizer.controls()] == [
		"Effect Scope:",
		"Ignore comma between number",
		"Number mode:",
		"global wait factor:",
		"number wait factor:",
		"pair wait factor:",
		"item wait factor:",
		"sayall wait factor:",
		"chinese space wait factor:",
		"Enable punctuation pause control",
		"Remove configured punctuation at pause points",
		"punctuation wait factor:",
		"Punctuation pause characters:",
	]
	assert panel._scope_choice.choices == ["All Synthesizers (Global)", "Only WorldVoice Synthesizer"]
	assert panel._scope_choice.selection == 0
	assert panel._number_mode_choice.selection == 2
	assert panel._ignore_comma_between_number_checkbox.value is True
	# The global factor is stored in tens and shown in units.
	assert panel._global_wait_factor_slider.value == 3
	assert [
		getattr(panel, f"_{name}_wait_factor_slider").value
		for name in ("number", "group", "item", "sayall", "chinesespace", "punctuation")
	] == [11, 12, 13, 14, 15, 16]
	assert panel._punctuation_pause_enabled_checkbox.value is False
	assert panel._remove_punctuation_characters_checkbox.value is True
	assert panel._punctuation_pause_characters_edit.value == "。，"


def test_pipeline_panel_selects_the_first_choice_for_an_unknown_stored_value(monkeypatch):
	env = pipeline_env(monkeypatch, scope="nowhere", number_mode="roman")
	panel, _sizer = build(env, "SpeechPipelinePanel")
	assert panel._scope_choice.selection == 0
	assert panel._number_mode_choice.selection == 0


def pause_controls_enabled(panel):
	return (
		panel._remove_punctuation_characters_checkbox.enabled,
		panel._punctuation_wait_factor_slider.enabled,
		panel._punctuation_pause_characters_edit.enabled,
	)


@pytest.mark.parametrize("remove", [False, True])
@pytest.mark.parametrize("pause", [False, True])
def test_pipeline_panel_enables_pause_controls_from_the_stored_switch(monkeypatch, pause, remove):
	env = pipeline_env(monkeypatch, punctuation_pause_enabled=pause, remove_punctuation_characters=remove)
	panel, _sizer = build(env, "SpeechPipelinePanel")
	assert pause_controls_enabled(panel) == (pause, pause, pause)


def test_pipeline_panel_pause_controls_follow_the_switch_only(monkeypatch):
	env = pipeline_env(monkeypatch, punctuation_pause_enabled=False, remove_punctuation_characters=False)
	panel, _sizer = build(env, "SpeechPipelinePanel")
	pause = panel._punctuation_pause_enabled_checkbox
	remove = panel._remove_punctuation_characters_checkbox

	pause.SetValue(True)
	fire(pause, "EVT_CHECKBOX", panel=panel)
	assert pause_controls_enabled(panel) == (True, True, True)

	# Removal decides nothing about the other controls, so nothing listens to it.
	remove.SetValue(True)
	with pytest.raises(LookupError, match="nothing handles"):
		fire(remove, "EVT_CHECKBOX", panel=panel)
	assert pause_controls_enabled(panel) == (True, True, True)

	pause.SetValue(False)
	fire(pause, "EVT_CHECKBOX", panel=panel)
	assert pause_controls_enabled(panel) == (False, False, False)


def test_pipeline_panel_saves_the_disabled_pause_controls(monkeypatch):
	env = pipeline_env(monkeypatch, punctuation_pause_enabled=False)
	panel, _sizer = build(env, "SpeechPipelinePanel")
	panel._remove_punctuation_characters_checkbox.SetValue(True)
	panel._punctuation_wait_factor_slider.SetValue(30)
	panel._punctuation_pause_characters_edit.SetValue("。")

	panel.onSave()

	stored = env.conf["WorldVoice"]["pipeline"]
	assert (stored["remove_punctuation_characters"], stored["punctuation_wait_factor"]) == (True, 30)
	assert stored["punctuation_pause_characters"] == "。"


def test_pipeline_panel_saves_the_edited_controls_to_config(monkeypatch):
	env = pipeline_env(monkeypatch)
	panel, _sizer = build(env, "SpeechPipelinePanel")
	panel._scope_choice.Select(0)
	panel._number_mode_choice.Select(1)
	panel._ignore_comma_between_number_checkbox.SetValue(True)
	panel._global_wait_factor_slider.SetValue(7)
	panel._group_wait_factor_slider.SetValue(40)
	panel._punctuation_pause_enabled_checkbox.SetValue(False)
	panel._punctuation_pause_characters_edit.SetValue(" ;: ")

	panel.onSave()

	stored = env.conf["WorldVoice"]["pipeline"]
	assert stored["scope"] == "all"
	assert stored["number_mode"] == "number"
	assert stored["ignore_comma_between_number"] is True
	assert stored["global_wait_factor"] == 70
	assert stored["group_wait_factor"] == 40
	assert stored["punctuation_pause_enabled"] is False
	assert stored["punctuation_pause_characters"] == ";:"


def test_pipeline_panel_saved_unchanged_keeps_the_stored_settings(monkeypatch):
	env = pipeline_env(monkeypatch, number_wait_factor=33)
	before = dict(env.conf["WorldVoice"]["pipeline"])
	panel, _sizer = build(env, "SpeechPipelinePanel")
	panel.onSave()
	assert env.conf["WorldVoice"]["pipeline"] == before


# SpeechEngineSettingsPanel

ENGINES = (("OneCore", "OneCore voices", True), ("SAPI5", "SAPI5 voices", False), ("VE", "Vocalizer", False))


def engine_env(monkeypatch, stored, answers=None):
	conf = {**worldvoice_conf(engine=stored), "speech": {"WorldVoice": {}}}
	return load_settings_dialog(monkeypatch, conf=conf, engines=ENGINES, answers=answers)


def test_engine_panel_lists_every_engine_with_its_stored_flag(monkeypatch):
	env = engine_env(monkeypatch, {"SAPI5": True, "VE": "False"})
	panel, sizer = build(env, "SpeechEngineSettingsPanel")

	info, group = sizer.items[0].item, sizer.items[1].item
	assert isinstance(info, TextCtrl) and info.value == "Please select one or more speech engines to enable."
	assert group.box.label == "Select Speech Engines to Enable"
	assert [(box.label, box.value) for box in group.controls()] == [
		("OneCore voices", True),  # not stored: the engine's default
		("SAPI5 voices", True),
		("Vocalizer", False),  # a stored string still reads as a flag
	]
	assert panel.previousActiveEngine == {"OneCore", "SAPI5"}


def test_engine_panel_refuses_to_save_with_no_engine_enabled(monkeypatch):
	env = engine_env(monkeypatch, {})
	panel, _sizer = build(env, "SpeechEngineSettingsPanel")
	panel.OneCoreCheckBox.SetValue(False)

	assert panel.isValid() is False

	((message, caption, style),) = env.shown
	assert "no speech engine is enabled" in message
	assert caption == "No Speech Engine Enabled"
	assert style == env.wx.OK | env.wx.ICON_WARNING
	assert env.conf["WorldVoice"]["engine"] == {}


def test_engine_panel_unchanged_engines_save_without_asking(monkeypatch):
	env = engine_env(monkeypatch, {})
	panel, _sizer = build(env, "SpeechEngineSettingsPanel")
	assert panel.isValid() is True
	panel.onSave()
	assert env.shown == []
	assert env.conf["WorldVoice"]["engine"] == {}
	assert env.queued == []


def test_engine_panel_change_cancelled_keeps_the_dialog_open(monkeypatch):
	env = engine_env(monkeypatch, {}, answers=[0x10])  # wx.CANCEL
	panel, _sizer = build(env, "SpeechEngineSettingsPanel")
	panel.VECheckBox.SetValue(True)
	assert panel.isValid() is False
	assert [caption for _message, caption, _style in env.shown] == ["Speech Engine Change"]


def test_engine_panel_change_confirmed_saves_and_restarts(monkeypatch):
	env = engine_env(monkeypatch, {}, answers=[0x2])  # wx.YES
	panel, _sizer = build(env, "SpeechEngineSettingsPanel")
	panel.VECheckBox.SetValue(True)
	assert panel.isValid() is True
	assert panel.confirm == env.wx.YES

	panel.onSave()

	assert env.conf["WorldVoice"]["engine"] == {"OneCore": True, "SAPI5": False, "VE": True}
	assert env.popped == ["save configuration"]
	assert env.queued == [("event queue", env.restart)]


# LogSettingsPanel


def log_env(monkeypatch, *, enabled, **stored):
	conf = {**worldvoice_conf(log=stored), "speech": {"WorldVoice": {}}}
	env = load_settings_dialog(monkeypatch, conf=conf)
	env.pipeline_log.enabled = enabled
	return env


def test_log_panel_shows_one_switch_per_stage_from_config(monkeypatch):
	env = log_env(monkeypatch, enabled=True, number_mode=True, speech_viewer=True)
	panel, sizer = build(env, "LogSettingsPanel")

	assert sizer.items[0].item is panel._enable_checkbox
	assert panel._enable_checkbox.value is True
	group = sizer.items[1].item
	boxes = group.controls()
	labels = env.module._LOG_LABELS
	assert [box.label for box in boxes] == [labels[key] for key in ORDER]
	assert {key for key, box in zip(ORDER, boxes, strict=True) if box.value} == {
		"number_mode",
		"speech_viewer",
	}
	assert all(box.enabled for box in boxes)


def test_log_panel_stage_switches_follow_the_enable_checkbox(monkeypatch):
	env = log_env(monkeypatch, enabled=False)
	panel, sizer = build(env, "LogSettingsPanel")
	boxes = sizer.items[1].item.controls()
	assert not any(box.enabled for box in boxes)

	panel._enable_checkbox.SetValue(True)
	fire(panel._enable_checkbox, "EVT_CHECKBOX", panel=panel)
	assert all(box.enabled for box in boxes)


def test_log_panel_cancelled_enable_is_unticked_and_blocks_the_save(monkeypatch):
	env = log_env(monkeypatch, enabled=False)
	env.confirm_answer[0] = env.wx.CANCEL
	panel, sizer = build(env, "LogSettingsPanel")
	panel._enable_checkbox.SetValue(True)
	fire(panel._enable_checkbox, "EVT_CHECKBOX", panel=panel)

	assert panel.isValid() is False

	assert env.log_calls == [("confirm", True)]
	assert panel._enable_checkbox.value is False
	assert not any(box.enabled for box in sizer.items[1].item.controls())


def test_log_panel_enabling_turns_logging_on_and_saves_the_switches(monkeypatch):
	env = log_env(monkeypatch, enabled=False)
	panel, _sizer = build(env, "LogSettingsPanel")
	panel._enable_checkbox.SetValue(True)
	panel.number_modeCheckBox.SetValue(True)

	assert panel.isValid() is True
	panel.onSave()

	assert env.log_calls == [("confirm", True), "enable"]
	assert env.conf["WorldVoice"]["log"]["number_mode"] is True
	assert env.conf["WorldVoice"]["log"]["item_wait_factor"] is False


@pytest.mark.parametrize("export", [True, False])
def test_log_panel_disabling_offers_to_export_the_log(monkeypatch, export):
	env = log_env(monkeypatch, enabled=True)
	env.export_answer[0] = export
	panel, _sizer = build(env, "LogSettingsPanel")
	panel._enable_checkbox.SetValue(False)

	assert panel.isValid() is True
	panel.onSave()

	assert env.log_calls == ["disable", "ask export"]
	assert env.wx.called_after == ([(env.pipeline_log.export, ())] if export else [])


def test_log_panel_unchanged_logging_saves_only_the_switches(monkeypatch):
	env = log_env(monkeypatch, enabled=True)
	panel, _sizer = build(env, "LogSettingsPanel")
	panel.speech_viewerCheckBox.SetValue(True)

	assert panel.isValid() is True
	panel.onSave()

	assert env.log_calls == []
	assert env.conf["WorldVoice"]["log"]["speech_viewer"] is True


# BaseSettingsPanel choices


def test_base_panel_choice_selects_the_stored_option_or_the_first(monkeypatch):
	env = load_settings_dialog(monkeypatch)
	env.conf["WorldVoice"]["engine"] = {"mode": "fast", "other": "unknown"}

	class Panel(env.module.BaseSettingsPanel):
		field = "engine"
		settings = {  # noqa: RUF012
			"mode": {"label": "Mode:", "options": {"slow": "Slow", "fast": "Fast"}},
			"other": {"label": "Other:", "options": {"a": "A", "b": "B"}},
		}

	panel = make_panel(Panel)
	panel.makeSettings(Sizer())

	assert panel.modeSelection.choices == ["Slow", "Fast"]
	assert panel.modeSelection.selection == 1
	assert panel.otherSelection.selection == 0
	assert ("debugWarning", "Invalid stored WorldVoice engine other") in env.logged

	panel.otherSelection.Select(1)
	panel.onSave()
	assert env.conf["WorldVoice"]["engine"] == {"mode": "fast", "other": "b"}


# UnicodeDetectionSettingsPanel


def test_unicode_panel_for_another_synth_only_says_so(monkeypatch):
	env = load_settings_dialog(monkeypatch, synth=SimpleNamespace(name="espeak"))
	panel, sizer = build(env, "UnicodeDetectionSettingsPanel")
	(info,) = sizer.contents()
	assert isinstance(info, TextCtrl)
	assert info.value == "Your current speech synthesizer is not WorldVoice."
	assert panel.disable is True
	panel.onSave()  # detection_settings is None in this harness: saving must not reach it


# WorldVoiceSettingsDialog


@pytest.mark.parametrize("worldvoice", [True, False])
def test_dialog_offers_role_and_unicode_panels_only_for_worldvoice(monkeypatch, worldvoice):
	synth = SimpleNamespace(name="WorldVoice" if worldvoice else "espeak")
	env = load_settings_dialog(monkeypatch, synth=synth)
	module = env.module

	dialog = module.WorldVoiceSettingsDialog("main frame")

	expected = [module.SpeechPipelinePanel]
	if worldvoice:
		expected.append(module.SpeechRoleSettingsPanel)
	expected.append(module.SpeechEngineSettingsPanel)
	if worldvoice:
		expected.append(module.UnicodeDetectionSettingsPanel)
	expected.append(module.LogSettingsPanel)
	assert dialog.opened_with == expected
	assert dialog.title == "WorldVoice - Settings"
