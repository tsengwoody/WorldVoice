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
