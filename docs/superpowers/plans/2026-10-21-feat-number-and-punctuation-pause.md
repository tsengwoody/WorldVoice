# Plan: number and punctuation pauses

Spec: `docs/superpowers/specs/2026-10-21-feat-number-and-punctuation-pause-design.md` (commit `9970c40`).
Branch `feat/number-and-punctuation-pause`, worktree `/workspace/WorldVoice-feat-pauses`, base `133cb1e`.
Baseline: `python3 -m pytest -q tests` **1745 passed, 0 skipped** (against `ref/nvda` `7d25bc76e`, through the worktree's git-ignored `ref` symlink); `prek run --all-files` all Passed.

F1 (spec section 11): the user's answer is pending while this plan is written. Every step except step 8 is independent of it. Step 8 is written for both options; the option that is implemented is recorded in "Implementation notes".

> Update (2026-10-21, during step 4): the user chose **F1 option B** (decided by the user). Step 8 implements option B, and step 9 adds property **N7**: when the split changed a string, a text item that fullmatches `_NUMBER_RE` is always next to a break, so leftover text never fullmatches a number unless it was a separate input item. The spec records the decision.

Each step: write the tests first and run them on the unchanged code (red), then change the code (green), then run the full verification of `DEVELOPMENT_WORKFLOW.md` section 7 and commit. pytest runs single-process, under a scratchpad memory guard that kills it when `MemAvailable` < 3 GB.

Full verification before every commit:

```bash
python3 -m pytest -q tests
prek run --all-files
git diff --check master
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
```

The last two print nothing.

Order of the steps: everything that does not depend on F1 first (steps 1 to 7), then the number split (step 8), then the number-split properties (step 9), mutmut (step 10) and the final verification (step 11).

Shorthand in expected outputs: `B(w)` is `("BreakCommand", w)`, `PB(p)` is `("PairNumberBreakCommand", p)`, `PuB(v)` is `("PunctuationBreakCommand", v)`, as printed by the `shape` helper of `tests/test_pipeline_filters.py`.

## Step 1. Plan (commit `docs: plan the number and punctuation pause changes`)

This file, added with `git add -f` (`docs/` is git-ignored). Full suite unchanged: **1745 passed, 0 skipped**.

## Step 2. 1a: `_both_numbers` uses `fullmatch` (commit `fix: pause only between items that are whole numbers`)

### 2a. Red

File: `tests/test_pipeline_filters.py`

Edit: add after `test_number_wait_factor_drops_blanks_then_breaks_between_numbers`.

```python
@pytest.mark.parametrize(
	"sequence,expected",
	[
		(["12", "3"], ["12", ("BreakCommand", 40), "3"]),
		(["-3.5", "4"], ["-3.5", ("BreakCommand", 40), "4"]),
		(["12abc", "3"], ["12abc", "3"]),
		(["1.", "2"], ["1.", "2"]),
		(["3", "12abc"], ["3", "12abc"]),
	],
)
def test_number_wait_breaks_only_between_whole_numbers(env, sequence, expected):
	env.settings.scaled_number_wait = lambda: 40
	assert shape(env.module.number_wait_factor(sequence, env.settings, env.module.GENERIC_CONTEXT)) == expected
```

Expected red: the three `False` cases fail (`["12abc", ("BreakCommand", 40), "3"]` and so on).

### 2b. Green

File: `addon/synthDrivers/WorldVoice/pipeline/__init__.py`

Edit: `_both_numbers`.

```python
def _both_numbers(previous: SpeechCmd, current: SpeechCmd) -> bool:
	# Whole items only: "12" and "-3.5" are numbers, "12abc" and "1." are not.
	return (
		_both_text(previous, current)
		and bool(_NUMBER_RE.fullmatch(previous))
		and bool(_NUMBER_RE.fullmatch(current))
	)
```

Expected green: **1750 passed, 0 skipped** (1745 + 5).

## Step 3. 1e: pair mode always yields `PairNumberBreakCommand` (commit `fix: separate number pairs with a pair break even at pause 0`)

### 3a. Red

File: `tests/test_pipeline_filters.py`

Edit: the number-mode table. Add `"123"` and `"12"`, and change the pair-0 expectation of `"-1234"`.

```python
TEXTS = ["12.5", "-1234", "123", "12", "v1.2", "a. 3", "3.", ".5", "1.2.3", ""]
SHARED = {"v1.2": ["v1.2"], "a. 3": ["a. 3"], "3.": ["3 ."], ".5": [". 5"], "1.2.3": ["1.2 . 3"], "": []}
NUMBER_MODES = {
	("value", 0): {"12.5": ["12.5"], "-1234": ["-1234"], "123": ["123"], "12": ["12"]},
	("number", 0): {"12.5": ["1 2.5"], "-1234": ["-1 2 3 4"], "123": ["1 2 3"], "12": ["1 2"]},
	# Pairs are separate items even at pause 0; up to two digits and decimals have no separator.
	("pair", 0): {
		"12.5": ["12.5"],
		"-1234": ["-12", ("PairNumberBreakCommand", 0), "34"],
		"123": ["12", ("PairNumberBreakCommand", 0), "3"],
		"12": ["12"],
	},
	("pair", 50): {
		"12.5": ["12.5"],
		"-1234": ["-12", ("PairNumberBreakCommand", 50), "34"],
		"123": ["12", ("PairNumberBreakCommand", 50), "3"],
		"12": ["12"],
	},
}
```

Expected red: `test_number_mode[-1234-pair-0]` (`['-12 34']`) and `test_number_mode[123-pair-0]` (`['12 3']`).

### 3b. Green

File: `addon/synthDrivers/WorldVoice/pipeline/__init__.py`

Edit: in `_translate_number`, replace

```python
		pause = pair_pause
		separator: SpeechCmd = PairNumberBreakCommand(pause) if pause > 0 else " "
```

with

```python
		# A break even at pause 0: the pairs must reach the synth as separate items.
		separator = PairNumberBreakCommand(pair_pause)
```

Expected green: **1758 passed, 0 skipped** (1750 + 8 new parameters).

## Step 4. 2-1 to 2-4: the switch controls the whole punctuation stage (commit `fix: let the punctuation switch control pauses and removal together`)

### 4a. Red

File: `tests/test_pipeline_punctuation_pause.py`

Edit: add a `shape` helper after `run_punctuation_filters`:

```python
def shape(sequence):
	return [item if isinstance(item, str) else (type(item).__name__, item.time) for item in sequence]
```

Edit: replace `test_zero_punctuation_wait_factor_preserves_existing_text_and_breaks` with

```python
def test_zero_wait_splits_off_the_mark_but_an_existing_break_suppresses_the_pause(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0))
	existing_break = BreakCommand(30)

	result = run_punctuation_filters(module, ["Hello.", existing_break, "World"])

	assert result == ["Hello", ".", existing_break, "World"]
```

Edit: replace `test_removal_uses_pause_points_even_with_zero_wait_or_disabled_pause_control` with

```python
def test_zero_wait_removal_still_pauses_and_a_disabled_switch_changes_nothing(monkeypatch):
	settings = punctuation_settings(0, remove_characters=True)
	module, _BreakCommand = load_pipeline_module(monkeypatch, settings)
	assert shape(run_punctuation_filters(module, ["Hello, world."])) == [
		"Hello",
		("PunctuationBreakCommand", 0),
		" world.",
	]

	settings.scaled_punctuation_wait = lambda: 250
	settings.punctuation_pause_enabled = False
	assert run_punctuation_filters(module, ["Hello, world."]) == ["Hello, world."]
```

Edit: add at the end

```python
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
		["Hello", ",", ("PunctuationBreakCommand", 0), " world", ".", ("PunctuationBreakCommand", 0), " Bye", "."],
		["Hi", ".", ("PunctuationBreakCommand", 0), "there"],
	),
	True: (
		["Hello", ("PunctuationBreakCommand", 0), " world", ("PunctuationBreakCommand", 0), " Bye", "."],
		["Hi", ("PunctuationBreakCommand", 0), "there"],
	),
}


@pytest.mark.parametrize("remove", [False, True])
def test_zero_wait_pauses_at_every_point_whether_or_not_marks_are_removed(monkeypatch, remove):
	module, _BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0, remove_characters=remove))
	inside, between = ZERO_WAIT[remove]

	assert shape(run_punctuation_filters(module, ["Hello, world. Bye."])) == inside
	assert shape(run_punctuation_filters(module, ["Hi.", "there"])) == between


@pytest.mark.parametrize("characters", ["", "  "])
@pytest.mark.parametrize("remove", [False, True])
def test_an_empty_or_blank_list_changes_nothing(monkeypatch, remove, characters):
	settings = punctuation_settings(0, remove_characters=remove)
	settings.punctuation_pause_characters = characters
	module, _BreakCommand = load_pipeline_module(monkeypatch, settings)

	assert run_punctuation_filters(module, ["Hello, world.", "Hi.", "there"]) == ["Hello, world.", "Hi.", "there"]


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
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0, remove_characters=remove))
	sequence = [BreakCommand(30) if item == "existing" else item for item in sequence]

	assert shape(run_punctuation_filters(module, sequence)) == expected
```

and `import pytest` at the top.

Expected red (9): the two replaced tests; `test_a_disabled_switch_changes_nothing[True-0-.,]` and `[True-250-.,]` (removal ran with the switch off); both `test_zero_wait_pauses_at_every_point...` cases (no break); the first three `test_zero_wait_keeps_the_pause_point_rules` cases (passed through). `test_an_empty_or_blank_list_changes_nothing` and the rule-4 case already pass: they pin 2-4 and 2-7.

### 4b. Green

File: `addon/synthDrivers/WorldVoice/pipeline/__init__.py`

Edit: the start of `inject_punctuation_pause`, after the docstring:

```python
	if not settings.punctuation_pause_enabled:
		yield from speechSequence
		return

	chars = settings.punctuation_pause_characters.strip()
	if not chars:
		# An empty character class would not compile (see _get_punctuation_regex).
		yield from speechSequence
		return

	remove_punctuation = settings.remove_punctuation_characters
	pause_cmd = PunctuationBreakCommand(settings.scaled_punctuation_wait())
	regex = _get_punctuation_regex(chars)
```

Edit: in `emit`, drop every `pause_cmd is not None` test:

```python
		boundary_pause = bool(stripped and stripped[-1] in chars and pause_text_follows)
		...
			if eligible_here:
				yield pause_cmd
		...
		if boundary_pause:
			yield pause_cmd
```

Edit: the docstring. Replace the last bullet ("When removal is enabled, eligible punctuation is omitted even when the pause duration is zero…") and add the switch rules:

```
	* The punctuation pause switch turns the whole stage on or off. With it
	  off, or with no configured characters, the sequence passes through
	  unchanged.
	* With the switch on, every pause point gets a PunctuationBreakCommand,
	  even when its duration is 0 ms; a 0 ms break still separates the text
	  on either side of it.
	* Removal only decides whether the mark at a pause point is dropped. A
	  mark at the end of an item is dropped even when an existing
	  BreakCommand, not this stage, supplies the pause.
```

Expected green: **1780 passed, 0 skipped** (1758 + 12 + 2 + 4 + 4 new).

## Step 5. Punctuation properties and the number properties that do not depend on F1 (commit `test: check the pause stages with Hypothesis`)

File: `tests/test_pipeline_pause_properties.py` (new). One function-scoped `env` fixture loads the pipeline once per test (`load_pipeline_module`), so every property uses `@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])`; the stages are pure functions of their arguments, so examples share nothing.

Strategies:

- `punctuation_sequences`: lists (up to 6) of text over `"ab1 .,;"` (letters, a digit, space and marks, two configured and one not) interleaved with `BreakCommand(30)` objects (fresh per draw).
- `number_texts`: text over `"0123456789+-.aZ共 \t　"`, up to 20 characters.
- `mixed_sequences`: lists of `number_texts` and `BreakCommand` objects.

Properties:

- **P1** `test_property_a_disabled_switch_changes_nothing`: switch off, any list from `["", " ", ".,", ".,;"]`, removal and wait in 0..500: output `==` input (same objects).
- **P2** `test_property_the_wait_changes_only_the_break_time`: switch on, list `".,"`, removal drawn, wait v in 1..500: `shape` of the output at wait 0, with each `PuB(0)` replaced by `PuB(v)`, equals `shape` of the output at wait v.
- **P3** `test_property_removal_changes_only_the_marks`: switch on, list `".,"`, wait 0. With removal off the joined text equals the joined input text. The command skeletons (each non-`str` item, named by type and time) are equal with removal on and off, so the `PuB` count and the existing breaks are the same and in the same order. Between each pair of consecutive commands, the removal-on text is the removal-off text with some configured marks deleted (a subsequence, and every deleted character is in `".,"`).
- **P4** `test_property_a_punctuation_break_never_ends_or_stacks_onto_an_existing_one` (renamed and narrowed during implementation, see the deviation in "Implementation notes"): switch on, list `".,"`, removal and wait drawn. The output does not end with a `PunctuationBreakCommand`; no `PunctuationBreakCommand` is directly followed by an existing `BreakCommand`; with removal off, none is directly preceded by one either. (With removal on, an item that starts with a mark at a pause point, after an existing break, does give `B`, `PuB`: the mark that separated them is removed. This exists on `master` with wait > 0 and is a pause-point rule that 2-7 keeps; it is reported, not changed.)
- **P5** `test_property_an_empty_or_blank_list_changes_nothing`: switch on, list from `["", " ", "\t "]`, removal and wait drawn: output `==` input.
- **N5** `test_property_zero_number_wait_changes_nothing`: `mixed_sequences`, wait in -5..0: output `==` input, item for item.
- **N6** `test_property_pairs_are_separate_items_at_any_pause`: optional sign, n in 3..20 digits, p in 0..500, through `inject_number_mode` in pair mode: the output alternates `str` and `PairNumberBreakCommand` of time p, starting and ending with `str`; it has `ceil(n / 2) - 1` breaks; the strings join back to the input.

Sanity red: P1 fails on step 3 code (`master` removal with the switch off), P2 fails on step 3 code (no break at wait 0), N6 fails on step 2 code (`"12 34"` at p = 0). On step 4 code all pass.

Expected: **1787 passed, 0 skipped** (1780 + 7). Also run `HYPOTHESIS_PROFILE=deep python3 -m pytest -q tests/test_pipeline_pause_properties.py` once.

## Step 6. 2-5: the Speech Pipeline panel enables the dependent controls from the switch (commit `fix: enable the punctuation controls only while pauses are on`)

### 6a. Red

File: `tests/test_settings_panels.py`

Edit: replace `test_pipeline_panel_enables_pause_controls_from_the_stored_switches` and `test_pipeline_panel_switches_follow_the_checkboxes` with

```python
def pause_controls_enabled(panel):
	return (
		panel._remove_punctuation_characters_checkbox.enabled,
		panel._punctuation_wait_factor_slider.enabled,
		panel._punctuation_pause_characters_edit.enabled,
	)


@pytest.mark.parametrize("remove", [False, True])
@pytest.mark.parametrize("pause", [False, True])
def test_pipeline_panel_enables_pause_controls_from_the_stored_switch(monkeypatch, pause, remove):
	env = pipeline_env(monkeypatch, punctuation_pause_enabled=pause, remove_punctuation_characters=remove)
	panel, _sizer = build(env, "SpeechPipelinePanel")
	assert pause_controls_enabled(panel) == (pause, pause, pause)


def test_pipeline_panel_pause_controls_follow_the_switch_only(monkeypatch):
	env = pipeline_env(monkeypatch, punctuation_pause_enabled=False, remove_punctuation_characters=False)
	panel, _sizer = build(env, "SpeechPipelinePanel")
	pause = panel._punctuation_pause_enabled_checkbox
	remove = panel._remove_punctuation_characters_checkbox

	pause.SetValue(True)
	fire(pause, "EVT_CHECKBOX", panel=panel)
	assert pause_controls_enabled(panel) == (True, True, True)

	# Removal decides nothing about the other controls, so nothing listens to it.
	remove.SetValue(True)
	with pytest.raises(LookupError, match="nothing handles"):
		fire(remove, "EVT_CHECKBOX", panel=panel)
	assert pause_controls_enabled(panel) == (True, True, True)

	pause.SetValue(False)
	fire(pause, "EVT_CHECKBOX", panel=panel)
	assert pause_controls_enabled(panel) == (False, False, False)


def test_pipeline_panel_saves_the_disabled_pause_controls(monkeypatch):
	env = pipeline_env(monkeypatch, punctuation_pause_enabled=False)
	panel, _sizer = build(env, "SpeechPipelinePanel")
	panel._remove_punctuation_characters_checkbox.SetValue(True)
	panel._punctuation_wait_factor_slider.SetValue(30)
	panel._punctuation_pause_characters_edit.SetValue("。")

	panel.onSave()

	stored = env.conf["WorldVoice"]["pipeline"]
	assert (stored["remove_punctuation_characters"], stored["punctuation_wait_factor"]) == (True, 30)
	assert stored["punctuation_pause_characters"] == "。"
```

Expected red: `[False-False]` and `[False-True]` of the first test (the remove checkbox is always enabled, and in `[False-True]` the edit too); the second test (firing the remove checkbox reaches the old handler). The save test passes on the old code too: it pins "disabled values are still saved".

### 6b. Green

File: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py`

- Remove the `self.Bind(wx.EVT_CHECKBOX, self.onRemovePunctuationCharactersChange, ...)` call and the `onRemovePunctuationCharactersChange` method.
- `onPunctuationPauseEnabledChange`:

```python
	def onPunctuationPauseEnabledChange(self, event):
		# Disabled controls keep their values, and onSave still stores them.
		enabled = self._punctuation_pause_enabled_checkbox.GetValue()
		self._remove_punctuation_characters_checkbox.Enable(enabled)
		self._punctuation_wait_factor_slider.Enable(enabled)
		self._punctuation_pause_characters_edit.Enable(enabled)
```

Expected green: **1789 passed, 0 skipped** (1787 − 3 old parameters − 1 old test + 4 + 1 + 1).

## Step 7a. 2-5: the NVDA Voice panel disables instead of hiding (commit `fix: disable the voice panel's punctuation controls while pauses are off`)

### Red

File: `tests/test_voice_settings_panel.py`

- `SETTINGS`: add `BooleanDriverSetting("removepunctuationcharacters")` between `punctuationpauseenabled` and `punctuationwaitfactor` (the driver's order, `PIPELINE_SETTINGS`). `Driver` defaults: `"removepunctuationcharacters": False`. `ALL`: add it.
- `test_every_setting_gets_a_control_in_standard_order_and_unsupported_ones_are_hidden`: add `"removepunctuationcharacters"` to both expected lists, after `"punctuationpauseenabled"` (follows from the new setting).
- Replace `test_wait_factor_slider_shows_only_while_pauses_are_enabled` and `test_toggling_pauses_shows_or_hides_the_slider_and_still_saves_the_setting` with

```python
def pause_controls_enabled(panel):
	return (
		panel.removepunctuationcharactersCheckbox.enabled,
		panel.punctuationwaitfactorSlider.enabled,
		panel.punctuationPauseCharactersEdit.enabled,
	)


@pytest.mark.parametrize("enabled", [True, False])
def test_pause_controls_are_enabled_only_while_pauses_are_enabled(monkeypatch, enabled):
	panel = open_panel(monkeypatch, Driver(ALL, punctuationpauseenabled=enabled)).panel
	assert pause_controls_enabled(panel) == (enabled, enabled, enabled)
	# Disabled, not hidden.
	assert panel.settingsSizer.IsShown(panel.sizerDict["punctuationwaitfactor"])


def test_toggling_pauses_enables_or_disables_the_controls_and_still_saves_the_setting(monkeypatch):
	driver = Driver(ALL, punctuationpauseenabled=True)
	panel = open_panel(monkeypatch, driver).panel
	checkbox = panel.punctuationpauseenabledCheckbox

	checkbox.SetValue(False)
	fire(checkbox, "EVT_CHECKBOX")
	assert pause_controls_enabled(panel) == (False, False, False)
	assert panel.settingsSizer.IsShown(panel.sizerDict["punctuationwaitfactor"])
	# WorldVoice's handler skips the event, so NVDA's own handler still writes the setting.
	assert driver.punctuationpauseenabled is False

	checkbox.SetValue(True)
	fire(checkbox, "EVT_CHECKBOX")
	assert pause_controls_enabled(panel) == (True, True, True)
	assert driver.punctuationpauseenabled is True


def test_a_voice_switch_keeps_the_pause_controls_disabled(monkeypatch):
	panel = open_panel(monkeypatch, Driver(ALL, punctuationpauseenabled=False)).panel

	panel.updateDriverSettings(changedSetting="voice")  # shows every supported control again

	assert pause_controls_enabled(panel) == (False, False, False)
	assert panel.settingsSizer.IsShown(panel.sizerDict["punctuationwaitfactor"])
```

- `test_a_synth_without_pause_settings_gets_the_characters_edit_at_the_end`: add `assert panel.punctuationPauseCharactersEdit.enabled is True`.

Expected red: `test_pause_controls_are_enabled_only_while_pauses_are_enabled[True]` passes, `[False]` fails (controls enabled, slider hidden); the toggle test and the voice-switch test fail. The order test and the non-WorldVoice test pass on the old code.

### Green

File: `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py`

```python
	def _bindPunctuationPauseEnabledToggle(self):
		"""
		Hook the "Enable punctuation pause control" checkbox so the controls that
		depend on it are enabled only while it is checked, starting with its state
		when the dialog opens.
		"""
		checkbox = getattr(self, "punctuationpauseenabledCheckbox", None)
		if checkbox is None:
			return
		checkbox.Bind(wx.EVT_CHECKBOX, self._onPunctuationPauseEnabledToggle)
		self._applyPunctuationPauseControlsState()

	def _onPunctuationPauseEnabledToggle(self, evt):
		# NVDA's own checkbox handler writes the setting; this one only updates the dependent controls.
		evt.Skip()
		self._applyPunctuationPauseControlsState()

	def _applyPunctuationPauseControlsState(self):
		# Disable rather than hide: NVDA's updateDriverSettings shows every supported
		# control again after a voice change, but never enables or disables one.
		enabled = self.punctuationpauseenabledCheckbox.GetValue()
		for name in (
			"removepunctuationcharactersCheckbox",
			"punctuationwaitfactorSlider",
			"punctuationPauseCharactersEdit",
		):
			control = getattr(self, name, None)
			if control is not None:
				control.Enable(enabled)
```

`_applyPunctuationWaitFactorVisibility` is removed.

Expected green: **1790 passed, 0 skipped** (1789 + 1).

## Step 7b. 2-6: empty default character list (commit `feat: start with no punctuation pause characters`)

### Red

File: `tests/test_pipeline_settings_service.py`

- `OLD_DEFAULTS["punctuation_pause_characters"] = ""`.
- `assert module.PIPELINE_CONFSPEC["punctuation_pause_characters"] == 'string(default="")'`.

Expected red: `test_table_drives_fields_defaults_keys_and_confspec` and `test_get_reads_defaults_and_current_profile`.

### Green

File: `addon/synthDrivers/WorldVoice/pipeline/settings.py`

```python
	PipelineSettingSpec("punctuation_pause_characters", str, "", normalize=_strip),
```

Expected green: **1790 passed, 0 skipped**.

## Step 8. 1b: split whitespace-separated numbers inside a string (commit `feat: pause between numbers separated by spaces within one string`)

### 8a. Red

File: `tests/test_pipeline_filters.py`

Edit: add after `test_number_wait_breaks_only_between_whole_numbers`. `F1` is the chosen option's expectation table: the three F1 inputs differ between the options, every other row is the same.

```python
B40 = ("BreakCommand", 40)
SPLITS = [
	("1 2", ["1", B40, "2"]),
	("共 12 34 個", ["共 ", "12", B40, "34", " 個"]),
	("5 -3", ["5", B40, "-3"]),
	("5 - 3", ["5 - 3"]),
	("1.2.3 4", ["1.2.", "3", B40, "4"]),
	("12 apples", ["12 apples"]),
	("abc1 2def", ["abc", "1", B40, "2", "def"]),
	("2026 10 21", ["2026", B40, "10", B40, "21"]),
	("12　34", ["12", B40, "34"]),
	("1\t2", ["1", B40, "2"]),
	("1 2", ["1", B40, "2"]),
	("1-2", ["1-2"]),
	("12abc 3", ["12abc 3"]),
	*F1,
]


@pytest.mark.parametrize("text,expected", SPLITS)
def test_number_wait_splits_numbers_separated_only_by_whitespace(env, text, expected):
	env.settings.scaled_number_wait = lambda: 40
	assert shape(env.module.number_wait_factor([text], env.settings, env.module.GENERIC_CONTEXT)) == expected


def test_number_wait_splits_across_items_and_keeps_commands(env):
	env.settings.scaled_number_wait = lambda: 40
	marker = env.module.BreakCommand(5)
	result = list(
		env.module.number_wait_factor(["5", "1 2", marker, "3 4"], env.settings, env.module.GENERIC_CONTEXT),
	)
	assert shape(result) == ["5", B40, "1", B40, "2", ("BreakCommand", 5), "3", B40, "4"]
	assert result[1] is result[3] is result[7]
	assert result[5] is marker


def test_digit_mode_then_number_wait_pauses_between_digits(env):
	env.settings.number_mode = "number"
	env.settings.scaled_number_wait = lambda: 40
	digits = env.module.inject_number_mode(["12"], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(env.module.number_wait_factor(digits, env.settings, env.module.GENERIC_CONTEXT)) == [
		"1",
		B40,
		"2",
	]


def test_translated_digits_are_not_split(env):
	env.settings.number_mode = "number"
	env.settings.scaled_number_wait = lambda: 40
	symbols = SimpleNamespace(symbols={"1": SimpleNamespace(language="zh", replacement="一")})
	context = env.module.SpeechContext(supports_roles=True, language="zh", number_language="zh", speech_symbols=symbols)
	digits = env.module.inject_number_mode(["11"], env.settings, context)
	assert list(env.module.number_wait_factor(digits, env.settings, context)) == ["一 一"]


def test_pair_mode_then_number_wait_breaks_between_numbers_only(env):
	env.settings.number_mode = "pair"
	env.settings.scaled_number_wait = lambda: 40
	pairs = env.module.inject_number_mode(["1234 5678"], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(env.module.number_wait_factor(pairs, env.settings, env.module.GENERIC_CONTEXT)) == [
		"12",
		("PairNumberBreakCommand", 0),
		"34",
		B40,
		"56",
		("PairNumberBreakCommand", 0),
		"78",
	]
```

`F1` for option A (the rule as decided):

```python
# F1 option A: a sign-attached number next to a split run is split out too.
F1 = [
	("02 2345-6789", ["02", B40, "2345", B40, "-6789"]),
	("3-1 2", ["3", B40, "-1", B40, "2"]),
	("1 2 3-4", ["1", B40, "2", B40, "3", B40, "-4"]),
]
```

`F1` for option B (recommended):

```python
# F1 option B: a number glued to another number with no gap is never split out.
F1 = [
	("02 2345-6789", ["02 2345-6789"]),
	("3-1 2", ["3-1 2"]),
	("1 2 3-4", ["1", B40, "2", " 3-4"]),
]
```

Expected red: option A, 12 of the 16 `SPLITS` rows (all but `"5 - 3"`, `"12 apples"`, `"1-2"`, `"12abc 3"`); option B, 10 rows (the same, also not the first two F1 rows). Plus the across-items, digit-mode and pair-mode tests. `test_translated_digits_are_not_split` passes on the old code (it pins F5).

### 8b. Green

File: `addon/synthDrivers/WorldVoice/pipeline/__init__.py`

Edit: add after `_remove_space`. Option B:

```python
def _split_spaced_numbers(text: str) -> Iterator[str]:
	"""
	Yield *text* with every number that only whitespace separates from a
	neighbouring number as an item of its own, without that whitespace.

	Everything else is kept verbatim, spaces included, and no empty piece is
	yielded. A number glued to another number with no gap, as in
	"2345-6789", is never split out, so a pause can only replace whitespace.
	"""
	matches = list(_NUMBER_RE.finditer(text))
	gaps = [text[left.end() : right.start()] for left, right in zip(matches, matches[1:])]
	glued = {index + side for index, gap in enumerate(gaps) if not gap for side in (0, 1)}
	# joined[i] is True when matches i - 1 and i are split apart; the ends are never joined.
	joined = [
		False,
		*(gap.isspace() and index not in glued and index + 1 not in glued for index, gap in enumerate(gaps)),
		False,
	]
	position = 0
	for index, match in enumerate(matches):
		if not (joined[index] or joined[index + 1]):
			continue
		if not joined[index] and match.start() > position:
			yield text[position : match.start()]
		yield match.group()
		position = match.end()
	if position < len(text):
		yield text[position:]


def _split_numbers(speechSequence: Iterable[SpeechCmd]) -> Iterator[SpeechCmd]:
	for item in speechSequence:
		if isinstance(item, str):
			yield from _split_spaced_numbers(item)
		else:
			yield item
```

Option A is the same without `glued` (`gap.isspace()` alone decides `joined`), and without the docstring's last sentence.

Edit: `number_wait_factor`:

```python
	yield from _insert_between(
		_split_numbers(_remove_space(speechSequence)),
		_both_numbers,
		BreakCommand(wait_factor),
	)
```

and a docstring:

```python
	"""
	Pause between numbers: between two items that are each a whole number, and
	between numbers that only whitespace separates inside one item, which become
	items of their own. Blank text items are dropped and the others stripped.
	"""
```

Expected green: **1810 passed, 0 skipped** (1790 + 16 + 4).

## Step 9. Number-split properties (commit `test: check the number split with Hypothesis`)

File: `tests/test_pipeline_pause_properties.py`. Input: one `number_texts` string through `number_wait_factor` at wait 40.

- **N1** `test_property_the_split_keeps_the_text_and_replaces_only_whitespace`: walk the output against `text.strip()`: each `str` is the next verbatim slice; each `BreakCommand` consumes a run of whitespace; the walk ends at the end. Option B: the run is non-empty. Option A: the run may be empty only when both neighbours fullmatch `_NUMBER_RE`.
- **N2** `test_property_no_text_item_keeps_two_numbers_apart_by_whitespace`: no output `str` contains two consecutive `_NUMBER_RE` matches with a non-empty all-whitespace gap between them. Option B: unless one of the two is glued (empty gap) to its other neighbouring match in that item, as in `"1 2-3 4"`, which stays unchanged.
- **N3** `test_property_no_digits_are_glued_together`: no two consecutive `str` items have an ASCII digit at the end of the first and at the start of the second.
- **N7** `test_property_leftover_text_is_never_a_number`: when the output differs from `[text.strip()]`, every output `str` that fullmatches `_NUMBER_RE` has a `BreakCommand` next to it.
- **N4** `test_property_breaks_sit_exactly_between_whole_numbers`: every `BreakCommand` has a `str` on each side and both fullmatch; two consecutive `str` items never both fullmatch; all breaks are one instance.

Sanity red: N1 to N4 checked against the step 7b code: N2 fails (`"1 2"` is not split). Expected: **1815 passed, 0 skipped** (N1 to N4 and N7). Also run the deep profile once.

## Step 10. mutmut (commit `build: run mutmut on the speech pipeline`, then `test: ...` for killed survivors)

File: `pyproject.toml`

- Add `"addon/synthDrivers/WorldVoice/pipeline/__init__.py"` to `[tool.mutmut] source_paths`.

Run (Linux, worktree), guarded by a scratchpad script that kills the run when `MemAvailable` < 3 GB:

```bash
mutmut run --max-children 3 \
  "addon.synthDrivers.WorldVoice.pipeline.x__both_numbers*" \
  "addon.synthDrivers.WorldVoice.pipeline.x_number_wait_factor*" \
  "addon.synthDrivers.WorldVoice.pipeline.x__split_spaced_numbers*" \
  "addon.synthDrivers.WorldVoice.pipeline.x__split_numbers*" \
  "addon.synthDrivers.WorldVoice.pipeline.x__translate_number*" \
  "addon.synthDrivers.WorldVoice.pipeline.x_inject_punctuation_pause*"
```

The exact names are confirmed with `mutmut results` first. Each survivor is checked with `mutmut show` and confirmed by running the suite with `MUTANT_UNDER_TEST=<name>` in `mutants/`. Survivors and reasons go to "Implementation notes"; reasonable ones are killed with a test. `mutants/` is git-ignored and is removed afterwards.

## Step 11. Final verification

Full verification as above; the counts are recorded below.

## Implementation notes

F1: the user chose option B (2026-10-21), during step 4; the spec records it (commit `322a66e`). Step 8 implements option B.

Red/green as planned:

- Step 2: 3 red (the three non-number cases). Green **1750 passed, 0 skipped**.
- Step 3: 2 red (`[-1234-pair-0]`, `[123-pair-0]`). Green **1758**.
- Step 4: 9 red, as listed. Green **1780**.
- Step 5: sanity red as planned: on `72ce60e` P1 and P2 fail; on `e6fd0fe` P1, P2 and N6 fail. Green **1787**.
- Step 6: 3 red. Green **1789**.
- Step 7a: 3 red. Green **1790**.
- Step 7b: 2 red. Green **1790**.
- Step 8 (option B): 13 red (10 `SPLITS` rows, across items, digit mode, pair mode). Green **1810**.
- Step 9: on `e78e6ba` (no split) N2 fails; on an option-A variant of the split (scratch copy), N1 and N7 fail. Green **1815 passed, 0 skipped**. `HYPOTHESIS_PROFILE=deep` on N1-N4, N7 and P4 (20000 examples each): 6 passed in 150 s. (Step 5's deep run of all seven properties found the P4 case described under Deviations.)
- Step 10 (mutmut kills): 3 new test cases. **1818 passed, 0 skipped**.

### mutmut (step 10)

Linux, mutmut 3.8.0, on `c4f2410`: `mutmut run --max-children 3` with the six globs of step 10, guarded by a scratchpad script that kills the run if MemAvailable < 3 GB. The guard never fired.

- First run: **205 mutants: 192 killed, 13 survived** (`_both_numbers` 10, `_split_spaced_numbers` 34, `_split_numbers` 1, `number_wait_factor` 12, `_translate_number` 48, `inject_punctuation_pause` 100). All mutants of the new split helpers and of `_both_numbers` are killed.
- Three survivors were real gaps and are killed by new tests: `number_wait_factor` 3 (`wait_factor <= 1`; `test_the_shortest_number_wait_still_breaks`), `inject_punctuation_pause` 19 (`item.rstrip()` -> `item.lstrip()`; rule-4 case `["Hi. ", "there"]`) and `inject_punctuation_pause` 52 (`and` -> `or` in the internal-point test; rule-3 case `["Bye. ."]`). Each was confirmed killed by running the suite in `mutants/` with the new tests and `MUTANT_UNDER_TEST=<name>` (hygiene guards excluded, as in `[tool.mutmut]`).
- The other ten pass the whole suite (1809 tests) with the mutant applied, so they really survive. Final: **205 mutants: 195 killed, 10 survived**.

The numbers are mutmut's names from this run (`mutate_only_covered_lines = true`); the "Change" column identifies each mutant.

| Mutant | Change | Why it survives |
| --- | --- | --- |
| `_translate_number` 1 | default `pair_pause = 1` | Equivalent: the only caller, `iter_number_speech_segments_mode`, always passes `pair_pause`. (Existed before.) |
| `_translate_number` 16 | `digits[0] in "XX+-XX"` | Equivalent: `digits[0]` is the first character of a `_NUMBER_RE` match, a sign or a digit, never `X`. (Existed before.) |
| `_translate_number` 42 | `previous_was_digit = None` | Equivalent: only read as a truth value. (Existed before.) |
| `inject_punctuation_pause` 36, 43, 44 | `default=None` / `+1` / `-2` for `last_punctuation_index` | Equivalent: the default is used only when the item has no punctuation part, and the index is compared only inside the punctuation branch. (Existed before.) |
| `inject_punctuation_pause` 64, 65 | `kind == "XXtextXX"` / `"TEXT"` in `emit`'s loop | Equivalent: a text part then takes the punctuation branch, where its index is never a pause point nor the last punctuation index, so it is yielded unchanged with no break. The `text` branch only skips that work. (Existed before.) |
| `inject_punctuation_pause` 94, 95 | `emit(previous, None, False)` / `emit(previous, False, None)` | Equivalent: both flags are only read as truth values. (Existed before.) |

Deviations:

- Step 8: `_split_spaced_numbers` uses `itertools.pairwise(matches)` instead of `zip(matches, matches[1:])`, because ruff (RUF007) asks for it. NVDA 2024.1, the minimum version, runs Python 3.11, which has it.
- Step 9, N7: checking only that a whole-number text item has a break next to it does not tell option A from option B (under A the leftover `"-6789"` also gets a break). N7 instead requires a break next to it that replaced whitespace in the input, using the same walk as N1. With that, the option-A variant fails N1 and N7.
- Step 4: `test_zero_wait_removal_still_pauses_and_a_disabled_switch_changes_nothing` expects `"Hello"`, `PuB(0)`, `" world"`, `"."`, not `" world."` as spec section 10 says. An item with a pause point is split into text and mark pieces (spec section 4.2, last bullet), so the final mark is its own piece; spec table 5.2 already shows this (`" Bye"`, `"."`). The code follows the unchanged pause-point rules.
- Step 5, P4: with removal on, a `PunctuationBreakCommand` can sit next to an existing `BreakCommand`. Hypothesis found `[".", ".", existing, "1"]` (the second item is only a mark at a pause point and disappears), and `["a", existing, ". b"]` gives `"a"`, existing, `PuB`, `" b"`. Both happen on `master` with wait > 0 too. They follow from the pause-point rules that spec item 2-7 keeps, so P4 checks adjacency only with removal off and checks "never last" always. Reported as a finding; not changed.
