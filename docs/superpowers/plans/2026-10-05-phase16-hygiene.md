# Phase 16 Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Clear the remaining ruff findings in the roadmap the way NVDA does.
- Make the WorldVoice-workspace path come from one place.
- Delete the last dead code and fix the stale VE/Cerence and SAPI5 details folded in from phase 15.

**Architecture:**
- Config and comment changes plus mechanical rewrites.
- One new pure module, `synthDrivers/WorldVoice/workspace.py`.
- Guards in `tests/test_hygiene_guards.py`.

**Tech Stack:** Python 3.11; pytest; ruff 0.16.

**Spec:** `docs/superpowers/specs/2026-10-05-phase16-hygiene-design.md`

## Global Constraints

- Never edit `driver/<Engine>/driver/` or `driver/sonic`. VE and Cerence change identically, and the drift test's allow-list stays the same.
- Rewritten format strings must produce byte-identical output.
- `git add` explicit paths only. Never stage `docs/superpowers/finish_task.md` or `refactor.md`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full suite `python3 -m pytest tests -q` (baseline 1665), lint gate and `ruff format --check addon`.

## Review Focus

1. **`%` conversions with a tuple or with `%r`/`%d`.** Check every rewritten site by eye: the f-string must render the same text, including the `repr` quotes.
2. **installTasks running from a pending-install directory.** It must load `workspace.py` by file path from its own add-on copy, not import the installed package. Task 3 tests the loader.
3. **NVDA started with `--config-path`.** All three users get the same directory. Task 3 tests it through a stubbed `globalVars`.
4. **The SAPI5 `stop_player` without a WASAPI player.** It is still a no-op. Task 4 tests it.
5. **`ruff --fix` touching an inner driver or sonic.** The scope excludes must be passed on every fix command; the final `git diff --stat` shows none.

---

### Task 1: Pin the outputs the rewrites touch

**Files:** create `tests/test_format_outputs.py`

- [ ] **Step 1:**
  - `_speechcommand`: load it with the stub `speech.commands` from `tests/test_language_detector.py`'s env fixture. Assert:
    - `repr(WVLangChangeCommand("zh"))` is `"WVLangChangeCommand ('zh')"`;
    - `repr(WVLangChangeCommand(None))` is `"WVLangChangeCommand (None)"`;
    - `repr(WorldVoiceIndexCommand(7))` is `"WorldVoiceIndexCommand(7)"`. Construct it via `object.__new__` and set `index`, because the stub `IndexCommand` stores `index`.
  - `generics/speechSymbols/models.py`: load it by file path with stubs for `globalVars` (`appArgs.configPath=str(tmp_path)`), `languageHandler` (`getAvailableLanguages=lambda: []`) and the other imports it needs. Read the file's imports first. Then:
    - `repr` of a `SpeechSymbol` with two fields set;
    - the line `_saveSymbol` produces for a symbol with an identifier that needs escaping (`\t`) and a `displayName`;
    - the line `save()` writes. Write to `tmp_path`, read the file and assert it exactly.
  - Compute every expectation by running the current code once, and hard-code it.
- [ ] **Step 2: Run** → PASS (characterization). Commit `test: pin the text that format-string rewrites must keep`.

---

### Task 2: ruff findings, NVDA style

**Files:** `pyproject.toml`; the UP031/UP004/UP008/UP035/RUF012 sites listed in the spec; `tests/test_hygiene_guards.py`

- [ ] **Step 1: Failing guard.** In `test_ruff_reports_no_blind_except_or_unsorted_import`, change `--select` to `BLE001,I001,UP004,UP008,UP031,UP035,RUF012,G201` and rename the test to `test_ruff_reports_none_of_the_gated_rules`. Run → FAIL.
- [ ] **Step 2: Implement.**
  - `pyproject.toml` `[tool.ruff.lint] ignore`:

```toml
	# log.error(..., exc_info=True) stays: NVDA's log.exception lowers expected Windows/COM errors
	# to debugWarning (ref/nvda/source/logHandler.py), and WorldVoice wants these at ERROR.
	# NVDA keeps the same calls with inline noqa.
	"G201",
```

  - Auto-fix:

```
ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select UP004,UP008,UP035 --fix
```

    Read the diff.
  - Rewrite the 15 UP031 sites by hand as f-strings with identical output. `views.py:328` becomes `log.error("Error saving user symbols info: %s", e)`. VE and Cerence get the same edit.
  - RUF012:
    - `# noqa: RUF012` on the main driver's `supportedCommands` and `supportedNotifications`, the four tables in `models.py`, and the two panels' `settings`;
    - `FIELDNAMES = ("id", "label", "timing", "timestamp", "sequence")`.
  - Run `ruff format addon`.
- [ ] **Step 3: Run** the full suite (Task 1 assertions unchanged), the drift test and the guard → PASS.
- [ ] **Step 4: Commit** `style: clear the roadmap's ruff findings the way NVDA does`.

---

### Task 3: One workspace path (C12)

**Files:**
- Create: `addon/synthDrivers/WorldVoice/workspace.py`, `tests/test_workspace.py`
- Modify: `addon/synthDrivers/WorldVoice/engine/__init__.py`, `addon/globalPlugins/WorldVoice/__init__.py`, `addon/installTasks.py`, `tests/test_hygiene_guards.py`

- [ ] **Step 1: Failing tests.**
  - `tests/test_workspace.py`:
    - load `workspace.py` by path with a stub `globalVars.appArgs.configPath`, and assert `workspace_path() == os.path.join(config, "WorldVoice-workspace")`;
    - load `installTasks.py` by path with stubs. Look at how existing tests load it: grep `installTasks` in tests and reuse that loader. Assert its workspace loader returns the same path.
  - Guard: the literal `"WorldVoice-workspace"` occurs in `addon/**/*.py` only in `workspace.py`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - `workspace.py` is the spec's code with the imports `os` and `globalVars`.
  - `engine/__init__.py`: delete `user_folder` and its comment; `from ..workspace import workspace_path`; `WVW_PATH = workspace_path()`.
  - GlobalPlugin: `from synthDrivers.WorldVoice.workspace import workspace_path` (with the other `synthDrivers.WorldVoice` imports, above `# isort: split`). In `onFileImport`, `workspace = workspace_path()`.
  - `installTasks.py`: a `_load_workspace()` helper beside the coreArchive loader:

```python
def _workspace_path():
	path = os.path.join(os.path.dirname(__file__), "synthDrivers", "WorldVoice", "workspace.py")
	spec = importlib.util.spec_from_file_location("_worldvoice_install_workspace", path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module.workspace_path()
```

    Use it in place of the inline join.
- [ ] **Step 4: Run** the full suite and lint → PASS.
- [ ] **Step 5: Commit** `refactor: derive the WorldVoice workspace path in one place`.

---

### Task 4: Dead code and the phase-15 leftovers

**Files:** `addon/generics/speechSymbols/models.py`, `addon/generics/speechSymbols/views.py`, `addon/synthDrivers/WorldVoice/driver/{VE,Cerence,SAPI5}/__init__.py`, `tests/test_hygiene_guards.py`, the SAPI5 test file (`tests/test_sapi5_segment_drain.py`)

- [ ] **Step 1: Failing tests.**
  - Guards: no `CancellableSynthDriver` in addon; no `localesToNames` in `models.py`; no `base_path` in `views.py`; the SAPI5 `stop_player` source has no `driver is not None`; neither VE nor Cerence contains `captured once per core`.
  - Behavior, in `tests/test_sapi5_segment_drain.py` with its loader: the strategy's `stop_player` with `driver.player = None` does nothing; with a player, it calls `stop()` once.
- [ ] **Step 2: Run** → the guards FAIL.
- [ ] **Step 3: Implement** per spec §3–§4, editing VE and Cerence identically.
- [ ] **Step 4: Run** the full suite (drift test included) and lint → PASS.
- [ ] **Step 5: Commit** `chore: remove the last dead code and stale details`.

---

Final verification:

```bash
python3 -m pytest tests -q
ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select BLE001,I001,UP004,UP008,UP031,UP035,RUF012,G201,F401,F821
ruff format --check addon
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver' addon/synthDrivers/WorldVoice/driver/sonic
```
