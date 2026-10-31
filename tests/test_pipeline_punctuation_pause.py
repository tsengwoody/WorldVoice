import pytest
from pipeline_harness import load_pipeline_module, load_settings_module, punctuation_settings


def run_punctuation_filters(module, speech_sequence):
	return list(
		module.inject_punctuation_pause(speech_sequence, module._test_settings, module.GENERIC_CONTEXT),
	)


def shape(sequence):
	return [item if isinstance(item, str) else (type(item).__name__, item.time) for item in sequence]


def test_zero_wait_splits_off_the_mark_but_an_existing_break_suppresses_the_pause(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0))
	existing_break = BreakCommand(30)

	result = run_punctuation_filters(module, ["Hello.", existing_break, "World"])

	assert result == ["Hello", ".", existing_break, "World"]


@pytest.mark.parametrize(
	("global_factor", "factor", "expected"),
	[
		# Global factor 0: the pause is 0 ms, but the switch still splits the text at the mark.
		(0, 30, 0),
		(10, 30, 30),
		# No cap: 10 units of 100 ms.
		(100, 100, 1000),
	],
)
def test_the_punctuation_pause_follows_the_global_factor(monkeypatch, global_factor, factor, expected):
	# Decided by the user (2026-10-26): global units times the punctuation factor, like every pause.
	module, _BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0))
	pipeline = {
		"globalWaitFactor": global_factor,
		"punctuationWaitFactor": factor,
		"punctuationPauseCharacters": ".",
	}
	settings = load_settings_module(
		monkeypatch,
		{"WorldVoice": {"pipeline": pipeline}},
	).pipeline_settings.get()

	result = list(module.inject_punctuation_pause(["Hello. World"], settings, module.GENERIC_CONTEXT))

	assert shape(result) == ["Hello", ".", ("PunctuationBreakCommand", expected), " World"]


def test_zero_wait_removal_still_pauses_and_a_disabled_switch_changes_nothing(monkeypatch):
	settings = punctuation_settings(0, remove_characters=True)
	module, _BreakCommand = load_pipeline_module(monkeypatch, settings)
	assert shape(run_punctuation_filters(module, ["Hello, world."])) == [
		"Hello",
		("PunctuationBreakCommand", 0),
		" world",
		".",
	]

	settings.scaled_punctuation_wait = lambda: 250
	settings.punctuation_pause_enabled = False
	assert run_punctuation_filters(module, ["Hello, world."]) == ["Hello, world."]


def test_removal_applies_at_pause_points_with_or_without_new_breaks(monkeypatch):
	module, BreakCommand = load_pipeline_module(
		monkeypatch,
		punctuation_settings(250, remove_characters=True),
	)
	existing_break = BreakCommand(30)

	result = run_punctuation_filters(module, ["Hello. World.", existing_break, "."])

	assert result[0] == "Hello"
	assert type(result[1]).__name__ == "PunctuationBreakCommand"
	assert result[1].time == 250
	assert result[2] == " World"
	assert result[3] is existing_break
	assert result[4] == "."
	assert len(result) == 5


def test_removal_preserves_numeric_punctuation_without_a_pause(monkeypatch):
	module, _BreakCommand = load_pipeline_module(
		monkeypatch,
		punctuation_settings(250, remove_characters=True),
	)

	result = run_punctuation_filters(module, ["Value 3.5 and 12,500. Next"])

	assert result[0] == "Value 3.5 and 12,500"
	assert type(result[1]).__name__ == "PunctuationBreakCommand"
	assert result[2] == " Next"


ZERO_WAIT = {
	# Switch on, wait 0: every pause point gets a 0 ms break; removal only drops the mark.
	False: (
		[
			"Hello",
			",",
			("PunctuationBreakCommand", 0),
			" world",
			".",
			("PunctuationBreakCommand", 0),
			" Bye",
			".",
		],
		["Hi", ".", ("PunctuationBreakCommand", 0), "there"],
	),
	True: (
		["Hello", ("PunctuationBreakCommand", 0), " world", ("PunctuationBreakCommand", 0), " Bye", "."],
		["Hi", ("PunctuationBreakCommand", 0), "there"],
	),
}


@pytest.mark.parametrize("remove", [False, True])
def test_zero_wait_pauses_at_every_point_whether_or_not_marks_are_removed(monkeypatch, remove):
	module, _BreakCommand = load_pipeline_module(
		monkeypatch,
		punctuation_settings(0, remove_characters=remove),
	)
	inside, between = ZERO_WAIT[remove]

	assert shape(run_punctuation_filters(module, ["Hello, world. Bye."])) == inside
	assert shape(run_punctuation_filters(module, ["Hi.", "there"])) == between


PAUSE = ("PunctuationBreakCommand", 250)


@pytest.mark.parametrize(
	("characters", "item", "expected"),
	[
		# A space is a character like any other: every space between words is a pause point.
		(
			" ",
			"\u4f60\u597d \u4e16\u754c hello world",
			["\u4f60\u597d", " ", PAUSE, "\u4e16\u754c", " ", PAUSE, "hello", " ", PAUSE, "world"],
		),
		# A comma followed by a space: both the comma and the space pause.
		(
			"\uff0c ",
			"\u4f60\u597d\uff0c\u4e16\u754c hello",
			["\u4f60\u597d", "\uff0c", PAUSE, "\u4e16\u754c", " ", PAUSE, "hello"],
		),
	],
	ids=["space", "comma and space"],
)
def test_a_space_in_the_list_pauses_at_every_such_space(monkeypatch, characters, item, expected):
	# Decided by the user (2026-10-23): the list keeps every character typed, spaces included.
	settings = punctuation_settings(250)
	settings.punctuation_pause_characters = characters
	module, _BreakCommand = load_pipeline_module(monkeypatch, settings)

	assert shape(run_punctuation_filters(module, [item])) == expected


@pytest.mark.parametrize(
	"remove,sequence,expected",
	[
		# Rule 1: no point before a digit.
		(
			False,
			["Value 3.5 and 12,500. Next"],
			["Value 3.5 and 12,500", ".", ("PunctuationBreakCommand", 0), " Next"],
		),
		# Rule 2: one point per run of marks.
		(False, ["Hi.,  there"], ["Hi", ".,", ("PunctuationBreakCommand", 0), "  there"]),
		# Rule 5: never at the end.
		(False, ["Bye."], ["Bye", "."]),
		# Rule 3: an internal point needs non-blank text after it in the item.
		(False, ["Bye. ."], ["Bye", ".", " ", "."]),
		# Rule 4: trailing spaces after the last mark do not hide a boundary point.
		(False, ["Hi. ", "there"], ["Hi", ".", " ", ("PunctuationBreakCommand", 0), "there"]),
		# Rule 4: an existing break suppresses the boundary pause but not boundary removal.
		(True, ["Hello.", "existing", "World"], ["Hello", ("BreakCommand", 30), "World"]),
	],
)
def test_zero_wait_keeps_the_pause_point_rules(monkeypatch, remove, sequence, expected):
	module, BreakCommand = load_pipeline_module(
		monkeypatch,
		punctuation_settings(0, remove_characters=remove),
	)
	sequence = [BreakCommand(30) if item == "existing" else item for item in sequence]

	assert shape(run_punctuation_filters(module, sequence)) == expected


@pytest.mark.parametrize(
	"sequence,expected",
	[
		# Review M2: a mark removed between two number breaks leaves one pause, the earlier one.
		(["12", "n1", ".", "n2", "5"], ["12", "n1", "5"]),
		# Language commands make no sound, so the breaks around them still meet.
		(["12", "n1", "lang", ".", "n2", "5"], ["12", "n1", "lang", "5"]),
		# Blank text makes no sound either.
		(["12", "n1", " ", ".", "n2", "5"], ["12", "n1", " ", "5"]),
		# Spoken text between them: the breaks never meet.
		(["12", "n1", "x", ".", "n2", "5"], ["12", "n1", "x", "n2", "5"]),
		# No break before the mark: the break after it stays.
		([".", "n2", "5"], ["n2", "5"]),
		# Only the break the removal brought next to the earlier one is dropped.
		(["12", "n1", ".", "n2", "n3", "5"], ["12", "n1", "n3", "5"]),
		# Removal changes only marks around any other break (the earlier spec's rule).
		(["12", "b1", ".", "b2", "5"], ["12", "b1", "b2", "5"]),
		(["12", "n1", ".", "b2", "5"], ["12", "n1", "b2", "5"]),
		(["12", "b1", ".", "n2", "5"], ["12", "b1", "n2", "5"]),
		# A later break counts, not the first one sent.
		(["12", "n1", "b1", ".", "n2", "5"], ["12", "n1", "b1", "n2", "5"]),
	],
)
def test_removal_never_leaves_two_number_breaks_that_were_apart(monkeypatch, sequence, expected):
	module, BreakCommand = load_pipeline_module(
		monkeypatch,
		punctuation_settings(250, remove_characters=True),
	)
	commands = {
		"b1": BreakCommand(10),
		"b2": BreakCommand(20),
		"n1": module.NumberBreakCommand(10),
		"n2": module.NumberBreakCommand(20),
		"n3": module.NumberBreakCommand(30),
		"lang": module.WVLangChangeCommand("en"),
	}
	result = run_punctuation_filters(module, [commands.get(item, item) for item in sequence])

	assert result == [commands.get(item, item) for item in expected]


# Number edge breaks (number-edge-pause spec §4.6.3: E1 and E2). The sequences are what the number
# stage gives in number mode with a 10 ms number wait.
EDGE_CHARACTERS = "。，."
E = ("NumberEdgeBreakCommand", 10)
NB = ("NumberBreakCommand", 10)


def P(time):
	return ("PunctuationBreakCommand", time)


# ASCII ids: pytest escapes a non-ASCII id, and mutmut's second collection escapes it again.
@pytest.mark.parametrize(
	("sequence", "remove", "wait", "expected"),
	[
		# Nothing follows: the mark at the end is never a pause point.
		(["第", "E", "3", "E", "。"], False, 50, ["第", E, "3", E, "。"]),
		(["第", "E", "3", "E", "。"], True, 50, ["第", E, "3", E, "。"]),
		(["第", "E", "3", "E", "。下一章"], False, 50, ["第", E, "3", E, "。", P(50), "下一章"]),
		# Removal brings the edge break and the punctuation break together: the longer stays.
		(["第", "E", "3", "E", "。下一章"], True, 50, ["第", E, "3", P(50), "下一章"]),
		(["3", "E", "，下"], False, 50, ["3", E, "，", P(50), "下"]),
		(["3", "E", "，下"], True, 50, ["3", P(50), "下"]),
		# E1: the edge break before the number does not suppress the boundary pause.
		(["Total. ", "E", "1", "NB", "2"], False, 50, ["Total", ".", " ", P(50), "1", NB, "2"]),
		(["Total. ", "E", "1", "NB", "2"], True, 50, ["Total", " ", P(50), "1", NB, "2"]),
		(["1", "E", "，", "E", "2"], False, 50, ["1", E, "，", P(50), "2"]),
		(["1", "E", "，", "E", "2"], True, 50, ["1", P(50), "2"]),
		# A 0 ms punctuation pause leaves the number apart by its edge break.
		(["第", "E", "3", "E", "。下一章"], True, 0, ["第", E, "3", E, "下一章"]),
		(["Total. ", "E", "1", "NB", "2"], False, 0, ["Total", ".", " ", E, "1", NB, "2"]),
		# A tie keeps the punctuation break.
		(["a.", "E50", "b"], False, 50, ["a", ".", P(50), "b"]),
	],
	ids=[
		"zh-3-end-off",
		"zh-3-end-on",
		"zh-3-next-off",
		"zh-3-next-on",
		"3-comma-off",
		"3-comma-on",
		"Total-off",
		"Total-on",
		"1-comma-2-off",
		"1-comma-2-on",
		"zh-3-next-on-wait0",
		"Total-off-wait0",
		"tie",
	],
)
def test_an_edge_break_keeps_the_punctuation_pause(monkeypatch, sequence, remove, wait, expected):
	settings = punctuation_settings(wait, remove_characters=remove)
	settings.punctuation_pause_characters = EDGE_CHARACTERS
	module, _BreakCommand = load_pipeline_module(monkeypatch, settings)
	commands = {
		"E": module.NumberEdgeBreakCommand(10),
		"E50": module.NumberEdgeBreakCommand(50),
		"NB": module.NumberBreakCommand(10),
	}
	result = run_punctuation_filters(module, [commands.get(item, item) for item in sequence])
	assert shape(result) == expected


class Marker:
	"""A speech command no stage knows, such as NVDA's IndexCommand."""


@pytest.mark.parametrize(
	("sequence", "expected"),
	[
		# Language and index commands make no sound: they are part of the run.
		(["a", "E10", "lang", "marker", "PB50", "b"], ["a", "lang", "marker", "PB50", "b"]),
		# A run without an edge break is untouched.
		(["a", "NB10", "PB50", "b"], ["a", "NB10", "PB50", "b"]),
		(["a", "E10", " ", "PB0", "b"], ["a", "E10", " ", "b"]),
		(["a", "E10", "E20"], ["a", "E20"]),
		(["E10", "PB10", "a"], ["PB10", "a"]),
		(["a", "E10", "E10b", "b"], ["a", "E10", "b"]),
		# One break object can sit in several runs: each run is decided on its own.
		(["a", "E10", "PB50", "b", "E10", "c"], ["a", "PB50", "b", "E10", "c"]),
	],
	ids=["transparent", "no-edge", "blank-text", "end", "start-tie", "edges-tie", "shared-instance"],
)
def test_merge_edge_breaks(monkeypatch, sequence, expected):
	module, _BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0))
	commands = {
		"E10": module.NumberEdgeBreakCommand(10),
		"E10b": module.NumberEdgeBreakCommand(10),
		"E20": module.NumberEdgeBreakCommand(20),
		"NB10": module.NumberBreakCommand(10),
		"PB0": module.PunctuationBreakCommand(0),
		"PB10": module.PunctuationBreakCommand(10),
		"PB50": module.PunctuationBreakCommand(50),
		"lang": module.WVLangChangeCommand("en"),
		"marker": Marker(),
	}
	result = list(module._merge_edge_breaks([commands.get(item, item) for item in sequence]))
	assert len(result) == len(expected)
	assert all(after is commands.get(name, after) for after, name in zip(result, expected))
	assert [item for item in result if isinstance(item, str)] == [
		item for item in expected if item not in commands
	]
