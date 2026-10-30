# Keep Other Engines' Speech Roles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** A main-voice change (engine list, Voice list, profile switch, Speech Role panel) never deletes locale speech roles; with "keep main engine and locale engine consistent" on, a role of another engine (or of a missing voice) is skipped at lookup and kept, so it speaks again after switching back (U1–U4).

**Architecture:** The decision moves from write time (prune) to read time. `EngineConsistency.admits` (core policy) says whether a role voice's engine may speak beside the main voice; `ConfigRoleRepository.voice_for` takes a `usable` predicate and skips rejected keys; `VoiceManager.get_voice_name_for_language` combines them; `initial_voice_name` keeps today's any-engine rule for the voice the synth reports before NVDA sets one. The main-voice setter and the Speech Role presenter stop pruning; the prune code is removed.

**Tech Stack:** Python 3 (NVDA add-on), pytest + Hypothesis, mutmut 3.8.0, ruff 0.16.3 via prek.

**Spec:** `docs/superpowers/specs/2026-10-30-keep-other-engine-roles-design.md` (commit `d5596f6`).

## Global Constraints

- No confspec change, no migration, no UI string change (so no `.po` update); nothing stored is deleted except by an explicit "no-select" in the Speech Role panel (spec D4).
- The lookup reads the saved flag `EngineConsistency.enabled`, never `preview` (D1); `visible` keeps its preview behaviour.
- `VoiceConsistency.follow` (`policy:63-65`) and `pick_engine_voice` (`filter:111-137`) unchanged (U4, D5).
- `voices/` is core: snake_case names (`admits`, `usable`, `initial_voice_name`); presenter and synth keep mixedCase (`tests/test_naming_layers.py`).
- Never modify `driver/*/driver/*`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; never add Neural; `ref` is a symlink, never staged.
- Engine drivers stay independently installable: no wrapper is touched; shared code only in core.
- ruff pinned `==0.16.3`; prek hooks run on commit (re-stage and recommit if a hook rewrites files; never `--no-verify`); explicit `git add` paths, `git diff --cached --stat` before each commit; English `<type>: <summary>` + why-body; no `Co-Authored-By`; no push; no `git stash`; do not touch `/workspace/WorldVoice`; at most 3 pytest workers with a MemAvailable ≥ 3 GB guard (serial is fine).
- Docs: only `addon/doc/zh_TW/readme.md` (user, 2026-10-30; the other readmes are synced in a later translation pass; never `en/` or `.html`).

## Review Focus

1. **Engine round trip A → B → A** (arrowing the engine list with the engine option on, "keep main speech role" off and on): no role is deleted on the way, B never speaks A's roles, back on A they speak again, and after the round trip the role section equals the original — Task 5 `test_an_engine_round_trip_keeps_and_restores_the_roles[False/True]`.
2. **Role of a removed voice** (engine disabled or voice uninstalled): skipped while missing, still stored, speaks again once the catalog has it — Task 3 `test_a_missing_role_voice_is_kept_and_speaks_when_back`; Hypothesis `test_lookups_never_write_and_speak_only_admitted_voices`.
3. **Speech Role panel OK with an untouched other-engine role** (engine option on, the locale shows "no-select"): OK keeps it; ticking the engine option on and OK keeps it; an explicit "no-select" removes it — Task 6 `test_apply_keeps_an_untouched_role_of_another_engine`, `test_engine_consistency_preview_cancel_and_apply`, `test_apply_writes_only_the_changed_locales`; panel side `test_a_stored_voice_the_locale_does_not_list_shows_no_select`.
4. **Legacy full-locale key of another engine** (`fr_CA` → B, `fr` → A, main A): the primary key speaks, not the main voice (D2) — Task 2 `test_voice_for_skips_an_unusable_voice_to_the_primary_locale`, Task 3 `test_a_skipped_full_locale_role_falls_back_to_the_primary_role`.
5. **Voice before NVDA sets one** (`_voice is None`, engine option on, the interface language's role belongs to another engine than the provisional main voice): the synth still reports the role voice, as today (D3) — Task 4 `test_initial_voice_is_the_available_role_of_any_engine`, `tests/test_engine_setting.py::test_before_load_settings_the_engine_follows_the_role_voice`.

Baseline (worktree at `031ff3d`): **3680 passed, 0 skipped**; prek all Passed; protected paths clean.

---

### Task 1: `EngineConsistency.admits`

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voices/mainLocalePolicy.py` (`EngineConsistency`, `:14-39`)
- Test: `tests/test_main_locale_policy.py`

**Interfaces:**
- Consumes: `EngineConsistency.enabled` (saved flag).
- Produces: `EngineConsistency.admits(engine: str, default_engine: str) -> bool` — `not self.enabled or engine == default_engine`; ignores `preview`.

- [ ] **Step 1: Write the failing test** `test_engine_consistency_admits_other_engines_only_when_saved_off`: `conf = flags(engine=True)`; `policy.admits("A", "A") is True`; `policy.admits("B", "A") is False`; `policy.preview = False` → `admits("B", "A") is False` (D1); `policy.preview = None; policy.enabled = False` → `admits("B", "A") is True`; `policy.preview = True` → still `True`.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_main_locale_policy.py` — Expected: 1 failed, `AttributeError: 'EngineConsistency' object has no attribute 'admits'`.
- [ ] **Step 3: Implement** `admits` with a one-line docstring (the lookup's rule, spec §3.1); update the class docstring (`:15`): role choices come from the main voice's engine and only its roles speak; other engines' roles are kept.
- [ ] **Step 4: Run** the file → PASS; full suite → **3681 passed, 0 skipped**.
- [ ] **Step 5: Commit** `voices/mainLocalePolicy.py tests/test_main_locale_policy.py`: `feat: let engine consistency judge a role voice's engine`.

### Task 2: `voice_for` skips unusable voices

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voices/roles.py` (`voice_for`, `:34-42`)
- Modify: `pyproject.toml` (`[tool.mutmut] source_paths`, `:45-65`)
- Test: `tests/test_role_repository.py`

**Interfaces:**
- Produces: `ConfigRoleRepository.voice_for(language: str, usable: Callable[[str], bool] | None = None) -> str | None` — the voice of the first key of (`language`, `primary_language(language)`) whose voice is non-empty and (`usable is None` or `usable(voice)`); a rejected key counts as unassigned (D2).

- [ ] **Step 1: Write the failing tests**
  - `test_voice_for_skips_an_unusable_voice_to_the_primary_locale`: add `zh_TW` → `C:tw`; `voice_for("zh_TW", lambda voice: voice != "C:tw") == "B:zh"`; `voice_for("zh_TW", lambda voice: voice == "C:tw") == "C:tw"`.
  - `test_voice_for_is_none_when_no_voice_is_usable`: `voice_for("zh_TW", lambda voice: False) is None`; the predicate is asked only for stored voices: record its arguments for `voice_for("ja", ...)` → `[]` (section without voice).
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_role_repository.py` — Expected: 2 failed, `TypeError: ... voice_for() takes 2 positional arguments but 3 were given`.
- [ ] **Step 3: Implement** the parameter; docstring states the order and the skip. Add `"addon/synthDrivers/WorldVoice/voices/roles.py"` to `source_paths` after `mainLocalePolicy.py`.
- [ ] **Step 4: Run** the file → PASS; full suite → **3683 passed, 0 skipped**.
- [ ] **Step 5: Commit** `voices/roles.py tests/test_role_repository.py pyproject.toml`: `feat: let the role lookup skip voices that may not speak`.

### Task 3: Lookup skips other engines' and missing role voices

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voices/manager.py` (`get_voice_name_for_language`, `_get_configured_voice_name_for_language`, `:311-323`; new private predicate)
- Test: `tests/test_voice_manager_roles.py`

**Interfaces:**
- Consumes: Task 1 `admits`; Task 2 `voice_for(language, usable)`; `catalog.by_name`; `_default_voice_instance.engine` (as `_visible_table`, `:296-297`).
- Produces: `VoiceManager._may_speak(name: str) -> bool` — in `catalog.by_name` and `engine_consistency.admits(spec.engine, self._default_voice_instance.engine)`; `_get_configured_voice_name_for_language(language)` → `self.roles.voice_for(language, self._may_speak)`; `get_voice_name_for_language(language)` → that, else `default_voice_name`.

- [ ] **Step 1: Write the failing tests** (`make_manager`: roles `fr` → `B:b`, `en` → `X:gone`; catalog `A:a en_US`, `B:b fr`, `A:c fr`; main `A:a`, engine `A`):
  - Replace `test_configured_voice_comes_from_the_repository` with `test_a_role_of_another_engine_is_kept_but_skipped` (`engine=True`): `get_voice_name_for_language("fr_CA") == "A:a"`; role section equals its copy from before; then `role["fr"] = {"voice": "A:c"}` → `"A:c"`.
  - `test_without_engine_consistency_any_engines_role_speaks` (`engine=False`): `get_voice_name_for_language("fr_CA") == "B:b"`; `get_voice_name_for_language("en") == "A:a"` (missing voice).
  - `test_a_missing_role_voice_is_kept_and_speaks_when_back` (`engine=True`): `"en"` → `"A:a"`; `role["en"] == {"voice": "X:gone"}`; catalog rebuilt with `X:gone` (engine `A`, `en`) added → `"X:gone"`.
  - `test_a_skipped_full_locale_role_falls_back_to_the_primary_role` (`engine=True`): `role = {"fr_CA": B:b, "fr": A:c}` → `get_voice_name_for_language("fr_CA") == "A:c"`.
  - Hypothesis `test_lookups_never_write_and_speak_only_admitted_voices` (`suppress_health_check=[HealthCheck.function_scoped_fixture]`): roles a dict from keys `("en", "fr", "fr_CA", "de")` to names `("A:a", "B:b", "A:c", "X:gone")`, `engine` flag a boolean, main `A:a` or `B:b` (instance namespace with its engine), language from the keys plus `"en_US"`. Result is the main voice or a catalog voice, of the main engine when the flag is on; the role section is unchanged.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_voice_manager_roles.py` — Expected: FAIL: `assert 'B:b' == 'A:a'` (other engine), `assert 'A:a' == 'A:c'` (fall-through) and the property; the missing-voice and flag-off tests pass already (pins).
- [ ] **Step 3: Implement** `_may_speak` and the two methods (docstrings: spec U2/D2).
- [ ] **Step 4: Run** the file → PASS; full suite → **3687 passed, 0 skipped**.
- [ ] **Step 5: Commit** `voices/manager.py tests/test_voice_manager_roles.py`: `fix: skip other engines' role voices instead of relying on pruning`.

### Task 4: The voice before NVDA sets one keeps today's rule

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voices/manager.py` (new `initial_voice_name`)
- Modify: `addon/synthDrivers/WorldVoice/__init__.py` (`_get_voice`, `:455-458`)
- Test: `tests/test_voice_manager_roles.py`, `tests/test_engine_setting.py` (fake `Manager`, `:62-63`)

**Interfaces:**
- Produces: `VoiceManager.initial_voice_name(language: str) -> str` — `roles.voice_for(language, <in catalog.by_name>)`, else `default_voice_name` (D3). `SynthDriver._get_voice` calls it while `_voice is None`.

- [ ] **Step 1: Write the failing tests**
  - `tests/test_voice_manager_roles.py::test_initial_voice_is_the_available_role_of_any_engine` (`engine=True`): `initial_voice_name("fr_CA") == "B:b"` while `get_voice_name_for_language("fr_CA") == "A:a"`; `initial_voice_name("en") == "A:a"` (missing voice).
  - `tests/test_engine_setting.py`: rename the fake's `get_voice_name_for_language` to `initial_voice_name` (same body); `test_before_load_settings_the_engine_follows_the_role_voice` unchanged.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_voice_manager_roles.py tests/test_engine_setting.py` — Expected: 2 failed: `AttributeError: ... 'initial_voice_name'` (manager) and `AttributeError: 'Manager' object has no attribute 'get_voice_name_for_language'` (synth).
- [ ] **Step 3: Implement** `initial_voice_name` (docstring: the main voice is not chosen yet, so no engine to keep consistent with) and the `_get_voice` call.
- [ ] **Step 4: Run** both files → PASS; full suite → **3688 passed, 0 skipped**.
- [ ] **Step 5: Commit** `voices/manager.py __init__.py tests/test_voice_manager_roles.py tests/test_engine_setting.py`: `fix: keep the any-engine role voice before NVDA sets a voice`.

### Task 5: A main-voice change no longer prunes

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voices/manager.py` (setter `:189-196`; remove `on_keep_engine_consistent`, `:246-247`)
- Test: `tests/test_runtime_composition.py`, `tests/test_voice_manager_roles.py` (remove `test_keep_engine_consistent_prunes_through_the_repository`, `:40-43`)

**Interfaces:**
- Consumes: Task 3 lookup.
- Produces: the `default_voice_name` setter calls only `on_keep_main_locale_voice_consistent` after the instance switch.

- [ ] **Step 1: Write the failing tests** (composition fixture, engines `first` and `second`, each with `a` (en) and `b` (zh); `keepMainLocaleEngineConsistent=True`):
  - `test_an_engine_round_trip_keeps_and_restores_the_roles` parametrized `follow` in `(False, True)` (`keepMainLocaleVoiceConsistent`): role `{"en": first:a, "zh": first:b}`, copy it; `default_voice_name = "second:a"` → `role["zh"] == {"voice": "first:b"}`, `get_voice_name_for_language("zh") == "second:a"`; `default_voice_name = "first:a"` → `get_voice_name_for_language("zh") == "first:b"` and the role section equals the copy.
  - `test_switching_back_picks_the_kept_role_voice_of_the_engine` (follow off): role `{"en": first:b}`; `default_voice_name = "second:a"` → `voice_name_for_engine("first", "en") == "first:b"` (D5; the language step alone would pick `first:a`).
  - Remove the prune test from `tests/test_voice_manager_roles.py`.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_runtime_composition.py` — Expected: 3 failed (`KeyError: 'zh'` / role missing; `'first:a' == 'first:b'`).
- [ ] **Step 3: Implement**: drop the call and the method.
- [ ] **Step 4: Run** → PASS; full suite → **3690 passed, 0 skipped** (+3, −1).
- [ ] **Step 5: Commit** `voices/manager.py tests/test_runtime_composition.py tests/test_voice_manager_roles.py`: `fix: keep other engines' speech roles on a main voice change`.

### Task 6: Speech Role panel OK writes only the changed locales

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/rolePresenter.py` (`:6`, `apply` `:126-136`)
- Test: `tests/test_role_presenter.py`, `tests/test_role_panel_ui.py`

**Interfaces:**
- Consumes: `roles.assignments()`, `roles.save(assignments)`.
- Produces: `RolePanelPresenter.apply()` saves `assignments()` with `_pending` applied (voice → set, `""` → pop) and no pruning; the import of `prune_assignments` goes.

- [ ] **Step 1: Write the failing tests**
  - `test_engine_consistency_preview_cancel_and_apply`: replace `assert "fr" not in env.conf["WorldVoice"]["role"]` with `role["fr"] == {"voice": env.b.name}` and `env.manager.get_voice_name_for_language("fr") == env.a.name`.
  - `test_apply_keeps_an_untouched_role_of_another_engine`: saved `keepMainLocaleEngineConsistent=True`, `presenter.discard()` (reread); `role["fr"] = b`; `presenter.voices("fr") == []`, `presenter.selectedVoice("fr") == env.b.name`; `selectVoice("en", env.c.name)`; `apply()` → role `== {"en": {"voice": c}, "fr": {"voice": b}}`.
  - `test_apply_writes_only_the_changed_locales` (engine option on): role `{"en": a, "fr": b}`; `selectVoice("fr", "")`; `apply()` → role `== {"en": {"voice": a}}` (pin: passes before the change).
  - `tests/test_role_panel_ui.py::test_a_stored_voice_the_locale_does_not_list_shows_no_select`: `ui.presenter.assigned["zh"] = "gone"`; choose locale 1 → `_voicesChoice.selection == 0`, sliders disabled, `ui.presenter.calls == []` (pin).
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_role_presenter.py tests/test_role_panel_ui.py` — Expected: 2 failed (`'fr'` pruned), the two pins pass.
- [ ] **Step 3: Implement** `apply` without `prune_assignments`.
- [ ] **Step 4: Run** → PASS; full suite → **3693 passed, 0 skipped**.
- [ ] **Step 5: Commit** `rolePresenter.py tests/test_role_presenter.py tests/test_role_panel_ui.py`: `fix: keep untouched speech roles when the Speech Role panel saves`.

### Task 7: Remove the prune code

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voices/roles.py` (`prune_assignments` `:9-18`, `prune` `:66-67`, the `Collection` import)
- Test: `tests/test_role_repository.py` (`test_prune_keeps_only_available_assignments`), `tests/test_role_presenter.py` (`load_presenter`'s `voices.roles` stub, `:29-34`)

**Interfaces:** none produced; `grep -rn "prune" addon tests` finds nothing afterwards.

- [ ] **Step 1:** Remove the prune test and the presenter test's `voices.roles` stub.
- [ ] **Step 2:** Remove `prune_assignments`, `prune` and the unused import.
- [ ] **Step 3: Run** `grep -rn "prune" addon tests` → no output; full suite → **3692 passed, 0 skipped** (−1).
- [ ] **Step 4: Commit** `voices/roles.py tests/test_role_repository.py tests/test_role_presenter.py`: `refactor: remove the unused speech role pruning`.

### Task 8: Readmes

**Files:**
- Modify: `addon/doc/zh_TW/readme.md` (line 27 bullet; 「下一版更新」 second bullet)

- [ ] **Step 1:** Rewrite the 「保持主要語音引擎與地區語音引擎一致」 bullet (spec §8) and add the changelog bullet **保留其他語音引擎的語音角色** right after the engine list bullet, concise and user-facing.
- [ ] **Step 2:** `python3 -m pytest -q tests` → **3692 passed, 0 skipped**; `git diff --check` clean.
- [ ] **Step 3: Commit** the zh_TW readme: `docs: describe that other engines' speech roles are kept`.

### Task 9: Mutation run and full verification

**Files:** none unless a survivor shows a test gap (then a `test:` commit).

- [ ] **Step 1:** Copy the worktree to the scratchpad (`cp -rL`, excluding `mutants/`); there, with a background guard that kills mutmut when MemAvailable < 3 GB, run `mutmut run --max-children 3` on `voices/roles.py` (`*ConfigRoleRepository*voice_for*`), `voices/mainLocalePolicy.py` (`*admits*`), and `voices/manager.py` added to `source_paths` in the copy only (`*_may_speak*`, `*get_voice_name_for_language*`, `*_get_configured_voice_name_for_language*`, `*initial_voice_name*`). Expected: all killed or explained as equivalent (`mutmut show`); record in the ledger; delete the scratch copy.
- [ ] **Step 2:** `python3 -m pytest -q tests` → **3692 passed, 0 skipped** (+ any Step 1 test); `prek run --all-files` → all Passed; `git diff --check master` → nothing; both protected-path commands → no output.
- [ ] **Step 3:** Ledger: final counts, Rulings, the spec §7 Windows/NVDA checklist (not verifiable on Linux).
