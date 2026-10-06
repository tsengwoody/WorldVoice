import sys
import types
from collections import OrderedDict

import pytest
from addon_loader import WORLDVOICE, load_definitions, load_source
from worldvoice_harness import chosen_voice, init_policies, load_voice_manager


def _create_voices(monkeypatch, config):
	package_name = "lifecycle_test_worldvoice"
	module = load_source(monkeypatch, f"{package_name}.driver", WORLDVOICE / "driver/__init__.py")
	config.conf["WorldVoice"]["voices"] = {}
	config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = False
	from voice_binding_harness import install_binding

	voice = install_binding(module, config)
	return voice("a", "A:a", "en"), voice("b", "B:b", "fr")


def _editing_manager(monkeypatch):
	module = load_voice_manager(monkeypatch)
	config = sys.modules["config"]
	config.AggregatedSection = dict
	config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"] = False
	config.conf["WorldVoice"]["role"] = {"en": {"voice": "A:a"}}
	a, b = _create_voices(monkeypatch, config)
	config.conf["speech"] = {"WorldVoice": {"voice": a.name}}
	manager = object.__new__(module.VoiceManager)
	init_policies(manager)
	manager.settings = a._binding.settings
	manager._instanceCache = {a.name: a}
	manager._defaultVoiceInstance = a
	manager.engine_consistency.enabled = False
	manager.catalog = module.VoiceCatalog.from_specs([a._state.spec, b._state.spec])
	manager.getVoiceInstance = lambda key: {a.name: a, b.name: b}[key]
	return manager, a, b, config


def _synth_settings_class(config):
	names = {
		"supportedSettings",
		"_driver_settings",
		"_pipeline_driver_setting",
		"_get_availableVariants",
		"_set_rate",
		"_set_voice_parameter",
		"_get_voice",
		"_set_voice",
	}
	setting = lambda name, *args, **kwargs: name
	env = {
		"_": lambda text: text,
		"OrderedDict": OrderedDict,
		"config": config,
		"PIPELINE_SETTINGS": (),
		"languageHandler": types.SimpleNamespace(getLanguage=lambda: "fr"),
		"BooleanDriverSetting": setting,
		"NumericDriverSetting": setting,
		"DriverSetting": setting,
		"StringParameterInfo": lambda id, name: types.SimpleNamespace(id=id, name=name),
	}
	cls = load_definitions(WORLDVOICE / "__init__.py", ["SynthDriver"], env, members=names)["SynthDriver"]
	for name in ("Voice", "Variant", "Rate", "RateBoost", "Pitch", "Inflection", "Volume"):
		setattr(cls, name + "Setting", staticmethod(lambda name=name: name.lower()))
	return cls


def test_main_synth_settings_use_manager_capabilities_and_variants(monkeypatch):
	manager, _a, _, config = _editing_manager(monkeypatch)
	manager.getVoiceCapabilities = lambda key: types.SimpleNamespace(settings={"rateBoost", "inflection"})
	manager.getVoiceVariants = lambda key: ({"id": "bright", "name": "Bright"},)
	synth = _synth_settings_class(config)()
	synth._voiceManager = manager
	assert {"rateboost", "inflection"} <= set(synth.supportedSettings)
	assert synth._get_availableVariants()["bright"].name == "Bright"


def test_main_voice_follows_the_nvda_language_until_one_is_chosen(monkeypatch):
	manager, a, b, config = _editing_manager(monkeypatch)
	manager.roles.assign("fr", b.name)
	synth = _synth_settings_class(config)()
	synth._voiceManager = manager
	synth._voice = None
	assert synth._get_voice() == b.name
	synth._voice = b.name
	assert synth._get_voice() == manager.defaultVoiceName == a.name


def test_main_synth_explicit_commit_updates_resolver_only_states(monkeypatch):
	manager, a, b, config = _editing_manager(monkeypatch)
	config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
	synth = _synth_settings_class(config)()
	synth._voiceManager = manager
	synth._set_rate(72)
	assert config.conf["WorldVoice"]["voices"][a.name]["rate"] == 72
	assert config.conf["WorldVoice"]["voices"][b.name]["rate"] == 72
	b.rate = 81
	b._binding.settings.rollback(b.name)
	assert b.rate == 72


def test_main_synth_records_a_chosen_voice_only_once_it_is_set(monkeypatch):
	manager, a, b, config = _editing_manager(monkeypatch)
	synth = _synth_settings_class(config)()
	synth._voiceManager = manager
	synth._voice = None
	with pytest.raises(LookupError):
		synth._set_voice("Missing:x")
	assert chosen_voice(synth) is None
	assert manager.defaultVoiceName == a.name
	synth._set_voice(b.name)
	assert chosen_voice(synth) == b.name
	assert manager.defaultVoiceName == b.name
