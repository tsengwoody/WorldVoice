"""The segment pause (feat/segment-pause spec §4.2): a break after at most segment_length characters
with no other pause.

The stage cuts each run of the sequence, the items between two breaks or utterance ends, where
segment_cuts says (tests/test_text_preprocessing.py), and puts one shared SegmentBreakCommand right
after each cut piece. With a segment length or a pause of 0 it leaves the sequence alone (U3).
"""

import sys
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from pipeline_harness import load_pipeline_module, load_settings_module, punctuation_settings


class IndexCommand:
	def __init__(self, index):
		self.index = index

	def __repr__(self):
		return f"IndexCommand({self.index})"


class CallbackCommand:
	"""NVDA's BaseCallbackCommand splits sequences, but the speech manager joins them again."""


@pytest.fixture
def env(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	return SimpleNamespace(
		module=module,
		segments=module.segments,
		commands=sys.modules["speech.commands"],
		chunker=sys.modules["synthDrivers.WorldVoice.text.chunker"],
	)


def seg(length, pause=7):
	return SimpleNamespace(segment_length=length, scaled_segment_wait=lambda: pause)


def stage(env, sequence, length, pause=7):
	return list(
		env.segments.inject_segment_pause(list(sequence), seg(length, pause), env.module.GENERIC_CONTEXT),
	)


def shape(sequence):
	"""Text as itself; a break as (class name, time); any other command as itself."""
	return [
		(type(item).__name__, item.time) if hasattr(item, "time") and not isinstance(item, str) else item
		for item in sequence
	]


SB = ("SegmentBreakCommand", 7)
FOX = ("The quick brown fox jumps over the lazy dog. " * 3).strip()


def test_worked_examples(env):
	c = env.commands
	index, end = IndexCommand(1), c.EndUtteranceCommand()
	rows = [
		(
			[FOX],
			50,
			[
				"The quick brown fox jumps over the lazy dog. The ",
				SB,
				"quick brown fox jumps over the lazy dog. The ",
				SB,
				"quick brown fox jumps over the lazy dog.",
			],
		),
		(
			["Hello world", c.BreakCommand(10), "foo bar baz"],
			8,
			["Hello ", SB, "world", ("BreakCommand", 10), "foo bar ", SB, "baz"],
		),
		(["one two", index, "three"], 8, ["one two", SB, index, "three"]),
		(["a" * 30, "b" * 30], 40, ["a" * 30, SB, "b" * 30]),
		(["中文語音合成" * 3], 5, ["中文語音合", SB, "成中文語音", SB, "合成中文語", SB, "音合成"]),
		(["e\u0301" * 3], 3, ["e\u0301", SB, "e\u0301", SB, "e\u0301"]),
		(["x" * 10 + "   "], 10, ["x" * 10 + "   "]),
		(["Hello world", end, "foo bar"], 8, ["Hello ", SB, "world", end, "foo bar"]),
	]
	for sequence, length, expected in rows:
		assert shape(stage(env, sequence, length)) == expected, sequence


def long_sequence(env):
	return [
		"one two three four five",
		IndexCommand(1),
		"six seven",
		env.commands.BreakCommand(5),
		"eight nine ten",
	]


@pytest.mark.parametrize(("length", "pause"), [(0, 7), (-1, 7), (8, 0)])
def test_nothing_changes_without_a_pause(env, length, pause):
	sequence = long_sequence(env)
	result = stage(env, sequence, length, pause)
	assert len(result) == len(sequence)
	assert all(a is b for a, b in zip(result, sequence, strict=True))


def real_settings(monkeypatch, **changes):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	values = {**module.DEFAULT_PIPELINE_SETTINGS, "segment_length": 3, "segment_wait_factor": 50, **changes}
	return module.PipelineSettings(**values)


def identical(env, sequence, settings):
	result = list(env.segments.inject_segment_pause(list(sequence), settings, env.module.GENERIC_CONTEXT))
	return len(result) == len(sequence) and all(a is b for a, b in zip(result, sequence, strict=True))


@pytest.mark.parametrize("global_factor", [0, 9])
def test_nothing_changes_for_real_settings(env, monkeypatch, global_factor):
	# The global factor scales in whole tens: below 10 every pause is 0 ms (U3).
	settings = real_settings(monkeypatch, global_wait_factor=global_factor)
	assert identical(env, long_sequence(env), settings)


def test_nothing_changes_for_another_synth_in_worldvoice_scope(env, monkeypatch):
	settings = real_settings(monkeypatch, global_wait_factor=10).effective(False)
	assert identical(env, long_sequence(env), settings)
	# Scope "all": another synth gets the segment pause too.
	everywhere = real_settings(monkeypatch, global_wait_factor=10, scope="all").effective(False)
	assert not identical(env, long_sequence(env), everywhere)


def marked_plain_break(env):
	return env.module._plain_break(env.module.NumberEdgeBreakCommand(5))


@pytest.mark.parametrize(
	"make",
	[
		lambda env: env.commands.BreakCommand(5),
		lambda env: env.module.NumberEdgeBreakCommand(5),
		marked_plain_break,
		lambda env: env.commands.BreakCommand(0),
		lambda env: env.commands.EndUtteranceCommand(),
		lambda env: env.commands.ConfigProfileTriggerCommand(),
	],
	ids=["break", "number-edge", "marked-plain", "zero-break", "end-utterance", "profile-trigger"],
)
def test_the_count_restarts_at(env, make):
	sequence = ["aaaa", make(env), "bbbb"]
	assert stage(env, sequence, 6) == sequence


@pytest.mark.parametrize(
	"make",
	[
		lambda env: env.commands.LangChangeCommand("fr"),
		lambda env: env.module.WVLangChangeCommand("fr"),
		lambda env: IndexCommand(1),
		lambda env: CallbackCommand(),
	],
	ids=["language", "wv-language", "index", "callback"],
)
def test_the_count_goes_on_across(env, make):
	command = make(env)
	assert shape(stage(env, ["aaaa", command, "bbbb"], 6)) == ["aaaa", SB, command, "bbbb"]


def test_the_break_goes_before_the_commands_after_the_cut(env):
	first, second = IndexCommand(1), IndexCommand(2)
	assert shape(stage(env, ["one two", first, second, "three"], 8)) == [
		"one two",
		SB,
		first,
		second,
		"three",
	]


def test_every_cut_shares_one_break(env):
	result = stage(env, ["abcdefghij"], 3)
	breaks = [item for item in result if not isinstance(item, str)]
	assert [item for item in result if isinstance(item, str)] == ["abc", "def", "ghi", "j"]
	assert len(breaks) == 3
	assert all(item is breaks[0] for item in breaks)
	assert type(breaks[0]) is env.module.SegmentBreakCommand
	assert breaks[0].time == 7


def test_a_one_millisecond_pause_still_cuts(env):
	assert shape(stage(env, ["Hello world"], 8, 1)) == ["Hello ", ("SegmentBreakCommand", 1), "world"]


def test_a_blank_item_keeps_the_break_after_it(env):
	assert shape(stage(env, ["aaaa", "  ", "bbbb"], 6)) == ["aaaa", "  ", SB, "bbbb"]


def test_number_stages_and_segments_share_ends_utterance(env):
	ends = env.module.sequence._ends_utterance
	assert env.module.numberStages._ends_utterance is ends
	assert env.segments._ends_utterance is ends


# Properties (spec §9.3, P1-P6). Text from the pieces the cut rule's hand-written tests pin; commands
# that restart the count and commands that do not.

PARTS = st.sampled_from(
	[
		"a",
		"b",
		" ",
		"\n",
		"\t",
		"\u00a0",
		"\u3000",
		"\u200b",
		"\u0301",
		"\u0e33",
		"\u200d",
		"\U0001f3fd",
		"中",
		"ก",
	],
)
TEXT = st.lists(PARTS, max_size=12).map("".join)
# The pipeline is loaded once per test; the stage keeps no state between examples.
SHARED_ENV = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])


def command_strategy(env):
	c = env.commands
	return st.one_of(
		st.builds(IndexCommand, st.integers(0, 9)),
		st.builds(c.BreakCommand, st.integers(0, 20)),
		st.builds(env.module.NumberEdgeBreakCommand, st.integers(1, 20)),
		st.builds(c.EndUtteranceCommand),
		st.builds(c.ConfigProfileTriggerCommand),
		st.builds(c.LangChangeCommand, st.sampled_from(["fr", None])),
	)


def sequences(env):
	return st.lists(st.one_of(TEXT, command_strategy(env)), max_size=8)


def is_inserted(env, item):
	return isinstance(item, env.module.SegmentBreakCommand)


def is_reset(env, item):
	return isinstance(item, env.commands.BreakCommand) or env.module.sequence._ends_utterance(item)


def joined(items):
	"""Adjacent text items joined into one."""
	result = []
	for item in items:
		if isinstance(item, str) and result and isinstance(result[-1], str):
			result[-1] += item
		else:
			result.append(item)
	return result


@SHARED_ENV
@given(data=st.data(), length=st.integers(1, 15), pause=st.integers(1, 50))
def test_property_removing_the_breaks_gives_back_the_input(env, data, length, pause):
	sequence = data.draw(sequences(env))
	result = stage(env, sequence, length, pause)
	kept = joined(item for item in result if not is_inserted(env, item))
	original = joined(sequence)
	assert len(kept) == len(original)
	for a, b in zip(kept, original, strict=True):
		assert a == b if isinstance(b, str) else a is b


def pieces(env, result):
	"""The text between two inserted breaks, resets or the sequence edges, and whether an inserted
	break ends it."""
	text, found = "", []
	for item in result:
		if isinstance(item, str):
			text += item
		elif is_reset(env, item):
			found.append((text, is_inserted(env, item)))
			text = ""
	found.append((text, False))
	return found


@SHARED_ENV
@given(data=st.data(), length=st.integers(1, 15))
def test_property_pieces_stay_within_the_length(env, data, length):
	for text, cut in pieces(env, stage(env, data.draw(sequences(env)), length)):
		counted = text.lstrip() if cut else text.strip()
		if len(counted) > length:
			assert all(env.chunker._attached(counted, index) for index in range(1, len(counted))), text


@SHARED_ENV
@given(data=st.data(), length=st.integers(-3, 15), pause=st.integers(0, 50))
def test_property_no_pause_leaves_the_sequence_alone(env, data, length, pause):
	if length > 0 and pause > 0:
		length = 0
	sequence = data.draw(sequences(env))
	result = stage(env, sequence, length, pause)
	assert len(result) == len(sequence)
	assert all(a is b for a, b in zip(result, sequence, strict=True))


@SHARED_ENV
@given(data=st.data(), length=st.integers(1, 15))
def test_property_inserted_breaks_have_spoken_text_around_them(env, data, length):
	result = stage(env, data.draw(sequences(env)), length)
	for position, item in enumerate(result):
		if not is_inserted(env, item):
			continue
		for side in (reversed(result[:position]), result[position + 1 :]):
			spoken = False
			for other in side:
				if isinstance(other, str) and other.strip():
					spoken = True
					break
				if is_reset(env, other):
					break
			assert spoken, result


@SHARED_ENV
@given(data=st.data(), length=st.integers(1, 15))
def test_property_no_cut_splits_a_character(env, data, length):
	result = stage(env, data.draw(sequences(env)), length)
	text, cuts = "", []
	for item in [*result, env.commands.BreakCommand(1)]:
		if isinstance(item, str):
			text += item
		elif is_inserted(env, item):
			cuts.append(len(text))
		elif is_reset(env, item):
			assert not any(env.chunker._attached(text, cut) for cut in cuts), (text, cuts)
			text, cuts = "", []


# The stage in the stage table (spec §4.3, O9).


def segment_stage(module):
	(stage,) = [stage for stage in module.STAGES if stage.log_key == "segment_wait_factor"]
	return stage


def scoped_settings(scope, length=8, pause=7):
	settings = punctuation_settings(0)
	settings.scope = scope
	settings.segment_length = length
	settings.scaled_segment_wait = lambda: pause
	return settings


def test_another_synth_gets_plain_breaks_at_the_cuts(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, scoped_settings("all"))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	result = segment_stage(module).handler(["Hello world"])
	assert [item for item in result if isinstance(item, str)] == ["Hello ", "world"]
	(pause,) = [item for item in result if not isinstance(item, str)]
	assert type(pause) is BreakCommand
	assert pause.time == 7


def test_the_segment_switch_logs_its_stage(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, scoped_settings("all"))
	sys.modules["config"].conf["WorldVoice"]["log"] = {
		"enable": True,
		**dict.fromkeys(module.LOG_SWITCHES, False),
		"segmentWaitFactor": True,
	}
	writes = []
	monkeypatch.setattr(module.registry, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["Hello world"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
	assert writes == [("segment_wait_factor", "before"), ("segment_wait_factor", "after")]
