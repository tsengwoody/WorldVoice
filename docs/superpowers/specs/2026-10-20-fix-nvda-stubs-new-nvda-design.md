# fix/nvda-stubs-new-nvda: test stubs for NVDA 7d25bc76e

Date: 2026-10-20.
Baseline: `master` (`5e1137b`). Branch: `fix/nvda-stubs-new-nvda`.
Status: auto flow (general flow, section 3 of `DEVELOPMENT_WORKFLOW.md`). This step is the spec only; no source or test change is made here.

The user moved the git-ignored NVDA source reference `ref/nvda` from `732d1ce2f` (2026-10-09) to `7d25bc76e` (2026-10-20, "Tell MSVC to compile NVDAHelper sources as UTF-8 (#21032)"). The same tree gives:

| `ref/nvda` | Result (`python3 -m pytest -q tests`, single process) |
| --- | --- |
| `732d1ce2f` | `1722 passed` (0 skipped) |
| `7d25bc76e` | `9 failed, 1601 passed, 112 errors` |

NVDA users hear or see nothing different from this fix: it changes one test stub. The NVDA change itself does reach WorldVoice users through code WorldVoice inherits; see "Product impact" below.

## 1. Cause

All 121 failing tests (9 failed + 112 errors) fail with the same exception; no failure has a second cause:

```
ImportError: cannot import name 'SequenceItemT' from 'speech.types' (unknown location)
ref/nvda/source/synthDrivers/oneCore.py:32
```

NVDA side. Between `732d1ce2f` and `7d25bc76e`, `source/synthDrivers/oneCore.py` (the only file under `source/synthDrivers/` that changed; `sapi5.py`, `_espeak.py` and `espeak.py` are unchanged) gained a OneCore single-character workaround:

- `ref/nvda/source/synthDrivers/oneCore.py:32`: `from speech.types import SpeechSequence, SequenceItemT` (was `SpeechSequence` only).
- `ref/nvda/source/synthDrivers/oneCore.py:45`: `CharacterModeCommand` is imported from `speech.commands`, and added to `OneCoreSynthDriver.supportedCommands` at `:207`.
- The old `_OcSsmlConverter.convertCharacterModeCommand` that returned `None` is removed, so `speechXml.SpeechXmlConverter.convertCharacterModeCommand` (`ref/nvda/source/speechXml.py:296-300`, `<say-as interpret-as="characters">`) applies.
- `ref/nvda/source/synthDrivers/oneCore.py:112-137`: new `_OcSsmlConverter.generateBalancerCommands` and `_fixSingleCharacters`, which yields `"\x1a"` after every `CharacterModeCommand(True)`. Their return annotations name `speechXml.XmlBalancerCommand` (new type alias, `ref/nvda/source/speechXml.py:107-115`) and `SequenceItemT`.

`SequenceItemT` itself is not new: it is defined at `ref/nvda/source/speech/types.py:22` in both NVDA versions. Only oneCore.py's import of it is new.

Test side. `tests/onecore_drain_harness.py:220` stubs the module as `module("speech.types", SpeechSequence=list)`, and `load_onecore` then executes the real NVDA file at `tests/onecore_drain_harness.py:249` (`load("synthDrivers.oneCore", NVDA / "source/synthDrivers/oneCore.py")`), so the `from ... import` fails. Every test that loads OneCore through `load_onecore` breaks:

| Group | Count | How it reaches `load_onecore` |
| --- | --- | --- |
| `tests/test_onecore_segment_drain.py` (all tests) | 75 errors | fixture `env`, `tests/test_onecore_segment_drain.py:39-43` |
| `tests/test_engine_segment_contract.py` `[OneCore]` params | 7 errors | fixture `engine` (`:76-79`) → `OneCoreAdapter.open`, `tests/engine_contract_harness.py:145` |
| `tests/test_runtime_drain_integration.py` (tests using fixture `composition`) | 30 errors | fixture `composition` (`:10-12`) → `assemble`, `tests/runtime_drain_integration_harness.py:223-224` |
| `tests/test_runtime_drain_integration.py::test_unsupported_profile_uses_legacy_from_first_segment` `[OneCore, VE, Cerence]` | 3 failed | `assemble(...)` in the test body, `:365-366` |
| `tests/test_runtime_completion_policies.py::test_six_enabled_profiles_use_shared_lifecycle` and `::test_disabled_force_switch_restores_legacy_done` `[OneCore, VE, Cerence]` | 6 failed | `load_installed_engine` (`:352-358`) → `assemble`, called in the test bodies at `:390` and `:419` |

The 9 "failed" differ from the 112 "errors" only in where the load happens: in the test body rather than in a fixture. The VE and Cerence parameters fail too because `assemble` loads OneCore unconditionally (`tests/runtime_drain_integration_harness.py:223-224`) before building the other engines.

The other names the new oneCore.py uses from stubbed modules do not break the load: `speechXml.XmlBalancerCommand` and `SequenceItemT` appear only in annotations, and Python 3.14 (the test interpreter, `Python 3.14.4`) evaluates annotations lazily. `CharacterModeCommand` is already in every `speech.commands` stub passed to `load_onecore` (`tests/onecore_drain_harness.py:209`, `tests/runtime_drain_integration_harness.py:220`). The harness's fake `speechXml.SsmlConverter` (`tests/onecore_drain_harness.py:183-188`), the base class of the real `_OcSsmlConverter` in the tests, has its own `convertToXml` that never calls `generateBalancerCommands`, so the new `_fixSingleCharacters` path is not run by the tests (see non-goals).

Other NVDA files the tests read were checked:

- `tests/test_native_strategy_guards.py:48,153` (sapi5.py, oneCore.py private names): pass; no private name WorldVoice relies on (`_OneCorePort.NVDA_PRIVATES`/`NVDA_OVERRIDES`, `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py:37-54`) changed.
- `tests/test_nvda_settings_copy.py:11` (`gui/settingsDialogs.py`): pass. `AutoSettingsMixin.updateDriverSettings` and `_updateValueForControl` are unchanged; the 39-line diff touches `onDiscard`, `refreshGui`, a browse-mode label and the profile check in `_doOnCategoryChange` (product notes in section 4).
- `tests/espeak_drain_harness.py:301,304`, `tests/sapi5_drain_harness.py:321`: those NVDA files are unchanged.

## 2. Goals and non-goals

Goals:

- The full suite passes against `ref/nvda` `7d25bc76e` with the baseline count (`1722 passed`, 0 skipped).
- The suite keeps passing against `732d1ce2f`. The user's `ref/` can lag behind or be ahead of a worktree's assumptions, and the fix costs nothing extra (see section 3). `Decided by orchestrator with the recommended default; user may override before merge`.

Non-goals:

- No product code change (open questions in section 6).
- No new test that runs the real `speechXml` through `_OcSsmlConverter` to check the `"\x1a"` insertion. That is NVDA's behaviour; WorldVoice only calls the converter (section 4.1).
- No refactor of how the drain harnesses stub `speech.types` (three separate stubs: `tests/onecore_drain_harness.py:220`, `tests/espeak_drain_harness.py:256`, `tests/test_say_all.py:42`). Only OneCore's needs the new name.
- Nothing under `ref/` is modified, staged or committed.

## 3. Fix

One line in `tests/onecore_drain_harness.py:220`:

```python
module("speech.types", SpeechSequence=list, SequenceItemT=object)
```

- `SequenceItemT` is only needed as an importable name; in NVDA it is `Union[SpeechCommand, str]` (`ref/nvda/source/speech/types.py:22`). The stub has no `SpeechCommand`, and nothing evaluates the annotation, so `object` is enough; `SpeechSequence=list` is stubbed the same loose way.
- Backward compatible: oneCore.py at `732d1ce2f` imports only `SpeechSequence`, and an extra attribute on the stub module is ignored.
- No other stub or harness changes. The fix belongs in the shared OneCore harness, so all five groups in section 1 recover through it.

Verified in a scratch copy of the tree (not committed): with this one line, `1722 passed` against `7d25bc76e` and `1722 passed` against `732d1ce2f` (the same 2 pre-existing `codecs.open` `DeprecationWarning`s from `addon/generics/speechSymbols/models.py:68,154` in both runs).

## 4. Product impact (findings, no change in this branch)

Product code was checked against the whole `source/` diff `732d1ce2f..7d25bc76e` (82 files, mostly locale `.po`/`.dic` files). The relevant changes:

### 4.1 OneCore character mode (inherited automatically)

WorldVoice already declares `CharacterModeCommand` in its own `supportedCommands` (`addon/synthDrivers/WorldVoice/__init__.py:88-96`), and `queue_speech_sequence` passes every command other than `SelectVoice`/`Pause` through to the engine unchanged (`addon/synthDrivers/WorldVoice/runtime/requestBuilder.py:36-52`). The OneCore wrapper converts with NVDA's own converters:

- correlated segments: `_OneCoreStrategy.prepare` builds `oneCore._OcSsmlConverter` / `_OcPreAPI5SsmlConverter` and calls `convertToXml` (`addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py:120-137`);
- ordinary speech: `SynthDriver.speak` calls the parent `speak` (`:234-237`), which converts the same way (`ref/nvda/source/synthDrivers/oneCore.py:330-339`).

So under NVDA `7d25bc76e`, a OneCore voice used through WorldVoice now speaks `CharacterModeCommand` spans as `<say-as interpret-as="characters">` with the `"\x1a"` workaround, the same as NVDA's own OneCore driver. Under earlier NVDA the command was dropped. This is a user-visible change (for example spelling with a OneCore voice), but it comes from NVDA and WorldVoice matches NVDA. `"\x1a"` is text, not a `<mark>`, so the wrapper's bookmark and drain handling is not affected. No WorldVoice change is needed; add a Windows manual check (section 5).

### 4.2 Settings panel `onDiscard`/`refreshGui` (inherited)

`WorldVoiceVoiceSettingsPanel` (`addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py:14`) inherits both from `AutoSettingsMixin` and calls `super().onDiscard()` (`:93-94`).

- New `onDiscard` (`ref/nvda/source/gui/settingsDialogs.py:1621-1628`) unbinds `EVT_CHOICE` for every created `<id>List` in `sizerDict` instead of only `supportedSettings`. WorldVoice creates controls for `allSupportedSettings` (`VoiceSettingsDialogs.py:133-148`), so hidden string controls are now unbound on Cancel too. This is harmless and matches what NVDA's comment intends.
- New `refreshGui` (`:1633-1646`) rebuilds the panel when the settings instance is a different object, not only after the old one is garbage collected, and then calls `Layout()`. It clears the sizer with `delete_windows=True` before calling `makeSettings`, so WorldVoice's extra punctuation-pause control (`VoiceSettingsDialogs.py:51-80`) is rebuilt, not duplicated. The `_pipelineSnapshot` taken in `makeSettings` (`:16`) is re-taken on that rebuild, as it already was on a GC-triggered rebuild.

No change is needed; add a Windows manual check (section 5). `tests/test_nvda_settings_copy.py` guards only the copied `updateDriverSettings` and the reviewed `_updateValueForControl`, both unchanged; there is no reason to start guarding these inherited methods.

### 4.3 MathCAT rate boost (no regression)

`ref/nvda/source/mathPres/MathCAT/speech.py:65-70` now multiplies the rate by `getattr(synth, "RATE_BOOST_MULTIPLIER", 1)` when `synth.isSupported("rateBoost") and synth.rateBoost`. WorldVoice exposes `rateBoost` when its default voice supports it (`addon/synthDrivers/WorldVoice/__init__.py:117-118`, `:431-435`) but has no `RATE_BOOST_MULTIPLIER` (only NVDA's `espeak.py:259` has one, value 3). Under WorldVoice with an eSpeak voice and rate boost on, MathCAT break lengths therefore stay unscaled, as they were for every synth before this NVDA change. This is not a regression; see open question 2.

### 4.4 No impact

- `speechXml.py`: `XmlBalancerCommand` alias and annotations only. The vendored RHVoice converter (`addon/synthDrivers/WorldVoice/driver/RHVoice/driver/__init__.py:431-441`, protected) overrides `generateBalancerCommands` with the same signature; nothing changes at runtime.
- `config/__init__.py` (`"magnifier"` in `BASE_ONLY_SECTIONS`), installer, `nvda_slave.pyw`, `inputGestures`, `virtualBuffers/gecko_ia2.py`, `winBindings/icu.py`, `comInterfaces_sconscript`, locale files: WorldVoice does not use them.
- `speech/`, `synthDriverHandler.py`, `nvwave.py`, `extensionPoints/`: unchanged in this range.

### 4.5 Comments that cite NVDA commits or lines

- `tests/test_nvda_settings_copy.py:13` (`ref/nvda 1406f9f8a: AutoSettingsMixin._updateValueForControl`) is still accurate: `1406f9f8a` is an ancestor of both NVDA versions, and the fingerprint of that method still matches at `7d25bc76e`. The comment records which reviewed version the fingerprint stands for, not the current ref. No change.
- `addon/synthDrivers/WorldVoice/_speechcommand.py:9-20` cites `speech/speech.py:1178-1180`, `speech/languageHandling.py:60-62` and `speech/manager.py:366-369, 95-105`, explicitly "line numbers from ref/nvda 1406f9f8a". `manager.py` and `languageHandling.py` are unchanged up to `7d25bc76e`. In `speech.py` the cited check moved to `:1185-1187` (header and docstring edits made between `1406f9f8a` and `732d1ce2f`, not in this pull); the code is the same. The citation is pinned to a commit, so it is not wrong; see open question 3.
- Harness docstrings that say "pinned NVDA" (`tests/onecore_drain_harness.py:1`, `tests/espeak_drain_harness.py:1`, `tests/sapi5_drain_harness.py:1`, `tests/test_sapi5_segment_drain.py:1`, `tests/test_espeak_segment_drain.py:53`) mean "the real NVDA file from `ref/`", not a commit. No change.

### 4.6 Note: tests depend on Python 3.14 lazy annotations

The fake `speechXml` module (`tests/onecore_drain_harness.py:221`) has no `SetAttrCommand` or `XmlBalancerCommand`, which oneCore.py names in annotations (`:95`, `:115`). The load works only because Python 3.14 does not evaluate annotations at definition time; on Python 3.13 it would fail with `AttributeError`. This was already true at `732d1ce2f` (`SetAttrCommand`). The tests already run on 3.14, so nothing changes here; noted for whoever runs the suite on another interpreter.

## 5. Test plan and verification

No new test: the 121 existing tests are the regression test for this fix (they fail now and pass with it).

In the worktree (`ref` → new NVDA `7d25bc76e`), single process, with the memory monitor that stops pytest below 3 GB MemAvailable (another agent may run tests at the same time):

- `python3 -m pytest -q tests`: `1722 passed`, 0 skipped (baseline at `732d1ce2f`: `1722 passed`, 0 skipped).
- Against old NVDA `732d1ce2f`: run from a scratch copy of the tree whose `ref` symlink points at the read-only checkout `/tmp/claude-0/-workspace-WorldVoice/4475b454-b750-4bfd-b046-7aad0fdefc9c/scratchpad/ref-prev`. Do not repoint the worktree's own `ref` symlink. Expect `1722 passed`, 0 skipped.
- `prek run --all-files`: all hooks Passed (ruff `0.16.3`).
- `git diff --check`.
- Protected paths, both empty:

  ```bash
  git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py
  git ls-files addon/synthDrivers/WorldVoice/driver/Neural
  ```

- `git status` shows no `ref` entry staged; `git diff --stat master` lists only `tests/onecore_drain_harness.py` and this spec.
- mutmut: not needed (no core decision module is touched).

Windows/NVDA manual items (not verifiable on Linux; for the user on NVDA built from `7d25bc76e` or later):

1. WorldVoice with a OneCore voice: spell a word with the review cursor (Numpad 5 pressed twice) and move by character (Numpad 1 and 3). Expect the same character pronunciation as NVDA's own OneCore driver, and index/caret tracking in say-all unchanged.
2. WorldVoice voice settings panel: open it, change a combo (for example variant), press Cancel; switch synthesizer while NVDA settings are open, then return to the Voice panel. Expect no exception in the log and no duplicated "Punctuation pause characters" field.

## 6. Open questions

1. **Keep passing against `732d1ce2f`?** Recommended: yes; the fix does not depend on the NVDA version. `Decided by orchestrator with the recommended default; user may override before merge`.
2. **Expose `RATE_BOOST_MULTIPLIER` on WorldVoice for MathCAT (section 4.3)?** Options: (a) no change (recommended): not a regression, it affects only math breaks with eSpeak and rate boost, and a correct value would have to follow the current default voice's engine; (b) a separate `fix/` branch adding a property that returns the default voice engine's multiplier (eSpeak 3, others 1). `Decided by orchestrator with the recommended default; user may override before merge`.
3. **Refresh the `1406f9f8a` line citations in `addon/synthDrivers/WorldVoice/_speechcommand.py:9-20` (section 4.5)?** Recommended: no; they are pinned to a commit and still true there, and this pull did not touch `speech/`. A later docs pass can re-pin them all to one newer commit. `Decided by orchestrator with the recommended default; user may override before merge`.
4. **OneCore character mode now reaches WorldVoice users (section 4.1).** User-visible, but it comes from NVDA and makes WorldVoice match NVDA's own OneCore driver. Recommended: accept, no WorldVoice change, confirm with manual item 1. Stripping `CharacterModeCommand` for OneCore in the wrapper would bring back the behaviour NVDA just fixed. `Decided by orchestrator with the recommended default; user may override before merge`.

## 7. Flow

This does not meet the complex-flow criteria (`DEVELOPMENT_WORKFLOW.md` section 4.0). The plan is not handed to anyone else to run, no byte-exact restoration or build change is involved, and the change is a single line in one test harness. General flow; the plan and implementation can be one short step.
