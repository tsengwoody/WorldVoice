import ast
from collections import defaultdict
import importlib.util
import sys
import types
from pathlib import Path

from test_worldvoice_lifecycle import _load_voice_manager, WORLDVOICE


PANEL_PATH = WORLDVOICE.parents[1] / "globalPlugins/WorldVoice/speechSettingsDialog.py"


def _load_panel_class(config, get_synth):
	tree = ast.parse(PANEL_PATH.read_text(encoding="utf-8"))
	panel = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SpeechRoleSettingsPanel")
	environment = {
		"SettingsPanel": object,
		"_": lambda value: value,
		"guard_errors": lambda **kwargs: lambda method: method,
		"got_error_callback": lambda self: None,
		"config": config,
		"getSynth": get_synth,
		"wx": types.SimpleNamespace(NOT_FOUND=-1),
		"defaultdict": defaultdict,
	}
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
	panel_type = _load_panel_class(config, lambda: types.SimpleNamespace(name="WorldVoice"))
	panel = panel_type()
	panel.disable = False
	panel._manager = manager
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
