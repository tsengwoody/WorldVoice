# Voice Panel Creation Order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Create WorldVoice's two non-driver Voice-panel controls at their table position, so window (object navigation), Tab and layout order all follow the table and each label sits directly before its control.

**Architecture:** An `updateDriverSettings` override runs a creation pre-pass over `allSupportedSettings`. The pre-pass creates each missing driver control with NVDA's `_createNewControl` and each WorldVoice non-driver control right after its anchor, chaining NVDA's `lastControl`. A layout-only move then corrects the sizer index that NVDA's `len(sizerDict) - 1` insertion gets wrong, and `super().updateDriverSettings` hides and updates. The copied `createDriverSettings` goes. Fingerprint guards pin the NVDA internals this relies on.

**Tech Stack:** Python 3, pytest, Hypothesis, mutmut 3.8.0, ruff 0.16.3 via prek.

**Spec:** `docs/superpowers/specs/2026-10-22-feat-voice-panel-creation-order-design.md`

## Global Constraints

- Never modify `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/`. Engine drivers stay independently installable. Never add Neural back.
- ruff is pinned `==0.16.3`. Every commit runs the prek hooks; never use `--no-verify`.
- Stage explicit paths only and check `git diff --cached --stat` first. Messages are English `<type>: <summary>` with a body that says why. No `Co-Authored-By`. Never `git stash`, never push, never touch `/workspace/WorldVoice`. Never stage `ref`.
- Full suite: single process, under the memory guard (stop when MemAvailable drops below 3 GB). mutmut: at most 3 workers.
- Behaviour kept: N5 (another synth: no non-driver control, no pipeline save), I1 (a destroyed control counts as absent), the `depends_on` enable rules, `onSave`/`onDiscard`, and RateBoost/Inflection shown in place on a voice switch.
- No `_()` string changes.
- Baseline: 2084 passed, 0 skipped.

## Review Focus

1. **A voice switch after the build** (`updateDriverSettings(changedSetting="voice")`) must create nothing, move nothing and keep all three orders. Task 4: `test_voice_panel_orders_follow_the_table[voice switch]`, which also asserts that the children count is unchanged.
2. **A WorldVoice → WorldVoice rebuild** leaves `lastControl` naming a destroyed window. The rebuild must not raise, and the orders must hold. Task 4: `test_voice_panel_orders_follow_the_table[worldvoice rebuild]`.
3. **An anchor driver setting whose control fails to make** (NVDA logs `UnsupportedConfigParameterError` and makes no row). The follower must still sit right after the previous row in every order. Task 4: `test_a_follower_of_a_failed_driver_control_follows_the_row_before`.
4. **A non-driver entry with no earlier driver entry** must be created after the driver rows and before NVDA's own controls, and must not crash the layout pass. Task 1: `test_creation_followers_without_an_earlier_listed_driver`. Task 4: `test_a_first_entry_without_a_driver_setting_comes_after_the_driver_rows`.
5. **Another synth without `allSupportedSettings`**: the pre-pass creates its `supportedSettings` controls in order and no WorldVoice control. A later voice switch then neither duplicates nor adds controls. Task 4: `test_another_synth_voice_switch_adds_no_control`.

---

### Task 1: `creation_followers` pure helper

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/panelLayout.py` (after `voice_placements`)
- Test: `tests/test_panel_layout.py`

**Interfaces:**
- Consumes: none.
- Produces: `creation_followers(specs: Sequence[Any], listed: Callable[[str], bool]) -> dict[str | None, tuple[str, ...]]`. This maps a driver id to the keys of the non-driver entries made right after it, in table order. Key `None` holds those with no listed driver entry before them. Keys with no followers are absent.

- [ ] **Step 1: Write the failing tests**

```python
def test_creation_followers_of_the_table(table):
	assert layout.creation_followers(voice(table), lambda driver_id: True) == {
		"nummod": ("group_size",),
		"punctuationwaitfactor": ("punctuation_pause_characters",),
	}

def test_creation_followers_skip_an_unlisted_driver(table):
	listed = lambda driver_id: driver_id not in {"nummod", "punctuationwaitfactor"}
	assert layout.creation_followers(voice(table), listed) == {
		"numlan": ("group_size",),
		"removepunctuationcharacters": ("punctuation_pause_characters",),
	}

def test_creation_followers_chain_in_table_order():
	# specs d(driver d), a(None), b(None), e(driver e), c(None)
	assert layout.creation_followers(specs, lambda d: True) == {"d": ("a", "b"), "e": ("c",)}

def test_creation_followers_without_an_earlier_listed_driver():
	# specs a(None), d(driver d unlisted), b(None)
	assert layout.creation_followers(specs, lambda d: False) == {None: ("a", "b")}

@given(specs=tables(), data=st.data())
def test_property_creation_follows_the_placement_anchor(specs, data):
	# Build the creation sequence: for each listed driver spec in table order, its key then
	# the followers; then the followers of None. Every non-driver key appears exactly once.
	# Its predecessor in the sequence is its voice_placements anchor, taking
	# has_row = listed for driver entries and True for the others; with anchor None it is
	# in the None group.
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q tests/test_panel_layout.py -k creation`
Expected: 5 failed, `AttributeError: ... 'creation_followers'`.

- [ ] **Step 3: Implement `creation_followers` in `panelLayout.py`**

Walk the specs once, keeping the last listed driver id (start `None`). Append each non-driver key to that id's list.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest -q tests/test_panel_layout.py`
Expected: all pass. Full suite: 2089 passed, 0 skipped.

- [ ] **Step 5: Commit**: `git add addon/synthDrivers/WorldVoice/pipeline/panelLayout.py tests/test_panel_layout.py`, then `feat: list the Voice panel controls to create after each driver setting`.

### Task 2: Guard the NVDA internals the override relies on

**Files:**
- Test: `tests/test_nvda_settings_copy.py`

**Interfaces:**
- Consumes: `method(path, cls, name)` (existing helper).
- Produces: fingerprint constants `CREATE_NEW_CONTROL_FINGERPRINT`, `UPDATE_DRIVER_SETTINGS_FINGERPRINT` and `REFRESH_GUI_FINGERPRINT`, each with a review comment (spec §5).

- [ ] **Step 1: Write the tests**
  - `test_nvda_create_new_control_is_the_reviewed_version`
  - `test_nvda_update_driver_settings_is_the_reviewed_version`
  - `test_nvda_refresh_gui_is_the_reviewed_version`

  Each asserts `sha256(ast.unparse(method)) == <CONST>`.
  - `test_nvda_makers_chain_last_control[_makeSliderSettingControl|_makeStringSettingControl|_makeBooleanSettingControl]`: the body contains, in order, `if self.lastControl:` whose body is `<c>.MoveAfterInTabOrder(self.lastControl)`, then `self.lastControl = <c>`, with the same `<c>`.
  - `test_nvda_voice_panel_makes_driver_settings_first`: the first statement of `VoiceSettingsPanel.makeSettings` that is not a comment or docstring unparses to `self.updateDriverSettings()`.
  - `test_nvda_voice_change_updates_the_driver_settings`: `StringDriverSettingChanger.__call__` contains the call `self.container.updateDriverSettings(changedSetting=self.setting.id)`.
- [ ] **Step 2: Prove they bite.** Write each fingerprint first as `"0" * 64`, run, and read the actual digest from the failure. Expected: 3 failed with an assertion diff. Then paste the real digests.
- [ ] **Step 3: Run the tests**

Run: `python3 -m pytest -q tests/test_nvda_settings_copy.py`
Expected: 10 passed. Full suite: 2097 passed.

- [ ] **Step 4: Commit**: `test: guard the NVDA panel internals the Voice panel relies on`.

### Task 3: Model window order, labels and Tab order separately in the UI harness

**Files:**
- Modify: `tests/ui_harness.py` (`Control.__init__`, `MoveAfterInTabOrder`, `Sizer.Clear`/`contents`, `BoxSizerHelper.addLabeledControl`, `SettingsPanel.__init__`, fake `_createNewControl`)
- Create: `tests/test_ui_harness.py`

**Interfaces:**
- Produces:
  - `SettingsPanel.children: list[Control]`: the creation order (HWND sibling order); destroyed windows leave it;
  - `SettingsPanel.tab_order: list[Control]`: separate from `children`;
  - `class Label(StaticText)`: the label `addLabeledControl` and the fake `_createNewControl` make before a slider or choice, with `label` = the label text;
  - `Sizer.windows() -> list[Control]`: every window, labels included;
  - `contents()` and `controls()` leave labels out.

- [ ] **Step 1: Write the failing tests** in `tests/test_ui_harness.py`
  - `test_move_after_in_tab_order_leaves_window_order`: make `a`, `b`, `c` on a panel; `a.MoveAfterInTabOrder(c)`; `panel.children == [a, b, c]` and `panel.tab_order == [b, c, a]`.
  - `test_a_labeled_control_follows_its_label`: `addLabeledControl("X:", TextCtrl)`; `panel.children[-2:]` is `[Label "X:", control]`, the row holds both, and `row.controls() == [control]`.
  - `test_clear_destroys_labels_and_drops_them_from_both_orders`: after `Clear(delete_windows=True)`, label and control are destroyed and appear in neither `children` nor `tab_order`.
- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q tests/test_ui_harness.py`
Expected: 3 failed (`AttributeError: children`, or no `Label`).
- [ ] **Step 3: Implement the harness changes** listed under Files. The fake `_createNewControl` adds a `Label(self, label=f"{displayName}:")` to the row before a slider or choice.
- [ ] **Step 4: Run the tests to verify they pass.** Run the new file, then the full suite. Expected: 3 passed, and 2100 passed in the full suite: no existing test changes behaviour, because `tab_order` keeps its old semantics.
- [ ] **Step 5: Commit**: `test: model window creation order apart from Tab order in the UI fakes`.

### Task 4: Create the non-driver controls in table order from an `updateDriverSettings` override

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py` (`makeSettings`; replace `_addPipelineControls` and `createDriverSettings`)
- Modify: `tests/test_nvda_settings_copy.py` (remove the AST-equality guard and its helpers)
- Modify: `tests/test_settings_order.py`, `tests/test_voice_settings_panel.py`

**Interfaces:**
- Consumes: `creation_followers` (Task 1), `panel.children` and `Label` (Task 3).
- Produces on `WorldVoiceVoiceSettingsPanel`:
  - `updateDriverSettings(self, changedSetting=None) -> None`;
  - `_makePipelineControl(self, spec, settings) -> control`: makes the control with a fresh `BoxSizerHelper(self, sizer=self.settingsSizer)`, sets the attribute and `self.lastControl`;
  - `_placePipelineRows(self, keys) -> None`: the layout-only move, for the given keys.
  - `createDriverSettings` and `_addPipelineControls` are removed.

- [ ] **Step 1: Write the failing tests** in `tests/test_settings_order.py`. Add helpers:
  - `window_keys(panel, controls)`: the keys in `panel.children` order;
  - `labels_precede_controls(env, panel, specs)`: for every non-checkbox entry, `panel.children[i - 1]` is a `Label` whose `label` equals `control.label` (driver rows: the setting display name plus a colon).

  Then add `test_voice_panel_orders_follow_the_table[first build|voice switch|worldvoice rebuild|other synth rebuild]`. For each scenario it asserts:
  - `window_keys == tab_keys == voice_rows == VOICE_KEYS`;
  - labels precede their controls;
  - for "voice switch", `len(panel.children)` is unchanged.

  Review Focus tests in `tests/test_voice_settings_panel.py`:
  - `test_a_follower_of_a_failed_driver_control_follows_the_row_before`: a panel subclass whose `_createNewControl` makes no row for `nummod`. Group size comes right after `voice`'s control in children, Tab and layout order.
  - `test_a_first_entry_without_a_driver_setting_comes_after_the_driver_rows`: table `(group_size, number_mode)`. Group size comes after the last driver row and before "Automatic language switching" in all three orders.
  - `test_another_synth_voice_switch_adds_no_control`: `other_synth()`, then `updateDriverSettings("voice")`. Children are unchanged, and `groupSizeSpin is None`.

  Replace every `tab_after` assertion with a `panel.tab_order` / `panel.children` adjacency assertion. Change `panel.createDriverSettings(changedSetting="rateBoost")` to `panel.updateDriverSettings(changedSetting="rateBoost")`. Add `"createDriverSettings"` and `"_addPipelineControls"` to `test_the_named_rule_and_placement_helpers_are_gone`.
- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q tests/test_settings_order.py tests/test_voice_settings_panel.py`
Expected: the window-order and label assertions fail on every orders scenario. Group size and the characters edit come last in `children`, and their labels are not adjacent. The helpers-gone test also fails.
- [ ] **Step 3: Implement** per spec §4:
  - `makeSettings` keeps the snapshot, then calls `super().makeSettings`, `_bindControllers` and `_applyDependencies`;
  - the `updateDriverSettings` pre-pass (I1 reset, N5 gate, skipping `changedSetting`, existing rows and private ids), then `_placePipelineRows(made)`, then `super().updateDriverSettings(changedSetting)`;
  - delete `createDriverSettings`, `_addPipelineControls` and the `MoveAfterInTabOrder` call. Keep `_moveSizer`, `_rowIndex` and `_updateValueForControl`.

  In `tests/test_nvda_settings_copy.py`, delete `test_create_driver_settings_is_nvdas_update_driver_settings_over_all_settings`, `without_docstring`, `AllSettings`, `is_settings_source` and the `COPY` constant, and update the module docstring.
- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest -q tests/test_settings_order.py tests/test_voice_settings_panel.py tests/test_pipeline_panels.py tests/test_nvda_settings_copy.py`
Expected: all pass. Full suite: 2106 passed, 0 skipped. That is 2100, minus the 1 AST guard, plus the 4 orders scenarios and the 3 Review Focus tests.
- [ ] **Step 5: Commit**: `feat: create the Voice panel's WorldVoice controls in table order`.

### Task 5: Mutation run and final verification

**Files:** none, unless a surviving mutant needs a test (`tests/test_panel_layout.py`).

- [ ] **Step 1: mutmut on `creation_followers`.** Run in a scratch copy, with `--max-children 3` and the memory guard: `mutmut run "*creation_followers*"`. Expected: every mutant killed, or each survivor recorded as equivalent, with the reason, in the ledger.
- **Mutation notes (final review M3, seeded on `VoiceSettingsDialogs.py`):**
  - `setting.id != changedSetting` in the pre-pass: killed by `test_the_pre_pass_leaves_the_changed_setting_to_nvda`, which lists a setting that has no row and passes it as `changedSetting`. In practice `changedSetting` is always `voice`, which already has a row.
  - `absent and` in `values = pipeline_settings.get() if absent and self._isWorldVoice() else None`: equivalent. `_makePipelineControls` makes only controls that `_voiceControl` counts as absent, so when nothing is absent the loaded values are never read; `absent` only saves one `pipeline_settings.get()`.
- [ ] **Step 2: §7 verification**
  - `python3 -m pytest -q tests` under the guard. Expected: 2106 passed, 0 skipped (plus any survivor-killing tests).
  - `prek run --all-files`. Expected: all Passed.
  - `git diff --check master`. Expected: no output.
  - The two protected-path commands. Expected: no output.
