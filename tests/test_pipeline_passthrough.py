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


@pytest.mark.parametrize(("enabled", "expected"), [(True, "12500 and 34"), (False, "12,500 and 3,4")])
def test_comma_between_digits_is_dropped_only_when_enabled(env, enabled, expected):
	env.settings.ignore_comma_between_number = enabled
	marker = Marker()
	result = list(
		env.module.ignore_comma_between_number(["12,500 and 3,4", marker], env.settings, env.generic),
	)
	assert result == [expected, marker]


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
	assert kinds(result, env.BreakCommand) == ["1", marker, "2", ("BreakCommand", 40), "3"]


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


def test_default_number_language_leaves_numbers_alone(env):
	marker = Marker()
	sequence = ["x 1", marker, "2"]
	ctx = voices_context(env.module, number_language="default")
	assert list(env.module.inject_number_language(sequence, env.settings, ctx)) == sequence


def test_digit_symbols_translate_only_in_the_number_language_or_windows(env):
	symbols = {
		"1": SimpleNamespace(language="zh", replacement="一"),
		"2": SimpleNamespace(language="Windows", replacement=""),
		"3": SimpleNamespace(language="fr", replacement="trois"),
	}
	ctx = env.module.SpeechContext(
		supports_roles=True,
		language="en",
		number_language="zh",
		speech_symbols=SimpleNamespace(symbols=symbols),
	)
	# An empty replacement keeps the digit; another language's symbol is not used.
	assert env.module.get_translate_table(ctx) == {ord("1"): "一", ord("2"): "2"}


def test_number_mode_passes_commands_and_merges_text_around_them(env):
	env.settings.number_mode = "number"
	marker = Marker()
	result = list(env.module.inject_number_mode([marker, "a 12", marker], env.settings, env.generic))
	assert result == [marker, "a 1 2", marker]


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


def test_a_pair_number_break_counts_as_an_existing_pause_for_punctuation(env):
	module = env.module
	pair_break = module.PairNumberBreakCommand(50)
	assert isinstance(pair_break, env.BreakCommand)
	result = list(
		module.inject_punctuation_pause(["a.", pair_break, "b"], punctuation_settings(250), env.generic),
	)
	# The pair pause already separates the text, so no punctuation pause stacks on it.
	assert result == ["a", ".", pair_break, "b"]


def test_langchange_reorder_flushes_commands_left_after_the_last_text(env):
	module = env.module
	first, second = Marker(), Marker()
	change = module.LangChangeCommand("fr")
	result = list(module.inject_langchange_reorder([first, change, "a", second]))
	assert result == [change, first, "a", second]
