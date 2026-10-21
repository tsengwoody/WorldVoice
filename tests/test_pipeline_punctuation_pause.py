import pytest
from pipeline_harness import load_pipeline_module, punctuation_settings


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


def test_positive_punctuation_wait_factor_inserts_a_punctuation_break(monkeypatch):
	module, _BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(250))

	result = run_punctuation_filters(module, ["Hello. World"])

	assert result[0] == "Hello"
	assert result[1] == "."
	assert type(result[2]).__name__ == "PunctuationBreakCommand"
	assert result[2].time == 250
	assert result[3] == " World"


def test_removing_configured_punctuation_preserves_existing_breaks(monkeypatch):
	module, BreakCommand = load_pipeline_module(
		monkeypatch,
		punctuation_settings(250, remove_characters=True),
	)
	existing_break = BreakCommand(30)

	result = run_punctuation_filters(module, ["Hello.", existing_break, "World"])

	assert result == ["Hello", existing_break, "World"]


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


def test_removal_applies_to_pause_between_text_items(monkeypatch):
	module, _BreakCommand = load_pipeline_module(
		monkeypatch,
		punctuation_settings(250, remove_characters=True),
	)

	result = run_punctuation_filters(module, ["Hello.", "World"])

	assert result[0] == "Hello"
	assert type(result[1]).__name__ == "PunctuationBreakCommand"
	assert result[2] == "World"


@pytest.mark.parametrize("characters", [".,", "", "  "])
@pytest.mark.parametrize("wait", [0, 250])
@pytest.mark.parametrize("remove", [False, True])
def test_a_disabled_switch_changes_nothing(monkeypatch, remove, wait, characters):
	settings = punctuation_settings(wait, remove_characters=remove)
	settings.punctuation_pause_enabled = False
	settings.punctuation_pause_characters = characters
	module, BreakCommand = load_pipeline_module(monkeypatch, settings)
	sequence = ["Hello, world. Bye.", "Hi.", BreakCommand(30), "there"]

	assert run_punctuation_filters(module, sequence) == sequence


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


@pytest.mark.parametrize("characters", ["", "  "])
@pytest.mark.parametrize("remove", [False, True])
def test_an_empty_or_blank_list_changes_nothing(monkeypatch, remove, characters):
	settings = punctuation_settings(0, remove_characters=remove)
	settings.punctuation_pause_characters = characters
	module, _BreakCommand = load_pipeline_module(monkeypatch, settings)
	sequence = ["Hello, world.", "Hi.", "there"]

	assert run_punctuation_filters(module, sequence) == sequence


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
