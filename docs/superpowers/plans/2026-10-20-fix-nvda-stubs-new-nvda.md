# fix/nvda-stubs-new-nvda implementation plan

Spec: `docs/superpowers/specs/2026-10-20-fix-nvda-stubs-new-nvda-design.md` (`ae7415c`). Branch `fix/nvda-stubs-new-nvda`, baseline `master` `5e1137b`. Test-only change; no product code, translation or packaging.

Every pytest run is `python3 -m pytest -q tests`, single process, with a memory monitor that stops pytest when MemAvailable drops below 3 GB (another agent runs tests at the same time).

## Step 1: red

The worktree's `ref` symlink points at `/workspace/WorldVoice/ref` (`ref/nvda` `7d25bc76e`). Run the full suite unchanged.

Expected:

```
9 failed, 1601 passed, 2 warnings, 112 errors
```

Every failure and error carries the same exception:

```
ImportError: cannot import name 'SequenceItemT' from 'speech.types' (unknown location)
```

## Step 2: green

File: `tests/onecore_drain_harness.py`

Edit:

```diff
-	module("speech.types", SpeechSequence=list)
+	module("speech.types", SpeechSequence=list, SequenceItemT=object)
```

`ref/nvda/source/synthDrivers/oneCore.py:32` at `7d25bc76e` imports `SequenceItemT` and uses it only in a return annotation, which Python 3.14 never evaluates here, so `object` is enough (spec section 3).

Expected, against `ref/nvda` `7d25bc76e` (worktree):

```
1722 passed, 2 warnings
```

Expected, against `ref/nvda` `732d1ce2f`: run from a scratch copy of the tree in the agent's scratchpad, whose `ref` symlink points at `/tmp/claude-0/-workspace-WorldVoice/4475b454-b750-4bfd-b046-7aad0fdefc9c/scratchpad/ref-prev`. The worktree's own `ref` and `ref-prev` are not changed.

```
1722 passed, 2 warnings
```

0 skipped in both runs. The 2 warnings are the pre-existing `codecs.open` `DeprecationWarning`s from `addon/generics/speechSymbols/models.py:68,154`.

Commit: `test: stub SequenceItemT for NVDA's new OneCore import`, staging only `tests/onecore_drain_harness.py`.

## Step 3: verification (`DEVELOPMENT_WORKFLOW.md` section 7)

- Full suite as in step 2, both NVDA versions: `1722 passed`, 0 skipped.
- `prek run --all-files`: every hook Passed.
- `git diff --check`: no output.
- Protected paths, both with no output:

  ```bash
  git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py
  git ls-files addon/synthDrivers/WorldVoice/driver/Neural
  ```

- `git diff --stat master` lists only the spec, this plan and `tests/onecore_drain_harness.py`; `ref` is never staged.
- mutmut: not needed (no core decision module is touched).

## Why there is no stub-drift guard test

A guard such as "every name a loaded ref file imports with `from speech.types import ...` exists in the stub" was considered and not added:

- The current failure is already easy to diagnose. All 121 failures carry one `ImportError` that names the missing name and the stubbed module, and the traceback points at the NVDA line (`oneCore.py:32`). A guard would report the same fact once instead of 121 times, and the 121 would still fail.
- The stub contents exist only inside `load_onecore`'s body, as inline `module(...)` calls (`tests/onecore_drain_harness.py:203-247`). A guard would have to copy that name list (which can drift itself) or move the stubs into a shared table, which is the harness refactor the spec rules out (spec section 2, non-goals).
- It would cover only `from X import name`. The other ways the stubs can drift, such as a stubbed class that lacks a method NVDA starts to call, or a name used at definition time rather than only in an annotation, would still surface as ordinary test failures.
- Skipping cleanly without `ref/` is possible (`tests/test_nvda_settings_copy.py:53-56` does it), but it does not help here: the guard has value only when `ref/` is present, and then the OneCore tests already fail with the precise message.

When NVDA is next upgraded, the stub drift shows up as the same kind of single, named `ImportError` or `AttributeError` across the OneCore tests. The fix stays a one-line change in the shared harness.
