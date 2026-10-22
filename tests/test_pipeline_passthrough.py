"""Pipeline stages on the inputs the other pipeline tests skip: commands, empty input, off switches."""

from types import SimpleNamespace

import pytest
from pipeline_harness import load_pipeline_module, punctuation_settings


class Marker:
	"""A speech command no stage knows, such as NVDA's IndexCommand."""


@pytest.fixture
def env(monkeypatch):
	settings = punctuation_settings(0)
	module, break_command = load_pipeline_module(monkeypatch, settings)
	return SimpleNamespace(
		module=module,
		settings=settings,
		BreakCommand=break_command,
		generic=module.GENERIC_CONTEXT,
	)


def voices_context(module, number_language):
	return module.SpeechContext(
		supports_roles=True,
		language="en",
		number_language=number_language,
		default_voice=SimpleNamespace(name="A", language="en"),
		voice_name_for_language={"en": "A", "fr": "F", "zh": "Z"}.get,
	)


def kinds(sequence, break_command):
	result = []
	for item in sequence:
		if isinstance(item, str):
			result.append(item)
		elif isinstance(item, break_command):
			result.append((type(item).__name__, item.time))
		elif hasattr(item, "lang"):
			result.append(("lang", item.lang))
		else:
			result.append(item)
	return result


@pytest.mark.parametrize(
	("text", "expected"),
	[
		("12,345,678", "12345678"),
		("1,234.56", "1234.56"),
		("-1,234", "-1234"),
		("1,234,", "1234,"),
		# German notation: the run after the dot is a valid thousands run (spec F7, accepted risk).
		("1.234,567", "1.234567"),
		("1,000,000,000", "1000000000"),
		("12,345 and 3,4", "12345 and 3,4"),
		# The whole comma/digit run must be valid, or it stays as it is (V1).
		("1,2", "1,2"),
		("1234,567", "1234,567"),
		("1,234,56", "1,234,56"),
		("1, 234", "1, 234"),
		("3,14", "3,14"),
		("a,1,234", "a,1,234"),
		("1,234,,5", "1,234,,5"),
	],
)
def test_value_mode_removes_only_valid_thousands_separators(env, text, expected):
	assert list(env.module.remove_thousands_separators([text], env.settings, env.generic)) == [expected]


@pytest.mark.parametrize("mode", ["none", "number", "group"])
def test_thousands_step_passes_through_other_modes(env, mode):
	env.settings.number_mode = mode
	assert list(env.module.remove_thousands_separators(["12,345"], env.settings, env.generic)) == ["12,345"]


def test_thousands_step_passes_commands_and_split_items(env):
	# Browse mode may split one number at a formatting change: nothing is joined across items.
	sequence = ["12", Marker(), ",345"]
	result = list(env.module.remove_thousands_separators(sequence, env.settings, env.generic))
	assert result == sequence
	assert result[1] is sequence[1]


def test_off_mode_leaves_the_sequence_unchanged(env):
	# "off" skips number-mode processing entirely, the dot rule included (V3).
	env.settings.number_mode = "none"
	sequence = ["12.5 a. 3", Marker(), "3."]
	result = list(env.module.inject_number_mode(sequence, env.settings, env.generic))
	assert result == sequence
	assert result[1] is sequence[1]


def test_speech_dictionaries_process_text_only(env, monkeypatch):
	monkeypatch.setattr(env.module.speechDictHandler, "processText", lambda text: text.upper())
	marker = Marker()
	result = list(env.module.apply_speech_dictionaries(["abc", marker, "d"], env.settings, env.generic))
	assert result == ["ABC", marker, "D"]


def test_speech_viewer_hands_on_the_sequence_unchanged(env):
	marker = Marker()
	assert env.module.speech_viewer(iter(["a", marker]), env.settings, env.generic) == ["a", marker]


def test_number_wait_drops_blank_text_but_not_commands(env):
	env.settings.scaled_number_wait = lambda: 40
	marker = Marker()
	result = list(env.module.number_wait_factor(["1", "  ", marker, "2", " 3 "], env.settings, env.generic))
	# A command between two numbers keeps them apart; adjacent numbers get the pause.
	assert kinds(result, env.BreakCommand) == ["1", marker, "2", ("NumberBreakCommand", 40), "3"]


def test_number_language_follows_each_language_change_in_the_sequence(env):
	module = env.module
	ctx = voices_context(module, number_language="zh")
	marker = Marker()
	sequence = ["x 1", module.LangChangeCommand("fr"), marker, "y 2", module.LangChangeCommand(None), "3"]
	result = list(module.inject_number_language(sequence, env.settings, ctx))
	# Each number switches to the number language and back to the language in force there;
	# other commands leave that language alone.
	assert kinds(result, env.BreakCommand) == [
		"x ",
		("lang", "zh"),
		"1",
		("lang", "en"),
		("lang", "fr"),
		marker,
		"y ",
		("lang", "zh"),
		"2",
		("lang", "fr"),
		("lang", None),
		("lang", "zh"),
		"3",
		("lang", "en"),
	]


def test_a_number_language_equal_to_the_main_language_still_applies_in_another_language(env):
	# NVDA's own language switching puts the number inside a French stretch: the switch to the
	# number language (the main one, English) must not be mistaken for "already English".
	module = env.module
	ctx = voices_context(module, number_language="en")
	sequence = [module.LangChangeCommand("fr"), "y 2"]
	result = list(module.inject_number_language(sequence, env.settings, ctx))
	assert kinds(result, env.BreakCommand) == [("lang", "fr"), "y ", ("lang", "en"), "2", ("lang", "fr")]


def test_default_number_language_leaves_numbers_alone(env):
	marker = Marker()
	sequence = ["x 1", marker, "2"]
	ctx = voices_context(env.module, number_language="default")
	assert list(env.module.inject_number_language(sequence, env.settings, ctx)) == sequence


def test_number_mode_passes_commands_and_merges_text_around_them(env):
	env.settings.number_mode = "number"
	marker = Marker()
	result = list(env.module.inject_number_mode([marker, "a 12", marker], env.settings, env.generic))
	assert kinds(result, env.BreakCommand) == [marker, "a 1", ("NumberBreakCommand", 0), "2", marker]


def test_merge_starts_a_new_string_after_each_command(env):
	marker = Marker()
	assert list(env.module.merge_consecutive_strings([marker, "a", "b", marker, "c"])) == [
		marker,
		"ab",
		marker,
		"c",
	]


def test_chinese_space_pause_passes_commands(env):
	env.settings.scaled_chinesespace_wait = lambda: 70
	marker = Marker()
	result = list(env.module.inject_chinese_space_pause([marker, "中 文"], env.settings, env.generic))
	assert kinds(result, env.BreakCommand) == [marker, "中", ("BreakCommand", 70), "文"]


def test_punctuation_pause_without_characters_changes_nothing(env):
	settings = punctuation_settings(250, remove_characters=True)
	settings.punctuation_pause_characters = "  "
	assert list(env.module.inject_punctuation_pause(["a. b"], settings, env.generic)) == ["a. b"]


def test_punctuation_pause_of_an_empty_sequence_is_empty(env):
	assert list(env.module.inject_punctuation_pause([], punctuation_settings(250), env.generic)) == []


def test_punctuation_pause_passes_a_leading_command(env):
	marker = Marker()
	result = list(
		env.module.inject_punctuation_pause([marker, "a. b"], punctuation_settings(250), env.generic),
	)
	assert kinds(result, env.BreakCommand) == [marker, "a", ".", ("PunctuationBreakCommand", 250), " b"]


def test_a_number_break_counts_as_an_existing_pause_for_punctuation(env):
	module = env.module
	number_break = module.NumberBreakCommand(50)
	assert isinstance(number_break, env.BreakCommand)
	result = list(
		module.inject_punctuation_pause(["a.", number_break, "b"], punctuation_settings(250), env.generic),
	)
	# The number pause already separates the text, so no punctuation pause stacks on it.
	assert result == ["a", ".", number_break, "b"]


def test_langchange_reorder_flushes_commands_left_after_the_last_text(env):
	module = env.module
	first, second = Marker(), Marker()
	change = module.LangChangeCommand("fr")
	result = list(module.inject_langchange_reorder([first, change, "a", second]))
	assert result == [change, first, "a", second]
