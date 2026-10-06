from pipeline_harness import load_pipeline_module, punctuation_settings


def run_punctuation_filters(module, speech_sequence):
	return list(
		module.inject_punctuation_pause(speech_sequence, module._test_settings, module.GENERIC_CONTEXT),
	)


def test_zero_punctuation_wait_factor_preserves_existing_text_and_breaks(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0))
	existing_break = BreakCommand(30)

	result = run_punctuation_filters(module, ["Hello.", existing_break, "World"])

	assert result == ["Hello.", existing_break, "World"]


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


def test_removal_uses_pause_points_even_with_zero_wait_or_disabled_pause_control(monkeypatch):
	settings = punctuation_settings(0, remove_characters=True)
	module, _BreakCommand = load_pipeline_module(monkeypatch, settings)
	assert "".join(run_punctuation_filters(module, ["Hello, world."])) == "Hello world."

	settings.scaled_punctuation_wait = lambda: 250
	settings.punctuation_pause_enabled = False
	assert "".join(run_punctuation_filters(module, ["Hello, world."])) == "Hello world."


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
