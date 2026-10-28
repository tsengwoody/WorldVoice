# Phase 40: synth `__init__.py` slimming, reduced scope (F3-2 + F3-3)

Date: 2026-10-27.
Base: `master` `4688473` (phase 44 merged). Branch: `phase40-synth-slimming`.
Source: round-9 review `storage/refactor9.md` §4.1 **F3** items 2 and 3, the §5 row for the confspec, the §6 row **P40**, the naming rule §6.1, and §7 items 13 and 14 (rejected); the user's scope decisions of 2026-10-27 relayed by the orchestrator.
Status: normal flow (DEVELOPMENT_WORKFLOW.md §3) with §3.2's "改名與搬移的證明": two pieces of code move to new modules, so each move gets its own commit and an order-sensitive move check. The complex flow's conditions (byte-exact target, hand-off plan) do not hold.

Paths are under `addon/synthDrivers/WorldVoice/` unless stated. NVDA paths are under `ref/nvda/source/`. Line numbers are at `4688473`.

## 1. Problem

`__init__.py` (530 lines) is the composition root of the synth. Two things in it are not composition:

**F3-2: the confspec is an import-time side effect between the imports and the driver class.**
`config.conf.spec["WorldVoice"] = {...}` (`__init__.py:69-86`) runs when the package is imported and spells three sections (`role`, `engine`, `log`) as literals, while the other four sections come from their owners (`DETECTION_CONFSPEC` from `languageDetection/settings.py:19`, `PIPELINE_CONFSPEC` from `pipeline/settings.py:298`, `VOICE_CONFSPEC` from `voices/settingsRepository.py:21`, `LOG_SWITCHES` from `pipeline/registry.py`). Four imports of `__init__.py` (`:35`, `:44`, `:49`, `:58`) exist only for it. The test stub `worldvoice_conf` reads the confspec from the AST of `__init__.py` (`tests/nvda_stubs.py:56-66`).

**F3-3: the number-language state is a small state machine inside the driver.**
`self._numlan` (`__init__.py:183`) and six members (`_get_availableNumlans`, `_isStoredNumberLanguage`, `_get_numlan`, `_numberLanguage`, `_set_numlan`, `_numlanDisplayName`, `:469-509`) keep the stored number language. Their rules (phase 35 spec §7.1; the review M2 decision pinned by `tests/test_worldvoice_speak.py:744-764`):
- a stored value is `FOLLOW`, `MAIN` or the locale of any installed voice (`voiceManager.all_languages`), else it reads as `FOLLOW` with a `debugWarning` (`:495-501`);
- the stored choice survives a voice or engine change that hides its locale (`:485-488`);
- speech uses the stored locale only while an offered voice speaks it (`voiceManager.languages`), else `FOLLOW` (`:490-493`);
- the choice list is the two follow values, each offered locale, then the stored hidden locale (`:469-479`).
Only the label lookup (`languageHandler.getLanguageDescription`, `:506-509`) and `StringParameterInfo` need NVDA; the rest needs only `languages`, `all_languages`, `FOLLOW` and `MAIN`.

## 2. Goals

1. **F3-2.** A new module `confspec.py` holds the confspec assembly as one function `installConfspec(conf)`, which sets `conf.spec["WorldVoice"]` to the same dict as today (same sections, same order, same values). `__init__.py` calls `installConfspec(config.conf)` once, at the place the assignment is today (after `addonHandler.initTranslation()`, before `WVStart`), and no longer imports the four owner names. *Decided by the user (2026-10-27): F3-2 in scope.*
2. **F3-3.** A new core module `voices/numberLanguageChoice.py` holds `NumberLanguageChoice`, the number-language state above. `SynthDriver` keeps NVDA's members (`_get_availableNumlans`, `_get_numlan`, `_set_numlan`, `_get_availableNummods`, `_numlanDisplayName`) and `_numberLanguage` as short forwards, and keeps the warning log and the NVDA label lookup. *Decided by the user (2026-10-27): F3-3 in scope.*
3. Each move is a separate commit that passes an order-sensitive move check (§7.2).
4. New tests: `test_confspec_sections` (the sections and their owners), unit tests of `NumberLanguageChoice`, and a guard that `voices/numberLanguageChoice.py` imports only the root `numberLanguage.py`.

## 3. Non-goals

- **Rejected by the user (refactor9 §7 items 13, 14):** descriptors replacing the `_get_x/_set_x` parameter forwards; `resolve_voices()` around the language-command steps of `speak()`.
- No change to driver setting ids or stored keys (`numlan`, `nummod`, `uwv` and the `[WorldVoice]` keys stay); no migration.
- The root `numberLanguage.py` stays as is: standard library only, pinned by `tests/test_pipeline_structure.py:72-83`.
- `_PipelineSetting` and its `for _spec in PIPELINE_SETTINGS` loop (`__init__.py:512-530`) stay in `__init__.py`: they bind the driver class, they are not configuration.
- No readme or changelog edit (no user-visible change); no new translatable string.
- Python 3.11 floor (NVDA 2024.1, `buildVars.py:39`): no 3.12+ syntax.

## 4. NVDA user's view

Nothing changes. The `[WorldVoice]` section has the same keys and defaults; the Voice panel and the settings ring list the same number languages in the same order; an unknown stored number language still reads as "Follow surrounding text language" with the same debug warning.

## 5. Design

### 5.1 `confspec.py` and where it is called

```python
def installConfspec(conf) -> None:
	conf.spec["WorldVoice"] = {...}  # the dict of __init__.py:69-86, unchanged
```

The module imports the four owner names (`DETECTION_CONFSPEC`, `PIPELINE_CONFSPEC`, `LOG_SWITCHES`, `VOICE_CONFSPEC`) and does nothing when imported. It does not import `config`: the caller passes NVDA's `config.conf`.

**The call stays at package import.** NVDA imports the synth package in two ways:
- `speech.initialize()` sets the configured synth (`speech/__init__.py:163-164`, via `synthDriverHandler._getSynthDriver`, `synthDriverHandler.py:452-453`), at `core.py:804`;
- the global plugin imports `synthDrivers.WorldVoice.pipeline.sayAll` (`addon/globalPlugins/WorldVoice/__init__.py:14`), which runs the package `__init__.py` first, at `globalPluginHandler.initialize()` (`core.py:928`, `globalPluginHandler.py:18-35`), also when the synth is not WorldVoice.

The global plugin's Pipeline, Engine and Log panels read `config.conf["WorldVoice"]` while the synth is another one (refactor9 §7 item 3; `addon/globalPlugins/WorldVoice/panels/base.py:12` `read_stored`). Calling `installConfspec` from `SynthDriver.__init__` would leave those sections without a spec when WorldVoice is not the synth, so the call stays in `__init__.py` at module level. *Decided by orchestrator with the recommended default; user may override before merge.*

**Layer.** `confspec.py` imports `pipeline/registry.py` and `pipeline/settings.py`, which import NVDA's `config` and `logHandler`, and refactor9 §6.1 lists "synth `__init__.py`（含新的 `confspec.py`）" as NVDA host layer. So the function is mixedCase `installConfspec` (refactor9's sketch `install_confspec` predates §6.1), and the naming guard registers `SYNTH + "confspec.py"` in `HOST` (`tests/test_naming_layers.py:70-78`); without it `test_every_add_on_module_has_a_layer` fails. *Decided by orchestrator with the recommended default; user may override before merge.*

**Test stub.** `worldvoice_conf` (`tests/nvda_stubs.py:56-66`) reads the defaults from the AST. It finds the `conf.spec["WorldVoice"] = {...}` assignment inside `installConfspec` in `confspec.py`, so every test keeps a fresh-profile config that matches the real confspec.

### 5.2 `voices/numberLanguageChoice.py`

**Module name.** refactor9 proposed `voices/numberLanguage.py`. Inside `voices/` that module would import `..numberLanguage` (the root values module): two modules of the same name, one importing the other, and `from .numberLanguage import` versus `from ..numberLanguage import` differing by one dot. The class name gives an unambiguous module name, `voices/numberLanguageChoice.py`, in the camelCase file naming the other `voices/` modules use (`settingsRepository.py`, `mainLocalePolicy.py`). *Decided by orchestrator with the recommended default; user may override before merge.* (Recorded as a Ruling in the ledger.)

**Layer.** `voices/` is portable core (refactor9 §6.1), so the module's own names are snake_case. It imports only `..numberLanguage` (`FOLLOW`, `MAIN`): no NVDA, no logger. The warning stays in the driver.

```python
class NumberLanguageChoice:
	"""The number language the user stored, and the one speech uses."""

	def __init__(self, manager): ...           # reads manager.languages and manager.all_languages on each call
	def is_storable(self, value) -> bool: ...  # FOLLOW, MAIN or any installed voice's locale (was _isStoredNumberLanguage)
	@property
	def stored(self) -> str: ...               # the stored value, FOLLOW when no longer storable (was _get_numlan)
	def store(self, value) -> bool: ...        # keeps value if storable, else FOLLOW; True when kept (was _set_numlan)
	@property
	def spoken(self) -> str: ...               # stored, or FOLLOW when no offered voice speaks it (was _numberLanguage)
	def listed_locales(self) -> list[str]: ... # each offered locale, then the stored hidden locale (was in _get_availableNumlans)
```

Starting value `FOLLOW`, as `self._numlan = FOLLOW` today (`__init__.py:183`).

**In the driver.**
- `__init__` sets `self._numberLanguageChoice = None` where it set `self._numlan`; `_initialize` builds `NumberLanguageChoice(self._voiceManager)` right after the `VoiceManager`, inside the same `timed(nvdaLog, "VoiceManager")` block, before the `LanguageDetector` that reads it (`:266-272`). NVDA sets `numlan` only after construction (`loadSettings`, `synthDriverHandler.py:402-408`), so nothing reads the choice earlier.
- `_get_numlan` returns `choice.stored`; `_numberLanguage` returns `choice.spoken`; `_set_numlan` calls `choice.store(value)` and, when it returns False, logs `nvdaLog.debugWarning("WorldVoice: unknown number language %r, using %r", value, FOLLOW)` with the same text and arguments as today. `_get_availableNumlans` builds the same dict from `NUMBER_LANGUAGE_CHOICES` and `choice.listed_locales()` with `_numlanDisplayName`.
- `_isStoredNumberLanguage` leaves the driver (its only callers were `_get_numlan`, `_set_numlan` and `_get_availableNumlans` via `_get_numlan`).
- ~~The choice is not cleared on `terminate`: it holds no resource, and `speechContext()` already answers `GENERIC_CONTEXT` once `_voiceManager` is None (`:361-364`). Before, reading `numlan` after terminate raised `AttributeError` on the cleared manager; now it answers from the last language lists. No caller depends on either. *Decided by orchestrator with the recommended default; user may override before merge.*~~ **Corrected by the review fix (M1):** `terminate` drops the choice with the voice manager it holds, so reading `numlan` after terminate fails as on master.

## 6. Settings, compatibility, errors

No stored key, default, setting id or log text changes. An unknown stored value is handled exactly as before (§1).

## 7. Tests and verification

### 7.1 New and changed tests

- `tests/test_confspec.py::test_confspec_sections`: `installConfspec` on a stub `conf` with an existing unrelated spec section sets only `conf.spec["WorldVoice"]`, whose sections are, in order, `autoLanguageSwitching`, `pipeline`, `role`, `engine`, `log`, `voices`; `autoLanguageSwitching` is the owner's `DETECTION_CONFSPEC` plus the three `keepMainLocale*` booleans; `pipeline` equals `PIPELINE_CONFSPEC`; `log` has `enable` and one boolean per `LOG_SWITCHES` entry; `voices.__many__` equals `VOICE_CONFSPEC`; `role` is empty; `engine` is `{"__many__": "boolean(default=false)"}`. Plus a check that `confspec.py` imports `config` from nowhere (it receives `conf`).
- `tests/test_runtime_composition.py` (the real package import, `:555-650`): importing the package installs `config.conf.spec["WorldVoice"]`, so the global plugin's import gets the spec.
- `tests/test_number_language_choice.py`: unit tests of `NumberLanguageChoice` over a `SimpleNamespace(languages=..., all_languages=...)`, one per rule of §1 (starting value, storable values, refused value, hidden locale kept and listed last, spoken falls back while hidden and returns when offered again, live reads of the manager); and the import guard.
- Existing driver tests that set `synth._numlan` directly (`tests/test_worldvoice_speak.py:206`, `:356`; `tests/test_worldvoice_pipeline_settings.py:201`; `tests/test_worldvoice_lifecycle.py:258`) set the choice through the driver or build the choice; the harness environments that run `_initialize` provide `NumberLanguageChoice`.
- `tests/nvda_stubs.py`: the AST reader looks in `confspec.py`.
- `tests/test_naming_layers.py`: `confspec.py` in `HOST`.

No Hypothesis or mutmut: no core decision logic changes; the number-language rules move with their existing tests (`tests/test_worldvoice_speak.py:262-276`, `:700-764`).

### 7.2 Move proof (§3.2)

Each move is prepared by an edit commit that reshapes the code in place, so the move commit moves it verbatim:
1. edit: wrap the assignment in `def installConfspec(conf)` inside `__init__.py`, call it, point the stub reader at the function; then move: `installConfspec` to `confspec.py`.
2. edit: replace the driver's number-language members by `NumberLanguageChoice` defined in `__init__.py`; then move: the class to `voices/numberLanguageChoice.py`.

The move check (script in the agent's scratchpad, results in the ledger) parses the parent and the move commit, takes the moved top-level definition's source segment from the old file, and asserts it is byte-identical in the new file; that the new file holds nothing else but a module docstring and imports; and that the old file at the move commit equals the old file at the parent with exactly that segment (and its surrounding blank lines) removed and only import lines changed. Test files in a move commit change only path references; the ledger lists them.

### 7.3 Verification

Full suite (baseline 3346 passed / 0 skipped; new tests add to it), `prek run --all-files`, `git diff --check`, protected paths (DEVELOPMENT_WORKFLOW.md §7). Not verified on Windows: NVDA's real `config.conf.spec` and the Voice panel; behaviour is unchanged by construction and by the move proof.

## 8. Open questions

None that block. Defaults the user may override: §5.1 call site and `installConfspec` name/layer, §5.2 module name ~~and the choice surviving `terminate`~~ (corrected by review M1).
