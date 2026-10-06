"""The pipeline settings table, repository and service."""

from dataclasses import fields
from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, load_source
from nvda_stubs import StubModules


def load_settings_module(monkeypatch, conf, errors=None):
	stubs = StubModules(monkeypatch)
	config = stubs.module("config")
	config.conf = conf
	addon_handler = stubs.module("addonHandler")
	addon_handler.initTranslation = lambda: None
	log_handler = stubs.module("logHandler")
	log_handler.log = SimpleNamespace(
		error=lambda *args, **kwargs: (errors if errors is not None else []).append(args),
	)
	synth_driver_handler = stubs.module("synthDriverHandler")
	synth_driver_handler.getSynth = lambda: None
	stubs.translation()
	return load_source(monkeypatch, "pipeline_settings_under_test", WORLDVOICE / "pipeline/settings.py")


OLD_DEFAULTS = {
	"scope": "WorldVoice",
	"ignore_comma_between_number": False,
	"number_mode": "value",
	"global_wait_factor": 10,
	"number_wait_factor": 10,
	"item_wait_factor": 10,
	"sayall_wait_factor": 10,
	"chinesespace_wait_factor": 10,
	"punctuation_wait_factor": 0,
	"punctuation_pause_enabled": True,
	"remove_punctuation_characters": False,
	"punctuation_pause_characters": "،؛,.;:!؟?…",
	"pair_wait_factor": 0,
}


def test_table_drives_fields_defaults_keys_and_confspec(monkeypatch):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	keys = [spec.key for spec in module.PIPELINE_SETTINGS]
	assert sorted(keys) == sorted(field.name for field in fields(module.PipelineSettings))
	assert module.DEFAULT_PIPELINE_SETTINGS == OLD_DEFAULTS
	assert module.PIPELINE_CONFIG_KEYS == tuple(keys)
	assert module.PIPELINE_CONFSPEC["global_wait_factor"] == "integer(default=10,min=0,max=100)"
	assert module.PIPELINE_CONFSPEC["punctuation_pause_enabled"] == "boolean(default=true)"
	assert module.PIPELINE_CONFSPEC["scope"] == 'string(default="WorldVoice")'
	assert module.PIPELINE_CONFSPEC["punctuation_pause_characters"] == 'string(default="،؛,.;:!؟?…")'
	driver_ids = [spec.driver_id for spec in module.PIPELINE_SETTINGS if spec.driver_id]
	assert driver_ids == [
		"cni",
		"nummod",
		"globalwaitfactor",
		"numberwaitfactor",
		"pairwaitfactor",
		"itemwaitfactor",
		"sayallwaitfactor",
		"chinesespacewaitfactor",
		"punctuationpauseenabled",
		"removepunctuationcharacters",
		"punctuationwaitfactor",
	]
	assert [spec.ring for spec in module.PIPELINE_SETTINGS if spec.driver_id].count(False) == 1
	assert module.PIPELINE_SETTING_BY_KEY["ignore_comma_between_number"].ring is False


def test_get_reads_defaults_and_current_profile(monkeypatch):
	profiles = {
		"normal": {"WorldVoice": {"pipeline": {}}},
		"app": {"WorldVoice": {"pipeline": {"item_wait_factor": 40}}},
	}
	active = ["normal"]
	module = load_settings_module(monkeypatch, profiles["normal"])
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: profiles[active[0]]))
	assert service.get() == module.PipelineSettings(**OLD_DEFAULTS)
	active[0] = "app"
	assert service.get().item_wait_factor == 40


def test_update_converts_normalizes_and_writes_only_changes(monkeypatch):
	writes = []

	class Section(dict):
		def __setitem__(self, key, value):
			writes.append((key, value))
			super().__setitem__(key, value)

	conf = {"WorldVoice": {"pipeline": Section()}}
	module = load_settings_module(monkeypatch, conf)
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))

	result = service.update(
		global_wait_factor="57",
		item_wait_factor=10,
		punctuation_pause_characters="  .,  ",
	)

	assert writes == [("global_wait_factor", 50), ("punctuation_pause_characters", ".,")]
	assert result.global_wait_factor == 50
	assert result.punctuation_pause_characters == ".,"


def test_update_rejects_unknown_keys_before_writing(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	module = load_settings_module(monkeypatch, conf)
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))
	with pytest.raises(KeyError):
		service.update(item_wait_factor=30, no_such_setting=1)
	assert conf["WorldVoice"]["pipeline"] == {}


def test_update_notifies_subscribers_and_survives_a_failing_one(monkeypatch):
	errors = []
	conf = {"WorldVoice": {"pipeline": {}}}
	module = load_settings_module(monkeypatch, conf, errors)
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))
	seen = []

	def failing(settings):
		raise RuntimeError("listener failed")

	service.subscribe(failing)
	service.subscribe(seen.append)
	service.subscribe(seen.append)

	service.update(scope="all")
	service.update(scope="all")
	service.unsubscribe(seen.append)
	service.update(scope="WorldVoice")

	assert [settings.scope for settings in seen] == ["all"]
	assert len(errors) == 2


def test_effective_matches_the_old_synth_scoping(monkeypatch):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	settings = module.PipelineSettings(
		**{
			**OLD_DEFAULTS,
			"ignore_comma_between_number": True,
			"remove_punctuation_characters": True,
			"punctuation_wait_factor": 30,
			"pair_wait_factor": 20,
			"global_wait_factor": 0,
		},
	)
	assert settings.effective(True) is settings
	scoped = settings.effective(False)
	assert (
		scoped.ignore_comma_between_number,
		scoped.number_wait_factor,
		scoped.item_wait_factor,
		scoped.sayall_wait_factor,
		scoped.chinesespace_wait_factor,
		scoped.punctuation_wait_factor,
		scoped.punctuation_pause_enabled,
		scoped.remove_punctuation_characters,
		scoped.pair_wait_factor,
	) == (
		False,
		0,
		0,
		0,
		0,
		0,
		False,
		False,
		0,
	)
	global_scope = module.PipelineSettings(
		**{
			**OLD_DEFAULTS,
			"scope": "all",
			"ignore_comma_between_number": True,
			"global_wait_factor": 0,
			"remove_punctuation_characters": True,
		},
	).effective(False)
	assert global_scope.ignore_comma_between_number is False
	assert global_scope.remove_punctuation_characters is True
	assert (
		module.PipelineSettings(
			**{
				**OLD_DEFAULTS,
				"scope": "all",
				"ignore_comma_between_number": True,
				"global_wait_factor": 10,
			},
		)
		.effective(False)
		.ignore_comma_between_number
		is True
	)
