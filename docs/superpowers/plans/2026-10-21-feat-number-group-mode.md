# Number Group Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Replace the fixed two-digit "pair" number mode by a "group" mode with a user-chosen group size (1–10, default 3), separate digits in digit mode with a `NumberBreakCommand`, and normalise unknown stored number modes to "value".

**Architecture:** The settings table (`pipeline/settings.py`) gains per-spec integer bounds with a clamp, the renamed `group_wait_factor`, the new non-driver key `group_size` and a `number_mode` normaliser. The number stages (`pipeline/__init__.py`) cut groups of `group_size` digits and emit two new `BreakCommand` subclasses. Both settings panels get a "Group size:" spin control that is enabled, with the group wait slider, only in group mode.

**Tech Stack:** Python 3.13 (NVDA add-on), wxPython via NVDA's GUI helpers, pytest 9 + Hypothesis against NVDA stubs, mutmut 3.8.0, ruff 0.16.3 through prek.

**Spec:** `docs/superpowers/specs/2026-10-21-feat-number-group-mode-design.md` (commit `a7c9f9c`). Open questions Q1–Q11 stay at their adopted defaults (F1 option A, Q11 keep U1 for every synth).

## Global Constraints

- Mode values are exactly `"value"`, `"number"`, `"group"`; `NUMBER_MODES = ("value", "number", "group")` in `pipeline/settings.py`. Any other stored or written mode becomes `"value"`. No migration, no compatibility layer, no `"pair"` anywhere in add-on code.
- `group_size`: int, default 3, bounds 1–10, confspec `integer(default=3,min=1,max=10)`, no driver id, not in the ring, appended after `punctuation_pause_characters`.
- `group_wait_factor`: int, default 0, bounds 0–100, confspec `integer(default=0,min=0,max=100)`, driver id `groupwaitfactor`, label `"Group wait factor"`, at the old `pair_wait_factor` position. `GROUP_WAIT_UNIT_MS = 5`; `scaled_group_wait() = min(group_wait_factor * 5, 500)`.
- Every existing int key keeps its exact confspec string `integer(default=<d>,min=0,max=100)`.
- `GroupNumberBreakCommand` docstring "Pause between digit groups in group number mode."; `NumberBreakCommand` docstring "Pause between numbers, and between the digits of a number in digit mode." No `__repr__` on either.
- No change to `compat/`, `runtime/`, the stage order (`STAGES`), the split rules (`_split_spaced_numbers`, `_both_numbers`), the punctuation stage, the settings-ring list or order, `buildVars.py`, or earlier specs and plans.
- Strings and zh_TW: `"group"` → 群組, `"Group size:"` → 每組位數：, `"group wait factor:"` → 群組停頓參數：, `"Group wait factor"` → 群組停頓參數. Do not commit `.pot` or `.mo`.
- DEVELOPMENT_WORKFLOW.md §8:
  - Never modify `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/`; WorldVoice behaviour lives in wrappers and core.
  - Engine drivers stay independently installable: no driver imports another driver's package.
  - Never add Neural back.
  - ruff is pinned `==0.16.3` (`required-version`); prek hooks run on commit; never `--no-verify`.
  - Stage explicit paths only; check `git diff --cached --stat` before each commit; messages in English `<type>: <summary>` with a body explaining why; no `Co-Authored-By`; no `git stash`; no push; never stage `ref`; `git add -f` for files under `docs/`.
  - Delete only own scratchpad files. mutmut at most 3 workers.
- **Full suite** in every verification step means `python3 -m pytest -q tests`, single process, under a scratchpad guard that kills pytest when MemAvailable drops below 3 GB. Baseline on `a7c9f9c`: **1830 passed, 0 skipped**. Skips may only come from missing optional components (none expected in this worktree).
- **Batch end** (§7): full suite, `prek run --all-files` all Passed, `git diff --check master` clean, and both protected-path commands print nothing:
  `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py` and `git ls-files addon/synthDrivers/WorldVoice/driver/Neural`.

## Review Focus

1. **A mode choice with no selection (wx `NOT_FOUND`, -1) in the Speech Pipeline panel.** `number_mode_value[-1]` is `"group"` in Python, so a naive lookup enables the group controls. Expected: no selection counts as not group. Test in Task 7 (`test_pipeline_panel_counts_no_selection_as_not_group`).
2. **The Voice panel's `nummodList` left with no selection** after a voice change whose list lacks the stored id (`_updateValueForControl` leaves -1). `self._nummods[-1]` is the group entry. Expected: both group controls disabled. Test in Task 9 (`test_a_mode_missing_from_the_list_counts_as_not_group`).
3. **Phone and account numbers with leading zeros** (`"0912345678"`, `"007"`, `"+0012"`) in group mode. Expected: every digit kept as written, no `int()` round trip, sign on the first group. Test in Task 3 (`test_group_mode_keeps_leading_zeros_and_every_digit`).
4. **Digits glued to letters or punctuation, and multi-character digit words** in digit mode (`"A12B"`, `"3.14"`, a table mapping `1` → `"one "`). Expected: a break only between two adjacent digits, letters and words kept verbatim. Tests in Task 6 (`test_digit_mode_breaks_only_between_adjacent_digits`, `test_digit_words_are_kept_verbatim_one_per_item`).
5. **A stored `group_size` outside 1–10 or as text, reaching a panel through a profile that does not validate** (stub configs, a profile section NVDA never validated). Expected: the spin control shows a value within 1–10 (`0` → 1, `12` → 10, `"4"` → 4). Test in Task 7 (`test_pipeline_panel_shows_an_out_of_range_stored_size_within_the_spin_range`).

## Batches

12 tasks, 3 batches of 4 (§3.2). After batches 1 and 2 the implementer stops and reports; the orchestrator dispatches an Opus batch review; Critical/Important findings are fixed with TDD before the next batch. Batch 3 is covered by the final Fable review.

| Batch | Tasks | Boundary |
| --- | --- | --- |
| 1 | 1–4 | settings table, group wait rename, group mode value, mode normalisation |
| 2 | 5–8 | the two break commands, Speech Pipeline panel, Voice panel spin control |
| 3 | 9–12 | Voice panel enable rule, strings and docs, X1 property, mutmut and final verification |

## File Map

| File | Responsibility | Tasks |
| --- | --- | --- |
| `addon/synthDrivers/WorldVoice/pipeline/settings.py` | spec bounds and clamp, keys, `NUMBER_MODES`, normaliser, `scaled_group_wait` | 1, 2, 4 |
| `addon/synthDrivers/WorldVoice/pipeline/__init__.py` | `GroupNumberBreakCommand`, `NumberBreakCommand`, `_translate_number`, `inject_number_mode`, `number_wait_factor` | 2, 3, 5, 6 |
| `addon/synthDrivers/WorldVoice/__init__.py` | `_get_availableNummods` | 3, 10 |
| `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` | Speech Pipeline panel | 2, 3, 7, 10 |
| `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py` | Voice panel spin control and enable rule | 8, 9, 10 |
| `tests/pipeline_harness.py`, `tests/ui_harness.py` | stage settings stub; `SpinCtrl`, `nvdaControls`, Choice writer | 2, 7, 9 |
| `addon/locale/zh_TW/LC_MESSAGES/nvda.po`, `readme.md`, `addon/doc/zh_TW/readme.md` | strings and docs | 10 |
| `pyproject.toml` | mutmut `source_paths` | 11 |

---

## Batch 1 (Tasks 1–4)

### Task 1: Spec bounds, clamp and confspec

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py:37-62`
- Test: `tests/test_pipeline_settings_service.py`, `tests/test_pipeline_pause_properties.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `PipelineSettingSpec(..., min_value: int = 0, max_value: int = 100)` (new fields after `normalize`); `convert` clamps every `kind is int` result to `[min_value, max_value]` after `normalize` / `kind(value)`; `confspec` for ints is `f"integer(default={default},min={min_value},max={max_value})"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_pipeline_settings_service.py`:

```python
def test_int_confspec_carries_the_spec_bounds(monkeypatch):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	bounded = module.PipelineSettingSpec("x", int, 3, min_value=1, max_value=10)
	assert bounded.confspec == "integer(default=3,min=1,max=10)"
	for spec in module.PIPELINE_SETTINGS:
		if spec.kind is int:
			assert spec.confspec == f"integer(default={spec.default},min=0,max=100)"

@pytest.mark.parametrize(("key", "raw", "expected"), [
	("number_wait_factor", 150, 100), ("number_wait_factor", -3, 0),
	("global_wait_factor", "57", 50), ("global_wait_factor", 150, 100), ("global_wait_factor", -5, 0),
])
def test_convert_clamps_ints_to_their_bounds(monkeypatch, key, raw, expected):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert module.PIPELINE_SETTING_BY_KEY[key].convert(raw) == expected
```

and in `tests/test_pipeline_pause_properties.py` (S1, first half; a `settings_module` fixture built with `load_settings_module`):

```python
def test_property_int_convert_is_bounded_and_idempotent(settings_module, data):
	# spec drawn from the int specs of PIPELINE_SETTINGS, value from st.integers(-1000, 1000)
	result = spec.convert(value)
	assert spec.min_value <= result <= spec.max_value
	assert spec.convert(result) == result
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q tests/test_pipeline_settings_service.py tests/test_pipeline_pause_properties.py -k "bounds or clamps or bounded"`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'min_value'`; clamp rows 150/-3/-5 return the raw value; the property fails on a value above 100.

- [ ] **Step 3: Implement the two fields, the clamp in `convert` and the bounded `confspec`** in `pipeline/settings.py`. `_floor_to_ten` still runs first for `global_wait_factor`. Bool and str specs are not clamped.

- [ ] **Step 4: Run the tests to verify they pass, then the full suite**

Run: the Step 2 command, then the full suite.
Expected: 7 passed; full suite **1837 passed, 0 skipped**.

- [ ] **Step 5: Commit** `feat: bound and clamp pipeline integer settings` (`settings.py`, both test files).

### Task 2: Rename the pair wait to the group wait and add the group size

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (constant `:23-26`, spec `:103-110`, table end `:161-162`, dataclass `:166-239`)
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py:390-392` (call `scaled_group_wait` only)
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:180-188, 277` (attribute and field rename only; the label stays `"pair wait factor:"` until Task 7)
- Modify: `tests/pipeline_harness.py:110-122`
- Test: `tests/test_pipeline_settings_service.py`, `tests/test_worldvoice_pipeline_settings.py`, `tests/test_settings_panels.py`, `tests/test_pipeline_panels.py`, `tests/test_pipeline_filters.py`, `tests/test_pipeline_pause_properties.py`

**Interfaces:**
- Consumes: Task 1 `min_value` / `max_value`.
- Produces: `GROUP_WAIT_UNIT_MS = 5`; spec `PipelineSettingSpec("group_wait_factor", int, 0, driver_id="groupwaitfactor", label=_("Group wait factor"))` (keep its existing `# Translators: Label for a setting in voice settings dialog.`); spec `PipelineSettingSpec("group_size", int, 3, min_value=1, max_value=10)` after `punctuation_pause_characters`; `PipelineSettings.group_wait_factor: int`, `PipelineSettings.group_size: int`; `PipelineSettings.scaled_group_wait() -> int`; `effective` zeroes `group_wait_factor` and keeps `group_size`; panel attribute `SpeechPipelinePanel._group_wait_factor_slider`; `pipeline_harness.punctuation_settings(...)` has `scaled_group_wait=lambda: 0` and `group_size=3` (no `scaled_pair_wait`).

- [ ] **Step 1: Write the failing tests.** New, in `tests/test_pipeline_settings_service.py`:

```python
def test_group_settings_replace_the_pair_wait_and_add_the_size(monkeypatch):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert module.PIPELINE_CONFSPEC["group_size"] == "integer(default=3,min=1,max=10)"
	assert module.PIPELINE_CONFSPEC["group_wait_factor"] == "integer(default=0,min=0,max=100)"
	assert "pair_wait_factor" not in module.PIPELINE_CONFSPEC
	assert module.PIPELINE_SETTING_BY_KEY["group_size"].driver_id is None
	assert module.PIPELINE_SETTING_BY_KEY["group_wait_factor"].label == "Group wait factor"
	assert module.PIPELINE_CONFIG_KEYS[-1] == "group_size"
```

Add rows to `test_convert_clamps_ints_to_their_bounds`: `("group_size", 0, 1)`, `("group_size", -5, 1)`, `("group_size", 11, 10)`, `("group_size", 99, 10)`, `("group_size", "7", 7)`.
Update existing expectations: `OLD_DEFAULTS` gets `"group_wait_factor": 0, "group_size": 3` instead of `"pair_wait_factor"`; the driver-id list has `"groupwaitfactor"` where `"pairwaitfactor"` was; `test_effective_matches_the_old_synth_scoping` uses `group_wait_factor` and also stores `group_size` 5 and asserts `scoped.group_size == 5`; the two `scaled_pair_wait` rows become `({"group_wait_factor": 20}, "scaled_group_wait", 100)` and `({"group_wait_factor": 200}, "scaled_group_wait", 500)`; `EXPECTED_IDS` in `tests/test_worldvoice_pipeline_settings.py` has `"groupwaitfactor"`, and that test asserts `not hasattr(synth_class, "groupsize")`; `tests/test_settings_panels.py` stores `group_wait_factor=12`, reads `_group_wait_factor_slider` (value and the `for name in (...)` list), and `stored["group_wait_factor"] == 40`; `tests/test_pipeline_panels.py` uses `_group_wait_factor_slider` and expects `"group_wait_factor": 7`; `tests/test_pipeline_filters.py::test_number_mode` and N6 in `tests/test_pipeline_pause_properties.py` set `scaled_group_wait` instead of `scaled_pair_wait`; `pipeline_harness.punctuation_settings` as in Produces.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q tests/test_pipeline_settings_service.py tests/test_worldvoice_pipeline_settings.py tests/test_settings_panels.py tests/test_pipeline_panels.py tests/test_pipeline_filters.py tests/test_pipeline_pause_properties.py`
Expected: FAIL — missing `group_size` / `group_wait_factor` confspec keys, `PipelineSettings` rejects `group_wait_factor`, `pairwaitfactor` id, `_group_wait_factor_slider` missing, `scaled_pair_wait` missing on the harness settings.

- [ ] **Step 3: Implement the rename and the new key** in `settings.py` (constant, spec, dataclass field, helper, `effective`), the one call in `inject_number_mode` (`scaled_group_wait()`; the local name may stay until Task 3), and the panel attribute and `group_wait_factor=` in `onSave`.

- [ ] **Step 4: Run to verify they pass, then the full suite**

Run: the Step 2 command, then the full suite.
Expected: PASS; full suite **1843 passed, 0 skipped** (+1 new test, +5 clamp rows).

- [ ] **Step 5: Commit** `refactor: rename the pair wait to the group wait and add the group size`.

### Task 3: Group mode replaces pair mode

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py:41-42, 350-418`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py:475-480`
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:142-147`
- Test: `tests/test_pipeline_filters.py`, `tests/test_pipeline_passthrough.py`, `tests/test_pipeline_pause_properties.py`, `tests/test_lint_rewrites.py`, `tests/test_worldvoice_pipeline_settings.py`, `tests/test_settings_panels.py`, `tests/test_pipeline_panels.py`

**Interfaces:**
- Consumes: Task 2 `settings.group_size`, `settings.scaled_group_wait()`.
- Produces: `class GroupNumberBreakCommand(BreakCommand)` (replaces `PairNumberBreakCommand`); `_translate_number(raw: str, mode: str, table: dict[int, str], group_size: int, group_pause: int) -> Iterator[SpeechCmd]` (no defaults); `iter_number_speech_segments_mode(item, mode, translate_table, group_size, group_pause, number_re=_NUMBER_RE)`; `inject_number_mode` reads `settings.group_size` and `settings.scaled_group_wait()` once per call; `availableNummods` ids `value`, `number`, `group` with `_("group")`; panel `number_mode_value = ["value", "number", "group"]` with label `_("group")`. Translator comments for `"group"` come in Task 10.

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_pipeline_filters.py`: `NUMBER_MODES` keys become `(mode, size, pause)`; the test sets `env.settings.group_size = size` and `scaled_group_wait = lambda: pause`. Rows: `("value", 3, 0)`, `("number", 3, 0)` (old expectations), and group rows, with `GB(p) = ("GroupNumberBreakCommand", p)`:

    | key | `"12.5"` | `"-1234"` | `"123"` | `"12"` |
    | --- | --- | --- | --- | --- |
    | `("group", 1, 0)` | `["12.5"]` | `["-1", GB0, "2", GB0, "3", GB0, "4"]` | `["1", GB0, "2", GB0, "3"]` | `["1", GB0, "2"]` |
    | `("group", 2, 0)` / `("group", 2, 50)` | `["12.5"]` | `["-12", GBp, "34"]` | `["12", GBp, "3"]` | `["12"]` |
    | `("group", 3, 0)` | `["12.5"]` | `["-123", GB0, "4"]` | `["123"]` | `["12"]` |
    | `("group", 10, 0)` | `["12.5"]` | `["-1234"]` | `["123"]` | `["12"]` |

    `SHARED` rows hold for every group size.
  - `test_group_mode_keeps_leading_zeros_and_every_digit` (Review Focus 3): size 3, `"0912345678"` → `["091", GB, "234", GB, "567", GB, "8"]`; size 2, `"007"` → `["00", GB, "7"]`; size 3, `"+0012"` → `["+001", GB, "2"]`.
  - `test_group_separator_is_one_instance_per_number` parametrized pause `0`, `50`: size 2, `"123456"` → the breaks are one object (`is`) with `.time == pause`.
  - `test_pair_mode_then_number_wait_breaks_between_numbers_only` → renamed `test_group_mode_then_number_wait_breaks_between_numbers_only`, `number_mode = "group"`, `group_size = 2`, `("GroupNumberBreakCommand", 0)` (the number break stays `("BreakCommand", 40)` until Task 5).
  - `tests/test_pipeline_passthrough.py`: rename to `test_a_group_number_break_counts_as_an_existing_pause_for_punctuation`, using `module.GroupNumberBreakCommand(50)`.
  - `tests/test_pipeline_pause_properties.py`: N6 replaced by **G1** `test_property_groups_are_separate_items_of_the_chosen_size` (sign from `["", "+", "-"]`, digits 1–30, size `st.integers(1, 10)`, pause `st.integers(0, 500)`): output alternates `str` / `GroupNumberBreakCommand(pause)`; strings join to the input; with the sign removed from the first string every group has exactly `size` digits except the last (1..size); `len(breaks) == ceil(len(digits) / size) - 1`; `len(digits) <= size` gives `[sign + digits]`. New **G2** `test_property_decimals_are_unchanged_in_group_mode`: any `[+-]?\d+\.\d+` (from `st.from_regex(r"[+-]?[0-9]{1,8}\.[0-9]{1,8}", fullmatch=True)`), any size 1–10 → `[text]`.
  - `tests/test_lint_rewrites.py`: last row `("group", "group", "group")`.
  - `tests/test_worldvoice_pipeline_settings.py::test_descriptors_read_and_write_through_the_service`: `synth.nummod = "group"` stores and reads `"group"`.
  - `tests/test_settings_panels.py::test_pipeline_panel_shows_the_stored_settings`: stored `number_mode="group"`, selection 2; `tests/test_pipeline_panels.py`: `number_mode_value` with `"group"`, expected `"number_mode": "group"`.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q tests/test_pipeline_filters.py tests/test_pipeline_passthrough.py tests/test_pipeline_pause_properties.py tests/test_lint_rewrites.py tests/test_worldvoice_pipeline_settings.py tests/test_settings_panels.py tests/test_pipeline_panels.py`
Expected: FAIL — group rows fall into the digit branch (`"1 2 3"`-style output), `GroupNumberBreakCommand` undefined, `"pair"` in the driver and panel lists.

- [ ] **Step 3: Implement group mode.** Rename the class and the mode value; the group branch keeps pair mode's rules (decimal unchanged, sign on the first group, cut from the left with `digits[i : i + group_size]`, one separator instance per number even at pause 0, digit table not applied). Change `"pair"` to `"group"` in `_get_availableNummods` and the panel's choice lists.

- [ ] **Step 4: Run to verify they pass, then the full suite**

Run: the Step 2 command, then the full suite.
Expected: PASS; full suite **1877 passed, 0 skipped** (+30 `test_number_mode` ids, +1 leading zeros, +2 instance, +1 G2).

- [ ] **Step 5: Commit** `feat: read numbers in groups of a chosen size`.

### Task 4: Unknown number modes read as value

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py:75-84`
- Test: `tests/test_pipeline_settings_service.py`, `tests/test_worldvoice_pipeline_settings.py`, `tests/test_pipeline_filters.py`, `tests/test_settings_panels.py`, `tests/test_pipeline_pause_properties.py`

**Interfaces:**
- Consumes: Task 3 mode values in the driver and the panel.
- Produces: `NUMBER_MODES: tuple[str, ...] = ("value", "number", "group")`; `_number_mode(value: Any) -> str` (`str(value)` if it is in `NUMBER_MODES`, else `"value"`); the `number_mode` spec gets `normalize=_number_mode`.

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_pipeline_settings_service.py::test_number_mode_reads_and_writes_only_known_modes`, parametrized `raw, expected`: `("pair", "value")`, `("roman", "value")`, `("", "value")`, `(None, "value")`, `("value", "value")`, `("number", "number")`, `("group", "group")`. Assert a profile storing `raw` loads `expected`, and `service.update(number_mode=raw)` on a profile storing `"number"` returns and stores `expected` (for `"number"` nothing is written).
  - `tests/test_worldvoice_pipeline_settings.py::test_an_unknown_number_mode_is_stored_and_read_as_value`: stored `"group"`; `synth.nummod = "pair"` → stored `"value"`, `synth.nummod == "value"`.
  - `tests/test_pipeline_filters.py::test_a_stored_pair_mode_reads_numbers_as_values`: settings from the real service (`load_settings_module` over `{"number_mode": "pair", "group_size": 2}`) passed to `inject_number_mode(["1234"], settings, GENERIC_CONTEXT)` → `["1234"]`.
  - `tests/test_settings_panels.py::test_number_modes_match_the_driver_and_the_panel`: `list(NUMBER_MODES) == list(<SynthDriver>._get_availableNummods()) == panel.number_mode_value` (driver method through `load_definitions`, as `tests/test_lint_rewrites.py::_driver_methods` does).
  - `tests/test_pipeline_pause_properties.py::test_property_number_mode_normalisation_is_closed_and_idempotent` (S1, second half): for `st.one_of(st.text(max_size=8), st.sampled_from(NUMBER_MODES), st.none(), st.integers())`, the result is in `NUMBER_MODES` and normalising it again gives itself.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q tests/test_pipeline_settings_service.py tests/test_worldvoice_pipeline_settings.py tests/test_pipeline_filters.py tests/test_settings_panels.py tests/test_pipeline_pause_properties.py -k "number_mode or nummod or pair_mode or number_modes or normalisation"`
Expected: FAIL — `NUMBER_MODES` / `_number_mode` undefined; `"pair"` and `"roman"` read back unchanged; `"1234"` read digit by digit.

- [ ] **Step 3: Implement `NUMBER_MODES`, `_number_mode` and the `normalize`** in `settings.py`.

- [ ] **Step 4: Run to verify they pass, then the full suite**

Run: the Step 2 command, then the full suite. Confirm `test_pipeline_panel_selects_the_first_choice_for_an_unknown_stored_value` still passes unchanged.
Expected: PASS; full suite **1888 passed, 0 skipped** (+7, +1, +1, +1, +1).

- [ ] **Step 5: Commit** `feat: read unknown number modes as value`.

**Batch 1 end:** §7 verification (Global Constraints), then stop and report to the orchestrator.

---

## Batch 2 (Tasks 5–8)

### Task 5: The number pause inserts NumberBreakCommand

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py:41-46, 249-268`
- Test: `tests/test_pipeline_filters.py`, `tests/test_pipeline_passthrough.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `class NumberBreakCommand(BreakCommand)`; `number_wait_factor` inserts one shared `NumberBreakCommand(wait)` per call, only when the wait is > 0.

- [ ] **Step 1: Write the failing tests.** `B40 = ("NumberBreakCommand", 40)` and every number-wait expectation in `tests/test_pipeline_filters.py` (`test_number_wait_factor_drops_blanks_then_breaks_between_numbers`, `test_number_wait_breaks_only_between_whole_numbers`, `SPLITS`, `test_the_shortest_number_wait_still_breaks` → `("NumberBreakCommand", 1)`, `test_number_wait_splits_across_items_and_keeps_commands` keeping the `("BreakCommand", 5)` marker, `test_digit_mode_then_number_wait_pauses_between_digits`, `test_group_mode_then_number_wait_breaks_between_numbers_only`) and `tests/test_pipeline_passthrough.py::test_number_wait_drops_blank_text_but_not_commands`. New `test_number_wait_inserts_number_break_commands`: `["1 2"]` at 40 → `result[1]` is a `module.NumberBreakCommand` and a `BreakCommand`, `.time == 40`. Keep the identity checks.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q tests/test_pipeline_filters.py tests/test_pipeline_passthrough.py`
Expected: FAIL — the stage still inserts `BreakCommand`; `NumberBreakCommand` undefined.

- [ ] **Step 3: Implement `NumberBreakCommand` and use it in `number_wait_factor`.**

- [ ] **Step 4: Run to verify they pass, then the full suite**

Expected: PASS; full suite **1889 passed, 0 skipped**.

- [ ] **Step 5: Commit** `feat: mark the number pause as a NumberBreakCommand`.

### Task 6: Digit mode separates digits with NumberBreakCommand

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py:350-418`
- Test: `tests/test_pipeline_filters.py`, `tests/test_pipeline_passthrough.py`, `tests/test_pipeline_stages.py`, `tests/test_pipeline_pause_properties.py`

**Interfaces:**
- Consumes: Task 3 signatures, Task 5 `NumberBreakCommand`.
- Produces: `_translate_number(raw, mode, table, group_size, group_pause, number_pause)`; `iter_number_speech_segments_mode(item, mode, translate_table, group_size, group_pause, number_pause, number_re=_NUMBER_RE)`; `inject_number_mode` also reads `settings.scaled_number_wait()` once per call. The digit branch yields one `NumberBreakCommand(number_pause)` instance per number between two adjacent digits, for every pause including 0; every character still goes through the table.

- [ ] **Step 1: Write the failing tests.** With `NB(w) = ("NumberBreakCommand", w)`:
  - `NUMBER_MODES[("number", 3, 0)]`: `"12.5"` → `["1", NB0, "2.5"]`, `"-1234"` → `["-1", NB0, "2", NB0, "3", NB0, "4"]`, `"123"` → `["1", NB0, "2", NB0, "3"]`, `"12"` → `["1", NB0, "2"]`.
  - `test_digit_mode_separates_digits_with_the_number_wait`, parametrized w `0`, `40`: `"12"` → `["1", NB(w), "2"]`; `"-1234"` → breaks are one object.
  - `test_digit_mode_breaks_only_between_adjacent_digits` (Review Focus 4), parametrized, number wait 0: `"A12B"` → `["A1", NB0, "2B"]`; `"3.14"` → `["3.1", NB0, "4"]`; `"1a2"` → `["1a2"]`; `"v1.2"` → `["v1.2"]`.
  - `test_digit_words_are_kept_verbatim_one_per_item` (Review Focus 4): table `{"1": "one ", "2": "two"}` (language `"zh"`, number language `"zh"`), `"12"` → `["one ", NB0, "two"]`.
  - `test_translated_digits_are_not_split` → renamed `test_translated_digits_are_split_by_the_number_wait`: `["一", NB(40), "一"]`.
  - `test_digit_mode_then_number_wait_pauses_between_digits`: exactly `["1", NB(40), "2"]` (no second break).
  - `tests/test_pipeline_passthrough.py::test_number_mode_passes_commands_and_merges_text_around_them`: `kinds(...) == [marker, "a 1", NB0, "2", marker]`.
  - `tests/test_pipeline_stages.py::test_number_mode_reads_symbols_from_context`: shapes `["一", NB0, "一"]` and `["1", NB0, "1"]`.
  - **D1** `test_property_digit_mode_separates_every_digit`: sign from `["", "+", "-"]`, 1–30 digits, w in 0–500, optional table drawn as `st.none() | st.dictionaries(st.sampled_from("0123456789"), st.text("abc一二", min_size=1, max_size=3))`: output alternates `str` / `NumberBreakCommand(w)`; `len(digits) - 1` breaks; without a table the strings join to the input; with a table each string is `sign` (first only) + the translation of one digit.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q tests/test_pipeline_filters.py tests/test_pipeline_passthrough.py tests/test_pipeline_stages.py tests/test_pipeline_pause_properties.py`
Expected: FAIL — digits are still joined by `" "` (`"1 2"`, `"一 一"`).

- [ ] **Step 3: Implement the digit branch and pass `number_pause` through.**

- [ ] **Step 4: Run to verify they pass, then the full suite**

Expected: PASS; full suite **1897 passed, 0 skipped** (+2, +4, +1, +1).

- [ ] **Step 5: Commit** `feat: pause between the digits of a number in digit mode`.

### Task 7: Speech Pipeline panel

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:1-12, 142-278`
- Modify: `tests/ui_harness.py` (`fake_wx`, `gui_stubs`)
- Test: `tests/test_settings_panels.py`, `tests/test_pipeline_panels.py`

**Interfaces:**
- Consumes: Task 2 `group_size`, `group_wait_factor`; `PIPELINE_SETTING_BY_KEY["group_size"].min_value` / `.max_value`.
- Produces: harness `SpinCtrl(parent=None, min=0, max=100, initial=0, **kwargs)` (a `Control` whose value is `initial`, stored as given and never clamped, with `GetMin()` / `GetMax()`), `wx.SpinCtrl`, and module `gui.nvdaControls` with `SelectOnFocusSpinCtrl = SpinCtrl`; panel `_group_size_spin` (`nvdaControls.SelectOnFocusSpinCtrl`, label `_("Group size:")`, min/max from the table, `initial=settings.group_size`), `_group_wait_factor_slider` labelled `_("group wait factor:")` right after it; `onNumberModeChange(self, event)` bound to `EVT_CHOICE` of `_number_mode_choice` and called once at the end of `makeSettings`; `onSave` adds `group_size=self._group_size_spin.GetValue()`. Translator comments come in Task 10.

- [ ] **Step 1: Write the failing tests** in `tests/test_settings_panels.py`:
  - `test_pipeline_panel_shows_the_stored_settings`: stored `group_size=4`; labels `["Effect Scope:", "Ignore comma between number", "Number mode:", "Group size:", "group wait factor:", "global wait factor:", "number wait factor:", "item wait factor:", "sayall wait factor:", "chinese space wait factor:", ...four punctuation controls]`; `panel._group_size_spin` value 4, `GetMin() == 1`, `GetMax() == 10`.
  - `test_pipeline_panel_enables_group_controls_for_the_stored_mode`, parametrized `("value", False)`, `("number", False)`, `("group", True)`, `("pair", False)`: `(spin.enabled, slider.enabled) == (expected, expected)`.
  - `test_pipeline_panel_group_controls_follow_the_mode_choice`: stored value; `Select(2)` + `fire(choice, "EVT_CHOICE", panel=panel)` → both enabled; `Select(1)` + fire → both disabled.
  - `test_pipeline_panel_counts_no_selection_as_not_group` (Review Focus 1): stored group; `Select(-1)` + fire → both disabled.
  - `test_pipeline_panel_saves_the_disabled_group_controls`: stored value; spin 7, slider 30, `onSave()` → stored `group_size == 7`, `group_wait_factor == 30`.
  - `test_pipeline_panel_shows_an_out_of_range_stored_size_within_the_spin_range` (Review Focus 5), parametrized `(0, 1)`, `(12, 10)`, `("4", 4)`: spin value equals the expected int.
  - `test_pipeline_panel_saves_the_edited_controls_to_config`: also sets the spin to 6 → stored `group_size == 6`.
  - `tests/test_pipeline_panels.py::test_pipeline_panel_saves_once_through_the_service`: `panel._group_size_spin = Widget(5)`; the update dict gains `"group_size": 5` and has no `pair_wait_factor`.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q tests/test_settings_panels.py tests/test_pipeline_panels.py`
Expected: FAIL — no `"Group size:"` control, `_group_size_spin` missing, no `EVT_CHOICE` handler (`LookupError: nothing handles`).

- [ ] **Step 3: Implement the harness fakes, then the panel** (control order, spin control, label, enable rule, save). `onNumberModeChange` treats a selection outside `range(len(self.number_mode_value))` as not group.

- [ ] **Step 4: Run to verify they pass, then the full suite**

Expected: PASS; full suite **1907 passed, 0 skipped** (+4, +1, +1, +1, +3).

- [ ] **Step 5: Commit** `feat: set the group size in the speech pipeline panel`.

### Task 8: Voice panel group size control

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py:1-20, 84-89`
- Test: `tests/test_voice_settings_panel.py`, `tests/test_pipeline_panels.py`

**Interfaces:**
- Consumes: Task 7 harness `SpinCtrl` / `gui.nvdaControls`; Task 2 `group_size`.
- Produces: `WorldVoiceVoiceSettingsPanel._addGroupSizeControl(self, settingsSizer)` called after `super().makeSettings` and before `_addPunctuationPauseCharactersControl`; `self.groupSizeSpin` (`nvdaControls.SelectOnFocusSpinCtrl`, label `_("Group size:")`, min/max from `PIPELINE_SETTING_BY_KEY["group_size"]`, `initial=pipeline_settings.get().group_size`), its sizer moved right after `self.sizerDict["nummod"]` (proportion, flag and border kept) and `MoveAfterInTabOrder(self.nummodList)` when `"nummod"` is in `sizerDict`; `onSave` writes `punctuation_pause_characters` and `group_size` in one `update`. Test `Driver` / `SETTINGS` gain `DriverSetting("nummod")` and `NumericDriverSetting("groupwaitfactor")` after `_private`, `availableNummods` (`value`, `number`, `group`), defaults `nummod="value"`, `groupwaitfactor=0`; `ALL` gains both ids.

- [ ] **Step 1: Write the failing tests** in `tests/test_voice_settings_panel.py`:
  - `SETTINGS`, `Driver`, `ALL` as in Produces; `test_every_setting_gets_a_control_in_standard_order_and_unsupported_ones_are_hidden` lists `nummod` and `groupwaitfactor` after `inflection` in `sizerDict` and in the shown ids.
  - `test_group_size_follows_the_number_mode_list`: stored `group_size=5`; `order(panel)` has `"Group size:"` right after `"nummod"`; `panel.groupSizeSpin.tab_after is panel.nummodList`; label `"Group size:"`, value 5, `GetMin() == 1`, `GetMax() == 10`.
  - `test_punctuation_characters_follow_the_wait_factor_slider`: also asserts the spin control's place as above.
  - `test_a_synth_without_pause_settings_gets_the_characters_edit_at_the_end` → renamed `test_a_synth_without_pipeline_settings_gets_the_group_size_and_characters_at_the_end`: order `["voice", "rate", "Automatic language switching (when supported)", "Group size:", "Punctuation pause characters:"]`; spin `tab_after is None` and enabled.
  - `test_saving_writes_the_group_size_and_keeps_it_after_a_later_cancel`: spin 7, `onSave()`, `onDiscard()` → stored `group_size == 7`.
  - `test_cancel_without_save_keeps_the_stored_group_size`: stored 4; spin 9; `onDiscard()` → stored `group_size == 4`.
  - `tests/test_pipeline_panels.py::test_voice_panel_discard_after_apply_keeps_applied_pipeline_values`: `panel.groupSizeSpin = Widget(3)`, `"group_size": 3` in `state` and `PIPELINE_CONFIG_KEYS`.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q tests/test_voice_settings_panel.py tests/test_pipeline_panels.py`
Expected: FAIL — no `groupSizeSpin`, no `"Group size:"` in the order, `onSave` writes no `group_size`.

- [ ] **Step 3: Implement `_addGroupSizeControl` and the `onSave` change**, following `_addPunctuationPauseCharactersControl`.

- [ ] **Step 4: Run to verify they pass, then the full suite**

Expected: PASS; full suite **1910 passed, 0 skipped** (+3).

- [ ] **Step 5: Commit** `feat: set the group size in the voice settings panel`.

**Batch 2 end:** §7 verification, then stop and report to the orchestrator.

---

## Batch 3 (Tasks 9–12)

### Task 9: Voice panel enables the group controls only in group mode

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py` (`makeSettings`, new methods, `_updateValueForControl` string branch `:166-189`)
- Modify: `tests/ui_harness.py` (`VoiceSettingsPanel._createNewControl`)
- Test: `tests/test_voice_settings_panel.py`

**Interfaces:**
- Consumes: Task 8 `groupSizeSpin`, test `Driver` with `nummod`.
- Produces: `_bindNumberModeChoice(self)` (last in `makeSettings`; returns when there is no `nummodList`; binds `wx.EVT_CHOICE` on `nummodList` to `_onNumberModeChoice`, then applies the state); `_onNumberModeChoice(self, evt)` (`evt.Skip()` first, then apply); `_applyGroupControlsState(self)` (no `nummodList` → return; group when `0 <= selection < len(self._nummods)` and `self._nummods[selection].id == "group"`; enables `groupwaitfactorSlider` and `groupSizeSpin`, skipping one that does not exist); `_updateValueForControl` calls it after setting the `nummod` selection. Harness: a string setting's `Choice` binds `EVT_CHOICE` to write `settingsStorage.<id>` from `options[event.GetEventObject().GetSelection()].id`, like NVDA's `StringDriverSettingChanger`.

- [ ] **Step 1: Write the failing tests** in `tests/test_voice_settings_panel.py` (`group_controls_enabled(panel) = (panel.groupSizeSpin.enabled, panel.groupwaitfactorSlider.enabled)`):
  - `test_group_controls_follow_the_stored_mode_when_the_panel_opens`, parametrized `("value", False)`, `("number", False)`, `("group", True)`.
  - `test_choosing_a_mode_updates_the_group_controls_and_still_saves_the_setting`: `nummodList.Select(2)` + `fire(list, "EVT_CHOICE")` → `(True, True)` and `driver.nummod == "group"`; `Select(0)` + fire → `(False, False)` and `driver.nummod == "value"`.
  - `test_a_voice_switch_after_a_settings_ring_mode_change_matches_the_group_controls`, parametrized `"group"`, `"value"`: opened in the other mode, `driver.nummod = mode`, `updateDriverSettings(changedSetting="voice")` → state matches `mode == "group"` and the list selection follows.
  - `test_a_mode_missing_from_the_list_counts_as_not_group` (Review Focus 2): opened in group; `driver.nummod = "gone"`; `updateDriverSettings(changedSetting="voice")` → `nummodList.selection == -1`, `(False, False)`.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q tests/test_voice_settings_panel.py`
Expected: FAIL — group controls stay enabled in value/number mode; `fire` on `nummodList` finds no handler before the harness change.

- [ ] **Step 3: Implement the harness writer, then the three panel methods and the `_updateValueForControl` hook.**

- [ ] **Step 4: Run to verify they pass, then the full suite**

Expected: PASS; full suite **1917 passed, 0 skipped** (+3, +1, +2, +1).

- [ ] **Step 5: Commit** `feat: enable the voice panel group controls only in group mode`.

### Task 10: Strings, translations and readme

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py` (`_("group")`), `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (`_("group")`, `_("Group size:")`, `_("group wait factor:")`), `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py` (`_("Group size:")`)
- Modify: `addon/locale/zh_TW/LC_MESSAGES/nvda.po`, `readme.md:44-46`, `addon/doc/zh_TW/readme.md:44-46`
- Test: `tests/test_translator_comments.py`

**Interfaces:**
- Consumes: the strings added in Tasks 2, 3, 7 and 8.
- Produces: translator comments (spec §4.7 texts); zh_TW entries `"group"` → `群組`, `"Group size:"` → `每組位數：`, `"group wait factor:"` → `群組停頓參數：`, `"Group wait factor"` → `群組停頓參數` (the three pair entries removed); a group-mode bullet in both readmes (spec §10 texts).

- [ ] **Step 1: Write the failing test** `test_group_strings_have_translator_comments` in `tests/test_translator_comments.py`: for every add-on `.py` line containing `_("group")`, `_("Group size:")`, `_("group wait factor:")` or `_("Group wait factor")`, the nearest preceding non-blank line(s) form a `# Translators:` comment block (or the NVDA multi-line form). Assert the list of offending `path:line` is `[]` and that each of the four msgids was found at least once.

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest -q tests/test_translator_comments.py`
Expected: FAIL — the `"group"`, `"Group size:"` and `"group wait factor:"` calls have no comment.

- [ ] **Step 3: Add the comments; update `nvda.po`; add the readme bullets.**

- [ ] **Step 4: Verify**

Run: `python3 -m pytest -q tests/test_translator_comments.py`; `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po`; `scons pot` and check the four msgids are in `WorldVoice.pot` and no `pair` msgid remains (do not stage the `.pot`); the full suite.
Expected: PASS; msgfmt silent; full suite **1918 passed, 0 skipped**.

- [ ] **Step 5: Commit** `docs: translate and document the number group mode` (source files with comments, `nvda.po`, both readmes, the test).

### Task 11: No stacked breaks (X1) and mutmut coverage of the settings

**Files:**
- Modify: `pyproject.toml:38-45`
- Test: `tests/test_pipeline_pause_properties.py`

**Interfaces:**
- Consumes: Tasks 3, 5 and 6 stage behaviour.
- Produces: `"addon/synthDrivers/WorldVoice/pipeline/settings.py"` in `[tool.mutmut] source_paths`.

- [ ] **Step 1: Write the property** **X1** `test_property_number_and_group_breaks_never_touch_another_break`: lists of up to 6 texts over `"0123456789 a.,-"` (max 12 chars), mode from `["value", "number", "group"]`, size 1–10, number wait, group wait, item wait in 0–60 and punctuation wait in 0–300 (punctuation enabled, characters `".,"`); run `inject_number_mode` → `inject_chinese_space_pause` → `item_wait_factor` → `inject_punctuation_pause` → `number_wait_factor` on one settings object; assert no `NumberBreakCommand` or `GroupNumberBreakCommand` has a `BreakCommand` as a neighbour (two item breaks may still be adjacent, spec F7).

- [ ] **Step 2: Run it**

Run: `python3 -m pytest -q tests/test_pipeline_pause_properties.py -k never_touch`; then once with `HYPOTHESIS_PROFILE=deep`.
Expected: PASS (a guard: the spec's prototype passed 3,000 examples). Sanity red: on a scratch copy where `number_wait_factor` inserts its break between every two items (predicate `lambda previous, current: True` instead of `_both_numbers`), X1 fails.

- [ ] **Step 3: Add `settings.py` to the mutmut `source_paths`.**

- [ ] **Step 4: Full suite**

Expected: full suite **1919 passed, 0 skipped**.

- [ ] **Step 5: Commit** `test: guard against stacked number and group breaks`.

### Task 12: mutmut run and final verification

**Files:**
- Modify (only if a survivor is a real gap): the owning test file.
- Modify: `docs/superpowers/specs/2026-10-21-feat-number-group-mode-design.md` (append "14. Mutation results").

**Interfaces:**
- Consumes: Task 11 `source_paths`.
- Produces: the mutation record.

- [ ] **Step 1: Run mutmut** under the scratchpad memory guard (kill below 3 GB MemAvailable):

```bash
mutmut run --max-children 3 \
  "addon.synthDrivers.WorldVoice.pipeline.x__translate_number*" \
  "addon.synthDrivers.WorldVoice.pipeline.x_iter_number_speech_segments_mode*" \
  "addon.synthDrivers.WorldVoice.pipeline.x_inject_number_mode*" \
  "addon.synthDrivers.WorldVoice.pipeline.x_number_wait_factor*" \
  "addon.synthDrivers.WorldVoice.pipeline.settings.*convert*" \
  "addon.synthDrivers.WorldVoice.pipeline.settings.*confspec*" \
  "addon.synthDrivers.WorldVoice.pipeline.settings.x__number_mode*" \
  "addon.synthDrivers.WorldVoice.pipeline.settings.*scaled_group_wait*"
```

Confirm the exact names with `mutmut results` first and adjust the globs.
Expected: the run finishes; the guard does not fire.

- [ ] **Step 2: Triage survivors.** For each: `mutmut show <name>`; confirm it survives by running the suite inside `mutants/` with `MUTANT_UNDER_TEST=<name>` (hygiene guards excluded). A real gap gets a test (red with the mutant, green without) in the owning test file; an equivalent mutant gets a one-line reason.

- [ ] **Step 3: Record** the run (command, counts per function, each survivor with change and reason) as spec section "14. Mutation results". Remove `mutants/`.

- [ ] **Step 4: Final verification** (§7): full suite **1919 passed, 0 skipped** (plus one per kill test added in Step 2); `prek run --all-files` all Passed; `git diff --check master`; both protected-path commands print nothing. Not verifiable on Linux: spec §9.5 items 1–6 (Windows, NVDA, audio, the ring, scope "all" synths, profile upgrade).

- [ ] **Step 5: Commit** `docs: record the group mode mutation results` (spec, plus `test: ...` commits for kills).
