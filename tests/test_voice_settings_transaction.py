import ast
from collections import OrderedDict
import importlib.util
import sys
import types

from test_worldvoice_lifecycle import _load_voice_manager, WORLDVOICE




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
	voice = install_binding(module, config)
	return voice("a", "A:a", "en"), voice("b", "B:b", "fr")






def _editing_manager(monkeypatch):
	module = _load_voice_manager(monkeypatch, {})
	config = sys.modules["config"]
	config.AggregatedSection = dict
	config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"] = False
	config.conf["WorldVoice"]["role"] = {"en": {"voice": "A:a"}}
	a, b = _create_voices(monkeypatch, config)
	config.conf["speech"] = {"WorldVoice": {"voice": a.name}}
	manager = object.__new__(module.VoiceManager)
	manager._init_policies()
	manager.settings = a._binding.settings
	manager._instanceCache = {a.name: a}
	manager._defaultVoiceInstance = a
	manager.engine_consistency.enabled = False
	manager.catalog = module.VoiceCatalog.from_specs([a._state.spec, b._state.spec])
	manager.getVoiceInstance = lambda key: {a.name: a, b.name: b}[key]
	return manager, a, b, config
















def _synth_settings_class(config):
	path = WORLDVOICE / "__init__.py"
	tree = ast.parse(path.read_text(encoding="utf-8"))
	driver = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SynthDriver")
	names = {"supportedSettings", "_driver_settings", "_pipeline_driver_setting", "_get_availableVariants",
		"_set_rate", "_set_voice_parameter", "_get_voice", "_set_voice"}
	driver.body = [node for node in driver.body if isinstance(node, ast.FunctionDef) and node.name in names]
	driver.bases = []
	setting = lambda name, *args, **kwargs: name
	env = {"_": lambda text: text, "OrderedDict": OrderedDict, "config": config, "PIPELINE_SETTINGS": (),
		"BooleanDriverSetting": setting, "NumericDriverSetting": setting, "DriverSetting": setting,
		"StringParameterInfo": lambda id, name: types.SimpleNamespace(id=id, name=name)}
	exec(compile(ast.Module(body=[driver], type_ignores=[]), str(path), "exec"), env)
	cls = env["SynthDriver"]
	for name in ("Voice", "Variant", "Rate", "RateBoost", "Pitch", "Inflection", "Volume"):
		setattr(cls, name + "Setting", staticmethod(lambda name=name: name.lower()))
	return cls


def test_main_synth_settings_use_manager_capabilities_and_variants(monkeypatch):
	manager, a, _, config = _editing_manager(monkeypatch)
	manager.getVoiceCapabilities = lambda key: types.SimpleNamespace(settings={"rateBoost", "inflection"})
	manager.getVoiceVariants = lambda key: ({"id": "bright", "name": "Bright"},)
	synth = _synth_settings_class(config)()
	synth._voiceManager = manager
	assert {"rateboost", "inflection"} <= set(synth.supportedSettings)
	assert synth._get_availableVariants()["bright"].name == "Bright"


def test_main_synth_explicit_commit_updates_resolver_only_states(monkeypatch):
	manager, a, b, config = _editing_manager(monkeypatch)
	config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
	synth = _synth_settings_class(config)()
	synth._voiceManager = manager
	synth._set_rate(72)
	assert config.conf["WorldVoice"]["voices"][a.name]["rate"] == 72
	assert config.conf["WorldVoice"]["voices"][b.name]["rate"] == 72
	b.rate = 81
	b.rollback()
	assert b.rate == 72


