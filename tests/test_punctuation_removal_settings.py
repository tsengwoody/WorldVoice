import importlib.util
import sys
from types import ModuleType, SimpleNamespace


def load_settings_module(monkeypatch, conf):
	config = ModuleType("config")
	config.conf = conf
	monkeypatch.setitem(sys.modules, "config", config)

	synth_driver_handler = ModuleType("synthDriverHandler")
	synth_driver_handler.getSynth = lambda: SimpleNamespace(name="WorldVoice")
	monkeypatch.setitem(sys.modules, "synthDriverHandler", synth_driver_handler)

	spec = importlib.util.spec_from_file_location(
		"punctuation_settings_under_test",
		"addon/synthDrivers/WorldVoice/pipeline/settings.py",
	)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module


def test_removal_defaults_off_and_round_trips_independently_of_pause(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {"punctuation_wait_factor": 0, "punctuation_pause_enabled": False}}}
	module = load_settings_module(monkeypatch, conf)

	settings = module.load_pipeline_settings(conf)
	assert settings.remove_punctuation_characters is False
	settings.remove_punctuation_characters = True
	module.save_pipeline_settings(settings, conf)

	assert conf["WorldVoice"]["pipeline"]["remove_punctuation_characters"] is True
	assert module.load_pipeline_settings(conf).remove_punctuation_characters is True


def test_removal_follows_pipeline_scope(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {"scope": "WorldVoice", "remove_punctuation_characters": True}}}
	module = load_settings_module(monkeypatch, conf)

	assert module.get_effective_pipeline_settings(SimpleNamespace(name="WorldVoice"), conf).remove_punctuation_characters
	assert not module.get_effective_pipeline_settings(SimpleNamespace(name="Other"), conf).remove_punctuation_characters

	conf["WorldVoice"]["pipeline"]["scope"] = "all"
	assert module.get_effective_pipeline_settings(SimpleNamespace(name="Other"), conf).remove_punctuation_characters


def test_removal_is_applied_to_synth_and_global_speech_settings(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}, "speech": {"WorldVoice": {}}}
	module = load_settings_module(monkeypatch, conf)
	settings = module.load_pipeline_settings(conf)
	settings.remove_punctuation_characters = True
	synth = SimpleNamespace(name="WorldVoice")

	module.apply_pipeline_settings_to_synth(synth, settings)
	module.apply_pipeline_settings_to_speech_config(settings, conf)

	assert synth.removepunctuationcharacters is True
	assert conf["speech"]["WorldVoice"]["removepunctuationcharacters"] is True
	assert module.get_effective_pipeline_settings(synth, conf).remove_punctuation_characters is True
