"""The WorldVoice synth exposes pipeline settings stored only in the pipeline config."""

import types

import pytest
from pipeline_harness import load_synth


def manager(capabilities=frozenset()):
	recorded = []
	return types.SimpleNamespace(
		defaultVoiceName="v",
		getVoiceCapabilities=lambda name: types.SimpleNamespace(settings=capabilities),
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
	"cni",
	"numlan",
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
	cni = next(s for s in synth.allSupportedSettings if s.id == "cni")
	assert cni.options["availableInSettingsRing"] is False
	wait = next(s for s in synth.allSupportedSettings if s.id == "globalwaitfactor")
	assert (wait.kind, wait.options["minStep"], wait.options["defaultVal"]) == ("int", 10, 10)


def test_descriptors_read_and_write_through_the_service(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, _ = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	assert synth.itemwaitfactor == 10
	synth.itemwaitfactor = 30
	synth.globalwaitfactor = 57
	synth.nummod = "pair"
	assert conf["WorldVoice"]["pipeline"] == {
		"item_wait_factor": 30,
		"global_wait_factor": 50,
		"number_mode": "pair",
	}
	assert (synth.itemwaitfactor, synth.globalwaitfactor, synth.nummod) == (30, 50, "pair")
	assert "speech" not in conf


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
	synth._voiceManager = types.SimpleNamespace(waitfactor=None)
	settings_module.pipeline_settings.subscribe(synth._apply_pipeline_settings)
	synth.globalwaitfactor = 100
	assert synth._voiceManager.waitfactor == 9
	synth._voiceManager = None
	synth.globalwaitfactor = 30


@pytest.mark.parametrize("name", ["volume", "rate", "pitch", "inflection", "variant", "rateBoost"])
@pytest.mark.parametrize("consistent", [False, True])
def test_voice_parameters_commit_and_follow_the_consistency_policy(monkeypatch, name, consistent):
	conf = {
		"WorldVoice": {
			"pipeline": {},
			"autoLanguageSwitching": {"KeepMainLocaleParameterConsistent": consistent},
		},
	}
	synth_class, _ = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	calls = []
	instance = types.SimpleNamespace(commit=lambda: calls.append("commit"))
	synth._voiceManager = types.SimpleNamespace(
		defaultVoiceInstance=instance,
		parameter_consistency=types.SimpleNamespace(enabled=consistent),
		onVoiceParameterConsistent=lambda voice: calls.append(("consistent", voice)),
	)
	# The AST-loaded class has no NVDA auto-property metaclass; call the setter itself.
	getattr(synth, f"_set_{name}")(42)
	assert getattr(instance, name) == 42
	assert calls == ["commit"] + ([("consistent", instance)] if consistent else [])


def test_speech_context_falls_back_while_the_synth_is_not_running(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, _ = load_synth(monkeypatch, conf)
	generic = object()
	monkeypatch.setitem(synth_class.speech_context.__globals__, "GENERIC_CONTEXT", generic)
	monkeypatch.setitem(synth_class.speech_context.__globals__, "SpeechContext", lambda **kwargs: kwargs)
	synth = object.__new__(synth_class)
	# What __init__ sets before any stage can run.
	synth._numlan, synth.speechSymbols = "default", None
	synth._voiceManager = None
	assert synth.speech_context() is generic
	voice = object()
	synth._voiceManager = types.SimpleNamespace(
		defaultVoiceInstance=voice,
		getVoiceNameForLanguage=lambda lang: None,
	)
	synth.language = "en"
	context = synth.speech_context()
	assert (context["number_language"], context["speech_symbols"], context["default_voice"]) == (
		"default",
		None,
		voice,
	)
