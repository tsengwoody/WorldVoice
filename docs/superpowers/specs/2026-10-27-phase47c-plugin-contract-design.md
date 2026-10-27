# Phase 47c: rename the plugin contract

Date: 2026-10-27.
Base: `master` `b7aede2` (phase 47b merged). Branch: `phase47c-plugin-contract`.
Source: round-9 review `storage/refactor9.md` §6.1 (layered naming rule, "外掛契約" paragraph), §6 row **P47c**, §5.3 rows on `VoiceFacade.update_settings` and `driver.Voice`; the user's scope decisions of 2026-10-27 (relayed by the orchestrator); phase 47b spec `docs/superpowers/specs/2026-10-27-phase47b-host-names-design.md` §3 and its review `docs/superpowers/finish/2026-10-27-phase47b-host-names-review.md`.
Status: normal flow (DEVELOPMENT_WORKFLOW.md §3) with §3.2 "改名與搬移的證明": scripted renames from explicit `OLD=NEW` lists, one group per commit, each proven by an order-sensitive token check plus an AST and ordered-comments check.

Paths are under `addon/synthDrivers/WorldVoice/` unless stated; guard paths are relative to `addon/`.

## 1. Problem

`driver.Voice` is the public base class of every engine wrapper and of WorldVoice-workspace plugins (`driver/__init__.py:1-5`). It belongs to the NVDA host layer (refactor9 §6.1, package table), whose own names follow NVDA mixedCase, yet five of its members are snake_case: `synth_driver_class`, `extra_capabilities`, `drain_profile` (`driver/__init__.py:25-27`), `create_core` and `destroy_core` (`driver/__init__.py:86-92`). Its base `bridge/voiceFacade.VoiceFacade` adds `update_settings` (`bridge/voiceFacade.py:52`). Phase 47a's guard parks these six in `TRANSITIONAL_47C` (`tests/test_naming_layers.py:127-139`) until this phase, because renaming them breaks every plugin built against the old names: the one external plugin, Neural, assigns `synth_driver_class = SynthDriver` (`ref/Neural/Neural/__init__.py:8`).

## 2. Goals

1. Rename the six contract names to mixedCase with no alias and no compatibility layer (user decision 2026-10-27):

   | Old | New | Defined at |
   | --- | --- | --- |
   | `Voice.synth_driver_class` | `synthDriverClass` | `driver/__init__.py:25` |
   | `Voice.extra_capabilities` | `extraCapabilities` | `driver/__init__.py:26` |
   | `Voice.drain_profile` | `drainProfile` | `driver/__init__.py:27` |
   | `Voice.create_core` | `createCore` | `driver/__init__.py:87` |
   | `Voice.destroy_core` | `destroyCore` | `driver/__init__.py:91` |
   | `VoiceFacade.update_settings` | `updateSettings` | `bridge/voiceFacade.py:52` |

2. Every caller follows: `bridge/engineAdapter.py` (`VoiceClassAdapter.open` `:72`, `close` `:108`, `capabilities` `:112`), `bridge/completionPolicies.py` (`:8`, `:60`, `:80`, `:82`, `:120`), the six wrappers' `Voice` subclasses (`driver/Cerence/__init__.py:961-964`, `driver/Espeak/__init__.py:210-211`, `driver/OneCore/__init__.py:631-632`, `driver/RHVoice/__init__.py:431-432`, `driver/SAPI5/__init__.py:654-656`, `driver/VE/__init__.py:954-957`), `globalPlugins/WorldVoice/rolePresenter.py:76`, and the tests. `voices/` has no caller of these names (`git grep -w` over `voices/` finds none); the core reaches them only through `bridge/`.
3. Engine discovery skips a plugin whose `Voice` still has a pre-rename name and logs a clear error naming the plugin, the old name and its new name (§5).
4. `TRANSITIONAL_47C` is deleted; the guard keeps only `INTERFACE_NAMES` and `TRANSITIONAL_47D` (§6).
5. `tests/test_plugin_voice_contract.py` describes the renamed contract, and its real-Neural test passes against Neural with the one-line change of §7.

## 3. Non-goals

- Names that are already mixedCase stay: `applyEngineSettings`, `voiceInfoToMetadata`, `supportedSettings`, `getVoiceKey`, `loadParameter`, `variants`, `voices`, `ready`, `core` (refactor9 §6.1 "外掛契約").
- `engineRegistry/` is pending in the naming rule (`tests/test_naming_layers.py:76`): only the old-name check is added there; its own names (`load_enabled_engine_classes`, `EngineSpec.module_name`, …) are not renamed.
- Stored identifiers (`TRANSITIONAL_47D`, setting ids, config keys): phase 47d.
- Editing `ref/Neural` in the main checkout. The orchestrator applies the one-line change there at merge time (§7); before that, master's tests read the shared `ref` symlink.
- Test function names that contain an old name as part of a longer word (`test_settings_come_from_the_synth_driver_class` `tests/test_driver_voice_base.py:55`, `test_actual_outer_voice_and_core_select_enabled_drain_profiles` `tests/test_runtime_completion_policies.py:278`, `test_close_releases_adapter_state_even_when_destroy_core_fails` `tests/test_runtime_legacy_adapter.py:121`): tests are outside the naming rule (`tests/test_naming_layers.py:10-11`), and the words read as prose. *Decided with the recommended default; user may override before merge.*
- Vendored drivers, `driver/sonic/`, generated Unicode data: no occurrence of the six names exists there (`git grep` over `driver/*/driver/` and `driver/sonic/` finds none), so nothing to keep.

## 4. NVDA user's view

- With the bundled engines, nothing changes: no panel, label, translatable string, setting, setting id or config key changes.
- With Neural (or any WorldVoice-workspace plugin) built for the old contract: today, after the rename, such a plugin would still pass `ready()` (`driver/__init__.py:82-84`, true by default), be handed to the voice manager, and fail in `VoiceClassAdapter.open` when `createCore` calls `cls.synthDriverClass()` on the base's `None` (`bridge/engineAdapter.py:72`, `driver/__init__.py:88`); the voice manager logs `engine Neural on error` with a traceback and drops the engine (`voices/manager.py:93-99`). Its voices vanish from the list either way. With this phase, discovery skips it first and the NVDA log says why (§5), so the user sees the same missing voices and the log tells them to update the plugin.
- WorldVoice and Neural must be released together (refactor9 §6.1). After the one-line change of §7, Neural works as before.

## 5. Discovery: reporting a pre-rename plugin

`engineRegistry/discovery.load_enabled_engine_classes` (`engineRegistry/discovery.py:142-176`) imports each enabled engine module, looks up `Voice` (`:157`), skips a missing export with a warning (`:158-160`) or a `Voice.engine` mismatch with a warning (`:161-167`), calls `voice.ready()` (`:169-170`), and logs any exception as an error and skips the engine (`:174-175`). The returned classes go to `VoiceManager` (`__init__.py:242`, `engineRegistry/__init__.py:40-42`).

**Decision: skip the engine, with an error log.** *Decided with the recommended default (the orchestrator's brief); user may override before merge.* Loading it would only defer the failure to `createCore` with a less clear message (§4); `extraCapabilities` or `drainProfile` set under an old name would silently drop VE-style waitfactor/variant support or select LEGACY_DONE instead of DRAIN, since the bridge reads them with `getattr` defaults (`bridge/engineAdapter.py:112`, `bridge/completionPolicies.py:60`, `:80`, `:120`).

- A module-level table in `engineRegistry/discovery.py`, `PRE_RENAME_CONTRACT_NAMES: dict[str, str]`, maps each old name to its new name (the six pairs of §2).
- After the `Voice.engine` check and before `ready()`, inside the existing `try`: the old names `voice` has (`hasattr`, so a name inherited from a plugin's own helper base also counts; the base `Voice` no longer defines any). If any, log at error level and `continue`:

  `Skipping <engine> engine candidate: plugin uses the pre-rename contract name(s) synth_driver_class (now synthDriverClass); update the plugin`

  Several names are listed in the table's order, joined with `, `. `ready()` is not called for a skipped plugin.
- Log text is English, not translatable, like the other discovery messages (`engineRegistry/discovery.py:68-77`, `:159`, `:163-166`).
- Detected: names the plugin's `Voice` defines or inherits (class attributes and method overrides, e.g. `synth_driver_class = SynthDriver`, `def create_core(cls)`). Not detected: a plugin method that calls an old name (`self.update_settings(...)`), which raises `AttributeError` when it runs; Neural defines no methods (`ref/Neural/Neural/__init__.py:5-8`).
- A false positive would skip every engine (the base `Voice` is in each MRO) and the synth would fail with "No WorldVoice voices are available" (`voices/manager.py:89-90`). A test pins that the base `Voice` and the six bundled wrappers define none of the old names and that every new name exists on the base (§9).

## 6. Guard end state

`tests/test_naming_layers.py`:

- Each rename commit deletes its own entries from `TRANSITIONAL_47C` (deletion only), so `test_lists_hold_only_names_that_break_the_rule` (`:409-412`) stays green commit by commit.
- A separate commit then deletes `TRANSITIONAL_47C` and its comment (`:127-139`), drops it from `test_naming_follows_layer` and `test_lists_hold_only_names_that_break_the_rule` (`:401`, `:411`), renames `test_only_stored_identifiers_and_the_plugin_contract_wait` (`:415-436`) to `test_only_stored_identifiers_wait` and drops its `TRANSITIONAL_47C` assertion, and updates the docstring's closing paragraph (`:33-35`): one list, `TRANSITIONAL_47D`, waits for phase 47d and may only shrink. Rule 2's mention of `driver.Voice` as a readable base (`:15`) stays: the wrappers' overrides of `applyEngineSettings`, `variants` and the renamed members are exempt by inheritance.
- `INTERFACE_NAMES` is unchanged: every new name follows mixedCase, so none needs listing.

## 7. Neural

- `ref/Neural/Neural/__init__.py:8` changes from `	synth_driver_class = SynthDriver` to `	synthDriverClass = SynthDriver` (tab indent kept). Neural's driver package does not import WorldVoice (refactor9 §6.1), so no other line changes.
- Verification in the worktree uses a local overlay: the worktree's `ref` symlink is replaced by a directory holding a symlink to every entry of `/workspace/WorldVoice/ref/` except `Neural`, and a copy of `ref/Neural` with only that line changed. `ref` stays git-ignored and is never staged. The exact commands are in the plan (Task 1) and the ledger.
- `tests/test_plugin_voice_contract.py`: `PLUGIN_VOICE_ATTRIBUTES` (`:13`) becomes `{"core", "engine", "synthDriverClass", "extraCapabilities", "drainProfile"}`; the Neural-style fake (`:39-44`) assigns `synthDriverClass`; `test_reference_neural_plugin_uses_only_plugin_attributes` (`:66-84`) then fails against the unchanged Neural and passes against the overlay.

## 8. Docs

Root `readme.md` and `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` describe features, settings and the changelog for users; none names a contract member or explains how to write a WorldVoice-workspace engine plugin (`grep -niE "synth_driver|plugin|workspace|drain"` over the six files finds none; `readme.md:86-87` only says other engines need their own driver package). No readme or changelog edit. *Decided with the recommended default; user may override before merge* (a changelog line asking Neural users to update together could be added at release).

## 9. Test plan

- **Per rename task (red/green).** Delete the group's entries from `TRANSITIONAL_47C`; `test_naming_follows_layer` fails listing them; run the rename; it passes; the full suite stays at the baseline count, 0 skipped.
- **Neural.** With the overlay in place, `test_reference_neural_plugin_uses_only_plugin_attributes` fails before the `synth_driver_class` rename (Neural assigns a name outside `PLUGIN_VOICE_ATTRIBUTES`) and passes after it.
- **New tests:**
  - `tests/test_engine_discovery.py::test_plugin_with_old_contract_names_is_reported`, parametrized over the six old names: a `Voice` that defines the name (a class attribute or a classmethod/method) is not returned, `ready()` is not called, and the error line is exactly the §5 message with that name and its new name.
  - `tests/test_engine_discovery.py::test_old_contract_names_are_listed_together_and_inherited_ones_count`: a plugin whose `Voice` inherits `create_core` from a helper base and defines `drain_profile` is skipped with one error naming `drain_profile (now drainProfile), create_core (now createCore)` in table order; a sibling plugin with only new names loads.
  - `tests/test_plugin_voice_contract.py::test_pre_rename_names_map_onto_the_base_voice`: for each pair in `PRE_RENAME_CONTRACT_NAMES`, the base `Voice` lacks the old name and has the new one.
  - `tests/test_plugin_voice_contract.py::test_no_bundled_voice_defines_a_pre_rename_name`: the `class Voice` body of each of the six wrapper modules (read by AST) assigns or defines none of the old names.
- **Existing coverage** through the new names: composition and lifecycle (`test_runtime_composition.py`, `test_worldvoice_lifecycle.py`), adapter and completion (`test_runtime_legacy_adapter.py`, `test_runtime_completion_policies.py`, `test_runtime_voice_facade.py`), wrappers (`test_*_segment_drain.py`, `test_worldvoice_cancel_wrappers.py`, `test_native_strategy_guards.py`), UI (`test_role_presenter.py`, `test_f4_voice_state.py`), plugin contract (`test_plugin_voice_contract.py`), discovery and registry (`test_engine_discovery.py`, `test_engine_registry.py`).
- Full suite: baseline 3303 passed, 0 skipped; 3303 + 9 new test cases after the phase (6 parametrized + 3), 0 skipped, with the overlay in place.
- No mutmut: the only decision logic added is a membership test whose branches the new tests pin.
- Windows/NVDA: not verified on Linux. A manual check after release: with old Neural, the NVDA log shows the §5 line and the other engines load; with updated Neural, Neural voices are listed.

## 10. Proof of the renames

Scripts in the session scratchpad `p47c/` (copied from phase 47b's `p47b/` and recorded in the ledger): `ren.py` applies a group's rules by AST position; `check.py REV <group>` proves per file that the token streams differ only by the group's `OLD → NEW` pairs in order (or, when ruff re-wraps a line, that the ASTs and the ordered comments differ only so), counts every OLD left in HEAD against the group's `KEPT` table, and fails on any changed file outside the group except deletions in the guard; `prescan.py` lists every string, comment and outside-group occurrence of the OLD names before a rename. One group per commit: one contract name across all its files (`create_core`/`destroy_core` together), so each commit leaves the suite green. Every group's `KEPT` is empty: no same-spelled token exists outside the contract.

## 11. Open questions

None blocking. Defaults taken (user may override before merge):

1. Discovery skips a pre-rename plugin with an error log rather than loading it (§5). *Decided with the recommended default; user may override before merge.*
2. Test function names containing an old name as prose are not renamed (§3). *Decided with the recommended default; user may override before merge.*
3. No readme or changelog edit (§8). *Decided with the recommended default; user may override before merge.*
