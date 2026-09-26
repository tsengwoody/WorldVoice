import ast
from collections import defaultdict, OrderedDict
import importlib.util
from functools import wraps
import sys
import types
from pathlib import Path
import pytest

from test_worldvoice_lifecycle import _load_voice_manager, WORLDVOICE


PANEL_PATH = WORLDVOICE.parents[1] / "globalPlugins/WorldVoice/speechSettingsDialog.py"


def _load_panel_class(config, get_synth, errors=None):
	tree = ast.parse(PANEL_PATH.read_text(encoding="utf-8"))
	panel = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SpeechRoleSettingsPanel")
	environment = {
		"SettingsPanel": object,
		"_": lambda value: value,
		"wraps": wraps,
		"got_error_callback": lambda self: None,
		"config": config,
		"getSynth": get_synth,
		"wx": types.SimpleNamespace(NOT_FOUND=-1, OK=1, ICON_ERROR=2),
		"defaultdict": defaultdict,
		"log": types.SimpleNamespace(error=lambda *args, **kwargs: None),
		"gui": types.SimpleNamespace(messageBox=lambda *args: errors.append(args) if errors is not None else None),
	}
	utils = ast.parse(PANEL_PATH.with_name("utils.py").read_text(encoding="utf-8"))
	guard = next(node for node in utils.body if isinstance(node, ast.FunctionDef) and node.name == "guard_errors")
	exec(compile(ast.Module(body=[guard], type_ignores=[]), str(PANEL_PATH.with_name("utils.py")), "exec"), environment)
	exec(compile(ast.Module(body=[panel], type_ignores=[]), str(PANEL_PATH), "exec"), environment)
	return environment["SpeechRoleSettingsPanel"]


def _create_voices(monkeypatch, config):
	package_name = "lifecycle_test_worldvoice"
	name = f"{package_name}.driver"
	spec = importlib.util.spec_from_file_location(name, WORLDVOICE / "driver/__init__.py")
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, name, module)
	spec.loader.exec_module(module)
	config.conf["WorldVoice"]["voices"] = {}
	config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = False
	from voice_binding_harness import install_binding
	install_binding(module, config)
	return (
		module.Voice("a", "A:a", None, "en"),
		module.Voice("b", "B:b", None, "fr"),
	)


def test_parameter_preview_is_undone_by_cancel(monkeypatch):
	module = _load_voice_manager(monkeypatch, {})
	config = sys.modules["config"]
	monkeypatch.setattr(sys.modules["synthDriverHandler"], "getSynth",
		lambda: types.SimpleNamespace(name="WorldVoice"), raising=False)
	monkeypatch.setattr(sys.modules["languageHandler"], "getLanguageDescription",
		lambda language: language, raising=False)
	a, b = _create_voices(monkeypatch, config)
	manager = object.__new__(module.VoiceManager)
	manager._instanceCache = {a.name: a, b.name: b}
	manager.settings = a._binding.settings
	panel_type = _load_panel_class(config, lambda: types.SimpleNamespace(name="WorldVoice"))
	panel = panel_type()
	panel.disable = False
	panel._manager = manager
	panel._editSession = manager.settings.begin_edit()
	panel._dataToPercist = defaultdict(dict)
	panel._initialKeepEngineConsistent = False
	panel._voicesChoice = types.SimpleNamespace(GetCurrentSelection=lambda: 0)
	panel._voiceNamesByChoiceIndex = [a.name]
	panel._rateSlider = types.SimpleNamespace(GetValue=lambda: 72)
	panel._keepParameterConsistentCheckBox = types.SimpleNamespace(GetValue=lambda: True)
	manager.getVoiceInstance = lambda name: manager._instanceCache[name]

	panel.onSpeechRateSliderScroll(None)
	assert (a.rate, b.rate) == (72, 72)
	panel.onDiscard()
	assert (a.rate, b.rate) == (50, 50)
	assert config.conf["WorldVoice"]["voices"][a.name]["rate"] == 50
	assert config.conf["WorldVoice"]["voices"][b.name]["rate"] == 50


def test_engine_consistency_preview_cancel_and_apply(monkeypatch):
	class Section(dict):
		pass

	module = _load_voice_manager(monkeypatch, {})
	config = sys.modules["config"]
	config.AggregatedSection = Section
	config.conf["WorldVoice"]["role"] = {
		"en": Section(voice="A:a"),
		"fr": Section(voice="B:b"),
	}
	monkeypatch.setattr(sys.modules["synthDriverHandler"], "getSynth",
		lambda: types.SimpleNamespace(name="WorldVoice"), raising=False)
	monkeypatch.setattr(sys.modules["languageHandler"], "getLanguageDescription",
		lambda language: language, raising=False)
	a, b = _create_voices(monkeypatch, config)
	manager = object.__new__(module.VoiceManager)
	manager._instanceCache = {a.name: a, b.name: b}
	manager.settings = a._binding.settings
	manager._defaultVoiceInstance = a
	manager.keepMainLocaleEngineConsistent = False
	manager.table = [
		module.VoiceMeta("a", a.name, "A", "en", "A", "en"),
		module.VoiceMeta("b", b.name, "B", "fr", "B", "fr"),
	]
	panel_type = _load_panel_class(config, lambda: types.SimpleNamespace(name="WorldVoice"))
	panel = panel_type()
	panel.disable = False
	panel._manager = manager
	panel._editSession = manager.settings.begin_edit()
	panel._dataToPercist = defaultdict(dict)
	panel._initialKeepEngineConsistent = False
	panel._keepEngineConsistentCheckBox = types.SimpleNamespace(GetValue=lambda: True)
	panel._localesChoice = types.SimpleNamespace(SetItems=lambda names: None)
	panel._updateVoicesSelection = lambda: None

	panel.onKeepEngineConsistentChange(None)
	assert manager.keepMainLocaleEngineConsistent is True
	assert config.conf["WorldVoice"]["role"]["fr"]["voice"] == b.name
	panel.onDiscard()
	assert manager.keepMainLocaleEngineConsistent is False
	assert config.conf["WorldVoice"]["role"]["fr"]["voice"] == b.name

	config.conf["speech"] = {"WorldVoice": {"voice": a.name}}
	panel._dataToPercist = defaultdict(dict)
	panel._keepParameterConsistentCheckBox = types.SimpleNamespace(GetValue=lambda: False)
	panel._keepConsistentCheckBox = types.SimpleNamespace(GetValue=lambda: False)
	panel.onKeepEngineConsistentChange(None)
	panel.onSave()
	assert config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"] is True
	panel.onDiscard()
	assert manager.keepMainLocaleEngineConsistent is True


def _editing_panel(monkeypatch):
	module = _load_voice_manager(monkeypatch, {})
	config = sys.modules["config"]
	config.AggregatedSection = dict
	config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"] = False
	config.conf["WorldVoice"]["role"] = {"en": {"voice": "A:a"}}
	a, b = _create_voices(monkeypatch, config)
	config.conf["speech"] = {"WorldVoice": {"voice": a.name}}
	manager = object.__new__(module.VoiceManager)
	manager.settings = a._binding.settings
	manager._instanceCache = {a.name: a}
	manager._defaultVoiceInstance = a
	manager.keepMainLocaleEngineConsistent = False
	manager.table = [a._state.spec, b._state.spec]
	manager.getVoiceInstance = lambda key: {a.name: a, b.name: b}[key]
	errors = []
	panel = _load_panel_class(config, lambda: types.SimpleNamespace(name="WorldVoice"), errors)()
	panel.disable = False
	panel._manager = manager
	panel._editSession = manager.settings.begin_edit()
	panel._initialKeepEngineConsistent = False
	panel._dataToPercist = defaultdict(dict)
	for name in ("_keepParameterConsistentCheckBox", "_keepEngineConsistentCheckBox", "_keepConsistentCheckBox"):
		setattr(panel, name, types.SimpleNamespace(GetValue=lambda: False))
	return panel, manager, a, b, config, errors


def test_dialog_late_voice_is_restored_on_discard(monkeypatch):
	panel, manager, a, b, config, _ = _editing_panel(monkeypatch)
	late = manager.settings.ensure(a._binding.spec_for("Fake:late"))
	late.update(rate=81)
	b.rate = 72  # A known state without a cached facade is in the same edit.
	panel.onDiscard()
	assert late.get("rate") == 50
	assert b.rate == 50
	assert config.conf["WorldVoice"]["voices"][b.name]["rate"] == 50


def test_apply_rebases_voice_and_role_edit_state(monkeypatch):
	panel, manager, a, b, config, _ = _editing_panel(monkeypatch)
	a.rate = 72
	b.rate = 64
	panel._dataToPercist["fr"]["voice"] = b.name
	panel.onSave()
	assert config.conf["WorldVoice"]["voices"][b.name]["rate"] == 64
	assert dict(panel._dataToPercist) == {}
	a.rate = 81
	b.rate = 90
	panel._dataToPercist["fr"]["voice"] = panel.NO_SELECT
	panel.onDiscard()
	assert (a.rate, b.rate) == (72, 64)
	assert config.conf["WorldVoice"]["role"]["fr"]["voice"] == b.name
	assert dict(panel._dataToPercist) == {}


def test_save_failure_keeps_pending_values_and_baseline(monkeypatch):
	panel, manager, a, b, config, errors = _editing_panel(monkeypatch)
	panel._dataToPercist["fr"]["voice"] = b.name
	panel._keepEngineConsistentCheckBox.GetValue = lambda: True
	manager.keepMainLocaleEngineConsistent = True
	a.rate = 72
	def fail_save(*args):
		raise OSError("save failed")
	monkeypatch.setattr(manager.settings._repository, "save", fail_save)
	with pytest.raises(OSError, match="save failed"):
		panel.onSave()
	assert errors
	assert a.rate == 72
	assert a._state.baseline("rate") == 50
	assert panel._initialKeepEngineConsistent is False
	assert config.conf["WorldVoice"]["role"] == {"en": {"voice": a.name}}
	assert panel._dataToPercist["fr"]["voice"] == b.name
	panel.onDiscard()
	assert a.rate == 50
	assert manager.keepMainLocaleEngineConsistent is False


def test_dialog_destroy_releases_edit_session(monkeypatch):
	panel, manager, a, _, _, _ = _editing_panel(monkeypatch)
	skipped = []
	child = types.SimpleNamespace(GetEventObject=lambda: object(), Skip=lambda: skipped.append(True))
	panel._onDestroy(child)
	with pytest.raises(RuntimeError, match="already open"):
		manager.beginVoiceSettingsEdit()
	event = types.SimpleNamespace(GetEventObject=lambda: panel, Skip=lambda: skipped.append(True))
	a.rate = 72
	panel.onDiscard()
	panel._onDestroy(event)
	manager.beginVoiceSettingsEdit().close()
	assert a.rate == 50
	assert skipped == [True, True]


def test_apply_previews_consistency_before_saving_resolver_only_states(monkeypatch):
	panel, manager, a, b, config, _ = _editing_panel(monkeypatch)
	panel._keepParameterConsistentCheckBox.GetValue = lambda: True
	a.update_settings(rate=72, pitch=64)
	panel.onSave()
	assert (b.rate, b.pitch) == (72, 64)
	assert config.conf["WorldVoice"]["voices"][b.name]["rate"] == 72
	b.rate = 90
	panel.onDiscard()
	assert b.rate == 72


def test_panel_queries_capabilities_and_variants_through_manager(monkeypatch):
	panel, manager, a, _, _, _ = _editing_panel(monkeypatch)
	panel._voicesChoice = types.SimpleNamespace(GetCurrentSelection=lambda: 0)
	panel._voiceNamesByChoiceIndex = [a.name]
	manager.getVoiceCapabilities = lambda key: types.SimpleNamespace(settings=frozenset({"rateBoost", "inflection"}))
	manager.getVoiceVariants = lambda key: ({"id": "bright", "name": "Bright"},)
	items = []
	panel._variantsChoice = types.SimpleNamespace(SetItems=lambda values: items.extend(values), Select=lambda index: None)
	assert panel._getVoiceSupportedSettings() == {"rateBoost", "inflection"}
	panel._updateVariantsSelection()
	assert items == ["default", "bright"]


def _synth_settings_class(config):
	path = WORLDVOICE / "__init__.py"
	tree = ast.parse(path.read_text(encoding="utf-8"))
	driver = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SynthDriver")
	names = {"supportedSettings", "_get_availableVariants", "_set_rate"}
	driver.body = [node for node in driver.body if isinstance(node, ast.FunctionDef) and node.name in names]
	driver.bases = []
	setting = lambda name, *args, **kwargs: name
	env = {"_": lambda text: text, "OrderedDict": OrderedDict, "config": config,
		"BooleanDriverSetting": setting, "NumericDriverSetting": setting, "DriverSetting": setting,
		"StringParameterInfo": lambda id, name: types.SimpleNamespace(id=id, name=name)}
	exec(compile(ast.Module(body=[driver], type_ignores=[]), str(path), "exec"), env)
	cls = env["SynthDriver"]
	for name in ("Voice", "Variant", "Rate", "RateBoost", "Pitch", "Inflection", "Volume"):
		setattr(cls, name + "Setting", staticmethod(lambda name=name: name.lower()))
	return cls


def test_main_synth_settings_use_manager_capabilities_and_variants(monkeypatch):
	_, manager, a, _, config, _ = _editing_panel(monkeypatch)
	manager.getVoiceCapabilities = lambda key: types.SimpleNamespace(settings={"rateBoost", "inflection"})
	manager.getVoiceVariants = lambda key: ({"id": "bright", "name": "Bright"},)
	synth = _synth_settings_class(config)()
	synth._voiceManager = manager
	assert {"rateboost", "inflection"} <= set(synth.supportedSettings)
	assert synth._get_availableVariants()["bright"].name == "Bright"


def test_main_synth_explicit_commit_updates_resolver_only_states(monkeypatch):
	_, manager, a, b, config, _ = _editing_panel(monkeypatch)
	config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
	synth = _synth_settings_class(config)()
	synth._voiceManager = manager
	synth._set_rate(72)
	assert config.conf["WorldVoice"]["voices"][a.name]["rate"] == 72
	assert config.conf["WorldVoice"]["voices"][b.name]["rate"] == 72
	b.rate = 81
	b.rollback()
	assert b.rate == 72


@pytest.mark.parametrize("ready", [False, True])
def test_panel_opens_shared_edit_only_when_manager_is_ready(monkeypatch, ready):
	panel, manager, a, _, config, _ = _editing_panel(monkeypatch)
	panel._editSession.close()
	a.rate = 61
	manager.ready = lambda: ready
	manager._getLocaleReadableName = lambda locale: locale
	class Control:
		def __init__(self, *args, **kwargs):
			pass
		def SetValue(self, value):
			pass
		def Disable(self):
			pass
		def Wrap(self, width):
			pass
		def SetBackgroundColour(self, colour):
			pass
	env = panel.makeSettings.__globals__
	env["getSynth"] = lambda: types.SimpleNamespace(name="WorldVoice", _voiceManager=manager)
	for name in ("TextCtrl", "StaticText", "Choice", "Slider", "CheckBox"):
		setattr(env["wx"], name, Control)
	for name in ("EVT_WINDOW_DESTROY", "EVT_CHOICE", "EVT_SLIDER", "EVT_CHECKBOX",
			"TE_READONLY", "TE_MULTILINE", "TE_WORDWRAP", "BORDER_NONE", "EXPAND", "SL_HORIZONTAL"):
		setattr(env["wx"], name, 1)
	env["guiHelper"] = types.SimpleNamespace(BoxSizerHelper=lambda *args, **kwargs: types.SimpleNamespace(
		addLabeledControl=lambda *args, **kwargs: Control(), addItem=lambda *args: None))
	bindings = []
	panel.Bind = lambda event, handler, *args: bindings.append(handler)
	panel.GetSize = lambda: (1000, 480)
	panel.GetBackgroundColour = lambda: None
	panel.makeSettings(types.SimpleNamespace(Add=lambda *args, **kwargs: None))
	if ready:
		assert panel._onDestroy in bindings
		with pytest.raises(RuntimeError, match="already open"):
			manager.beginVoiceSettingsEdit()
		a.rate = 72
		panel.onDiscard()
		assert a.rate == 61  # Opening establishes the current preview baseline.
		panel._onDestroy(types.SimpleNamespace(GetEventObject=lambda: panel, Skip=lambda: None))
	manager.beginVoiceSettingsEdit().close()
