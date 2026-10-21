"""The pipeline settings table, repository and service."""

from dataclasses import fields

import pytest
from pipeline_harness import load_settings_module

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
	"punctuation_pause_characters": "",
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
	assert module.PIPELINE_CONFSPEC["punctuation_pause_characters"] == 'string(default="")'
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


@pytest.mark.parametrize(
	("changes", "method", "expected"),
	[
		# The global factor scales in whole tens; what is left over is dropped.
		({"global_wait_factor": 25, "number_wait_factor": 7}, "scaled_number_wait", 14),
		({"global_wait_factor": 30, "item_wait_factor": 4}, "scaled_item_wait", 12),
		({"global_wait_factor": 9, "sayall_wait_factor": 50}, "scaled_sayall_wait", 0),
		({"global_wait_factor": 10, "chinesespace_wait_factor": 6}, "scaled_chinesespace_wait", 6),
		# Punctuation and pair pauses ignore the global factor: 5 ms a step, at most 500 ms.
		({"global_wait_factor": 0, "punctuation_wait_factor": 30}, "scaled_punctuation_wait", 150),
		({"punctuation_wait_factor": 100}, "scaled_punctuation_wait", 500),
		({"punctuation_wait_factor": 101}, "scaled_punctuation_wait", 500),
		({"pair_wait_factor": 20}, "scaled_pair_wait", 100),
		({"pair_wait_factor": 200}, "scaled_pair_wait", 500),
	],
)
def test_scaled_waits_follow_their_units_and_caps(monkeypatch, changes, method, expected):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	settings = module.PipelineSettings(**{**OLD_DEFAULTS, **changes})
	assert getattr(settings, method)() == expected
