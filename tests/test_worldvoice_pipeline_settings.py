"""The WorldVoice synth exposes pipeline settings stored only in the pipeline config."""

import sys
import types

import pytest
from nvda_stubs import RefusingSection, worldvoice_conf
from pipeline_harness import load_synth


def manager(capabilities=frozenset()):
	recorded = []
	return types.SimpleNamespace(
		default_voice_name="v",
		get_voice_capabilities=lambda name: types.SimpleNamespace(settings=capabilities),
		reload=lambda: recorded.append("reload"),
		recorded=recorded,
	)


EXPECTED_IDS = [
	"voice",
	"variant",
	"rate",
	"rateBoost",
	"pitch",
	"inflection",
	"volume",
	"uwv",
	"globalwaitfactor",
	"numlan",
	"nummod",
	"numberwaitfactor",
	"itemwaitfactor",
	"sayallwaitfactor",
	"unspacedscriptspacewaitfactor",
	"punctuationpauseenabled",
	"removepunctuationcharacters",
	"punctuationwaitfactor",
]


def test_settings_lists_keep_their_order_and_store_pipeline_values_outside_speech_config(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, _ = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	synth._voiceManager = manager()
	assert [s.id for s in synth.allSupportedSettings] == EXPECTED_IDS
	assert [s.id for s in synth.supportedSettings] == [
		i for i in EXPECTED_IDS if i not in {"rateBoost", "inflection"}
	]
	synth._voiceManager = manager(frozenset({"rateBoost", "inflection"}))
	assert [s.id for s in synth.supportedSettings] == EXPECTED_IDS
	pipeline_ids = set(EXPECTED_IDS[8:]) - {"numlan"}
	for setting in synth.allSupportedSettings:
		assert setting.options.get("useConfig", True) is (setting.id not in pipeline_ids)
	assert all(setting.options["availableInSettingsRing"] for setting in synth.allSupportedSettings[8:])
	# The group size is set in the panels only: no synth setting, no descriptor, not in the ring.
	assert not hasattr(synth_class, "groupsize")
	wait = next(s for s in synth.allSupportedSettings if s.id == "globalwaitfactor")
	assert (wait.kind, wait.options["minStep"], wait.options["defaultVal"]) == ("int", 10, 10)


def test_number_language_is_a_driver_setting_nvda_stores(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, _ = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	synth._voiceManager = manager()
	(numlan,) = [setting for setting in synth.allSupportedSettings if setting.id == "numlan"]
	assert (numlan.kind, numlan.label) == ("str", "Number &language")
	assert numlan.options["displayName"] == "Number language"
	assert numlan.options["defaultVal"] == "default"
	assert numlan.options["availableInSettingsRing"] is True
	# NVDA stores it in [speech][WorldVoice]: useConfig keeps its default, True.
	assert numlan.options.get("useConfig", True) is True
	# The driver's own numlan property stays; no pipeline descriptor replaces it.
	assert "numlan" not in vars(synth_class)


def test_numeric_settings_carry_the_spec_bounds(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, settings_module = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	synth._voiceManager = manager()
	numeric = [s for s in synth.allSupportedSettings if s.kind == "int"]
	assert numeric
	for setting in numeric:
		spec = next(spec for spec in settings_module.PIPELINE_SETTINGS if spec.driver_id == setting.id)
		assert (setting.options["minVal"], setting.options["maxVal"]) == (spec.min_value, spec.max_value)


def test_descriptors_read_and_write_through_the_service(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, _ = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	assert synth.itemwaitfactor == 10
	synth.itemwaitfactor = 30
	synth.globalwaitfactor = 57
	synth.nummod = "group"
	assert conf["WorldVoice"]["pipeline"] == {
		"item_wait_factor": 30,
		"global_wait_factor": 50,
		"number_mode": "group",
	}
	assert (synth.itemwaitfactor, synth.globalwaitfactor, synth.nummod) == (30, 50, "group")
	assert "speech" not in conf


def test_a_ring_change_writes_only_its_own_key(monkeypatch):
	# The settings ring and NVDA's Voice panel set one synth attribute at a time; that writes its
	# key and nothing else, even beside a stored value NVDA refuses.
	section = RefusingSection({"group_size": 11, "number_wait_factor": 40})
	conf = {"WorldVoice": {"pipeline": section}}
	synth_class, _ = load_synth(monkeypatch, conf)
	section.refused["group_size"] = sys.modules["configobj.validate"].VdtValueTooBigError(11)
	synth = object.__new__(synth_class)
	synth.itemwaitfactor = 30
	assert section.written == ["item_wait_factor"]
	assert dict(section) == {"group_size": 11, "number_wait_factor": 40, "item_wait_factor": 30}


def test_an_unknown_number_mode_is_stored_and_read_as_value(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {"number_mode": "group"}}}
	synth_class, _ = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	synth.nummod = "pair"
	assert conf["WorldVoice"]["pipeline"]["number_mode"] == "value"
	assert synth.nummod == "value"


def test_load_settings_reapplies_waitfactor_without_writing_pipeline(monkeypatch):
	class Section(dict):
		def __setitem__(self, key, value):
			raise AssertionError(f"loadSettings wrote {key}")

	conf = {"WorldVoice": {"pipeline": Section(global_wait_factor=0)}}
	synth_class, _ = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	writes = []
	recorded = []

	class Manager:
		def reload(self):
			recorded.append(("reload", list(writes)))

		@property
		def waitfactor(self):
			return 0

		@waitfactor.setter
		def waitfactor(self, value):
			writes.append(value)

	synth._voiceManager = Manager()
	synth.loadSettings(onlyChanged=True)
	# Re-applied even though the value did not change, and before voices reload.
	assert writes == [0]
	assert recorded == [("reload", [0])]


def test_global_wait_change_reaches_the_voice_manager(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, settings_module = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	manager = types.SimpleNamespace(waitfactor=None)
	synth._voiceManager = manager
	settings_module.pipeline_settings.subscribe(synth._applyPipelineSettings)
	synth.globalwaitfactor = 100
	assert manager.waitfactor == 9
	synth._voiceManager = None
	synth.globalwaitfactor = 30


@pytest.mark.parametrize("name", ["volume", "rate", "pitch", "inflection", "variant", "rateBoost"])
@pytest.mark.parametrize("consistent", [False, True])
def test_voice_parameters_commit_and_follow_the_consistency_policy(monkeypatch, name, consistent):
	conf = worldvoice_conf(autoLanguageSwitching={"KeepMainLocaleParameterConsistent": consistent})
	synth_class, _ = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	calls = []
	instance = types.SimpleNamespace(commit=lambda: calls.append("commit"))
	synth._voiceManager = types.SimpleNamespace(
		default_voice_instance=instance,
		parameter_consistency=types.SimpleNamespace(enabled=consistent),
		on_voice_parameter_consistent=lambda voice: calls.append(("consistent", voice)),
	)
	# The AST-loaded class has no NVDA auto-property metaclass; call the setter itself.
	getattr(synth, f"_set_{name}")(42)
	assert getattr(instance, name) == 42
	assert calls == ["commit"] + ([("consistent", instance)] if consistent else [])


def test_speech_context_falls_back_while_the_synth_is_not_running(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, _ = load_synth(monkeypatch, conf)
	generic = object()
	monkeypatch.setitem(synth_class.speechContext.__globals__, "GENERIC_CONTEXT", generic)
	monkeypatch.setitem(synth_class.speechContext.__globals__, "SpeechContext", lambda **kwargs: kwargs)
	synth = object.__new__(synth_class)
	# What __init__ sets before any stage can run.
	synth._numlan = "default"
	synth._voiceManager = None
	assert synth.speechContext() is generic
	voice = types.SimpleNamespace(name="A:en", language="en")
	synth._voiceManager = manager = types.SimpleNamespace(
		default_voice_instance=voice,
		get_voice_name_for_language=lambda lang: None,
		get_voice_locale_for_language=lambda lang: "zh_TW",
	)
	synth.language = "en"
	context = synth.speechContext()
	assert context["number_language"] == "default"
	assert (context["default_voice_name"], context["default_voice_language"]) == ("A:en", "en")
	assert context["voice_locale_for_language"] is manager.get_voice_locale_for_language
	assert "speech_symbols" not in context
	# Each speak builds its own context, so a new default voice reaches the next one.
	manager.default_voice_instance = types.SimpleNamespace(name="B:zh", language="zh")
	context = synth.speechContext()
	assert (context["default_voice_name"], context["default_voice_language"]) == ("B:zh", "zh")
