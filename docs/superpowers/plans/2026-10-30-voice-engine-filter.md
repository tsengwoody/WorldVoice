# Voice Engine Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** A "Speech engine" combo box above "Voice" in NVDA's Voice settings panel filters the Voice list and the settings ring's Voice entry to one engine; choosing an engine switches at once to that engine's voice for NVDA's interface language (R1, R2, R4; voice texts keep ` [engine]`).

**Architecture:** A new NVDA-free core function `voices/engineFilter.pick_engine_voice` chooses the voice; `VoiceCatalog` gains per-engine views and `VoiceManager` exposes them. The synth gets an `engine` driver setting (`useConfig=False`, not in the ring, listed first), overrides NVDA's caching `availableVoices` with the current engine's list, keeps `availableLanguages` on every engine and fixes the ring's initial position. The Voice panel gives the engine combo box its own changer (cancel speech, set engine, refresh); the Speech Role panel sets the main voice through NVDA's `changeVoice`.

**Tech Stack:** Python 3 (NVDA add-on), pytest + Hypothesis, mutmut 3.8.0, ruff 0.16.3 via prek, gettext.

**Spec:** `docs/superpowers/specs/2026-10-30-voice-engine-filter-design.md` (commits `1c931a2`, `e37aa0c`; R3 dropped: no voice text or dictionary change).

## Global Constraints

- Voice texts unchanged everywhere (` [engine]` kept): no change to `driver/__init__.py` metadata, the VE/Cerence wrappers, `bridge/engineAdapter.py` or `VoiceSpec`; no new metadata key or `Voice` attribute.
- Nothing new stored: `engine` is `useConfig=False`, `availableInSettingsRing=False`; no confspec change, no migration.
- Label `_("Speec&h engine")` with the translator comment of spec §5 verbatim; zh_TW 「語音引擎(&H)」.
- `voices/engineFilter.py` is core: snake_case, imports only `..locales` and `..runtime.models`; synth, `ui/`, global plugin are host (mixedCase) — `tests/test_naming_layers.py`.
- Never modify `driver/*/driver/*`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; never add Neural; `ref` is a symlink, never staged.
- Engine drivers stay independently installable: no wrapper is touched; shared code only in core (`voices/`).
- Setters raise `LookupError` for unknown values before changing anything (phase-21 N14).
- ruff pinned `==0.16.3`; prek hooks run on commit (re-stage and recommit if a hook rewrites files; never `--no-verify`); explicit `git add` paths, `git diff --cached --stat` before each commit; English `<type>: <summary>` + why-body; no `Co-Authored-By`; no push; no `git stash`; at most 3 pytest workers with a MemAvailable ≥ 3 GB guard.
- Translations: `# Translators:` comment directly above the call; only `addon/locale/zh_TW/LC_MESSAGES/nvda.po` updated; no `.pot`/`.mo` committed. Docs: root `readme.md` and `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` only.

**Plan decisions where the spec is loose or a guard forces a name** (each also a `Ruling:` line in the ledger):

- P1 (spec §3.3 step 2): the exact-language step compares locales with `-`/`_` folded and case ignored. Spec §7 asks `zh-TW` vs `zh_TW` to match, and eSpeak reports `pt-br`/`en-gb`; with a raw `==` they would fall to the primary step and pick the first `zh*`/`pt*` voice (`zh_CN`/`zh_HK`, `pt`) instead.
- P2 (spec §3.4 `EngineSetting()`): the factory is the static method `SynthDriver._engineSetting()`; a public CapWords method name fails `tests/test_naming_layers.py` (host methods are mixedCase, leading underscore free).
- P3 (spec §7 "test_naming_layers passes unchanged"): `test_nvda_setting_ids_are_nvdas` subtracts `{"uwv"}`, WorldVoice's own id; `engine` is WorldVoice's own id too, so the test subtracts `{"uwv", "engine"}`.
- P4 (spec §7 role tests in `tests/test_role_panel.py`): they go in `tests/test_role_panel_ui.py`, whose fixture runs the real `makeSettings` where `setMainVoice` is defined.
- P5 (spec §7 "`voice_name_for_engine` uses ... `get_language`"): the signature of §3.2 takes `language`; the synth passes `languageHandler.getLanguage()` (§3.4). The manager test passes the language.

## Review Focus

1. **Interface and voice languages spelled differently** (`zh-TW`, `ZH_tw`, `pt_BR` vs eSpeak `pt-br`, bare `en` vs `en_US`): the region-matching voice wins, not the first voice of the primary language — Task 1 `test_exact_match_folds_separator_and_case`, `test_primary_language_comes_before_the_first_voice`.
2. **Stale or foreign role voice** (a role names a voice of another engine, or one no longer installed): ignored, the language steps decide — Task 1 `test_a_role_voice_outside_the_engine_is_ignored`.
3. **Voice with an empty language** (a plugin reporting `""`), first in table order: never matched by language, only the fallback picks it — Task 1 `test_a_voice_without_language_is_matched_only_as_fallback`.
4. **Before `loadSettings` (`_voice is None`) with a role voice of another engine than the default voice** (keep-engine-consistent off): `engine`, `availableVoices` and `availableVoices[self.voice]` stay consistent, so NVDA's `_get_language` does not raise — Task 4 `test_before_load_settings_the_engine_follows_the_role_voice`.
5. **Choosing the engine already current** (arrowing back, or a single engine): no `changeVoice`, no voice change, no role pruning, no `LookupError` — Task 4 `test_choosing_the_current_engine_changes_nothing`; panel path Task 5 `test_choosing_the_current_engine_keeps_the_voice`.

Baseline (worktree at `e37aa0c`): **3638 passed, 0 skipped**; prek all Passed; protected paths clean.

---

### Task 1: Core voice pick for an engine switch

**Files:**
- Create: `addon/synthDrivers/WorldVoice/voices/engineFilter.py`
- Create: `tests/test_engine_filter.py`
- Modify: `pyproject.toml` (`[tool.mutmut] source_paths`, `:45-65`)

**Interfaces:**
- Consumes: `locales.primary_language(locale: str) -> str`; `runtime.models.VoiceSpec` (`name`, `engine`, `language`).
- Produces: `pick_engine_voice(specs: Iterable[VoiceSpec], engine: str, language: str, role_voice: str | None) -> str` — over the specs of `engine` in the given order: (1) `role_voice` if it names one of them; (2) first whose language equals `language` with `-`→`_` and case folded (P1); (3) first whose `primary_language(spec.language) == primary_language(language)`, skipping empty languages; (4) the first; `LookupError(engine)` when the engine has no spec.

- [ ] **Step 1: Write the failing tests** in `tests/test_engine_filter.py`. Load the module like `tests/test_voice_catalog.py` loads `voices.catalog` (`stub_modules.package` over `WORLDVOICE`, then `importlib.import_module(PACKAGE + ".voices.engineFilter")`; no NVDA stubs needed). Fixture `SPECS`, already in table order (engine, language, name), built with `VoiceSpec(id, name, description=name, language, engine, locale=language)`:
  `A:de de_DE`, `A:hk zh_HK`, `A:tw zh_TW`, `A:us en_US`, `B:x ""`, `B:en en`, `B:pt pt`, `B:br pt-br`.
  - `test_the_role_voice_of_the_engine_wins`: `pick(SPECS, "A", "de", "A:tw") == "A:tw"`.
  - `test_a_role_voice_outside_the_engine_is_ignored` (parametrize role `"B:en"`, `"A:gone"`, `None`): `pick(SPECS, "A", "de", role) == "A:de"`.
  - `test_exact_language_comes_before_primary_language`: `pick(SPECS, "A", "zh_TW", None) == "A:tw"`.
  - `test_exact_match_folds_separator_and_case` (parametrize `("zh-TW","A","A:tw")`, `("ZH_tw","A","A:tw")`, `("pt_BR","B","B:br")`): result as given.
  - `test_primary_language_comes_before_the_first_voice` (parametrize `("en","A","A:us")`, `("zh","A","A:hk")`, `("en_GB","B","B:en")`, `("pt_PT","B","B:pt")`).
  - `test_the_first_voice_is_the_fallback`: `pick(SPECS, "A", "fr", None) == "A:de"`.
  - `test_a_voice_without_language_is_matched_only_as_fallback`: `pick(SPECS, "B", "en", None) == "B:en"` and `pick(SPECS, "B", "fr", None) == "B:x"`.
  - `test_an_engine_without_voices_raises`: `pytest.raises(LookupError)` for `pick(SPECS, "C", "en", None)`.
  - Hypothesis `test_the_pick_is_always_a_voice_of_the_engine`: `engine` from `("A","B")`, `language` from the spec languages plus `st.text(max_size=6)`, `role` from the names plus `None`. Assert the result's engine is `engine`; and when `role` is not a voice of `engine` and some voice of `engine` has a folded language equal to the folded request, the result's folded language equals it.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_engine_filter.py` — Expected: collection ERROR `ModuleNotFoundError: ... voices.engineFilter`.
- [ ] **Step 3: Implement** `pick_engine_voice` in `voices/engineFilter.py` (module docstring: the voice an engine switch picks, spec §3.3) with a private `_folded(locale)` helper; add `"addon/synthDrivers/WorldVoice/voices/engineFilter.py"` to `[tool.mutmut] source_paths` after `mainLocalePolicy.py`.
- [ ] **Step 4: Run** the file → 16 passed; full suite `python3 -m pytest -q tests` → **3654 passed, 0 skipped** (the naming and hygiene guards included).
- [ ] **Step 5: Commit** `addon/synthDrivers/WorldVoice/voices/engineFilter.py tests/test_engine_filter.py pyproject.toml`: `feat: add the voice pick for a speech engine switch`.

### Task 2: Per-engine catalog views and manager queries

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voices/catalog.py` (`VoiceCatalog`, `:23-49`)
- Modify: `addon/synthDrivers/WorldVoice/voices/manager.py` (after `voice_infos`, `:272-274`)
- Test: `tests/test_voice_catalog.py`, `tests/test_runtime_composition.py`, `tests/test_plugin_voice_contract.py`

**Interfaces:**
- Consumes: Task 1 `pick_engine_voice`; `ConfigRoleRepository.voice_for(language) -> str | None`.
- Produces:
  - `VoiceCatalog.engines: tuple[str, ...]` (distinct engines, table order); `VoiceCatalog.engine_voice_infos: Mapping[str, OrderedDict[str, VoiceInfo]]` (`MappingProxyType`; each entry the same object as in `voice_infos`); `EMPTY_CATALOG.engines == ()`.
  - `VoiceManager.engines -> tuple[str, ...]`; `engine_of(voice_name: str) -> str`; `voice_infos_for_engine(engine: str) -> OrderedDict[str, VoiceInfo]` (raises `LookupError`; `KeyError` qualifies); `voice_name_for_engine(engine: str, language: str) -> str` = `pick_engine_voice(self.table, engine, language, self.roles.voice_for(language))`.

- [ ] **Step 1: Write the failing tests**
  - `tests/test_voice_catalog.py::test_catalog_groups_voices_by_engine_in_table_order`: specs `B:x de`, `A:y en_US`, `B:w de`, `A:z en_GB` → `catalog.engines == ("A", "B")`; `{e: list(v) for e, v in catalog.engine_voice_infos.items()} == {"A": ["A:z", "A:y"], "B": ["B:w", "B:x"]}`; each entry `is catalog.voice_infos[name]`; each value `isinstance(..., OrderedDict)`; `list(catalog.voice_infos) == ["A:z", "A:y", "B:w", "B:x"]`.
  - `test_empty_catalog_has_no_engines`: `EMPTY_CATALOG.engines == ()` and `dict(EMPTY_CATALOG.engine_voice_infos) == {}`.
  - Extend `test_catalog_is_immutable`: `catalog.engines = ()` raises `FrozenInstanceError`; `catalog.engine_voice_infos["Z"] = None` raises `TypeError`.
  - `tests/test_runtime_composition.py::test_engine_queries_follow_the_catalog`: engines `first`, `second` → `manager.engines == ("first", "second")`; `manager.engine_of("second:b") == "second"`; `list(manager.voice_infos_for_engine("second")) == ["second:a", "second:b"]`; `pytest.raises(LookupError)` for `voice_infos_for_engine("missing")`.
  - `test_voice_name_for_engine_uses_the_configured_role`: set `c.config.conf["WorldVoice"]["role"]["zh"] = {"voice": "second:b"}` (as the role tests set roles) → `voice_name_for_engine("second", "zh") == "second:b"`; `voice_name_for_engine("first", "zh") == "first:b"` (role of another engine ignored); `voice_name_for_engine("first", "en_US") == "first:a"` (primary language).
  - `tests/test_plugin_voice_contract.py::test_a_plugin_is_listed_under_its_engine`: `composition.engine("ok")` plus the Neural-style class → `"Neural" in manager.engines`; `list(manager.voice_infos_for_engine("Neural")) == ["Neural:v1"]`; that entry `is manager.voice_infos["Neural:v1"]` and its `description.endswith(" [Neural]")`; `"Neural:v1" not in manager.voice_infos_for_engine("ok")`.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_voice_catalog.py tests/test_runtime_composition.py tests/test_plugin_voice_contract.py` — Expected: FAIL with `AttributeError: ... 'engines'` / `'engine_voice_infos'` / `'voice_infos_for_engine'` (5 new tests and the extended immutability test).
- [ ] **Step 3: Implement** the two catalog fields in `from_specs` and the four manager members (`engines` a property; the rest methods). `voice_infos` keeps every engine's voices (spec §3.2).
- [ ] **Step 4: Run** the three files → PASS; full suite → **3659 passed, 0 skipped**.
- [ ] **Step 5: Commit** `voices/catalog.py voices/manager.py` and the three test files: `feat: list voices per speech engine in the voice catalog`.

### Task 3: The engine driver setting and the ring's start

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py` (`_driverSettings`, `:117-139`; new `_engineSetting`, `_get_initialSettingsRingSetting`)
- Modify: `tests/pipeline_harness.py` (`Setting`, `Base`, `:303-343`)
- Test: `tests/test_settings_order.py`, `tests/test_worldvoice_pipeline_settings.py` (`EXPECTED_IDS`, slices `[8:]`), `tests/test_naming_layers.py` (`test_nvda_setting_ids_are_nvdas`, P3)

**Interfaces:**
- Consumes: NVDA `DriverSetting(id, displayNameWithAccelerator, availableInSettingsRing=..., useConfig=...)`.
- Produces: `SynthDriver._engineSetting() -> DriverSetting` (static; id `"engine"`, label `_("Speec&h engine")`, `availableInSettingsRing=False`, `useConfig=False`; P2), first in `_driverSettings` (so in `supportedSettings` and `allSupportedSettings`); `SynthDriver._get_initialSettingsRingSetting(self) -> int | None` — index in the ring list (`supportedSettings` filtered by `availableInSettingsRing`) of `rate`, else `0` when that list is non-empty, else `None`.
- Harness: `pipeline_harness.Setting.availableInSettingsRing` reads `options.get("availableInSettingsRing", False)` (NVDA's default); `Base.VoiceSetting` … `Base.VolumeSetting` pass `availableInSettingsRing=True`, as NVDA's do (`ref/nvda/source/synthDriverHandler.py:129-211`).

- [ ] **Step 1: Write the failing tests and the harness change**
  - `test_settings_order.py`: `STANDARD = ["engine", "voice", ...]`; `test_ring_follows_the_table_after_the_standard_settings` expects `["voice", "variant", "rate", "pitch", "volume", "uwv", *TABLE_DRIVER_IDS]` (the real ring today, now that the harness flags NVDA's settings; no `engine`).
  - New `test_engine_setting_is_first_unstored_and_off_the_ring`: `(engine.kind, engine.id, engine.label) == ("str", "engine", "Speec&h engine")`; `engine.options["useConfig"] is False`; `engine.options["availableInSettingsRing"] is False`; it is `supportedSettings[0]` and `allSupportedSettings[0]`.
  - New `test_initial_ring_setting_is_rates_place_in_the_ring`: `synth._get_initialSettingsRingSetting() == 2` and the ring list's entry 2 is `rate` (NVDA's own would answer 3).
  - New `test_initial_ring_setting_without_rate` (parametrize: settings `[engine, voice(ring)]` → `0`; `[engine]` → `None`), replacing `supportedSettings` on the class with `monkeypatch.setattr(type(synth), "supportedSettings", property(...))`.
  - `test_worldvoice_pipeline_settings.py`: `EXPECTED_IDS` starts with `"engine"`; `[8:]` → `[9:]`; the `useConfig` check expects `False` for `engine` too.
  - `test_naming_layers.py::test_nvda_setting_ids_are_nvdas`: subtract `{"uwv", "engine"}` and say so in its comment (P3).
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_settings_order.py tests/test_worldvoice_pipeline_settings.py tests/test_naming_layers.py` — Expected: FAIL: id lists lack `engine`, `AttributeError: _get_initialSettingsRingSetting`; the ring-list test passes already (harness only).
- [ ] **Step 3: Implement** `_engineSetting` with the spec §5 translator comment directly above `_("Speec&h engine")`, put it first in `_driverSettings`, and add `_get_initialSettingsRingSetting` (one comment: NVDA counts non-ring settings, `synthDriverHandler.py:417-429`).
- [ ] **Step 4: Run** the three files → PASS; full suite → **3663 passed, 0 skipped**.
- [ ] **Step 5: Commit** `__init__.py tests/pipeline_harness.py` and the three test files: `feat: add the speech engine setting to WorldVoice`.

### Task 4: Engine, voice list and languages on the synth

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py` (import `changeVoice` from `synthDriverHandler`; `_getAvailableVoices`, `:393-394`; new `_get_availableEngines`, `_get_engine`, `_set_engine`, `_get_availableVoices`, `_get_availableLanguages`)
- Modify: `tests/pipeline_harness.py` (new `auto_properties`)
- Create: `tests/test_engine_setting.py`

**Interfaces:**
- Consumes: Task 2 `VoiceManager.engines`, `engine_of`, `voice_infos_for_engine`, `voice_name_for_engine`, `voice_infos`; NVDA `synthDriverHandler.changeVoice(synth, voice)`; `languageHandler.getLanguage()`; `StringParameterInfo(id, displayName)`.
- Produces (synth): `_get_availableEngines() -> OrderedDict[str, StringParameterInfo]` (`StringParameterInfo(engine, engine)` per `manager.engines`, D3); `_get_engine() -> str` = `manager.engine_of(self.voice)`; `_set_engine(value: str) -> None` — same engine: nothing; not in `availableEngines`: `LookupError(value)` before anything; else `changeVoice(self, manager.voice_name_for_engine(value, languageHandler.getLanguage()))`, no cancel; `_get_availableVoices()` = `manager.voice_infos_for_engine(self.engine)`, recomputed per read, never sets `_availableVoices`; `_getAvailableVoices()` returns the same; `_get_availableLanguages() -> set[str]` = languages of `manager.voice_infos.values()` (every engine, D8).
- Harness: `auto_properties(monkeypatch, cls, *names)` — for each name, a class `property` calling `_get_<name>` and, when defined, `_set_<name>` (NVDA's `AutoPropertyType` mapping the exec harness lacks).

- [ ] **Step 1: Write the failing tests** in `tests/test_engine_setting.py`. Fixture: `load_synth(monkeypatch, worldvoice_conf())`; in the synth's globals (`synth_class._get_voice.__globals__`) set `OrderedDict`, `StringParameterInfo` (`SimpleNamespace(id=, displayName=)`), `languageHandler` (`getLanguage` from a mutable `lang`), `changeVoice` recording `(synth, voice)` then doing `synth.voice = voice` as NVDA does; `auto_properties` for `voice`, `engine`, `availableEngines`, `availableVoices`, `availableLanguages`. A fake manager with the Task 2 interface over `A:a1 "One - English [A]" en_US`, `A:a2 "Two - German [A]" de_DE`, `B:b1 "Bee - French [B]" fr_FR`; it records `voice_name_for_engine` calls (returns the engine's first voice) and cancels, its `default_voice_name` setter raises `LookupError` for unknown names, and `get_voice_name_for_language` returns a role from a dict else `default_voice_name`. Synth starts with `_voice = "A:a1"`.
  - `test_available_engines_lists_the_catalog_engines`: `[(k, v.id, v.displayName) for k, v in synth.availableEngines.items()] == [("A","A","A"), ("B","B","B")]`.
  - `test_engine_follows_the_voice`: `synth.engine == "A"`; `synth.voice = "B:b1"` → `synth.engine == "B"`.
  - `test_available_voices_is_the_current_engines_list_and_follows_a_voice_change` (F1): `list(synth.availableVoices) == ["A:a1", "A:a2"]`; `synth.voice = "B:b1"`; `list(synth.availableVoices) == ["B:b1"]`; `synth.availableVoices["B:b1"].displayName == "Bee - French [B]"`; `list(synth._getAvailableVoices()) == ["B:b1"]`; `"_availableVoices" not in vars(synth)`.
  - `test_available_languages_lists_every_engines_languages` (F8): `synth.availableLanguages == {"en_US", "de_DE", "fr_FR"}`.
  - `test_choosing_another_engine_changes_the_voice_through_change_voice`: `lang = "de"`; `synth.engine = "B"` → `changes == [(synth, "B:b1")]`, `manager.picks == [("B", "de")]`, `synth.voice == "B:b1"`, `manager.cancels == 0`.
  - `test_choosing_the_current_engine_changes_nothing` (RF5): `synth.voice = "A:a2"`; `synth.engine = "A"` → `changes == []`, `manager.picks == []`, `synth.voice == "A:a2"`.
  - `test_choosing_an_unknown_engine_raises_and_keeps_the_voice`: `pytest.raises(LookupError)` for `synth.engine = "C"`; `changes == []`, `manager.picks == []`, `synth.voice == "A:a1"`.
  - `test_before_load_settings_the_engine_follows_the_role_voice` (RF4): `synth._voice = None`, role `{"fr": "B:b1"}`, `lang = "fr"` → `synth.voice == "B:b1"`, `synth.engine == "B"`, `synth.availableVoices[synth.voice].language == "fr_FR"`.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_engine_setting.py` — Expected: 8 FAIL/ERROR (`AttributeError: ... '_get_engine'` / `'_get_availableEngines'`; `availableVoices` lists every voice).
- [ ] **Step 3: Implement** the five synth members and `_getAvailableVoices`; `_set_engine` keeps `_set_voice`'s no-stop rule (one comment: NVDA's panel cancels; `changeVoice` rebuilds the ring and loads the voice dictionary, F4/F6). Add `auto_properties` to the harness.
- [ ] **Step 4: Run** the file → 8 passed; full suite → **3671 passed, 0 skipped**.
- [ ] **Step 5: Commit** `__init__.py tests/pipeline_harness.py tests/test_engine_setting.py`: `feat: filter the WorldVoice voice list by the current speech engine`.

### Task 5: The Voice panel's engine combo box

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/ui/voicePanel.py` (imports; new `_EngineSettingChanger`; `WorldVoiceVoiceSettingsPanel._makeStringSettingControl`)
- Modify: `tests/ui_harness.py` (`Control.Unbind`; `gui.settingsDialogs` stub gains NVDA's real `DriverSettingChanger`/`StringDriverSettingChanger` via `load_definitions(REF / "nvda/source/gui/settingsDialogs.py", ...)` with `weakref`; stand-in `VoiceSettingsPanel._createNewControl` makes a string row through a new `_makeStringSettingControl(setting, settingsStorage) -> Sizer`; stand-in `onDiscard` mirrors NVDA, `settingsDialogs.py:1621-1628`: unbind `EVT_CHOICE` on every `<id>List`, then `getSettings().loadSettings()` when the driver has it; `load_voice_panel` stubs `speech.cancelSpeech` recording into `env.cancels`)
- Test: `tests/test_voice_settings_panel.py`

**Interfaces:**
- Consumes: Task 3/4 synth `engine` setting (`availableEngines`, `engine`); NVDA `StringDriverSettingChanger(driver, setting, container)` (`driver` is a weakref property); `speech.cancelSpeech()`.
- Produces: `_EngineSettingChanger(StringDriverSettingChanger).__call__(self, evt)` — `evt.Skip()`; `speech.cancelSpeech()`; `setattr(self.driver, "engine", self.container._engines[evt.GetSelection()].id)`; `self.container.updateDriverSettings(changedSetting="engine")`. `WorldVoiceVoiceSettingsPanel._makeStringSettingControl(self, setting, settingsStorage)` — NVDA's, then for `setting.id == "engine"`: `self.engineList.Unbind(wx.EVT_CHOICE)` and bind `_EngineSettingChanger(settingsStorage, setting, self)`; returns NVDA's sizer.

- [ ] **Step 1: Write the failing tests** with an `EngineDriver` test double: settings `(DriverSetting("engine"),) + SETTINGS`, supported `ALL | {"engine"}`; voices `A: a1 "One [A]", a2 "Two [A]"`, `B: b1 "Bee [B]"`; `availableEngines`, `engine` (getter from `voice`; setter records into `engineSets` and, for another engine, sets `voice` to its first voice), `availableVoices` (the current engine's), `loadSettings()` restoring a saved voice `"a1"`.
  - `test_the_engine_row_comes_first_and_before_voice_in_tab_order`: `list(panel.sizerDict)[:2] == ["engine", "voice"]`; `order(panel)[:2] == ["engine", "voice"]`; `before(panel.tab_order, panel.voiceList) is panel.engineList`; `panel.engineList.choices == ["A", "B"]`, `selection == 0`.
  - `test_choosing_an_engine_switches_the_voice_and_rebuilds_the_voice_list`: `panel.engineList.Select(1)`; `event = fire(panel.engineList, "EVT_CHOICE")` → `event.skipped`; `env.cancels == [True]`; `driver.engineSets == ["B"]`; `panel.voiceList.choices == ["Bee [B]"]`, `selection == 0`; `panel.engineList.choices == ["A", "B"]`, `selection == 1`.
  - `test_choosing_the_current_engine_keeps_the_voice` (RF5, panel path): `driver.voice = "a2"` before opening; select 0 and fire → `driver.voice == "a2"`; `panel.voiceList.selection == 1`.
  - `test_the_engine_combo_box_has_exactly_one_choice_handler`: the `EVT_CHOICE` handlers of `panel.engineList` are one `env.module._EngineSettingChanger`; `panel.voiceList` keeps its one handler (not ours).
  - `test_cancel_unbinds_the_engine_handler_and_restores_voice_and_engine`: choose `B`, then `panel.onDiscard()` → no `EVT_CHOICE` binding on `engineList`; `driver.voice == "a1"`; `driver.engine == "A"`.
  - `test_another_synth_gets_no_engine_row`: `Driver(ALL, name="espeak")` → `"engine" not in panel.sizerDict`; `getattr(panel, "engineList", None) is None`.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_voice_settings_panel.py` — Expected: the harness-only changes keep the existing tests green; the engine tests FAIL (`AttributeError: ... '_EngineSettingChanger'`, `env.cancels == []`, `voiceList.choices` still `["One [A]", "Two [A]"]`).
- [ ] **Step 3: Implement** `_EngineSettingChanger` and `_makeStringSettingControl` in `ui/voicePanel.py` (import `speech`, `StringDriverSettingChanger`); one comment: NVDA's Cancel unbinds one `EVT_CHOICE` handler per combo box (`settingsDialogs.py:1621-1628`), so ours replaces NVDA's.
- [ ] **Step 4: Run** the file → PASS; full suite → **3677 passed, 0 skipped** (`tests/test_settings_order.py` and every panel test still green with the new stand-in).
- [ ] **Step 5: Commit** `ui/voicePanel.py tests/ui_harness.py tests/test_voice_settings_panel.py`: `feat: switch the voice when the speech engine is chosen in the Voice panel`.

### Task 6: Speech Role panel sets the main voice through `changeVoice`

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/panels/role.py` (`setMainVoice`, `:39-43`; `import synthDriverHandler`)
- Modify: `tests/ui_harness.py` (`load_settings_dialog` stub `synthDriverHandler.changeVoice` recording into `env.voice_changes`)
- Test: `tests/test_role_panel_ui.py` (P4; its fake `Presenter` keeps `setMainVoice`)

**Interfaces:**
- Consumes: NVDA `synthDriverHandler.changeVoice(synth, voice)`; `worldvoice_synth()`.
- Produces: `setMainVoice(name)` = `changeVoice(current, name)` when WorldVoice is the current synth, then `config.conf["speech"][synth.name]["voice"] = name` as today.

- [ ] **Step 1: Write the failing tests**
  - `test_setting_the_main_voice_goes_through_nvdas_change_voice`: `ui.presenter.setMainVoice("eva")` → `ui.env.voice_changes == [(ui.synth, "eva")]`; `ui.env.conf["speech"]["WorldVoice"]["voice"] == "eva"`.
  - `test_setting_the_main_voice_without_worldvoice_only_writes_the_config`: `ui.env.current[0] = SimpleNamespace(name="espeak")`; `setMainVoice("eva")` → `voice_changes == []`; config written.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_role_panel_ui.py` — Expected: FAIL `assert [] == [(..., 'eva')]` (the panel sets `current.voice`).
- [ ] **Step 3: Implement** the `changeVoice` call (one comment: the ring and voice dictionary follow, spec F4/F6).
- [ ] **Step 4: Run** the file → PASS; full suite → **3679 passed, 0 skipped**.
- [ ] **Step 5: Commit** `panels/role.py tests/ui_harness.py tests/test_role_panel_ui.py`: `fix: set the main voice through changeVoice in the Speech Role panel`.

### Task 7: Translation and readmes

**Files:**
- Modify: `addon/locale/zh_TW/LC_MESSAGES/nvda.po`
- Modify: `readme.md`, `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` (Notes bullet + "Next update" first bullet)

**Interfaces:**
- Consumes: Task 3 label `Speec&h engine` and translator comment.
- Produces: user docs (spec §8).

- [ ] **Step 1:** Add to the zh_TW `.po` (`#.` translator comment, `#: addon/synthDrivers/WorldVoice/__init__.py:<line>`): `msgid "Speec&h engine"` / `msgstr "語音引擎(&H)"`. Run `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` → no output, exit 0.
- [ ] **Step 2:** In each readme add (a) a Notes bullet: "Speech engine", above "Voice" in NVDA's Voice settings panel, chooses which engine's voices the Voice list and the settings ring offer; choosing an engine switches to that engine's voice for the NVDA interface language, or its first voice; the ring's Voice entry cycles only within the current engine and the engine is changed only in the Voice settings panel; (b) the first "Next update" bullet **Speech engine list in the Voice settings panel:** with the same content. Each in the file's language, terms as that file already uses them (zh_TW/zh_HK 「語音引擎」, zh_CN 「语音引擎」).
- [ ] **Step 3:** `python3 -m pytest -q tests` → **3679 passed, 0 skipped**; `git diff --check` clean.
- [ ] **Step 4: Commit** `nvda.po` and the six readmes: `docs: describe the speech engine list in the Voice settings panel`.

### Task 8: Mutation run and full verification

**Files:** none changed unless a surviving mutant shows a test gap (then the test goes in `tests/test_engine_filter.py`, own commit `test: ...`).

- [ ] **Step 1:** Copy the worktree to the scratchpad (`cp -rL` excluding `mutants/`), and there run, with a background guard that kills mutmut when MemAvailable < 3 GB: `mutmut run --max-children 3 "*x_pick_engine_voice*" "*x__folded*"`. Expected: every mutant killed or explained (equivalent) by `mutmut show`; record counts and survivors in the ledger; delete the scratch copy.
- [ ] **Step 2:** In the worktree: `python3 -m pytest -q tests` → **3679 passed, 0 skipped** (+ any Step 1 test); `prek run --all-files` → all Passed; `git diff --check master` → nothing; both protected-path commands of DEVELOPMENT_WORKFLOW.md §7 → no output.
- [ ] **Step 3:** Ledger: final counts, Rulings, Windows/NVDA manual items (spec §7 checklist 1–10, not verifiable on Linux).
