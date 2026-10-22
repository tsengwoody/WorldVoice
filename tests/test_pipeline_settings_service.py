"""The pipeline settings table, repository and service."""

import sys
from dataclasses import fields

import pytest
from nvda_stubs import RefusingSection
from pipeline_harness import load_settings_module

OLD_DEFAULTS = {
	"scope": "WorldVoice",
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
	"group_size": 3,
}


def test_table_drives_fields_defaults_keys_and_confspec(monkeypatch):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	keys = [spec.key for spec in module.PIPELINE_STORED_SETTINGS]
	assert sorted(keys) == sorted(field.name for field in fields(module.PipelineSettings))
	assert module.DEFAULT_PIPELINE_SETTINGS == OLD_DEFAULTS
	assert module.PIPELINE_CONFIG_KEYS == tuple(keys)
	assert module.PIPELINE_CONFSPEC["global_wait_factor"] == "integer(default=10,min=0,max=100)"
	assert module.PIPELINE_CONFSPEC["punctuation_pause_enabled"] == "boolean(default=true)"
	assert module.PIPELINE_CONFSPEC["scope"] == 'string(default="WorldVoice")'
	assert module.PIPELINE_CONFSPEC["punctuation_pause_characters"] == 'string(default="")'
	driver_ids = [spec.driver_id for spec in module.PIPELINE_SETTINGS if spec.driver_id]
	assert driver_ids == [
		"globalwaitfactor",
		"numlan",
		"nummod",
		"numberwaitfactor",
		"itemwaitfactor",
		"sayallwaitfactor",
		"chinesespacewaitfactor",
		"punctuationpauseenabled",
		"removepunctuationcharacters",
		"punctuationwaitfactor",
	]
	assert all(spec.ring for spec in module.PIPELINE_SETTINGS if spec.driver_id)


def test_number_mode_choices_put_off_first(monkeypatch):
	# Decided by the user (2026-10-22): "off" leaves numbers alone; the default stays "value".
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert module.NUMBER_MODE_CHOICES == (
		("none", "off"),
		("value", "value"),
		("number", "number"),
		("group", "group"),
	)
	assert module.PIPELINE_SETTING_BY_KEY["number_mode"].default == "value"


def test_group_size_confspec_is_its_range(monkeypatch):
	# Decided by the user (2026-10-22): integer(default=3,min=2,max=10); NVDA refuses a stored
	# value outside it, so it reads as 3 (read_stored), and convert resets it the same way.
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	spec = module.PIPELINE_SETTING_BY_KEY["group_size"]
	assert (spec.min_value, spec.max_value, spec.default, spec.reset_out_of_range) == (2, 10, 3, True)
	assert module.PIPELINE_CONFSPEC["group_size"] == "integer(default=3,min=2,max=10)"
	assert not hasattr(spec, "stored_min_value")
	assert [other.key for other in module.PIPELINE_SETTINGS if other.reset_out_of_range] == ["group_size"]


def test_group_wait_setting_is_gone(monkeypatch):
	# Decided by the user (2026-10-22): groups and symbols are separated by the number wait; no migration.
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert "group_wait_factor" not in module.PIPELINE_CONFIG_KEYS
	assert "group_wait_factor" not in {field.name for field in fields(module.PipelineSettings)}
	assert "groupwaitfactor" not in {spec.driver_id for spec in module.PIPELINE_SETTINGS}
	assert not hasattr(module.PipelineSettings, "scaled_group_wait")
	assert not hasattr(module, "GROUP_WAIT_UNIT_MS")


def test_ignore_comma_option_is_gone(monkeypatch):
	# Decided by the user (2026-10-22): value mode removes thousands separators instead; no migration.
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert "ignore_comma_between_number" not in module.PIPELINE_CONFIG_KEYS
	assert "ignore_comma_between_number" not in {field.name for field in fields(module.PipelineSettings)}
	assert "cni" not in {spec.driver_id for spec in module.PIPELINE_SETTINGS}


def test_table_lists_every_setting_in_the_canonical_order(monkeypatch):
	# Every panel and the settings ring follow this order, decided by the user on 2026-10-21.
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert [spec.key for spec in module.PIPELINE_SETTINGS] == [
		"scope",
		"global_wait_factor",
		"number_language",
		"number_mode",
		"group_size",
		"number_wait_factor",
		"item_wait_factor",
		"sayall_wait_factor",
		"chinesespace_wait_factor",
		"punctuation_pause_enabled",
		"remove_punctuation_characters",
		"punctuation_wait_factor",
		"punctuation_pause_characters",
	]
	assert module.NUMBER_MODES == ("none", "value", "number", "group")


def test_number_language_is_ordering_only(monkeypatch):
	# NVDA stores number language as a driver setting; the table only places it.
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert [spec.key for spec in module.PIPELINE_SETTINGS if not spec.pipeline_config] == ["number_language"]
	for keys in (
		module.PIPELINE_SETTING_BY_KEY,
		module.PIPELINE_CONFSPEC,
		module.PIPELINE_CONFIG_KEYS,
		module.DEFAULT_PIPELINE_SETTINGS,
		[field.name for field in fields(module.PipelineSettings)],
	):
		assert "number_language" not in keys
	with pytest.raises(KeyError, match="Unknown pipeline setting: number_language"):
		module.pipeline_settings.update(number_language="en")


def test_int_confspec_carries_the_spec_bounds(monkeypatch):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	bounded = module.PipelineSettingSpec("x", int, 3, min_value=1, max_value=10)
	assert bounded.confspec == "integer(default=3,min=1,max=10)"
	# Every int key that existed before the group size keeps its exact confspec string.
	for spec in module.PIPELINE_SETTINGS:
		if spec.kind is int and spec.key != "group_size":
			assert spec.confspec == f"integer(default={spec.default},min=0,max=100)"


@pytest.mark.parametrize(
	("key", "raw", "expected"),
	[
		("number_wait_factor", 150, 100),
		("number_wait_factor", -3, 0),
		# The global factor is floored to tens first, then clamped.
		("global_wait_factor", "57", 50),
		("global_wait_factor", 150, 100),
		("global_wait_factor", -5, 0),
	],
)
def test_convert_clamps_ints_to_their_bounds(monkeypatch, key, raw, expected):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert module.PIPELINE_SETTING_BY_KEY[key].convert(raw) == expected


@pytest.mark.parametrize(
	("raw", "expected"),
	[(0, 3), (-5, 3), (1, 3), (11, 3), (99, 3), (2, 2), (10, 10), ("7", 7)],
)
def test_group_size_outside_its_range_reads_as_the_default(monkeypatch, raw, expected):
	# Decided by the user (2026-10-22): outside 2..10 is 3, not clamped.
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert module.PIPELINE_SETTING_BY_KEY["group_size"].convert(raw) == expected


def test_group_settings_add_the_size_without_a_wait(monkeypatch):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert module.PIPELINE_CONFSPEC["group_size"] == "integer(default=3,min=2,max=10)"
	assert "pair_wait_factor" not in module.PIPELINE_CONFSPEC
	assert module.PIPELINE_SETTING_BY_KEY["group_size"].driver_id is None
	assert module.PIPELINE_CONFIG_KEYS[-1] == "punctuation_pause_characters"


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


@pytest.mark.parametrize(
	("raw", "expected"),
	[
		("pair", "value"),
		("roman", "value"),
		("", "value"),
		(None, "value"),
		("value", "value"),
		("number", "number"),
		("group", "group"),
		("none", "none"),
	],
)
def test_number_mode_reads_and_writes_only_known_modes(monkeypatch, raw, expected):
	writes = []

	class Section(dict):
		def __setitem__(self, key, value):
			writes.append((key, value))
			super().__setitem__(key, value)

	stored = {"WorldVoice": {"pipeline": {"number_mode": raw}}}
	conf = {"WorldVoice": {"pipeline": Section(number_mode="number")}}
	module = load_settings_module(monkeypatch, conf)
	assert module.PipelineSettingsService(
		module.ConfigPipelineRepository(lambda: stored),
	).get().number_mode == (expected)
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))
	assert service.update(number_mode=raw).number_mode == expected
	# Only a change is written: "number" normalises to the stored value, so nothing is.
	assert writes == ([] if expected == "number" else [("number_mode", expected)])


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
			"remove_punctuation_characters": True,
			"punctuation_wait_factor": 30,
			"group_size": 5,
			"global_wait_factor": 0,
		},
	)
	assert settings.effective(True) is settings
	scoped = settings.effective(False)
	assert (
		scoped.number_wait_factor,
		scoped.item_wait_factor,
		scoped.sayall_wait_factor,
		scoped.chinesespace_wait_factor,
		scoped.punctuation_wait_factor,
		scoped.punctuation_pause_enabled,
		scoped.remove_punctuation_characters,
		scoped.group_size,
	) == (
		0,
		0,
		0,
		0,
		0,
		False,
		False,
		5,
	)
	# Scope "all": other synthesizers get the settings as stored, whatever the global wait (V6).
	global_scope = module.PipelineSettings(
		**{
			**OLD_DEFAULTS,
			"scope": "all",
			"global_wait_factor": 0,
			"remove_punctuation_characters": True,
		},
	)
	assert global_scope.effective(False) is global_scope


@pytest.mark.parametrize(
	("changes", "method", "expected"),
	[
		# The global factor scales in whole tens; what is left over is dropped.
		({"global_wait_factor": 25, "number_wait_factor": 7}, "scaled_number_wait", 14),
		({"global_wait_factor": 30, "item_wait_factor": 4}, "scaled_item_wait", 12),
		({"global_wait_factor": 9, "sayall_wait_factor": 50}, "scaled_sayall_wait", 0),
		({"global_wait_factor": 10, "chinesespace_wait_factor": 6}, "scaled_chinesespace_wait", 6),
		# Punctuation and group pauses ignore the global factor: 5 ms a step, at most 500 ms.
		({"global_wait_factor": 0, "punctuation_wait_factor": 30}, "scaled_punctuation_wait", 150),
		({"punctuation_wait_factor": 100}, "scaled_punctuation_wait", 500),
		({"punctuation_wait_factor": 101}, "scaled_punctuation_wait", 500),
	],
)
def test_scaled_waits_follow_their_units_and_caps(monkeypatch, changes, method, expected):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	settings = module.PipelineSettings(**{**OLD_DEFAULTS, **changes})
	assert getattr(settings, method)() == expected


def refusing_conf(values=(), refused=None):
	return {"WorldVoice": {"pipeline": RefusingSection(values, refused)}}


def test_read_stored_returns_the_default_for_an_invalid_value_and_warns_once(monkeypatch):
	# Decided by the user (2026-10-22, Q3 and D3): the default, nothing written back, one debug warning.
	warnings = []
	conf = refusing_conf()
	module = load_settings_module(monkeypatch, conf, warnings=warnings)
	too_big = sys.modules["configobj.validate"].VdtValueTooBigError
	section = conf["WorldVoice"]["pipeline"]
	section.refused["group_size"] = too_big(11)
	assert module.read_stored(section, "group_size", 3) == 3
	assert module.read_stored(section, "group_size", 3) == 3
	assert len(warnings) == 1
	assert "'group_size'" in warnings[0][0] and '"11"' in warnings[0][0]
	assert dict(section) == {}


@pytest.mark.parametrize("key", list(OLD_DEFAULTS))
def test_load_reads_the_default_for_each_invalid_key(monkeypatch, key):
	# Decided by the user (2026-10-22, decision A): every pipeline key falls back on its own.
	other = "number_wait_factor" if key == "item_wait_factor" else "item_wait_factor"
	conf = refusing_conf({other: 40})
	module = load_settings_module(monkeypatch, conf)
	wrong_type = sys.modules["configobj.validate"].VdtTypeError
	conf["WorldVoice"]["pipeline"].refused[key] = wrong_type("abc")
	loaded = module.ConfigPipelineRepository(lambda: conf).load()
	assert getattr(loaded, key) == module.PIPELINE_SETTING_BY_KEY[key].convert(OLD_DEFAULTS[key])
	assert getattr(loaded, other) == 40


def test_a_new_invalid_value_warns_again(monkeypatch):
	warnings = []
	conf = refusing_conf()
	module = load_settings_module(monkeypatch, conf, warnings=warnings)
	too_big = sys.modules["configobj.validate"].VdtValueTooBigError
	repository = module.ConfigPipelineRepository(lambda: conf)
	for value in (11, 11, 12):
		conf["WorldVoice"]["pipeline"].refused["group_size"] = too_big(value)
		assert repository.load().group_size == 3
	assert [('"11"' in args[0], '"12"' in args[0]) for args in warnings] == [(True, False), (False, True)]


@pytest.mark.parametrize("source", ["configobj.validate", "validate", None])
def test_validate_error_comes_from_configobj(monkeypatch, source):
	# NVDA imports it from configobj.validate; the top-level shim is configobj's older home. With
	# neither, any error reading a value falls back, so WorldVoice still loads.
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}}, validate=source)
	expected = sys.modules[source].ValidateError if source else Exception
	assert module.ValidateError is expected
