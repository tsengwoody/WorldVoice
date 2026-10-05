# Phase 20 Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Take `ruff check` on the add-on from 38 findings to 0, rule by rule, the way NVDA handles each rule.
- Keep it at 0: run NVDA's `ruff --fix` lint hook in pre-commit, and gate every rule in `tests/test_hygiene_guards.py`.
- Change no behavior. Every rewritten output stays byte-identical.

**Architecture:**
- One new function: `worldvoice_synth()` in `pipeline/context.py`.
- One renamed method: `VoiceSettingsStore.keys()` becomes `names()`.
- One new module constant: `_LEGACY_CONTRACT` in `nvdaEventBridge.py`.
- Lint configuration:
  - `pyproject.toml` gains a `TRY004` per-file ignore, an `S110` ignore and a `driver/sonic` exclude, each with its reason;
  - `.pre-commit-config.yaml` gains the `ruff` lint hook and the same sonic exclude.

**Tech Stack:** Python 3.11; pytest; ruff 0.16 (pre-commit pins 0.16.3, local 0.16.9); pre-commit.

**Spec:** `docs/superpowers/specs/2026-10-05-phase20-hygiene-design.md`

## Global Constraints

- Never edit `driver/<Engine>/driver/` or `driver/sonic`, and keep both out of the new lint hook. The only engine wrapper touched is `driver/OneCore/__init__.py`. VE and Cerence are not touched, and the `tests/test_vocalizer_drift.py` allowlist stays.
- The Neural plugin contract stays: `tests/test_plugin_voice_contract.py` passes. `ref/Neural` does not use `VoiceSettingsStore.keys()`.
- No user-visible behavior changes. Translated strings (`_()`, `pgettext`) are not edited. Kept by user decision: the `except Exception: pass` in `with_order_log`, VE/Cerence as separate copies, and the `exec`-based tests.
- Before rewriting code whose output could change, add a test that pins the current output and passes on the current code.
- After every automatic fix, review the diff line by line.
- `git add` explicit paths only (`-f` for files under the ignored `docs/`). Never stage `docs/superpowers/finish_task.md`, `refactor-cleanup.md`, `refactor.md` or anything under `storage/`.
- Commits end with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Tab indentation, line length 110, `ruff format`.
- Verification after every task:
  - the full suite `python3 -m pytest tests -q` (baseline 1745);
  - the ruff total never rises. Until Task 9, measure it with `ruff check addon --extend-exclude addon/synthDrivers/WorldVoice/driver/sonic --statistics`; after Task 9, plain `ruff check addon`;
  - `ruff format --check addon --extend-exclude addon/synthDrivers/WorldVoice/driver/sonic`.

## Review Focus

1. **`SIM118` false positives (Task 4).** None of the five sites is a dict. `VoiceSettingsStore` is not iterable, so `for key in store` would raise. The rename must reach every caller, including `VoiceEditSession._keys()`, which ruff does not report.
2. **Repr order (Task 3).** `__slots__` is sorted, but `repr(SpeechSymbol(...))` keeps the constructor order (`EXPECTED_REPR` unchanged).
3. **`worldvoice_synth()` (Task 6).** `set_main_voice` still asks at save time. It does not capture the synth from when the panel opened.
4. **Lint scope (Tasks 9–10).** `ruff check addon` and the pre-commit hook skip `driver/*/driver`, `driver/sonic` and `script_data.py`. The gate test must not use CLI `--exclude`, which replaces the pyproject list.
5. **Ignores (Task 9).** `TRY004` is ignored only in the three `compat/` files. `S110` is ignored only because every report is also a `BLE001` or `E722` report.

---

### Task 1: Pin the outputs the rewrites must keep

**Files:**
- Modify: `tests/test_format_outputs.py`
- Create: `tests/test_lint_rewrites.py`

- [ ] **Step 1: Speech symbol load warning.** In `tests/test_format_outputs.py`, add `test_invalid_symbol_line_warning`:
  - Capture `log.warning` in the `models` fixture's `logHandler` stub.
  - Write a file whose only non-comment line is `x\ty\ten\tbogus` (an unknown mode makes `_loadSymbol` raise `ValueError`), then call `SpeechSymbols().load(path)`.
  - Assert the single warning equals `f"Invalid line in file {path}: x\ty\ten\tbogus"`.
- [ ] **Step 2: Main driver helpers.** In `tests/test_lint_rewrites.py`, exec only the needed `SynthDriver` methods, using the `_synth_settings_class` pattern from `tests/test_voice_settings_transaction.py`, and test:
  - `patchedSpeakSpelling`, with `uwv` on and `trustVoiceLanguage` on: one `_realSpellingFunc` call per `(text, locale)` part from `_languageDetector.process_for_spelling(text, locale)`, with `useCharacterDescriptions` and `priority` passed through;
  - `patchedSpeakSpelling`, with either flag off: one call with the original arguments;
  - `_get_availableNummods`: returns a plain `dict` with the keys `value`, `number`, `pair` in that order, each a `StringParameterInfo` with the same id.
- [ ] **Step 3: Run** both files → PASS on the current code.
- [ ] **Step 4: Commit** `test: pin the outputs the lint rewrites must keep`.

### Task 2: Apply ruff's safe fixes

**Files:**
- Modify: `languageDetection/__init__.py` (UP009), `_speechcommand.py` (UP045 and the now-unused `Optional` import), `pipeline/__init__.py` (UP007), `generics/speechSymbols/views.py` (UP024), `VoiceSettingsDialogs.py` (B010), `runtime/scheduler.py` (SIM117 ×3)

- [ ] **Step 1: Fix.** Run `ruff check addon --extend-exclude addon/synthDrivers/WorldVoice/driver/sonic --select UP009,UP045,UP007,UP024,B010,SIM117,F401 --fix`, then `ruff format` on the touched files.
- [ ] **Step 2: Review the diff.**
  - Each `with a:` / `with b:` pair becomes `with a, b:` with nothing between them.
  - `Union` stays imported in `pipeline/__init__.py` (still used at line 27).
  - `setattr` becomes a plain attribute assignment.
- [ ] **Step 3: Run** the full suite → PASS. The ruff total drops by 8 (to 30).
- [ ] **Step 4: Commit** `style: apply ruff's safe fixes`.

### Task 3: Speech symbols the way NVDA writes them

**Files:**
- Modify: `addon/generics/speechSymbols/models.py`, `addon/generics/speechSymbols/views.py`, `tests/test_format_outputs.py`

- [ ] **Step 1: Failing test.** `test_repr_lists_every_slot`: `set(models.SpeechSymbol._REPR_FIELDS) == set(models.SpeechSymbol.__slots__)` and `list(__slots__) == sorted(__slots__)`. Run → FAIL (no `_REPR_FIELDS`).
- [ ] **Step 2: Implement.**
  - `__slots__ = ("displayName", "identifier", "language", "mode", "replacement")`.
  - `_REPR_FIELDS = ("identifier", "replacement", "language", "mode", "displayName")`, with a comment that repr keeps the constructor's order.
  - `__repr__` builds `f"{attr}={getattr(self, attr)!r}"` over `_REPR_FIELDS`.
  - The load warning becomes `f"Invalid line in file {fileName}: {line}"`.
  - In `views.py`, `list(X.keys())[0]` becomes `next(iter(X))` (two lines).
- [ ] **Step 3: Run** `tests/test_format_outputs.py` → PASS, with `EXPECTED_REPR` and the Task 1 warning unchanged. Run the full suite → PASS. The ruff total drops by 5.
- [ ] **Step 4: Commit** `refactor: write the speech symbol strings and slots the way NVDA does`.

### Task 4: Rename `VoiceSettingsStore.keys()` to `names()`

**Files:**
- Modify: `runtime/settings.py`, `voiceManager.py`, `mainLocalePolicy.py`, `globalPlugins/WorldVoice/rolePresenter.py`, `tests/test_runtime_settings_store.py`, `tests/test_runtime_session.py`

- [ ] **Step 1: Failing test.** In `tests/test_runtime_settings_store.py`, change the existing assertion to `store.names() == ("Fake:a",)`, and add an assertion that `store` has no `keys` attribute. Run → FAIL.
- [ ] **Step 2: Implement.**
  - Rename the method; its docstring says it returns a snapshot of the voice names taken under the lock.
  - Update the five reported callers and `VoiceEditSession._keys()`.
  - Update `tests/test_runtime_session.py:189`.
  - `grep -rn "\.keys()" addon tests` shows no store caller left.
- [ ] **Step 3: Run** the full suite → PASS. The ruff total drops by 5.
- [ ] **Step 4: Commit** `refactor: name the voice settings store's listing names() so it does not pass for a dict`.

### Task 5: Loops and literals that do only what they use

**Files:**
- Modify: `globalPlugins/WorldVoice/speechSettingsDialog.py`, `voiceManager.py`, `synthDrivers/WorldVoice/__init__.py`

- [ ] **Step 1: Implement.**
  - PERF102: `for k, v in self.settings.items()` becomes `for k in self.settings` (×3), and `voiceManager.reload` iterates `self._instanceCache.values()`.
  - C403: `set([...])` becomes `{...}`.
  - C418: `_get_availableNummods` returns the dict literal directly.
  - SIM102: `SpeechEngineSettingsPanel.onSave` becomes one condition, `self.activeEngine != self.previousActiveEngine and self._write_settings() and self.confirm == wx.YES`, with the comment kept above it.
- [ ] **Step 2: Run** the full suite → PASS; the Task 1 `_get_availableNummods` test is unchanged. The ruff total drops by 7.
- [ ] **Step 3: Commit** `refactor: iterate and build only what each settings helper uses`.

### Task 6: One helper asks whether WorldVoice is the current synth

**Files:**
- Modify: `synthDrivers/WorldVoice/pipeline/context.py`, `globalPlugins/WorldVoice/speechSettingsDialog.py`, `tests/test_role_panel.py`, `tests/test_unicode_panel.py`
- Create: tests in `tests/test_lint_rewrites.py`

- [ ] **Step 1: Failing test.** `test_worldvoice_synth_returns_only_worldvoice`: with `getSynth` stubbed, the helper returns the synth when its name is `"WorldVoice"`, and `None` for `"eSpeak"`, for a synth without a name, and for `None`. `current_context()` still returns `GENERIC_CONTEXT` for the non-WorldVoice cases. Run → FAIL (no helper).
- [ ] **Step 2: Implement.**
  - Add `worldvoice_synth()`, and make `current_context()` use it.
  - In `speechSettingsDialog.py`, import it from `synthDrivers.WorldVoice.pipeline.context`.
  - Replace the six checks:
    - `worldvoice_synth() is None` at 297, 581, 605 and 676;
    - `worldvoice_synth() is not None` at 833;
    - in `set_main_voice`, `current = worldvoice_synth()`, then `if current is not None: current.voice = name`.
- [ ] **Step 3: Update the exec environments** in `test_role_panel.py` (four) and `test_unicode_panel.py` (one) to provide `worldvoice_synth`, with the same synth or `None` the test meant.
- [ ] **Step 4: Run** the full suite → PASS. The ruff total drops by 3. `grep -n '== "WorldVoice"' addon/globalPlugins` finds nothing.
- [ ] **Step 5: Commit** `refactor: ask one helper whether WorldVoice is the current synth`.

### Task 7: Driver loop variable and the bridge's default contract

**Files:**
- Modify: `synthDrivers/WorldVoice/__init__.py`, `synthDrivers/WorldVoice/nvdaEventBridge.py`

- [ ] **Step 1: Implement.**
  - B020/PLR1704: in `patchedSpeakSpelling`, `for part, loc in ...: self._realSpellingFunc(part, loc, ...)`.
  - B008: add `_LEGACY_CONTRACT = CompletionContract()` after the imports, with the comment "Frozen, so one instance can be every binding's default." Then `completion: CompletionContract = _LEGACY_CONTRACT`.
- [ ] **Step 2: Run** the Task 1 tests, the event bridge tests and the full suite → PASS. The ruff total drops by 3.
- [ ] **Step 3: Commit** `refactor: keep the spelling argument unshadowed and name the bridge's default contract`.

### Task 8: OneCore's stale noqa and unused unpacked error (N12)

**Files:**
- Modify: `synthDrivers/WorldVoice/driver/OneCore/__init__.py`

- [ ] **Step 1: Implement.**
  - Delete the whole `# noqa: BLE001 - …` comment on line 304; the handler logs with `exc_info` in its `else` branch, so ruff no longer reports it.
  - Rename `error` to `_error` on line 499.
- [ ] **Step 2: Run** the full suite (the OneCore and blind-except guard tests) → PASS. The ruff total drops by 2, leaving `TRY004` ×4 and `S110` ×1.
- [ ] **Step 3: Commit** `refactor: drop OneCore's stale noqa and its unused unpacked error`.

### Task 9: Ignore `TRY004` and `S110` with reasons, and exclude sonic

**Files:**
- Modify: `pyproject.toml`, `.pre-commit-config.yaml`, `tests/test_hygiene_guards.py`

- [ ] **Step 1: Failing test.** `test_lint_ignores_keep_their_documented_reasons`:
  - pyproject ignores `"S110"` with a reason naming `BLE001` and `E722`;
  - it ignores `TRY004` per file for exactly the three `compat/` files, with a reason naming the `ValueError` contract;
  - it excludes `driver/sonic`.
  Run → FAIL.
- [ ] **Step 2: Implement.**
  - `pyproject.toml`:
    - add `"./addon/synthDrivers/WorldVoice/driver/sonic"` to `exclude` ("Copied from NVDA; WorldVoice never modifies it.");
    - add `"S110"` to `ignore` with its reason;
    - add the three `TRY004` per-file entries under one reason comment.
  - `.pre-commit-config.yaml`: add `driver/sonic/ |` to the global exclude.
- [ ] **Step 3: Run** `ruff check addon` → `All checks passed!`. Run `ruff format --check addon` → PASS. Run the full suite → PASS.
- [ ] **Step 4: Commit** `build: ignore TRY004 and S110 with their reasons and keep sonic out of ruff`.

### Task 10: Gate every rule and run the lint hook in pre-commit

**Files:**
- Modify: `tests/test_hygiene_guards.py`, `.pre-commit-config.yaml`

- [ ] **Step 1: Failing test.** In `tests/test_hygiene_guards.py`:
  - Replace `test_ruff_reports_none_of_the_gated_rules` with `test_ruff_reports_nothing`: `ruff check addon --output-format concise`, with no `--select` and no CLI exclude.
  - Delete `GATED_RULES` and `RUFF_SCOPE`, and reword the comment in the `G201` test.
  - Add `test_pre_commit_runs_the_ruff_lint_hook`: the YAML text has `- id: ruff` with `args: [ --fix ]` before `- id: ruff-format`, and no longer says the lint hook is omitted.
  Run → the hook test FAILS; `test_ruff_reports_nothing` PASSES.
- [ ] **Step 2: Implement.** Add the `ruff` hook (`name: lint with ruff`, `args: [ --fix ]`, `files: ^addon/`) before `ruff-format`, and delete the "omits the lint hook" comment.
- [ ] **Step 3: Mutation check.**
  - Add `x = dict({})` at the end of `addon/synthDrivers/WorldVoice/workspace.py`, then run `test_ruff_reports_nothing` → FAIL (C418).
  - Revert with `git checkout -- addon/synthDrivers/WorldVoice/workspace.py`, then run it again → PASS.
- [ ] **Step 4: Run** the full suite → PASS. Run `pre-commit run --all-files` (pre-commit from a scratch venv) → every hook passes with no file modified; if the environment cannot run it, record why.
- [ ] **Step 5: Commit** `build: run ruff's lint hook in pre-commit and gate every rule`.

### Task 11: Final verification

- [ ] The full suite passes, at 1745 plus the new tests.
- [ ] `ruff check addon` reports 0, and `ruff format --check addon` passes.
- [ ] `git diff master --stat -- addon/synthDrivers/WorldVoice/driver/*/driver addon/synthDrivers/WorldVoice/driver/sonic addon/synthDrivers/WorldVoice/driver/VE addon/synthDrivers/WorldVoice/driver/Cerence` is empty.
- [ ] `git diff master -- addon | grep '^[-+].*_(\|pgettext'` shows no translated string text changed.
- [ ] Align the spec and plan with what was implemented, if anything differed.
