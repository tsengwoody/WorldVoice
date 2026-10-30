# Voice engine filter in NVDA's Voice settings panel

Date: 2026-10-30.
Base: `master` `650291e` (P55 merged). Branch: `feat/voice-engine-filter`. Normal flow (DEVELOPMENT_WORKFLOW.md §3); not the complex flow: no byte-exact target, no handed-off plan.
Source: brainstorming with the user, 2026-10-30.

| Item | Decision |
|---|---|
| R1: an engine list directly above the Voice list, listing every engine that owns at least one available voice, shown even with one engine | Decided by the user (2026-10-30) |
| R2: the engine list filters the Voice list; WorldVoice's `availableVoices` is the filtered list, so the settings ring cycles only within the current engine | Decided by the user (2026-10-30) |
| R3: the NVDA-facing voice text drops the trailing ` [engine]`; the Speech Role panel keeps it | Decided by the user (2026-10-30) |
| R4: choosing an engine switches the voice at once to that engine's voice for NVDA's interface language, else the engine's first voice | Decided by the user (2026-10-30) |
| D1: the current engine is derived from the current voice; nothing new is stored | Decided by orchestrator with the recommended default; user may override before merge |
| D2: the engine setting is not in the settings ring | Decided by orchestrator with the recommended default; user may override before merge |
| D3: the engine list shows the internal engine names (`Espeak`, `OneCore`, ...) | Decided by orchestrator with the recommended default; user may override before merge |
| D4: label `Speec&h engine`, zh_TW 「語音引擎(&H)」: `&E` is taken (§5) | Decided by orchestrator with the recommended default; user may override before merge (Q4) |
| D5: two voices whose texts would be equal after dropping the suffix keep the suffix (§3.2) | Decided by orchestrator with the recommended default; user may override before merge (Q2) |
| D6: existing voice dictionaries are copied to the new file names (§3.7) | Decided by orchestrator with the recommended default; user may override before merge (Q1) |
| D7: a primary-language step in the voice choice of R4 (§3.3) | Decided by orchestrator with the recommended default; user may override before merge (Q3) |
| D8: `availableLanguages` keeps listing every engine's languages (§3.4) | Decided by orchestrator with the recommended default; user may override before merge |
| D9: the Speech Role panel sets the main voice through NVDA's `changeVoice` (§3.6) | Decided by orchestrator with the recommended default; user may override before merge |

Line conventions: `synth:` is `addon/synthDrivers/WorldVoice/__init__.py`; `manager:` `voices/manager.py`; `catalog:` `voices/catalog.py`; `roles:` `voices/roles.py`; `policy:` `voices/mainLocalePolicy.py`; `panel:` `ui/voicePanel.py`; `adapter:` `bridge/engineAdapter.py`; `base:` `driver/__init__.py` (all under `addon/synthDrivers/WorldVoice/`); `role.py:` and `presenter:` are `addon/globalPlugins/WorldVoice/panels/role.py` and `addon/globalPlugins/WorldVoice/rolePresenter.py`. `sdh:` is `ref/nvda/source/synthDriverHandler.py`, `sd:` `ref/nvda/source/gui/settingsDialogs.py`, `ring:` `ref/nvda/source/synthSettingsRing.py`, `as:` `ref/nvda/source/autoSettingsUtils/autoSettings.py`.

## 1. Problem, goals, non-goals

### Problem

WorldVoice reports every voice of every opened engine to NVDA as one list: `_getAvailableVoices` returns `manager.voice_infos` (`synth:393-394`, `manager:272-274`), the whole catalog sorted by engine, language and name (`catalog:36`, `:40`). With several engines (OneCore, SAPI5, eSpeak, RHVoice, VE, Cerence, plugins such as Neural) the Voice list holds hundreds of entries, and the settings ring (NVDA+Ctrl+arrows) cycles through all of them. Each entry ends with ` [<engine>]` so the user can tell the engines apart: the base `voiceInfoToMetadata` builds `f"{voice.displayName} - {langDescription} [{cls.engine}]"` (`base:39-56`, `:54`); the VE and Cerence outer wrappers build `f"{voice.id} - {langDescription} [{cls.engine}]"` (`driver/VE/__init__.py:935-949`, `driver/Cerence/__init__.py:947-961`). The adapter copies it into `VoiceSpec.description` (`adapter:117-134`, `:127`), which becomes both NVDA's `VoiceInfo.displayName` (`catalog:40`) and the Speech Role panel's voice text (`presenter:42-48`).

### Goals

- R1–R4 above.
- The Speech Role panel's voice list (`presenter:42-48`, all engines) is unchanged and keeps ` [engine]`.
- The engine interface for bundled wrappers and external plugins is unchanged: no new metadata key, no new `Voice` attribute (`tests/test_plugin_voice_contract.py`, `tests/test_engine_interface_guards.py`).

### Non-goals

- No change to which engines load (the Speech Engine panel, which restarts NVDA, `addon/globalPlugins/WorldVoice/panels/engine.py:1`).
- No engine labels from manifests (`engineRegistry/discovery.py:98`); internal names (D3).
- No change to the role-pruning timing of `keepMainLocaleEngineConsistent` (Q5).
- No change to the inner drivers (`driver/*/driver/*`), the outer wrappers' metadata, sonic or the generated Unicode data.

### What NVDA users hear and see

- NVDA's Voice settings panel with WorldVoice: a new combo box "Speech engine" is the first control of the synth settings, right above "Voice". It lists, for example, `Espeak`, `OneCore`, `RHVoice`, `SAPI5`. It shows the current voice's engine.
- The Voice list shows only that engine's voices, without the bracket: "Microsoft Hanhan - Chinese (Taiwan)" instead of "Microsoft Hanhan - Chinese (Taiwan) [OneCore]" (except D5's rare duplicates).
- Choosing another engine (arrowing through the closed combo box counts, as for Voice) stops speech, switches the voice at once (R4), updates the Voice, Variant and parameter controls, and NVDA reads the new engine name in the new voice. Focus stays on the engine list.
- The settings ring's Voice entry cycles only through the current engine's voices and reads them without the bracket. The ring has no engine entry; to change engine, use the Voice settings panel.
- Cancel restores the previous voice, so the engine follows it. OK or Apply saves the voice as today; nothing else is stored.
- The WorldVoice Speech Role panel is unchanged, voice texts keep ` [engine]`.
- Voice dictionaries keep working (§3.7).

## 2. How NVDA builds the panel and the ring (findings)

These shape the design; F1, F3, F4, F5, F6 and F8 contradict a naive "add a setting and filter the list" implementation.

- **F1 `availableVoices` is cached.** `SynthDriver._get_availableVoices` stores the first `_getAvailableVoices()` result in `self._availableVoices` and returns it forever (`sdh:274-277`). WorldVoice overrides only `_getAvailableVoices` (`synth:393-394`) and never clears the cache (no add-on code names `_availableVoices`). A filtered list returned through `_getAvailableVoices` would freeze on the first engine. The synth must override the `_get_availableVoices` property itself (§3.4).
- **F2 NVDA refreshes values, WorldVoice also rebuilds lists.** NVDA's `updateDriverSettings(changedSetting)` hides unsupported rows, then for every supported setting except `changedSetting` calls `_updateValueForControl` or creates the control (`sd:1546-1575`). NVDA's `_updateValueForControl` only re-selects a string setting from the cached `_<id>s` list (`sd:1601-1619`); it never rebuilds the choices. WorldVoice's panel override already re-reads `available<Id>s` and calls `SetItems` (`panel:227-263`, `:238-254`), so the Voice list *is* rebuilt whenever `updateDriverSettings` runs with another `changedSetting`, provided `availableVoices` is fresh (F1).
- **F3 Only "voice" gets NVDA's voice-change treatment.** `StringDriverSettingChanger` cancels speech, calls `changeVoice` and `updateDriverSettings(changedSetting="voice")` only when `setting.id == "voice"`; any other string setting is a bare `setattr` (`sd:1340-1356`). An engine setting therefore needs its own changer (§3.5), or the Voice list, Variant, parameters and the ring would not follow.
- **F4 The ring snapshots each list.** A ring `StringSynthSetting` reads `available<Id>s` once and stores it as an instance attribute (`ring:75-77`; `Getter` is a non-data descriptor, `ref/nvda/source/baseObject.py:28-37`, `:106-107`). The ring rebuilds its settings only in `updateSupportedSettings` (`ring:197-240`), which `changeVoice` calls (`sdh:439-449`). A voice change that bypasses `changeVoice` leaves the ring with the old engine's list; `_get_value` then returns `None` for the new voice (`ring:86-90`) and `increase` fails on `None + 1` (`ring:38-41`). Today the Speech Role panel sets `synth.voice` directly (`role.py:39-43`, called from `presenter:138-141`), so §3.6 routes it through `changeVoice`.
- **F5 NVDA's initial ring position counts non-ring settings.** `_get_initialSettingsRingSetting` returns the index of `rate` in `supportedSettings` (`sdh:417-429`), but the ring indexes its own list, which skips `availableInSettingsRing=False` settings (`ring:130`, `:208-219`, `:232`). With a non-ring engine setting placed first, the ring would start one entry after Rate. WorldVoice overrides it (§3.4).
- **F6 NVDA names voice dictionaries after the voice text.** `VoiceDictionary.load` uses `synth.availableVoices[synth.voice].displayName` and `createVoiceDictFileName(synth.name, voice)` = `"WorldVoice-<filterFileName(text)>.dic"` under `WritePaths.voiceDictsDir/WorldVoice/` (`ref/nvda/source/speechDictHandler/types.py:330-344`, `ref/nvda/source/speechDictHandler/dictFormatUpgrade.py:50-58`; the same in NVDA 2024.1's `loadVoiceDict`, `git show release-2024.1:source/speechDictHandler/__init__.py:146-161`). WorldVoice applies that dictionary in its pipeline (`pipeline/registry.py:56`). Dropping the bracket (R3) renames every WorldVoice voice dictionary file: without §3.7 a user's existing voice dictionaries silently stop applying. Voices that differ only by engine (for example a voice id shipped by both VE and Cerence, whose texts are `"<id> - <language> [VE]"` and `"... [Cerence]"`) would also share one dictionary (§3.2, D5).
- **F7 `get_voice_name_for_language` is the role lookup.** It returns the role voice configured for the language (`manager:295-299`, `roles:34-42`, which tries the full locale then the primary language) or else the *current* voice; it never matches voice languages. The only language matching is `_get_default_voice_spec`: the first catalog voice whose `language` equals `getLanguage()` exactly, else the first voice (`manager:208-213`). NVDA's interface language is often a bare language (`languageHandler.getLanguage`, `ref/nvda/source/languageHandler.py:440-441`, e.g. `en`, `de`), while most voices carry a locale (`en_US`), so exact matching alone usually falls through to the first voice. §3.3 combines the role lookup and the exact match, restricted to the engine, and adds a primary-language step (D7, Q3).
- **F8 NVDA's `languageIsSupported` reads `availableVoices`.** `languageIsSupported` (`sdh:339-362`) iterates `availableLanguages`, which is built from `availableVoices` (`sdh:259-260`). NVDA uses it to report "<language> (not supported)" when reading language changes (`ref/nvda/source/speech/languageHandling.py:39-47`) and in the report-caret-language script (`ref/nvda/source/globalCommands.py:5445-5452`). A filtered `availableVoices` would make WorldVoice claim it cannot speak languages it speaks through other engines' role voices. §3.4 keeps `availableLanguages` on the whole catalog (D8).
- **F9 Cancel restores through `loadSettings`.** NVDA's `onDiscard` unbinds every `<id>List` combo's `EVT_CHOICE` and calls `loadSettings()` (`sd:1621-1628`); WorldVoice's `loadSettings` runs NVDA's (`synth:287-291`), which calls `changeVoice(self, <saved voice>)` (`sdh:386-399`). The engine, derived from the voice (D1), follows. `saveSettings` skips settings with `useConfig=False` (`as:156-166`), `loadSettings` skips them too (`sdh:401-404`, `as:200-202`), and the config spec omits them (`as:130-139`).
- **F10 A saved voice is never outside the filtered list.** The filter is the current voice's engine (D1), so `self.voice` is always in `availableVoices`; `saveSettings` writes `self.voice`. A saved voice of an engine that is no longer loaded raises `LookupError` in `_set_voice` (`manager:188-192`), and NVDA repairs the config to `self.voice` (`sdh:393-399`); the engine follows that voice.

## 3. Design

### 3.1 The engine is a WorldVoice driver setting

`engine` is a `DriverSetting` of the WorldVoice synth, `useConfig=False`, `availableInSettingsRing=False`, listed first in `_driverSettings` (`synth:117-139`), with `_get_availableEngines`, `_get_engine` and `_set_engine`.

Why a driver setting, not a WorldVoice-only panel control:

- NVDA's mixin then makes the combo box, its label, its accelerator, its Tab order and its row position (`sd:1462-1515`, `:1577-1590`). WorldVoice's `updateDriverSettings` creates every row in `allSupportedSettings` order before NVDA's pass (`panel:95-142`); listed first, the engine row is row 0 and its combo box comes before Voice in Tab order (`lastControl`, `sd:1512-1514`). No placement code is needed.
- NVDA's Cancel already unbinds and restores it (`sd:1621-1628`, F9), and `refreshGui` drops it with the other driver rows when the synth changes (`sd:1633-1646`).
- It needs nothing from the pipeline table machinery: `PIPELINE_SETTINGS` (`pipeline/settings.py`) holds pipeline settings stored in the pipeline config, and `panelLayout.py` places controls that are *not* driver settings (`ui/panelLayout.py:95-113`). The engine is neither stored nor a pipeline setting.
- `useConfig=False` keeps it out of `nvda.ini` (F9), as D1 requires, and the stored-id naming rule is met anyway (`engine`: lowercase, no underscore, `tests/test_naming_layers.py:25-30`).
- The id `engine` gives NVDA's derived name `availableEngines` (`sd:1476-1487` uses `f"available{setting.id.capitalize()}s"`); an id such as `voiceEngine` would become `availableVoiceengines`. No NVDA code reads a synth attribute `engine`.

### 3.2 Core: per-engine NVDA voice lists (`voices/engineFilter.py`, new; `voices/catalog.py`)

A new NVDA-free core module `voices/engineFilter.py` (core layer, snake_case; imports only `..locales` and `..runtime.models`):

- `nvda_voice_texts(specs: Iterable[VoiceSpec]) -> dict[str, str]`: voice name to the text NVDA shows.
  1. Candidate: `spec.description` minus a trailing `f" [{spec.engine}]"` when it ends with exactly that; otherwise `spec.description` unchanged. So third-party plugins that add no suffix, or a different one, keep their text; a suffix naming another engine is kept.
  2. The candidate is used unless another voice has the same candidate, or another voice's `description` equals the candidate; then the voice keeps its full `description` (D5).
  - Property: two voices with different descriptions never get the same text (both shortened: equal candidates are excluded by rule 2; one shortened, one full: excluded by rule 2's second clause; both full: their descriptions differ). Voices that already shared a description keep sharing it, as today.
- `pick_engine_voice(specs, engine, language, role_voice) -> str` (§3.3).
- `plan_dictionary_copies(renames, existing) -> list[tuple[str, str]]` (§3.7).

`VoiceCatalog` (`catalog:23-46`) gains two immutable fields filled in `from_specs`:

- `engines: tuple[str, ...]`: the distinct `spec.engine` values in table order (the table is sorted by engine first, `catalog:36`), so the engine list follows the order the Voice list grouped them in until now.
- `engine_voice_infos: Mapping[str, OrderedDict[str, VoiceInfo]]`: per engine, `VoiceInfo(spec.name, nvda_text, spec.language)` in table order (a `MappingProxyType` over per-engine `OrderedDict`s, which stay mutable on purpose like `voice_infos`, `catalog:27`).

`voice_infos` stays as it is: every voice, full description. It is the validation set of `default_voice_name` and `get_voice_name_for_language` (`manager:190`, `:297`) and keeps its current meaning. `EMPTY_CATALOG` gets `engines == ()` and an empty mapping.

`VoiceManager` (`manager:34`) exposes, without new state:

- `engines` → `catalog.engines`;
- `engine_of(voice_name)` → `get_voice_spec(voice_name).engine` (`manager:168-169`);
- `voice_infos_for_engine(engine)` → `catalog.engine_voice_infos[engine]`, raising `LookupError` for an unknown engine;
- `voice_name_for_engine(engine, language)` → `pick_engine_voice(self.table, engine, language, self.roles.voice_for(language))`.

### 3.3 Which voice an engine switch picks (R4, D7)

`pick_engine_voice(specs, engine, language, role_voice)`, over the engine's voices in table order:

1. `role_voice`, when it is a voice of `engine`: the role lookup `get_voice_name_for_language` uses (`manager:295-299`, `roles:34-42`), restricted to the engine.
2. The first voice whose `language` equals `language`: `_get_default_voice_spec`'s exact match (`manager:208-213`), restricted to the engine.
3. The first voice whose `primary_language(language)` equals `primary_language(language)` of the request (`locales.py:8-15`; it also folds `-`/`_` and case). New (D7): without it an `en` or `de` interface (F7) never matches an `en_US` or `de_DE` voice.
4. The engine's first voice (R4's fallback).

An engine with no voices cannot be listed (R1), so the function raises `LookupError` for it; the setter never passes one (§3.4).

With the default `keepMainLocaleEngineConsistent = true` (`confspec.py:20`) every role voice belongs to the current engine (`policy:35-39`, pruned in `manager:245-246`), so step 1 only matters with that option off.

### 3.4 The synth (`synth:`)

- `EngineSetting()`: `DriverSetting("engine", _("Speec&h engine"), availableInSettingsRing=False, useConfig=False)`, with the translator comment of §5. `_driverSettings` puts it before `VoiceSetting()` (`synth:119`); `supportedSettings` and `allSupportedSettings` both list it (`synth:141-148`).
- `_get_availableEngines()`: an `OrderedDict` of `StringParameterInfo(engine, engine)` for `manager.engines` (D3).
- `_get_engine()`: `manager.engine_of(self.voice)`. It reads `self.voice`, not the default voice instance, so it stays consistent with `_get_voice`'s early `_voice is None` branch (`synth:396-399`) and `availableVoices[self.voice]` is always valid (NVDA's `_get_language`, `sdh:253-254`; F10).
- `_set_engine(value)`: when `value == self.engine`, nothing. An engine not in `availableEngines` raises `LookupError` before anything changes (the phase-21 N14 rule for setters). Otherwise `changeVoice(self, manager.voice_name_for_engine(value, languageHandler.getLanguage()))`, NVDA's `synthDriverHandler.changeVoice` (`sdh:439-449`): it sets the voice through `_set_voice` (`synth:401-408`, no engine stop, as that comment requires), rebuilds the ring (F4) and loads the new voice's dictionary (F6). No speech cancel in the setter (`synth:403-405`); the panel cancels (§3.5).
- `_get_availableVoices()` overrides NVDA's caching property (F1): `manager.voice_infos_for_engine(self.engine)`, recomputed on every read (two dictionary lookups; `_get_language` reads it per utterance through `self.language`, `synth:255`, `:354`). `_getAvailableVoices` returns the same for any caller of the old method. Nothing sets `_availableVoices`.
- `_get_availableLanguages()` overrides NVDA's (`sdh:259-260`): the languages of `manager.voice_infos` (every engine), so `languageIsSupported` answers as it does today (F8, D8).
- `_get_initialSettingsRingSetting()` overrides NVDA's (F5): over `supportedSettings` filtered to `availableInSettingsRing`, the index of `rate`, or `0` without rate when any ring setting exists, else `None` (NVDA's own fallbacks, `sdh:417-429`, counted in the ring's list).

### 3.5 The Voice panel (`panel:`)

- Override `_makeStringSettingControl(setting, settingsStorage)`: call NVDA's, and for `setting.id == "engine"` replace the combo box's handler: `self.engineList.Unbind(wx.EVT_CHOICE)` then bind `_EngineSettingChanger(settingsStorage, setting, self)`. Exactly one `EVT_CHOICE` handler stays on the combo box, as NVDA's Cancel expects (`sd:1623-1626`). NVDA reaches the override through `_getSettingMaker` (`sd:1592-1599`).
- `_EngineSettingChanger(StringDriverSettingChanger)` (`sd:1333-1356`), mirroring NVDA's voice branch (`sd:1343-1350`): `evt.Skip()`; `speech.cancelSpeech()`; `setattr(self.driver, "engine", self.container._engines[evt.GetSelection()].id)` (§3.4 switches the voice through `changeVoice`); `self.container.updateDriverSettings(changedSetting="engine")`. The refresh rebuilds the Voice and Variant lists (F2), shows or hides Rate boost and Inflection for the new voice and updates the sliders, and leaves the engine combo box (focused) alone (`sd:1564-1566`).
- No other panel change. A voice change from the Voice list refreshes the engine combo box through the existing `_updateValueForControl` (it is not the changed setting); its list and selection stay the same.
- The panel class is installed only while WorldVoice runs (`synth:188-192`); another synth never lists `engine`.

### 3.6 Speech Role panel sets the main voice through `changeVoice` (`role.py:39-43`, D9)

`setMainVoice` replaces `current.voice = name` with `synthDriverHandler.changeVoice(current, name)`, then writes the config as today. When "keep main and locale speech role consistent" moves the main voice to another engine (`presenter:138-141`), the ring and voice dictionary follow (F4, F6). Before, the ring kept a stale snapshot, which the filter would turn into a failing ring step. User-visible side effect: the voice dictionary now follows a main-voice change made in the Speech Role panel (it did not before).

### 3.7 Voice dictionary continuity (D6, Q1)

On startup, right after the voice manager is built (`synth:218-235`) and before NVDA's `initSettings` loads the first voice dictionary (`sdh:490-495`, `:364-385`), the synth copies old voice dictionaries to the new names:

- For every catalog voice whose NVDA text differs from its description: old = `createVoiceDictFileName(self.name, description)`, new = `createVoiceDictFileName(self.name, nvda_text)` (NVDA's own naming, `dictFormatUpgrade.py:50-58`), in `WritePaths.voiceDictsDir/<synth name>` (`ref/nvda/source/NVDAState.py:59`; available since NVDA 2023.2, below the add-on minimum 2024.1, `buildVars.py:39`).
- `plan_dictionary_copies(renames, existing)` (core, pure): copy when the old file exists and the new one does not; skip pairs whose old and new names are equal; skip every pair of a new name that two old names map to (`filterFileName` can merge texts), rather than guess.
- The directory is listed once; a missing directory means nothing to do. Copy (not move) with `shutil.copy2`, so a downgrade still finds the old file. Never overwrite.
- Skipped when NVDA runs as the launcher, as NVDA's own dictionary upgrade is (`dictFormatUpgrade.py:61-67`).
- Each failure is logged (`log.error(..., exc_info=True)`) and the startup continues; it is never raised.
- Known limitation: if D5 later changes a voice's text (for example the user enables Cerence beside VE, or removes it), the dictionary file name changes back or forth; the copy rule keeps the newer file when both exist, so edits made under the other name are not merged.

### 3.8 What stays unchanged

- Engine wrappers and plugins: metadata (`base:39-56`, VE, Cerence) and `VoiceSpec.description` (`adapter:127`) keep ` [engine]`; the NVDA text is derived in the core (§3.2). The Neural reference plugin uses the base metadata (`ref/Neural/Neural/__init__.py:5-8`) and is covered by rule 1.
- The Speech Role panel's voice texts (`presenter:42-48`, from `manager.table` descriptions): R3.
- `keepMainLocaleEngineConsistent` and `keepMainLocaleVoiceConsistent`: an engine switch is a voice change through `default_voice_name` (`manager:188-195`), so `on_keep_engine_consistent` prunes the roles to the new engine (`manager:245-246`, `policy:35-39`) and `follow` assigns the main locale's role (`policy:63-65`), exactly as choosing that voice in the Voice list does today (Q5).
- `keepMainLocaleParameterConsistent`, the language detector (`manager.all_languages`, `synth:252-253`), `speechContext` (`synth:347-360`), speech, cancel and the scheduler.

## 4. Edge cases

- **One engine:** the engine list shows one entry (R1); choosing it does nothing.
- **Engine with voices but none in the interface language:** the engine's first voice (§3.3 step 4), in table order (language, then name).
- **Saved voice of an engine no longer loaded:** NVDA's repair (F10) picks `self.voice`; the engine follows.
- **Current engine disappears:** engines change only with a NVDA restart (the Speech Engine panel restarts NVDA); the previous case applies.
- **No voices at all:** `VoiceManager` raises and WorldVoice does not load (`manager:89-90`), as today.
- **Switching synth away and back:** a new synth instance; `initSettings` → `loadSettings` restores the saved voice (`sdh:364-385`), and the engine follows; the panel rebuilds its rows (`sd:1633-1646`).
- **Config profile switch:** `handlePostConfigProfileSwitch` calls `loadSettings(onlyChanged=True)` (`sdh:582-600`), which calls `changeVoice` when the profile's voice differs (`sdh:390-392`); the engine and the ring follow.
- **Cancel after an engine change:** F9. Role assignments pruned by the change are not restored (Q5, existing behavior).
- **Speech Role panel changes the main voice while NVDA's Voice panel is open:** the open panel keeps showing the old engine and list until it is refreshed (an existing kind of staleness: today its voice selection goes stale too). OK saves `self.voice`, the role-chosen voice, so nothing is lost.
- **Two engines expose voices with the same text:** D5 keeps their suffix.
- **A plugin whose description carries no suffix or another one:** shown unchanged.
- **Empty description:** unchanged (`""`), as today (`adapter:127`).

## 5. Panel layout and strings

- Order: Speech engine, Voice, Variant, Rate, ... (WorldVoice rows follow as today). Tab order the same; object navigation follows window creation order, also the same.
- NVDA reads: "Speech engine combo box OneCore" (label from `displayNameWithAccelerator`, `sd:1474`, `:1489-1494`). Help id: the generic `SpeechSettings` (`sd:1669-1684`).
- Accelerators: the Voice panel already uses `v a r t p i o` (NVDA's synth settings, `sdh:122-211`), `g l z n c b s x e m d u` (NVDA's other Voice panel controls, `sd:1734-1938`, among them `Sp&eech dictionaries:`), and WorldVoice's `Number &language`, `Number &mode` (`pipeline/settings.py:170`, `:184`). In NVDA's zh_TW translation `Sp&eech dictionaries:` is 「語音字典(&E):」 (`ref/nvda/source/locale/zh_TW/LC_MESSAGES/nvda.po`). So `&E` collides; `h` is free in both.

New string (`synth:`, `EngineSetting`):

```python
# Translators: Label for a setting in voice settings dialog: the speech engine whose voices
# the Voice list and the settings ring offer. Choosing one switches to a voice of that engine.
_("Speec&h engine")
```

zh_TW: 「語音引擎(&H)」 (the add-on already uses 語音引擎 for "Speech Engine", `addon/locale/zh_TW/LC_MESSAGES/nvda.po`). zh_HK the same; zh_CN 「语音引擎(&H)」. Translations follow DEVELOPMENT_WORKFLOW.md §6.

## 6. Settings, data, compatibility

- Nothing new in `nvda.ini` (`useConfig=False`, F9); no config spec change; no migration of settings.
- Voice dictionary files: §3.7 (copies, never deletes).
- Engine interface: unchanged (§3.8). The NVDA-facing text of a plugin voice changes only when its description ends with ` [<its engine>]`.
- NVDA versions: `changeVoice`, `StringDriverSettingChanger`, `WritePaths`, `createVoiceDictFileName`, `filterFileName` exist from 2024.1 to the reference NVDA (`git -C ref/nvda log -S`: `createVoiceDictFileName` 2017, `_WritePaths` 2023.2).
- Errors: `_set_engine` raises `LookupError` for an unknown engine before changing anything; the panel only offers listed engines. Dictionary copying never raises (§3.7).

## 7. Tests

Every test is written red first. Baseline: 3638 passed, 0 skipped.

### Unit (Linux)

- `tests/test_engine_filter.py` (new, core):
  - `nvda_voice_texts`: strips exactly ` [<engine>]`; keeps a description without suffix; keeps `"X [VE]"` on a `Cerence` voice; two engines with `"X [VE]"`/`"X [Cerence]"` both keep the suffix; a shortened text equal to another voice's description keeps the suffix.
  - Hypothesis: for generated specs (descriptions built from a small alphabet, optional `[engine]` suffixes, several engines), distinct descriptions give distinct texts; each text is the description or the description minus its own engine's suffix.
  - `pick_engine_voice`: the role voice of the engine wins; a role voice of another engine is ignored; exact language before primary language; primary language (`en` → `en_US`, `zh-TW` vs `zh_TW`) before the first voice; first voice otherwise; unknown engine raises `LookupError`. Hypothesis: the result is always a voice of the engine; with no role voice in the engine and an exact match present, the result has the exact language.
  - `plan_dictionary_copies`: copies old→new only when old exists and new does not; equal names skipped; a new name with two sources skipped.
- `tests/test_voice_catalog.py`: `engines` in table order without duplicates; `engine_voice_infos` per engine in table order with NVDA texts; `voice_infos` unchanged (full descriptions); `EMPTY_CATALOG.engines == ()`; the new fields are immutable.
- `tests/test_runtime_composition.py` (composition fixture): `voice_name_for_engine` uses the configured role and `get_language`; `voice_infos_for_engine` raises `LookupError` for an unknown engine.
- Synth (`tests/test_driver_ui_hooks.py` or a new `tests/test_engine_setting.py` on `pipeline_harness.load_synth`):
  - the engine setting is first, `useConfig` false, not in the ring; `availableEngines` lists the catalog's engines;
  - `engine` follows `voice`; `availableVoices` is the current engine's list and changes after a voice change of another engine (F1 regression: read it, change voice, read again); `_availableVoices` is never set;
  - `availableLanguages` lists every engine's languages;
  - `engine = <other>` calls `changeVoice` with the picked voice; the same engine changes nothing; an unknown engine raises `LookupError` and leaves the voice;
  - `initialSettingsRingSetting` is Rate's index in the ring list with the engine setting present.
- `tests/test_settings_order.py`: `STANDARD` starts with `engine`; the ring list is unchanged.
- `tests/test_voice_settings_panel.py`: the engine row is first and before Voice in Tab order; choosing an engine cancels speech, sets the engine, rebuilds the Voice list to the new engine's texts and selects the new voice, and leaves the engine control alone; the combo box has one `EVT_CHOICE` handler, ours; Cancel unbinds it and `loadSettings` restores the voice and with it the engine; another synth gets no engine row.
- `tests/test_role_panel.py`: `setMainVoice` calls `changeVoice` on the current synth and still writes the config; with no current synth it only writes the config.
- `tests/test_role_presenter.py`: `voices()` texts still end with ` [engine]`.
- `tests/test_plugin_voice_contract.py`: a Neural-style plugin's voice is shown without the suffix to NVDA and with it in the role list; a plugin overriding `voiceInfoToMetadata` without a suffix keeps its text.
- Dictionary copy (synth level, `tmp_path` as `voiceDictsDir`): copies an old file, never overwrites, skips under the launcher, logs and continues on an `OSError`.
- `tests/test_naming_layers.py` and `tests/test_hygiene_guards.py` pass unchanged (the new module is under `voices/`, a core path).

### Mutation

`voices/engineFilter.py` is core decision logic: add it to `[tool.mutmut] source_paths` (`pyproject.toml:45-65`) and run mutmut on Linux; record surviving mutants and why in the review.

### Windows / NVDA manual checklist (not verifiable on Linux)

1. Voice panel with OneCore, SAPI5, eSpeak, RHVoice enabled: "Speech engine" is the first control, NVDA reads its label and value; Shift+Tab from Voice lands on it; Alt+H focuses it (English and zh_TW).
2. Arrow through engines: speech stops, each engine is announced in its own new voice; the Voice list shows only that engine's voices without brackets; Variant/Rate boost/Inflection appear or hide as the voice supports.
3. Interface language zh_TW: choosing OneCore picks a zh_TW voice; an engine without a Chinese voice picks its first voice; interface English (`en`) picks an `en_*` voice.
4. Cancel: the previous voice and engine come back. OK: after a NVDA restart the voice and engine are the chosen ones.
5. Settings ring: Voice cycles only within the current engine, without brackets; Rate is the first entry after a NVDA restart; no engine entry.
6. A voice dictionary created before the update still applies after it (file copied); a VE and a Cerence voice with the same name keep separate dictionaries.
7. Speech Role panel: voice texts keep brackets; with "keep main and locale speech role consistent" on, assigning another engine's voice to the main locale changes the NVDA voice, the ring follows (NVDA+Ctrl+arrows works) and the engine shown in the Voice panel follows after reopening.
8. With "Report when switching to language is not supported" on (NVDA 2025.2+), a language spoken only by another engine's role voice is not reported as unsupported.
9. Neural plugin (if installed): listed as `Neural`; its voices without brackets in the Voice list.
10. Switch to another synth and back; switch configuration profiles with different voices: engine follows the voice each time.

## 8. Readme

Root `readme.md` and `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` (not `addon/doc/en/` or `.html`, build output):

- A short paragraph (Features or Notes): in NVDA's Voice settings panel, "Speech engine", above "Voice", chooses which engine's voices the Voice list and the settings ring offer; choosing an engine switches to that engine's voice for the NVDA interface language, or its first voice; voice names there no longer end with the engine in brackets, while the Speech Role panel still shows it.
- Changelog "Next update" bullet: **Speech engine list in the Voice settings panel**, same content, plus: voice dictionaries made for a voice before this update keep working.

## 9. Constraints

- Stage explicit paths only; check `git diff --cached --stat` before each commit; English `<type>: <summary>` messages with a body, no `Co-Authored-By`; prek hooks run on commit (ruff `==0.16.3`), never `--no-verify`; no push; no `git stash`; do not touch the main checkout.
- Never edit `driver/*/driver/*`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; do not add Neural to git; `ref` is a symlink, never staged.
- Engine drivers stay independently installable: nothing here touches a wrapper; shared code is core (`voices/`).
- Naming: `voices/engineFilter.py` is core (snake_case); the synth, `ui/` and the global plugin are host (mixedCase), `tests/test_naming_layers.py`.

## 10. Open questions (for the user; the spec proceeds with the recommended answer)

- **Q1 Voice dictionaries (F6, D6).** Dropping the bracket renames NVDA's voice dictionary file of every WorldVoice voice. (a) Copy existing dictionaries to the new names at startup (recommended); (b) accept that existing voice dictionaries stop applying and say so in the changelog.
- **Q2 Same text in two engines (D5).** (a) Those voices keep ` [engine]` in the Voice list, so each keeps its own dictionary (recommended); (b) always drop the bracket and let such voices share one voice dictionary.
- **Q3 Interface-language match (F7, D7).** (a) Role voice, exact language, then primary language (`en` matches `en_US`), then first voice (recommended); (b) exactly the existing logic, role voice then exact language then first voice, which with an `en`/`de` interface usually gives the first voice.
- **Q4 Accelerator (D4).** `&E` collides with NVDA's "Sp&eech dictionaries" (zh_TW 語音字典(&E)). (a) "Speec&h engine" / 「語音引擎(&H)」 (recommended); (b) another free letter (`f h j k q w y`).
- **Q5 Role pruning on an engine change (existing behavior).** With "keep main and locale engine consistent" on (the default), choosing another engine at once removes the locale roles of other engines, and Cancel does not bring them back; choosing another engine's voice in today's Voice list does the same. The engine list makes such browsing more likely. (a) Keep it for this feature and track a separate fix that prunes only on save (recommended); (b) fix it in this feature.

## 11. Verification

`python3 -m pytest -q tests` (passed/skipped vs 3638/0), `prek run --all-files`, `git diff --check`, the protected-path checks of DEVELOPMENT_WORKFLOW.md §7 (no output), mutmut on `voices/engineFilter.py`. Linux tests cover the controlled NVDA and wx boundaries only; NVDA on Windows, real engines and the voice dictionary files are verified only by §7's manual checklist.
