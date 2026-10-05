"""The role panel turns a failed apply into NVDA's save-abort signal."""

import ast
from pathlib import Path
import types

import pytest


PANEL = Path(__file__).resolve().parents[1] / "addon/globalPlugins/WorldVoice/speechSettingsDialog.py"


def load_panel(environment):
	tree = ast.parse(PANEL.read_text(encoding="utf-8"))
	node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SpeechRoleSettingsPanel")
	exec(compile(ast.Module(body=[node], type_ignores=[]), str(PANEL), "exec"), environment)
	return environment["SpeechRoleSettingsPanel"]


def checkbox(value):
	return types.SimpleNamespace(GetValue=lambda: value)


def test_failed_apply_shows_error_and_raises_value_error():
	messages, logged = [], []
	panel_type = load_panel({
		"SettingsPanel": object,
		"_": lambda text: text,
		"guard_errors": lambda **kwargs: (lambda method: method),
		"got_error_callback": None,
		"wx": types.SimpleNamespace(OK=1, ICON_ERROR=2),
		"gui": types.SimpleNamespace(messageBox=lambda *args: messages.append(args)),
		"log": types.SimpleNamespace(error=lambda *args, **kwargs: logged.append(args)),
		"getSynth": lambda: types.SimpleNamespace(name="WorldVoice"),
	})
	panel = object.__new__(panel_type)
	panel.disable = False
	calls = []
	def apply():
		raise OSError("save failed")
	panel._presenter = types.SimpleNamespace(
		set_engine_consistency=lambda value: calls.append(("engine", value)),
		set_voice_consistency=lambda value: calls.append(("voice", value)),
		set_parameter_consistency=lambda value: calls.append(("parameter", value)),
		apply=apply,
	)
	panel._keepEngineConsistentCheckBox = checkbox(True)
	panel._keepConsistentCheckBox = checkbox(False)
	panel._keepParameterConsistentCheckBox = checkbox(True)

	with pytest.raises(ValueError):
		panel.onSave()

	# The checkbox handlers already told the presenter; saving only applies.
	assert calls == []
	assert messages and "save failed" in messages[0][0]
	assert logged


def test_panel_no_longer_touches_role_config_directly():
	source = PANEL.read_text(encoding="utf-8")
	for name in ("AggregatedSection", "_dataToPercist", "_defaultVoiceInstance", '["role"]'):
		assert name not in source


def test_destroy_closes_the_presenter_only_for_the_panel_itself():
	panel_type = load_panel({"SettingsPanel": object, "_": lambda text: text,
		"guard_errors": lambda **kwargs: (lambda method: method), "got_error_callback": None})
	panel = object.__new__(panel_type)
	closed, skipped = [], []
	panel._presenter = types.SimpleNamespace(close=lambda: closed.append(True))
	panel._onDestroy(types.SimpleNamespace(GetEventObject=lambda: object(), Skip=lambda: skipped.append(True)))
	assert closed == []
	panel._onDestroy(types.SimpleNamespace(GetEventObject=lambda: panel, Skip=lambda: skipped.append(True)))
	assert closed == [True]
	assert skipped == [True, True]


class Control:
	def __init__(self, *args, **kwargs):
		self.items = kwargs.get("choices")
	def __getattr__(self, name):
		return lambda *args, **kwargs: None


def test_panel_opens_its_presenter_for_the_worldvoice_manager():
	created = []
	manager = types.SimpleNamespace()

	class Presenter:
		def __init__(self, manager, **kwargs):
			created.append((manager, sorted(kwargs)))
			self.keep_engine = self.keep_voice = self.keep_parameters = False
		def locales(self):
			return [("en", "English")]

	wx = types.SimpleNamespace(**{name: Control for name in ("TextCtrl", "StaticText", "Choice", "Slider", "CheckBox")})
	for name in ("EVT_WINDOW_DESTROY", "EVT_CHOICE", "EVT_SLIDER", "EVT_CHECKBOX",
			"TE_READONLY", "TE_MULTILINE", "TE_WORDWRAP", "BORDER_NONE", "EXPAND", "SL_HORIZONTAL"):
		setattr(wx, name, 1)
	panel_type = load_panel({
		"SettingsPanel": object, "_": lambda text: text,
		"guard_errors": lambda **kwargs: (lambda method: method), "got_error_callback": None,
		"wx": wx,
		"getSynth": lambda: types.SimpleNamespace(name="WorldVoice", _voiceManager=manager),
		"config": types.SimpleNamespace(conf={}),
		"guiHelper": types.SimpleNamespace(BoxSizerHelper=lambda *args, **kwargs: types.SimpleNamespace(
			addLabeledControl=lambda *args, **kwargs: Control(**kwargs), addItem=lambda *args: None)),
		"RolePanelPresenter": Presenter,
	})
	panel = object.__new__(panel_type)
	bindings = []
	panel.Bind = lambda event, handler, *args: bindings.append(handler)
	panel.GetSize = lambda: (1000, 480)
	panel.GetBackgroundColour = lambda: None
	panel.makeSettings(types.SimpleNamespace(Add=lambda *args, **kwargs: None))
	assert created == [(manager, ["set_main_voice", "speech_section"])]
	assert panel._onDestroy in bindings
	assert panel._locales == ["en"]
	assert panel.disable is False


def test_save_does_nothing_after_the_synth_was_switched_away():
	applied = []
	panel_type = load_panel({
		"SettingsPanel": object, "_": lambda text: text,
		"guard_errors": lambda **kwargs: (lambda method: method), "got_error_callback": None,
		"getSynth": lambda: types.SimpleNamespace(name="eSpeak"),
	})
	panel = object.__new__(panel_type)
	panel.disable = False
	panel._presenter = types.SimpleNamespace(apply=lambda: applied.append(True))
	panel.onSave()
	assert applied == []
