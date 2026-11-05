import builtins

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from nvda_stubs import worldvoice_conf
from runtime_harness import load_settings_repository, make_spec

DEFAULTS = {
	"rate": 50,
	"pitch": 50,
	"volume": 50,
	"variant": "default",
	"inflection": 50,
	"rateBoost": False,
}


@pytest.fixture
def conf():
	return {
		**worldvoice_conf(),
		"speech": {"WorldVoice": {"rate": "83", "variant": "main", "rateBoost": "True"}},
	}


@pytest.fixture
def repository(monkeypatch, rt, conf):
	module = load_settings_repository(monkeypatch, rt)
	return module.ConfigVoiceSettingsRepository(lambda: conf)


def test_load_converts_existing_values_and_defaults_missing_fields(repository, conf):
	conf["WorldVoice"]["voices"]["Fake:a"] = {
		"rate": "72",
		"pitch": "63",
		"volume": "84",
		"inflection": "35",
		"variant": "bright",
		"rateBoost": "False",
		"waitfactor": 9,
	}
	values = repository.load(make_spec())
	assert values == {
		"rate": 72,
		"pitch": 63,
		"volume": 84,
		"inflection": 35,
		"variant": "bright",
		"rateBoost": False,
	}
	conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "72", "pitch": None}
	assert repository.load(make_spec()) == dict(DEFAULTS, rate=72)


def test_load_reads_the_legacy_empty_variant_as_default(repository, conf):
	# WorldVoice 3.x stored "" for the default variant.
	conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "72", "variant": ""}
	assert repository.load(make_spec()) == dict(DEFAULTS, rate=72)


class RecordingLogger:
	def __init__(self):
		self.records = []

	def log(self, level, message, *args):
		self.records.append((level, message % args))


@pytest.fixture
def logger():
	return RecordingLogger()


@pytest.fixture
def tolerant(monkeypatch, rt, conf, logger):
	module = load_settings_repository(monkeypatch, rt)
	return module.ConfigVoiceSettingsRepository(lambda: conf, logger=logger)


@pytest.mark.parametrize("stored", ["abc", "", "50.0", "1e2", ["1", "2"]])
def test_load_uses_the_default_for_a_stored_value_int_refuses(tolerant, conf, logger, stored):
	# "50.0" is refused like pipeline's int convert and NVDA's integer validator refuse it;
	# a list is what configobj makes of "rate = 1, 2".
	conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": stored, "pitch": "61", "variant": "bright"}
	assert tolerant.load(make_spec()) == dict(DEFAULTS, pitch=61, variant="bright")
	assert logger.records == [
		(
			15,
			f"WorldVoice: stored voice setting 'rate' of 'Fake:a' is invalid ({stored!r}); using its default 50",
		),
	]


def test_load_leaves_an_invalid_stored_value_in_the_config(tolerant, conf):
	conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "abc"}
	tolerant.load(make_spec())
	assert conf["WorldVoice"]["voices"]["Fake:a"] == {"rate": "abc"}


def test_each_invalid_stored_value_is_reported_once(tolerant, conf, logger):
	conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "abc", "volume": "x"}
	for _ in range(3):
		assert tolerant.load(make_spec()) == DEFAULTS
	assert [message.split(" is ")[0] for _, message in logger.records] == [
		"WorldVoice: stored voice setting 'rate' of 'Fake:a'",
		"WorldVoice: stored voice setting 'volume' of 'Fake:a'",
	]
	conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "xyz"}
	conf["WorldVoice"]["voices"]["Fake:b"] = {"rate": "abc"}
	tolerant.load(make_spec())
	tolerant.load(make_spec("Fake:b"))
	assert len(logger.records) == 4


@pytest.mark.parametrize("stored", ["150", "101", "-5", "-1", 250, -1])
def test_load_uses_the_default_for_a_stored_int_outside_the_bounds(tolerant, conf, logger, stored):
	# An out-of-range value is invalid, not a request to approximate (decided by the user, 2026-11-05).
	conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": stored, "pitch": "61", "inflection": stored}
	for _ in range(3):
		assert tolerant.load(make_spec()) == dict(DEFAULTS, pitch=61)
	assert logger.records == [
		(
			15,
			f"WorldVoice: stored voice setting {name!r} of 'Fake:a' is invalid ({stored!r}); using its default 50",
		)
		for name in ("rate", "inflection")
	]
	assert conf["WorldVoice"]["voices"]["Fake:a"]["rate"] == stored


@pytest.mark.parametrize("stored", ["0", "100", 0, 100])
def test_load_keeps_the_bounds_of_the_int_parameters_without_a_log(tolerant, conf, logger, stored):
	conf["WorldVoice"]["voices"]["Fake:a"] = {
		name: stored for name in ("rate", "pitch", "volume", "inflection")
	}
	expected = int(stored)
	assert tolerant.load(make_spec()) == dict(
		DEFAULTS,
		rate=expected,
		pitch=expected,
		volume=expected,
		inflection=expected,
	)
	assert logger.records == []


def test_the_default_logger_is_the_modules_stdlib_logger(repository, conf, caplog):
	conf["WorldVoice"]["voices"]["Fake:a"] = {"pitch": "high"}
	with caplog.at_level(15):
		assert repository.load(make_spec()) == DEFAULTS
	assert [(record.levelno, record.name.rsplit(".", 1)[-1]) for record in caplog.records] == [
		(15, "settingsRepository"),
	]


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.dictionaries(st.sampled_from(list(DEFAULTS)), st.text() | st.integers() | st.none()))
def test_load_never_raises_and_keeps_ints_in_range(tolerant, conf, stored):
	# Each example replaces the voice's section, so the shared fixtures carry nothing over.
	conf["WorldVoice"]["voices"]["Fake:a"] = stored
	values = tolerant.load(make_spec())
	assert set(values) == set(DEFAULTS)
	assert all(0 <= values[name] <= 100 for name in ("rate", "pitch", "volume", "inflection"))
	assert isinstance(values["variant"], str) and values["variant"] != ""
	assert isinstance(values["rateBoost"], bool)


def test_save_converts_six_values_and_does_not_add_waitfactor(repository, conf):
	repository.save(make_spec(), dict(DEFAULTS, rate="72", variant=42, rateBoost="False", waitfactor=8))
	assert conf["WorldVoice"]["voices"]["Fake:a"] == dict(DEFAULTS, rate=72, variant="42")


def test_save_preserves_unrelated_config_values(repository, conf):
	conf["WorldVoice"]["voices"]["Fake:a"] = {"other": "retain", "waitfactor": 9}
	repository.save(make_spec(), dict(DEFAULTS, rate=72, waitfactor=8))
	assert conf["WorldVoice"]["voices"]["Fake:a"] == dict(DEFAULTS, rate=72, other="retain", waitfactor=9)


def test_repository_load_and_save_need_no_nvda_or_engine_imports(monkeypatch, rt, conf):
	original_import = builtins.__import__

	def guarded_import(name, *args, **kwargs):
		if (
			name in {"config", "synthDriverHandler", "logHandler"}
			or "driver" in name.lower()
			or "session" in name.lower()
		):
			raise AssertionError(f"Unexpected dependency: {name}")
		return original_import(name, *args, **kwargs)

	monkeypatch.setattr(builtins, "__import__", guarded_import)
	repository = load_settings_repository(monkeypatch, rt).ConfigVoiceSettingsRepository(lambda: conf)
	values = repository.load(make_spec())
	repository.save(make_spec(), values)
	assert conf["WorldVoice"]["voices"]["Fake:a"] == DEFAULTS


def test_repository_reads_the_conf_its_provider_returns_at_each_call(monkeypatch, rt, conf):
	# Like every other config reader (refactor9 F9): NVDA's config.conf is read when used.
	current = [{**worldvoice_conf(), "speech": {"WorldVoice": {}}}]
	repository = load_settings_repository(monkeypatch, rt).ConfigVoiceSettingsRepository(lambda: current[0])
	current[0] = conf
	conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "72"}
	assert repository.load(make_spec())["rate"] == 72
	repository.save(make_spec(), {**DEFAULTS, "pitch": 61})
	assert conf["WorldVoice"]["voices"]["Fake:a"]["pitch"] == 61


def test_missing_voice_persists_and_loads_the_six_defaults(repository, conf):
	assert repository.load(make_spec()) == DEFAULTS
	assert conf["WorldVoice"]["voices"]["Fake:a"] == DEFAULTS


def test_voices_load_their_own_values_whatever_the_main_synth_has(repository, conf):
	# Following the main voice is ParameterConsistency's job, through the settings store.
	conf["WorldVoice"]["autoLanguageSwitching"]["keepMainLocaleParameterConsistent"] = True
	conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "72", "variant": "bright"}
	assert repository.load(make_spec()) == dict(DEFAULTS, rate=72, variant="bright")
