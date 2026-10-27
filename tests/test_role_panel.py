"""The role panel turns a failed apply into NVDA's save-abort signal."""

import types

import pytest
from addon_loader import ADDON, load_definitions

PANEL = ADDON / "globalPlugins/WorldVoice/panels/role.py"


def load_panel(environment):
	return load_definitions(PANEL, ["SpeechRoleSettingsPanel"], environment)["SpeechRoleSettingsPanel"]


def checkbox(value):
	return types.SimpleNamespace(GetValue=lambda: value)


def test_failed_apply_shows_error_and_raises_value_error():
	messages, logged = [], []
	manager = object()
	panel_type = load_panel(
		{
			"SettingsPanel": object,
			"_": lambda text: text,
			"guardErrors": lambda **kwargs: lambda method: method,
			"gotErrorCallback": None,
			"reportError": messages.append,
			"log": types.SimpleNamespace(error=lambda *args, **kwargs: logged.append(args)),
			"worldvoice_synth": lambda: types.SimpleNamespace(name="WorldVoice", voiceManager=manager),
		},
	)
	panel = object.__new__(panel_type)
	panel.disable = False
	panel._manager = manager
	calls = []

	def apply():
		raise OSError("save failed")

	panel._presenter = types.SimpleNamespace(
		setEngineConsistency=lambda value: calls.append(("engine", value)),
		setVoiceConsistency=lambda value: calls.append(("voice", value)),
		setParameterConsistency=lambda value: calls.append(("parameter", value)),
		apply=apply,
	)
	panel._keepEngineConsistentCheckBox = checkbox(True)
	panel._keepConsistentCheckBox = checkbox(False)
	panel._keepParameterConsistentCheckBox = checkbox(True)

	with pytest.raises(ValueError):
		panel.onSave()

	# The checkbox handlers already told the presenter; saving only applies.
	assert calls == []
	assert [str(error) for error in messages] == ["save failed"]
	assert logged


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


class Control:
	def __init__(self, *args, **kwargs):
		self.items = kwargs.get("choices")

	def __getattr__(self, name):
		return lambda *args, **kwargs: None


def test_panel_opens_its_presenter_for_the_worldvoice_manager():
	created = []
	manager = types.SimpleNamespace()
	synth = types.SimpleNamespace(name="WorldVoice", voiceManager=manager)
	current = [synth]
	speech = {"WorldVoice": {}}
	hooks = {}

	class Presenter:
		def __init__(self, manager, **kwargs):
			created.append((manager, sorted(kwargs)))
			hooks.update(kwargs)
			self.keepEngine = self.keepVoice = self.keepParameters = False

		def locales(self):
			return [("en", "English")]

	wx = types.SimpleNamespace(
		**{name: Control for name in ("TextCtrl", "StaticText", "Choice", "Slider", "CheckBox")},
	)
	for name in (
		"EVT_WINDOW_DESTROY",
		"EVT_CHOICE",
		"EVT_SLIDER",
		"EVT_CHECKBOX",
		"TE_READONLY",
		"TE_MULTILINE",
		"TE_WORDWRAP",
		"BORDER_NONE",
		"EXPAND",
		"SL_HORIZONTAL",
	):
		setattr(wx, name, 1)
	panel_type = load_panel(
		{
			"SettingsPanel": object,
			"_": lambda text: text,
			"guardErrors": lambda **kwargs: lambda method: method,
			"gotErrorCallback": None,
			"wx": wx,
			"worldvoice_synth": lambda: current[0],
			"config": types.SimpleNamespace(conf={"speech": speech}),
			"guiHelper": types.SimpleNamespace(
				BoxSizerHelper=lambda *args, **kwargs: types.SimpleNamespace(
					addLabeledControl=lambda *args, **kwargs: Control(**kwargs),
					addItem=lambda *args: None,
				),
			),
			"RolePanelPresenter": Presenter,
		},
	)
	panel = object.__new__(panel_type)
	bindings = []
	panel.Bind = lambda event, handler, *args: bindings.append(handler)
	panel.GetSize = lambda: (1000, 480)
	panel.GetBackgroundColour = lambda: None
	panel.makeSettings(types.SimpleNamespace(Add=lambda *args, **kwargs: None))
	assert created == [(manager, ["setMainVoice", "speechSection"])]
	assert panel._onDestroy in bindings
	assert panel._locales == ["en"]
	assert panel.disable is False
	# The dialog is not modal: setting the main voice asks for the current synth when it runs.
	hooks["setMainVoice"]("b")
	assert synth.voice == "b" and speech["WorldVoice"]["voice"] == "b"
	current[0] = None
	hooks["setMainVoice"]("c")
	assert synth.voice == "b" and speech["WorldVoice"]["voice"] == "c"


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
