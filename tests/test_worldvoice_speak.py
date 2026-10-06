"""SynthDriver.speak from the speech sequence NVDA hands over to the work it queues.

The driver class, pipeline functions, language detector, command normalization and request
builder are the add-on's own; only NVDA's command classes, the voice manager and the task
manager are stand-ins. The task manager records what the request builder appends, so each
test reads the voice, chunks and pauses that would reach the engines, in order.
"""

import importlib
import sys
from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, alias_package
from nvda_stubs import StubModules, worldvoice_conf
from worldvoice_harness import load_synth_class

PACKAGE = "speak_test_worldvoice"
VOICES = {"en": "A:en", "zh": "B:zh"}


class SynthCommand:
	pass


class SynthParamCommand(SynthCommand):
	pass


class IndexCommand(SynthCommand):
	def __init__(self, index):
		self.index = index

	def __repr__(self):
		return f"IndexCommand({self.index})"


class BreakCommand(SynthCommand):
	def __init__(self, time):
		self.time = time


class LangChangeCommand(SynthParamCommand):
	def __init__(self, lang):
		self.lang = lang
		self.isDefault = not lang


class RecordingTasks:
	"""The task manager surface queue_speech_sequence uses, recording each call."""

	def __init__(self, ports):
		self.ports = ports
		self.calls = []

	def new_request(self):
		return SimpleNamespace(state=None)

	def append_speech(self, request, playback, voice_key, chunks):
		assert playback is self.ports[voice_key]
		self.calls.append(("speech", voice_key, chunks))

	def append_break(self, request, seconds):
		self.calls.append(("break", seconds))

	def submit_request(self, request):
		self.calls.append("submit")
		return True

	def pause_current(self, switch):
		self.calls.append(("pause", switch))


class VoiceManager:
	"""Voices by primary language; the default voice speaks English."""

	defaultVoiceName = VOICES["en"]
	defaultVoiceInstance = SimpleNamespace(name=VOICES["en"], language="en")
	languages = ("en", "zh_TW")

	def __init__(self, ports):
		self.ports = ports
		self.cancels = 0

	def getVoiceNameForLanguage(self, language):
		return VOICES.get(language.replace("-", "_").split("_")[0])

	def resolve_playback(self, voice_key):
		return self.ports.get(voice_key)

	def cancel(self):
		self.cancels += 1


def _load_modules(monkeypatch, conf):
	for name in tuple(sys.modules):
		if name.startswith(PACKAGE + "."):
			monkeypatch.delitem(sys.modules, name)
	stubs = StubModules(monkeypatch)
	stubs.translation()
	stubs.module("speech")
	stubs.module(
		"speech.commands",
		SynthCommand=SynthCommand,
		SynthParamCommand=SynthParamCommand,
		IndexCommand=IndexCommand,
		BreakCommand=BreakCommand,
		LangChangeCommand=LangChangeCommand,
	)
	stubs.module("speech.extensions", filter_speechSequence=SimpleNamespace())
	stubs.module("speechDictHandler", processText=lambda text: text)
	stubs.module("globalVars", speechDictionaryProcessing=True)
	stubs.module("synthDriverHandler", getSynth=lambda: None)
	stubs.module("config", conf=conf)
	stubs.module("addonHandler", initTranslation=lambda: None)
	stubs.module(
		"logHandler",
		log=SimpleNamespace(debug=lambda *args: None, error=lambda *args, **kwargs: None),
	)
	alias_package(monkeypatch, PACKAGE, WORLDVOICE)

	def load(name):
		return importlib.import_module(f"{PACKAGE}.{name}")

	return SimpleNamespace(
		pipeline=load("pipeline"),
		context=load("pipeline.context"),
		detection=load("languageDetection"),
		detection_settings=load("languageDetection.settings"),
		builder=load("runtime.requestBuilder"),
		commands=load("compat.commands"),
		models=load("runtime.models"),
		WV=load("_speechcommand").WVLangChangeCommand,
	)


def _synth(monkeypatch, *, timing="after", uwv=True):
	conf = {
		"general": {"loggingLevel": "INFO"},
		**worldvoice_conf(autoLanguageSwitching={"DetectLanguageTiming": timing}),
	}
	modules = _load_modules(monkeypatch, conf)
	pipeline = modules.pipeline
	detection_settings = modules.detection_settings.DetectionSettingsService(lambda: conf)
	environment = {
		"SynthDriver": object,
		"IndexCommand": IndexCommand,
		"CharacterModeCommand": SynthCommand,
		"LangChangeCommand": LangChangeCommand,
		"BreakCommand": BreakCommand,
		"PitchCommand": SynthCommand,
		"RateCommand": SynthCommand,
		"VolumeCommand": SynthCommand,
		"synthIndexReached": object(),
		"synthDoneSpeaking": object(),
		"inject_langchange_reorder": pipeline.inject_langchange_reorder,
		"deduplicate_language_command": pipeline.deduplicate_language_command,
		"lang_cmd_to_voice": pipeline.lang_cmd_to_voice,
		"queue_speech_sequence": modules.builder.queue_speech_sequence,
		"normalize_legacy_commands": modules.commands.normalize_legacy_commands,
		"detection_settings": detection_settings,
		"SpeechContext": modules.context.SpeechContext,
		"GENERIC_CONTEXT": modules.context.GENERIC_CONTEXT,
		"StringParameterInfo": lambda id, name: SimpleNamespace(id=id, displayName=name),
		"languageHandler": SimpleNamespace(
			getLanguageDescription=lambda locale: {"en": "English"}.get(locale),
		),
		"_": lambda text: text,
	}
	ports = {key: object() for key in VOICES.values()}
	synth = object.__new__(load_synth_class(environment))
	synth._terminated = False
	synth._numlan = "default"
	synth.speechSymbols = None
	synth.language = "en"
	synth.uwv = uwv
	synth.taskManager = RecordingTasks(ports)
	synth._voiceManager = VoiceManager(ports)
	detector = modules.detection.LanguageDetector(
		list(VOICES),
		settings=detection_settings,
		language=lambda: synth.language,
	)
	synth.add_detected_language_commands = pipeline.listable(detector.add_detected_language_commands)
	return synth, modules


def test_detection_after_nvda_switches_voices_and_keeps_indexes_with_the_following_text(monkeypatch):
	synth, _ = _synth(monkeypatch, timing="after")
	index = IndexCommand(1)
	synth.speak(["Hello 世界", index, BreakCommand(200), "bye"])
	# The detector switches to Chinese for 世界 and back for "bye"; the reorder moves that
	# switch before the index and break, so they belong to the English text that follows.
	assert synth.taskManager.calls == [
		("speech", "A:en", ("Hello ",)),
		("speech", "B:zh", ("世界",)),
		("speech", "A:en", (index,)),
		("break", 0.2),
		("speech", "A:en", ("bye",)),
		"submit",
	]


@pytest.mark.parametrize(("timing", "uwv"), [("before", True), ("after", False)])
def test_speak_detects_nothing_unless_detection_runs_after_nvda(monkeypatch, timing, uwv):
	synth, _ = _synth(monkeypatch, timing=timing, uwv=uwv)
	synth.speak(["Hello 世界"])
	assert synth.taskManager.calls == [("speech", "A:en", ("Hello 世界",)), "submit"]


def test_language_changes_lead_the_commands_they_follow_and_revert_to_the_default_voice(monkeypatch):
	# With detection before NVDA, the sequence already carries the language changes.
	synth, modules = _synth(monkeypatch, timing="before")
	first, second = IndexCommand(1), IndexCommand(2)
	synth.speak([first, LangChangeCommand("zh"), "你好", modules.WV(None), second, "ok"])
	assert synth.taskManager.calls == [
		("speech", "B:zh", (first, "你好")),
		("speech", "A:en", (second, "ok")),
		"submit",
	]


def test_language_changes_that_keep_the_voice_are_dropped(monkeypatch):
	synth, modules = _synth(monkeypatch, timing="before")
	# en_GB maps to the voice already speaking; French has no voice, so the default stays.
	synth.speak(["one", LangChangeCommand("en_GB"), "two", modules.WV("fr"), "three"])
	assert synth.taskManager.calls == [("speech", "A:en", ("one", "two", "three")), "submit"]


def test_number_languages_list_every_voice_language_by_its_description(monkeypatch):
	synth, _ = _synth(monkeypatch)
	numlans = synth._get_availableNumlans()
	assert {key: info.displayName for key, info in numlans.items()} == {
		"default": "default",
		"en": "English",
		# No description: the locale itself names it.
		"zh_TW": "zh_TW",
	}
	synth._set_numlan("zh_TW")
	assert synth._get_numlan() == "zh_TW"
	assert synth.speech_context().number_language == "zh_TW"


def test_choosing_the_current_voice_records_it_without_stopping_speech(monkeypatch):
	synth, _ = _synth(monkeypatch)
	stops = []
	synth._voiceManager.defaultVoiceInstance = SimpleNamespace(stop=lambda: stops.append(True))
	synth._set_voice("A:en")
	assert stops == []
	assert synth._voice == "A:en"
	assert synth._get_voice() == "A:en"


def test_pause_and_cancel_reach_the_runtime_until_the_synth_terminates(monkeypatch):
	synth, _ = _synth(monkeypatch)
	synth.pause(True)
	synth.cancel()
	assert synth.taskManager.calls == [("pause", True)]
	assert synth._voiceManager.cancels == 1
	synth._terminated = True
	synth.cancel()
	synth.pause(False)
	assert synth._voiceManager.cancels == 1
	assert synth.taskManager.calls == [("pause", True)]
