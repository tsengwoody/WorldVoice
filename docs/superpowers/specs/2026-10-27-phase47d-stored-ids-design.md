# Phase 47d: stored identifiers in NVDA camelCase

Date: 2026-10-27.
Base: `master` `f1f61bf` (phase 47c merged). Branch: `phase47d-stored-ids`.
Source: round-9 review `storage/refactor9.md` §6.1 rule 3 (overturned by the user on 2026-10-27) and the §6 row **P47d**; the user's decisions of 2026-10-27 relayed by the orchestrator.
Status: normal flow (DEVELOPMENT_WORKFLOW.md §3) with §3.2 "改名與搬移的證明": scripted renames from explicit `OLD=NEW` lists, one group per commit, each proven by an order-sensitive token check plus an AST and ordered-comments check, in which a string may change only by a listed pair.

Paths are under `addon/synthDrivers/WorldVoice/` unless stated. NVDA paths are under `ref/nvda/source/`.

## 1. Problem

WorldVoice stores identifiers in three NVDA files, which belong to the NVDA host layer, but they come in four spellings:

- nvda.ini `[WorldVoice]` keys: PascalCase (`DetectLanguageTiming` `languageDetection/settings.py:20`, `KeepMainLocaleVoiceConsistent` `__init__.py:72`, `CJKCharactersLanguage` `languageDetection/scriptLanguages.py:115`), camelCase (`latinCharactersLanguage` `:114`), and snake_case. The snake_case keys are the pipeline section's, whose key *is* the core field name (`PIPELINE_CONFSPEC = {spec.key: …}` `pipeline/settings.py:278`, read and written by `ConfigPipelineRepository` `:377-386`), and the log section's, whose key is a stage's log key (`__init__.py:83`, `pipeline/registry.py:148-167`).
- Driver setting ids: concatenated lowercase (`globalwaitfactor`, `sayallwaitfactor`, … `pipeline/settings.py:135-254`). A driver setting id is the synth's property name (NVDA reads and writes `getattr(synth, setting.id)`, `autoSettingsUtils/autoSettings.py:160-163`, `:201-206`).
- gestures.ini script names: `script_popup_SpeechSettingsDialog` and `script_switch_log_record` (`addon/globalPlugins/WorldVoice/__init__.py:127`, `:134`). NVDA binds a user's gesture by the name after `script_` (`inputCore.py:879`, `scriptHandler.py:73`).

Rule 3 of refactor9 §6.1 first kept these out of the naming rule because renaming needs a settings migration. The user overturned it on 2026-10-27: style uniformity wins, users' WorldVoice settings and custom gestures may reset, and no migration is written. Phase 47a's guard parks the two script names in `TRANSITIONAL_47D` (`tests/test_naming_layers.py:121-129`).

## 2. Goals

1. Every identifier WorldVoice defines and stores in an NVDA file is NVDA camelCase (`ref/nvda/projectDocs/dev/codingStandards.md`: lowercase first letter, no underscore), apart from the exceptions of §3. *Decided by the user (2026-10-27).*
2. Core program fields stay snake_case (`PipelineSettings.number_mode` `pipeline/settings.py:284`, `Stage.log_key` `pipeline/registry.py:130`); only the stored keys and ids change. The core table maps a field to its stored key by one derivation (§5). *Decided by the user (2026-10-27); mechanism decided by the orchestrator with the recommended default; user may override before merge.*
3. No migration and no changelog line (§4). *Decided by the user (2026-10-27).*
4. The naming guard ends with no `TRANSITIONAL_47D` and checks the stored identifiers too (§6). *Decided by the user (2026-10-27).*

### 2.1 Every stored identifier, old and new

**nvda.ini `[WorldVoice][autoLanguageSwitching]`**

| Old | New | Defined at |
| --- | --- | --- |
| `CJKCharactersLanguage` | `cjkCharactersLanguage` | `languageDetection/scriptLanguages.py:115` |
| `DetectLanguageTiming` | `detectLanguageTiming` | `languageDetection/settings.py:20`, `:24` |
| `KeepMainLocaleVoiceConsistent` | `keepMainLocaleVoiceConsistent` | `__init__.py:72`, `voices/mainLocalePolicy.py:45` |
| `KeepMainLocaleParameterConsistent` | `keepMainLocaleParameterConsistent` | `__init__.py:73`, `voices/mainLocalePolicy.py:71` |
| `KeepMainLocaleEngineConsistent` | `keepMainLocaleEngineConsistent` | `__init__.py:74`, `voices/mainLocalePolicy.py:21` |
| `latinCharactersLanguage`, `arabicCharactersLanguage`, `cyrillicCharactersLanguage`, `devanagariCharactersLanguage` | unchanged | `languageDetection/scriptLanguages.py:114`, `:116`, `:118-119` |

**nvda.ini `[WorldVoice][pipeline]`**: the stored key of each `PipelineSettingSpec` with `pipeline_config=True` (`pipeline/settings.py:120-268`, `:274`), derived from its field key (§5).

| Field key (unchanged) | Old stored key | New stored key |
| --- | --- | --- |
| `scope` | `scope` | `scope` |
| `global_wait_factor` | `global_wait_factor` | `globalWaitFactor` |
| `number_mode` | `number_mode` | `numberMode` |
| `group_size` | `group_size` | `groupSize` |
| `number_wait_factor` | `number_wait_factor` | `numberWaitFactor` |
| `item_wait_factor` | `item_wait_factor` | `itemWaitFactor` |
| `sayall_wait_factor` | `sayall_wait_factor` | `sayAllWaitFactor` |
| `unspaced_script_space_wait_factor` | `unspaced_script_space_wait_factor` | `unspacedScriptSpaceWaitFactor` |
| `punctuation_pause_enabled` | `punctuation_pause_enabled` | `punctuationPauseEnabled` |
| `remove_punctuation_characters` | `remove_punctuation_characters` | `removePunctuationCharacters` |
| `punctuation_wait_factor` | `punctuation_wait_factor` | `punctuationWaitFactor` |
| `punctuation_pause_characters` | `punctuation_pause_characters` | `punctuationPauseCharacters` |

**nvda.ini `[WorldVoice][log]`**: `enable` (`addon/globalPlugins/WorldVoice/pipelineLog.py:26-32`, `pipeline/registry.py:93`) is unchanged; each log switch is derived from a stage's log key or `also_logged_by` key (`pipeline/registry.py:148-167`, §5).

| Log key (unchanged, `Stage.log_key`) | Old switch | New switch |
| --- | --- | --- |
| `apply_speech_dictionaries` | `apply_speech_dictionaries` | `applySpeechDictionaries` |
| `number_language` (`also_logged_by`) | `number_language` | `numberLanguage` |
| `number_mode` | `number_mode` | `numberMode` |
| `unspaced_script_space_wait_factor` | `unspaced_script_space_wait_factor` | `unspacedScriptSpaceWaitFactor` |
| `item_wait_factor` | `item_wait_factor` | `itemWaitFactor` |
| `punctuation_wait_factor` | `punctuation_wait_factor` | `punctuationWaitFactor` |
| `number_wait_factor` | `number_wait_factor` | `numberWaitFactor` |
| `speech_viewer` | `speech_viewer` | `speechViewer` |

**Driver setting ids** (synth properties; NVDA stores in `[speech][WorldVoice]` only those with `useConfig=True`, `autoSettingsUtils/autoSettings.py:136`, `:160`, `:201`):

| Old | New | Defined at | Stored in nvda.ini? |
| --- | --- | --- | --- |
| `globalwaitfactor` | `globalWaitFactor` | `pipeline/settings.py:135` | no (`useConfig=False`, `__init__.py:116`) |
| `numberwaitfactor` | `numberWaitFactor` | `pipeline/settings.py:192` | no |
| `itemwaitfactor` | `itemWaitFactor` | `pipeline/settings.py:202` | no |
| `sayallwaitfactor` | `sayAllWaitFactor` | `pipeline/settings.py:212` | no |
| `unspacedscriptspacewaitfactor` | `unspacedScriptSpaceWaitFactor` | `pipeline/settings.py:221` | no |
| `punctuationpauseenabled` | `punctuationPauseEnabled` | `pipeline/settings.py:231` | no |
| `removepunctuationcharacters` | `removePunctuationCharacters` | `pipeline/settings.py:242` | no |
| `punctuationwaitfactor` | `punctuationWaitFactor` | `pipeline/settings.py:254` | no |
| `uwv`, `numlan`, `nummod` | unchanged (§3) | `__init__.py:144`, `pipeline/settings.py:148`, `:162` | `uwv`, `numlan` yes; `nummod` no |

The NVDA controls the Voice panel makes follow the id (`<id>Slider`, `<id>Checkbox`, `gui/settingsDialogs.py:1443`, `:1526`; `ui/panelLayout.py:127-129`), and so does the `_PipelineSetting` descriptor each pipeline driver setting is installed as (`__init__.py:528-530`): neither needs its own edit. Each new id equals the new pipeline stored key of its entry, which the table guard checks (§6).

**gestures.ini script names** (`[globalPlugins.WorldVoice.GlobalPlugin]`)

| Old | New | Defined at |
| --- | --- | --- |
| `script_popup_SpeechSettingsDialog` (stored as `popup_SpeechSettingsDialog`) | `script_popupSpeechSettingsDialog` | `addon/globalPlugins/WorldVoice/__init__.py:127` |
| `script_switch_log_record` (stored as `switch_log_record`) | `script_switchLogRecord` | `addon/globalPlugins/WorldVoice/__init__.py:134` |

## 3. Non-goals and exceptions

Each exception, with its reason:

- **`WorldVoice`**: the `[WorldVoice]` section (`__init__.py:69`), `[speech][WorldVoice]`, and the synth `name` (`__init__.py:93`), which NVDA stores as the selected synthesizer (`[speech] synth`). It is the product's proper noun. *Decided by the user (2026-10-27).*
- **Data keys, not identifiers**: voice names under `[WorldVoice][voices]` (`__many__`, `__init__.py:85`), engine names under `[WorldVoice][engine]` (`__many__`, `:79-81`), and locale keys under `[WorldVoice][role]` (`:78`, written by `voices/roles.py:55-61`). *Decided by the user (2026-10-27).*
- **Names NVDA defines**: the setting ids `voice`, `variant`, `rate`, `rateBoost`, `pitch`, `inflection`, `volume` (`synthDriverHandler.py:132-209`), which are also the keys of each voice under `[WorldVoice][voices]` (`runtime/voiceSettings.py:17-24`) and the `voice` key of each role (`voices/roles.py:59`). NVDA config keys WorldVoice reads or writes, such as `speech.trustVoiceLanguage` (`__init__.py:340`), `general.loggingLevel` (`pipeline/registry.py:90`) and `speech.<synth>.voice` (`addon/globalPlugins/WorldVoice/panels/role.py:43`). All of them already satisfy mixedCase. *Decided by the user (2026-10-27).*
- **Coined single-token driver setting ids `uwv`, `numlan`, `nummod`** stay. They are one lowercase token, so they already satisfy mixedCase. `uwv` and `numlan` are the only WorldVoice ids NVDA stores (`useConfig=True`), so keeping them keeps those two settings across the upgrade. `numlan` and `nummod` are choice settings, for which NVDA looks up `available{id.capitalize()}s` (`gui/settingsDialogs.py:1484`, `synthSettingsRing.py:76`). A camelCase choice id would need an accessor such as `_get_availableNumbermodes`, so the table guard requires a choice driver id to be one lowercase token (§6). *Decided by orchestrator with the recommended default; user may override before merge.*
- **Single-word keys already conforming**: `scope`, `enable`, the section names `autoLanguageSwitching`, `pipeline`, `role`, `engine`, `log`, `voices`.
- **Values are not identifiers**: stored values such as `"WorldVoice"`/`"all"` (scope), `"before"`/`"after"` (timing), the number modes, the `numlan` values `"default"`/`"main"`, and locale codes are not renamed.
- **Core names stay**: `PipelineSettingSpec.key`, `PipelineSettings` fields, `Stage.log_key`, `depends_on` keys, the `update(**changes)` keywords, `PIPELINE_SETTING_BY_KEY`, `DEFAULT_PIPELINE_SETTINGS`, `PIPELINE_CONFIG_KEYS` (all keyed by field key), `DetectionSettings` fields, `DetectionScript.config_key` (a field; its value is what changes). Log rows in `addon/log/pipeline.csv` and debug messages keep the log key (`pipeline/registry.py:96-104`): the CSV is WorldVoice's own debug file, not an NVDA file.
- **Host-layer attributes that are not stored** stay, e.g. `self._DetectLanguageTimingValue` in `addon/globalPlugins/WorldVoice/panels/detection.py:50` (an attribute; the guard accepts it as CapWords). The scripts' description strings (`_("popup speech settings dialog")`, `_("switch log record")`) are msgids and do not change.
- `VoiceSnapshot.rateBoost` stays in `INTERFACE_NAMES` (`tests/test_naming_layers.py:111-114`): the core field mirrors NVDA's setting id `rateBoost`, so it is the one camelCase name in a core module. *Decided by orchestrator with the recommended default; user may override before merge.*
- Historical documents under `docs/` (earlier specs, plans, reviews) keep the old names. They record what was true then.
- Vendored drivers, `driver/sonic/`, generated Unicode data: none of the old names occurs there. The one byte-level hit, `uwv` inside `driver/RHVoice/driver/lib/x86/RHVoice.dll`, is an unchanged id and a binary.

## 4. NVDA user's view

**What resets after the upgrade.** Each WorldVoice setting stored under a renamed key reads as its default, in every profile, until the user sets it again:

- the Unicode Detection panel's CJK language choice and detection timing (defaults `ja` and `after`, `languageDetection/scriptLanguages.py:115`, `languageDetection/settings.py:20`);
- the three "keep main locale … consistent" options (defaults on, off, on, `__init__.py:72-74`);
- every Speech Pipeline setting except the effect scope (`pipeline/settings.py:120-268`), and with it the number mode in the settings ring;
- the Log Record panel's stage switches (default off; the "enable" switch is kept);
- custom gestures for the two scripts ("popup speech settings dialog", "switch log record"). Neither has a default gesture (`addon/globalPlugins/WorldVoice/__init__.py:122-139`).

**What is kept**: the selected synthesizer, the voice, variant, rate, rate boost, pitch, inflection and volume (NVDA's ids), "Detect language based on Unicode characters" (`uwv`), the number language (`numlan`), the Latin, Arabic, Cyrillic and Devanagari assumed languages, the effect scope, the log "enable" switch, speech roles, enabled engines and each voice's own parameters. Nothing in `[speech][WorldVoice]` changes, because the only WorldVoice ids NVDA stores there (`uwv`, `numlan`) keep their names.

**No migration and no changelog line.** *Decided by the user (2026-10-27).* `readme.md` and `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` name none of the renamed keys, ids or script names (`grep -i` for each old name over the six files finds none), so no readme edit.

**NVDA tolerates the orphaned old keys.** The old keys stay in nvda.ini and in each profile. They are ignored and never removed:

- On load, NVDA validates each profile against the confspec (`config/profileUpgrader.py:27`, `:47-66`) and fails only on a validation result that is not a bool. configobj reports a key outside the spec in `extra_values`, not as an error. Checked with configobj 5.0.9, the version NVDA requires (`ref/nvda/pyproject.toml:31`): a profile holding `number_mode = group`, `global_wait_factor = 50` and `DetectLanguageTiming = before` against a spec naming only the new keys validates `True` with no errors, and `write()` keeps the old lines. The scratch script is recorded in the ledger. Old and new keys that differ only in case (`KeepMainLocaleVoiceConsistent`/`keepMainLocaleVoiceConsistent`) are distinct configobj keys.
- `AggregatedSection.__getitem__` validates only a key that has a spec (`config/__init__.py:1269-1273`). WorldVoice never looks an old key up after this phase. It never iterates `[autoLanguageSwitching]`, `[pipeline]` or `[log]`, where `__iter__` would list orphans (`config/__init__.py:1280-1293`). `voices/roles.py:55-61` iterates only `[role]`, whose keys do not change.
- Saving writes the whole profile (`config/__init__.py:714-716`), so orphans stay but break nothing.
- gestures.ini: a binding to a script that no longer exists logs a debug warning and is skipped in the Input Gestures dialog (`inputCore.py:877-884`). At run time the old binding's `getattr` fails and NVDA falls through to the object's own bindings (`scriptHandler.py:72-80`). The old binding therefore does nothing, and the user rebinds the gesture in Input Gestures under the WorldVoice category.

No NVDA-defined key changes, no profile becomes invalid, and NVDA reads none of the renamed keys itself: `[WorldVoice]` is WorldVoice's own section, and the renamed driver ids are `useConfig=False`.

## 5. Design: from a core field to its stored key

**One derivation, in the core** (`pipeline/settings.py`):

```python
# A word that NVDA spells in camelCase where a field name writes it as one word: NVDA's own
# keys say sayAll (config/configSpec.py:53, sayAllReadingUnit).
STORED_WORDS = {"sayall": "sayAll"}


def stored_key_for(name: str) -> str:
	"""The nvda.ini key for a snake_case name of the table: NVDA camelCase (refactor9 §6.1 rule 3)."""
```

`stored_key_for("number_mode") == "numberMode"`, `stored_key_for("sayall_wait_factor") == "sayAllWaitFactor"`, `stored_key_for("scope") == "scope"`. `PipelineSettingSpec` gains a read-only property `stored_key` (`stored_key_for(self.key)`). It is the key of a stored entry in `[WorldVoice][pipeline]`, and the key of the log switch of a stage named after the entry. An explicit per-entry field was the alternative. It would repeat every name, and the guard would still have to check the derivation. The one word that does not follow mechanically gets the word table instead. *Decided by orchestrator with the recommended default; user may override before merge.*

**Pipeline section.** Only the NVDA-facing reads and writes change:

- `PIPELINE_CONFSPEC` is keyed by `spec.stored_key` (`pipeline/settings.py:278`).
- `ConfigPipelineRepository.load` reads each entry's `stored_key` with `read_stored` and returns `PipelineSettings` by field key (`:377-381`).
- `ConfigPipelineRepository.save` takes values by field key and writes each one under its entry's `stored_key` (`:383-386`).
- `read_stored`'s warning names the stored key, the one the user finds in nvda.ini (`:341-361`).

Everything above the repository (`PipelineSettingsService.update(**changes)`, the panels, `depends_on`, `PIPELINE_CONFIG_KEYS` in `ui/voicePanel.py:221`) keeps field keys.

**Log section** (`pipeline/registry.py`):

- each `Stage` binds its handler with the stored switches of its `also_logged_by` keys and its log key (`:142-144`);
- `_run_logged` falls back to the stored switch of its label (`:94`);
- `LOG_SWITCHES` holds the stored switches, in stage order (`:160-167`). The confspec line `__init__.py:83` and the Log Record panel then use them unchanged.

In `addon/globalPlugins/WorldVoice/panels/log.py`, `_STAGE_LOG_LABELS` (`:17-22`) is keyed by the stored switches `applySpeechDictionaries`/`speechViewer`, and `_SETTING_NAMES` (`:25`) by `spec.stored_key`. A switch named after a setting still shows that setting's name. The panel's checkbox attributes become `<switch>CheckBox` (`addon/globalPlugins/WorldVoice/panels/base.py:48-56`). Those are not stored, and their spelling follows. CSV rows and debug messages keep the log key.

**Detection, main-locale flags, driver ids, scripts.** These are literal identifiers in code, so they are plain renames of the literal (§2.1). `DetectionScript.config_key` and `_TIMING_KEY` keep their names and hold the new strings. The driver ids are literal `driver_id=` strings, which the guard checks against `stored_key` (§6).

**Test infrastructure.** `tests/nvda_stubs.py:_spread_defaults` (`:91-117`) rebuilds a fresh profile's defaults from the source AST. It must produce the stored keys, so it executes `STORED_WORDS` and `stored_key_for` from `pipeline/settings.py` and applies them to the table keys and stage log keys. `tests/test_config_stub.py` keeps cross-checking the pipeline section against the real `PIPELINE_CONFSPEC`.

## 6. Guard end state

`tests/test_naming_layers.py`:

- The script rename deletes the two `TRANSITIONAL_47D` entries (deletion only). A later commit deletes `TRANSITIONAL_47D`, its comment and `test_only_stored_identifiers_wait`, and checks `INTERFACE_NAMES` alone.
- Rule 3 of the docstring becomes "stored identifiers use NVDA camelCase". Rule 2's list of unreadable interfaces drops "a stored setting id" and keeps `rateBoost`. The closing paragraph says no list waits for a later phase.
- A new check, `test_stored_identifiers_use_nvda_camel_case`, collects every stored identifier WorldVoice defines and requires each to fullmatch `MIXED_CASE`:
  - every section and key of a fresh profile's `[WorldVoice]` (`nvda_stubs.worldvoice_conf()`, which reads the confspec, `DETECTION_CONFSPEC`, the pipeline table and `STAGES`);
  - every voice parameter key (`VOICE_PARAMETERS`, the `voices` `__many__` keys);
  - every driver setting id in `SynthDriver.allSupportedSettings` (`pipeline_harness.load_synth`);
  - every `script_` method name in the host layer, after the prefix (AST).
  Three explicit tables justify what is not checked or checked differently:
  - `PROPER_NOUN_SECTIONS = {"WorldVoice": …}`: the root is outside the walk.
  - `DATA_SECTIONS = {"role": …, "engine": …, "voices": …}`: their keys are data. The check asserts that a fresh profile has no key in them, i.e. the spec gives only `__many__` or nothing.
  - `NVDA_SETTING_IDS = {"voice", "variant", "rate", "rateBoost", "pitch", "inflection", "volume"}`: each must be a setting id in NVDA's `synthDriverHandler.py`, read from `ref/nvda`.
  A self-test runs the collector's checker on `DetectLanguageTiming`, `number_mode` and `numberMode`. The first two must be reported, the third not.
- `tests/test_settings_table_guard.py` gains `check_stored_names`, with broken-table cases:
  - every `stored_key` fullmatches mixedCase;
  - a `driver_id` is the entry's `stored_key` unless it is one of the coined ids `numlan`/`nummod` (`CODED_DRIVER_IDS`, §3);
  - a choice driver id is one lowercase token, because NVDA looks up `available{id.capitalize()}s`.
  `uwv` is not a table entry. The naming check covers it as mixedCase.

## 7. Translations and docs

- No msgid changes. No `#.` or `msgctxt` in `addon/locale/*/LC_MESSAGES/nvda.po` names a renamed key or id (`grep` for every old name over the seven `.po` files finds none). No `# Translators:` comment changes, because no translatable string changes.
- No readme or changelog edit (§4). `buildVars.py` names none of them.

## 8. Test plan

- **Per rename task.** Before the rename, the tests that pin the new name (new or renamed assertions) fail red. After `ren.py` they pass. The full suite stays at the baseline count, 0 skipped.
- **New tests:**
  - `tests/test_pipeline_settings_service.py::test_stored_key_is_nvda_camel_case_of_the_field` (parametrized: `scope`, `number_mode`, `sayall_wait_factor`, `unspaced_script_space_wait_factor`), and `::test_every_entry_reads_its_stored_key_from_the_derivation`.
  - `::test_repository_reads_and_writes_stored_keys`: a profile holding `numberMode = group` and `sayAllWaitFactor = 30` loads them into `number_mode`/`sayall_wait_factor`. `update(number_mode="number")` writes `numberMode` and writes no `number_mode`.
  - `::test_old_snake_case_keys_read_as_defaults`: a profile holding only the old `number_mode = group` loads `number_mode == "value"`. `update` leaves the old key untouched.
  - `tests/test_pipeline_filters.py`: the log-switch tests read the camelCase switch, and an old snake_case switch alone does not turn logging on.
  - `tests/test_detection_settings.py` and `tests/test_main_locale_policy.py`: an old PascalCase key alone reads as the default (the section stub holds both spellings).
  - The guards of §6, each with a deliberately broken input that must be reported.
- **Existing coverage through the new names**: Voice panel dependencies and creation order (`test_voice_settings_panel.py`, `test_panel_layout.py`), settings order and ring (`test_settings_order.py`), synth pipeline properties (`test_worldvoice_pipeline_settings.py`), Speech Pipeline and Log Record panels (`test_pipeline_panels.py`, `test_settings_panels.py`), detection (`test_detection_settings.py`, `test_unicode_panel.py`, `test_language_detector.py`), global plugin scripts (`test_global_plugin_menu.py`).
- Full suite: baseline 3318 passed, 0 skipped. Afterwards 3318 plus the new cases, 0 skipped. The plan pins each count.
- No mutmut: the only logic added is the four-line derivation, which the parametrized test pins word by word.
- Windows/NVDA: not verified on Linux. A manual check after release: upgrade over a profile with old keys. NVDA starts without a config error. The reset settings show defaults and can be saved, and the old keys remain in nvda.ini. Each gesture can be rebound under Input Gestures, WorldVoice.

## 9. Proof of the renames

The scripts live in the session scratchpad `p47d/`, copied from phase 47c's `p47c/` and extended. They are recorded in the ledger.

- `ren.py` applies a group's rules by AST or token position. A new `strings` rule renames every word occurrence of OLD in the file's string tokens. Line-scoped `text` rules handle files where the same spelling is also a core field name in a string, such as `getattr(settings, "number_mode")`.
- `check.py REV <group>` proves per file that:
  - the token streams differ only by the group's `OLD → NEW` pairs, in order;
  - when ruff re-wraps, the ASTs and the ordered comments differ only so;
  - a string constant changes only by replacing word occurrences of a listed OLD with its NEW.
  It counts every OLD left in HEAD against the group's `KEPT` table, with a reason for each entry. It fails on any changed file outside the group, except deletions in the guard.
- Tasks 6 and 7 switch the repository and the registry to `stored_key`, which is not a rename. Their groups list each such code change as an explicit `EDITS` entry, a `(before, after)` snippet that must occur exactly once. `check.py` applies the EDITS to REV and then requires the rest of the diff to be a pure rename of listed pairs. The code change and the test-fixture renames it forces then share a commit that is still fully accounted for.
- `prescan.py` lists every occurrence of the OLD strings before a rename. It covers string tables, `getattr` strings, monkeypatch targets, guard tables, the readmes, the `.po` files and `buildVars.py`.

## 10. Open questions

None blocking. Defaults taken (the user may override before merge):

1. `uwv`, `numlan`, `nummod` stay (§3). *Decided by orchestrator with the recommended default; user may override before merge.*
2. Stored keys come from one derivation with a word table (`sayall → sayAll`), not from a per-entry field (§5). *Decided by orchestrator with the recommended default; user may override before merge.*
3. `VoiceSnapshot.rateBoost` stays in `INTERFACE_NAMES` (§3). *Decided by orchestrator with the recommended default; user may override before merge.*
4. The pipeline CSV and debug messages keep the snake_case log key (§3). *Decided by orchestrator with the recommended default; user may override before merge.*
