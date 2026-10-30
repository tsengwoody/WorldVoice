# Keep other engines' speech roles ("keep, don't apply")

Date: 2026-10-30.
Base: `master` `031ff3d` (voice engine filter merged). Branch: `fix/keep-other-engine-roles`. Normal flow (DEVELOPMENT_WORKFLOW.md §3); not the complex flow: no byte-exact target, no handed-off plan.
Source: the voice engine filter's Q5/D10 (`docs/superpowers/specs/2026-10-30-voice-engine-filter-design.md` §3.7) and the user's decision of 2026-10-30.

| Item | Decision |
|---|---|
| U1: a main-voice change never deletes locale roles; `on_keep_engine_consistent` stops pruning | Decided by the user (2026-10-30) |
| U2: at lookup, with "keep main engine and locale engine consistent" on, a role voice of another engine than the main voice is skipped (as if unassigned → main voice); a role voice that no longer exists is skipped too, and both stay stored | Decided by the user (2026-10-30) |
| U3: Speech Role panel OK writes only the locales the user changed: a chosen voice overwrites, "no-select" removes; untouched locales, other engines' roles included, are kept; no prune on save | Decided by the user (2026-10-30) |
| U4: "keep main speech role and locale speech role consistent" still overwrites the main locale's role with the new main voice (per-engine role storage would need a config migration) | Decided by the user (2026-10-30) |
| D1: the lookup reads the saved engine-consistency flag, not the Speech Role panel's unsaved checkbox (§3.2) | Decided by orchestrator with the recommended default; user may override before merge |
| D2: a skipped role at the full-locale key (`zh_TW`) falls through to the primary-language key (`zh`), as an unassigned key does today (§3.2) | Decided by orchestrator with the recommended default; user may override before merge |
| D3: the voice the synth reports before NVDA sets one (`_voice is None`) keeps today's rule: the interface language's available role voice of any engine (§3.4) | Decided by orchestrator with the recommended default; user may override before merge |
| D4: ~~nothing stored is cleaned up any more, also not roles at non-primary (pre-2026-07 legacy) keys~~ (review I1). One-time install-time cleanup: on an update, `installTasks.onInstall` removes the role sections under keys with `_` or `-` (`zh_TW`, `pt-br`) and keeps primary keys and non-section values; roles whose voice sits in another locale's list are kept. Limits: only the configuration active at install time is cleaned (normally the normal configuration; other profiles are not touched), and it relies on NVDA saving the config on exit; a failure is logged and the install goes on (§3.5) | Decided by the user (2026-10-30): one-time install-time cleanup |
| D5: the engine switch's voice pick (`voice_name_for_engine`) keeps its order; with the roles kept it now brings back the interface language's role voice of the chosen engine; like the lookup (D2) it skips a full-locale role of another engine to the primary role (review M1) (§3.3) | Decided by orchestrator with the recommended default; user may override before merge |
| D6: `prune_assignments`, `ConfigRoleRepository.prune` and `VoiceManager.on_keep_engine_consistent` become unused and are removed (§3.6) | Decided by orchestrator with the recommended default; user may override before merge |

Line conventions (all under `addon/synthDrivers/WorldVoice/` unless stated): `synth:` is `__init__.py`; `manager:` `voices/manager.py`; `roles:` `voices/roles.py`; `policy:` `voices/mainLocalePolicy.py`; `filter:` `voices/engineFilter.py`; `catalog:` `voices/catalog.py`; `presenter:` is `addon/globalPlugins/WorldVoice/rolePresenter.py`; `role.py:` `addon/globalPlugins/WorldVoice/panels/role.py`; `sdh:` `ref/nvda/source/synthDriverHandler.py`.

## 1. Problem, goals, non-goals

### Problem

`keepMainLocaleEngineConsistent` defaults to on (`confspec.py:20`). Every main-voice change goes through the `default_voice_name` setter (`manager:189-196`), which calls `on_keep_engine_consistent` (`manager:195`, `:246-247`) → `roles.prune(locale_to_voices_map)` (`roles:66-67`) → `prune_assignments` (`roles:9-18`), which keeps only roles whose locale and voice are in the *visible* table (`manager:296-297`, `:303-305`, `policy:35-39`) and rewrites `config["WorldVoice"]["role"]` (`roles:53-61`). With the flag on, every role of another engine is deleted; with it off, every role whose voice is not installed is deleted (the setter prunes regardless of the flag). Switching back or Cancel (NVDA's `loadSettings` restores only the voice, `sdh:386-399`) never restores them, and NVDA saves the config on exit. The Speech Role panel's OK prunes too (`presenter:126-136`).

The engine filter's "Speech engine" combo box switches the main voice on every arrow step (`synth:446-453`), so browsing engines now deletes the user's per-language voices.

### Goals

- U1–U4 above.
- Switching back to the engine (combo box, Voice list, profile switch, Speech Role panel) makes its kept roles speak again; Cancel loses nothing.
- With `keepMainLocaleEngineConsistent` off, roles of any engine speak, as today.

### Non-goals

- No per-engine role storage, no config migration, no confspec change (U4).
- No change to `VoiceConsistency.follow` (`policy:63-65`), the engine-switch pick (`filter:111-137`, D5), the visible lists of the Speech Role and detection panels (`manager:296-309`, `addon/globalPlugins/WorldVoice/panels/detection.py:29-30`), or language detection (`synth:285`, `manager:292-294`, every engine's languages).
- No UI string change.
- No change to inner drivers, wrappers, sonic or generated Unicode data.

### What NVDA users hear and see

- Arrowing through "Speech engine" in the Voice panel, choosing another engine's voice, or a configuration profile switch to another engine's voice no longer deletes the locale speech roles. While the main voice is engine B's, a language whose role is engine A's voice is read by the main voice — the same sound as today after the deletion.
- Switching back to engine A: those languages are read by their A voices again. Cancel in the Voice panel after browsing engines: every role is as before (with "keep main speech role and locale speech role consistent" on, the main locale's role is reassigned to the restored main voice, so it is also as before).
- A role whose engine is disabled or uninstalled is kept and speaks again when the engine comes back (today it is deleted at the next main-voice change, also with the engine option off).
- Speech Role panel with the engine option on: a locale whose role is another engine's voice shows "no-select", like an unassigned locale; OK keeps that role unless the user changes that locale. With the option ticked off in the panel, the stored voice shows as selected.
- Known limit (U4): with "keep main speech role and locale speech role consistent" on (default), the main locale's role always follows the main voice, so it is not kept per engine.

## 2. Findings: who reads the roles

- **Speech** asks `SpeechContext.voice_name_for_language` (`synth:379-392` → `manager:311-315`) per language command (`pipeline/languageCommands.py:45`, `:60`, `:86`); `voice_locale_for_language` (`manager:317-320`) follows the same voice for symbol names (`pipeline/numberStages.py:340`, `pipeline/symbols.py:87`). Today `get_voice_name_for_language` uses the role voice when it is in `voice_infos`, else the main voice (`manager:311-315`); there is no engine check, because pruning kept only main-engine roles.
- **`roles.voice_for`** tries the full locale, then the primary language, and returns the first non-empty voice (`roles:34-42`). Panel and follow write only primary keys (`catalog:16-20`, `policy:60-65`); full-locale keys come only from versions before `78f3880` (2026-07-28), whose follow also wrote `zh_TW`-style keys.
- **Engine switch** `voice_name_for_engine` → `pick_engine_voice(table, engine, language, roles.voice_for(language))` (`manager:288-290`); the role voice wins only when it is a voice of the target engine (`filter:127-128`). The engine filter spec noted this step "only matters with that option off" because of pruning (`docs/superpowers/specs/2026-10-30-voice-engine-filter-design.md:114`); with roles kept it now restores the role voice on switching back (D5).
- **Before NVDA sets a voice** `_get_voice` returns `get_voice_name_for_language(getLanguage())` while `_voice is None` (`synth:455-458`): the first session with no saved voice (NVDA's confspec has no `voice` default, `ref/nvda/source/config/configSpec.py:55-59`; `loadSettings` then calls `changeVoice(self, None)`, which sets nothing, `sdh:390-393`, `:442-443`) and the repair after an invalid saved voice (`sdh:394-399`). There the main voice is still the provisional `_get_default_voice_spec` voice (`manager:209-214`).
- **Main-locale follow** `roles.assign` (`roles:63-64`, `policy:63-65`) saves all assignments plus one; it never deleted.
- **Speech Role panel**: `voices()` lists the visible voices of a locale (`presenter:42-48`); `selectedVoice` returns the pending or the stored voice (`presenter:50-53`); the panel selects index 0 ("no-select") when that voice is not listed (`role.py:177-185`) without firing `EVT_CHOICE`, so nothing becomes pending; only a user choice calls `selectVoice` (`role.py:216-223`). The engine checkbox only previews the visible lists (`presenter:88-91`, `role.py:231-237`). `apply` merges `_pending` into the stored assignments, then saves them pruned against the visible table after writing the flags (`presenter:126-136`). Nothing else assumes every stored role is visible.
- **Other users of `prune`/`prune_assignments`**: only `manager:247` and `presenter:6`, `:136`. Settings repository and transactions (`voices/settingsRepository.py`, `runtime/voiceSettings.py`) do not touch `["role"]`; `ConfigRoleRepository` is its only reader and writer (`roles:25-32`).
- **Tests asserting pruning**: `tests/test_role_repository.py:58-61`, `tests/test_voice_manager_roles.py:40-43`, `tests/test_role_presenter.py:131`; `tests/test_voice_manager_roles.py:52-57` expects another engine's role (`B:b`) to speak with the engine flag on (its `make_manager` default), which U2 reverses.

## 3. Design

### 3.1 Policy (`policy:14-39`)

`EngineConsistency.admits(engine: str, default_engine: str) -> bool`: `True` when the *saved* flag is off or `engine == default_engine` (D1). `visible` keeps using the preview.

### 3.2 Lookup (`roles:34-42`, `manager:311-323`)

- `ConfigRoleRepository.voice_for(language, usable=<always true>)`: the stored voice of the first key among (full locale, primary language) whose voice is non-empty **and** `usable(voice)`; `None` otherwise. Without `usable` it behaves as today. A key whose voice is skipped counts as unassigned, so the next key is tried (D2).
- `VoiceManager.get_voice_name_for_language(language)`: `roles.voice_for(language, usable)` where a voice is usable when it is in the catalog and `engine_consistency.admits(its engine, the main voice's engine)` (the main voice's engine as `_visible_table` reads it, `manager:296-297`); else the main voice. `get_voice_locale_for_language` follows unchanged.

### 3.3 Main-voice change (`manager:189-196`, `:246-247`)

The setter no longer calls `on_keep_engine_consistent`; the method is removed (D6). It still calls `on_keep_main_locale_voice_consistent` (U4). `voice_name_for_engine` passes an engine check to `voice_for`, so a full-locale role of another engine falls through to the primary role, as in D2 (review M1).

### 3.4 Before NVDA sets a voice (`synth:455-458`)

New `VoiceManager.initial_voice_name(language) -> str`: `roles.voice_for(language, usable)` with usable = in the catalog (any engine), else the main voice — today's rule. `_get_voice` calls it while `_voice is None`. Reason (D3): the main voice is not chosen yet, so there is no engine to be consistent with; the role voice is the user's choice for that language, as today. Applying U2 here would instead pick the provisional voice of whichever engine sorts first, e.g. after a removed main voice.

### 3.5 Speech Role panel apply (`presenter:120-136`)

`apply` saves the stored assignments with `_pending` applied (voice → set, `""` → remove) and nothing pruned; the `prune_assignments` import goes. Order otherwise unchanged (edit apply first; a failure leaves roles and flags unsaved, `tests/test_role_presenter.py:200-221`). No cleanup runs at a main-voice change or on save. ~~No other cleanup runs anywhere (D4)~~: legacy full-locale keys, which the old prune removed and which would otherwise keep shadowing the panel's primary role (review I1), are removed once when the add-on is updated (`addon/installTasks.py` `_removeLegacyRoleKeys`, D4); roles whose voice sits in another locale's list are kept.

### 3.6 Dead code (D6)

Remove `prune_assignments` (`roles:9-18`), `ConfigRoleRepository.prune` (`roles:66-67`), `VoiceManager.on_keep_engine_consistent` (`manager:246-247`) and their tests; `tests/test_role_presenter.py:29-34` stubs `voices.roles` only for the presenter's import and goes too. Update the `EngineConsistency` docstring (`policy:15`).

## 4. Edge cases

- Engine round trip A → B → A with the engine option on, "keep main speech role" off: B shows/speaks no A roles; back on A every A role speaks; config unchanged throughout.
- Same with "keep main speech role" on: as above, except the main locale's role follows each main voice (U4); a Cancel back to the original voice restores it too.
- Role voice of a removed voice: skipped, main voice speaks; stored; speaks again once the voice is back (new catalog).
- Engine option off: any engine's available role speaks (unchanged); toggling the option on in the panel changes only the lists until OK, then other engines' roles are skipped; off again → they speak again.
- Explicit "no-select" for a locale in the panel removes it, also when the stored role is another engine's (reachable with the option unticked in the panel, or by choosing a voice and then "no-select").
- Profile switch to a profile whose voice is another engine's: no role write any more (the old prune wrote into the active profile's `role` section).
- Main voice of another engine than a full-locale legacy key: D2 falls through to the primary key.

## 5. Panel layout and strings

No layout, focus or string change; no translation update.

## 6. Settings, data, compatibility

- No confspec change, no migration. Existing configs keep whatever the old prune left; from now on nothing is deleted except by an explicit "no-select".
- Rolling back to an older WorldVoice: its prune runs at the next main-voice change, as before.
- Errors: none new; `voice_for` with a predicate cannot raise for a missing voice (it checks the catalog).

## 7. Tests

Every behaviour test is written red first. Baseline: 3680 passed, 0 skipped.

### Unit (Linux)

- `tests/test_main_locale_policy.py`: `admits` is true for the same engine, false for another with the flag on, true for any with the flag off; the preview does not change it.
- `tests/test_role_repository.py`: `voice_for` with a predicate skips a rejected full-locale voice and returns the primary key's; rejects both → `None`; without a predicate unchanged; the prune test goes.
- `tests/test_voice_manager_roles.py`: with the flag on another engine's role is skipped and a same-engine role speaks; with it off any available role speaks; a missing voice is skipped and comes back when the catalog has it again; lookup never writes config; `initial_voice_name` returns another engine's available role and falls back to the main voice for a missing one; Hypothesis: for random roles over two engines plus missing names and random main voices, the result is the main voice or an available voice of the main engine (flag on), and the role section is never changed by lookups or by main-voice changes with "keep main speech role" off.
- Composition (`tests/test_runtime_composition.py` or `tests/test_voice_manager_roles.py` on the `composition` fixture): engine round trip through `default_voice_name` keeps the roles and restores the speaking voice; with "keep main speech role" on only the main locale changes; `voice_name_for_engine` brings back the interface language's role voice when switching back (D5).
- `tests/test_engine_setting.py`: `_get_voice` before `loadSettings` reads `initial_voice_name` (fake renamed).
- `tests/test_role_presenter.py`: with the engine option on, OK keeps an untouched other-engine role; a chosen voice overwrites; `""` removes; ticking the option on and OK keeps the other-engine role (replaces `:131`); `selectedVoice` returns the stored other-engine voice.
- `tests/test_role_panel_ui.py`: a locale whose stored voice is not listed shows "no-select", disables the sliders and calls nothing.

### Mutation

`voices/roles.py` joins `[tool.mutmut] source_paths` (`pyproject.toml:45-65`); `mainLocalePolicy.py` is already there. `manager.py`'s lookup methods are mutated on a scratch copy (≤ 3 children, memory guard); surviving mutants are recorded in the plan ledger and the review.

### Windows / NVDA manual checklist (not verifiable on Linux)

1. Engines OneCore and eSpeak, engine option on, "keep main speech role" off: assign an English role (OneCore) and a German role (OneCore); main voice OneCore. Arrow "Speech engine" to eSpeak: English/German text is read by the eSpeak main voice. Arrow back to OneCore: English/German text uses the role voices again. Restart NVDA: still there.
2. Same, then press Cancel while eSpeak is shown: roles intact, OneCore voice back.
3. Speech Role panel while the main voice is eSpeak: English shows "no-select"; press OK; switch to OneCore: English role still speaks.
4. In that panel, untick the engine option: English shows its OneCore voice; choose "no-select", OK: the role is gone.
5. Disable an engine with roles in the Speech Engine panel (restart), then enable it again (restart): its roles speak again.
6. "Keep main speech role" on (default): browsing engines and back keeps the other locales' roles; the main locale's role follows the main voice.

## 8. Readme

Only `addon/doc/zh_TW/readme.md` (user's docs scope, 2026-10-30: root `readme.md` and `addon/doc/{ru,uk,zh_CN,zh_HK}/readme.md` are synced in a later translation pass once zh_TW is final; not `addon/doc/en/` or `.html`). Concise, user-facing:

- Rewrite the 「保持主要語音引擎與地區語音引擎一致」 bullet (`addon/doc/zh_TW/readme.md:27`): only the main engine's voices can be chosen and only its locale roles speak; other engines' locale roles are kept, read by the main voice and shown as unselected in the panel while another engine is the main one, and used again when switching back; OK in the panel changes only the locales the user changed.
- 「下一版更新」 (`addon/doc/zh_TW/readme.md:93-95`), right after the engine list bullet: **保留其他語音引擎的語音角色**: switching engines no longer deletes the previous engine's locale roles; they come back when switching back; browsing the engine list or Cancel loses nothing; a disabled engine's roles are kept too.

## 9. Constraints

- Stage explicit paths only; `git diff --cached --stat` before each commit; English `<type>: <summary>` with a body, no `Co-Authored-By`; prek hooks run on commit (ruff `==0.16.3`), never `--no-verify`; no push; no `git stash`; do not touch the main checkout.
- Never edit `driver/*/driver/*`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; do not add Neural; `ref` is a symlink, never staged.
- Engine drivers stay independently installable (no wrapper touched); the change is core (`voices/`), the synth and the global plugin.
- Naming: `voices/` is core (snake_case: `admits`, `initial_voice_name`, `usable`); presenter and synth keep their mixedCase.

## 10. Questions

- Q1 (D1) Lookup with the panel's unsaved engine checkbox: saved flag. Decided by orchestrator with the recommended default; user may override before merge.
- Q2 (D3) Voice before NVDA sets one: today's rule, any engine. Decided by orchestrator with the recommended default; user may override before merge.
- Q3 (D4) Legacy-key cleanup: ~~none~~ one-time cleanup at install time (review I1). Decided by the user (2026-10-30).

## 11. Verification

`python3 -m pytest -q tests` (passed/skipped vs 3680/0), `prek run --all-files`, `git diff --check`, the protected-path checks of DEVELOPMENT_WORKFLOW.md §7 (no output), mutmut as in §7. Linux tests cover the controlled NVDA and wx boundaries only; NVDA on Windows and real engines are verified only by §7's manual checklist.
