"""The Say All patch: NVDA's say-all speaks through a getTextInfoSpeech that adds the configured pause."""

import importlib
import sys
from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, alias_package
from nvda_stubs import worldvoice_conf

PACKAGE = "say_all_test_worldvoice"


class BreakCommand:
	def __init__(self, time):
		self.time = time


@pytest.fixture
def say_all(stub_modules, monkeypatch):
	for name in tuple(sys.modules):
		if name.startswith(PACKAGE + "."):
			monkeypatch.delitem(sys.modules, name)
	conf = worldvoice_conf()
	initialized = []
	spoken_by_nvda = []

	def get_text_info_speech(*args, **kwargs):
		spoken_by_nvda.append((args, kwargs))
		yield ["first"]
		yield ["second"]

	nvda_speech = SimpleNamespace(
		speak=object(),
		speakObject=object(),
		getTextInfoSpeech=get_text_info_speech,
		SpeakTextInfoState=object(),
	)
	nvda_say_all = stub_modules.module("speech.sayAll", initialize=lambda *args: initialized.append(args))
	stub_modules.module("speech", speech=nvda_speech, sayAll=nvda_say_all)
	stub_modules.module("speech.commands", BreakCommand=BreakCommand)
	stub_modules.module("speech.types", SpeechSequence=list)
	stub_modules.module("config", conf=conf)
	stub_modules.module("addonHandler", initTranslation=lambda: None)
	stub_modules.module("logHandler", log=SimpleNamespace(error=lambda *args, **kwargs: None))
	synth = SimpleNamespace(name="WorldVoice", speech_context=lambda: SimpleNamespace(supports_roles=True))
	stub_modules.module("synthDriverHandler", getSynth=lambda: synth)
	stub_modules.translation()
	alias_package(monkeypatch, PACKAGE, WORLDVOICE)
	# The pipeline package without its __init__: say-all needs only its context and settings.
	alias_package(monkeypatch, PACKAGE + ".pipeline", WORLDVOICE / "pipeline")
	return SimpleNamespace(
		module=importlib.import_module(PACKAGE + ".sayAll"),
		nvda=nvda_speech,
		initialized=initialized,
		spoken_by_nvda=spoken_by_nvda,
		pipeline=conf["WorldVoice"]["pipeline"],
		synth=synth,
	)


def speak_say_all(say_all):
	"""Patch, then run the getTextInfoSpeech NVDA's say-all received, as say-all does."""
	say_all.module.patch()
	speak, speak_object, get_text_info_speech, state = say_all.initialized[-1]
	assert (speak, speak_object, state) == (
		say_all.nvda.speak,
		say_all.nvda.speakObject,
		say_all.nvda.SpeakTextInfoState,
	)
	assert get_text_info_speech is not say_all.nvda.getTextInfoSpeech
	return list(get_text_info_speech("info", reason="sayAll"))


def test_say_all_adds_the_scaled_pause_after_nvdas_speech(say_all):
	say_all.pipeline.update(global_wait_factor=30, sayall_wait_factor=4)
	sequences = speak_say_all(say_all)
	assert sequences[:2] == [["first"], ["second"]]
	# 30 // 10 units of 4, plus the fixed 100.
	assert [command.time for command in sequences[2]] == [112]
	assert len(sequences) == 3
	assert say_all.spoken_by_nvda == [(("info",), {"reason": "sayAll"})]


def test_the_pause_is_read_when_say_all_reaches_the_end(say_all):
	say_all.module.patch()
	get_text_info_speech = say_all.initialized[-1][2]
	say_all.pipeline.update(global_wait_factor=10, sayall_wait_factor=0)
	assert list(get_text_info_speech()) == [["first"], ["second"]]


@pytest.mark.parametrize(("scope", "paused"), [("WorldVoice", False), ("all", True)])
def test_another_synth_gets_the_pause_only_when_the_pipeline_covers_every_synth(say_all, scope, paused):
	say_all.synth.name = "espeak"
	say_all.pipeline.update(scope=scope)
	sequences = speak_say_all(say_all)
	assert len(sequences) == (3 if paused else 2)


def test_unpatch_hands_nvda_its_own_text_info_speech_again(say_all):
	say_all.module.patch()
	say_all.module.unpatch()
	assert say_all.initialized[-1] == (
		say_all.nvda.speak,
		say_all.nvda.speakObject,
		say_all.nvda.getTextInfoSpeech,
		say_all.nvda.SpeakTextInfoState,
	)
