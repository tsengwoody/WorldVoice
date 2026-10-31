"""The role panel closes its presenter with itself and saves nothing once another synth is active."""

import types

from addon_loader import ADDON, load_definitions

PANEL = ADDON / "globalPlugins/WorldVoice/panels/role.py"


def load_panel(environment):
	return load_definitions(PANEL, ["SpeechRoleSettingsPanel"], environment)["SpeechRoleSettingsPanel"]


def test_destroy_closes_the_presenter_only_for_the_panel_itself():
	panel_type = load_panel(
		{
			"SettingsPanel": object,
			"_": lambda text: text,
			"guardErrors": lambda **kwargs: lambda method: method,
			"gotErrorCallback": None,
		},
	)
	panel = object.__new__(panel_type)
	closed, skipped = [], []
	panel._presenter = types.SimpleNamespace(close=lambda: closed.append(True))
	panel._onDestroy(
		types.SimpleNamespace(GetEventObject=lambda: object(), Skip=lambda: skipped.append(True)),
	)
	assert closed == []
	panel._onDestroy(types.SimpleNamespace(GetEventObject=lambda: panel, Skip=lambda: skipped.append(True)))
	assert closed == [True]
	assert skipped == [True, True]


def test_save_does_nothing_after_the_synth_was_switched_away():
	applied = []
	panel_type = load_panel(
		{
			"SettingsPanel": object,
			"_": lambda text: text,
			"guardErrors": lambda **kwargs: lambda method: method,
			"gotErrorCallback": None,
			"worldvoice_synth": lambda: None,
		},
	)
	panel = object.__new__(panel_type)
	panel.disable = False
	panel._presenter = types.SimpleNamespace(apply=lambda: applied.append(True))
	panel.onSave()
	assert applied == []
