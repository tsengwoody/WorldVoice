"""SynthDriver.speak from the speech sequence NVDA hands over to the work it queues.

The driver class, pipeline functions, language detector, command normalization and request
builder are the add-on's own; only NVDA's command classes, the voice manager and the task
manager are stand-ins. The task manager records what the request builder appends, so each
test reads the voice, chunks and pauses that would reach the engines, in order.
"""

import importlib
import sys
from itertools import pairwise
from types import SimpleNamespace

import pytest
from addon_loader import REF, WORLDVOICE, alias_package
from detector_harness import master_detection
from hypothesis import HealthCheck, example, given, settings, strategies as st
from nvda_stubs import StubModules, worldvoice_conf
from pipeline_harness import load_nvda_character_processing, nvda_normalize_language, symbol_name
from worldvoice_harness import chosen_voice, load_synth_class, number_language_choice_class, voice_manager

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


class EndUtteranceCommand:
	"""NVDA's speech manager ends an utterance here; the pipeline reads it."""


class ConfigProfileTriggerCommand:
	"""NVDA's speech manager ends an utterance before it; the pipeline reads it."""


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

	default_voice_name = VOICES["en"]
	default_voice_instance = SimpleNamespace(name=VOICES["en"], language="en")
	# The languages the voice settings offer; all_languages has every installed voice's, also those
	# that "Keep main locale engine consistent" hides.
	languages = ("en", "zh_TW")
	all_languages = ("en", "zh_TW")

	def __init__(self, ports):
		self.ports = ports
		self.cancels = 0

	def get_voice_name_for_language(self, language):
		return VOICES.get(language.replace("-", "_").split("_")[0])

	def get_voice_locale_for_language(self, language):
		# An engine with no locale of its own reports the voice's language.
		name = self.get_voice_name_for_language(language)
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
		EndUtteranceCommand=EndUtteranceCommand,
		ConfigProfileTriggerCommand=ConfigProfileTriggerCommand,
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
		pipeline=load("pipeline.registry"),
		language_commands=load("pipeline.languageCommands"),
		number_stages=load("pipeline.numberStages"),
		settings=load("pipeline.settings"),
		number_language=load("numberLanguage"),
		context=load("pipeline.context"),
		detection=load("languageDetection.detector"),
		breaks=load("pipeline.breaks"),
		detection_settings=load("languageDetection.settings"),
		builder=load("runtime.requestBuilder"),
		commands=load("bridge.commands"),
		models=load("runtime.models"),
		WV=load("speechCommands").WVLangChangeCommand,
	)


def _synth(monkeypatch, *, timing="after", uwv=True):
	conf = {
		"general": {"loggingLevel": "INFO"},
		**worldvoice_conf(autoLanguageSwitching={"detectLanguageTiming": timing}),
	}
	modules = _load_modules(monkeypatch, conf)
	pipeline = modules.pipeline
	detection_settings = modules.detection_settings.DetectionSettingsService(lambda: conf)
	warnings = []
	environment = {
		"BaseSynthDriver": object,
		"IndexCommand": IndexCommand,
		"CharacterModeCommand": SynthCommand,
		"LangChangeCommand": LangChangeCommand,
		"BreakCommand": BreakCommand,
		"PitchCommand": SynthCommand,
		"RateCommand": SynthCommand,
		"VolumeCommand": SynthCommand,
		"synthIndexReached": object(),
		"synthDoneSpeaking": object(),
		"inject_langchange_reorder": modules.language_commands.inject_langchange_reorder,
		"deduplicate_language_command": modules.language_commands.deduplicate_language_command,
		"lang_cmd_to_voice": modules.language_commands.lang_cmd_to_voice,
		"detect_with_number_language": modules.number_stages.detect_with_number_language,
		"queue_speech_sequence": modules.builder.queue_speech_sequence,
		"normalizeNvdaCommands": modules.commands.normalizeNvdaCommands,
		"detection_settings": detection_settings,
		"SpeechContext": modules.context.SpeechContext,
		"GENERIC_CONTEXT": modules.context.GENERIC_CONTEXT,
		"NUMBER_LANGUAGE_CHOICES": modules.settings.NUMBER_LANGUAGE_CHOICES,
		"FOLLOW": modules.number_language.FOLLOW,
		"MAIN": modules.number_language.MAIN,
		"nvdaLog": SimpleNamespace(debugWarning=lambda *args: warnings.append(args)),
		"StringParameterInfo": lambda id, name: SimpleNamespace(id=id, displayName=name),
		"languageHandler": SimpleNamespace(
			getLanguageDescription=lambda locale: {"en": "English"}.get(locale),
		),
		"_": lambda text: text,
	}
	ports = {key: object() for key in VOICES.values()}
	synth = object.__new__(load_synth_class(environment))
	synth.warnings = warnings
	synth._terminated = False
	synth.language = "en"
	synth.uwv = uwv
	synth._taskManager = RecordingTasks(ports)
	synth._voiceManager = VoiceManager(ports)
	synth._numberLanguageChoice = number_language_choice_class()(synth._voiceManager)
	# Wired as the driver wires it: the detector reads the number language speech uses.
	detector = modules.detection.LanguageDetector(
		list(VOICES),
		settings=detection_settings,
		language=lambda: synth.language,
		number_language=synth._numberLanguage,
		is_internal_break=modules.breaks.is_internal_break,
	)
	synth._languageDetector = detector
	synth.addDetectedLanguageCommands = pipeline.listable(synth._detectLanguages)
	return synth, modules


def test_detection_after_nvda_switches_voices_and_keeps_indexes_with_the_following_text(monkeypatch):
	synth, _ = _synth(monkeypatch, timing="after")
	index = IndexCommand(1)
	synth.speak(["Hello 世界", index, BreakCommand(200), "bye"])
	# The detector switches to Chinese for 世界 and back for "bye"; the reorder moves that
	# switch before the index and break, so they belong to the English text that follows.
	assert synth._taskManager.calls == [
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
	assert synth._taskManager.calls == [("speech", "A:en", ("Hello 世界",)), "submit"]


def test_language_changes_lead_the_commands_they_follow_and_revert_to_the_default_voice(monkeypatch):
	# With detection before NVDA, the sequence already carries the language changes.
	synth, modules = _synth(monkeypatch, timing="before")
	first, second = IndexCommand(1), IndexCommand(2)
	synth.speak([first, LangChangeCommand("zh"), "你好", modules.WV(None), second, "ok"])
	assert synth._taskManager.calls == [
		("speech", "B:zh", (first, "你好")),
		("speech", "A:en", (second, "ok")),
		"submit",
	]


def test_language_changes_that_keep_the_voice_are_dropped(monkeypatch):
	synth, modules = _synth(monkeypatch, timing="before")
	# en_GB maps to the voice already speaking; French has no voice, so the default stays.
	synth.speak(["one", LangChangeCommand("en_GB"), "two", modules.WV("fr"), "three"])
	assert synth._taskManager.calls == [("speech", "A:en", ("one", "two", "three")), "submit"]


def test_number_languages_list_every_voice_language_by_its_description(monkeypatch):
	synth, _ = _synth(monkeypatch)
	numlans = synth._get_availableNumlans()
	# The two follow values come first, then each voice language (spec §3).
	assert [(key, info.displayName) for key, info in numlans.items()] == [
		("default", "Follow surrounding text language"),
		("main", "Follow main language"),
		("en", "English"),
		# No description: the locale itself names it.
		("zh_TW", "zh_TW"),
	]
	synth._set_numlan("zh_TW")
	assert synth._get_numlan() == "zh_TW"
	assert synth.speechContext().number_language == "zh_TW"


class _CheckedVoices(VoiceManager):
	"""The real manager's voice setter: an unavailable voice raises LookupError."""

	@property
	def default_voice_name(self):
		return self.default_voice_instance.name

	@default_voice_name.setter
	def default_voice_name(self, name):
		if name not in VOICES.values():
			raise LookupError(name)
		self.default_voice_instance = SimpleNamespace(name=name, stop=self.default_voice_instance.stop)


def _voice_choice_synth(monkeypatch):
	synth, _ = _synth(monkeypatch)
	stops = []
	manager = _CheckedVoices(synth._voiceManager.ports)
	manager.default_voice_instance = SimpleNamespace(name=VOICES["en"], stop=lambda: stops.append(True))
	synth._voiceManager = manager
	synth._voice = VOICES["en"]
	return synth, stops


@pytest.mark.parametrize("voice", [VOICES["en"], VOICES["zh"]])
def test_choosing_a_voice_records_it_without_stopping_speech(monkeypatch, voice):
	# A profile switch can change the voice while speech is in flight. Queued speech keeps its
	# voice, as with NVDA's own drivers; a direct stop would leave the request waiting forever.
	synth, stops = _voice_choice_synth(monkeypatch)
	synth._set_voice(voice)
	assert stops == []
	assert voice_manager(synth).cancels == 0
	assert synth._taskManager.calls == []
	assert chosen_voice(synth) == voice
	assert synth._get_voice() == voice


def test_choosing_an_unavailable_voice_raises_and_changes_nothing(monkeypatch):
	synth, stops = _voice_choice_synth(monkeypatch)
	with pytest.raises(LookupError):
		synth._set_voice("Missing:x")
	assert stops == []
	assert voice_manager(synth).cancels == 0
	assert synth._taskManager.calls == []
	assert chosen_voice(synth) == VOICES["en"]
	assert synth._get_voice() == VOICES["en"]


def test_pause_and_cancel_reach_the_runtime_until_the_synth_terminates(monkeypatch):
	synth, _ = _synth(monkeypatch)
	synth.pause(True)
	synth.cancel()
	assert synth._taskManager.calls == [("pause", True)]
	assert voice_manager(synth).cancels == 1
	synth._terminated = True
	synth.cancel()
	synth.pause(False)
	assert voice_manager(synth).cancels == 1
	assert synth._taskManager.calls == [("pause", True)]


# Which voice reads a number (phase 35). Every row was recorded on da7f791, before phase 35.

EN, ZH = VOICES["en"], VOICES["zh"]
# A Nepali voice, added by the tests of digits with a script (fix/script-digit-language).
NE = "C:ne"
L = LangChangeCommand


def stage_settings(
	*,
	number_mode="value",
	punctuation=False,
	number_wait=0,
	group_size=0,
	segment_length=0,
	segment_wait=0,
	item_wait=0,
	unspaced_wait=0,
	punctuation_characters=".,",
	punctuation_wait=0,
):
	"""The pipeline settings the stages read: only the given pauses and modes, every other wait 0."""
	return SimpleNamespace(
		number_mode=number_mode,
		scope="WorldVoice",
		punctuation_pause_characters=punctuation_characters,
		punctuation_pause_enabled=punctuation,
		remove_punctuation_characters=False,
		scaled_item_wait=lambda: item_wait,
		scaled_number_wait=lambda: number_wait,
		scaled_unspaced_script_space_wait=lambda: unspaced_wait,
		scaled_punctuation_wait=lambda: punctuation_wait,
		group_size=group_size,
		segment_length=segment_length,
		scaled_segment_wait=lambda: segment_wait,
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
	nvda=None,
	oracle=False,
):
	"""Run the pipeline stages, then detection when it runs before NVDA, then *nvda* (what NVDA's
	speak() does to the filtered sequence), then speak; what is heard. With *oracle*, detection is the
	rule before fix/leading-punctuation-language (detector_harness.master_detection)."""
	synth, modules = _synth(monkeypatch, timing=timing, uwv=uwv)
	if oracle:
		detector = synth._languageDetector
		detector.add_detected_language_commands = lambda sequence: master_detection(detector, sequence)
	synth._set_numlan(numlan)
	if main in ("zh", "ne"):
		voice, language = {"zh": (ZH, "zh_TW"), "ne": (NE, "ne_NP")}[main]
		synth.language = language
		synth._voiceManager.default_voice_name = voice
		synth._voiceManager.default_voice_instance = SimpleNamespace(name=voice, language=language)
	monkeypatch.setattr(sys.modules["speech"], "getCurrentLanguage", lambda: synth.language, raising=False)
	monkeypatch.setattr(sys.modules["characterProcessing"], "processSpeechSymbol", symbol_name)
	ctx = synth.speechContext()
	sequence = list(sequence)
	for stage in modules.pipeline.STAGES:
		sequence = list(stage.fn(sequence, settings or stage_settings(), ctx))
	if uwv and timing == "before":
		sequence = synth.addDetectedLanguageCommands(sequence)
	if nvda is not None:
		sequence = nvda(sequence)
	synth.speak(sequence)
	return heard(synth._taskManager.calls)


TIMINGS = pytest.mark.parametrize("timing", ["after", "before"])

# The segment pause end to end (spec feat/segment-pause §9.2): each piece is its own engine segment.
SENTENCE = "The quick brown fox jumps over the lazy dog, then it sleeps."


def test_a_long_sentence_is_spoken_in_segments(monkeypatch):
	assert len(SENTENCE) == 60
	settings = stage_settings(segment_length=20, segment_wait=10)
	synth_calls = []
	original = _synth

	def recording_synth(*args, **kwargs):
		synth, modules = original(*args, **kwargs)
		synth_calls.append(synth)
		return synth, modules

	monkeypatch.setattr(sys.modules[__name__], "_synth", recording_synth)
	assert speak_through_stages(monkeypatch, [SENTENCE], numlan="default", settings=settings) == [
		(EN, "The quick brown fox "),
		"|",
		(EN, "jumps over the lazy "),
		"|",
		(EN, "dog, then it sleeps."),
	]
	(synth,) = synth_calls
	assert [call for call in synth._taskManager.calls if call[0] == "break"] == [("break", 0.01)] * 2


PUNCTUATION = stage_settings(punctuation=True)
NUMBER_MODE = stage_settings(number_mode="number")
# "Follow main language" reads digits as today's "ignore numbers" off did.
MAIN = {"numlan": "main"}
# "Follow surrounding text language" reads digits as today's "ignore numbers" on did.
FOLLOW = {"numlan": "default"}

MAIN_ROWS = [
	pytest.param(["中12"], {}, [(ZH, "中"), (EN, "12")], id="zh12"),
	pytest.param(["中文 12"], {}, [(ZH, "中文 "), (EN, "12")], id="zh-space-12"),
	pytest.param([L("de_DE"), "abc 12 中"], {}, [(EN, "abc 12 "), (ZH, "中")], id="tagged-de"),
	pytest.param(["abc 123 def"], {"main": "zh"}, [(EN, "abc "), (ZH, "123 "), (EN, "def")], id="zh-main"),
	pytest.param(
		["中12.5 ok"],
		{"settings": NUMBER_MODE},
		[(ZH, "中"), (EN, "1 2 full stop en 5 ok")],
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
		# Number mode joins the pieces with spaces (decided by the user, 2026-11-01); detection reads
		# the harness's English name of "." as English.
		[(ZH, "中1 2 "), (EN, "full stop en 5 ok")],
		id="number-mode",
	),
]


@TIMINGS
@pytest.mark.parametrize(("sequence", "options", "expected"), FOLLOW_ROWS)
def test_follow_language_numbers(monkeypatch, sequence, options, expected, timing):
	assert speak_through_stages(monkeypatch, sequence, timing=timing, **FOLLOW, **options) == expected


# Under "Follow surrounding text language" a Devanagari digit goes to the Nepali voice
# (spec fix/script-digit-language §7.4).
@TIMINGS
@pytest.mark.parametrize(
	("sequence", "expected"),
	[(["२०८१"], [(NE, "२०८१")]), (["link", "२०८१"], [(EN, "link"), (NE, "२०८१")])],
	ids=["alone", "after-english-item"],
)
def test_follow_gives_script_digits_to_their_language(monkeypatch, sequence, expected, timing):
	monkeypatch.setitem(VOICES, "ne", NE)
	assert speak_through_stages(monkeypatch, sequence, numlan="default", timing=timing) == expected


@TIMINGS
def test_main_keeps_script_digits_in_the_main_voice(monkeypatch, timing):
	monkeypatch.setitem(VOICES, "ne", NE)
	assert speak_through_stages(monkeypatch, ["२०८१"], numlan="main", timing=timing) == [(EN, "२०८१")]


@TIMINGS
def test_a_hidden_number_language_reads_script_digits_as_follow(monkeypatch, timing):
	# A stored locale that no offered voice speaks is spoken as "default" (NumberLanguageChoice.spoken).
	monkeypatch.setitem(VOICES, "ne", NE)
	monkeypatch.setattr(VoiceManager, "all_languages", ("en", "zh_TW", "ne"))
	assert speak_through_stages(monkeypatch, ["२०८१"], numlan="ne", timing=timing) == [(NE, "२०८१")]


@TIMINGS
def test_digit_mode_names_the_symbol_before_detection(monkeypatch, timing):
	# A known limitation (spec fix/script-digit-language §2.3): the symbol is named in the language
	# in force before detection, which then reads the name by its own letters.
	monkeypatch.setitem(VOICES, "ne", NE)
	result = speak_through_stages(monkeypatch, ["५.५"], numlan="default", timing=timing, settings=NUMBER_MODE)
	assert result == [(NE, "५ "), (EN, "full stop en "), (NE, "५")]


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
	result = speak_through_stages(monkeypatch, ["abc１２３"], numlan="zh_TW", timing=timing)
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
	# A hyphen after a word stays with it (decided by the user, 2026-10-23, U1).
	pytest.param(
		["中 COVID-19 中"],
		{"main": "zh"},
		[(ZH, "中 "), (EN, "COVID-"), (ZH, "19 中")],
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
	result = speak_through_stages(monkeypatch, ["中１２３"], numlan="en", timing=timing)
	assert result == [(ZH, "中"), (EN, "１２３")]


# NVDA's speak() runs processText on each text item after the filters, and appends its chunk
# separator: symbol rules that read the text around a symbol see only that item.
def nvda_processes_each_item(character_processing, locale, level="SOME"):
	"""What NVDA's speak() does to the filtered sequence, with WorldVoice's default of NVDA's own
	language switching off: each text item through the symbol step of processText in the synth's
	language, at symbol *level* ("some" by default), then the chunk separator; empty items dropped.
	"""
	level = getattr(character_processing.SymbolLevel, level)

	def process(sequence):
		return [
			character_processing.processSpeechSymbols(locale, item, level) + "  "
			if isinstance(item, str)
			else item
			for item in sequence
			if item != ""
		]

	return process


NVDA_WARNINGS = pytest.mark.filterwarnings("ignore:codecs.open:DeprecationWarning")
# Where the voice does not change, a number wrapped for detection reaches NVDA's processText in its
# item, as it did before phase 35: NVDA's context rules (a negative number, "1st", a sentence end
# after a digit) read the whole item (batch 1 review C1).
WHOLE_ITEM_ROWS = [
	pytest.param("en", "main", "COVID-19 cases", id="en-main-covid"),
	pytest.param("en", "en", "COVID-19 cases", id="en-locale-covid"),
	pytest.param("en", "main", "the 1st item", id="en-main-1st"),
	pytest.param("en", "en", "the 1st item", id="en-locale-1st"),
	pytest.param("en", "main", "in 2024!", id="en-main-bang"),
	pytest.param("en", "en", "in 2024!", id="en-locale-bang"),
	pytest.param("en", "main", "Is it 5?", id="en-main-question"),
	pytest.param("en", "en", "Is it 5?", id="en-locale-question"),
	pytest.param("zh", "main", "第1名", id="zh-main-rank"),
	pytest.param("zh", "zh_TW", "第1名", id="zh-locale-rank"),
]


@NVDA_WARNINGS
@TIMINGS
@pytest.mark.parametrize(("main", "numlan", "text"), WHOLE_ITEM_ROWS)
def test_numbers_reach_nvda_in_their_item_where_the_voice_stays(
	monkeypatch,
	tmp_path,
	main,
	numlan,
	text,
	timing,
):
	character_processing = load_nvda_character_processing(monkeypatch, tmp_path)
	nvda = nvda_processes_each_item(character_processing, "zh_TW" if main == "zh" else "en")
	result = speak_through_stages(monkeypatch, [text], numlan=numlan, main=main, timing=timing, nvda=nvda)
	assert result == [(ZH if main == "zh" else EN, f"{text}  ")]


# Number mode edge pauses (number-edge-pause spec §4.8, O6): detection passes the breaks through,
# so the voices stay those of today and only pauses are added; _remove_space strips the items.
EDGE_ROWS = [
	pytest.param(
		["第3章"],
		"default",
		"zh",
		[(ZH, "第3章")],
		[(ZH, "第"), "|", (ZH, "3"), "|", (ZH, "章")],
		id="rank-follow",
	),
	pytest.param(
		["第3章"],
		"main",
		"zh",
		[(ZH, "第3章")],
		[(ZH, "第"), "|", (ZH, "3"), "|", (ZH, "章")],
		id="rank-main",
	),
	pytest.param(
		["第3章"],
		"en",
		"zh",
		[(ZH, "第"), (EN, "3"), (ZH, "章")],
		[(ZH, "第"), "|", (EN, "3"), "|", (ZH, "章")],
		id="rank-en",
	),
	pytest.param(
		["中12"],
		"main",
		"en",
		[(ZH, "中"), (EN, "1 2")],
		[(ZH, "中"), "|", (EN, "1 2")],
		id="zh12-main",
	),
	pytest.param(
		["中12"],
		"default",
		"en",
		[(ZH, "中1 2")],
		[(ZH, "中"), "|", (ZH, "1 2")],
		id="zh12-follow",
	),
	pytest.param(
		["abc3中"],
		"default",
		"en",
		[(EN, "abc3"), (ZH, "中")],
		[(EN, "abc"), "|", (EN, "3"), "|", (ZH, "中")],
		id="abc3-follow",
	),
	pytest.param(
		["中 COVID-19 中"],
		"main",
		"zh",
		[(ZH, "中 "), (EN, "COVID-"), (ZH, "1 9 中")],
		[(ZH, "中 "), (EN, "COVID-"), "|", (ZH, "1 9"), "|", (ZH, "中")],
		id="covid-main",
	),
	pytest.param(
		["中 -12 34"],
		"main",
		"en",
		# At a number pause of 0 nothing adds a break, so the two numbers run together.
		[(ZH, "中 "), (EN, "-1 2 3 4")],
		[(ZH, "中"), "|", (EN, "-1 2"), "|", (EN, "3 4")],
		id="sign-main",
	),
	pytest.param(
		["abc 123 def"],
		"zh_TW",
		"zh",
		[(EN, "abc "), (ZH, "1 2 3 "), (EN, "def")],
		[(EN, "abc"), "|", (ZH, "1 2 3"), "|", (EN, "def")],
		id="zh-locale",
	),
]


@TIMINGS
@pytest.mark.parametrize("wait", [0, 10])
@pytest.mark.parametrize(("sequence", "numlan", "main", "wait0", "wait10"), EDGE_ROWS)
def test_number_mode_edges_with_detection(monkeypatch, sequence, numlan, main, wait0, wait10, wait, timing):
	# The edge pause comes with a group size above 0 (decided by the user, 2026-11-01, U4); every
	# number of these rows has at most 3 digits, so a size of 3 cuts none of them.
	settings = stage_settings(number_mode="number", number_wait=wait, group_size=3)
	result = speak_through_stages(
		monkeypatch,
		sequence,
		numlan=numlan,
		main=main,
		timing=timing,
		settings=settings,
	)
	assert result == (wait0 if wait == 0 else wait10)


# Without groups number mode adds no edge pause (U4), so at a number pause of 10 it speaks as at 0,
# except that two numbers that only whitespace separates still get the pause (U5).
NO_GROUP_WAIT10 = {(("中 -12 34",), "main"): [(ZH, "中 "), (EN, "-1 2"), "|", (EN, "3 4")]}


@TIMINGS
@pytest.mark.parametrize(("sequence", "numlan", "main", "wait0", "wait10"), EDGE_ROWS)
def test_number_mode_without_groups_has_no_edges_with_detection(
	monkeypatch,
	sequence,
	numlan,
	main,
	wait0,
	wait10,
	timing,
):
	settings = stage_settings(number_mode="number", number_wait=10, group_size=0)
	result = speak_through_stages(
		monkeypatch,
		sequence,
		numlan=numlan,
		main=main,
		timing=timing,
		settings=settings,
	)
	assert result == NO_GROUP_WAIT10.get((tuple(sequence), numlan), wait0)


@TIMINGS
def test_value_mode_has_no_edges_with_detection(monkeypatch, timing):
	settings = stage_settings(number_wait=10)
	result = speak_through_stages(
		monkeypatch,
		["第3章"],
		numlan="default",
		main="zh",
		timing=timing,
		settings=settings,
	)
	assert result == [(ZH, "第3章")]


@TIMINGS
def test_main_keeps_superscripts_in_the_text(monkeypatch, timing):
	# Decided by the user (2026-10-23, spec §4.7 item 2): "²" is not a digit, so it stays with the text.
	assert speak_through_stages(monkeypatch, ["中²"], timing=timing, **MAIN) == [(ZH, "中²")]


# A stored number language must be one of the choices (phase 35 spec §7.1, Q7); NVDA stores any
# string, and an unknown one broke the settings ring.
@pytest.mark.parametrize("value", ["fr"])
def test_an_unknown_number_language_reads_as_follow(monkeypatch, value):
	synth, _ = _synth(monkeypatch)
	synth._set_numlan(value)
	assert synth._get_numlan() == "default"
	assert synth.speechContext().number_language == "default"
	(warning,) = synth.warnings
	assert value in warning


class NvdaSettings:
	"""What NVDA's loadSettings(onlyChanged=True) and saveSettings do with the number language."""

	def __init__(self, synth, stored):
		self.synth, self.conf = synth, {"numlan": stored}

	def load_changed(self):
		# synthDriverHandler.py:402-408: a setting is set only when it differs from the config.
		if self.synth._get_numlan() != self.conf["numlan"]:
			self.synth._set_numlan(self.conf["numlan"])

	def save(self):
		# autoSettings.py:159-163: the property is written back to the config.
		self.conf["numlan"] = self.synth._get_numlan()


@pytest.mark.parametrize("hidden_first", [True, False], ids=["hidden-on-load", "hidden-after-load"])
def test_a_hidden_locale_survives_loading_and_saving_and_comes_back(monkeypatch, hidden_first):
	# A voice or engine change can hide the stored locale ("Keep main locale engine consistent").
	# Decided by orchestrator with the recommended default (final review M2): the choice is kept, as
	# long as an installed voice speaks it, while the speech reads numbers as "default".
	synth, _ = _synth(monkeypatch)
	nvda = NvdaSettings(synth, "zh_TW")
	if hidden_first:
		synth._voiceManager.languages = ("en",)
	nvda.load_changed()
	synth._voiceManager.languages = ("en",)
	nvda.load_changed()
	nvda.save()
	assert nvda.conf["numlan"] == "zh_TW"
	assert synth.speechContext().number_language == "default"
	# NVDA's settings ring and the Voice panel find the stored value among the choices.
	assert "zh_TW" in synth._get_availableNumlans()
	assert synth.warnings == []
	synth._voiceManager.languages = ("en", "zh_TW")
	assert synth.speechContext().number_language == "zh_TW"


# Decided by the user (2026-10-23, U1/U2, amending Q5): a sign right after a word character is a
# hyphen, as in "COVID-19" or "中-1", and stays with the text before it, in both number-language
# wrappers; after a space, punctuation or at the start it is a sign and moves with the number. NVDA's
# own negative-number rule reads it the same way (ref/nvda/source/locale/en/symbols.dic:19).
def heard_through_nvda(monkeypatch, tmp_path, text, *, main, level="SOME", **options):
	character_processing = load_nvda_character_processing(monkeypatch, tmp_path)
	nvda = nvda_processes_each_item(character_processing, "zh_TW" if main == "zh" else "en", level)
	return speak_through_stages(monkeypatch, [text], main=main, nvda=nvda, **options)


# What the base commit (da7f791, ignore numbers off) gives with NVDA's processing: "main" and the main
# voice's own locale give the same items.
HYPHEN_ROWS = [
	pytest.param("en", "COVID-19", [(EN, "COVID-19  ")], [(EN, "COVID-19  ")], id="en-covid"),
	pytest.param("en", "a-1", [(EN, "a-1  ")], [(EN, "a-1  ")], id="en-a"),
	pytest.param("en", "中-1", [(ZH, "中-"), (EN, "1  ")], [(ZH, "中-  "), (EN, "1  ")], id="en-han"),
	pytest.param(
		"zh",
		"COVID-19 疫情",
		[(EN, "COVID-"), (ZH, "19 疫情  ")],
		[(EN, "COVID-  "), (ZH, "19 疫情  ")],
		id="zh-covid",
	),
	pytest.param("zh", "中-1", [(ZH, "中-1  ")], [(ZH, "中-1  ")], id="zh-han"),
	pytest.param("zh", "a-1", [(EN, "a-"), (ZH, "1  ")], [(EN, "a-  "), (ZH, "1  ")], id="zh-a"),
]


@NVDA_WARNINGS
@pytest.mark.parametrize("value", ["main", "locale"])
@pytest.mark.parametrize(("main", "text", "after", "before"), HYPHEN_ROWS)
def test_a_hyphen_after_a_word_stays_with_it(monkeypatch, tmp_path, main, text, after, before, value):
	numlan = value if value == "main" else ("zh_TW" if main == "zh" else "en")
	for timing, expected in (("after", after), ("before", before)):
		with monkeypatch.context() as patch:
			assert (
				heard_through_nvda(patch, tmp_path, text, main=main, numlan=numlan, timing=timing) == expected
			)


@TIMINGS
@pytest.mark.parametrize(
	("main", "text", "expected"),
	[
		pytest.param("en", "價格是 -3 度", [(ZH, "價格是 "), (EN, "-3 "), (ZH, "度")], id="han-sentence"),
		pytest.param("en", "abc -3 def", [(EN, "abc -3 def")], id="latin-space"),
		pytest.param("zh", "價格是 -3 度", [(ZH, "價格是 -3 度")], id="zh-han-sentence"),
	],
)
def test_a_sign_after_a_space_moves_with_the_number(monkeypatch, main, text, expected, timing):
	assert speak_through_stages(monkeypatch, [text], numlan="main", main=main, timing=timing) == expected


@pytest.mark.parametrize("uwv", [True, False], ids=["detection", "no-detection"])
@TIMINGS
def test_a_number_language_leaves_a_hyphen_with_the_word(monkeypatch, timing, uwv):
	# U2: the early wrapping of a number language whose voice differs follows the same rule.
	result = speak_through_stages(monkeypatch, ["COVID-19 a-1"], numlan="zh_TW", timing=timing, uwv=uwv)
	assert result == [(EN, "COVID-"), (ZH, "19"), (EN, " a-"), (ZH, "1")]


@pytest.mark.parametrize("uwv", [True, False], ids=["detection", "no-detection"])
@TIMINGS
def test_a_number_language_still_takes_a_sign_after_a_space(monkeypatch, timing, uwv):
	result = speak_through_stages(monkeypatch, ["abc -3 def"], numlan="zh_TW", timing=timing, uwv=uwv)
	assert result == [(EN, "abc "), (ZH, "-3"), (EN, " def")]


# Decided by the user (2026-10-23, U3): with detection after NVDA and a number language of another
# voice, the wrapping sees NVDA's symbol names, and a digit in a name ("subscript 2", "上標2") is
# read by the number language's voice. "default" and "main" are unaffected.
@NVDA_WARNINGS
@pytest.mark.parametrize(
	("main", "numlan", "text", "expected"),
	[
		pytest.param(
			"en",
			"zh_TW",
			"H₂O 是水",
			[(EN, "H subscript "), (ZH, "2"), (EN, " O "), (ZH, "是水  ")],
			id="subscript",
		),
		pytest.param(
			"zh",
			"en",
			"面積 30 m²",
			[(ZH, "面積   "), (EN, "30  "), (ZH, " "), (EN, "m "), (ZH, "上標"), (EN, "2"), (ZH, "   ")],
			id="superscript",
		),
	],
)
def test_a_digit_in_a_symbol_name_takes_the_number_language_after_nvda(
	monkeypatch,
	tmp_path,
	main,
	numlan,
	text,
	expected,
):
	assert (
		heard_through_nvda(monkeypatch, tmp_path, text, main=main, numlan=numlan, timing="after") == expected
	)


# Phase 35 spec §11.4 item 5: the voice of every decimal digit, end to end, per number language.
SPOKEN_PIECES = st.lists(st.sampled_from(["abc", "中文", "12", "٣", "１", " ", "२"]), max_size=8).map("".join)


def has_own_script(character):
	"""Whether a character of SPOKEN_PIECES has a script of its own: letters, "٣" and "२", not the
	ASCII and full-width digits or the space."""
	return character.isalpha() or character in "٣२"


def voice_of_each_character(result):
	return [(character, voice) for voice, text in result for character in text]


@TIMINGS
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None, max_examples=50)
@given(
	text=SPOKEN_PIECES,
	main=st.sampled_from(["en", "zh"]),
	numlan=st.sampled_from(["default", "main", "en", "zh_TW"]),
)
# Random draws find these in most runs, not all; the examples make every run check them.
@example(text="中文12", main="en", numlan="main")
@example(text="abc 12", main="zh", numlan="zh_TW")
@example(text="中文 12", main="en", numlan="default")
@example(text="abc२ 12", main="en", numlan="default")
@example(text="२", main="en", numlan="main")
def test_property_each_digit_is_read_by_the_number_language_voice(monkeypatch, timing, text, main, numlan):
	with monkeypatch.context() as patch:
		patch.setitem(VOICES, "ne", NE)
		result = speak_through_stages(patch, [text], numlan=numlan, main=main, timing=timing)
	characters = voice_of_each_character(result)
	assert "".join(character for character, _voice in characters) == text
	main_voice = ZH if main == "zh" else EN
	# Under "default" a digit before the first character with a script of its own takes that
	# character's voice (spec fix/leading-punctuation-language U2); with none, the main voice.
	deciders = [voice for character, voice in characters if has_own_script(character)]
	leading_voice = deciders[0] if deciders else main_voice
	seen_decider = False
	run_voice = None
	for character, voice in characters:
		seen_decider = seen_decider or has_own_script(character)
		if character.isalpha():
			# Every voice is installed: Latin letters are English, Han characters Chinese.
			run_voice = voice
		elif character == "२" and numlan == "default":
			# A Devanagari digit goes to the Nepali voice and opens its run (fix/script-digit-language).
			assert voice == NE, (text, result)
			run_voice = NE
		elif character.isdecimal():
			expected = {
				"default": run_voice or (main_voice if seen_decider else leading_voice),
				"main": main_voice,
				"en": EN,
				"zh_TW": ZH,
			}[numlan]
			assert voice == expected, (text, result)


# Leading punctuation follows the text after it (spec fix/leading-punctuation-language §3, §7.4). Main
# voice English, a Nepali voice installed, the item pause on (10 ms) unless a test says otherwise.
ITEM = stage_settings(item_wait=10)


def spoken(result):
	"""What each voice reads, without pauses and blank text: (voice, text) with each text stripped and
	neighbours of one voice joined."""
	voices = []
	for entry in result:
		if entry == "|" or not entry[1].strip():
			continue
		voice, text = entry[0], entry[1].strip()
		if voices and voices[-1][0] == voice:
			voices[-1] = (voice, voices[-1][1] + text)
		else:
			voices.append((voice, text))
	return voices


def voice_changes(result):
	"""The voices in the order they speak, blank text included, each change once."""
	voices = [entry[0] for entry in result if entry != "|"]
	return [voice for index, voice in enumerate(voices) if index == 0 or voices[index - 1] != voice]


def heard_with_nepali(monkeypatch, sequence, *, numlan="default", settings=ITEM, **options):
	with monkeypatch.context() as patch:
		patch.setitem(VOICES, "ne", NE)
		return spoken(speak_through_stages(patch, sequence, numlan=numlan, settings=settings, **options))


@TIMINGS
@pytest.mark.parametrize(
	("text", "numlan", "main", "expected"),
	[
		pytest.param("(नेपाल)", "default", "en", [(NE, "(नेपाल)")], id="paren"),
		pytest.param("- नेपाल", "default", "en", [(NE, "- नेपाल")], id="dash"),
		pytest.param('" २०८१', "default", "en", [(NE, '" २०८१')], id="quote-script-digits"),
		pytest.param("(2024) नेपाल", "default", "en", [(NE, "(2024) नेपाल")], id="paren-digits"),
		pytest.param("「中文」", "default", "en", [(ZH, "「中文」")], id="corner-bracket"),
		pytest.param("2024年", "default", "en", [(ZH, "2024年")], id="digits-han"),
		pytest.param("2024年", "main", "en", [(EN, "2024"), (ZH, "年")], id="digits-han-main"),
		pytest.param('abc "नेपाल"', "default", "en", [(EN, 'abc "'), (NE, 'नेपाल"')], id="mid-line"),
		pytest.param("「中文」", "default", "zh", [(ZH, "「中文」")], id="corner-bracket-zh"),
		# The harness's value mode spaces "1." (as in FOLLOW_ROWS "next").
		pytest.param("1. Introduction", "default", "zh", [(EN, "1 . Introduction")], id="digits-latin-zh"),
		pytest.param('"Hello"', "default", "ne", [(EN, '"Hello"')], id="mirror"),
	],
)
def test_leading_punctuation_is_read_by_the_voice_of_the_text(
	monkeypatch,
	timing,
	text,
	numlan,
	main,
	expected,
):
	assert heard_with_nepali(monkeypatch, [text], numlan=numlan, main=main, timing=timing) == expected


@NVDA_WARNINGS
@pytest.mark.parametrize(
	("text", "timing", "level", "expected"),
	[
		pytest.param('"नेपाल"', "before", "SOME", [(NE, "नेपाल")], id="quote-before-some"),
		pytest.param('"नेपाल"', "after", "SOME", [(NE, "नेपाल")], id="quote-after-some"),
		pytest.param('"नेपाल"', "before", "MOST", [(NE, "quote नेपाल quote")], id="quote-before-most"),
		pytest.param("(नेपाल)", "after", "SOME", [(NE, "(नेपाल)")], id="paren-after-some"),
		# NVDA has already turned the marks into English names: unchanged from master (spec F4).
		pytest.param(
			"(नेपाल)",
			"after",
			"MOST",
			[(EN, "left paren("), (NE, "नेपाल"), (EN, "right paren)")],
			id="paren-after-most",
		),
	],
)
def test_a_marked_line_through_nvda(monkeypatch, tmp_path, text, timing, level, expected):
	with monkeypatch.context() as patch:
		patch.setitem(VOICES, "ne", NE)
		result = heard_through_nvda(
			patch,
			tmp_path,
			text,
			main="en",
			level=level,
			numlan="default",
			timing=timing,
			settings=ITEM,
		)
	assert spoken(result) == expected
	# A voice given only blank text still costs a switch (spec §3): none is left.
	assert voice_changes(result) == [voice for voice, _text in expected]


@TIMINGS
@pytest.mark.parametrize(
	("text", "pauses"),
	[
		pytest.param('abc, "नेपाल"', {"punctuation": True, "punctuation_characters": ","}, id="punctuation-0"),
		pytest.param(
			'abc, "नेपाल"',
			{"punctuation": True, "punctuation_characters": ",", "punctuation_wait": 30},
			id="punctuation-30",
		),
	],
)
def test_pause_settings_keep_the_voices(monkeypatch, timing, text, pauses):
	# Spec U5: the pauses a stage puts inside an item do not end it. The stages cut the text at their
	# pauses, so only the characters that are no whitespace are compared.
	off = heard_with_nepali(monkeypatch, [text], timing=timing)
	on = heard_with_nepali(
		monkeypatch,
		[text],
		timing=timing,
		settings=stage_settings(item_wait=10, **pauses),
	)
	assert [(voice, "".join(text.split())) for voice, text in on] == [
		(voice, "".join(text.split())) for voice, text in off
	]
	assert [voice for voice, _text in on] == [EN, NE]
	assert off[0][1].endswith(('"', "("))


@TIMINGS
def test_adjacent_items_without_an_item_pause(monkeypatch, timing):
	# The limitation of spec U5: with the item pause at 0 the boundary is invisible.
	result = heard_with_nepali(monkeypatch, ["link", '"नेपाल"'], timing=timing, settings=stage_settings())
	assert result == [(EN, 'link"'), (NE, 'नेपाल"')]


@TIMINGS
def test_an_item_pause_ends_the_item(monkeypatch, timing):
	assert heard_with_nepali(monkeypatch, ["link", '"नेपाल"'], timing=timing) == [(EN, "link"), (NE, '"नेपाल"')]


@TIMINGS
@pytest.mark.parametrize(
	("sequence", "numlan", "options", "expected"),
	[
		pytest.param(
			["(नेपाल)"],
			"default",
			{"settings": stage_settings(item_wait=10, punctuation=True, punctuation_characters="(")},
			[(NE, "(नेपाल)")],
			id="configured-paren",
		),
		pytest.param(["-", "नेपाल"], "default", {}, [(NE, "-नेपाल")], id="dash-item"),
		pytest.param(["(", "1", "नेपाल"], "default", {}, [(NE, "(1नेपाल")], id="paren-digit-items"),
		pytest.param(["(", "1", "नेपाल"], "main", {}, [(EN, "(1"), (NE, "नेपाल")], id="paren-digit-items-main"),
		pytest.param(["Price", "100", "नेपाल"], "default", {}, [(EN, "Price100"), (NE, "नेपाल")], id="price"),
	],
)
def test_an_utterance_start_looks_ahead(monkeypatch, timing, sequence, numlan, options, expected):
	assert heard_with_nepali(monkeypatch, sequence, numlan=numlan, timing=timing, **options) == expected


@TIMINGS
def test_a_main_number_after_leading_punctuation_keeps_its_item(monkeypatch, timing):
	# Spec D3: the wrapped number and the text around it keep master's languages.
	result = heard_with_nepali(monkeypatch, ["नेपाल (2024) नेपाल"], numlan="main", timing=timing)
	assert result == [(NE, "नेपाल ("), (EN, "2024)"), (NE, "नेपाल")]


# Review I1, decided by the user (2026-11-10, option b): with a specific number language, an item that
# ends with a number keeps the item pause before the next item, and the next item's leading marks
# follow its own text, whatever the number pause.
@TIMINGS
@pytest.mark.parametrize(
	("items", "pauses"),
	[
		pytest.param(["abc 12", '"नेपाल"'], {"group_size": 3, "number_wait": 0}, id="groups-no-number-pause"),
		pytest.param(["abc 12", '"नेपाल"'], {"group_size": 3, "number_wait": 10}, id="groups-number-pause"),
		pytest.param(["Total 12", '"नेपाल"'], {"group_size": 0, "number_wait": 10}, id="near-default"),
	],
)
def test_an_item_ending_with_a_number_language_number_keeps_its_boundary(monkeypatch, timing, items, pauses):
	with monkeypatch.context() as patch:
		patch.setitem(VOICES, "ne", NE)
		result = speak_through_stages(
			patch,
			items,
			numlan="zh_TW",
			timing=timing,
			settings=stage_settings(item_wait=10, **pauses),
		)
	assert spoken(result) == [(EN, items[0].split()[0]), (ZH, "12"), (NE, '"नेपाल"')]
	voices = [entry if entry == "|" else entry[0] for entry in result]
	assert voices[voices.index(ZH) + 1] == "|"


# The two invariants end to end (spec fix/leading-punctuation-language §4.3, §7.3).
INVARIANT_PIECES = ["abc", "नेपाल", "中文", "12", "34", " ", ",", ".", "(", ")", '"', "「", "-", "२", "ー"]
# Index markers are told apart from the text by their number.
INVARIANT_INDEX = 7
# Text items with document language commands and index commands among them (review M2). Utterance ends
# are left to the detector's properties: heard() cannot read an EndUtteranceCommand (spec F9).
INVARIANT_ITEMS = st.lists(
	st.one_of(
		st.lists(st.sampled_from(INVARIANT_PIECES), min_size=1, max_size=5).map("".join),
		st.lists(st.sampled_from(INVARIANT_PIECES), min_size=1, max_size=5).map("".join),
		st.builds(LangChangeCommand, st.sampled_from([None, "de_DE", "en", "zh_TW", "ne_NP"])),
		st.builds(IndexCommand, st.just(INVARIANT_INDEX)),
	),
	min_size=1,
	max_size=4,
)


@st.composite
def pauses_on(draw):
	"""A random configuration of the four pauses that are inside an item."""
	return {
		"punctuation": draw(st.booleans()),
		"punctuation_characters": ',.("',
		"punctuation_wait": draw(st.sampled_from((0, 5, 30))),
		"number_wait": draw(st.sampled_from((0, 10))),
		"segment_length": draw(st.sampled_from((0, 4))),
		"segment_wait": 10,
		"unspaced_wait": draw(st.sampled_from((0, 10))),
	}


def voiced_characters(result):
	"""(character, voice) for each character that is no whitespace."""
	return [
		(character, voice) for character, voice in voice_of_each_character(result) if not character.isspace()
	]


def voice_change_count(result):
	"""How often the voice changes, a voice given only whitespace included (spec §3)."""
	voices = [voice for voice, _text in result]
	return sum(1 for before, after in pairwise(voices) if before != after)


def heard_for_property(monkeypatch, items, **options):
	"""What is heard, without pauses and index markers; an entry that only held markers is dropped."""
	with monkeypatch.context() as patch:
		patch.setitem(VOICES, "ne", NE)
		result = speak_through_stages(patch, items, **options)
	marker = f"[{INVARIANT_INDEX}]"
	entries = [(entry[0], entry[1].replace(marker, "")) for entry in result if entry != "|"]
	return [(voice, text) for voice, text in entries if text]


# Invariant 2 (U5, U6): with the item pause on, the pauses inside an item never change a voice.
@TIMINGS
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None, max_examples=100)
@given(
	items=INVARIANT_ITEMS,
	# Specific number languages too: their wrappers keep the item boundary (review I1).
	numlan=st.sampled_from(["default", "main", "zh_TW", "en"]),
	main=st.sampled_from(["en", "zh"]),
	group_size=st.sampled_from([0, 3]),
	pauses=pauses_on(),
)
@example(items=['abc, "नेपाल"'], numlan="default", main="en", group_size=0, pauses={"punctuation": True})
@example(items=["abc 12 34 (नेपाल)"], numlan="default", main="en", group_size=0, pauses={"number_wait": 10})
@example(items=["abc 12", '"नेपाल"'], numlan="zh_TW", main="en", group_size=3, pauses={"number_wait": 10})
@example(items=["Total 12", '"नेपाल"'], numlan="zh_TW", main="en", group_size=0, pauses={"number_wait": 10})
def test_property_pause_settings_do_not_change_voices(
	monkeypatch,
	timing,
	items,
	numlan,
	main,
	group_size,
	pauses,
):
	common = {"numlan": numlan, "main": main, "timing": timing}
	off = heard_for_property(
		monkeypatch,
		items,
		settings=stage_settings(item_wait=10, group_size=group_size),
		**common,
	)
	on_settings = stage_settings(
		item_wait=10,
		group_size=group_size,
		**{"punctuation_characters": ',.("', **pauses},
	)
	on = heard_for_property(monkeypatch, items, settings=on_settings, **common)
	assert voiced_characters(on) == voiced_characters(off), (items, on, off)


# Invariant 1 (D6) end to end: never more voice changes than the rule before, whatever the pauses.
@TIMINGS
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None, max_examples=100)
@given(
	items=INVARIANT_ITEMS,
	# Specific number languages too: their wrappers keep the item boundary (review I1).
	numlan=st.sampled_from(["default", "main", "zh_TW", "en"]),
	main=st.sampled_from(["en", "zh"]),
	item_wait=st.sampled_from([0, 10]),
	pauses=pauses_on(),
)
@example(items=['"नेपाल"'], numlan="default", main="en", item_wait=10, pauses={})
def test_property_never_more_voice_changes_than_today(
	monkeypatch,
	timing,
	items,
	numlan,
	main,
	item_wait,
	pauses,
):
	settings = stage_settings(item_wait=item_wait, **{"punctuation_characters": ',.("', **pauses})
	common = {"numlan": numlan, "main": main, "timing": timing, "settings": settings}
	new = heard_for_property(monkeypatch, items, **common)
	old = heard_for_property(monkeypatch, items, oracle=True, **common)
	assert [character for character, _ in voiced_characters(new)] == [
		character for character, _ in voiced_characters(old)
	], (items, new, old)
	assert voice_change_count(new) <= voice_change_count(old), (items, new, old)
