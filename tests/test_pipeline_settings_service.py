"""The pipeline settings table, repository and service."""

import inspect
import sys
from dataclasses import asdict, fields

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
	"unspaced_script_space_wait_factor": 10,
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
		"globalWaitFactor",
		"numlan",
		"nummod",
		"numberWaitFactor",
		"itemWaitFactor",
		"sayAllWaitFactor",
		"unspacedScriptSpaceWaitFactor",
		"punctuationPauseEnabled",
		"removePunctuationCharacters",
		"punctuationWaitFactor",
	]
	assert all(spec.ring for spec in module.PIPELINE_SETTINGS if spec.driver_id)


@pytest.mark.parametrize(
	("field", "stored"),
	[
		("scope", "scope"),
		("number_mode", "numberMode"),
		# NVDA spells "say all" sayAll in its own keys.
		("sayall_wait_factor", "sayAllWaitFactor"),
		("unspaced_script_space_wait_factor", "unspacedScriptSpaceWaitFactor"),
	],
)
def test_stored_key_is_nvda_camel_case_of_the_field(monkeypatch, field, stored):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert module.stored_key_for(field) == stored


def test_every_entry_reads_its_stored_key_from_the_derivation(monkeypatch):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert all(spec.stored_key == module.stored_key_for(spec.key) for spec in module.PIPELINE_SETTINGS)
	assert [spec.stored_key for spec in module.PIPELINE_STORED_SETTINGS] == [
		"scope",
		"globalWaitFactor",
		"numberMode",
		"groupSize",
		"numberWaitFactor",
		"itemWaitFactor",
		"sayAllWaitFactor",
		"unspacedScriptSpaceWaitFactor",
		"punctuationPauseEnabled",
		"removePunctuationCharacters",
		"punctuationWaitFactor",
		"punctuationPauseCharacters",
	]


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


def test_punctuation_wait_has_no_unit_or_cap_of_its_own(monkeypatch):
	# Decided by the user (2026-10-26): no 5 ms unit and no 500 ms cap; no migration of stored values.
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert not hasattr(module, "PUNCTUATION_WAIT_UNIT_MS")
	assert not hasattr(module, "MAX_PUNCTUATION_WAIT_MS")
	assert module.PIPELINE_CONFSPEC["punctuation_wait_factor"] == "integer(default=0,min=0,max=100)"


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
		"unspaced_script_space_wait_factor",
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


def test_update_converts_normalizes_and_writes_every_passed_key(monkeypatch):
	# Decided by the user (2026-10-22, fix/uniform-settings-save): a save writes every value it is
	# given, and NVDA's __setitem__ skips one equal to the current value.
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

	assert writes == [
		("global_wait_factor", 50),
		("item_wait_factor", 10),
		("punctuation_pause_characters", "  .,  "),
	]
	assert result.global_wait_factor == 50
	assert result.punctuation_pause_characters == "  .,  "


@pytest.mark.parametrize(
	"characters",
	[" ", "\uff0c ", " \uff0c", "\u3000", "\u00a0", "\t", "\uff0c\n\u3002", ""],
	ids=[
		"space",
		"trailing space",
		"leading space",
		"ideographic space",
		"no-break space",
		"tab",
		"newline",
		"empty",
	],
)
def test_the_characters_are_stored_and_read_exactly_as_typed(monkeypatch, characters):
	# Decided by the user (2026-10-23): every character typed is kept, spaces included.
	conf = {"WorldVoice": {"pipeline": {}}}
	module = load_settings_module(monkeypatch, conf)
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))

	result = service.update(punctuation_pause_characters=characters)

	assert conf["WorldVoice"]["pipeline"]["punctuation_pause_characters"] == characters
	assert result.punctuation_pause_characters == characters
	assert service.get().punctuation_pause_characters == characters


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
	# Every passed key is written, normalised; NVDA skips the one equal to the stored value.
	assert writes == [("number_mode", expected)]


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
		scoped.unspaced_script_space_wait_factor,
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
		(
			{"global_wait_factor": 10, "unspaced_script_space_wait_factor": 6},
			"scaled_unspaced_script_space_wait",
			6,
		),
		(
			{"global_wait_factor": 9, "unspaced_script_space_wait_factor": 6},
			"scaled_unspaced_script_space_wait",
			0,
		),
		# The punctuation pause follows the global factor like every other pause, with no cap
		# (decided by the user, 2026-10-26).
		({"global_wait_factor": 0, "punctuation_wait_factor": 30}, "scaled_punctuation_wait", 0),
		({"global_wait_factor": 9, "punctuation_wait_factor": 30}, "scaled_punctuation_wait", 0),
		({"global_wait_factor": 10, "punctuation_wait_factor": 30}, "scaled_punctuation_wait", 30),
		({"global_wait_factor": 25, "punctuation_wait_factor": 7}, "scaled_punctuation_wait", 14),
		({"global_wait_factor": 100, "punctuation_wait_factor": 100}, "scaled_punctuation_wait", 1000),
	],
)
def test_scaled_waits_are_the_global_units_times_the_factor(monkeypatch, changes, method, expected):
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


def nvda_conf(values=(), refused=None):
	"""A pipeline section that refuses and skips like NVDA's, with the pipeline defaults."""
	section = RefusingSection(values, refused, defaults=OLD_DEFAULTS)
	return {"WorldVoice": {"pipeline": section}}, section


@pytest.mark.parametrize("key", list(OLD_DEFAULTS))
def test_a_panel_save_writes_the_default_over_a_refused_value(monkeypatch, key):
	# Decided by the user (2026-10-22, fix/uniform-settings-save): a save writes every value the
	# panel shows, and a refused value shows as the default; NVDA writes only what differs.
	other = "number_wait_factor" if key == "item_wait_factor" else "item_wait_factor"
	conf, section = nvda_conf({key: "abc", other: 40})
	module = load_settings_module(monkeypatch, conf)
	section.refused[key] = sys.modules["configobj.validate"].VdtTypeError("abc")
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))
	seen = []
	service.subscribe(seen.append)
	shown = asdict(service.get())
	service.update(**shown)
	assert section.written == [key]
	assert dict(section) == {key: shown[key], other: 40}
	# The effective settings did not change, so no subscriber is told.
	assert seen == []
	# Repaired: the same save again writes nothing.
	service.update(**shown)
	assert section.written == [key]


@pytest.mark.parametrize(
	("key", "stored", "shown"),
	[
		("global_wait_factor", 57, 50),
		("number_mode", "pair", "value"),
	],
)
def test_a_panel_save_rewrites_a_valid_stored_value_in_its_shown_form(monkeypatch, key, stored, shown):
	# NVDA accepts the stored value, but it reads as another; the save writes what the panel shows.
	conf, section = nvda_conf({key: stored})
	module = load_settings_module(monkeypatch, conf)
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))
	seen = []
	service.subscribe(seen.append)
	values = asdict(service.get())
	assert values[key] == shown
	service.update(**values)
	assert section.written == [key]
	assert dict(section) == {key: shown}
	assert seen == []


def test_subscribers_hear_only_a_real_change(monkeypatch):
	conf, section = nvda_conf({"item_wait_factor": 40})
	module = load_settings_module(monkeypatch, conf)
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))
	seen = []
	service.subscribe(seen.append)
	values = asdict(service.get())
	assert service.update(**values) == service.get()
	assert seen == []
	service.update(**{**values, "scope": "all"})
	assert [settings.scope for settings in seen] == ["all"]
	assert section.written == ["scope"]


def test_a_save_writes_every_passed_key_even_unchanged(monkeypatch):
	writes = []

	class Section(dict):
		def __setitem__(self, key, value):
			writes.append((key, value))
			super().__setitem__(key, value)

	conf = {"WorldVoice": {"pipeline": Section(item_wait_factor=40)}}
	module = load_settings_module(monkeypatch, conf)
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))
	seen = []
	service.subscribe(seen.append)
	service.update(**asdict(service.get()))
	assert sorted(key for key, _value in writes) == sorted(module.PIPELINE_CONFIG_KEYS)
	assert seen == []


def test_the_refused_key_bookkeeping_is_gone(monkeypatch):
	# The save writes every key, so the repository no longer tracks which keys NVDA refused.
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert not hasattr(module.ConfigPipelineRepository, "fallen_back")
	assert "on_fallback" not in inspect.signature(module.read_stored).parameters


def test_a_save_leaves_a_refused_key_it_does_not_name(monkeypatch):
	# The settings ring saves one key; only a save that names the refused key rewrites it.
	conf, section = nvda_conf({"group_size": 11})
	module = load_settings_module(monkeypatch, conf)
	section.refused["group_size"] = sys.modules["configobj.validate"].VdtValueTooBigError(11)
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))
	assert service.update(item_wait_factor=30).group_size == 3
	assert section.written == ["item_wait_factor"]
	assert dict(section) == {"group_size": 11, "item_wait_factor": 30}


@pytest.mark.parametrize("source", ["configobj.validate", "validate"])
def test_validate_error_comes_from_configobj(monkeypatch, source):
	# NVDA imports it from configobj.validate; the top-level shim is configobj's older home.
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}}, validate=source)
	assert module.ValidateError is sys.modules[source].ValidateError


def test_without_configobj_a_read_error_is_not_hidden(monkeypatch):
	# NVDA cannot run without configobj, so this branch is unreachable there. If it is ever
	# reached, a bug in reading a value must still raise rather than read as the default.
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}}, validate=None)
	assert issubclass(module.ValidateError, Exception)
	assert module.ValidateError is not Exception

	class Broken:
		def get(self, key, default):
			raise TypeError("a bug")

	with pytest.raises(TypeError):
		module.read_stored(Broken(), "group_size", 3)
