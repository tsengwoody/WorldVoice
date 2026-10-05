"""Saving the WorldVoice settings panels writes config before persisting it."""

import ast
from collections import OrderedDict
from pathlib import Path
import types

import pytest


PANEL_PATH = Path(__file__).resolve().parents[1] / "addon/globalPlugins/WorldVoice/speechSettingsDialog.py"


class RecordingSection(dict):
	def __init__(self, calls, values):
		super().__init__(values)
		self._calls = calls

	def __setitem__(self, key, value):
		self._calls.append(("write", key, value))
		super().__setitem__(key, value)


def _load_panels(calls, logged):
	tree = ast.parse(PANEL_PATH.read_text(encoding="utf-8"))
	wanted = {"BaseSettingsPanel", "SpeechEngineSettingsPanel"}
	classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in wanted]
	section = RecordingSection(calls, {"VE": False, "OneCore": True, "SAPI5": False})
	environment = {
		"SettingsPanel": object,
		"_": lambda value: value,
		"OrderedDict": OrderedDict,
		"config": types.SimpleNamespace(conf={"WorldVoice": {"engine": section}}),
		"tones": types.SimpleNamespace(beep=lambda *args: calls.append(("beep",))),
		"log": types.SimpleNamespace(error=lambda *args, **kwargs: logged.append((args, kwargs))),
		"wx": types.SimpleNamespace(YES=2, NO=8, CANCEL=16),
		"gui": types.SimpleNamespace(
			mainFrame=types.SimpleNamespace(onSaveConfigurationCommand=lambda event: calls.append(("save",))),
		),
		"queueHandler": types.SimpleNamespace(
			eventQueue=object(),
			queueFunction=lambda queue, function: calls.append(("queue", function)),
		),
		"core": types.SimpleNamespace(restart=lambda: None),
	}
	exec(compile(ast.Module(body=classes, type_ignores=[]), str(PANEL_PATH), "exec"), environment)
	return environment, section


def _checkbox(value):
	def is_checked():
		if isinstance(value, BaseException):
			raise value
		return value

	return types.SimpleNamespace(IsChecked=is_checked)


def _engine_panel(environment, *, active, previous, confirm):
	panel = environment["SpeechEngineSettingsPanel"]()
	panel.settings = OrderedDict((name, {"label": name}) for name in ("VE", "OneCore", "SAPI5"))
	for name in panel.settings:
		setattr(panel, name + "CheckBox", _checkbox(name in active))
	panel.activeEngine = set(active)
	panel.previousActiveEngine = set(previous)
	panel.confirm = confirm
	return panel


def test_engine_change_writes_flags_before_saving_and_restarting():
	calls, logged = [], []
	environment, section = _load_panels(calls, logged)
	panel = _engine_panel(environment, active={"VE"}, previous={"OneCore"}, confirm=environment["wx"].YES)

	panel.onSave()

	assert calls == [
		("write", "VE", True),
		("write", "OneCore", False),
		("write", "SAPI5", False),
		("save",),
		("queue", environment["core"].restart),
	]
	assert dict(section) == {"VE": True, "OneCore": False, "SAPI5": False}


def test_engine_change_without_restart_writes_flags_only():
	calls, logged = [], []
	environment, section = _load_panels(calls, logged)
	panel = _engine_panel(environment, active={"VE"}, previous={"OneCore"}, confirm=environment["wx"].NO)

	panel.onSave()

	assert calls == [("write", "VE", True), ("write", "OneCore", False), ("write", "SAPI5", False)]


def test_unchanged_engines_write_nothing():
	calls, logged = [], []
	environment, section = _load_panels(calls, logged)
	panel = _engine_panel(environment, active={"OneCore"}, previous={"OneCore"}, confirm=None)

	panel.onSave()

	assert calls == []


def test_engine_change_does_not_restart_after_failed_flag_write():
	calls, logged = [], []
	environment, section = _load_panels(calls, logged)
	panel = _engine_panel(environment, active={"VE"}, previous={"OneCore"}, confirm=environment["wx"].YES)
	panel.OneCoreCheckBox = _checkbox(RuntimeError("checkbox destroyed"))

	panel.onSave()

	assert calls == [("beep",)]
	assert dict(section) == {"VE": False, "OneCore": True, "SAPI5": False}
	assert len(logged) == 1


def test_failed_save_changes_no_settings_and_logs():
	calls, logged = [], []
	environment, section = _load_panels(calls, logged)
	panel = environment["BaseSettingsPanel"]()
	panel.field = "engine"
	panel.settings = OrderedDict((name, {"label": name}) for name in ("VE", "OneCore", "SAPI5"))
	panel.VECheckBox = _checkbox(True)
	panel.OneCoreCheckBox = _checkbox(RuntimeError("checkbox destroyed"))
	panel.SAPI5CheckBox = _checkbox(True)

	assert panel._write_settings() is False

	assert calls == [("beep",)]
	assert dict(section) == {"VE": False, "OneCore": True, "SAPI5": False}
	assert len(logged) == 1
	args, kwargs = logged[0]
	assert args == ("WorldVoice: failed to save %s settings", "engine")
	assert kwargs == {"exc_info": True}


def test_failed_choice_save_changes_no_settings():
	calls, logged = [], []
	environment, section = _load_panels(calls, logged)
	panel = environment["BaseSettingsPanel"]()
	panel.field = "engine"
	panel.settings = OrderedDict(
		(name, {"label": name, "options": {"on": "On", "off": "Off"}}) for name in ("VE", "OneCore", "SAPI5")
	)
	panel.VESelection = types.SimpleNamespace(GetSelection=lambda: 0)
	panel.OneCoreSelection = types.SimpleNamespace(GetSelection=lambda: 7)
	panel.SAPI5Selection = types.SimpleNamespace(GetSelection=lambda: 1)

	assert panel._write_settings() is False

	assert calls == [("beep",)]
	assert dict(section) == {"VE": False, "OneCore": True, "SAPI5": False}


def test_failed_save_does_not_swallow_keyboard_interrupt():
	calls, logged = [], []
	environment, section = _load_panels(calls, logged)
	panel = environment["BaseSettingsPanel"]()
	panel.field = "engine"
	panel.settings = OrderedDict((name, {"label": name}) for name in ("VE", "OneCore"))
	panel.VECheckBox = _checkbox(KeyboardInterrupt())
	panel.OneCoreCheckBox = _checkbox(True)

	with pytest.raises(KeyboardInterrupt):
		panel.onSave()

	assert calls == []
	assert logged == []


def test_on_save_returns_nothing_like_nvda_panels():
	calls, logged = [], []
	environment, section = _load_panels(calls, logged)
	panel = environment["BaseSettingsPanel"]()
	panel.field = "engine"
	panel.settings = OrderedDict((name, {"label": name}) for name in ("VE", "OneCore"))
	panel.VECheckBox = _checkbox(True)
	panel.OneCoreCheckBox = _checkbox(False)
	assert panel.onSave() is None
	assert dict(section) == {"VE": True, "OneCore": False, "SAPI5": False}
