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
from addon_loader import REF, WORLDVOICE, alias_package
from nvda_stubs import StubModules, worldvoice_conf
from pipeline_harness import nvda_normalize_language, symbol_name
from worldvoice_harness import chosen_voice, load_synth_class, voice_manager

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

	def getVoiceLocaleForLanguage(self, language):
		# An engine with no locale of its own reports the voice's language.
		name = self.getVoiceNameForLanguage(language)
		return name.split(":")[1] if name else None

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
	stubs.module("characterProcessing", processSpeechSymbol=lambda locale, symbol: symbol)
	stubs.module("globalVars", speechDictionaryProcessing=True, appDir=str(REF / "nvda/source"))
	stubs.module("languageHandler", normalizeLanguage=nvda_normalize_language())
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
		settings=load("pipeline.settings"),
		number_language=load("numberLanguage"),
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
		"NUMBER_LANGUAGE_CHOICES": modules.settings.NUMBER_LANGUAGE_CHOICES,
		"FOLLOW": modules.number_language.FOLLOW,
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
	synth.language = "en"
	synth.uwv = uwv
	synth._uwv = uwv
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
	# The two follow values come first, then each voice language (spec §3).
	assert [(key, info.displayName) for key, info in numlans.items()] == [
		("default", "Follow current text language"),
		("main", "Follow document main language"),
		("en", "English"),
		# No description: the locale itself names it.
		("zh_TW", "zh_TW"),
	]
	synth._set_numlan("zh_TW")
	assert synth._get_numlan() == "zh_TW"
	assert synth.speech_context().number_language == "zh_TW"


def test_choosing_the_current_voice_records_it_without_stopping_speech(monkeypatch):
	synth, _ = _synth(monkeypatch)
	stops = []
	synth._voiceManager.defaultVoiceInstance = SimpleNamespace(stop=lambda: stops.append(True))
	synth._set_voice("A:en")
	assert stops == []
	assert chosen_voice(synth) == "A:en"
	assert synth._get_voice() == "A:en"


def test_pause_and_cancel_reach_the_runtime_until_the_synth_terminates(monkeypatch):
	synth, _ = _synth(monkeypatch)
	synth.pause(True)
	synth.cancel()
	assert synth.taskManager.calls == [("pause", True)]
	assert voice_manager(synth).cancels == 1
	synth._terminated = True
	synth.cancel()
	synth.pause(False)
	assert voice_manager(synth).cancels == 1
	assert synth.taskManager.calls == [("pause", True)]


# Which voice reads a number (phase 35). Every row was recorded on da7f791, before phase 35.

EN, ZH = VOICES["en"], VOICES["zh"]
L = LangChangeCommand


def stage_settings(*, number_mode="value", punctuation=False, number_wait=0, group_size=3):
	"""The pipeline settings the stages read: only the given pauses and modes, every other wait 0."""
	return SimpleNamespace(
		number_mode=number_mode,
		scope="WorldVoice",
		punctuation_pause_characters=".,",
		punctuation_pause_enabled=punctuation,
		remove_punctuation_characters=False,
		scaled_item_wait=lambda: 0,
		scaled_number_wait=lambda: number_wait,
		scaled_chinesespace_wait=lambda: 0,
		scaled_punctuation_wait=lambda: 0,
		group_size=group_size,
	)


def heard(calls):
	"""What each voice reads, in order: (voice, text) with an index as "[i]", and "|" for a break."""
	result = []
	for call in calls:
		if call == "submit":
			continue
		if call[0] != "speech":
			result.append("|")
			continue
		_kind, voice, chunks = call
		text = "".join(chunk if isinstance(chunk, str) else f"[{chunk.index}]" for chunk in chunks)
		if result and isinstance(result[-1], tuple) and result[-1][0] == voice:
			result[-1] = (voice, result[-1][1] + text)
		else:
			result.append((voice, text))
	return result


def speak_through_stages(
	monkeypatch,
	sequence,
	*,
	numlan,
	timing="after",
	uwv=True,
	main="en",
	settings=None,
	ignore=False,
):
	"""Run the pipeline stages, then detection when it runs before NVDA, then speak; what is heard."""
	synth, modules = _synth(monkeypatch, timing=timing, uwv=uwv)
	synth._numlan = numlan
	if main == "zh":
		synth.language = "zh_TW"
		synth._voiceManager.defaultVoiceName = ZH
		synth._voiceManager.defaultVoiceInstance = SimpleNamespace(name=ZH, language="zh_TW")
	conf = sys.modules["config"].conf
	conf["WorldVoice"]["autoLanguageSwitching"]["ignoreNumbersInLanguageDetection"] = ignore
	monkeypatch.setattr(sys.modules["speech"], "getCurrentLanguage", lambda: synth.language, raising=False)
	monkeypatch.setattr(sys.modules["characterProcessing"], "processSpeechSymbol", symbol_name)
	ctx = synth.speech_context()
	sequence = list(sequence)
	for stage in modules.pipeline.STAGES:
		sequence = list(stage.fn(sequence, settings or stage_settings(), ctx))
	if uwv and timing == "before":
		sequence = synth.add_detected_language_commands(sequence)
	synth.speak(sequence)
	return heard(synth.taskManager.calls)


TIMINGS = pytest.mark.parametrize("timing", ["after", "before"])
PUNCTUATION = stage_settings(punctuation=True)
NUMBER_MODE = stage_settings(number_mode="number")
# "Follow document main language" reads digits as today's "ignore numbers" off did.
MAIN = {"numlan": "main", "ignore": False}
# Today's "ignore numbers" on: digits follow the text.
FOLLOW = {"numlan": "default", "ignore": True}

MAIN_ROWS = [
	pytest.param(["中12"], {}, [(ZH, "中"), (EN, "12")], id="zh12"),
	pytest.param(["中文 12"], {}, [(ZH, "中文 "), (EN, "12")], id="zh-space-12"),
	pytest.param([L("de_DE"), "abc 12 中"], {}, [(EN, "abc 12 "), (ZH, "中")], id="tagged-de"),
	pytest.param(["abc 123 def"], {"main": "zh"}, [(EN, "abc "), (ZH, "123 "), (EN, "def")], id="zh-main"),
	pytest.param(
		["中12.5 ok"],
		{"settings": NUMBER_MODE},
		[(ZH, "中"), (EN, "1"), "|", (EN, "2"), "|", (EN, "full stop en"), "|", (EN, "5 ok")],
		id="number-mode",
	),
	pytest.param(["Total. 12"], {"settings": PUNCTUATION}, [(EN, "Total."), "|", (EN, " 12")], id="total"),
	pytest.param(
		["中 12. Next"],
		{"settings": PUNCTUATION},
		[(ZH, "中 "), (EN, "12 ."), "|", (EN, " Next")],
		id="next",
	),
	pytest.param(["中", IndexCommand(1), "12"], {}, [(ZH, "中"), (EN, "[1]12")], id="index"),
	pytest.param(["", "12", ""], {}, [(EN, "12")], id="empty"),
]


@TIMINGS
@pytest.mark.parametrize(("sequence", "options", "expected"), MAIN_ROWS)
def test_main_language_numbers(monkeypatch, sequence, options, expected, timing):
	assert speak_through_stages(monkeypatch, sequence, timing=timing, **MAIN, **options) == expected


FOLLOW_ROWS = [
	pytest.param(["中12"], {}, [(ZH, "中12")], id="zh12"),
	pytest.param(["中文 12"], {}, [(ZH, "中文 12")], id="zh-space-12"),
	pytest.param(["Total. 12"], {"settings": PUNCTUATION}, [(EN, "Total."), "|", (EN, " 12")], id="total"),
	pytest.param(
		["中 12. Next"],
		{"settings": PUNCTUATION},
		[(ZH, "中 12 ."), "|", (ZH, " "), (EN, "Next")],
		id="next",
	),
	pytest.param(
		["中12.5 ok"],
		{"settings": NUMBER_MODE},
		[(ZH, "中1"), "|", (ZH, "2"), "|", (EN, "full stop en"), "|", (EN, "5 ok")],
		id="number-mode",
	),
]


@TIMINGS
@pytest.mark.parametrize(("sequence", "options", "expected"), FOLLOW_ROWS)
def test_follow_language_numbers(monkeypatch, sequence, options, expected, timing):
	assert speak_through_stages(monkeypatch, sequence, timing=timing, **FOLLOW, **options) == expected


OFF_ROWS = [
	pytest.param("default", ["中12"], {}, [(EN, "中12")], id="default-zh12"),
	pytest.param(
		"default",
		["Total. 12"],
		{"settings": PUNCTUATION},
		[(EN, "Total."), "|", (EN, " 12")],
		id="default-total",
	),
	pytest.param(
		"default",
		["12. Next"],
		{"settings": PUNCTUATION},
		[(EN, "12 ."), "|", (EN, " Next")],
		id="default-next",
	),
	pytest.param("main", ["中12"], {}, [(EN, "中12")], id="main-zh12"),
	pytest.param("zh_TW", ["中12"], {}, [(EN, "中"), (ZH, "12")], id="locale-zh12"),
	pytest.param(
		"zh_TW",
		["Total. 12"],
		{"settings": PUNCTUATION},
		[(EN, "Total. "), (ZH, "12")],
		id="locale-total",
	),
	pytest.param(
		"zh_TW",
		["12. Next"],
		{"settings": PUNCTUATION},
		[(ZH, "12"), (EN, "."), "|", (EN, " Next")],
		id="locale-next",
	),
]


@pytest.mark.parametrize(("numlan", "sequence", "options", "expected"), OFF_ROWS)
def test_numbers_without_detection(monkeypatch, numlan, sequence, options, expected):
	assert speak_through_stages(monkeypatch, sequence, numlan=numlan, uwv=False, **options) == expected


LOCALE_ROWS = [
	# The voice of the number language is the main voice: the stage's own dedupe drops its wrappers.
	pytest.param(["abc 123 def"], {"main": "zh"}, [(EN, "abc "), (ZH, "123 "), (EN, "def")], id="zh-main"),
	pytest.param(["abc 12"], {}, [(EN, "abc "), (ZH, "12")], id="en-main"),
]


@TIMINGS
@pytest.mark.parametrize(("sequence", "options", "expected"), LOCALE_ROWS)
def test_locale_numbers_with_detection(monkeypatch, sequence, options, expected, timing):
	assert speak_through_stages(monkeypatch, sequence, numlan="zh_TW", timing=timing, **options) == expected


@TIMINGS
def test_full_width_digits_are_numbers(monkeypatch, timing):
	result = speak_through_stages(monkeypatch, ["abc１２３"], numlan="zh_TW", ignore=True, timing=timing)
	assert result == [(EN, "abc"), (ZH, "１２３")]


# Decided by the user (2026-10-23, spec §4.7 item 1): a sign or hyphen right before the digits
# moves with them, as a specific number language already wraps it.
SIGN_ROWS = [
	pytest.param(["中 -12"], {}, [(ZH, "中 "), (EN, "-12")], id="sign"),
	pytest.param(
		["中 -12 34"],
		{"settings": stage_settings(number_wait=50)},
		[(ZH, "中 "), (EN, "-12"), "|", (EN, "34")],
		id="wait",
	),
	pytest.param(
		["中 COVID-19 中"],
		{"main": "zh"},
		[(ZH, "中 "), (EN, "COVID"), (ZH, "-19 中")],
		id="covid",
	),
]


@TIMINGS
@pytest.mark.parametrize(("sequence", "options", "expected"), SIGN_ROWS)
def test_main_moves_a_sign_with_its_number(monkeypatch, sequence, options, expected, timing):
	assert speak_through_stages(monkeypatch, sequence, timing=timing, **MAIN, **options) == expected


@TIMINGS
def test_a_number_language_with_the_main_voice_still_reads_numbers_in_the_text(monkeypatch, timing):
	# Spec §3 last row: the main voice speaks the number language, so the early stage's dedupe drops
	# its wrappers (the second trap, spec §4.2); the late stage keeps the digits in that language.
	result = speak_through_stages(monkeypatch, ["中１２３"], numlan="en", ignore=True, timing=timing)
	assert result == [(ZH, "中"), (EN, "１２３")]
