# Phase 7 Roles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give role assignments one repository, the three main-locale flags one policy module, and the role panel a wx-free presenter (fixing D1/D4/D6). Share the pipeline-log flow (D7) and the core-archive extraction. Remove the `wvd` service locator.

**Architecture:**
- `roles.py` and `mainLocalePolicy.py` are pure modules (no NVDA imports; config access is injected). `VoiceManager` owns one instance of each and delegates.
- `rolePresenter.py` holds the role panel's pending state and transaction; the panel only maps widgets.
- `pipelineLog.py` and `generics/coreArchive.py` remove the two UI/installer duplicates.

**Tech Stack:** Python 3.11 NVDA add-on; pytest with stubbed NVDA modules; ruff format (tabs).

**Spec:** `docs/superpowers/specs/2026-10-04-phase7-roles-design.md`

## Global Constraints

- Never edit `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/` or `driver/sonic`.
- `addon/` stays `ruff format`-clean (tabs). New test files use tabs.
- `roles.py` and `mainLocalePolicy.py` import nothing from NVDA: `tests/runtime_harness.forbid_legacy_runtime_imports` rejects `config` and `languageHandler`, and `configRepository.py` imports the policy module.
- `git add` explicit paths only. Never stage the `docs/superpowers/finish_task.md` deletion or `refactor.md`. Add the plan with `git add -f`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `WorldVoiceVoiceSettingsPanel` behavior is unchanged (user decision); only a comment is added.
- No new translatable strings.
- Full suite: `python3 -m pytest tests -q` (baseline 1443 passed).

## Review Focus

1. **Discard after Apply in the WorldVoice dialog.** After Apply then Cancel, roles, flags and voice parameters must stay at the applied values. `presenter.apply()` must rebase: pending cleared, engine initial value updated, D1 record cleared. Test in Task 4.
2. **Parameter-consistency checkbox already on when the dialog opens.** Turning it off must not touch any voice (no D1 record exists); turning it on again must preview. Test in Task 4.
3. **Save failure mid-apply.** If `edit.apply()` raises, nothing else may change: no role, no flag, no speech section, and pending choices stay. The panel converts the failure to `ValueError` so NVDA keeps the dialog open. Tests in Task 4 and Task 5.
4. **Role section holding scalar values or a voice-less section** (hand-edited `nvda.ini`). `assignments()` must ignore them, `save` must keep the scalars, and nothing may crash. Test in Task 1.
5. **A corrupted zip imported from the menu.** The user sees the failure message instead of silence. Test in Task 7.

---

### Task 1: `ConfigRoleRepository`

**Files:**
- Create: `addon/synthDrivers/WorldVoice/roles.py`
- Test: `tests/test_role_repository.py`

**Interfaces:**
- Produces:
  - `getPrimaryLocale(locale) -> str`;
  - `prune_assignments(assignments, available) -> dict[str, str]`;
  - `ConfigRoleRepository(conf_provider)`, with `.voice_for(language)`, `.assignments()`, `.save(assignments)`, `.assign(locale, voice)` and `.prune(available)`.

- [ ] **Step 1: Write the failing test**

```python
"""Role assignments live behind one repository."""

import importlib.util
import sys

import pytest


def load_roles(monkeypatch):
	spec = importlib.util.spec_from_file_location("roles_under_test", "addon/synthDrivers/WorldVoice/roles.py")
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module


class Section(dict):
	"""Stands in for NVDA's AggregatedSection (not a dict subclass in NVDA)."""


@pytest.fixture
def roles(monkeypatch):
	module = load_roles(monkeypatch)
	conf = {"WorldVoice": {"role": {
		"en": Section(voice="A:en"),
		"zh": Section(voice="B:zh"),
		"ja": Section(),
		"legacy": "kept",
	}}}
	return module, conf, module.ConfigRoleRepository(lambda: conf)


def test_primary_locale(monkeypatch):
	module = load_roles(monkeypatch)
	assert module.getPrimaryLocale("zh_TW") == "zh"
	assert module.getPrimaryLocale("en-US") == "en"
	assert module.getPrimaryLocale("") == ""


def test_voice_for_prefers_exact_then_primary_locale(roles):
	module, conf, repository = roles
	conf["WorldVoice"]["role"]["zh_TW"] = Section(voice="C:tw")
	assert repository.voice_for("zh_TW") == "C:tw"
	assert repository.voice_for("zh_CN") == "B:zh"
	assert repository.voice_for("ja") is None
	assert repository.voice_for("fr") is None


def test_assignments_ignore_scalars_and_voiceless_sections(roles):
	_, _, repository = roles
	assert repository.assignments() == {"en": "A:en", "zh": "B:zh"}


def test_save_rewrites_sections_and_keeps_scalars(roles):
	_, conf, repository = roles
	repository.save({"fr": "C:fr"})
	assert conf["WorldVoice"]["role"] == {"fr": {"voice": "C:fr"}, "legacy": "kept"}


def test_assign_adds_or_replaces_one_locale(roles):
	_, conf, repository = roles
	repository.assign("zh", "C:zh")
	assert repository.assignments() == {"en": "A:en", "zh": "C:zh"}


def test_prune_keeps_only_available_assignments(roles):
	_, conf, repository = roles
	repository.prune({"en": ["A:en"], "zh": ["X:zh"]})
	assert conf["WorldVoice"]["role"] == {"en": {"voice": "A:en"}, "legacy": "kept"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_role_repository.py -q`
Expected: FAIL (`FileNotFoundError` for `roles.py`).

- [ ] **Step 3: Implement `roles.py`**

```python
"""Locale to voice assignments ("speech roles") stored in the WorldVoice config."""

from collections.abc import Callable, Collection, Mapping
import re
from typing import Any


def getPrimaryLocale(locale: str) -> str:
	"""Return the primary language subtag from locale strings like en_US / en-US."""
	if not locale:
		return locale
	return re.split(r"[-_]", locale, maxsplit=1)[0].lower()


def prune_assignments(
	assignments: Mapping[str, str],
	available: Mapping[str, Collection[str]],
) -> dict[str, str]:
	"""Keep the assignments whose locale and voice are still available."""
	return {
		locale: voice
		for locale, voice in assignments.items()
		if locale in available and voice in available[locale]
	}


def _is_section(value: Any) -> bool:
	return isinstance(value, Mapping) or (hasattr(value, "items") and hasattr(value, "get"))


class ConfigRoleRepository:
	"""The only reader and writer of config["WorldVoice"]["role"]."""

	def __init__(self, conf_provider: Callable[[], Any]):
		self._conf_provider = conf_provider

	def _section(self) -> Any:
		return self._conf_provider()["WorldVoice"]["role"]

	def voice_for(self, language: str) -> str | None:
		section = self._section()
		for locale in (language, getPrimaryLocale(language)):
			value = section.get(locale) if hasattr(section, "get") else None
			if _is_section(value):
				voice = value.get("voice")
				if voice:
					return voice
		return None

	def assignments(self) -> dict[str, str]:
		result = {}
		for locale, value in self._section().items():
			if _is_section(value):
				voice = value.get("voice")
				if voice:
					result[locale] = voice
		return result

	def save(self, assignments: Mapping[str, str]) -> None:
		conf = self._conf_provider()
		kept = {locale: value for locale, value in conf["WorldVoice"]["role"].items() if not _is_section(value)}
		conf["WorldVoice"]["role"] = {
			**{locale: {"voice": voice} for locale, voice in assignments.items()},
			**kept,
		}

	def assign(self, locale: str, voice: str) -> None:
		self.save({**self.assignments(), locale: voice})

	def prune(self, available: Mapping[str, Collection[str]]) -> None:
		self.save(prune_assignments(self.assignments(), available))
```

`voice_for` reproduces `_getConfiguredVoiceNameForLanguage`: the exact locale first, then the primary locale; an empty voice is skipped.

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_role_repository.py -q` → 6 passed.

- [ ] **Step 5: Commit**

```bash
ruff format addon/synthDrivers/WorldVoice/roles.py
git add addon/synthDrivers/WorldVoice/roles.py tests/test_role_repository.py
git commit -m "feat(roles): add a repository for locale voice assignments

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Main-locale policies; the config repository uses `ParameterConsistency`

**Files:**
- Create: `addon/synthDrivers/WorldVoice/mainLocalePolicy.py`
- Modify: `addon/synthDrivers/WorldVoice/configRepository.py`
- Test: `tests/test_main_locale_policy.py`; `tests/test_voice_config_repository.py` must stay green unchanged.

**Interfaces:**
- Consumes: `getPrimaryLocale` (Task 1).
- Produces:
  - `PARAMETER_NAMES`;
  - `EngineConsistency(conf_provider)`, with `.enabled` (a plain attribute), `.persist()` and `.visible(table, default_engine)`;
  - `VoiceConsistency(conf_provider, roles, language)`, with an `.enabled` property, `.main_locale(voice)` and `.follow(voice)`;
  - `ParameterConsistency(conf_provider)`, with an `.enabled` property, `.copy_from(store, base_name)` and `.shared_section(synth_name)`;
  - `ConfigVoiceSettingsRepository(conf, synth_name, parameters=None)`.

- [ ] **Step 1: Write the failing test**

```python
"""The three KeepMainLocale* policies."""

import importlib.util
import sys
from types import ModuleType, SimpleNamespace


def load_policy(monkeypatch):
	package = ModuleType("policy_pkg")
	package.__path__ = ["addon/synthDrivers/WorldVoice"]
	monkeypatch.setitem(sys.modules, "policy_pkg", package)
	spec = importlib.util.spec_from_file_location(
		"policy_pkg.mainLocalePolicy", "addon/synthDrivers/WorldVoice/mainLocalePolicy.py",
	)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module


def flags(**values):
	return {"WorldVoice": {"autoLanguageSwitching": {
		"KeepMainLocaleEngineConsistent": values.get("engine", True),
		"KeepMainLocaleVoiceConsistent": values.get("voice", True),
		"KeepMainLocaleParameterConsistent": values.get("parameter", False),
	}}, "speech": {"WorldVoice": {"rate": 70}}}


def test_engine_consistency_is_a_pending_flag_until_persisted(monkeypatch):
	module = load_policy(monkeypatch)
	conf = flags(engine=True)
	policy = module.EngineConsistency(lambda: conf)
	table = [SimpleNamespace(engine="A", name="a"), SimpleNamespace(engine="B", name="b")]
	assert [v.name for v in policy.visible(table, "A")] == ["a"]
	policy.enabled = False
	assert [v.name for v in policy.visible(table, "A")] == ["a", "b"]
	assert conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"] is True
	policy.persist()
	assert conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"] is False


def test_voice_consistency_follows_the_main_voice_only_when_enabled(monkeypatch):
	module = load_policy(monkeypatch)
	conf = flags(voice=False)
	assigned = []
	roles = SimpleNamespace(assign=lambda locale, voice: assigned.append((locale, voice)))
	policy = module.VoiceConsistency(lambda: conf, roles, language=lambda: "zh_TW")
	voice = SimpleNamespace(name="A:a", language="en_US")
	policy.follow(voice)
	assert assigned == []
	policy.enabled = True
	assert conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"] is True
	policy.follow(voice)
	policy.follow(SimpleNamespace(name="B:b", language=None))
	assert assigned == [("en", "A:a"), ("zh", "B:b")]


def test_parameter_copy_updates_each_voice_once(monkeypatch):
	module = load_policy(monkeypatch)
	updates = {}
	class State:
		def __init__(self, key):
			self.key = key
		def update(self, **values):
			updates.setdefault(self.key, []).append(values)
	base = SimpleNamespace(rate=72, pitch=60, volume=70, inflection=55, rateBoost=True, variant="x")
	store = SimpleNamespace(
		snapshot=lambda key: base, keys=lambda: ("a", "b"), state=State,
	)
	module.ParameterConsistency(lambda: flags()).copy_from(store, "a")
	expected = [{"rate": 72, "pitch": 60, "volume": 70, "inflection": 55, "rateBoost": True}]
	assert updates == {"a": expected, "b": expected}


def test_shared_section_only_when_enabled_and_available(monkeypatch):
	module = load_policy(monkeypatch)
	conf = flags(parameter=False)
	policy = module.ParameterConsistency(lambda: conf)
	assert policy.shared_section(lambda: "WorldVoice") is None
	policy.enabled = True
	assert policy.shared_section(lambda: "WorldVoice") == {"rate": 70}
	def unavailable():
		raise RuntimeError("no synth")
	assert policy.shared_section(unavailable) is None
	assert policy.shared_section(lambda: "Other") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_main_locale_policy.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

`mainLocalePolicy.py`:

```python
"""The three "keep main locale consistent" options, each owning its config flag."""

from collections.abc import Callable, Mapping
from typing import Any

from .roles import getPrimaryLocale

PARAMETER_NAMES = ("rate", "pitch", "volume", "inflection", "rateBoost")


def _flags(conf_provider: Callable[[], Any]) -> Any:
	return conf_provider()["WorldVoice"]["autoLanguageSwitching"]


class EngineConsistency:
	"""KeepMainLocaleEngineConsistent: role choices come from the main voice's engine.

	``enabled`` is a pending value the settings panel previews; ``persist`` saves it.
	"""

	_KEY = "KeepMainLocaleEngineConsistent"

	def __init__(self, conf_provider: Callable[[], Any]):
		self._conf_provider = conf_provider
		self.enabled = bool(_flags(conf_provider)[self._KEY])

	def persist(self) -> None:
		_flags(self._conf_provider)[self._KEY] = self.enabled

	def visible(self, table, default_engine: str) -> list:
		if self.enabled:
			return [voice for voice in table if voice.engine == default_engine]
		return list(table)


class VoiceConsistency:
	"""KeepMainLocaleVoiceConsistent: the main locale's role follows the main voice."""

	_KEY = "KeepMainLocaleVoiceConsistent"

	def __init__(self, conf_provider: Callable[[], Any], roles, language: Callable[[], str]):
		self._conf_provider = conf_provider
		self._roles = roles
		self._language = language

	@property
	def enabled(self) -> bool:
		return bool(_flags(self._conf_provider)[self._KEY])

	@enabled.setter
	def enabled(self, value: bool) -> None:
		_flags(self._conf_provider)[self._KEY] = value

	def main_locale(self, voice) -> str:
		return getPrimaryLocale(voice.language or self._language())

	def follow(self, voice) -> None:
		if self.enabled:
			self._roles.assign(self.main_locale(voice), voice.name)


class ParameterConsistency:
	"""KeepMainLocaleParameterConsistent: every voice speaks with the main voice's parameters."""

	_KEY = "KeepMainLocaleParameterConsistent"

	def __init__(self, conf_provider: Callable[[], Any]):
		self._conf_provider = conf_provider

	@property
	def enabled(self) -> bool:
		return bool(_flags(self._conf_provider)[self._KEY])

	@enabled.setter
	def enabled(self, value: bool) -> None:
		_flags(self._conf_provider)[self._KEY] = value

	def copy_from(self, store, base_name: str) -> None:
		base = store.snapshot(base_name)
		values = {name: getattr(base, name) for name in PARAMETER_NAMES}
		for key in store.keys():
			# One update per voice keeps each copy atomic for a worker activation.
			store.state(key).update(**values)

	def shared_section(self, synth_name: Callable[[], str]) -> Mapping | None:
		"""The main synth's speech settings every voice loads from, or None."""
		if not self.enabled:
			return None
		try:
			return self._conf_provider()["speech"][synth_name()]
		except Exception:
			# Preserve the legacy fallback even during synth startup.
			return None
```

`configRepository.py`:

```python
"""The existing NVDA config format, accessed through injected dependencies."""

from collections.abc import Callable, Mapping, MutableMapping

from .mainLocalePolicy import ParameterConsistency
from .runtime.models import SettingValue, VoiceSpec, VoiceValues
from .runtime.settings import VOICE_PARAMETERS


class ConfigVoiceSettingsRepository:
	def __init__(
		self,
		conf: MutableMapping,
		synth_name: Callable[[], str],
		parameters: ParameterConsistency | None = None,
	):
		self._conf = conf
		self._synth_name = synth_name
		self._parameters = parameters or ParameterConsistency(lambda: conf)

	def load(self, spec: VoiceSpec) -> VoiceValues:
		voices = self._conf["WorldVoice"]["voices"]
		values = {name: convert(default) for name, convert, default in VOICE_PARAMETERS}
		if spec.name not in voices:
			voices[spec.name] = values.copy()
		# Persist the legacy defaults, but load effective main-synth values on
		# first use too, before the shared state establishes its edit baseline.
		source = self._parameters.shared_section(self._synth_name)
		if source is None:
			source = voices[spec.name]
		for name, convert, _ in VOICE_PARAMETERS:
			value = source.get(name, None)
			if value is not None:
				values[name] = convert(value)
		return values

	# save() unchanged
```

`tests/runtime_harness.load_config_repository` registers only the `runtime` subpackages. `configRepository` now imports `.mainLocalePolicy` and `.roles` relatively; with `package.__path__` pointing at the real directory, both load from file. Neither imports NVDA modules, so `forbid_legacy_runtime_imports` stays satisfied.

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_main_locale_policy.py tests/test_voice_config_repository.py -q` → all pass.
Then run `python3 -m pytest tests -q` → all pass.

- [ ] **Step 5: Commit**

```bash
ruff format addon/synthDrivers/WorldVoice/mainLocalePolicy.py addon/synthDrivers/WorldVoice/configRepository.py
git add addon/synthDrivers/WorldVoice/mainLocalePolicy.py addon/synthDrivers/WorldVoice/configRepository.py tests/test_main_locale_policy.py
git commit -m "feat: put the three main-locale consistency options in one policy module

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `VoiceManager` delegates to roles and policies

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voiceManager.py`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py` (`_set_voice_parameter` flag read)
- Test: `tests/test_voice_manager_roles.py` (create); existing manager tests that build `object.__new__(VoiceManager)` get `manager._init_policies()`.

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces:
  - `VoiceManager(..., roles=None)`;
  - `VoiceManager._init_policies(roles=None)`;
  - attributes `roles`, `engine_consistency`, `voice_consistency`, `parameter_consistency`;
  - the `keepMainLocaleEngineConsistent` property;
  - `_visible_table()`.
- `voiceManager.getPrimaryLocale` stays importable (re-exported).

- [ ] **Step 1: Write the failing test**

```python
"""VoiceManager answers role and consistency questions through its repository and policies."""

import sys
import types

from test_f4_voice_state import _load_voice_manager


def make_manager(monkeypatch, *, engine=True, voice=True):
	module = _load_voice_manager(monkeypatch, {})
	conf = sys.modules["config"].conf
	conf["WorldVoice"]["autoLanguageSwitching"].update(
		KeepMainLocaleEngineConsistent=engine, KeepMainLocaleVoiceConsistent=voice)
	conf["WorldVoice"]["role"] = {"fr": {"voice": "B:b"}, "en": {"voice": "X:gone"}}
	manager = object.__new__(module.VoiceManager)
	manager._init_policies()
	spec = module.VoiceMeta
	manager.table = [spec("a", "A:a", "A", "en_US", "A", "en_US"), spec("b", "B:b", "B", "fr", "B", "fr"),
		spec("c", "A:c", "C", "fr", "A", "fr")]
	manager._defaultVoiceInstance = types.SimpleNamespace(name="A:a", engine="A", language="en_US")
	return module, conf, manager


def test_engine_filter_is_shared_by_every_locale_view(monkeypatch):
	_, _, manager = make_manager(monkeypatch, engine=True)
	assert manager.languages == ["en", "fr"]
	assert manager.localeToVoicesMap == {"en": ["A:a"], "fr": ["A:c"]}
	assert set(manager.localesToNamesMap) == {"en", "fr"}
	manager.keepMainLocaleEngineConsistent = False
	assert manager.engine_consistency.enabled is False
	assert manager.localeToVoicesMap == {"en": ["A:a"], "fr": ["B:b", "A:c"]}


def test_keep_engine_consistent_prunes_through_the_repository(monkeypatch):
	_, conf, manager = make_manager(monkeypatch, engine=False)
	manager.onKeepEngineConsistent()
	assert conf["WorldVoice"]["role"] == {"fr": {"voice": "B:b"}}


def test_main_locale_voice_follows_default_voice(monkeypatch):
	_, conf, manager = make_manager(monkeypatch, voice=True)
	manager.onKeepMainLocaleVoiceConsistent()
	assert conf["WorldVoice"]["role"]["en"] == {"voice": "A:a"}


def test_configured_voice_comes_from_the_repository(monkeypatch):
	_, conf, manager = make_manager(monkeypatch)
	manager._voiceInfos = {"B:b": object()}
	manager._defaultVoiceInstance.name = "A:a"
	assert manager.getVoiceNameForLanguage("fr_CA") == "B:b"
	assert manager.getVoiceNameForLanguage("en") == "A:a"
```

Note on `languages` order: `groupVoicesByPrimaryLocale` keys follow table order, and `languages` sorts. The `localeToVoicesMap` list order follows table order (b before c).

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_voice_manager_roles.py -q`
Expected: FAIL (`_init_policies` missing).

- [ ] **Step 3: Implement in `voiceManager.py`**

- Imports:
  - `from .roles import ConfigRoleRepository, getPrimaryLocale`, plus the comment `# getPrimaryLocale is re-exported for callers of this module.`;
  - `from .mainLocalePolicy import EngineConsistency, ParameterConsistency, VoiceConsistency`;
  - delete the local `getPrimaryLocale` definition and the `re` import if unused.
- `__init__` gains the keyword-only `roles=None` and calls `self._init_policies(roles)` before `self._initialize()` (inside the try).
- Add:

```python
	def _init_policies(self, roles=None):
		conf_provider = lambda: config.conf  # noqa: E731
		self.roles = roles or ConfigRoleRepository(conf_provider)
		self.engine_consistency = EngineConsistency(conf_provider)
		self.voice_consistency = VoiceConsistency(conf_provider, self.roles, languageHandler.getLanguage)
		self.parameter_consistency = ParameterConsistency(conf_provider)

	@property
	def keepMainLocaleEngineConsistent(self):
		return self.engine_consistency.enabled

	@keepMainLocaleEngineConsistent.setter
	def keepMainLocaleEngineConsistent(self, value):
		self.engine_consistency.enabled = value

	def _visible_table(self):
		return self.engine_consistency.visible(self.table, self._defaultVoiceInstance.engine)
```

  If ruff in this repo rejects `noqa: E731` as unused, use a nested `def conf_provider(): return config.conf` instead.
- Delete the first two lines of `_initialize` (the flag read).
- `previewVoiceParameterConsistent` body: `self.parameter_consistency.copy_from(self.settings, baseInstance.name)`.
- `onKeepEngineConsistent` body: `self.roles.prune(self.localeToVoicesMap)`.
- `onKeepMainLocaleVoiceConsistent` body: `self.voice_consistency.follow(self.defaultVoiceInstance)`.
- `languages` → `groupVoicesByPrimaryLocale(self._visible_table())`, sorted and non-empty as before. `localeToVoicesMap` → `groupVoicesByPrimaryLocale(self._visible_table())`. `localesToNamesMap` → the same, mapped to readable names.
- `_getConfiguredVoiceNameForLanguage(language)` → `return self.roles.voice_for(language)`.

Main driver `_set_voice_parameter`: replace the `config.conf[...]["KeepMainLocaleParameterConsistent"]` read with `self._voiceManager.parameter_consistency.enabled`.

Tests:
- Every `object.__new__(...VoiceManager)` in `tests/` must call `manager._init_policies()` right after construction. Find them with `grep -rn "object.__new__(.*VoiceManager" tests`. Any test that then sets `manager.keepMainLocaleEngineConsistent = X` keeps working through the property.
- `tests/test_worldvoice_pipeline_settings.py::test_voice_parameters_commit_and_follow_the_consistency_policy` gives its fake manager `parameter_consistency=types.SimpleNamespace(enabled=consistent)`.
- Loaders that stub `config` without `role` or `autoLanguageSwitching` keys add them where `_init_policies` reads them: `EngineConsistency` reads the engine flag at construction.

- [ ] **Step 4: Run to verify**

Run: `python3 -m pytest tests/test_voice_manager_roles.py -q` → PASS.
Then run `python3 -m pytest tests -q` → all pass.

- [ ] **Step 5: Commit**

```bash
ruff format addon/synthDrivers/WorldVoice/voiceManager.py addon/synthDrivers/WorldVoice/__init__.py
git add addon/synthDrivers/WorldVoice/voiceManager.py addon/synthDrivers/WorldVoice/__init__.py tests/
git commit -m "refactor(voiceManager): delegate roles and main-locale policies

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(`tests/` is staged as a directory here because several harness files change. Check `git status` first: only test files may be listed.)

---

### Task 4: `RolePanelPresenter` (D1, D4, transaction)

**Files:**
- Create: `addon/globalPlugins/WorldVoice/rolePresenter.py`
- Test: `tests/test_role_presenter.py` (create)

**Interfaces:**
- Consumes:
  - `manager.beginVoiceSettingsEdit()`, `.roles`, `.engine_consistency`, `.voice_consistency`, `.parameter_consistency`;
  - `.languages`, `.localeToVoicesMap`, `.localesToNamesMap`, `.table`;
  - `.getVoiceInstance(name)`, `.getVoiceCapabilities(name)`, `.getVoiceVariants(name)`;
  - `.defaultVoiceInstance`, `.defaultVoiceName`, `.settings`, `.previewVoiceParameterConsistent(voice)`.
- Produces: `RolePanelPresenter(manager, *, speech_section, set_main_voice)` with the API in spec §4.

- [ ] **Step 1: Write the failing tests**

```python
"""The role panel's state and transaction, without wx."""

import importlib.util
import sys
import threading
import types

import pytest

from test_f4_voice_state import _load_voice_manager, _create_voices, RecordingCore
from voice_binding_harness import bind_core


PRESENTER = "addon/globalPlugins/WorldVoice/rolePresenter.py"


def load_presenter(monkeypatch):
	spec = importlib.util.spec_from_file_location("role_presenter_under_test", PRESENTER)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module.RolePanelPresenter


@pytest.fixture
def env(monkeypatch):
	module = _load_voice_manager(monkeypatch, {})
	config = sys.modules["config"]
	conf = config.conf
	conf["WorldVoice"]["autoLanguageSwitching"].update(
		KeepMainLocaleEngineConsistent=False,
		KeepMainLocaleVoiceConsistent=False,
		KeepMainLocaleParameterConsistent=False,
	)
	conf["WorldVoice"]["role"] = {"en": {"voice": "A:a"}}
	a, b = _create_voices(monkeypatch, config)
	c = type(a)(type(a._state.spec)("c", "A:c", "A:c", "en", "A", "en"), a._binding, None)
	voices = {voice.name: voice for voice in (a, b, c)}
	manager = object.__new__(module.VoiceManager)
	manager._init_policies()
	manager.settings = a._binding.settings
	manager._instanceCache = dict(voices)
	manager._voiceInfos = dict.fromkeys(voices)
	manager.table = [voice._state.spec for voice in voices.values()]
	manager._defaultVoiceInstance = a
	manager.getVoiceInstance = voices.__getitem__
	conf["speech"] = {"WorldVoice": {"voice": a.name}}
	switched = []

	def set_main_voice(name):
		switched.append(name)
		manager.defaultVoiceName = name
		conf["speech"]["WorldVoice"]["voice"] = name

	presenter = load_presenter(monkeypatch)(
		manager,
		speech_section=lambda: conf["speech"]["WorldVoice"],
		set_main_voice=set_main_voice,
	)
	return types.SimpleNamespace(
		presenter=presenter, manager=manager, conf=conf, a=a, b=b, c=c, switched=switched, config=config,
	)


def test_parameter_preview_is_undone_by_discard(env):
	env.presenter.set_parameter_consistency(True)
	env.presenter.set_parameter(env.a.name, "rate", 72)
	assert (env.a.rate, env.b.rate) == (72, 72)
	env.presenter.discard()
	assert (env.a.rate, env.b.rate) == (50, 50)
	assert env.conf["WorldVoice"]["voices"][env.a.name]["rate"] == 50


def test_unticking_parameter_consistency_restores_the_previewed_voices(env):
	env.b.rate = 64
	env.presenter.set_parameter_consistency(True)
	assert env.b.rate == env.a.rate == 50
	env.presenter.set_parameter_consistency(False)
	assert env.b.rate == 64
	env.presenter.apply()
	assert env.conf["WorldVoice"]["voices"][env.b.name]["rate"] == 64
	assert env.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] is False


def test_unticking_a_consistency_that_was_already_on_changes_nothing(env):
	env.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
	env.presenter.discard()  # re-read pending flags from config
	env.b.rate = 64
	env.presenter.set_parameter_consistency(False)
	assert env.b.rate == 64
	env.presenter.set_parameter_consistency(True)
	assert env.b.rate == 50


def test_engine_consistency_preview_cancel_and_apply(env):
	env.conf["WorldVoice"]["role"]["fr"] = {"voice": env.b.name}
	env.presenter.set_engine_consistency(True)
	assert env.manager.keepMainLocaleEngineConsistent is True
	assert [locale for locale, _ in env.presenter.locales()] == ["en"]
	assert env.conf["WorldVoice"]["role"]["fr"]["voice"] == env.b.name
	env.presenter.discard()
	assert env.manager.keepMainLocaleEngineConsistent is False
	env.presenter.set_engine_consistency(True)
	env.presenter.apply()
	assert env.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"] is True
	assert "fr" not in env.conf["WorldVoice"]["role"]
	env.presenter.discard()
	assert env.manager.keepMainLocaleEngineConsistent is True


def test_late_voice_is_restored_on_discard(env):
	late = env.manager.settings.ensure(type(env.a._state.spec)("late", "Fake:late", "Fake:late", "en", "Fake", "en"))
	late.update(rate=81)
	env.b.rate = 72
	env.presenter.discard()
	assert late.get("rate") == 50
	assert env.b.rate == 50


def test_apply_rebases_voice_and_role_edit_state(env):
	env.a.rate = 72
	env.b.rate = 64
	env.presenter.select_voice("fr", env.b.name)
	env.presenter.apply()
	assert env.conf["WorldVoice"]["voices"][env.b.name]["rate"] == 64
	assert env.conf["WorldVoice"]["role"]["fr"] == {"voice": env.b.name}
	env.a.rate = 81
	env.b.rate = 90
	env.presenter.select_voice("fr", "")
	env.presenter.discard()
	assert (env.a.rate, env.b.rate) == (72, 64)
	assert env.conf["WorldVoice"]["role"]["fr"] == {"voice": env.b.name}
	assert env.presenter.selected_voice("fr") == env.b.name


def test_main_locale_voice_consistency_switches_then_mirrors_new_voice(env):
	env.conf["WorldVoice"]["role"]["fr"] = {"voice": env.b.name}
	env.presenter.set_voice_consistency(True)
	env.presenter.select_voice("en", env.c.name)
	env.c.rate = 72
	env.presenter.apply()
	assert env.switched == [env.c.name]
	assert env.manager.defaultVoiceName == env.c.name
	assert env.conf["speech"]["WorldVoice"]["voice"] == env.c.name
	assert env.conf["speech"]["WorldVoice"]["rate"] == 72  # D4: mirrored from the new main voice
	assert env.conf["WorldVoice"]["role"] == {"en": {"voice": env.c.name}, "fr": {"voice": env.b.name}}

	env.presenter.apply()
	assert env.switched == [env.c.name]

	env.presenter.select_voice("en", env.a.name)
	env.presenter.select_voice("fr", "")
	env.c.rate = 81
	env.presenter.discard()
	assert env.c.rate == 72
	assert env.manager.defaultVoiceName == env.c.name
	assert env.conf["WorldVoice"]["role"] == {"en": {"voice": env.c.name}, "fr": {"voice": env.b.name}}


def test_save_failure_writes_nothing_else_and_keeps_pending(env, monkeypatch):
	env.presenter.select_voice("fr", env.b.name)
	env.presenter.set_engine_consistency(True)
	env.a.rate = 72
	def fail_save(*args):
		raise OSError("save failed")
	monkeypatch.setattr(env.manager.settings._repository, "save", fail_save)
	speech_before = dict(env.conf["speech"]["WorldVoice"])
	with pytest.raises(OSError, match="save failed"):
		env.presenter.apply()
	assert env.a.rate == 72
	assert env.a._state.baseline("rate") == 50
	assert env.conf["WorldVoice"]["role"] == {"en": {"voice": env.a.name}}
	assert env.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"] is False
	assert env.conf["speech"]["WorldVoice"] == speech_before
	assert env.presenter.selected_voice("fr") == env.b.name
	env.presenter.discard()
	assert env.a.rate == 50
	assert env.manager.keepMainLocaleEngineConsistent is False


def test_apply_previews_consistency_before_saving(env):
	env.presenter.set_parameter_consistency(True)
	env.a.rate = 66  # edited after the preview, e.g. via the main synth
	env.presenter.apply()
	assert env.conf["WorldVoice"]["voices"][env.b.name]["rate"] == 66


def test_queries_go_through_the_manager(env):
	env.manager.getVoiceCapabilities = lambda key: types.SimpleNamespace(settings={"rateBoost", "inflection"})
	env.manager.getVoiceVariants = lambda key: ({"id": "bright", "name": "Bright"},)
	assert env.presenter.capabilities(env.a.name) == {"rateBoost", "inflection"}
	assert env.presenter.variants(env.a.name) == ["default", "bright"]
	assert env.presenter.voices("en") == [(env.a.name, env.a.name), (env.c.name, env.c.name)]
	assert env.presenter.selected_voice("en") == env.a.name
	assert env.presenter.selected_voice("fr") == ""


def test_close_releases_the_edit(env):
	env.presenter.close()
	env.manager.settings.begin_edit().close()


def test_select_voice_copies_main_parameters_atomically(env, monkeypatch):
	env.a.update_settings(rate=72, pitch=61, volume=73, inflection=44, rateBoost=True)
	core = RecordingCore()
	bind_core(core, env.a, env.b)
	env.presenter.set_parameter_consistency(True)
	rate_written, release_copy, worker_done = threading.Event(), threading.Event(), threading.Event()
	errors = []
	original_update = env.b._state.update
	def gated_update(**values):
		with env.b._state._lock:
			original_update(**values)
			if values.get("rate") == 72 and not rate_written.is_set():
				rate_written.set()
				release_copy.wait(2)
	env.b.rate = 10
	monkeypatch.setattr(env.b._state, "update", gated_update)

	def activate_b():
		try:
			env.b.active()
		except Exception as error:
			errors.append(error)
		finally:
			worker_done.set()

	ui_thread = threading.Thread(target=lambda: env.presenter.select_voice("fr", env.b.name))
	worker_thread = threading.Thread(target=activate_b)
	ui_thread.start()
	try:
		assert rate_written.wait(1)
		worker_thread.start()
		assert not worker_done.wait(0.05), "worker observed settings during the UI copy"
	finally:
		release_copy.set()
		ui_thread.join(1)
		if worker_thread.ident is not None:
			worker_thread.join(1)
	assert errors == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_role_presenter.py -q`
Expected: FAIL (presenter file missing).

- [ ] **Step 3: Implement `rolePresenter.py`**

```python
"""State and transaction of the WorldVoice speech-role settings panel, without wx."""

from collections.abc import Callable, MutableMapping

PARAMETER_NAMES = ("rate", "pitch", "volume", "inflection", "rateBoost")


class RolePanelPresenter:
	"""Pending role choices and consistency flags over one shared voice edit.

	Voice parameters change live (preview) through the shared edit; apply()
	saves them, then roles, flags, the main voice and its speech section.
	"""

	def __init__(
		self,
		manager,
		*,
		speech_section: Callable[[], MutableMapping],
		set_main_voice: Callable[[str], None],
	):
		self._manager = manager
		self._speech_section = speech_section
		self._set_main_voice = set_main_voice
		self._edit = manager.beginVoiceSettingsEdit()
		self._pending: dict[str, str] = {}
		self._initial_engine = manager.engine_consistency.enabled
		self._before_parameter_preview: dict[str, dict] | None = None
		self._read_flags()

	def _read_flags(self):
		self.keep_engine = self._manager.engine_consistency.enabled
		self.keep_voice = self._manager.voice_consistency.enabled
		self.keep_parameters = self._manager.parameter_consistency.enabled

	# Queries

	def locales(self) -> list[tuple[str, str]]:
		names = self._manager.localesToNamesMap
		return [(locale, names[locale]) for locale in self._manager.languages]

	def voices(self, locale: str) -> list[tuple[str, str]]:
		descriptions = {voice.name: voice.description for voice in self._manager.table}
		names = []
		for name in self._manager.localeToVoicesMap.get(locale, []):
			if name not in names:
				names.append(name)
		return [(name, descriptions.get(name) or name) for name in names]

	def selected_voice(self, locale: str) -> str:
		if locale in self._pending:
			return self._pending[locale]
		return self._manager.roles.assignments().get(locale, "")

	def voice(self, name: str):
		return self._manager.getVoiceInstance(name)

	def capabilities(self, name: str) -> frozenset:
		return self._manager.getVoiceCapabilities(name).settings if name else frozenset()

	def variants(self, name: str) -> list[str]:
		return ["default"] + [item["id"] for item in self._manager.getVoiceVariants(name) if item != ""]

	# Edits

	def _main_parameters(self) -> dict:
		base = self._manager.defaultVoiceInstance.snapshot()
		return {parameter: getattr(base, parameter) for parameter in PARAMETER_NAMES}

	def select_voice(self, locale: str, name: str):
		self._pending[locale] = name
		if not name:
			return None
		voice = self.voice(name)
		if self.keep_parameters:
			voice.update_settings(**self._main_parameters())
		return voice

	def set_parameter(self, name: str, parameter: str, value) -> None:
		voice = self.voice(name)
		setattr(voice, parameter, value)
		if self.keep_parameters:
			self._manager.previewVoiceParameterConsistent(voice)

	def set_variant(self, name: str, value: str) -> None:
		self.voice(name).variant = value

	def set_engine_consistency(self, enabled: bool) -> None:
		self.keep_engine = enabled
		self._manager.engine_consistency.enabled = enabled

	def set_voice_consistency(self, enabled: bool) -> None:
		self.keep_voice = enabled

	def set_parameter_consistency(self, enabled: bool) -> None:
		if enabled and not self.keep_parameters:
			settings = self._manager.settings
			self._before_parameter_preview = {
				key: {parameter: settings.state(key).get(parameter) for parameter in PARAMETER_NAMES}
				for key in settings.keys()
			}
			self.keep_parameters = True
			self._manager.previewVoiceParameterConsistent(self._manager.defaultVoiceInstance)
		elif not enabled and self.keep_parameters:
			self.keep_parameters = False
			# Undo only this dialog's preview, keeping other edits made before it.
			for key, values in (self._before_parameter_preview or {}).items():
				self._manager.settings.state(key).update(**values)
			self._before_parameter_preview = None

	# Transaction

	def apply(self) -> None:
		manager = self._manager
		if self.keep_parameters:
			manager.previewVoiceParameterConsistent(manager.defaultVoiceInstance)
		self._edit.apply()  # A failure leaves everything below unsaved.

		assignments = manager.roles.assignments()
		for locale, name in self._pending.items():
			if name:
				assignments[locale] = name
			else:
				assignments.pop(locale, None)
		manager.engine_consistency.enabled = self.keep_engine
		manager.engine_consistency.persist()
		manager.voice_consistency.enabled = self.keep_voice
		manager.parameter_consistency.enabled = self.keep_parameters
		available = manager.localeToVoicesMap
		manager.roles.save(
			{locale: name for locale, name in assignments.items() if locale in available and name in available[locale]},
		)

		if self.keep_voice:
			chosen = self._pending.get(manager.voice_consistency.main_locale(manager.defaultVoiceInstance))
			if chosen and chosen != manager.defaultVoiceName:
				self._set_main_voice(chosen)

		try:
			section = self._speech_section()
		except KeyError:
			section = None
		if section is not None:
			snapshot = manager.settings.snapshot(manager.defaultVoiceName)
			for parameter in PARAMETER_NAMES:
				section[parameter] = getattr(snapshot, parameter)

		self._pending.clear()
		self._before_parameter_preview = None
		self._initial_engine = manager.engine_consistency.enabled

	def discard(self) -> None:
		self._edit.discard()
		self._pending.clear()
		self._before_parameter_preview = None
		self._manager.engine_consistency.enabled = self._initial_engine
		self._read_flags()

	def close(self) -> None:
		self._edit.close()
```

Use `prune_assignments` from `roles.py` instead of the inline dict comprehension if the package import is available. The presenter lives in the global plugin and imports `synthDrivers.WorldVoice.roles`; the test loads the file by path without the package. So keep the comprehension inline: it is one line and does not need the import.

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_role_presenter.py -q` → all pass.

- [ ] **Step 5: Commit**

```bash
ruff format addon/globalPlugins/WorldVoice/rolePresenter.py
git add addon/globalPlugins/WorldVoice/rolePresenter.py tests/test_role_presenter.py
git commit -m "feat(ui): add a wx-free presenter for the speech role panel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `SpeechRoleSettingsPanel` maps widgets onto the presenter (D6)

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (`SpeechRoleSettingsPanel`)
- Modify: `tests/test_voice_settings_transaction.py`. Delete the role-panel tests ported in Task 4:
  - `test_parameter_preview_is_undone_by_cancel`;
  - `test_engine_consistency_preview_cancel_and_apply`;
  - `test_dialog_late_voice_is_restored_on_discard`;
  - `test_apply_rebases_voice_and_role_edit_state`;
  - `test_main_locale_voice_consistency_repeated_apply_then_discard`;
  - `test_save_failure_keeps_pending_values_and_baseline`;
  - `test_dialog_destroy_releases_edit_session`;
  - `test_apply_previews_consistency_before_saving_resolver_only_states`;
  - `test_panel_queries_capabilities_and_variants_through_manager`;
  - `test_panel_opens_shared_edit_only_when_manager_is_ready`.

  Keep `test_main_synth_*` and the helpers they use. Read each deleted test first and confirm its assertions exist in `tests/test_role_presenter.py`. Any that do not get added there before deleting.
- Modify: `tests/test_f4_voice_state.py`. Delete `test_preview_b_while_a_is_playing_then_cancel_restores_next_segment` and `test_ui_consistency_copy_is_atomic_for_worker_activation`, and remove `_load_panel_class` if it becomes unused. Port the preview-while-playing test into `tests/test_role_presenter.py` as `test_preview_b_while_a_is_playing_then_discard_restores_next_segment`. Use the same body, replacing the panel calls with `env.presenter.set_parameter_consistency(True)`, `env.presenter.set_parameter(env.b.name, "rate", 72)` and `env.presenter.discard()`, keeping every assertion. Its playback set-up uses `RecordingCore`/`bind_core` exactly as in the original.
- Test: `tests/test_role_panel.py` (create)

**Interfaces:**
- Consumes: `RolePanelPresenter` (Task 4).

- [ ] **Step 1: Write the failing test**

```python
"""The role panel turns a failed apply into NVDA's save-abort signal."""

import ast
from pathlib import Path
import types

import pytest


PANEL = Path(__file__).resolve().parents[1] / "addon/globalPlugins/WorldVoice/speechSettingsDialog.py"


def load_panel(environment):
	tree = ast.parse(PANEL.read_text(encoding="utf-8"))
	node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SpeechRoleSettingsPanel")
	exec(compile(ast.Module(body=[node], type_ignores=[]), str(PANEL), "exec"), environment)
	return environment["SpeechRoleSettingsPanel"]


def checkbox(value):
	return types.SimpleNamespace(GetValue=lambda: value)


def test_failed_apply_shows_error_and_raises_value_error():
	messages, logged = [], []
	panel_type = load_panel({
		"SettingsPanel": object,
		"_": lambda text: text,
		"guard_errors": lambda **kwargs: (lambda method: method),
		"got_error_callback": None,
		"wx": types.SimpleNamespace(OK=1, ICON_ERROR=2),
		"gui": types.SimpleNamespace(messageBox=lambda *args: messages.append(args)),
		"log": types.SimpleNamespace(error=lambda *args, **kwargs: logged.append(args)),
	})
	panel = object.__new__(panel_type)
	panel.disable = False
	calls = []
	def apply():
		raise OSError("save failed")
	panel._presenter = types.SimpleNamespace(
		set_engine_consistency=lambda value: calls.append(("engine", value)),
		set_voice_consistency=lambda value: calls.append(("voice", value)),
		set_parameter_consistency=lambda value: calls.append(("parameter", value)),
		apply=apply,
	)
	panel._keepEngineConsistentCheckBox = checkbox(True)
	panel._keepConsistentCheckBox = checkbox(False)
	panel._keepParameterConsistentCheckBox = checkbox(True)

	with pytest.raises(ValueError):
		panel.onSave()

	assert calls == [("engine", True), ("voice", False), ("parameter", True)]
	assert messages and "save failed" in messages[0][0]
	assert logged


def test_panel_no_longer_touches_role_config_directly():
	source = PANEL.read_text(encoding="utf-8")
	for name in ("AggregatedSection", "_dataToPercist", "_defaultVoiceInstance", '["role"]'):
		assert name not in source
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_role_panel.py -q`
Expected: FAIL (the panel has no `_presenter`; source still contains `_dataToPercist`).

- [ ] **Step 3: Rewrite the panel**

- Imports: add `from .rolePresenter import RolePanelPresenter`. Keep `getPrimaryLocale` imported only if still used (it is not after the rewrite: delete it, and drop the `voiceManager` import if unused). Delete `defaultdict` from imports if unused.
- `makeSettings`: keep the two info-text early returns. Replace everything from `self._editSession = ...` through `self._dataToPercist = ...` with:

```python
		synth = getSynth()

		def set_main_voice(name):
			if getSynth().name == "WorldVoice":
				getSynth().voice = name
			config.conf["speech"]["WorldVoice"]["voice"] = name

		self._presenter = RolePanelPresenter(
			self._manager,
			speech_section=lambda: config.conf["speech"][synth.name],
			set_main_voice=set_main_voice,
		)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._onDestroy)
		self._locales = []
		self._voiceNamesByChoiceIndex = []
```

- `self._localesChoice` is created with `choices=[name for _, name in self._presenter.locales()]`, after `self._locales = [locale for locale, _ in self._presenter.locales()]`.
- The three consistency checkboxes take their initial values from `self._presenter.keep_engine`, `keep_voice` and `keep_parameters`.
- Bind `self._keepConsistentCheckBox` to a new `onKeepVoiceConsistentChange` that calls `self._presenter.set_voice_consistency(checkbox value)`.
- Delete `self._initialKeepEngineConsistent`, `self.ready` (local `ready` variable instead), `self._localeToVoices`, `self.localesToNames`, `self._voiceDescriptions` and `self._voiceNameByDescription`, along with `_resolveVoiceName`.

Methods:

```python
	@property
	def voiceInstance(self):
		voiceName = self._getSelectedVoiceName()
		return self._presenter.voice(voiceName) if voiceName else None

	def _currentLocale(self):
		index = self._localesChoice.GetCurrentSelection()
		return self._locales[index] if 0 <= index < len(self._locales) else None

	def _updateVoicesSelection(self):
		locale = self._currentLocale()
		if locale is None:
			self._voiceNamesByChoiceIndex = []
			self._voicesChoice.SetItems([])
			return
		voices = self._presenter.voices(locale)
		self._voiceNamesByChoiceIndex = [""] + [name for name, _ in voices]
		self._voicesChoice.SetItems([self.NO_SELECT] + [label for _, label in voices])
		selected = self._presenter.selected_voice(locale)
		try:
			self._voicesChoice.Select(self._voiceNamesByChoiceIndex.index(selected))
		except ValueError:
			self._voicesChoice.Select(0)
		self._showVoice(self._getSelectedVoiceName())

	def _showVoice(self, voiceName):
		if voiceName:
			voiceInstance = self._presenter.voice(voiceName)
			self._rateSlider.SetValue(voiceInstance.rate)
			self._pitchSlider.SetValue(voiceInstance.pitch)
			self._volumeSlider.SetValue(voiceInstance.volume)
			self._inflectionSlider.SetValue(voiceInstance.inflection)
			self._rateBoostCheckBox.SetValue(voiceInstance.rateBoost)
		self._updateVariantsSelection()
		self.sliderDisable()
		self.sliderEnable()

	def _updateVariantsSelection(self):
		voiceName = self._getSelectedVoiceName()
		if not voiceName:
			self._variantsChoice.SetItems([])
			return
		variants = self._presenter.variants(voiceName)
		self._variantsChoice.SetItems(variants)
		try:
			self._variantsChoice.Select(variants.index(self._presenter.voice(voiceName).variant))
		except ValueError:
			self._variantsChoice.Select(0)

	@guard_errors(callback=got_error_callback)
	def onLocaleChanged(self, event):
		self._updateVoicesSelection()

	@guard_errors(callback=got_error_callback)
	def onVoiceChange(self, event):
		locale = self._currentLocale()
		if locale is None:
			return
		self._presenter.select_voice(locale, self._getSelectedVoiceName())
		self._showVoice(self._getSelectedVoiceName())

	@guard_errors(callback=got_error_callback)
	def onVariantChange(self, event):
		voiceName = self._getSelectedVoiceName()
		if voiceName:
			self._presenter.set_variant(voiceName, self._variantsChoice.GetStringSelection())

	@guard_errors(callback=got_error_callback)
	def onKeepEngineConsistentChange(self, event):
		self._presenter.set_engine_consistency(self._keepEngineConsistentCheckBox.GetValue())
		locales = self._presenter.locales()
		self._locales = [locale for locale, _ in locales]
		self._localesChoice.SetItems([name for _, name in locales])
		self._updateVoicesSelection()

	@guard_errors(callback=got_error_callback)
	def onKeepVoiceConsistentChange(self, event):
		self._presenter.set_voice_consistency(self._keepConsistentCheckBox.GetValue())

	@guard_errors(callback=got_error_callback)
	def onKeepParameterConsistentChange(self, event):
		self._presenter.set_parameter_consistency(self._keepParameterConsistentCheckBox.GetValue())
		self._showVoice(self._getSelectedVoiceName())

	def sliderEnable(self):
		voiceName = self._getSelectedVoiceName()
		if voiceName:
			supportedSettings = self._presenter.capabilities(voiceName)
			self._rateSlider.Enable()
			self._pitchSlider.Enable()
			self._volumeSlider.Enable()
			if "inflection" in supportedSettings:
				self._inflectionSlider.Enable()
			if "rateBoost" in supportedSettings:
				self._rateBoostCheckBox.Enable()

	def _setParameter(self, parameter, value):
		voiceName = self._getSelectedVoiceName()
		if voiceName:
			self._presenter.set_parameter(voiceName, parameter, value)

	@guard_errors(callback=got_error_callback)
	def onSpeechRateSliderScroll(self, event):
		self._setParameter("rate", self._rateSlider.GetValue())
```

  The pitch, volume, inflection and rateBoost handlers follow the same one-line pattern, each with its own widget and parameter name. `sliderDisable` and `_getSelectedVoiceName` stay unchanged; delete `_getVoiceSupportedSettings`.

- Discard, destroy and save:

```python
	@guard_errors(callback=lambda self: None)
	def onDiscard(self):
		if self.disable:
			return
		self._presenter.discard()

	def _onDestroy(self, event):
		# Child control destruction also bubbles through the panel.
		if event.GetEventObject() is self:
			self._presenter.close()
		event.Skip()

	def onSave(self):
		if self.disable:
			return
		self._presenter.set_engine_consistency(self._keepEngineConsistentCheckBox.GetValue())
		self._presenter.set_voice_consistency(self._keepConsistentCheckBox.GetValue())
		self._presenter.set_parameter_consistency(self._keepParameterConsistentCheckBox.GetValue())
		try:
			self._presenter.apply()
		except Exception as error:
			log.error("Failed to save voice settings", exc_info=True)
			gui.messageBox(
				_(
					"An unexpected error occurred while processing your action.\n\n"
					"Details: {err}\n\n"
					"A full stack trace has been written to the NVDA log.",
				).format(err=str(error)),
				_("WorldVoice Setting Dialog - Error"),
				wx.OK | wx.ICON_ERROR,
			)
			# NVDA's settings dialog aborts the save and stays open only on ValueError.
			raise ValueError("WorldVoice voice settings were not saved") from error
```

  The `onSave` early return no longer needs `getSynth().name` (the panel is only active for WorldVoice: `disable` covers it).

- [ ] **Step 4: Run to verify**

Run: `python3 -m pytest tests/test_role_panel.py tests/test_role_presenter.py tests/test_voice_settings_transaction.py tests/test_f4_voice_state.py -q` → PASS.
Then run `python3 -m pytest tests -q` → all pass.

- [ ] **Step 5: Commit**

```bash
ruff format addon/globalPlugins/WorldVoice/speechSettingsDialog.py
git add addon/globalPlugins/WorldVoice/speechSettingsDialog.py tests/test_role_panel.py tests/test_role_presenter.py tests/test_voice_settings_transaction.py tests/test_f4_voice_state.py
git commit -m "refactor(ui): drive the speech role panel through its presenter

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `PipelineLogService` and D7

**Files:**
- Create: `addon/globalPlugins/WorldVoice/pipelineLog.py`
- Modify: `addon/globalPlugins/WorldVoice/__init__.py` (`check_log_record`, `enable_log_record`, `disable_log_record`)
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (`LogSettingsPanel.isValid/onSave`)
- Test: `tests/test_pipeline_log.py`

**Interfaces:**
- Produces:
  - `PipelineLogService(conf_provider, exporter)`, with `.enabled`, `.enable()`, `.disable()` and `.export()`;
  - `confirm_enable(*, allow_cancel) -> int`, `ask_export() -> bool`, `ask_disable_on_start() -> bool`;
  - the module singleton `pipeline_log`.

- [ ] **Step 1: Write the failing tests**

```python
"""Pipeline log switching is shared by the plugin scripts and the log panel."""

import ast
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "addon/globalPlugins/WorldVoice/pipelineLog.py"
PANEL = ROOT / "addon/globalPlugins/WorldVoice/speechSettingsDialog.py"


def load_service(monkeypatch, answers=None):
	answers = answers or []
	asked = []
	stubs = {
		"config": types.SimpleNamespace(conf={"WorldVoice": {"log": {"enable": False}}}),
		"gui": types.SimpleNamespace(mainFrame=None, messageBox=lambda *args: asked.append(args) or answers.pop(0)),
		"wx": types.SimpleNamespace(YES=2, NO=8, CANCEL=16),
		"logHandler": types.SimpleNamespace(log=types.SimpleNamespace(error=lambda *a, **k: asked.append("logged"))),
		"addonHandler": types.SimpleNamespace(initTranslation=lambda: None),
		"synthDrivers": types.SimpleNamespace(__path__=[]),
		"synthDrivers.WorldVoice": types.SimpleNamespace(__path__=[]),
		"synthDrivers.WorldVoice.pipeline": types.SimpleNamespace(pl=types.SimpleNamespace(export=lambda: asked.append("exported"))),
	}
	for name, module in stubs.items():
		monkeypatch.setitem(sys.modules, name, module)
	import builtins
	monkeypatch.setattr(builtins, "_", lambda text: text, raising=False)
	spec = importlib.util.spec_from_file_location("pipeline_log_under_test", SERVICE)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module, stubs["config"].conf, asked


def test_service_switches_config_and_swallows_export_errors(monkeypatch):
	module, conf, asked = load_service(monkeypatch)
	def broken():
		raise OSError("disk")
	service = module.PipelineLogService(lambda: conf, broken)
	service.enable()
	assert service.enabled and conf["WorldVoice"]["log"]["enable"] is True
	service.disable()
	assert conf["WorldVoice"]["log"]["enable"] is False
	service.export()
	assert asked == ["logged"]


def test_prompts_map_answers(monkeypatch):
	module, _, asked = load_service(monkeypatch, answers=[2, 8, 2])
	assert module.confirm_enable(allow_cancel=True) == 2
	assert module.ask_export() is False
	assert module.ask_disable_on_start() is True
	assert asked[0][2] == 2 | 8 | 16


def test_log_panel_no_unticks_enable(monkeypatch):
	tree = ast.parse(PANEL.read_text(encoding="utf-8"))
	node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LogSettingsPanel")
	node.body = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name in {"isValid", "onEnableCheckboxChange"}]
	node.bases = []
	enabled = []
	environment = {
		"wx": types.SimpleNamespace(YES=2, NO=8, CANCEL=16),
		"pipeline_log": types.SimpleNamespace(enabled=False),
		"confirm_enable": lambda *, allow_cancel: 8,
	}
	exec(compile(ast.Module(body=[node], type_ignores=[]), str(PANEL), "exec"), environment)
	panel = environment["LogSettingsPanel"]()
	state = {"value": True}
	panel._enable_checkbox = types.SimpleNamespace(GetValue=lambda: state["value"], SetValue=lambda v: state.update(value=v))
	panel.sliderEnable = lambda: enabled.append(True)
	panel.sliderDisable = lambda: enabled.append(False)
	assert panel.isValid() is True
	assert state["value"] is False
	assert enabled == [False]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_pipeline_log.py -q` → FAIL (`pipelineLog.py` missing; `isValid` references `config`).

- [ ] **Step 3: Implement**

`pipelineLog.py`:

```python
"""Turning the speech pipeline log on and off, shared by the plugin and the log panel."""

import addonHandler
import config
import gui
from logHandler import log
import wx

from synthDrivers.WorldVoice.pipeline import pl

addonHandler.initTranslation()


class PipelineLogService:
	def __init__(self, conf_provider=lambda: config.conf, exporter=None):
		self._conf_provider = conf_provider
		self._exporter = exporter or pl.export

	def _section(self):
		return self._conf_provider()["WorldVoice"]["log"]

	@property
	def enabled(self) -> bool:
		return bool(self._section()["enable"])

	def enable(self) -> None:
		self._section()["enable"] = True

	def disable(self) -> None:
		self._section()["enable"] = False

	def export(self) -> None:
		try:
			self._exporter()
		except Exception:
			log.error("WorldVoice: exporting the pipeline log failed", exc_info=True)


pipeline_log = PipelineLogService()


def confirm_enable(*, allow_cancel: bool) -> int:
	buttons = wx.YES | wx.NO | (wx.CANCEL if allow_cancel else 0)
	return gui.messageBox(
		# Translators: The message displayed
		_(
			"Enabling logging of WorldVoice’s speech pipeline will reduce speech response speed. If you are not debugging, we recommend keeping it disabled. Would you like to enable it anyway?",
		),
		# Translators: The title of the dialog
		_("Speech Pipeline Logging"),
		buttons,
		gui.mainFrame,
	)


def ask_export() -> bool:
	return (
		gui.messageBox(
			# Translators: The message displayed
			_(
				"Logging of WorldVoice’s speech pipeline has been disabled. Would you like to export the pipeline log now?",
			),
			# Translators: The title of the dialog
			_("Speech Pipeline Logging"),
			wx.YES | wx.NO,
			gui.mainFrame,
		)
		== wx.YES
	)


def ask_disable_on_start() -> bool:
	return (
		gui.messageBox(
			# Translators: The message displayed
			_(
				"Logging of WorldVoice’s speech pipeline is enabled. This may reduce speech response speed. If you are not debugging, we recommend disabling it. Would you like to disable it now?",
			),
			# Translators: The title of the dialog
			_("Speech Pipeline Logging"),
			wx.YES | wx.NO,
			gui.mainFrame,
		)
		== wx.YES
	)
```

The three message strings must be copied character-for-character from the current code (they contain U+2019 `’`), so existing translations still match.

Plugin:

```python
	def script_switch_log_record(self, gesture):
		if not pipeline_log.enabled:
			wx.CallAfter(self.enable_log_record)
		else:
			wx.CallAfter(self.disable_log_record)

	def check_log_record(self):
		if pipeline_log.enabled and ask_disable_on_start():
			pipeline_log.disable()
			pipeline_log.export()

	def enable_log_record(self):
		if confirm_enable(allow_cancel=False) == wx.YES:
			pipeline_log.enable()
			ui.message(_("turn on WorldVoice`s log record"))

	def disable_log_record(self):
		pipeline_log.disable()
		if ask_export():
			pipeline_log.export()
			ui.message(_("turn off WorldVoice`s log record"))
```

- Import `from .pipelineLog import ask_disable_on_start, ask_export, confirm_enable, pipeline_log`.
- Drop `pl` from the plugin imports if unused.

`LogSettingsPanel`:

```python
	def isValid(self) -> bool:
		if self._enable_checkbox.GetValue() and not pipeline_log.enabled:
			answer = confirm_enable(allow_cancel=True)
			if answer == wx.CANCEL:
				self._enable_checkbox.SetValue(False)
				self.onEnableCheckboxChange(None)
				return False
			if answer != wx.YES:
				# "No" keeps logging off; show that instead of a checked box.
				self._enable_checkbox.SetValue(False)
				self.onEnableCheckboxChange(None)
		return True

	def onSave(self):
		enabled_before = pipeline_log.enabled
		enabled_after = self._enable_checkbox.GetValue()
		if enabled_after and not enabled_before:
			pipeline_log.enable()
		elif enabled_before and not enabled_after:
			pipeline_log.disable()
			if ask_export():
				wx.CallAfter(pipeline_log.export)
		super().onSave()
```

`makeSettings` uses `self._enable_checkbox.SetValue(pipeline_log.enabled)`. In `speechSettingsDialog.py`, import `from .pipelineLog import ask_export, confirm_enable, pipeline_log` and drop `pl` from the pipeline import if unused.

- [ ] **Step 4: Run to verify**

Run: `python3 -m pytest tests/test_pipeline_log.py -q` → PASS.
Then run `python3 -m pytest tests -q` → all pass.

- [ ] **Step 5: Commit**

```bash
ruff format addon/globalPlugins/WorldVoice
git add addon/globalPlugins/WorldVoice/pipelineLog.py addon/globalPlugins/WorldVoice/__init__.py addon/globalPlugins/WorldVoice/speechSettingsDialog.py tests/test_pipeline_log.py
git commit -m "refactor(ui): share pipeline log switching and keep No from enabling it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Shared core-archive extraction

**Files:**
- Create: `addon/generics/coreArchive.py`
- Modify: `addon/installTasks.py`, `addon/globalPlugins/WorldVoice/__init__.py` (`onFileImport`)
- Test: `tests/test_core_archive.py`

**Interfaces:**
- Produces: `extract_core_archive(archive_path, workspace_path) -> list[str]`, which raises `BadZipFile` when the archive is corrupt.

- [ ] **Step 1: Write the failing tests**

```python
"""One extraction routine serves installation and the Import menu."""

import ast
import importlib.util
from pathlib import Path
import sys
import types
from zipfile import BadZipFile, ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "addon/generics/coreArchive.py"
INSTALL = ROOT / "addon/installTasks.py"
PLUGIN = ROOT / "addon/globalPlugins/WorldVoice/__init__.py"


def load(path, name, monkeypatch, logged):
	monkeypatch.setitem(sys.modules, "logHandler", types.SimpleNamespace(log=types.SimpleNamespace(
		info=lambda *a: logged.append(("info",) + a), warning=lambda *a: logged.append(("warning",) + a),
		error=lambda *a: logged.append(("error",) + a), exception=lambda *a: logged.append(("exception",) + a),
	)))
	spec = importlib.util.spec_from_file_location(name, path)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, name, module)
	spec.loader.exec_module(module)
	return module


def make_zip(path, **members):
	with ZipFile(path, "w") as archive:
		for name, data in members.items():
			archive.writestr(name, data)
	return str(path)


def test_extracts_members_and_reports_skipped(tmp_path, monkeypatch):
	logged = []
	module = load(ARCHIVE, "core_archive_under_test", monkeypatch, logged)
	archive = make_zip(tmp_path / "core.zip", **{"Engine/a.txt": "a", "Engine/b.txt": "b"})
	workspace = tmp_path / "ws"
	assert module.extract_core_archive(archive, str(workspace)) == []
	assert (workspace / "Engine/a.txt").read_text() == "a"
	original = ZipFile.extract
	def locked(self, member, path=None, pwd=None):
		if member.filename.endswith("b.txt"):
			raise PermissionError("in use")
		return original(self, member, path, pwd)
	monkeypatch.setattr(ZipFile, "extract", locked)
	assert module.extract_core_archive(archive, str(workspace)) == ["Engine/b.txt"]


def test_corrupt_archive_raises_bad_zip(tmp_path, monkeypatch):
	module = load(ARCHIVE, "core_archive_under_test", monkeypatch, [])
	broken = tmp_path / "broken.zip"
	broken.write_bytes(b"not a zip")
	with pytest.raises(BadZipFile):
		module.extract_core_archive(str(broken), str(tmp_path / "ws"))


@pytest.mark.parametrize("corrupt", [False, True])
def test_install_always_removes_the_archive(tmp_path, monkeypatch, corrupt):
	logged = []
	monkeypatch.setitem(sys.modules, "config", types.SimpleNamespace(conf={}))
	monkeypatch.setitem(sys.modules, "globalVars", types.SimpleNamespace())
	module = load(INSTALL, "install_tasks_under_test", monkeypatch, logged)
	archive = tmp_path / "core.zip"
	if corrupt:
		archive.write_bytes(b"not a zip")
	else:
		make_zip(archive, **{"x.txt": "x"})
	module._extract_core_archive(str(archive), str(tmp_path / "ws"))
	assert not archive.exists()
	assert any(entry[0] == "error" for entry in logged) is corrupt


def test_menu_import_reports_a_corrupt_archive(tmp_path):
	tree = ast.parse(PLUGIN.read_text(encoding="utf-8"))
	plugin = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GlobalPlugin")
	method = next(n for n in plugin.body if isinstance(n, ast.FunctionDef) and n.name == "onFileImport")
	broken = tmp_path / "broken.zip"
	broken.write_bytes(b"not a zip")
	shown = []

	class FileDialog:
		def __init__(self, *args, **kwargs):
			pass
		def __enter__(self):
			return self
		def __exit__(self, *args):
			return False
		def ShowModal(self):
			return 1
		def GetPath(self):
			return str(broken)

	environment = {
		"wx": types.SimpleNamespace(FileDialog=FileDialog, ID_OK=1, OK=4, CANCEL=16, ICON_WARNING=0),
		"gui": types.SimpleNamespace(mainFrame=None, messageBox=lambda *args: shown.append(args) or 16),
		"_": lambda text: text,
		"os": __import__("os"),
		"globalVars": types.SimpleNamespace(appArgs=types.SimpleNamespace(configPath=str(tmp_path))),
		"log": types.SimpleNamespace(exception=lambda *a: None, info=lambda *a: None, warning=lambda *a: None),
		"extract_core_archive": load(ARCHIVE, "core_archive_for_plugin", pytest.MonkeyPatch(), []).extract_core_archive,
	}
	exec(compile(ast.Module(body=[method], type_ignores=[]), str(PLUGIN), "exec"), environment)
	environment["onFileImport"](None, None)
	assert shown and shown[0][0] == "Import fail"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_core_archive.py -q` → FAIL (`coreArchive.py` missing).

- [ ] **Step 3: Implement**

`addon/generics/coreArchive.py`:

```python
"""Extract a WorldVoice core archive into the workspace, skipping files in use."""

import os
from zipfile import BadZipFile, ZipFile

from logHandler import log


def extract_core_archive(archive_path: str, workspace_path: str) -> list[str]:
	"""Extract every member; return the names skipped because they are in use.

	Raises BadZipFile when the archive is corrupt.
	"""
	name = os.path.basename(archive_path)
	with ZipFile(archive_path, "r") as core_file:
		try:
			bad_member = core_file.testzip()
		except (BadZipFile, RuntimeError) as error:
			raise BadZipFile(f"Corrupted archive '{name}': {error}") from error
		if bad_member is not None:
			raise BadZipFile(f"Corrupted archive '{name}': bad member {bad_member}")
		skipped = []
		for member in core_file.infolist():
			try:
				core_file.extract(member, path=workspace_path)
			except Exception as error:
				# Catching a broad Exception is intentional. Locked files (e.g., in-use DLLs)
				# can raise different errors on different OSes. This safely skips them.
				log.warning(f"Could not extract '{member.filename}' (likely in use): {error}")
				skipped.append(member.filename)
	if skipped:
		log.warning(f"Update complete. Skipped {len(skipped)} in-use file(s): {skipped}")
	else:
		log.info("All components extracted successfully.")
	return skipped
```

`ZipFile(...)` on a non-zip file raises `BadZipFile` itself, which satisfies the corrupt-archive test.

`installTasks.py`:

```python
import importlib.util
import os
from zipfile import BadZipFile

from logHandler import log

import config
import globalVars


def _load_core_archive():
	# Load by path: during installation an older `generics` may already be imported.
	path = os.path.join(os.path.dirname(__file__), "generics", "coreArchive.py")
	spec = importlib.util.spec_from_file_location("_worldvoice_install_core_archive", path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def _extract_core_archive(archive_path, workspace_path):
	log.info(f"Found '{os.path.basename(archive_path)}', preparing to extract to '{workspace_path}'")
	try:
		_load_core_archive().extract_core_archive(archive_path, workspace_path)
	except BadZipFile as e:
		log.error(f"Cannot extract corrupted archive '{os.path.basename(archive_path)}': {e}")
	except Exception:
		# Catch any other unexpected errors during I/O or ZipFile init.
		log.exception(f"An unexpected error occurred while processing '{os.path.basename(archive_path)}'")
	finally:
		# (keep the existing removal block unchanged)
```

`onInstall` is unchanged.

Plugin: add `from generics.coreArchive import extract_core_archive` beside the existing `generics` import. `onFileImport` becomes:

```python
	def onFileImport(self, event):
		with wx.FileDialog(
			gui.mainFrame,
			message=_("Import file..."),
			wildcard="zip files (*.zip)|*.zip",
		) as entryDialog:
			if entryDialog.ShowModal() != wx.ID_OK:
				return
			core_zip_path = entryDialog.GetPath()

		workspace_path = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace")
		try:
			os.makedirs(workspace_path, exist_ok=True)
			extract_core_archive(core_zip_path, workspace_path)
		except Exception:
			log.exception(
				f"An unexpected error occurred while processing '{os.path.basename(core_zip_path)}'",
			)
			gui.messageBox(
				_("Import fail"),
				_("Import File"),
				wx.OK,
			)
		else:
			# (keep the existing restart prompt unchanged)
```

Drop `ZipFile, BadZipFile` from the plugin imports.

- [ ] **Step 4: Run to verify**

Run: `python3 -m pytest tests/test_core_archive.py -q` → PASS.
Then run `python3 -m pytest tests -q` → all pass.

- [ ] **Step 5: Commit**

```bash
ruff format addon/generics/coreArchive.py addon/installTasks.py addon/globalPlugins/WorldVoice/__init__.py
git add addon/generics/coreArchive.py addon/installTasks.py addon/globalPlugins/WorldVoice/__init__.py tests/test_core_archive.py
git commit -m "refactor: share core archive extraction between install and import

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `guard_errors` without `wvd`, monkey-patch note, guards

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (`got_error_callback`, `WorldVoiceSettingsDialog`)
- Modify: `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py` (comment only)
- Test: `tests/test_role_guards.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
"""Role config, consistency flags and the dialog locator each have one home."""

import ast
from pathlib import Path
import re
import types

ADDON = Path(__file__).resolve().parents[1] / "addon"
PANELS = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"


def addon_sources():
	for path in ADDON.rglob("*.py"):
		parts = path.relative_to(ADDON).parts
		if parts[:3] == ("synthDrivers", "WorldVoice", "driver") and (
			parts[3] == "sonic" or len(parts) > 5 and parts[4] == "driver"
		):
			continue
		yield path, path.read_text(encoding="utf-8")


def test_role_section_is_only_touched_by_the_repository():
	pattern = re.compile(r"\[\s*[\"']role[\"']\s*\]")
	assert [p.name for p, text in addon_sources() if pattern.search(text)] == ["roles.py"]


def test_keep_main_locale_flags_live_in_the_policy_module():
	found = {p.name for p, text in addon_sources() if "KeepMainLocale" in text}
	assert found == {"mainLocalePolicy.py", "__init__.py"}
	synth = (ADDON / "synthDrivers/WorldVoice/__init__.py").read_text(encoding="utf-8")
	assert synth.count("KeepMainLocale") == 3  # the confspec entries only


def test_error_callback_finds_its_dialog_without_a_class_registry():
	assert ".wvd" not in PANELS.read_text(encoding="utf-8")
	tree = ast.parse(PANELS.read_text(encoding="utf-8"))
	node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "got_error_callback")
	calls = []

	class Dialog:
		def onCancel(self, event):
			calls.append(("cancel", event))

	dialog = Dialog()
	environment = {
		"wx": types.SimpleNamespace(GetTopLevelParent=lambda window: dialog, CallAfter=lambda *args: calls.append(args)),
		"gui": types.SimpleNamespace(mainFrame=types.SimpleNamespace(popupSettingsDialog="popup")),
	}
	exec(compile(ast.Module(body=[node], type_ignores=[]), str(PANELS), "exec"), environment)
	environment["got_error_callback"](object())
	assert calls == [("cancel", None), ("popup", Dialog)]
```

`test_keep_main_locale_flags_live_in_the_policy_module` expects `__init__.py` to be only the synth's (confspec). The global plugin's `__init__.py` does not mention the flags; if it ever does, the count assertion still pins the synth file. The panel file must no longer contain `KeepMainLocale` after Task 5: its checkboxes read `presenter.keep_*`.

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_role_guards.py -q`
Expected: FAIL (`.wvd` present). The other two should already pass after Tasks 3 and 5; if they fail, fix the stragglers they list.

- [ ] **Step 3: Implement**

```python
def got_error_callback(panel):
	dialog = wx.GetTopLevelParent(panel)
	dialog.onCancel(None)
	wx.CallAfter(gui.mainFrame.popupSettingsDialog, type(dialog))
```

- In `WorldVoiceSettingsDialog.__init__`, delete `self.__class__.wvd = self` and `self.Bind(wx.EVT_WINDOW_DESTROY, self._onDestroy)`; delete the `_onDestroy` method.
- In `VoiceSettingsDialogs.py`, add a comment at the top of `createDriverSettings`:

```python
		# Copied from NVDA's private AutoSettingsMixin.createDriverSettings to list
		# allSupportedSettings; compare with NVDA's version on every NVDA upgrade.
```

- [ ] **Step 4: Verify everything**

Run each and check the result:

```bash
python3 -m pytest tests -q
ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select F401,F821
ruff format --check addon
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver' addon/synthDrivers/WorldVoice/driver/sonic
```

Expected: all green, `All checks passed!`, format clean, and an empty diff.

- [ ] **Step 5: Commit**

```bash
git add addon/globalPlugins/WorldVoice/speechSettingsDialog.py addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py tests/test_role_guards.py
git commit -m "refactor(ui): find the settings dialog from the panel instead of a class registry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
