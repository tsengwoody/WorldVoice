# Segment Pause Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Replace the VE/Cerence 100-character chunking with a speech-pipeline stage that, for every engine, inserts a segment break after at most `segment_length` characters without another pause, and make WorldVoice replay the synth parameters in effect after every pause or voice switch.

**Architecture:** An NVDA-free cut rule `segment_cuts` in `text/chunker.py` decides where a run of text items is cut; a new stage `inject_segment_pause` in `pipeline/segments.py` walks the sequence, resets its count at every break and utterance end, and puts one shared `SegmentBreakCommand` after each cut piece; it runs after `number_wait_factor`, before `speech_viewer`. Two table entries in `pipeline/settings.py` give the settings, panels, ring and log switch without UI code. `bridge/commands.normalizeNvdaCommands` keeps an NVDA `ParamChangeTracker`-like state and replays it before the first text after a `Pause` or `SelectVoice`; the VE and Cerence wrappers send one native call per segment again.

**Tech Stack:** Python 3 (NVDA add-on, tabs, ruff `==0.16.3`), pytest, Hypothesis, mutmut 3.8 (Linux), gettext, SCons.

**Spec:** `docs/superpowers/specs/2026-11-03-feat-segment-pause-design.md` (U1–U7, O1–O12, Q1–Q3 decided; §-numbers below refer to it).

## Global Constraints

- Baseline `master` `73eb8c8`: `python3 -m pytest -q -p no:cacheprovider tests` → 3633 passed, 0 skipped; `prek run --all-files` all Passed.
- Defaults: `segment_wait_factor` 0 (slider 0..100, `driver_id="segmentWaitFactor"`), `segment_length` 0 (spin 0..`SPIN_MAX`, `reset_out_of_range=True`, no `driver_id`). With length 0 or a computed pause of 0 ms the stage yields its input unchanged, same objects (U3).
- Pause ms = `global_factor_units × segment_wait_factor` (`scaled_segment_wait`). `effective()` zeroes `segment_wait_factor` for a synth without roles unless scope is "all"; `segment_length` is kept (O3).
- Cut rule (§4.1, O4, Q2 (a), Q3 (a)): candidates after any `str.isspace()` character and at item boundaries, never where `_attached`; the count starts at a piece's first non-blank character; no cut without non-blank text on both sides; hard cut at N moved back before marks, a cluster longer than N stays whole.
- The count resets at every `BreakCommand` instance (any subclass, marked plain breaks, 0 ms) and at `_ends_utterance` items; not at language, index or callback commands (O5).
- Stage order: `… number_wait_factor, segment_wait_factor, speech_viewer` (O6). Log key `segment_wait_factor`, switch `segmentWaitFactor` (O9).
- UI order (U6): "Segment wait factor" (slider) then "Segment length" (spin), right after "Punctuation pause characters".
- Strings: `Segment wait factor` → 「分段停頓參數」, `Segment length` → 「分段字數」, each with the `# Translators:` comment of spec §6.3.
- O7: delete `split_speech_text_pieces`, `MAX_TEXT_LENGTH`, `_ESCAPE_RE`, `_break` and their tests, no shim; `text/chunker.py` stays (public path).
- Docs: only `addon/locale/zh_TW/LC_MESSAGES/nvda.po` and `addon/doc/zh_TW/readme.md`; never the root `readme.md` or other languages. `.pot`/`.mo` are never committed.
- §8 fixed constraints: never edit `addon/synthDrivers/WorldVoice/driver/*/driver/*`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; engine drivers stay independently installable (no driver imports another driver's package; shared code only in core); no Neural; ruff `0.16.3`, tabs; NVDA-free modules snake_case, NVDA-layer camelCase.
- §8 git: stage explicit paths, `git diff --cached --stat` before every commit; English `<type>: <summary>` with a why-body; no `Co-Authored-By`; never `--no-verify`, never `git stash`, no push; never touch `/workspace/WorldVoice`; `ref` symlink never staged. `docs/` files need `git add -f`.
- §8 resources: ≤3 parallel test workers with a MemAvailable < 3 GB guard; mutmut in the background with the same guard killing only its own process tree (`pkill -P`), never `ulimit -v`.

## Review Focus

1. **Unusual whitespace at a cut:** NBSP (U+00A0) and ideographic space are candidates (`isspace`), ZWSP (U+200B) is not, `\r\n` cuts after the `\n`; a person expects no cut inside a word and no pause before trailing spaces. Covered by Task 1 (`test_segment_cuts_pieces` rows `nbsp`, `ideographic`, `zwsp`, `newline-tab`, `crlf` (added by review M1), `trailing-spaces`; property `test_property_segment_cuts_keep_the_rules` draws `\r\n`, NBSP, ZWSP).
2. **Blank and empty text items inside a run** (NVDA hands `""` and `"  "` items, the number stage strips): no break on an empty item, none before only-blank text, none at the run's start or end. Covered by Task 1 (`test_segment_cuts_map_a_cut_to_the_first_item_ending_there`) and Task 3 (`test_a_blank_item_keeps_the_break_after_it`, property `test_property_inserted_breaks_have_spoken_text_around_them`).
3. **Index and callback commands at a cut** (Say All's caret, NVDA's `CallbackCommand`): never dropped, duplicated or reordered; the break goes before them. Covered by Task 3 (`test_the_break_goes_before_the_commands_after_the_cut`, property `test_property_removing_the_breaks_gives_back_the_input`) and Task 5 (`test_index_commands_keep_their_place_while_a_replay_is_pending`).
4. **Replay edges:** a sequence that starts with a pause, ends with a pause and parameter commands, has two pauses with no text between, or turns character mode on across a voice switch: the engine must never get a call of parameter commands alone, nor lose or double a parameter. Covered by Task 5 (`test_no_replay_at_the_end_of_a_sequence`, `test_a_parameter_after_the_pause_is_replayed_once`, `test_character_mode_is_replayed_after_a_voice_switch`, property `test_property_every_segment_speaks_with_nvdas_parameters`).
5. **Extreme segment lengths:** N = 1 and N = `SPIN_MAX`, and 100 000-character text: no quadratic slowdown, no cut for N ≥ text length. Covered by Task 1 (`test_segment_cuts_stay_fast`, `test_segment_cuts_without_a_cut` row `n-max`).

---

### Task 1: The cut rule `segment_cuts`

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/text/chunker.py` (add `segment_cuts`; `_cut_before_marks` gains `start`)
- Test: `tests/test_text_preprocessing.py` (new section "Segment cuts"; the old chunker tests stay until Task 6)

**Interfaces:**
- Consumes: `_attached(token, index)`, `_end_of_marks(token, start)` (unchanged).
- Produces: `segment_cuts(texts: Sequence[str], max_length: int) -> list[tuple[int, int]]` — cuts `(item index, offset)` in order, `0 < offset <= len(texts[index])`; `_cut_before_marks(token, cut, start=0)`.

- [ ] **Step 1: Write the failing tests** (helper `cut_pieces(chunker, texts, n)` splits `"".join(texts)` at the returned cuts and returns the pieces)

```python
E = "é"
@pytest.mark.parametrize(("texts", "n", "pieces"), [
	pytest.param([FOX], 50, ["The quick brown fox jumps over the lazy dog. The ", "quick brown fox jumps over the lazy dog. The ", "quick brown fox jumps over the lazy dog."], id="fox"),
	pytest.param(["Hello world"], 8, ["Hello ", "world"], id="space"),
	pytest.param(["foo bar baz"], 8, ["foo bar ", "baz"], id="last-space"),
	pytest.param(["one two", "three"], 8, ["one two", "three"], id="item-boundary"),
	pytest.param(["a" * 30, "b" * 30], 40, ["a" * 30, "b" * 30], id="boundary-beats-hard-cut"),
	pytest.param(["中文語音合成" * 3], 5, ["中文語音合", "成中文語音", "合成中文語", "音合成"], id="han"),
	pytest.param([E * 3], 3, [E, E, E], id="marks"),
	pytest.param(["x" * 10 + "   "], 10, ["x" * 10 + "   "], id="trailing-spaces"),
	pytest.param(["  ab cd"], 5, ["  ab cd"], id="leading-spaces-uncounted"),
	pytest.param(["   aaaaaaaa b"], 8, ["   aaaaaaaa", " b"], id="leading-spaces-hard-cut"),
	pytest.param(["ab\ncd\tef"], 5, ["ab\n", "cd\tef"], id="newline-tab"),
	pytest.param(["中文　中文"], 3, ["中文　", "中文"], id="ideographic"),
	pytest.param(["ab cd"], 3, ["ab ", "cd"], id="nbsp"),
	pytest.param(["abcd​efgh"], 6, ["abcd​e", "fgh"], id="zwsp"),
	pytest.param(["abc", "́def"], 4, ["abć", "def"], id="mark-item"),
	pytest.param(["\U00020000" * 6], 3, ["\U00020000" * 3] * 2, id="astral"),
	pytest.param(["é́́x"], 2, ["é́́", "x"], id="long-cluster"),
	pytest.param(["abcdefgh"], 3, ["abc", "def", "gh"], id="hard-cuts"),
	pytest.param(["aaaa", "  ", "bbbb"], 6, ["aaaa  ", "bbbb"], id="blank-item"),
])
def test_segment_cuts_pieces(chunker, texts, n, pieces):
	assert cut_pieces(chunker, texts, n) == pieces

@pytest.mark.parametrize(("texts", "n"), [(["abc"], 0), (["abc"], -1), ([], 5), (["   "], 2), (["", " \n"], 1), (["abc"], 3), pytest.param(["a b" * 1000], 2**31 - 1, id="n-max")])
def test_segment_cuts_without_a_cut(chunker, texts, n):
	assert chunker.segment_cuts(texts, n) == []

@pytest.mark.parametrize(("texts", "n", "cuts"), [(["ab ", "", "cd"], 3, [(0, 3)]), (["ab", "", "cd"], 2, [(0, 2)]), (["one two", "three"], 8, [(0, 7)]), (["abc", "́def"], 4, [(1, 1)]), (["aaaa", "  ", "bbbb"], 6, [(1, 2)])])
def test_segment_cuts_map_a_cut_to_the_first_item_ending_there(chunker, texts, n, cuts):
	assert chunker.segment_cuts(texts, n) == cuts

def test_cut_before_marks_stops_at_its_start(chunker):
	assert chunker._cut_before_marks("aé́", 3, 1) == 1
	assert chunker._cut_before_marks("é", 1) == 0

def test_segment_cuts_stay_fast(chunker):
	for texts, n in ((["a" * 100_000], 1), (["ab " * 33_000], 1), (["word " * 20_000], 7), (["x" * 100_000], 2**31 - 1)):
		start = time.perf_counter()
		chunker.segment_cuts(texts, n)
		assert time.perf_counter() - start < 2
```

`FOX = ("The quick brown fox jumps over the lazy dog. " * 3).strip()`. Property `test_property_segment_cuts_keep_the_rules` (`@given` lists of 0–5 items, each a list of 0–12 parts from `["a", "b", " ", "\n", "\r\n", "\t", " ", "　", "​", "́", "ำ", "‍", "\U0001f3fd", "中", "ก"]`, N 1–15): with `T = "".join(texts)` and the pieces between cuts, assert (P1) `"".join(pieces) == T`; offsets valid, in order, never on an empty item; every cut has non-blank text before it and after it in `T`; (P5) `not chunker._attached(T, c)` at every cut; (P2) `len(piece.lstrip())` (the last piece: `len(piece.strip())`) `<= N`, unless every character after the first of the stripped piece is `_attached`.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_text_preprocessing.py -k "segment_cuts or cut_before_marks"`
Expected: FAIL, `AttributeError: module 'text_chunker_under_test' has no attribute 'segment_cuts'` (and a `TypeError` for the 3-argument `_cut_before_marks`).

- [ ] **Step 3: Implement `segment_cuts(texts, max_length)` and `_cut_before_marks(token, cut, start=0)` in `text/chunker.py`**

Follow spec §4.1 steps 1–5 exactly. Precompute the sorted candidate positions and the non-blank positions once (`bisect` over both is fine); never rescan `T` per cut. `_cut_before_marks` loops `while start < cut < len(token) and _attached(token, cut)`. Docstring: the contract of §4.1 (pieces concatenate, non-blank on both sides, no cut before an attached character, the length bound).

- [ ] **Step 4: Run to verify they pass**

Run: same command. Expected: 34 passed (19 + 7 + 5 + 1 + 1 + 1).
Run: `python3 -m pytest -q -p no:cacheprovider tests` → 3667 passed, 0 skipped.

- [ ] **Step 5: Commit** — `git add addon/synthDrivers/WorldVoice/text/chunker.py tests/test_text_preprocessing.py`; `feat: add the segment cut rule for long runs of text`.

---

### Task 2: The two settings

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (two `PIPELINE_SETTINGS` entries after `punctuation_pause_characters`; fields; `scaled_segment_wait`; `effective`)
- Test: `tests/test_pipeline_settings_service.py`, `tests/test_pipeline_pause_properties.py`, `tests/test_settings_order.py`, `tests/test_panel_layout.py`, `tests/test_worldvoice_pipeline_settings.py`, `tests/test_settings_table_guard.py`, `tests/test_settings_panels.py`, `tests/test_pipeline_panels.py`

**Interfaces:**
- Produces: `PipelineSettings.segment_wait_factor: int`, `PipelineSettings.segment_length: int`, `PipelineSettings.scaled_segment_wait() -> int`; stored keys `segmentWaitFactor`, `segmentLength`; voice-panel spin attribute `_segment_length_spin` / `segmentLengthSpin`, slider `segmentWaitFactorSlider`.

- [ ] **Step 1: Update the expectation tests (red first)**
  - `test_pipeline_settings_service.py`: `OLD_DEFAULTS` + `"segment_wait_factor": 0, "segment_length": 0`; `STORED_KEYS` + `"segmentWaitFactor"`, `"segmentLength"`; the canonical order list ends `…, "punctuation_pause_characters", "segment_wait_factor", "segment_length"`; the reset list in `test_group_size_confspec_is_its_range` becomes `["group_size", "segment_length"]`; `test_effective_matches_the_old_synth_scoping` asserts `segment_wait_factor == 0` and `segment_length` kept for a synth without roles and scope "WorldVoice", both kept with scope "all"; a scaled-wait row `({"global_wait_factor": 30, "segment_wait_factor": 7}, "scaled_segment_wait", 21)`; new `test_segment_length_confspec_is_its_range`: `(min, max, default, reset) == (0, 2**31 - 1, 0, True)`, `PIPELINE_CONFSPEC["segmentLength"] == "integer(default=0,min=0,max=2147483647)"`, `PIPELINE_CONFSPEC["segmentWaitFactor"] == "integer(default=0,min=0,max=100)"`.
  - `test_pipeline_pause_properties.py`: `SCALED_WAITS["segment_wait_factor"] = "scaled_segment_wait"`; new `test_property_segment_length_convert_keeps_or_resets` (copy of the group-size property for `segment_length`).
  - `test_panel_layout.py`: creation followers gain `"segmentWaitFactor": ("segment_length",)`; attribute-name rows `segment_length` → `("_segment_length_spin", "segmentLengthSpin", None)` and `segment_wait_factor` → `("_segment_wait_factor_slider", "segmentWaitFactorSlider", "segmentWaitFactorSlider")`; per-panel spec lists gain both keys last.
  - `test_worldvoice_pipeline_settings.py`: `EXPECTED_IDS` gains `"segmentWaitFactor"` last; no setting or descriptor named `segmentLength`.
  - `test_settings_order.py`, `test_settings_panels.py`, `test_pipeline_panels.py`: every hard-coded order or row list gains the two rows after punctuation pause characters (voice panel: `Segment wait factor` slider then `Segment length` spin; ring: `Segment wait factor` after `Punctuation wait factor`; pipeline panel saves both keys).
  - `test_settings_table_guard.py`: new `test_segment_length_is_an_independent_panel_only_spin`, as `test_group_size_is_an_independent_panel_only_spin` (no `driver_id`, `control == "spin"`, no `depends_on`, both panels), and `segment_wait_factor` has no `depends_on` (O2).

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_settings_service.py tests/test_pipeline_pause_properties.py tests/test_settings_order.py tests/test_panel_layout.py tests/test_worldvoice_pipeline_settings.py tests/test_settings_table_guard.py tests/test_settings_panels.py tests/test_pipeline_panels.py`
Expected: FAIL (order lists, `KeyError: 'segment_length'`, `AttributeError: … scaled_segment_wait`).

- [ ] **Step 3: Implement in `pipeline/settings.py`**
  - `PipelineSettingSpec("segment_wait_factor", int, 0, driver_id="segmentWaitFactor", label=_("Segment wait factor"), control="slider")` with the Translators comment of `punctuation_wait_factor`.
  - `PipelineSettingSpec("segment_length", int, 0, label=_("Segment length"), min_value=0, max_value=SPIN_MAX, reset_out_of_range=True, control="spin")` with Translators comment "Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel: the most characters spoken before a segment pause (0: no segments)." and a code comment: resets like `group_size` (decided by the user, 2026-11-03, U2).
  - Fields `segment_wait_factor: int`, `segment_length: int` after `group_size`; `scaled_segment_wait()`; `segment_wait_factor=0` in `effective()`'s `replace`.

- [ ] **Step 4: Run to verify they pass** — same command: all pass. Full suite: 3667 + 4 new tests = 3671 (the table-driven parametrized tests may add cases for the two keys — record the exact count in the ledger), 0 skipped.

- [ ] **Step 5: Commit** — the settings module and the listed tests; `feat: add the segment wait factor and segment length settings`.

---

### Task 3: The stage `inject_segment_pause`

**Files:**
- Create: `addon/synthDrivers/WorldVoice/pipeline/segments.py`
- Modify: `addon/synthDrivers/WorldVoice/pipeline/breaks.py` (`SegmentBreakCommand`), `pipeline/sequence.py` (`_ends_utterance` moves here), `pipeline/numberStages.py` (imports it), `tests/pipeline_harness.py` (pop `…pipeline.segments` and `…text.chunker` in `load_pipeline_module`)
- Test: `tests/test_pipeline_segment_pause.py` (new)

**Interfaces:**
- Consumes: `segment_cuts` (Task 1); `settings.segment_length`, `settings.scaled_segment_wait()` (Task 2).
- Produces: `inject_segment_pause(speech_sequence: Iterable[SpeechCmd], settings: "PipelineSettings", ctx: SpeechContext) -> Iterator[SpeechCmd]`; `class SegmentBreakCommand(BreakCommand)` in `breaks.py`; `_ends_utterance(item: SpeechCmd) -> bool` in `sequence.py`.

- [ ] **Step 1: Write the failing tests** — fixture: `load_pipeline_module(monkeypatch, punctuation_settings(0))`, then `importlib.import_module("synthDrivers.WorldVoice.pipeline.segments")`; `seg(length, pause)` = `SimpleNamespace(segment_length=length, scaled_segment_wait=lambda: pause)`; local `IndexCommand`/`CallbackCommand` classes; `shape()` as in `test_pipeline_unspaced_space.py`; `SB = ("SegmentBreakCommand", 7)`.
  - `test_worked_examples` — the eight §5 rows with commands, pause 7, e.g. `(["Hello world", Break(10), "foo bar baz"], 8) → ["Hello ", SB, "world", ("BreakCommand", 10), "foo bar ", SB, "baz"]`, `(["one two", Index(1), "three"], 8) → ["one two", SB, Index(1), "three"]`, `(["Hello world", EndUtterance(), "foo bar"], 8) → ["Hello ", SB, "world", EndUtterance, "foo bar"]`, the "x" × 10 + spaces row unchanged.
  - `test_nothing_changes_without_a_pause[(0, 7), (-1, 7), (8, 0)]`: `len(out) == len(seq) and all(a is b for a, b in zip(out, seq))` for a long text with commands.
  - `test_nothing_changes_for_real_settings[global 0, global 9]` and `test_nothing_changes_for_another_synth_in_worldvoice_scope`: real `PipelineSettings` from `load_settings_module` with `segment_length=3, segment_wait_factor=50`, global as given (scope "WorldVoice" `.effective(False)` for the second): output objects identical.
  - `test_the_count_restarts_at[Break(5), NumberEdgeBreakCommand(5), marked plain break, EndUtterance(), ConfigProfileTrigger()]`: `["aaaa", X, "bbbb"]`, N 6 → unchanged.
  - `test_the_count_goes_on_across[LangChange("fr"), WVLangChange("fr"), Index(1), Callback()]`: `["aaaa", X, "bbbb"]`, N 6 → `["aaaa", SB, X, "bbbb"]`.
  - `test_the_break_goes_before_the_commands_after_the_cut`: `["one two", Index(1), Index(2), "three"]` → SB right after `"one two"`.
  - `test_every_cut_shares_one_break`: `["abcdefghij"]`, N 3 → three SB, all the same object, `.time == 7`.
  - `test_a_blank_item_keeps_the_break_after_it`: `["aaaa", "  ", "bbbb"]`, N 6 → `["aaaa", "  ", SB, "bbbb"]`.
  - `test_number_stages_and_segments_share_ends_utterance`: `numberStages._ends_utterance is sequence._ends_utterance is segments._ends_utterance`.
  - Properties (Hypothesis; items: text from Task 1's parts, `IndexCommand`, `BreakCommand`, `NumberEdgeBreakCommand`, `EndUtteranceCommand`, `ConfigProfileTriggerCommand`, `LangChangeCommand`; N 1–15, pause 1–50): `test_property_removing_the_breaks_gives_back_the_input` (P1+P6: drop every `SegmentBreakCommand`, join adjacent strings in input and output; equal, commands by identity); `test_property_pieces_stay_within_the_length` (P2 per piece between breaks and resets); `test_property_no_pause_leaves_the_sequence_alone` (P3, length 0 or pause 0); `test_property_inserted_breaks_have_spoken_text_around_them` (P4: between an SB and any other break, reset item or sequence edge there is non-blank text); `test_property_no_cut_splits_a_character` (P5 over each run's joined text).

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_segment_pause.py`
Expected: ERROR at the fixture, `ModuleNotFoundError: No module named 'synthDrivers.WorldVoice.pipeline.segments'`.

- [ ] **Step 3: Implement**
  - `breaks.py`: `class SegmentBreakCommand(BreakCommand): """Pause at a segment cut: after at most segment_length characters with no other pause."""` after `PunctuationBreakCommand`.
  - `sequence.py`: move `_ends_utterance` (body and docstring unchanged) with `from speech.commands import ConfigProfileTriggerCommand, EndUtteranceCommand`; `numberStages.py` imports it from `.sequence` and drops its own.
  - `segments.py` (module docstring: the segment pause, `segment_wait_factor`): `inject_segment_pause` per spec §4.2 — pass through when `length <= 0` or `pause <= 0`; collect a run until an `isinstance(item, BreakCommand)` or `_ends_utterance(item)` item, emit the run cut, then the item; cut a run with `segment_cuts([text items of the run], length)`, split each text item at its offsets and put the one `SegmentBreakCommand(pause)` right after each cut piece. Imports: `from ..text.chunker import segment_cuts` (no `unicodedata` here, structure guard).

- [ ] **Step 4: Run to verify they pass** — same command: 32 passed (8 + 3 + 2 + 1 + 5 + 4 + 1 + 1 + 1 + 1 + 5). Full suite: Task 2 count + 32 (≈ 3703), 0 skipped.

- [ ] **Step 5: Commit** — the four pipeline modules, the harness and the new test; `feat: add the segment pause stage`.

---

### Task 4: Register the stage

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/registry.py` (`STAGES`)
- Modify (tests): `tests/pipeline_harness.py` (`PIPELINE_MODULES` + `"segments"`; `ORDER` / `LOG_SWITCH_ORDER` gain `segment_wait_factor` / `segmentWaitFactor` before `speech_viewer` / `speechViewer`; `punctuation_settings` gains `segment_length=0, scaled_segment_wait=lambda: 0`), every other settings stub that runs the whole `STAGES` (`test_pipeline_unspaced_space.make_settings`, `test_pipeline_number_edges`, `test_pipeline_number_edge_properties`, `test_pipeline_number_groups`, `test_worldvoice_speak.stage_settings`, and any other the full suite names), `tests/test_pipeline_structure.py` (`STAGE_MODULES` + `"segments"`)
- Test: `tests/test_pipeline_segment_pause.py`, `tests/test_pipeline_nvda_ssml.py`, `tests/test_pipeline_log.py`

**Interfaces:**
- Consumes: `inject_segment_pause`, `SegmentBreakCommand` (Task 3).
- Produces: `Stage("segment_wait_factor", inject_segment_pause)` between `number_wait_factor` and `speech_viewer`; `LOG_SWITCHES` gains `segmentWaitFactor`.

- [ ] **Step 1: Write the failing tests**
  - Harness `ORDER`/`LOG_SWITCH_ORDER` updated (the existing order tests go red).
  - `test_pipeline_segment_pause.py::test_another_synth_gets_plain_breaks_at_the_cuts`: with `registry.current_context` patched to `GENERIC_CONTEXT`, settings stub scope "all", `segment_length=8`, pause 7, the stage's `handler(["Hello world"])` → `["Hello ", B, "world"]` with `type(B) is BreakCommand` and `B.time == 7`.
  - `test_pipeline_segment_pause.py::test_the_segment_switch_logs_its_stage`: as the existing per-switch log tests, `segmentWaitFactor` on → a before and an after row under `segment_wait_factor`.
  - `test_pipeline_nvda_ssml.py::test_nvda_ssml_keeps_every_word_at_the_segment_cuts`: scope-all settings with `segment_length=10`, pause 30, `["The quick brown fox jumps over the lazy dog"]` through every `STAGES` handler and NVDA's `SsmlConverter`: the words without tags and spaces equal the input's, `xml.count('<break time="30ms"/>') == 4`, no warnings.
  - `test_pipeline_structure.py` `STAGE_MODULES` gains `"segments"`.
  - The Log Record label: `_LOG_LABELS["segmentWaitFactor"] == "Segment wait factor"` in the existing log panel label test (add the row where that test lists labels).

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_segment_pause.py tests/test_pipeline_nvda_ssml.py tests/test_pipeline_log.py tests/test_pipeline_structure.py tests/test_pipeline_stages.py`
Expected: FAIL on the order lists and the two new handler tests (`StopIteration`/no stage named `segment_wait_factor`).

- [ ] **Step 3: Implement** — import `inject_segment_pause` in `registry.py` and add the `Stage` (spec §4.3 order); add the two fields to every settings stub the full suite reports as `AttributeError: … segment_length`.

- [ ] **Step 4: Run to verify they pass** — same command passes; full suite: Task 3 count + 3 tests + 1 `STAGE_MODULES` case (≈ 3707), 0 skipped.

- [ ] **Step 5: Commit** — registry, harness, the stubs and tests; `feat: run the segment pause after the number pause`.

---

### Task 5: Replay the synth parameters after a pause or voice switch

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/bridge/commands.py`
- Modify (tests): `tests/conftest.py` (`nvda_commands` stub gains `LangChangeCommand(SynthParamCommand)` with `lang` and `isDefault = not lang`, and `SynthParamCommand.isDefault = False`)
- Test: `tests/test_legacy_speech_commands.py`

**Interfaces:**
- Consumes: `Pause`, `SelectVoice` (`runtime/models.py`); `LangChangeCommand`, `SynthParamCommand` (`speech.commands`); `WVLangChangeCommand` (`speechCommands`).
- Produces: `normalizeNvdaCommands(sequence: Iterable[object]) -> Iterator[object]` with the replay of spec §4.6 (still lazy; still raises for `WorldVoiceIndexCommand`).

- [ ] **Step 1: Write the failing tests** — local `Pitch(offset=0)` and `CharMode(state)` classes derived from `nvda_commands.SynthParamCommand` with NVDA's `isDefault`; `P = rt.models.Pause`.
  - `test_parameters_are_replayed_after_a_pause`: `[p := Pitch(30), "a b", Break(10), "c"]` → `[p, "a b", P(0.01), p, "c"]` (the replayed object `is p`).
  - `test_character_mode_is_replayed_after_a_voice_switch`: `[m := CharMode(True), "a", SelectVoice("X"), "b"]` → `[m, "a", SelectVoice("X"), m, "b"]`.
  - `test_a_default_command_clears_its_type`: `[Pitch(30), "a", Pitch(0), "b", Break(10), "c"]` → output after the pause is `[P(0.01), "c"]`.
  - `test_a_parameter_after_the_pause_is_replayed_once`: `[Pitch(30), "a", Break(10), q := Pitch(10), "c"]` → tail `[P(0.01), q, "c"]` (exactly one Pitch after the pause).
  - `test_no_replay_at_the_end_of_a_sequence`: `[Pitch(30), "a", Break(10), Pitch(10)]` → `[Pitch(30) obj, "a", P(0.01)]`.
  - `test_index_commands_keep_their_place_while_a_replay_is_pending`: `[p, "a", Break(10), i := Index(1), "b"]` → `[p, "a", P(0.01), i, p, "b"]`.
  - `test_language_commands_are_not_tracked`: `[LangChangeCommand("fr"), WVLangChangeCommand("de"), "a", Break(10), "b"]` → language commands yielded in place, nothing replayed after the pause.
  - Existing laziness and `WorldVoiceIndexCommand` tests stay green.
  - `test_property_every_segment_speaks_with_nvdas_parameters` (P7): sequences of text, `Pitch(0|10|30)`, `CharMode(True|False)`, `Break`, `SelectVoice`, `Index`; for each text item, NVDA's tracker state over the input up to it (by type → object) equals a fresh tracker run over the output's current segment (split at `Pause`/`SelectVoice`) up to it; the output's text items equal the input's in order.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_legacy_speech_commands.py`
Expected: FAIL — the replay tests show no replayed command after `Pause`.

- [ ] **Step 3: Implement the tracker in `normalizeNvdaCommands`** — a dict by command type; a `SynthParamCommand` that is not `LangChangeCommand`/`WVLangChangeCommand` updates it (`isDefault` pops); pending after a yielded `Pause` or a passed `SelectVoice`; while pending, parameter commands only update the tracker; at the next `str` yield the tracker's values first; nothing at the end. Docstring cites spec §4.6 and NVDA's `ParamChangeTracker` (`ref/nvda/source/speech/manager.py:83-112`).

- [ ] **Step 4: Run to verify they pass** — same command passes. Full suite: Task 4 count + 8 (≈ 3715), 0 skipped.

- [ ] **Step 5: Commit** — `bridge/commands.py`, `tests/conftest.py`, `tests/test_legacy_speech_commands.py`; `fix: keep synth parameters in effect after a WorldVoice pause` (body: F2, O10, Q1 (a)).

---

### Task 6: VE and Cerence speak each segment in one call; remove the old chunker

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py:13,537-542`, `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py:13,541-546` (outer wrappers only)
- Modify: `addon/synthDrivers/WorldVoice/text/chunker.py` (delete `split_speech_text_pieces`, `MAX_TEXT_LENGTH`, `_ESCAPE_RE`, `_break`, `import re`; module docstring), `addon/synthDrivers/WorldVoice/text/__init__.py` (docstring)
- Modify (tests): `tests/worldvoice_cancel_wrapper_harness.py:153` (drop the chunker stub), `tests/test_vocalizer_segment_drain.py` (`:801-825`, `speak_pieces`, `test_segment_without_native_call_reaches_engine_done`, `speak_ordinary_pieces`), `tests/test_worldvoice_cancel_wrappers.py` (`:139-200`), `tests/test_text_preprocessing.py` (drop the 37 `split_speech_text_pieces` tests, escape helpers and the chunk property; module docstring)

**Interfaces:**
- Consumes: `break_repeated_runs` (unchanged).
- Produces: `_speak(self, voiceInstance, chunks)` queues exactly one `_NativeTask` with `break_repeated_runs("".join(chunks))`, none when that is empty.

- [ ] **Step 1: Write the failing tests** (in `test_vocalizer_segment_drain.py`, run for both engines by the `env` fixture)
  - `test_a_long_segment_is_one_native_call`: `text = " ".join(["word"] * 60)` (299 characters); `speak(env, (text,))` → native calls `== [text]`.
  - `test_break_repeated_runs_still_runs`: `env.module.break_repeated_runs` patched to `str.upper` → calls `== ["HELLO"]`.
  - `test_empty_wrapper_text_makes_no_native_call`: `break_repeated_runs` patched to `lambda text: ""` → no native call, one `SEGMENT_DRAINED` event.
  - Rewrites (same assertions, no `split_speech_text_pieces`): several calls come from language switches through the inner driver — helper `switching(texts)` → `(texts[0], Lang(l1), texts[1], Lang(l2), …)` with `env.core.getVoiceNameForLanguage` patched to `lambda language: language`, so each text is its own native call on its own instance; `test_multichunk_langchange_has_one_work_and_final_drain` asserts 2 calls on instances `[1, 2]`, indexes `[1, 2]`; `test_segment_without_native_call_reaches_engine_done` speaks `("   ",)` (the inner driver skips blank text, `veinner:357-360`); the two cancel-wrapper tests speak `["first", Lang("fr"), "second"]` with the language patched to a second voice.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py tests/test_text_preprocessing.py`
Expected: FAIL — `test_a_long_segment_is_one_native_call` gets three calls of ≤ 100 characters from the real chunker (the harness stub is gone; the wrappers still import `split_speech_text_pieces`).

- [ ] **Step 3: Implement** — the wrappers drop the `text.chunker` import and loop; `text/chunker.py` keeps `_attached`, `_end_of_marks`, `_cut_before_marks`, `segment_cuts` and says it now holds the segment cut rule the pipeline uses; `text/__init__.py` says wrappers import `text.arabic`, the pipeline `text.chunker`, both public paths.

- [ ] **Step 4: Run to verify they pass** — same command passes; `git grep -n split_speech_text_pieces -- addon tests` prints nothing. Full suite: Task 5 count − 37 + 6 (3 tests × 2 engines) (≈ 3684), 0 skipped.

- [ ] **Step 5: Commit** — the two wrappers, `text/`, the harness and the three tests; `fix: send each VE and Cerence segment in one native call` (body: F1, U5, O7).

---

### Task 7: WorldVoice end to end and mutation testing

**Files:**
- Test: `tests/test_worldvoice_speak.py` (`stage_settings` gains `segment_length=0, segment_wait=0` parameters)
- Modify: `pyproject.toml` (`[tool.mutmut] source_paths` + `text/chunker.py`, `pipeline/segments.py`, `bridge/commands.py`)

**Interfaces:**
- Consumes: Tasks 1–6.

- [ ] **Step 1: Write the tests**
  - `test_a_long_sentence_is_spoken_in_segments`: `speak_through_stages(monkeypatch, ["The quick brown fox jumps over the lazy dog, then it sleeps."], numlan="default", settings=stage_settings(segment_length=20, segment_wait=10))` → `[(EN, "The quick brown fox "), "|", (EN, "jumps over the lazy "), "|", (EN, "dog, then it sleeps.")]`, and both break calls are `("break", 0.01)`.
  - `test_by_default_a_long_sentence_is_one_segment`: the same sentence with `stage_settings()` → `[(EN, sentence)]`.

- [ ] **Step 2: Run** — `python3 -m pytest -q -p no:cacheprovider tests/test_worldvoice_speak.py -k segment` → 2 passed (Tasks 3–6 already provide the behavior; to confirm the test can fail, set `segment_wait=0` locally once and see the first test fail, then restore). Full suite: Task 6 count + 2 (≈ 3686), 0 skipped.

- [ ] **Step 3: mutmut** — add the three paths to `source_paths`; in a scratch copy (`git worktree add` of the branch into the scratchpad, `ref` symlinked) restrict `source_paths` to the three files and run `mutmut run` in the background with the memory guard; record survivors and reasons in the ledger; kill only mutmut's own tree on low memory; remove the scratch worktree afterwards (own scratch only).

- [ ] **Step 4: Commit** — `tests/test_worldvoice_speak.py`, `pyproject.toml`; `test: speak a long sentence in segments end to end`.

---

### Task 8: zh_TW translation and user guide

**Files:**
- Modify: `addon/locale/zh_TW/LC_MESSAGES/nvda.po`, `addon/doc/zh_TW/readme.md`

- [ ] **Step 1: Translation** — `scons pot`; `msgmerge --update addon/locale/zh_TW/LC_MESSAGES/nvda.po WorldVoice.pot`; `msgattrib --no-obsolete -o addon/locale/zh_TW/LC_MESSAGES/nvda.po addon/locale/zh_TW/LC_MESSAGES/nvda.po`; fill `msgstr "分段停頓參數"` and `msgstr "分段字數"`; `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` prints nothing; no `fuzzy` on the two entries.
- [ ] **Step 2: User guide** — spec §6.4: append「分段停頓相關設定」to the 支援全域 list; the 分段停頓 block after the 標點停頓 block; `## 下一版更新` with both bullets directly below `# WorldVoice 更新日誌`.
- [ ] **Step 3: Verify** — `python3 -m pytest -q -p no:cacheprovider tests/test_translator_comments.py tests/test_locales.py` passes; full suite unchanged from Task 7; `prek run --all-files` all Passed.
- [ ] **Step 4: Commit** — the two files only (no `.pot`, `.mo`); `docs: describe the segment pause in the zh_TW guide and translation`.

---

### Final verification (§7)

- `python3 -m pytest -q -p no:cacheprovider tests` — passed count vs 3633 baseline with the per-task deltas, 0 skipped.
- `prek run --all-files` all Passed; `git diff --check master` empty.
- Both protected-path commands of §7 print nothing.
- Report: commits, counts, Rulings, mutmut survivors, Windows/NVDA manual items of spec §9.5 (unverified).
