# Phase 36: `bridge/` and `voices/` packages, one primary-language helper

Date: 2026-10-26.
Base: `master` `c94623b` (Unicode 18.0.0 data). Branch: `phase36-bridge-voices`.
Source: round-8 review `storage/refactor8.md` §6 "階段 36" — findings F2 (§2.2), F5 (§2.5), A1 (§4.1) and the F11 docstring items for `driver/__init__.py` and `text/__init__.py` (§2.11).
Status: automatic flow (DEVELOPMENT_WORKFLOW.md §3), run as the **complex flow** (§4).

## 0. Why the complex flow

This phase is a wide mechanical move and rename: seven add-on modules change package, one package is renamed, and about 35 test files and harnesses name those modules by path or by dotted name. DEVELOPMENT_WORKFLOW.md §4.0 lists "大範圍的機械式修改 … 必須證明沒有夾帶其他修改" as a complex-flow case. The plan therefore carries byte-exact `File:`/`Edit:` blocks and the expected `HEAD:addon`/`HEAD:tests` tree ids after every commit, and is dry-run in a fresh clone before it is applied (§4.2–4.4).

## 1. Problem

All paths below are under `addon/synthDrivers/WorldVoice/` unless stated.

1. **`compat/` reads as removable, but it is the permanent boundary layer** (F2).
   - The plugin base `Voice` subclasses `compat.voiceFacade.VoiceFacade` (`driver/__init__.py:5`, `:12`).
   - Every engine resource the voice manager opens is a `compat.engineAdapter.LegacyEngineAdapter` (`voiceManager.py:7-8`).
   - The phase 5 rule "`runtime/` does not depend on `compat/`" (`docs/superpowers/specs/2026-10-04-phase5-voice-binding-design.md:29`) shows what the package is: the NVDA/Voice side of the pure runtime.
   - Two modules of that same layer sit at the package root: `nvdaEventBridge.py` ("Translate NVDA notifications at the boundary of the pure voice runtime", `nvdaEventBridge.py:1`) and `indexLedger.py`, whose importers are all boundary code (`compat/indexCodec.py:10`, `compat/engineAdapter.py:22`, `nvdaEventBridge.py:7`, `voiceManager.py:9`, `__init__.py:34`).
2. **The voice-management modules are scattered at the root** (F5). `voiceManager.py` and its four collaborators — `voiceCatalog.py` (used only by `voiceManager.py:18`), `mainLocalePolicy.py` (only `voiceManager.py:10`), `roles.py` (`voiceManager.py:12`, `mainLocalePolicy.py:6`, `voiceCatalog.py:12`, `globalPlugins/WorldVoice/rolePresenter.py:5`) and `configRepository.py` (only `__init__.py:32`) — sit among 17 root modules. `configRepository.py` holds only `ConfigVoiceSettingsRepository` and `VOICE_CONFSPEC` (`configRepository.py:20`, `:24`), the per-voice parameter store; the name does not say which of the add-on's config repositories it is.
3. **Two copies of the primary-language helper** (A1).
   - `roles.getPrimaryLocale` (`roles.py:8-12`): `if not locale: return locale`, then `re.split(r"[-_]", locale, maxsplit=1)[0].lower()`.
   - `languageDetection.get_primary_language` (`languageDetection/__init__.py:97-98`): `locale.replace("-", "_").split("_", maxsplit=1)[0].lower()`.
   - For every `str` both return the text before the first `-` or `_`, lower-cased; for `""` both return `""`. They differ only for a falsy non-string: `getPrimaryLocale(None)` returns `None`, `get_primary_language(None)` raises `AttributeError`.
4. **Two misleading docstrings** (F11).
   - `driver/__init__.py:1` says "Legacy engine metadata and lifecycle …". This module is the one base every engine wrapper subclasses, built-in or WorldVoice-workspace plugin (`ref/Neural/Neural/__init__.py` imports only `synthDrivers.WorldVoice.driver`); "Legacy" suggests it should not be used.
   - `text/__init__.py:1` does not say that wrappers import it by absolute path (`driver/VE/__init__.py:12-13`, `driver/Cerence/__init__.py:12-13`), which makes its path public.

## 2. Goals

1. Rename `compat/` to `bridge/` and move `nvdaEventBridge.py` → `bridge/nvdaEvents.py` and `indexLedger.py` → `bridge/indexLedger.py`. `bridge/__init__.py` stays empty (it is empty today as `compat/__init__.py`), so importing a submodule has no side effect.
2. New package `voices/` with an empty `__init__.py`:

   | From | To |
   | --- | --- |
   | `voiceManager.py` | `voices/manager.py` |
   | `voiceCatalog.py` | `voices/catalog.py` |
   | `roles.py` | `voices/roles.py` |
   | `mainLocalePolicy.py` | `voices/mainLocalePolicy.py` |
   | `configRepository.py` | `voices/settingsRepository.py` |

3. One primary-language helper: `primary_language(locale)` in a new root module `locales.py` that imports nothing (like `numberLanguage.py`, whose docstring gives the same reason, `numberLanguage.py:1-5`). `voices/roles.py`, `voices/catalog.py`, `voices/mainLocalePolicy.py` and `languageDetection/__init__.py` import it; `getPrimaryLocale` and `get_primary_language` are removed.
4. Docstrings: `driver/__init__.py` describes the base every engine wrapper subclasses; `text/__init__.py` says it is wrapper-facing and its import path is public.
5. Every importer, test, harness, guard, comment and docstring in `addon/` and `tests/` follows the new paths. `pyproject.toml` (`[tool.mutmut] source_paths`, `[tool.ruff.lint.per-file-ignores]`) follows them too; the per-file ignores must move with the files or `ruff check` (and so `prek` and `tests/test_hygiene_guards.py::test_ruff_reports_nothing`) fails on `bridge/`.
6. Every move uses `git mv` and keeps the file's content apart from import lines and the edits listed here, so `git log --follow` and rename detection keep the history.

## 3. Non-goals

- No behavior change. NVDA users hear and see nothing new; no new or changed UI strings, so no translation work.
- No class, function or attribute renames: `LegacyEngineAdapter`, `LegacyVoiceBinding`, `VoiceFacade`, `NvdaEventBridge`, `IndexLedger`, `VoiceManager`, `VoiceCatalog`, `ConfigRoleRepository`, `ConfigVoiceSettingsRepository`, `EngineConsistency`/`VoiceConsistency`/`ParameterConsistency`, the synth's `_voiceManager`/`_indexLedger`/`_eventBridge` attributes, and `VoiceManager.roles` keep their names.
- No change to phases 37–39 items (F1, F3, F4, F6–F10, A2, A3).
- Historical documents under `docs/` keep the old paths as written.
- Test files named after classes (`test_index_ledger.py`, `test_nvda_event_bridge.py`, `test_voice_manager_structure.py`, …) keep their names.

## 4. Constraints (DEVELOPMENT_WORKFLOW.md §8, refactor8.md §0)

- Public import paths do not change: `synthDrivers.WorldVoice.driver` (`Voice`, `getVoiceKey`), `runtime.{engineControl, models, playbackWork, segmentHost, session}`, `text.arabic`, `text.chunker`, `driver.sonic._sonic`. `tests/test_plugin_voice_contract.py` passes unchanged. `driver/__init__.py` changes only its docstring and one relative import line.
- Never modify `driver/<Engine>/driver/`, `driver/sonic/`, `languageDetection/script_data.py`, `pipeline/unspaced_common_data.py`. Engine drivers stay independently installable. No Neural, no `ref` in commits.
- Dependency direction after the phase: `voices → bridge → runtime`, `driver → bridge.voiceFacade, runtime.*`, `languageDetection → locales`, `voices → locales`. `runtime/` imports nothing outside itself (unchanged); `locales.py` imports nothing.
- ruff pinned `==0.16.3`; files as prek leaves them.

## 5. Design

### 5.1 `bridge/`

```
bridge/
├── __init__.py            empty (git mv from compat/__init__.py)
├── commands.py            ← compat/commands.py
├── completionPolicies.py  ← compat/completionPolicies.py
├── engineAdapter.py       ← compat/engineAdapter.py
├── indexCodec.py          ← compat/indexCodec.py
├── indexLedger.py         ← indexLedger.py
├── nvdaEvents.py          ← nvdaEventBridge.py (the package name already says "bridge")
└── voiceFacade.py         ← compat/voiceFacade.py
```

Import changes:

- `bridge/indexLedger.py`: `from .runtime.…` → `from ..runtime.…` (two lines).
- `bridge/nvdaEvents.py`: `from .runtime.…` → `from ..runtime.…`; `from .indexLedger import IndexLedger` stays (same package now).
- `bridge/indexCodec.py`, `bridge/engineAdapter.py` (`TYPE_CHECKING` block): `from ..indexLedger import IndexLedger` → `from .indexLedger import IndexLedger`.
- `__init__.py`, `driver/__init__.py`, `voices/manager.py`: `compat.` → `bridge.`, `.indexLedger`/`.nvdaEventBridge` → `.bridge.indexLedger`/`.bridge.nvdaEvents`.

`runtime/completion.py:3` names "the index ledger, the event bridge" as prose; it names concepts, not paths, and stays.

### 5.2 `voices/`

```
voices/
├── __init__.py            empty (new)
├── catalog.py             ← voiceCatalog.py
├── mainLocalePolicy.py    ← mainLocalePolicy.py
├── manager.py             ← voiceManager.py
├── roles.py               ← roles.py
└── settingsRepository.py  ← configRepository.py
```

- Every relative import gains one level for modules outside `voices/` (`.runtime.…` → `..runtime.…`, `.bridge.…` → `..bridge.…`, `.locales` → `..locales`); imports inside the package (`.roles`, `.catalog`, `.mainLocalePolicy`) keep one dot with the new module names.
- `__init__.py` imports `from .voices.manager import VoiceManager` and `from .voices.settingsRepository import VOICE_CONFSPEC, ConfigVoiceSettingsRepository`.
- `globalPlugins/WorldVoice/rolePresenter.py:5`: `from synthDrivers.WorldVoice.voices.roles import prune_assignments`.
- `voices/__init__.py` re-exports nothing, as `bridge/__init__.py`: re-exports would make every submodule import load all of them.

### 5.3 `locales.primary_language` (A1)

```python
def primary_language(locale: str) -> str:
	if not locale:
		return locale
	return locale.replace("-", "_").split("_", maxsplit=1)[0].lower()
```

- The empty guard keeps `getPrimaryLocale`'s contract: `voices/roles.py` `ConfigRoleRepository.voice_for(language)` can get `None` — `pipeline/__init__.py:936` passes `cmd.lang or ctx.default_voice_language`, and NVDA types `VoiceInfo.language` as `str | None` (`ref/nvda/source/synthDriverHandler.py:111`, `:253-254`).
- On the detector side `get_primary_language(None)` raised `AttributeError`; `primary_language(None)` returns `None`. No detector caller passes `None` in practice: the languages come from `VoiceManager.allLanguages` (keys of `group_by_primary_locale`, which already maps locales through the roles helper) and `self.language`, whose voice metadata defaults to `"unknown"` (`driver/__init__.py:33`). For every `str` the result is identical (the two former implementations split at the first `-` or `_` and lower-case it).

  Decided by orchestrator with the recommended default; user may override before merge.
- The `replace`/`split` form is kept over `re.split` so `locales.py` imports nothing, not even `re`.

### 5.4 Docstrings

- `driver/__init__.py:1` becomes `"""Base class every engine wrapper (built-in or WorldVoice-workspace plugin) subclasses."""` followed by a paragraph stating the public import path (`synthDrivers.WorldVoice.driver`: `Voice`, `getVoiceKey`) and that the rest of the add-on may move but this path may not.
- `text/__init__.py` keeps its first line and adds that engine wrappers import `text.arabic` and `text.chunker` by absolute path, so the path is public API and the package stays where it is.

### 5.5 Tests and harnesses

- Path constants and dotted names follow §5.1/§5.2 in `tests/` (harnesses, `conftest.py`, guard tests).
- The `compat` fixture in `tests/conftest.py` (adapter + facade under the alias `worldvoice_compat_test`) is renamed to `bridge` with alias `worldvoice_bridge_test`; its users (`test_completion_characterization.py`, `test_f4_engine_session.py`, `test_runtime_legacy_adapter.py`, `test_runtime_voice_facade.py`, `test_voice_parameter_guards.py`) follow. `test_runtime_playback_context.py::test_models_load_without_nvda_or_compat` becomes `…_or_bridge`. Test ids change; the number of tests does not.
- `tests/runtime_harness.py::forbid_legacy_runtime_imports` forbids every `bridge` module except `indexLedger` and `nvdaEvents`. Today it forbids the `compat` segment while allowing the root `indexLedger` and `nvdaEventBridge` ("Ledger is pure Python; native may use it without importing any legacy boundary", `runtime_harness.py:341`); the native contract imports both under the guard (`runtime_harness.py:360`, `:499`). The rule keeps that split now that all three live in one package.
- `tests/test_runtime_scheduler.py:18` and `tests/test_runtime_request_builder.py:33` check `".bridge" not in name` instead of `".compat"`.
- `tests/test_completion_rules.py:112` allows `bridge/completionPolicies.py`.
- A1 tests (test first): new `tests/test_locales.py`.
  - `test_primary_language_is_the_first_subtag`: the union of the cases of `test_role_repository.py::test_primary_locale` and `test_language_detector.py::test_primary_language_is_the_first_subtag` plus `None`; those two tests move here (1 + 6 test items removed, 10 added).
  - `test_primary_language_matches_both_former_helpers` (Hypothesis): equals both former expressions for any text over `a Z - _ ß İ`.
  - `test_locales_imports_nothing`.
  - `test_no_other_module_defines_a_primary_language_helper`: an AST scan of the synth package finds only `locales.py:primary_language`.
  - `test_role_repository.py` loads `roles.py` inside an alias package (it now has a relative import).

Expected counts: baseline 3213 passed, 0 skipped; after the phase 3213 − 7 + 13 = 3219 passed, 0 skipped.

## 6. Settings, data, compatibility

No config key, confspec, stored value or UI string changes. A user upgrading from the previous build keeps every setting. An installed WorldVoice-workspace plugin keeps working: it imports only `synthDrivers.WorldVoice.driver`, whose names are unchanged.

## 7. Test plan

- Unit: §5.5; `tests/test_plugin_voice_contract.py` unchanged and green.
- Property (Hypothesis): `test_primary_language_matches_both_former_helpers`.
- Mutation: not needed — the only new logic is two lines whose equivalence the property test checks against both former expressions; the moved modules keep their tests.
- Full verification per DEVELOPMENT_WORKFLOW.md §7 after every commit.
- Windows/NVDA manual: none required (no behavior change). Not packaged, not verified on Windows.

## 8. Open questions

None. The one judgement call (the `None` case on the detector side, §5.3) uses the conservative default.
