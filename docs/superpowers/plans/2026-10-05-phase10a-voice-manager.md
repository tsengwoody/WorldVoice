# Phase 10a Voice Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Give `VoiceManager` one per-engine data structure and an immutable `VoiceCatalog`.
- Inject engine classes instead of a module global.
- Move completion glue into `CompletionPolicy`.
- Slim `VoiceFacade` to its live members, and pin the Neural-style plugin contract.

**Architecture:**
- `voiceManager.py` keeps its NVDA/UI-facing names but forwards to:
  - `self._resources: dict[str, EngineResource]` (with `voices`/`published`);
  - `self.catalog: VoiceCatalog` (new `voiceCatalog.py`).
- The main driver builds `engine_classes` with `engine.ready_engine_classes(conf)` and passes `CompletionPolicy.select` as `completion_for`.

**Tech Stack:** Python 3.11; pytest with NVDA stubs (`tests/nvda_stubs.StubModules`); ruff (tabs, ref/nvda style).

**Spec:** `docs/superpowers/specs/2026-10-05-phase10a-voice-manager-design.md`

## Global Constraints

- Never edit `driver/<Engine>/driver/` or `driver/sonic`; every ruff command passes `--exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic'`.
- User-visible behavior must not change, including:
  - voice lists, language lists and their labels;
  - numlan labels;
  - the fallback warning text;
  - engine enable logic.
- `driver.Voice` stays the only class external plugins subclass. A Neural-style subclass (`core = None`, `engine`, `synth_driver_class`) must keep working.
- NVDA/UI-facing manager names stay camelCase. New APIs use snake_case.
- `git add` explicit paths only. Never stage the `docs/superpowers/finish_task.md` deletion or `refactor.md`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full suite: `python3 -m pytest tests -q` (baseline 1533).
- Lint gate: `ruff check addon <scope> --select F401,F821,BLE001,I001` → 0; `ruff format --check addon`.

## Review Focus

1. **Engine whose bind fails after open.** It is in `_resources` for cleanup but must never be visible: not in `playback_ports`, `resolve_playback` → `None`, its voices not in the catalog. Task 3 adds the test.
2. **Calls after terminate.**
   - `resolve_playback` must return `None`.
   - `getVoiceCapabilities` must raise `KeyError`, as it does today.
   - `playback_ports` must be empty.
   - Task 3 adds the test.
3. **Duplicate voice names inside one engine.** The last spec wins, as `_specs[name] = spec` did today. Task 2 tests `from_specs`.
4. **Fallback warning dedupe.** It lives per `CompletionPolicy` instance and is keyed on the full profile tuple. One warning per distinct profile, with the same text. Task 1 tests it.
5. **Neural `core = None` shadowing.** With the class attribute shadowing the facade property, the base `variants` and `applyEngineSettings` must still work through a real `VoiceManager`. Task 5 tests it.

---

### Task 1: `CompletionPolicy.select`

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/compat/completionPolicies.py`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py` (the `_completionPolicy` construction; delete `_completion_for` and `_warn_drain_fallback`)
- Test: `tests/test_runtime_completion_policies.py`, `tests/test_runtime_composition.py:600-625` (the helper that returns `synth._completion_for`)

**Interfaces:**
- Produces: `CompletionPolicy(*, nvda_version: str | None = None, logger=None, force_unverified_drain: bool = True)`; `CompletionPolicy.select(voice_class: type, core: object) -> CompletionContract`.

- [ ] **Step 1: Failing tests** in `tests/test_runtime_completion_policies.py`.
  - Replace the helper at line ~199 that builds `synth._completion_for` with one that returns `policies.CompletionPolicy(nvda_version=..., logger=logger).select`. Keep every existing assertion on contracts and warnings.
  - Add:

```python
def test_select_warns_once_per_distinct_fallback_profile():
    logger = RecordingLogger()
    policy = policies.CompletionPolicy(nvda_version="2026.1", logger=logger)
    unsupported_a = drain_voice_returning(DrainSupport(False, "p", "reason a"))
    unsupported_b = drain_voice_returning(DrainSupport(False, "p", "reason b"))
    for voice_class, core in (unsupported_a, unsupported_a, unsupported_b):
        assert policy.select(voice_class, core) == CompletionContract()
    assert [args[1:] for args in logger.warnings] == [
        ("Fake", "2026.1", "default", "p", "reason a"),
        ("Fake", "2026.1", "default", "p", "reason b"),
    ]
    assert logger.warnings[0][0] == "WorldVoice %s uses LEGACY_DONE (NVDA %s, audio %s, profile %s): %s"
```

    Use the module's existing fake voice/core builders. If a builder is missing, add `drain_voice_returning(support)`, which returns `(VoiceClass, core)`:
    - `drain_profile` is non-None;
    - the core is an instance of `synth_driver_class`, with `speak_segment` and `get_segment_drain_support` returning `support`.
  - Also add `test_select_matches_contract_for` for three cases (supported, unsupported, no profile): `select(...) == contract_for(...)[0]` with `nvda_version=policy.nvda_version` and `audio_mode=policy.audio_mode(...)`.

- [ ] **Step 2: Run** `python3 -m pytest tests/test_runtime_completion_policies.py -q` → FAIL (`select` missing).
- [ ] **Step 3: Implement**

```python
import logging

class CompletionPolicy:
	def __init__(self, *, nvda_version: str | None = None, logger=None, force_unverified_drain: bool = True):
		# Forced activation of DRAIN on wrapper profiles without playback evidence.
		self.force_unverified_drain = force_unverified_drain
		self.nvda_version = nvda_version
		self._logger = logger or logging.getLogger(__name__)
		self._fallbacks: set[tuple] = set()

	def select(self, voice_class: type, core: object) -> CompletionContract:
		"""Choose the opened core's contract, logging each distinct fallback once."""
		audio_mode = self.audio_mode(voice_class, core)
		contract, support = self.contract_for(
			voice_class,
			core,
			nvda_version=self.nvda_version,
			audio_mode=audio_mode,
		)
		if support is not None and not support.supported:
			profile = (voice_class.engine, self.nvda_version, audio_mode, support.profile, support.reason)
			if profile not in self._fallbacks:
				self._fallbacks.add(profile)
				self._logger.warning(
					"WorldVoice %s uses LEGACY_DONE (NVDA %s, audio %s, profile %s): %s",
					*profile,
				)
		return contract
```

  Main driver:
  - `self._completionPolicy = CompletionPolicy(nvda_version=versionInfo.version, logger=nvdaLog)`;
  - `completion_for=self._completionPolicy.select`;
  - delete `_completion_for` and `_warn_drain_fallback`.
  - Update the `test_runtime_composition.py` helper (~line 600-620) to return `policies.CompletionPolicy(nvda_version=<stub version>, logger=<its log recorder>).select`. Keep its callers' assertions.
- [ ] **Step 4: Run** both test files, then the full suite → PASS.
- [ ] **Step 5: Commit** `refactor: let CompletionPolicy choose contracts and dedupe fallback warnings`.

---

### Task 2: `VoiceCatalog`

**Files:**
- Create: `addon/synthDrivers/WorldVoice/voiceCatalog.py`
- Modify: `addon/synthDrivers/WorldVoice/voiceManager.py`; `addon/synthDrivers/WorldVoice/__init__.py` (`_getLocaleReadableName` → `_numlanDisplayName`); `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (drop the two `_manager.ready()` branches and `self.ready`)
- Test: create `tests/test_voice_catalog.py`; modify `tests/test_role_presenter.py`, `tests/test_voice_settings_transaction.py`, `tests/test_voice_manager_roles.py`, plus any test that sets `manager.table`/`manager._voiceInfos`/`keepMainLocaleEngineConsistent`

**Interfaces:**
- Produces:
  - `VoiceCatalog.from_specs(specs: Iterable[VoiceSpec]) -> VoiceCatalog`;
  - fields `table: tuple[VoiceSpec, ...]`, `by_name: Mapping[str, VoiceSpec]` (a `MappingProxyType`), `voice_infos: OrderedDict[str, VoiceInfo]`, `all_languages: tuple[str, ...]`;
  - `readable_name(locale) -> str`;
  - module-level `EMPTY_CATALOG` and `group_by_primary_locale(specs) -> dict[str, list[str]]`;
  - `VoiceManager.catalog`.

- [ ] **Step 1: Failing tests** `tests/test_voice_catalog.py`. Load the module with `stub_modules` from conftest:
  - stub `languageHandler` with `getLanguageDescription`;
  - stub `synthDriverHandler.VoiceInfo` as a namedtuple-like class;
  - stub the package path as other tests do (follow `tests/test_voice_manager_roles.py`'s loader).

```python
def test_catalog_sorts_by_engine_language_name_and_last_duplicate_wins(catalog_module, spec):
	a2 = spec("x", "B:x", "B", "fr")
	catalog = catalog_module.VoiceCatalog.from_specs([spec("y", "A:y", "A", "en_US"), spec("x", "B:x", "B", "de"), a2])
	assert [v.name for v in catalog.table] == ["A:y", "B:x"]
	assert catalog.by_name["B:x"] is a2
	assert list(catalog.voice_infos) == ["A:y", "B:x"]
	assert isinstance(catalog.voice_infos, OrderedDict)
	assert catalog.all_languages == ("en", "fr")

def test_catalog_is_immutable(catalog_module, spec):
	catalog = catalog_module.VoiceCatalog.from_specs([spec("y", "A:y", "A", "en")])
	with pytest.raises(dataclasses.FrozenInstanceError):
		catalog.table = ()
	with pytest.raises(TypeError):
		catalog.by_name["z"] = None

def test_group_by_primary_locale(catalog_module, spec):
	specs = [spec("a", "A:a", "A", "en_US"), spec("b", "A:b", "A", "en_GB"), spec("c", "A:c", "A", "fr")]
	assert catalog_module.group_by_primary_locale(specs) == {"en": ["A:a", "A:b"], "fr": ["A:c"]}

def test_readable_name(catalog_module, descriptions):
	descriptions["en"] = "English"
	assert catalog_module.EMPTY_CATALOG.readable_name("en") == "English - en"
	assert catalog_module.EMPTY_CATALOG.readable_name("xx") == "xx"
```

  `spec(id, name, engine, language)` builds `VoiceSpec(id=id, name=name, description=name, language=language, engine=engine, locale=language)`.

- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: Implement** `voiceCatalog.py`:

```python
"""Immutable view of the voices that opened engines published."""

from collections import OrderedDict, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from operator import attrgetter
from types import MappingProxyType

import languageHandler
from synthDriverHandler import VoiceInfo

from .roles import getPrimaryLocale
from .runtime.models import VoiceSpec


def group_by_primary_locale(specs: Iterable[VoiceSpec]) -> dict[str, list[str]]:
	groups: dict[str, list[str]] = defaultdict(list)
	for spec in specs:
		groups[getPrimaryLocale(spec.locale)].append(spec.name)
	return dict(groups)


@dataclass(frozen=True)
class VoiceCatalog:
	table: tuple[VoiceSpec, ...]
	by_name: Mapping[str, VoiceSpec]
	voice_infos: "OrderedDict[str, VoiceInfo]"
	all_languages: tuple[str, ...]

	@classmethod
	def from_specs(cls, specs: Iterable[VoiceSpec]) -> "VoiceCatalog":
		by_name = {}
		for spec in specs:
			by_name[spec.name] = spec
		table = tuple(sorted(by_name.values(), key=attrgetter("engine", "language", "name")))
		return cls(
			table=table,
			by_name=MappingProxyType(by_name),
			voice_infos=OrderedDict((v.name, VoiceInfo(v.name, v.description, v.language)) for v in table),
			all_languages=tuple(sorted(group_by_primary_locale(table))),
		)

	def readable_name(self, locale: str) -> str:
		description = languageHandler.getLanguageDescription(locale)
		return "%s - %s" % (description, locale) if description else locale


EMPTY_CATALOG = VoiceCatalog.from_specs(())
```

  Check against the old code: `groupVoicesByPrimaryLocale` grouped on the `locale` field through `getPrimaryLocale`, and `VoiceInfo(v.name, v.description, v.language)` was keyed by `VoiceInfo.id`, which is `v.name`. So the behavior is identical.

  `voiceManager.py`:
  - Delete `groupByField`, `groupVoicesByPrimaryLocale`, `getVoiceKey`, `VoiceMeta`, `ready()`, `keepMainLocaleEngineConsistent`, and the `T/K/V` TypeVars with their now-unused imports.
  - Add `self.catalog = EMPTY_CATALOG` in `__init__`, before `_initialize`.
  - `_setVoiceDatas`: `self.catalog = VoiceCatalog.from_specs(self._specs.values())`. Task 3 switches the source to published resources.
  - Make each of these a read-only forwarder:
    - `table` → `catalog.table`; it becomes a property, and callers already only iterate it;
    - `voiceInfos` → `catalog.voice_infos`;
    - `allLanguages` → `list(catalog.all_languages)`;
    - `getVoiceSpec(key)` → `catalog.by_name[key]`;
    - `languages` → `sorted(group_by_primary_locale(self._visible_table()))`;
    - `localeToVoicesMap` → `group_by_primary_locale(self._visible_table())`;
    - `localesToNamesMap` → `{locale: self.catalog.readable_name(locale) for locale in group_by_primary_locale(self._visible_table())}`.
  - `defaultVoiceName` setter: `self.catalog.voice_infos`.
  - `_getDefaultVoiceMeta` → rename to `_getDefaultVoiceSpec`, returning a `VoiceSpec`.
  - `waitfactor` setter: iterate `self.catalog.by_name`.
  - Delete `_getLocaleReadableName`.

  Main driver: rename `_getLocaleReadableName` to `_numlanDisplayName` and add the comment `# Settings-ring entries show the language description only.` Update its single caller in `_get_availableNumlans`.

  `speechSettingsDialog.py`: delete the two `if not self._manager.ready():` blocks (lines ~305-313 and ~626-635) and `self.ready = ...`. Keep the `self._manager = getSynth()._voiceManager` lines.

  Tests:
  - `manager.table = [...]` / `manager._voiceInfos = ...` → `manager.catalog = <catalog module>.VoiceCatalog.from_specs([...])`. Load the catalog module the same way the test loads voiceManager. Its import is relative, so it lands in the same stub package.
  - `manager.keepMainLocaleEngineConsistent` → `manager.engine_consistency.enabled`.
  - `module.VoiceMeta` → `module.VoiceSpec`. Import `VoiceSpec` from `runtime.models` through the test's package if `voiceManager` no longer re-exports it; `voiceManager` still imports `VoiceSpec` for typing, so `module.VoiceSpec` works.
- [ ] **Step 4: Run** the new and modified files plus the full suite → PASS. Run `ruff check` on the lint gate.
- [ ] **Step 5: Commit** `refactor: give VoiceManager an immutable voice catalog and drop dead manager members`.

---

### Task 3: One resource map and injected engine classes

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voiceManager.py`, `addon/synthDrivers/WorldVoice/engine/__init__.py`, `addon/synthDrivers/WorldVoice/engine/discovery.py` (`_coerce_bool` → `coerce_bool`), `addon/synthDrivers/WorldVoice/__init__.py`, `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (`EngineType` → `ENGINE_SPECS`)
- Test: `tests/test_runtime_composition.py`, `tests/test_worldvoice_lifecycle.py`, `tests/test_f4_voice_state.py`, `tests/runtime_drain_integration_harness.py`, `tests/test_engine_discovery*.py` (if any references `_coerce_bool`)

**Interfaces:**
- Consumes: `VoiceCatalog.from_specs` (Task 2).
- Produces:
  - `VoiceManager(taskManager, settings, bridge, *, index_ledger, completion_for, engine_classes: Mapping[str, type], roles=None)`;
  - `EngineResource.voices: tuple[VoiceSpec, ...]` and `EngineResource.published: bool`;
  - `engine.ready_engine_classes(engine_config) -> dict[str, type]`;
  - `discovery.coerce_bool(value) -> bool`.

- [ ] **Step 1: Failing tests**, in `tests/test_runtime_composition.py`.
  - Change the fixture's `create` so it passes `engine_classes={name: Voice ...}` instead of mutating `manager_module.EngineType`/`READY_ENGINE_CLASS`. Also drop those names from the `.engine` stub at line ~574; voiceManager no longer imports `.engine`.
  - Add:

```python
def test_unbound_engine_is_cleaned_up_but_never_visible(composition):
	# second engine's bind raises after open; first stays usable
	...  # use the module's existing bind-failure helper (see test_partial_bind_failure_releases_resources_without_commit)
	assert [port for port in manager.playback_ports] == [first_session]
	assert manager.resolve_playback(second_voice_name) is None
	assert second_voice_name not in manager.voiceInfos

def test_after_terminate_nothing_resolves(composition):
	manager = composition.create()
	name = manager.table[0].name
	manager.terminate()
	assert manager.resolve_playback(name) is None
	assert manager.playback_ports == ()
	with pytest.raises(KeyError):
		manager.getVoiceCapabilities(name)

def test_engines_open_in_engine_classes_order(composition):
	...  # pass engine_classes in reverse spec order; assert list(manager._resources) matches that order
```

  If the existing partial-bind test already builds a manager where bind fails partway, write the first test against a *non-raising* partial failure: patch the second resource's `_bind` to raise inside `_initialize`'s loop and catch at `create`. Otherwise assert visibility on the manager state captured before `terminate` runs. If no fixture can produce a visible-after-failed-bind state (bind failure aborts construction), assert instead that the failed construction leaves `playback_ports == ()` and every opened session closed. That is the observable form of the same guarantee.

- [ ] **Step 2: Run** → FAIL (`engine_classes` unexpected keyword).
- [ ] **Step 3: Implement** per the spec's design section:
  - `EngineResource` gets `voices: tuple[VoiceSpec, ...] = ()` and `published: bool = False`.
  - `__init__` gets the `engine_classes` keyword; `self._engine_classes = dict(engine_classes)`; `self._resources: dict[str, EngineResource] = {}`. Delete `_sessions`, `_bindings` and `_specs`.
  - `_initialize`: `for name, cls in self._engine_classes.items():` then open, bind, publish. Delete the `refresh_ready_engine_classes`, `get_engine_enabled` and `EngineType` uses, and the `.engine` import.
  - `_open_engine`: `self._resources[name] = resource` before `session.open()`.
  - `_publish`: `resource.voices = resource.adapter.list_voices()`; `resource.published = True`.
  - Add `_published(engine) -> EngineResource`, which raises `KeyError` when the engine is missing or unpublished.
  - `resolve_playback`, `getVoiceCapabilities`, `getVoiceVariants`, `_createVoiceInstance` and `playback_ports` follow the spec's code. `_createVoiceInstance` uses `resource = self._published(spec.engine)`; `resource.voice_class(spec, resource.binding, self.taskManager)` (Task 4 drops the third argument).
  - `_setVoiceDatas`: `VoiceCatalog.from_specs(spec for r in self._resources.values() if r.published for spec in r.voices)`.
  - `terminate`:
    - start with `for resource in self._resources.values(): resource.published = False`;
    - the cleanup loop runs over `reversed(list(self._resources.values()))`;
    - end with `self._resources.clear()`.
  - `engine/__init__.py`: delete `EngineType`, `READY_ENGINE_CLASS` and `refresh_ready_engine_classes`. Add:

```python
def ready_engine_classes(engine_config) -> dict[str, type]:
	"""Load the enabled, ready Voice classes in discovery order."""
	return load_enabled_engine_classes(list(ENGINE_SPECS), engine_config, logger=log)
```

    `get_engine_enabled`'s unknown-engine branch becomes `return engine_name in engine_config and coerce_bool(engine_config[engine_name])`. Import `coerce_bool` from `.discovery`.
  - `discovery.py`: rename `_coerce_bool` → `coerce_bool`, updating its caller.
  - Main driver: `from .engine import ready_engine_classes`; pass `engine_classes=ready_engine_classes(config.conf["WorldVoice"]["engine"])` to `VoiceManager`.
  - `speechSettingsDialog.py`: import `ENGINE_SPECS` instead of `EngineType`, and replace both loops.
  - Update the other tests listed under Files:
    - replace `READY_ENGINE_CLASS`/`EngineType`/`refresh_ready_engine_classes` stubbing with `engine_classes=`;
    - replace `manager._sessions`/`_bindings`/`_specs`/`_resources = [...]` setups with `_resources = {name: EngineResource(..., voices=..., published=True)}` plus `manager.catalog = VoiceCatalog.from_specs(...)`;
    - change the `test_worldvoice_lifecycle.py:47` fake `VoiceManager.__init__` to accept `engine_classes` and assert it is a mapping.
- [ ] **Step 4: Run** the full suite and the lint gate → PASS. Run `test_runtime_composition.py` and `runtime_drain_integration_harness` users 5×.
- [ ] **Step 5: Commit** `refactor: keep one resource map per engine and inject ready engine classes`.

---

### Task 4: Slim `VoiceFacade`

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/compat/voiceFacade.py`, `addon/synthDrivers/WorldVoice/driver/__init__.py` (delete `core.wv`), `addon/synthDrivers/WorldVoice/voiceManager.py` (`_createVoiceInstance` drops `self.taskManager`)
- Test: `tests/test_runtime_voice_facade.py`, `tests/test_f4_voice_state.py`, `tests/test_role_presenter.py`, `tests/test_voice_settings_transaction.py`, `tests/test_worldvoice_request_manager.py`, `tests/test_f4_engine_adapters.py`, and any other file constructing `VoiceFacade`/`Voice` with three arguments

**Interfaces:**
- Produces: `VoiceFacade(spec: VoiceSpec, binding: LegacyVoiceBinding)`. Public members are exactly:
  - `id`, `name`, `language`, `core`;
  - `rate`, `pitch`, `volume`, `variant`, `inflection`, `rateBoost`, `waitfactor`;
  - `snapshot`, `update_settings`, `loadParameter`, `commit`, `stop`.

- [ ] **Step 1: Failing test** `tests/test_voice_manager_structure.py` (create):

```python
FACADE_MEMBERS = {
	"id", "name", "language", "core",
	"rate", "pitch", "volume", "variant", "inflection", "rateBoost", "waitfactor",
	"snapshot", "update_settings", "loadParameter", "commit", "stop",
}

def test_voice_facade_exposes_only_live_members(facade_module):
	cls = facade_module.VoiceFacade
	public = {name for name in dir(cls) if not name.startswith("_")}
	assert public | {"id", "name", "language"} == FACADE_MEMBERS
	assert list(inspect.signature(cls.__init__).parameters) == ["self", "spec", "binding"]

def test_create_core_does_not_tag_the_core():
	source = (ADDON / "synthDrivers/WorldVoice/driver/__init__.py").read_text(encoding="utf-8")
	assert ".wv" not in source
```

  `facade_module` loads `compat/voiceFacade.py` through `stub_modules`; it only imports `runtime.*`, which tests already load. Follow `tests/test_runtime_voice_facade.py`'s loader. `ADDON = Path(__file__).resolve().parents[1] / "addon"`.

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - `voiceFacade.py`:
    - delete `_baseline`, the six `commit_*`, `revision`, `rollback`, `active`, `speak`, `breaks`, `pause`, `resume` and `close`;
    - `__init__(self, spec, binding)` without `taskManager`.
  - `driver/__init__.py`: `create_core` returns `cls.synth_driver_class()`.
  - `voiceManager._createVoiceInstance`: `resource.voice_class(spec, resource.binding)`.
  - Tests:
    - `voice.active()` → `voice._binding.session.activate(voice.name)`. Add a local helper `activate(voice)` in each file that uses it.
    - `voice.rollback()` → `voice._binding.settings.rollback(voice.name)`.
    - `voice.revision` → `voice.snapshot().revision`.
    - Three-argument constructions drop the third argument.
    - Delete `test_speech_queue_does_not_activate_voice` (it tests the removed `speak`). Also delete the `commit_rate` assertion in `test_runtime_voice_facade.py` and the `first.wv == "A"` assertion.
    - `test_worldvoice_request_manager.py`'s `Port.activate` returns `voice._binding.session.activate(key)`.
- [ ] **Step 4: Run** the full suite and the lint gate → PASS.
- [ ] **Step 5: Commit** `refactor: drop the voice facade's unused members and task manager`.

---

### Task 5: Structure guards and the Neural plugin contract

**Files:**
- Modify: `tests/test_voice_manager_structure.py`
- Create: `tests/test_plugin_voice_contract.py`

**Interfaces:**
- Consumes: everything above. `PLUGIN_VOICE_ATTRIBUTES = {"core", "engine", "synth_driver_class", "extra_capabilities", "drain_profile"}`.

- [ ] **Step 1: Structure guards** appended to `tests/test_voice_manager_structure.py`:

```python
FORBIDDEN = {
	"synthDrivers/WorldVoice/voiceManager.py": ["_sessions", "_bindings", "_specs", "READY_ENGINE_CLASS", "EngineType",
		"VoiceMeta", "groupByField", "keepMainLocaleEngineConsistent", "def ready"],
	"synthDrivers/WorldVoice/engine/__init__.py": ["READY_ENGINE_CLASS", "EngineType", "refresh_ready_engine_classes"],
	"globalPlugins/WorldVoice/speechSettingsDialog.py": ["EngineType", "_manager.ready"],
	"synthDrivers/WorldVoice/__init__.py": ["_completion_for", "_warn_drain_fallback", "_drainFallbacks"],
}

@pytest.mark.parametrize("path", sorted(FORBIDDEN))
def test_removed_structures_stay_removed(path):
	source = (ADDON / path).read_text(encoding="utf-8")
	assert [name for name in FORBIDDEN[path] if name in source] == []

def test_one_boolean_coercion():
	sources = [(ADDON / p).read_text(encoding="utf-8") for p in
		("synthDrivers/WorldVoice/engine/__init__.py", "synthDrivers/WorldVoice/engine/discovery.py")]
	assert sum(s.count('{"false", "0", ""}') for s in sources) == 1
```

- [ ] **Step 2: Neural contract** in `tests/test_plugin_voice_contract.py`.
  - Load the real `voiceManager` stack the way `tests/test_runtime_composition.py` does (reuse its fixture builder by importing the helper, or copy its loader into a local fixture using `stub_modules`). The real `driver/__init__.py` must be loaded as `<package>.driver`; it imports `languageHandler` (stub `getLanguageDescription=lambda locale: None`).

```python
class FakeCore:
	supportsCancellationToken = False
	def __init__(self):
		self.availableVoices = {"v1": SimpleNamespace(id="v1", displayName="Neural One - English", language="en")}
		self.writes, self.terminated = [], False
	def __setattr__(self, name, value):
		if name in {"voice", "rate", "pitch", "volume"}:
			self.__dict__.setdefault("writes", []).append((name, value))
		object.__setattr__(self, name, value)
	def speak(self, commands): pass
	def cancel(self): pass
	def pause(self, switch): pass
	def terminate(self): self.terminated = True

def neural_voice(base):
	class Voice(base):
		core = None
		engine = "Neural"
		synth_driver_class = FakeCore
	return Voice

def test_neural_style_plugin_runs_through_the_manager(stack):
	Voice = neural_voice(stack.driver.Voice)
	manager = stack.create(engine_classes={"Neural": Voice})
	assert [spec.name for spec in manager.table] == ["Neural:v1"]
	voice = manager.getVoiceInstance("Neural:v1")
	assert voice.core is None  # the plugin's class attribute shadows the facade property
	session = manager.resolve_playback("Neural:v1")
	session.activate("Neural:v1")
	core = manager._resources["Neural"].adapter.core
	assert ("voice", "v1") in core.writes
	assert {name for name, _ in core.writes} >= {"voice"}
	assert manager.getVoiceVariants("Neural:v1") == ()
	manager.terminate()
	assert core.terminated

def test_plugin_attributes_exist_on_the_base_voice(stack):
	for name in PLUGIN_VOICE_ATTRIBUTES - {"core"}:
		assert hasattr(stack.driver.Voice, name)
	assert isinstance(inspect.getattr_static(stack.driver.Voice, "core"), property)

def test_reference_neural_plugin_uses_only_plugin_attributes():
	path = ROOT / "ref/Neural/Neural/__init__.py"
	if not path.is_file():
		pytest.skip("ref/Neural is not checked out")
	tree = ast.parse(path.read_text(encoding="utf-8"))
	aliases = {a.asname or a.name for node in tree.body if isinstance(node, ast.ImportFrom)
		and node.module == "synthDrivers.WorldVoice.driver" for a in node.names if a.name == "Voice"}
	(voice,) = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Voice"]
	assert [b.id for b in voice.bases] and {b.id for b in voice.bases} <= aliases
	assigned = set()
	for stmt in voice.body:
		assert isinstance(stmt, ast.Assign), ast.dump(stmt)
		assigned |= {t.id for t in stmt.targets}
	assert assigned <= PLUGIN_VOICE_ATTRIBUTES
```

  `supportedSettings()` for `FakeCore` returns `[]` (no `supportedSettings` attribute → `TypeError`? No: `cls.synth_driver_class.supportedSettings` raises `AttributeError`). Give `FakeCore` `supportedSettings = (SimpleNamespace(id="rate"), SimpleNamespace(id="pitch"), SimpleNamespace(id="volume"))`, so the base hook returns those ids and `apply` writes them. Then assert `{"voice", "rate", "pitch", "volume"} <= {n for n, _ in core.writes}`.

- [ ] **Step 3: Run** both files and the full suite → PASS. These tests exercise existing behavior and should pass without addon changes; a failure means an earlier task broke the contract, so fix that task's code.
- [ ] **Step 4: Commit** `test: pin the plugin Voice contract and the removed manager structures`.

---

Final verification:

```bash
python3 -m pytest tests -q
ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select F401,F821,BLE001,I001
ruff format --check addon
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver' addon/synthDrivers/WorldVoice/driver/sonic
```
