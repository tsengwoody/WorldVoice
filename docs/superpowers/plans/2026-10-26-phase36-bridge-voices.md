# Phase 36: `bridge/` and `voices/` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice complex flow (DEVELOPMENT_WORKFLOW.md §4): one implementer runs every task in order,
> applying the `File:`/`Edit:` blocks byte for byte; every commit's tree ids must match this plan.
> The orchestrator dispatches the final Fable 5.1 review (§3.3, §4.5).

**Goal:** Put the NVDA/Voice boundary layer in one package `bridge/` (was `compat/` plus the root `nvdaEventBridge.py` and `indexLedger.py`), gather the five voice-management modules in `voices/`, keep a single primary-language helper in a dependency-free `locales.py`, and fix the `driver/__init__.py` and `text/__init__.py` docstrings — with no behavior change.

**Architecture:** Pure moves with `git mv`; only import lines, path strings in tests, `pyproject.toml` path lists, and the listed docstrings/comments change. Dependency direction afterwards: `voices → bridge → runtime`, `driver → bridge.voiceFacade`, `voices → locales`, `languageDetection → locales`. Both new package `__init__.py` files are empty.

**Tech Stack:** Python 3 (NVDA add-on), pytest, Hypothesis, ruff `==0.16.3` and add-trailing-comma through prek.

**Spec:** `docs/superpowers/specs/2026-10-26-phase36-bridge-voices-design.md`

**Base:** `master` `c94623b` — `HEAD:addon` = `ee9e837c3be77c9370ed1e9fca995fdf96e702ac`, `HEAD:tests` = `5ee7e1de56aab9ebcf90aff0f474c642edf13c80`; `python3 -m pytest -q -p no:cacheprovider tests` → 3213 passed, 0 skipped; `prek run --all-files` all Passed. The spec and this plan are committed under `docs/` before Task 1; `docs/` does not enter the tree ids.

**Dry run:** see the end of this plan.

## Global Constraints

- Apply every `File:` block as the file's whole content and every `Edit:` block as one exact replacement (the "Replace" text occurs exactly once in the file at that point; blocks of one file apply top to bottom). Block text is whole lines; an empty "With" block deletes the "Replace" text. The blocks are already in the form prek leaves them, so each commit passes the hooks on the first try. If a hook still changes a file, stop: the tree ids will not match (§4.4).
- Public import paths do not change: `synthDrivers.WorldVoice.driver` (`Voice`, `getVoiceKey`), `runtime.{engineControl, models, playbackWork, segmentHost, session}`, `text.arabic`, `text.chunker`, `driver.sonic._sonic`. `tests/test_plugin_voice_contract.py` is not edited and stays green.
- Never modify `driver/<Engine>/driver/`, `driver/sonic/`, `languageDetection/script_data.py`, `pipeline/unspaced_common_data.py`; engine drivers stay independently installable; never stage Neural or `ref`.
- No class, function or attribute renames in `addon/`; the only identifier renames are in `tests/` (the `compat` fixture → `bridge`, one test name) — see spec §5.5.
- ruff pinned `0.16.3`; tabs. Commits: English `<type>: <summary>` with a body saying why, no `Co-Authored-By`, `git add` with explicit paths only, check `git diff --cached --stat` first, never `--no-verify`, never `git stash`, no push, never touch the main checkout.
- Tests: one pytest process at a time (at most 3 workers), with a memory guard that kills pytest when MemAvailable < 3 GB.

## Review Focus

1. **`None`, empty and mixed-separator locales through the merged helper.** `ConfigRoleRepository.voice_for(None)` (reachable from `pipeline/__init__.py:936` when the default voice has no language) must still look `None` up without raising (the helper returns `None`, as `getPrimaryLocale` did); `""` stays `""`; `sr-Latn-RS`, `zh_Hant_TW`, upper case. Covered by Task 1 `test_primary_language_is_the_first_subtag` and the Hypothesis test `test_primary_language_matches_both_former_helpers`.
2. **Package-relative imports one level deeper** (`..runtime`, `..bridge`, `..locales`) when a test loads a moved file under an alias package with `load_source` and no parent package module (`policy_pkg.voices.mainLocalePolicy`, `roles_pkg.voices.roles`, `worldvoice_repository_test.voices.settingsRepository`, `<alias>.bridge.nvdaEvents`). Covered by `tests/test_main_locale_policy.py`, `tests/test_role_repository.py`, `tests/test_voice_config_repository.py`, `tests/test_nvda_event_bridge*.py` staying green in Tasks 2–3.
3. **The pure-runtime import guard after the move.** `forbid_legacy_runtime_imports` must still reject the legacy boundary (`bridge.engineAdapter`, `bridge.voiceFacade`, `bridge.indexCodec`, `bridge.commands`, `bridge.completionPolicies`) yet let the native contract import `bridge.indexLedger` and `bridge.nvdaEvents`, as it allowed the root modules before. Covered by Task 2 (`tests/test_runtime_adapter_contract.py` native params, `tests/test_index_ledger.py`, `tests/test_runtime_playback_context.py`).
4. **NVDA start-up through the real entry point.** `synthDrivers/WorldVoice/__init__.py` must import `bridge.*` and `voices.*` without a cycle (`voices.manager → bridge → runtime`; `driver → bridge.voiceFacade`) and `IndexLedger`/`CompletionPolicy` must be the real classes. Covered by `tests/test_runtime_composition.py::test_entry_point_imports_real_ledger_and_completion_policy` (asserts the new `__file__` paths) and `tests/test_runtime_drain_integration.py` (imports `synthDrivers.WorldVoice.voices.manager`) in Tasks 2–3.
5. **The global plugin's role panel import path** `synthDrivers.WorldVoice.voices.roles` (the only `globalPlugins` change). Covered by `tests/test_role_presenter.py` in Task 3.

Also watched: ruff per-file ignores follow the files (`tests/test_hygiene_guards.py::test_ruff_reports_nothing`), and `test_completion_rules.py` still finds the one module allowed to compare `CompletionMode`.

---

### Task 1: One primary-language helper in `locales.py` (A1, test first)

**Files:**
- Create: `addon/synthDrivers/WorldVoice/locales.py`, `tests/test_locales.py`
- Modify: `addon/synthDrivers/WorldVoice/roles.py`, `addon/synthDrivers/WorldVoice/mainLocalePolicy.py`, `addon/synthDrivers/WorldVoice/voiceCatalog.py`, `addon/synthDrivers/WorldVoice/languageDetection/__init__.py`
- Test: `tests/test_role_repository.py` (loads `roles.py` in an alias package; `test_primary_locale` moves to `test_locales.py`), `tests/test_language_detector.py` (`test_primary_language_is_the_first_subtag` moves to `test_locales.py`; helper calls renamed)

**Interfaces:**
- Consumes: nothing.
- Produces: `locales.primary_language(locale: str) -> str` (an empty or `None` locale is returned as is). Removes `roles.getPrimaryLocale` and `languageDetection.get_primary_language`.

- [ ] **Step 1: Write the failing tests**

**File:** `tests/test_locales.py`

```text
"""One primary-language helper, shared by the voice roles and the language detector."""

import ast
import re

import pytest
from addon_loader import WORLDVOICE, load_source
from hypothesis import given, strategies as st


@pytest.fixture
def locales(monkeypatch):
	return load_source(monkeypatch, "locales_under_test", WORLDVOICE / "locales.py")


@pytest.mark.parametrize(
	"locale,primary",
	[
		("en_US", "en"),
		("en-US", "en"),
		("zh_TW", "zh"),
		("ar-WW", "ar"),
		("ZH-tw", "zh"),
		("ja", "ja"),
		("sr-Latn-RS", "sr"),
		("zh_Hant_TW", "zh"),
		("", ""),
		(None, None),
	],
)
def test_primary_language_is_the_first_subtag(locales, locale, primary):
	assert locales.primary_language(locale) == primary


@given(st.text(alphabet=st.sampled_from("aZ-_ßİ"), max_size=8))
def test_primary_language_matches_both_former_helpers(locale):
	# roles.getPrimaryLocale and languageDetection.get_primary_language before phase 36.
	module = load_source(None, "locales_under_test", WORLDVOICE / "locales.py", register=False)
	former_roles = re.split(r"[-_]", locale, maxsplit=1)[0].lower() if locale else locale
	former_detection = locale.replace("-", "_").split("_", maxsplit=1)[0].lower()
	assert module.primary_language(locale) == former_roles == former_detection


def test_locales_imports_nothing():
	# The detector and the voice roles both load it; neither may pull the other in.
	tree = ast.parse((WORLDVOICE / "locales.py").read_text(encoding="utf-8"))
	assert not [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]


def test_no_other_module_defines_a_primary_language_helper():
	defined = sorted(
		f"{path.relative_to(WORLDVOICE).as_posix()}:{node.name}"
		for path in WORLDVOICE.rglob("*.py")
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
		if isinstance(node, ast.FunctionDef)
		and node.name in {"primary_language", "getPrimaryLocale", "get_primary_language"}
	)
	assert defined == ["locales.py:primary_language"]
```

- [ ] **Step 2: Run them to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_locales.py`
Expected: `3 failed, 10 errors`. The 10 errors (the parametrized fixture) and two failures (`test_primary_language_matches_both_former_helpers`, `test_locales_imports_nothing`) are `FileNotFoundError` for `addon/synthDrivers/WorldVoice/locales.py`; `test_no_other_module_defines_a_primary_language_helper` fails listing `languageDetection/__init__.py:get_primary_language` and `roles.py:getPrimaryLocale`.

- [ ] **Step 3: Add `locales.py` and use it on both sides**

**File:** `addon/synthDrivers/WorldVoice/locales.py`

```text
"""Locale string helpers shared by the voice roles and the language detector.

This module imports nothing, so either side can use it without loading the other or any NVDA
module.
"""


def primary_language(locale: str) -> str:
	"""Return the lower-case primary language subtag of a locale like en_US or en-US.

	An empty locale (or None) is returned as it is.
	"""
	if not locale:
		return locale
	return locale.replace("-", "_").split("_", maxsplit=1)[0].lower()
```

**Edit:** `addon/synthDrivers/WorldVoice/roles.py` (1/3)

Replace:

```text
import re
```

With:

```text
```

**Edit:** `addon/synthDrivers/WorldVoice/roles.py` (2/3)

Replace:

```text

def getPrimaryLocale(locale: str) -> str:
	"""Return the primary language subtag from locale strings like en_US / en-US."""
	if not locale:
		return locale
	return re.split(r"[-_]", locale, maxsplit=1)[0].lower()
```

With:

```text
from .locales import primary_language
```

**Edit:** `addon/synthDrivers/WorldVoice/roles.py` (3/3)

Replace:

```text
		for locale in (language, getPrimaryLocale(language)):
```

With:

```text
		for locale in (language, primary_language(language)):
```

**Edit:** `addon/synthDrivers/WorldVoice/mainLocalePolicy.py` (1/2)

Replace:

```text
from .roles import getPrimaryLocale
```

With:

```text
from .locales import primary_language
```

**Edit:** `addon/synthDrivers/WorldVoice/mainLocalePolicy.py` (2/2)

Replace:

```text
		return getPrimaryLocale(voice.language or self._language())
```

With:

```text
		return primary_language(voice.language or self._language())
```

**Edit:** `addon/synthDrivers/WorldVoice/voiceCatalog.py` (1/2)

Replace:

```text
from .roles import getPrimaryLocale
```

With:

```text
from .locales import primary_language
```

**Edit:** `addon/synthDrivers/WorldVoice/voiceCatalog.py` (2/2)

Replace:

```text
		groups[getPrimaryLocale(spec.locale)].append(spec.name)
```

With:

```text
		groups[primary_language(spec.locale)].append(spec.name)
```

**Edit:** `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (1/8)

Replace:

```text
from .._speechcommand import WVLangChangeCommand
from ..numberLanguage import FOLLOW, MAIN
```

With:

```text
from .._speechcommand import WVLangChangeCommand
from ..locales import primary_language
from ..numberLanguage import FOLLOW, MAIN
```

**Edit:** `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (2/8)

Replace:

```text
def get_primary_language(locale: str) -> str:
	return locale.replace("-", "_").split("_", maxsplit=1)[0].lower()


```

With:

```text
```

**Edit:** `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (3/8)

Replace:

```text
		self.availableLanguages = frozenset(get_primary_language(lang) for lang in availableLanguages)
```

With:

```text
		self.availableLanguages = frozenset(primary_language(lang) for lang in availableLanguages)
```

**Edit:** `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (4/8)

Replace:

```text
		primary = get_primary_language(language)
```

With:

```text
		primary = primary_language(language)
```

**Edit:** `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (5/8)

Replace:

```text
			configured_primary = get_primary_language(configured)
```

With:

```text
			configured_primary = primary_language(configured)
```

**Edit:** `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (6/8)

Replace:

```text
					if get_primary_language(targetLang) != get_primary_language(tmpLang):
```

With:

```text
					if primary_language(targetLang) != primary_language(tmpLang):
```

**Edit:** `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (7/8)

Replace:

```text
		if number_language != MAIN and get_primary_language(number_language) in self.availableLanguages:
```

With:

```text
		if number_language != MAIN and primary_language(number_language) in self.availableLanguages:
```

**Edit:** `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (8/8)

Replace:

```text
			if get_primary_language(target_language) != get_primary_language(current_language):
```

With:

```text
			if primary_language(target_language) != primary_language(current_language):
```

- [ ] **Step 4: Move the two old helper tests into `test_locales.py` and follow the rename**

`roles.py` now has a relative import, so `test_role_repository.py` loads it inside an alias package, as `test_main_locale_policy.py` does.

**Edit:** `tests/test_role_repository.py` (1/3)

Replace:

```text
from addon_loader import WORLDVOICE, load_source
```

With:

```text
from addon_loader import WORLDVOICE, alias_package, load_source
```

**Edit:** `tests/test_role_repository.py` (2/3)

Replace:

```text
	return load_source(monkeypatch, "roles_under_test", WORLDVOICE / "roles.py")
```

With:

```text
	alias_package(monkeypatch, "roles_pkg", WORLDVOICE)
	return load_source(monkeypatch, "roles_pkg.roles", WORLDVOICE / "roles.py")
```

**Edit:** `tests/test_role_repository.py` (3/3)

Replace:

```text


def test_primary_locale(monkeypatch):
	module = load_roles(monkeypatch)
	assert module.getPrimaryLocale("zh_TW") == "zh"
	assert module.getPrimaryLocale("en-US") == "en"
	assert module.getPrimaryLocale("") == ""
```

With:

```text
```

**Edit:** `tests/test_language_detector.py` (1/5)

Replace:

```text
@pytest.mark.parametrize(
	"locale,primary",
	[
		("en_US", "en"),
		("ar-WW", "ar"),
		("ZH-tw", "zh"),
		("ja", "ja"),
		("sr-Latn-RS", "sr"),
		("zh_Hant_TW", "zh"),
	],
)
def test_primary_language_is_the_first_subtag(env, locale, primary):
	assert env.module.get_primary_language(locale) == primary


```

With:

```text
```

**Edit:** `tests/test_language_detector.py` (2/5)

Replace:

```text
	primary = env.module.get_primary_language(language)
	installed = {env.module.get_primary_language(voice) for voice in scenario.installed}
```

With:

```text
	primary = env.module.primary_language(language)
	installed = {env.module.primary_language(voice) for voice in scenario.installed}
```

**Edit:** `tests/test_language_detector.py` (3/5)

Replace:

```text
	installed = {env.module.get_primary_language(voice) for voice in scenario.installed}
	for script, language, _base, inserted in spoken_letters(env, scenario, items, result):
		if inserted is not None:
			assert env.module.get_primary_language(inserted) in installed
```

With:

```text
	installed = {env.module.primary_language(voice) for voice in scenario.installed}
	for script, language, _base, inserted in spoken_letters(env, scenario, items, result):
		if inserted is not None:
			assert env.module.primary_language(inserted) in installed
```

**Edit:** `tests/test_language_detector.py` (4/5)

Replace:

```text
	assert all(part for part, _language in runs)
	primary = env.module.get_primary_language
	assert all(language == base for _part, language in runs if primary(language) == primary(base))
```

With:

```text
	assert all(part for part, _language in runs)
	primary = env.module.primary_language
	assert all(language == base for _part, language in runs if primary(language) == primary(base))
```

**Edit:** `tests/test_language_detector.py` (5/5)

Replace:

```text
	primary = env.module.get_primary_language
```

With:

```text
	primary = env.module.primary_language
```

- [ ] **Step 5: Run the touched tests to see green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_locales.py tests/test_role_repository.py tests/test_language_detector.py tests/test_main_locale_policy.py tests/test_voice_catalog.py`
Expected: `103 passed`.

- [ ] **Step 6: Full suite**

Run: `python3 -m pytest -q -p no:cacheprovider tests`
Expected: `3219 passed` (3213 − 1 − 6 moved items + 13 in `test_locales.py`), 0 skipped.

- [ ] **Step 7: Commit**

```bash
git add addon/synthDrivers/WorldVoice/locales.py tests/test_locales.py addon/synthDrivers/WorldVoice/roles.py addon/synthDrivers/WorldVoice/mainLocalePolicy.py addon/synthDrivers/WorldVoice/voiceCatalog.py addon/synthDrivers/WorldVoice/languageDetection/__init__.py tests/test_role_repository.py tests/test_language_detector.py
git diff --cached --stat   # 8 files
git commit -q -F - <<'EOF'
refactor: one primary-language helper in locales.py

roles.getPrimaryLocale and languageDetection.get_primary_language both
returned the lower-case text before the first "-" or "_". Keep one
implementation, primary_language, in a root module that imports nothing,
so the voice roles and the language detector share it without loading
each other. It keeps getPrimaryLocale's guard: an empty locale, or None
from a voice without a language, is returned as it is.
EOF
git rev-parse HEAD:addon HEAD:tests
```

Expected after the commit: `HEAD:addon` = `b165bfbfb55c5061242e285b14e529670d0c86c8`, `HEAD:tests` = `30c8ca3636587c0c5fbec84fbce82d429cfe9b11`

---

### Task 2: Rename `compat/` to `bridge/` and move the ledger and the NVDA event bridge into it (F2)

**Files:**
- Move: `compat/` → `bridge/` (all six files), `nvdaEventBridge.py` → `bridge/nvdaEvents.py`, `indexLedger.py` → `bridge/indexLedger.py` (under `addon/synthDrivers/WorldVoice/`)
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`, `addon/synthDrivers/WorldVoice/driver/__init__.py` (one import line), `addon/synthDrivers/WorldVoice/voiceManager.py`, the moved `bridge/engineAdapter.py`, `bridge/indexCodec.py`, `bridge/indexLedger.py`, `bridge/nvdaEvents.py`, `pyproject.toml`
- Test: `tests/conftest.py` (fixture `compat` → `bridge`), `tests/runtime_harness.py` (import guard, alias lists), `tests/runtime_drain_integration_harness.py`, `tests/voice_binding_harness.py`, and the test modules listed in Step 4

**Interfaces:**
- Consumes: Task 1's tree.
- Produces: modules `bridge.{commands, completionPolicies, engineAdapter, indexCodec, indexLedger, nvdaEvents, voiceFacade}`; `bridge/__init__.py` empty. Class names unchanged. Test fixture `bridge` (`.adapter`, `.facade`) under alias `worldvoice_bridge_test`.

- [ ] **Step 1: Move the files**

```bash
W=addon/synthDrivers/WorldVoice
git mv $W/compat $W/bridge
git mv $W/nvdaEventBridge.py $W/bridge/nvdaEvents.py
git mv $W/indexLedger.py $W/bridge/indexLedger.py
```

- [ ] **Step 2: Fix the imports of the moved modules and their importers**

`bridge/indexLedger.py` and `bridge/nvdaEvents.py` are one level deeper; `bridge/indexCodec.py` and `bridge/engineAdapter.py` now find the ledger beside them. ruff's isort orders `..` imports before `.` imports.

**Edit:** `addon/synthDrivers/WorldVoice/bridge/indexLedger.py` (1/1)

Replace:

```text
from .runtime.completion import CompletionRule, rule_for
from .runtime.models import (
```

With:

```text
from ..runtime.completion import CompletionRule, rule_for
from ..runtime.models import (
```

**Edit:** `addon/synthDrivers/WorldVoice/bridge/nvdaEvents.py` (1/2)

Replace:

```text
from .indexLedger import IndexLedger
from .runtime.completion import rule_for
from .runtime.models import (
```

With:

```text
from ..runtime.completion import rule_for
from ..runtime.models import (
```

**Edit:** `addon/synthDrivers/WorldVoice/bridge/nvdaEvents.py` (2/2)

Replace:

```text
	SegmentEventSink,
)

# Frozen, so one instance can be every binding's default.
```

With:

```text
	SegmentEventSink,
)
from .indexLedger import IndexLedger

# Frozen, so one instance can be every binding's default.
```

**Edit:** `addon/synthDrivers/WorldVoice/bridge/indexCodec.py` (1/1)

Replace:

```text
from ..indexLedger import IndexLedger
from ..runtime.models import PlaybackContext, SpeechCommands
```

With:

```text
from ..runtime.models import PlaybackContext, SpeechCommands
from .indexLedger import IndexLedger
```

**Edit:** `addon/synthDrivers/WorldVoice/bridge/engineAdapter.py` (1/1)

Replace:

```text
	from ..indexLedger import IndexLedger
```

With:

```text
	from .indexLedger import IndexLedger
```

**Edit:** `addon/synthDrivers/WorldVoice/__init__.py` (1/1)

Replace:

```text
from .compat.commands import normalize_legacy_commands
from .compat.completionPolicies import CompletionPolicy
from .configRepository import VOICE_CONFSPEC, ConfigVoiceSettingsRepository
from .engine import ready_engine_classes
from .indexLedger import IndexLedger
from .languageDetection.settings import DETECTION_CONFSPEC, detection_settings
from .numberLanguage import FOLLOW, MAIN
from .nvdaEventBridge import NvdaEventBridge
```

With:

```text
from .bridge.commands import normalize_legacy_commands
from .bridge.completionPolicies import CompletionPolicy
from .bridge.indexLedger import IndexLedger
from .bridge.nvdaEvents import NvdaEventBridge
from .configRepository import VOICE_CONFSPEC, ConfigVoiceSettingsRepository
from .engine import ready_engine_classes
from .languageDetection.settings import DETECTION_CONFSPEC, detection_settings
from .numberLanguage import FOLLOW, MAIN
```

**Edit:** `addon/synthDrivers/WorldVoice/driver/__init__.py` (1/1)

Replace:

```text
from ..compat.voiceFacade import VoiceFacade
```

With:

```text
from ..bridge.voiceFacade import VoiceFacade
```

**Edit:** `addon/synthDrivers/WorldVoice/voiceManager.py` (1/1)

Replace:

```text
from .compat.engineAdapter import LegacyEngineAdapter
from .compat.voiceFacade import LegacyVoiceBinding
from .indexLedger import IndexLedger
from .mainLocalePolicy import EngineConsistency, ParameterConsistency, VoiceConsistency
from .nvdaEventBridge import NvdaEventBridge
```

With:

```text
from .bridge.engineAdapter import LegacyEngineAdapter
from .bridge.indexLedger import IndexLedger
from .bridge.nvdaEvents import NvdaEventBridge
from .bridge.voiceFacade import LegacyVoiceBinding
from .mainLocalePolicy import EngineConsistency, ParameterConsistency, VoiceConsistency
```

- [ ] **Step 3: Move the ruff per-file ignores and the mutmut paths with the files**

Without this, `ruff check` reports TRY004 in `bridge/` and prek fails.

**Edit:** `pyproject.toml` (1/2)

Replace:

```text
	"addon/synthDrivers/WorldVoice/indexLedger.py",
	"addon/synthDrivers/WorldVoice/compat/indexCodec.py",
```

With:

```text
	"addon/synthDrivers/WorldVoice/bridge/indexLedger.py",
	"addon/synthDrivers/WorldVoice/bridge/indexCodec.py",
```

**Edit:** `pyproject.toml` (2/2)

Replace:

```text
"addon/synthDrivers/WorldVoice/compat/commands.py" = ["TRY004"]
"addon/synthDrivers/WorldVoice/compat/engineAdapter.py" = ["TRY004"]
"addon/synthDrivers/WorldVoice/compat/indexCodec.py" = ["TRY004"]
```

With:

```text
"addon/synthDrivers/WorldVoice/bridge/commands.py" = ["TRY004"]
"addon/synthDrivers/WorldVoice/bridge/engineAdapter.py" = ["TRY004"]
"addon/synthDrivers/WorldVoice/bridge/indexCodec.py" = ["TRY004"]
```

- [ ] **Step 4: Follow the move in the tests**

The `compat` fixture becomes `bridge`; `forbid_legacy_runtime_imports` forbids `bridge` modules except `indexLedger` and `nvdaEvents`, which it allowed as root modules before (spec §5.5).

**Edit:** `tests/conftest.py` (1/3)

Replace:

```text
def compat(monkeypatch, rt):
	"""The compat engine adapter and voice facade, bound to this test's runtime."""
	name = "worldvoice_compat_test"
```

With:

```text
def bridge(monkeypatch, rt):
	"""The bridge engine adapter and voice facade, bound to this test's runtime."""
	name = "worldvoice_bridge_test"
```

**Edit:** `tests/conftest.py` (2/3)

Replace:

```text
	# Remove cached compatibility imports between isolated runtime fixtures.
	for suffix in ("compat", "compat.engineAdapter", "compat.voiceFacade"):
		monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
	return SimpleNamespace(
		adapter=importlib.import_module(name + ".compat.engineAdapter"),
		facade=importlib.import_module(name + ".compat.voiceFacade"),
```

With:

```text
	# Remove cached bridge imports between isolated runtime fixtures.
	for suffix in ("bridge", "bridge.engineAdapter", "bridge.voiceFacade"):
		monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
	return SimpleNamespace(
		adapter=importlib.import_module(name + ".bridge.engineAdapter"),
		facade=importlib.import_module(name + ".bridge.voiceFacade"),
```

**Edit:** `tests/conftest.py` (3/3)

Replace:

```text
	bridge_module = importlib.import_module(package + ".nvdaEventBridge")
	models = importlib.import_module(package + ".runtime.models")
	ledger = importlib.import_module(package + ".indexLedger").IndexLedger()
```

With:

```text
	bridge_module = importlib.import_module(package + ".bridge.nvdaEvents")
	models = importlib.import_module(package + ".runtime.models")
	ledger = importlib.import_module(package + ".bridge.indexLedger").IndexLedger()
```

**Edit:** `tests/runtime_harness.py` (1/9)

Replace:

```text
	forbidden = {
		"compat",
		"driver",
```

With:

```text
	forbidden = {
		"driver",
```

**Edit:** `tests/runtime_harness.py` (2/9)

Replace:

```text
	def check(name):
		if forbidden.intersection(name.split(".")):
```

With:

```text
	# bridge/ is the legacy boundary, except the ledger and the NVDA event bridge: both are pure
	# Python, and a native engine uses them too.
	bridge_allowed = {"indexLedger", "nvdaEvents"}

	def check(name):
		parts = name.split(".")
		if forbidden.intersection(parts) or ("bridge" in parts and bridge_allowed.isdisjoint(parts)):
```

**Edit:** `tests/runtime_harness.py` (3/9)

Replace:

```text
		"indexLedger",
		"nvdaEventBridge",
		"compat",
		"compat.engineAdapter",
		"compat.indexCodec",
```

With:

```text
		"bridge",
		"bridge.indexLedger",
		"bridge.nvdaEvents",
		"bridge.engineAdapter",
		"bridge.indexCodec",
```

**Edit:** `tests/runtime_harness.py` (4/9)

Replace:

```text
	ledger = importlib.import_module(name + ".indexLedger").IndexLedger()
```

With:

```text
	ledger = importlib.import_module(name + ".bridge.indexLedger").IndexLedger()
```

**Edit:** `tests/runtime_harness.py` (5/9)

Replace:

```text
					# As compat/indexCodec.py: a segment without wire indexes is sent without its indexes.
```

With:

```text
					# As bridge/indexCodec.py: a segment without wire indexes is sent without its indexes.
```

**Edit:** `tests/runtime_harness.py` (6/9)

Replace:

```text
		legacy = importlib.import_module(name + ".compat.engineAdapter")
```

With:

```text
		legacy = importlib.import_module(name + ".bridge.engineAdapter")
```

**Edit:** `tests/runtime_harness.py` (7/9)

Replace:

```text
		bridge_type = importlib.import_module(name + ".nvdaEventBridge").NvdaEventBridge
```

With:

```text
		bridge_type = importlib.import_module(name + ".bridge.nvdaEvents").NvdaEventBridge
```

**Edit:** `tests/runtime_harness.py` (8/9)

Replace:

```text
	for suffix in ("indexLedger", "_speechcommand", "compat.indexCodec"):
```

With:

```text
	for suffix in ("bridge.indexLedger", "_speechcommand", "bridge.indexCodec"):
```

**Edit:** `tests/runtime_harness.py` (9/9)

Replace:

```text
		ledger=importlib.import_module(package_name + ".indexLedger"),
```

With:

```text
		ledger=importlib.import_module(package_name + ".bridge.indexLedger"),
```

**Edit:** `tests/runtime_drain_integration_harness.py` (1/1)

Replace:

```text
	ledger = importlib.import_module(PACKAGE + ".indexLedger").IndexLedger()
	bridge_type = importlib.import_module(PACKAGE + ".nvdaEventBridge").NvdaEventBridge
```

With:

```text
	ledger = importlib.import_module(PACKAGE + ".bridge.indexLedger").IndexLedger()
	bridge_type = importlib.import_module(PACKAGE + ".bridge.nvdaEvents").NvdaEventBridge
```

**Edit:** `tests/voice_binding_harness.py` (1/2)

Replace:

```text
	sessions = importlib.import_module(package + ".runtime.session")
	facade = importlib.import_module(package + ".compat.voiceFacade")
	repository = importlib.import_module(package + ".configRepository")
```

With:

```text
	sessions = importlib.import_module(package + ".runtime.session")
	facade = importlib.import_module(package + ".bridge.voiceFacade")
	repository = importlib.import_module(package + ".configRepository")
```

**Edit:** `tests/voice_binding_harness.py` (2/2)

Replace:

```text
	adapters = importlib.import_module(package + ".compat.engineAdapter")
	sessions = importlib.import_module(package + ".runtime.session")
	facade = importlib.import_module(package + ".compat.voiceFacade")
```

With:

```text
	adapters = importlib.import_module(package + ".bridge.engineAdapter")
	sessions = importlib.import_module(package + ".runtime.session")
	facade = importlib.import_module(package + ".bridge.voiceFacade")
```

**Edit:** `tests/test_completion_characterization.py` (1/2)

Replace:

```text
def adapter_env(monkeypatch, compat, rt, nvda_commands):
	support = load_index_support(monkeypatch, rt, "worldvoice_compat_test")
```

With:

```text
def adapter_env(monkeypatch, bridge, rt, nvda_commands):
	support = load_index_support(monkeypatch, rt, "worldvoice_bridge_test")
```

**Edit:** `tests/test_completion_characterization.py` (2/2)

Replace:

```text
		adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls(), index_ledger=index_ledger)
```

With:

```text
		adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls(), index_ledger=index_ledger)
```

**Edit:** `tests/test_completion_rules.py` (1/1)

Replace:

```text
	"compat/completionPolicies.py": None,
```

With:

```text
	"bridge/completionPolicies.py": None,
```

**Edit:** `tests/test_f4_engine_session.py` (1/2)

Replace:

```text
def engine(session_module, compat, rt):
```

With:

```text
def engine(session_module, bridge, rt):
```

**Edit:** `tests/test_f4_engine_session.py` (2/2)

Replace:

```text
		return compat.adapter.LegacyEngineAdapter(
```

With:

```text
		return bridge.adapter.LegacyEngineAdapter(
```

**Edit:** `tests/test_index_codec.py` (1/3)

Replace:

```text
def encode(env, commands):
	path = env.support.package + ".compat.indexCodec"
	assert importlib.util.find_spec(path) is not None, "Segment codec has not been implemented"
```

With:

```text
def encode(env, commands):
	path = env.support.package + ".bridge.indexCodec"
	assert importlib.util.find_spec(path) is not None, "Segment codec has not been implemented"
```

**Edit:** `tests/test_index_codec.py` (2/3)

Replace:

```text
	path = env.support.package + ".compat.indexCodec"
```

With:

```text
	path = env.support.package + ".bridge.indexCodec"
```

**Edit:** `tests/test_index_codec.py` (3/3)

Replace:

```text
	encoded = importlib.import_module(env.support.package + ".compat.indexCodec").encode_segment(
```

With:

```text
	encoded = importlib.import_module(env.support.package + ".bridge.indexCodec").encode_segment(
```

**Edit:** `tests/test_index_ledger.py` (1/1)

Replace:

```text
	monkeypatch.delitem(sys.modules, name + ".indexLedger", raising=False)
	with forbid_legacy_runtime_imports(monkeypatch):
		module = importlib.import_module(name + ".indexLedger")
```

With:

```text
	monkeypatch.delitem(sys.modules, name + ".bridge.indexLedger", raising=False)
	with forbid_legacy_runtime_imports(monkeypatch):
		module = importlib.import_module(name + ".bridge.indexLedger")
```

**Edit:** `tests/test_legacy_speech_commands.py` (1/1)

Replace:

```text
	for suffix in ("driver", "compat", "compat.commands", "_speechcommand"):
		monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
	driver = importlib.import_module(name + ".driver")
	commands = importlib.import_module(name + ".compat.commands")
```

With:

```text
	for suffix in ("driver", "bridge", "bridge.commands", "_speechcommand"):
		monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
	driver = importlib.import_module(name + ".driver")
	commands = importlib.import_module(name + ".bridge.commands")
```

**Edit:** `tests/test_nvda_event_bridge.py` (1/1)

Replace:

```text
	monkeypatch.delitem(sys.modules, f"{name}.indexLedger", raising=False)
	ledger_module = importlib.import_module(f"{name}.indexLedger")
	module = load_source(monkeypatch, f"{name}.nvdaEventBridge", RUNTIME.parent / "nvdaEventBridge.py")
```

With:

```text
	monkeypatch.delitem(sys.modules, f"{name}.bridge.indexLedger", raising=False)
	ledger_module = importlib.import_module(f"{name}.bridge.indexLedger")
	module = load_source(monkeypatch, f"{name}.bridge.nvdaEvents", RUNTIME.parent / "bridge/nvdaEvents.py")
```

**Edit:** `tests/test_nvda_event_bridge_contracts.py` (1/1)

Replace:

```text
	monkeypatch.delitem(sys.modules, f"{name}.indexLedger", raising=False)
	ledger_module = importlib.import_module(f"{name}.indexLedger")
	module = load_source(monkeypatch, f"{name}.nvdaEventBridge", RUNTIME.parent / "nvdaEventBridge.py")
```

With:

```text
	monkeypatch.delitem(sys.modules, f"{name}.bridge.indexLedger", raising=False)
	ledger_module = importlib.import_module(f"{name}.bridge.indexLedger")
	module = load_source(monkeypatch, f"{name}.bridge.nvdaEvents", RUNTIME.parent / "bridge/nvdaEvents.py")
```

**Edit:** `tests/test_runtime_completion_policies.py` (1/3)

Replace:

```text
	adapter = importlib.import_module(module.__package__ + ".compat.engineAdapter")
```

With:

```text
	adapter = importlib.import_module(module.__package__ + ".bridge.engineAdapter")
```

**Edit:** `tests/test_runtime_completion_policies.py` (2/3)

Replace:

```text
	return importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
```

With:

```text
	return importlib.import_module(env.module.__package__ + ".bridge.completionPolicies")
```

**Edit:** `tests/test_runtime_completion_policies.py` (3/3)

Replace:

```text
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.compat.completionPolicies", raising=False)
	return importlib.import_module("synthDrivers.WorldVoice.compat.completionPolicies")
```

With:

```text
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.bridge.completionPolicies", raising=False)
	return importlib.import_module("synthDrivers.WorldVoice.bridge.completionPolicies")
```

**Edit:** `tests/test_runtime_composition.py` (1/6)

Replace:

```text
	with pytest.raises(importlib.import_module(c.module.__package__ + ".indexLedger").InvalidIndexContext):
```

With:

```text
	with pytest.raises(
		importlib.import_module(c.module.__package__ + ".bridge.indexLedger").InvalidIndexContext,
	):
```

**Edit:** `tests/test_runtime_composition.py` (2/6)

Replace:

```text
		ledger = importlib.import_module(package + ".indexLedger")
		policies = importlib.import_module(package + ".compat.completionPolicies")
```

With:

```text
		ledger = importlib.import_module(package + ".bridge.indexLedger")
		policies = importlib.import_module(package + ".bridge.completionPolicies")
```

**Edit:** `tests/test_runtime_composition.py` (3/6)

Replace:

```text
		assert ledger.__file__ == str(WORLDVOICE / "indexLedger.py")
		assert policies.__file__ == str(WORLDVOICE / "compat/completionPolicies.py")
```

With:

```text
		assert ledger.__file__ == str(WORLDVOICE / "bridge/indexLedger.py")
		assert policies.__file__ == str(WORLDVOICE / "bridge/completionPolicies.py")
```

**Edit:** `tests/test_runtime_composition.py` (4/6)

Replace:

```text
def runtime_completion_selector(c, version="synthetic"):
	policies = importlib.import_module(c.module.__package__ + ".compat.completionPolicies")
	logs = []
```

With:

```text
def runtime_completion_selector(c, version="synthetic"):
	policies = importlib.import_module(c.module.__package__ + ".bridge.completionPolicies")
	logs = []
```

**Edit:** `tests/test_runtime_composition.py` (5/6)

Replace:

```text
		port._adapter.configure_completion(c.models.CompletionContract())
	policies = importlib.import_module(c.module.__package__ + ".compat.completionPolicies")
	assert policies._VERIFIED_CONTRACTS == {}
```

With:

```text
		port._adapter.configure_completion(c.models.CompletionContract())
	policies = importlib.import_module(c.module.__package__ + ".bridge.completionPolicies")
	assert policies._VERIFIED_CONTRACTS == {}
```

**Edit:** `tests/test_runtime_composition.py` (6/6)

Replace:

```text
	policies = importlib.import_module(c.module.__package__ + ".compat.completionPolicies")
```

With:

```text
	policies = importlib.import_module(c.module.__package__ + ".bridge.completionPolicies")
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (1/25)

Replace:

```text
def test_lifecycle_metadata_and_apply_order(compat, rt):
	core = Core()
	cls = legacy_class(core)
	adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
```

With:

```text
def test_lifecycle_metadata_and_apply_order(bridge, rt):
	core = Core()
	cls = legacy_class(core)
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (2/25)

Replace:

```text
def test_voice_metadata_defaults_and_canonical_key(compat, rt, extra):
	cls = legacy_class(Core())
	cls.voices = classmethod(lambda cls, core: [dict(engine="Fake", id="a", language="en_US", **extra)])
	adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
```

With:

```text
def test_voice_metadata_defaults_and_canonical_key(bridge, rt, extra):
	cls = legacy_class(Core())
	cls.voices = classmethod(lambda cls, core: [dict(engine="Fake", id="a", language="en_US", **extra)])
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (3/25)

Replace:

```text
def test_malformed_voice_metadata_does_not_hide_valid_voices(compat, rt):
```

With:

```text
def test_malformed_voice_metadata_does_not_hide_valid_voices(bridge, rt):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (4/25)

Replace:

```text
	cls.voices = classmethod(lambda cls, core: [malformed, valid])
	adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	assert adapter.list_voices() == (rt.models.VoiceSpec("a", "Fake:a", "A", "en", "Fake", "en"),)
```

With:

```text
	cls.voices = classmethod(lambda cls, core: [malformed, valid])
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	assert adapter.list_voices() == (rt.models.VoiceSpec("a", "Fake:a", "A", "en", "Fake", "en"),)
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (5/25)

Replace:

```text
def test_token_support_comes_from_actual_core(compat, support):
```

With:

```text
def test_token_support_comes_from_actual_core(bridge, support):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (6/25)

Replace:

```text
	cls.supportsCancellationToken = True  # Class claims are not authoritative.
	adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

With:

```text
	cls.supportsCancellationToken = True  # Class claims are not authoritative.
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (7/25)

Replace:

```text
def test_unsupported_generic_settings_are_not_written(compat, rt):
```

With:

```text
def test_unsupported_generic_settings_are_not_written(bridge, rt):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (8/25)

Replace:

```text
	cls.supportedSettings = classmethod(lambda cls: ["rate"])
	adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

With:

```text
	cls.supportedSettings = classmethod(lambda cls: ["rate"])
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (9/25)

Replace:

```text
def test_failed_core_creation_leaves_nothing_to_clean(compat, rt):
```

With:

```text
def test_failed_core_creation_leaves_nothing_to_clean(bridge, rt):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (10/25)

Replace:

```text
	cls.create_core = classmethod(fail_open)
	adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	session = rt.session.EngineSession(adapter, rt.settings.VoiceSettingsStore(MemoryRepository()))
```

With:

```text
	cls.create_core = classmethod(fail_open)
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	session = rt.session.EngineSession(adapter, rt.settings.VoiceSettingsStore(MemoryRepository()))
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (11/25)

Replace:

```text
def test_close_releases_adapter_state_even_when_destroy_core_fails(compat):
```

With:

```text
def test_close_releases_adapter_state_even_when_destroy_core_fails(bridge):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (12/25)

Replace:

```text
	cls.destroy_core = classmethod(fail_destroy)
	adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

With:

```text
	cls.destroy_core = classmethod(fail_destroy)
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (13/25)

Replace:

```text
def test_each_adapter_owns_its_own_core(compat):
	first_core, second_core = Core(), Core()
	first_cls, second_cls = legacy_class(first_core), legacy_class(second_core)
	first = compat.adapter.LegacyEngineAdapter(first_cls, lambda key: first_cls())
	second = compat.adapter.LegacyEngineAdapter(second_cls, lambda key: second_cls())
```

With:

```text
def test_each_adapter_owns_its_own_core(bridge):
	first_core, second_core = Core(), Core()
	first_cls, second_cls = legacy_class(first_core), legacy_class(second_core)
	first = bridge.adapter.LegacyEngineAdapter(first_cls, lambda key: first_cls())
	second = bridge.adapter.LegacyEngineAdapter(second_cls, lambda key: second_cls())
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (14/25)

Replace:

```text
def test_onecore_cached_a_b_a_restores_language(compat, rt):
```

With:

```text
def test_onecore_cached_a_b_a_restores_language(bridge, rt):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (15/25)

Replace:

```text
	store.ensure(make_spec("OneCore:b", "zh_TW")).update(rate=31)
	adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	session = rt.session.EngineSession(adapter, store)
```

With:

```text
	store.ensure(make_spec("OneCore:b", "zh_TW")).update(rate=31)
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	session = rt.session.EngineSession(adapter, store)
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (16/25)

Replace:

```text
def test_real_variant_and_waitfactor_hooks(compat, rt, monkeypatch, engine):
```

With:

```text
def test_real_variant_and_waitfactor_hooks(bridge, rt, monkeypatch, engine):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (17/25)

Replace:

```text
	adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: voice)
```

With:

```text
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: voice)
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (18/25)

Replace:

```text
def marker_env(monkeypatch, compat, rt, nvda_commands):
	support = load_index_support(monkeypatch, rt, "worldvoice_compat_test")
```

With:

```text
def marker_env(monkeypatch, bridge, rt, nvda_commands):
	support = load_index_support(monkeypatch, rt, "worldvoice_bridge_test")
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (19/25)

Replace:

```text
	adapter = compat.adapter.LegacyEngineAdapter(
```

With:

```text
	adapter = bridge.adapter.LegacyEngineAdapter(
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (20/25)

Replace:

```text
def test_legacy_without_context_preserves_commands(compat, monkeypatch):
```

With:

```text
def test_legacy_without_context_preserves_commands(bridge, monkeypatch):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (21/25)

Replace:

```text
	cls = legacy_class(core)
	adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

With:

```text
	cls = legacy_class(core)
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (22/25)

Replace:

```text
def drain_env(monkeypatch, compat, rt, nvda_commands, request):
	support = load_index_support(monkeypatch, rt, "worldvoice_compat_test")
```

With:

```text
def drain_env(monkeypatch, bridge, rt, nvda_commands, request):
	support = load_index_support(monkeypatch, rt, "worldvoice_bridge_test")
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (23/25)

Replace:

```text
	adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls(), index_ledger=ledger)
```

With:

```text
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls(), index_ledger=ledger)
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (24/25)

Replace:

```text
def test_segment_event_configuration_rejects_wrong_lifecycle_phase(compat, rt, phase):
```

With:

```text
def test_segment_event_configuration_rejects_wrong_lifecycle_phase(bridge, rt, phase):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (25/25)

Replace:

```text
	adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
```

With:

```text
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
```

**Edit:** `tests/test_runtime_playback_context.py` (1/1)

Replace:

```text
def test_models_load_without_nvda_or_compat(monkeypatch):
```

With:

```text
def test_models_load_without_nvda_or_bridge(monkeypatch):
```

**Edit:** `tests/test_runtime_request_builder.py` (1/1)

Replace:

```text
		assert ".driver" not in name and ".compat" not in name
```

With:

```text
		assert ".driver" not in name and ".bridge" not in name
```

**Edit:** `tests/test_runtime_scheduler.py` (1/1)

Replace:

```text
		assert "synthDrivers" not in name and ".compat" not in name
```

With:

```text
		assert "synthDrivers" not in name and ".bridge" not in name
```

**Edit:** `tests/test_runtime_voice_facade.py` (1/3)

Replace:

```text
def setup(compat, rt):
```

With:

```text
def setup(bridge, rt):
```

**Edit:** `tests/test_runtime_voice_facade.py` (2/3)

Replace:

```text
	binding = compat.facade.LegacyVoiceBinding(store, session, None)

	class Voice(compat.facade.VoiceFacade):
```

With:

```text
	binding = bridge.facade.LegacyVoiceBinding(store, session, None)

	class Voice(bridge.facade.VoiceFacade):
```

**Edit:** `tests/test_runtime_voice_facade.py` (3/3)

Replace:

```text
def test_facade_reads_its_engine_core_from_the_binding(setup, compat):
	core = object()
	binding = compat.facade.LegacyVoiceBinding(setup.store, setup.session, core)
```

With:

```text
def test_facade_reads_its_engine_core_from_the_binding(setup, bridge):
	core = object()
	binding = bridge.facade.LegacyVoiceBinding(setup.store, setup.session, core)
```

**Edit:** `tests/test_voice_parameter_guards.py` (1/1)

Replace:

```text
def test_the_adapter_applies_every_copyable_parameter_rate_boost_first(rt, compat):
	order = compat.adapter.APPLY_ORDER
```

With:

```text
def test_the_adapter_applies_every_copyable_parameter_rate_boost_first(rt, bridge):
	order = bridge.adapter.APPLY_ORDER
```

**Edit:** `tests/test_worldvoice_lifecycle.py` (1/1)

Replace:

```text
			index_ledger=importlib.import_module(module.__package__ + ".indexLedger").IndexLedger(),
```

With:

```text
			index_ledger=importlib.import_module(module.__package__ + ".bridge.indexLedger").IndexLedger(),
```

**Edit:** `tests/test_worldvoice_request_builder.py` (1/1)

Replace:

```text
		adapter=load("compat.engineAdapter"),
		facade=load("compat.voiceFacade"),
		commands=load("compat.commands"),
		bridge=load("nvdaEventBridge"),
```

With:

```text
		adapter=load("bridge.engineAdapter"),
		facade=load("bridge.voiceFacade"),
		commands=load("bridge.commands"),
		bridge=load("bridge.nvdaEvents"),
```

**Edit:** `tests/test_worldvoice_request_manager.py` (1/1)

Replace:

```text
	bridge_module = importlib.import_module(package_name + ".nvdaEventBridge")
```

With:

```text
	bridge_module = importlib.import_module(package_name + ".bridge.nvdaEvents")
```

**Edit:** `tests/test_worldvoice_speak.py` (1/1)

Replace:

```text
		commands=load("compat.commands"),
```

With:

```text
		commands=load("bridge.commands"),
```

- [ ] **Step 5: Check that nothing names the old paths**

Run: `git grep -n -E "compat|nvdaEventBridge" -- 'addon/*.py' 'tests/*.py' ':!addon/synthDrivers/WorldVoice/driver/*/driver/*' | grep -v RHVoice_are_languages_compatible`
Expected: no output.

- [ ] **Step 6: Run the touched tests**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_index_ledger.py tests/test_runtime_adapter_contract.py tests/test_runtime_playback_context.py tests/test_runtime_composition.py tests/test_runtime_legacy_adapter.py tests/test_nvda_event_bridge.py tests/test_nvda_event_bridge_contracts.py tests/test_runtime_completion_policies.py tests/test_worldvoice_request_builder.py tests/test_worldvoice_speak.py`
Expected: `486 passed`.

Run: `python3 -m pytest -q -p no:cacheprovider tests` → `3219 passed`, 0 skipped.

- [ ] **Step 7: Commit**

The old paths are already staged by `git mv`; name only the new ones.

```bash
W=addon/synthDrivers/WorldVoice
git add $W/bridge $W/__init__.py $W/driver/__init__.py $W/voiceManager.py pyproject.toml tests/conftest.py tests/runtime_harness.py tests/runtime_drain_integration_harness.py tests/voice_binding_harness.py tests/test_completion_characterization.py tests/test_completion_rules.py tests/test_f4_engine_session.py tests/test_index_codec.py tests/test_index_ledger.py tests/test_legacy_speech_commands.py tests/test_nvda_event_bridge.py tests/test_nvda_event_bridge_contracts.py tests/test_runtime_completion_policies.py tests/test_runtime_composition.py tests/test_runtime_legacy_adapter.py tests/test_runtime_playback_context.py tests/test_runtime_request_builder.py tests/test_runtime_scheduler.py tests/test_runtime_voice_facade.py tests/test_voice_parameter_guards.py tests/test_worldvoice_lifecycle.py tests/test_worldvoice_request_builder.py tests/test_worldvoice_request_manager.py tests/test_worldvoice_speak.py
git diff --cached --stat   # 36 files: 8 renames, 28 modified
git commit -q -F - <<'EOF'
refactor: rename compat to bridge and move the ledger and event bridge in

compat/ read as a shim waiting to be removed, but it is the permanent
boundary between NVDA, the engine wrappers and the pure runtime: the
plugin base Voice and every engine resource depend on it. The index
ledger and the NVDA event bridge belong to the same layer and sat at
the package root. bridge/ now holds all seven modules; nvdaEventBridge
becomes bridge/nvdaEvents since the package already says "bridge".
Pure move: class names and behaviour are unchanged. The test fixture
follows the package name, and the runtime import guard keeps allowing
the ledger and the event bridge while it rejects the rest of bridge/.
EOF
git rev-parse HEAD:addon HEAD:tests
```

Expected after the commit: `HEAD:addon` = `f2ef46afcc398909bc9db91a296e8feac8cd86a7`, `HEAD:tests` = `390f412c501f27a2bbbea240386c258b4440e1c1`

---

### Task 3: Gather the voice modules in `voices/` (F5)

**Files:**
- Create: `addon/synthDrivers/WorldVoice/voices/__init__.py` (empty)
- Move: `voiceManager.py` → `voices/manager.py`, `voiceCatalog.py` → `voices/catalog.py`, `roles.py` → `voices/roles.py`, `mainLocalePolicy.py` → `voices/mainLocalePolicy.py`, `configRepository.py` → `voices/settingsRepository.py` (under `addon/synthDrivers/WorldVoice/`)
- Modify: the five moved modules (imports), `addon/synthDrivers/WorldVoice/__init__.py`, `addon/globalPlugins/WorldVoice/rolePresenter.py`, `addon/synthDrivers/WorldVoice/languageDetection/settings.py` (docstring), `pyproject.toml` (mutmut paths)
- Test: `tests/conftest.py`, `tests/runtime_harness.py`, `tests/runtime_drain_integration_harness.py`, `tests/voice_binding_harness.py`, `tests/worldvoice_harness.py` and the test modules listed in Step 4

**Interfaces:**
- Consumes: Task 2's tree.
- Produces: modules `voices.{manager, catalog, roles, mainLocalePolicy, settingsRepository}`; `voices/__init__.py` empty. The `composition` fixture gains `package` (the alias root, since `module.__package__` is now `<root>.voices`).

- [ ] **Step 1: Create the package and move the files**

**File:** `addon/synthDrivers/WorldVoice/voices/__init__.py` (empty file)

```text
```

Create the empty file above first, then:

```bash
W=addon/synthDrivers/WorldVoice
git mv $W/voiceManager.py $W/voices/manager.py
git mv $W/voiceCatalog.py $W/voices/catalog.py
git mv $W/roles.py $W/voices/roles.py
git mv $W/mainLocalePolicy.py $W/voices/mainLocalePolicy.py
git mv $W/configRepository.py $W/voices/settingsRepository.py
```

- [ ] **Step 2: Fix the imports of the moved modules and their importers**

**Edit:** `addon/synthDrivers/WorldVoice/voices/manager.py` (1/1)

Replace:

```text
from .bridge.engineAdapter import LegacyEngineAdapter
from .bridge.indexLedger import IndexLedger
from .bridge.nvdaEvents import NvdaEventBridge
from .bridge.voiceFacade import LegacyVoiceBinding
from .mainLocalePolicy import EngineConsistency, ParameterConsistency, VoiceConsistency
from .roles import ConfigRoleRepository
from .runtime.completion import rule_for
from .runtime.models import CompletionContract, EngineCapabilities, VoiceSpec
from .runtime.scheduler import TaskManager
from .runtime.session import EngineSession, PlaybackPort
from .runtime.settings import VoiceEditSession, VoiceSettingsStore
from .voiceCatalog import EMPTY_CATALOG, VoiceCatalog, group_by_primary_locale
```

With:

```text
from ..bridge.engineAdapter import LegacyEngineAdapter
from ..bridge.indexLedger import IndexLedger
from ..bridge.nvdaEvents import NvdaEventBridge
from ..bridge.voiceFacade import LegacyVoiceBinding
from ..runtime.completion import rule_for
from ..runtime.models import CompletionContract, EngineCapabilities, VoiceSpec
from ..runtime.scheduler import TaskManager
from ..runtime.session import EngineSession, PlaybackPort
from ..runtime.settings import VoiceEditSession, VoiceSettingsStore
from .catalog import EMPTY_CATALOG, VoiceCatalog, group_by_primary_locale
from .mainLocalePolicy import EngineConsistency, ParameterConsistency, VoiceConsistency
from .roles import ConfigRoleRepository
```

**Edit:** `addon/synthDrivers/WorldVoice/voices/catalog.py` (1/1)

Replace:

```text
from .locales import primary_language
from .runtime.models import VoiceSpec
```

With:

```text
from ..locales import primary_language
from ..runtime.models import VoiceSpec
```

**Edit:** `addon/synthDrivers/WorldVoice/voices/mainLocalePolicy.py` (1/1)

Replace:

```text
from .locales import primary_language
from .runtime.settings import PARAMETER_NAMES
```

With:

```text
from ..locales import primary_language
from ..runtime.settings import PARAMETER_NAMES
```

**Edit:** `addon/synthDrivers/WorldVoice/voices/roles.py` (1/1)

Replace:

```text
from .locales import primary_language
```

With:

```text
from ..locales import primary_language
```

**Edit:** `addon/synthDrivers/WorldVoice/voices/settingsRepository.py` (1/1)

Replace:

```text
from .runtime.models import SettingValue, VoiceSpec, VoiceValues
from .runtime.settings import VOICE_PARAMETERS, boolean
```

With:

```text
from ..runtime.models import SettingValue, VoiceSpec, VoiceValues
from ..runtime.settings import VOICE_PARAMETERS, boolean
```

**Edit:** `addon/synthDrivers/WorldVoice/__init__.py` (1/2)

Replace:

```text
from .configRepository import VOICE_CONFSPEC, ConfigVoiceSettingsRepository
```

With:

```text
```

**Edit:** `addon/synthDrivers/WorldVoice/__init__.py` (2/2)

Replace:

```text
from .voiceManager import VoiceManager
```

With:

```text
from .voices.manager import VoiceManager
from .voices.settingsRepository import VOICE_CONFSPEC, ConfigVoiceSettingsRepository
```

**Edit:** `addon/globalPlugins/WorldVoice/rolePresenter.py` (1/1)

Replace:

```text
from synthDrivers.WorldVoice.roles import prune_assignments
from synthDrivers.WorldVoice.runtime.settings import PARAMETER_NAMES
```

With:

```text
from synthDrivers.WorldVoice.runtime.settings import PARAMETER_NAMES
from synthDrivers.WorldVoice.voices.roles import prune_assignments
```

**Edit:** `addon/synthDrivers/WorldVoice/languageDetection/settings.py` (1/1)

Replace:

```text
KeepMainLocale* flags, which mainLocalePolicy owns.
```

With:

```text
KeepMainLocale* flags, which voices/mainLocalePolicy.py owns.
```

- [ ] **Step 3: Move the mutmut paths**

**Edit:** `pyproject.toml` (1/1)

Replace:

```text
	"addon/synthDrivers/WorldVoice/configRepository.py",
	"addon/synthDrivers/WorldVoice/mainLocalePolicy.py",
```

With:

```text
	"addon/synthDrivers/WorldVoice/voices/settingsRepository.py",
	"addon/synthDrivers/WorldVoice/voices/mainLocalePolicy.py",
```

- [ ] **Step 4: Follow the move in the tests**

**Edit:** `tests/conftest.py` (1/2)

Replace:

```text
	package = manager_module.__package__
	monkeypatch.setattr(
		importlib.import_module(package + ".voiceCatalog"),
```

With:

```text
	package = manager_module.__package__.removesuffix(".voices")
	monkeypatch.setattr(
		importlib.import_module(package + ".voices.catalog"),
```

**Edit:** `tests/conftest.py` (2/2)

Replace:

```text
		module=manager_module,
		driver=driver,
```

With:

```text
		module=manager_module,
		package=package,
		driver=driver,
```

**Edit:** `tests/runtime_harness.py` (1/1)

Replace:

```text
		f"{package_name}.configRepository",
		RUNTIME.parent / "configRepository.py",
```

With:

```text
		f"{package_name}.voices.settingsRepository",
		RUNTIME.parent / "voices/settingsRepository.py",
```

**Edit:** `tests/runtime_drain_integration_harness.py` (1/1)

Replace:

```text
	manager_module = importlib.import_module(PACKAGE + ".voiceManager")
```

With:

```text
	manager_module = importlib.import_module(PACKAGE + ".voices.manager")
```

**Edit:** `tests/voice_binding_harness.py` (1/1)

Replace:

```text
	repository = importlib.import_module(package + ".configRepository")
```

With:

```text
	repository = importlib.import_module(package + ".voices.settingsRepository")
```

**Edit:** `tests/worldvoice_harness.py` (1/4)

Replace:

```text
	"""voiceManager under lifecycle_test_worldvoice, with stub config, language, log and synth modules."""
```

With:

```text
	"""voices.manager under lifecycle_test_worldvoice, with stub config, language, log and synth modules."""
```

**Edit:** `tests/worldvoice_harness.py` (2/4)

Replace:

```text
			),
		),
	)
	return load_source(monkeypatch, f"{package_name}.voiceManager", WORLDVOICE / "voiceManager.py")


def init_policies(manager):
```

With:

```text
			),
		),
	)
	return load_source(monkeypatch, f"{package_name}.voices.manager", WORLDVOICE / "voices/manager.py")


def init_policies(manager):
```

**Edit:** `tests/worldvoice_harness.py` (3/4)

Replace:

```text
	"""voiceManager under f4_test_worldvoice; its stubs also have getLanguageDescription and getSynth."""
```

With:

```text
	"""voices.manager under f4_test_worldvoice; its stubs also have getLanguageDescription and getSynth."""
```

**Edit:** `tests/worldvoice_harness.py` (4/4)

Replace:

```text
	return load_source(monkeypatch, f"{package_name}.voiceManager", WORLDVOICE / "voiceManager.py")
```

With:

```text
	return load_source(monkeypatch, f"{package_name}.voices.manager", WORLDVOICE / "voices/manager.py")
```

**Edit:** `tests/test_f4_voice_state.py` (1/1)

Replace:

```text
	manager_module = sys.modules["f4_test_worldvoice.voiceManager"]
```

With:

```text
	manager_module = sys.modules["f4_test_worldvoice.voices.manager"]
```

**Edit:** `tests/test_main_locale_policy.py` (1/1)

Replace:

```text
	return load_source(monkeypatch, "policy_pkg.mainLocalePolicy", WORLDVOICE / "mainLocalePolicy.py")
```

With:

```text
	return load_source(
		monkeypatch,
		"policy_pkg.voices.mainLocalePolicy",
		WORLDVOICE / "voices/mainLocalePolicy.py",
	)
```

**Edit:** `tests/test_pipeline_stages.py` (1/1)

Replace:

```text
	# (voiceManager.py:295-299), so deduplication drops the wrapper and the name comes from the
```

With:

```text
	# (voices/manager.py:295-299), so deduplication drops the wrapper and the name comes from the
```

**Edit:** `tests/test_role_presenter.py` (1/2)

Replace:

```text
	monkeypatch.setitem(sys.modules, "synthDrivers.WorldVoice.roles", sys.modules[f"{package}.roles"])
```

With:

```text
	monkeypatch.setitem(
		sys.modules,
		"synthDrivers.WorldVoice.voices.roles",
		sys.modules[f"{package}.voices.roles"],
	)
```

**Edit:** `tests/test_role_presenter.py` (2/2)

Replace:

```text
	runtime_settings = sys.modules[module.__package__ + ".runtime.settings"]
```

With:

```text
	runtime_settings = sys.modules[module.__package__.removesuffix(".voices") + ".runtime.settings"]
```

**Edit:** `tests/test_role_repository.py` (1/1)

Replace:

```text
	return load_source(monkeypatch, "roles_pkg.roles", WORLDVOICE / "roles.py")
```

With:

```text
	return load_source(monkeypatch, "roles_pkg.voices.roles", WORLDVOICE / "voices/roles.py")
```

**Edit:** `tests/test_runtime_completion_policies.py` (1/3)

Replace:

```text
	models = importlib.import_module(module.__package__ + ".runtime.models")
	adapter = importlib.import_module(module.__package__ + ".bridge.engineAdapter")
	return SimpleNamespace(module=module, models=models, adapter=adapter)
```

With:

```text
	package = module.__package__.removesuffix(".voices")
	models = importlib.import_module(package + ".runtime.models")
	adapter = importlib.import_module(package + ".bridge.engineAdapter")
	return SimpleNamespace(module=module, package=package, models=models, adapter=adapter)
```

**Edit:** `tests/test_runtime_completion_policies.py` (2/3)

Replace:

```text
	return importlib.import_module(env.module.__package__ + ".bridge.completionPolicies")
```

With:

```text
	return importlib.import_module(env.package + ".bridge.completionPolicies")
```

**Edit:** `tests/test_runtime_completion_policies.py` (3/3)

Replace:

```text
	return importlib.import_module(env.module.__package__ + ".runtime.playbackWork")
```

With:

```text
	return importlib.import_module(env.package + ".runtime.playbackWork")
```

**Edit:** `tests/test_runtime_composition.py` (1/9)

Replace:

```text
	policies = importlib.import_module(c.module.__package__ + ".mainLocalePolicy")
	roles_module = importlib.import_module(c.module.__package__ + ".roles")
```

With:

```text
	policies = importlib.import_module(c.package + ".voices.mainLocalePolicy")
	roles_module = importlib.import_module(c.package + ".voices.roles")
```

**Edit:** `tests/test_runtime_composition.py` (2/9)

Replace:

```text
	repository_module = importlib.import_module(c.module.__package__ + ".configRepository")
```

With:

```text
	repository_module = importlib.import_module(c.package + ".voices.settingsRepository")
```

**Edit:** `tests/test_runtime_composition.py` (3/9)

Replace:

```text
	assembly = importlib.import_module(c.module.__package__ + ".assembly")
```

With:

```text
	assembly = importlib.import_module(c.package + ".assembly")
```

**Edit:** `tests/test_runtime_composition.py` (4/9)

Replace:

```text
			scheduler = importlib.import_module(c.module.__package__ + ".runtime.scheduler")
```

With:

```text
			scheduler = importlib.import_module(c.package + ".runtime.scheduler")
```

**Edit:** `tests/test_runtime_composition.py` (5/9)

Replace:

```text
		importlib.import_module(c.module.__package__ + ".bridge.indexLedger").InvalidIndexContext,
```

With:

```text
		importlib.import_module(c.package + ".bridge.indexLedger").InvalidIndexContext,
```

**Edit:** `tests/test_runtime_composition.py` (6/9)

Replace:

```text
def runtime_completion_selector(c, version="synthetic"):
	policies = importlib.import_module(c.module.__package__ + ".bridge.completionPolicies")
	logs = []
```

With:

```text
def runtime_completion_selector(c, version="synthetic"):
	policies = importlib.import_module(c.package + ".bridge.completionPolicies")
	logs = []
```

**Edit:** `tests/test_runtime_composition.py` (7/9)

Replace:

```text
	work = importlib.import_module(c.module.__package__ + ".runtime.playbackWork")
```

With:

```text
	work = importlib.import_module(c.package + ".runtime.playbackWork")
```

**Edit:** `tests/test_runtime_composition.py` (8/9)

Replace:

```text
		port._adapter.configure_completion(c.models.CompletionContract())
	policies = importlib.import_module(c.module.__package__ + ".bridge.completionPolicies")
	assert policies._VERIFIED_CONTRACTS == {}
```

With:

```text
		port._adapter.configure_completion(c.models.CompletionContract())
	policies = importlib.import_module(c.package + ".bridge.completionPolicies")
	assert policies._VERIFIED_CONTRACTS == {}
```

**Edit:** `tests/test_runtime_composition.py` (9/9)

Replace:

```text
	policies = importlib.import_module(c.module.__package__ + ".bridge.completionPolicies")
```

With:

```text
	policies = importlib.import_module(c.package + ".bridge.completionPolicies")
```

**Edit:** `tests/test_voice_catalog.py` (1/1)

Replace:

```text
	return importlib.import_module(PACKAGE + ".voiceCatalog")
```

With:

```text
	return importlib.import_module(PACKAGE + ".voices.catalog")
```

**Edit:** `tests/test_voice_manager_structure.py` (1/1)

Replace:

```text
	tree = ast.parse((ADDON / "synthDrivers/WorldVoice/voiceManager.py").read_text(encoding="utf-8"))
```

With:

```text
	tree = ast.parse((ADDON / "synthDrivers/WorldVoice/voices/manager.py").read_text(encoding="utf-8"))
```

**Edit:** `tests/test_worldvoice_lifecycle.py` (1/2)

Replace:

```text
	models = importlib.import_module(module.__package__ + ".runtime.models")
```

With:

```text
	package = module.__package__.removesuffix(".voices")
	models = importlib.import_module(package + ".runtime.models")
```

**Edit:** `tests/test_worldvoice_lifecycle.py` (2/2)

Replace:

```text
			index_ledger=importlib.import_module(module.__package__ + ".bridge.indexLedger").IndexLedger(),
```

With:

```text
			index_ledger=importlib.import_module(package + ".bridge.indexLedger").IndexLedger(),
```

- [ ] **Step 5: Check that nothing names the old paths**

Run: `git grep -n -E 'configRepository|voiceCatalog|voiceManager\.py|\.voiceManager\b|"roles\.py|[^s]\.roles"|WorldVoice\.roles|[^.s/]mainLocalePolicy|getPrimaryLocale|get_primary_language' -- 'addon/*.py' 'tests/*.py' ':!addon/synthDrivers/WorldVoice/driver/*/driver/*' ':!tests/test_locales.py'`
Expected: no output (at `c94623b` the same pattern finds 44 lines; `tests/test_locales.py` names the two old helpers on purpose).

- [ ] **Step 6: Run the touched tests**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_runtime_composition.py tests/test_worldvoice_lifecycle.py tests/test_runtime_completion_policies.py tests/test_role_presenter.py tests/test_f4_voice_state.py tests/test_main_locale_policy.py tests/test_role_repository.py tests/test_voice_catalog.py tests/test_voice_manager_structure.py tests/test_voice_config_repository.py tests/test_voice_parameter_guards.py tests/test_runtime_drain_integration.py tests/test_locales.py tests/test_worldvoice_speak.py tests/test_voice_settings_transaction.py`
Expected: `380 passed`.

Run: `python3 -m pytest -q -p no:cacheprovider tests` → `3219 passed`, 0 skipped.

- [ ] **Step 7: Commit**

The old paths are already staged by `git mv`; name only the new ones.

```bash
W=addon/synthDrivers/WorldVoice
git add $W/voices $W/__init__.py $W/languageDetection/settings.py addon/globalPlugins/WorldVoice/rolePresenter.py pyproject.toml tests/conftest.py tests/runtime_harness.py tests/runtime_drain_integration_harness.py tests/voice_binding_harness.py tests/worldvoice_harness.py tests/test_f4_voice_state.py tests/test_main_locale_policy.py tests/test_pipeline_stages.py tests/test_role_presenter.py tests/test_role_repository.py tests/test_runtime_completion_policies.py tests/test_runtime_composition.py tests/test_voice_catalog.py tests/test_voice_manager_structure.py tests/test_worldvoice_lifecycle.py
git diff --cached --stat   # 25 files: 1 new, 5 renames, 19 modified
git commit -q -F - <<'EOF'
refactor: gather the voice modules in voices/

The voice manager and its four collaborators (catalog, roles, the
main-locale policies and the per-voice settings repository) sat among
the 17 root modules, so nothing showed they belong together. voices/
holds them; configRepository becomes settingsRepository, the store of
each voice's parameters, since the add-on has several config
repositories. Pure move: class names and behaviour are unchanged;
voices -> bridge -> runtime has no back edge.
EOF
git rev-parse HEAD:addon HEAD:tests
```

Expected after the commit: `HEAD:addon` = `6b026b005a6f0f662ed2a84cdc0502f33b1dfc97`, `HEAD:tests` = `e74d2f8bf9f55d566b3b3714ac5a802a97c6f0cf`

---

### Task 4: Docstrings of the two public packages (F11)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/__init__.py:1`, `addon/synthDrivers/WorldVoice/text/__init__.py:1`

**Interfaces:**
- Consumes: Task 3's tree.
- Produces: docstrings only.

- [ ] **Step 1: Rewrite the docstrings**

**Edit:** `addon/synthDrivers/WorldVoice/driver/__init__.py` (1/1)

Replace:

```text
"""Legacy engine metadata and lifecycle backed by the runtime voice facade."""
```

With:

```text
"""Base class every engine wrapper (built-in or WorldVoice-workspace plugin) subclasses.

Voice gives a wrapper its engine metadata and lifecycle, backed by the runtime voice facade.
Plugins import this module as synthDrivers.WorldVoice.driver (Voice, getVoiceKey), so that
import path is public API: the rest of the add-on may move, this module may not.
"""
```

**Edit:** `addon/synthDrivers/WorldVoice/text/__init__.py` (1/1)

Replace:

```text
"""Engine-side text preprocessing shared by speech synthesis drivers."""
```

With:

```text
"""Engine-side text preprocessing shared by speech synthesis drivers.

Wrapper-facing: engine wrappers import text.arabic and text.chunker by absolute path
(synthDrivers.WorldVoice.text...), so this import path is public API and the package stays here.
"""
```

- [ ] **Step 2: Full suite**

Run: `python3 -m pytest -q -p no:cacheprovider tests` → `3219 passed`, 0 skipped.

- [ ] **Step 3: Commit**

```bash
git add addon/synthDrivers/WorldVoice/driver/__init__.py addon/synthDrivers/WorldVoice/text/__init__.py
git diff --cached --stat   # 2 files
git commit -q -F - <<'EOF'
docs: describe the driver base and the text package as public

driver/__init__.py called itself "Legacy engine metadata", which tells
a plugin author not to use the one base every engine wrapper, built-in
or WorldVoice-workspace plugin, subclasses. text/ is imported by the
wrappers by absolute path; say that its path is public, so it is not
moved like the internal packages.
EOF
git rev-parse HEAD:addon HEAD:tests
```

Expected after the commit: `HEAD:addon` = `9d4a7b01a9c558f4a984051b6f28c6a9be17b109`, `HEAD:tests` = `e74d2f8bf9f55d566b3b3714ac5a802a97c6f0cf`

---

### Task 5: Full verification (DEVELOPMENT_WORKFLOW.md §7)

- [ ] **Step 1:** `python3 -m pytest -q -p no:cacheprovider tests` → `3219 passed`, 0 skipped (baseline 3213; +6 net from Task 1).
- [ ] **Step 2:** `prek run --all-files` → every hook Passed.
- [ ] **Step 3:** `git diff --check master` → no output.
- [ ] **Step 4:** protected paths → both commands print nothing:

```bash
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py addon/synthDrivers/WorldVoice/pipeline/unspaced_common_data.py
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
```

- [ ] **Step 5:** `git diff master --stat -- tests/test_plugin_voice_contract.py` → no output (the plugin contract test is unchanged).
- [ ] **Step 6:** `git log --follow --oneline -- addon/synthDrivers/WorldVoice/bridge/nvdaEvents.py | tail -1` reaches a commit older than this phase (history follows the moves).
- [ ] **Step 7:** final `git rev-parse HEAD:addon HEAD:tests` equals Task 4's ids. Not packaged, not verified on Windows (no behavior change).

---

## Dry run record

2026-10-26, fresh clone of `/workspace/WorldVoice` at `c94623b` in the scratchpad (`ref` symlinked, `prek install`), every step applied from this plan's text (blocks by exact replacement, shell blocks as written):

| Commit | Files | Focused run | Full suite | Tree ids |
| --- | --- | --- | --- | --- |
| Task 1 | 8 | red `3 failed, 10 errors`, then `103 passed` | 3219 passed | match |
| Task 2 | 36 (8 renames) | `486 passed` | 3219 passed | match |
| Task 3 | 25 (1 new, 5 renames) | `380 passed` | 3219 passed | match |
| Task 4 | 2 | — | 3219 passed | match |

Every commit passed the hooks on the first try and left a clean tree. Task 5 in the clone: `prek run --all-files` all Passed; `git diff --check c94623b` and both protected-path commands printed nothing; `tests/test_plugin_voice_contract.py` unchanged; `git log --follow` of `bridge/nvdaEvents.py` reaches `0b433d1 refactor: isolate NVDA speech event bridge`.

The first attempt stopped at Task 2 Step 7: `git add` named the old paths (`compat`, `nvdaEventBridge.py`, …), which `git mv` had already staged and which no longer exist, so git refused the pathspec. The plan now names only the new paths (Tasks 2 and 3), and the dry run was redone from `c94623b`; the result above is that second run.

---

## 修正

Fixes for the Fable review `docs/superpowers/finish/2026-10-26-phase36-bridge-voices-review.md` (I1, M1, M2; M3 needs no change). They start from Task 4's tree — `HEAD:addon` = `9d4a7b01a9c558f4a984051b6f28c6a9be17b109`, `HEAD:tests` = `e74d2f8bf9f55d566b3b3714ac5a802a97c6f0cf` — and touch `tests/` only, so `HEAD:addon` stays the same. Same block rules and Global Constraints as Tasks 1–5.

### Task F1: The runtime import guard resolves relative imports (I1, M2, test first)

**Files:**
- Create: `tests/test_runtime_import_guard.py`
- Modify: `tests/runtime_harness.py` (`forbid_legacy_runtime_imports`)

**Interfaces:**
- Consumes: Task 4's tree.
- Produces: `guarded_import` checks `importlib.util.resolve_name("." * level + name, globals["__package__"])` for a relative import (level > 0 with a package) and the name as given otherwise; `forbidden` and `bridge_allowed` are unchanged.

- [ ] **Step 1: Write the failing tests**

The probe tests build their own `bridge/` under `tmp_path`, so no add-on file is touched: a sibling import `from .voiceFacade import VoiceFacade` in `bridge/indexLedger.py`, and the same line as a re-export in `bridge/__init__.py`. The real ledger and event bridge must still import under the guard, and both new package `__init__.py` files must stay empty.

**File:** `tests/test_runtime_import_guard.py`

```text
"""The pure-runtime import guard sees through relative imports inside bridge/."""

import importlib
import sys

import pytest
from addon_loader import WORLDVOICE, alias_package
from runtime_harness import forbid_legacy_runtime_imports


@pytest.fixture
def probe_package(monkeypatch, tmp_path):
	"""An alias package with a bridge/ of its own; returns (name, bridge directory)."""
	name = "worldvoice_guard_probe"
	bridge = tmp_path / "bridge"
	bridge.mkdir()
	(bridge / "__init__.py").write_text("", encoding="utf-8")
	(bridge / "voiceFacade.py").write_text("class VoiceFacade:\n\tpass\n", encoding="utf-8")
	alias_package(monkeypatch, name, tmp_path)
	yield name, bridge
	for module in tuple(sys.modules):
		if module.startswith(name + "."):
			del sys.modules[module]


def test_guard_rejects_a_relative_import_of_a_legacy_sibling(monkeypatch, probe_package):
	name, bridge = probe_package
	(bridge / "indexLedger.py").write_text("from .voiceFacade import VoiceFacade\n", encoding="utf-8")
	with forbid_legacy_runtime_imports(monkeypatch), pytest.raises(AssertionError, match="voiceFacade"):
		importlib.import_module(name + ".bridge.indexLedger")


def test_guard_rejects_a_legacy_re_export_in_the_bridge_package(monkeypatch, probe_package):
	name, bridge = probe_package
	(bridge / "__init__.py").write_text("from .voiceFacade import VoiceFacade\n", encoding="utf-8")
	(bridge / "nvdaEvents.py").write_text("", encoding="utf-8")
	with forbid_legacy_runtime_imports(monkeypatch), pytest.raises(AssertionError, match="voiceFacade"):
		importlib.import_module(name + ".bridge.nvdaEvents")


def test_guard_allows_the_ledger_and_the_event_bridge(monkeypatch, rt):
	name = "worldvoice_guard_allowed"
	alias_package(monkeypatch, name, WORLDVOICE)
	for suffix, module in (("", rt.package), (".models", rt.models)):
		monkeypatch.setitem(sys.modules, name + ".runtime" + suffix, module)
	for suffix in ("bridge", "bridge.indexLedger", "bridge.nvdaEvents"):
		monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
	with forbid_legacy_runtime_imports(monkeypatch):
		ledger = importlib.import_module(name + ".bridge.indexLedger")
		events = importlib.import_module(name + ".bridge.nvdaEvents")
	assert ledger.IndexLedger.__name__ == "IndexLedger"
	assert events.NvdaEventBridge.__name__ == "NvdaEventBridge"


@pytest.mark.parametrize("package", ["bridge", "voices"])
def test_package_init_stays_empty(package):
	# Importing one module of the package must not load the others (spec phase 36, section 2).
	assert (WORLDVOICE / package / "__init__.py").read_bytes() == b""
```

- [ ] **Step 2: Run them to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_runtime_import_guard.py`
Expected: `2 failed, 3 passed` — `test_guard_rejects_a_relative_import_of_a_legacy_sibling` and `test_guard_rejects_a_legacy_re_export_in_the_bridge_package` fail with `Failed: DID NOT RAISE AssertionError`.

- [ ] **Step 3: Resolve relative names in the guard**

**Edit:** `tests/runtime_harness.py` (1/3)

Replace:

```text
import importlib
import sys
```

With:

```text
import importlib
import importlib.util
import sys
```

**Edit:** `tests/runtime_harness.py` (2/3)

Replace:

```text
	# Python, and a native engine uses them too.
```

With:

```text
	# Python, and a native engine uses them too. The names they had before phase 36 (root
	# indexLedger and nvdaEventBridge, compat/) no longer exist, so they need no rule.
```

**Edit:** `tests/runtime_harness.py` (3/3)

Replace:

```text
	def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
		check(name)
		for item in fromlist or ():
```

With:

```text
	def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
		# A relative import names only the sibling ("voiceFacade"); check where it resolves to.
		if level and globals and globals.get("__package__"):
			check(importlib.util.resolve_name("." * level + name, globals["__package__"]))
		else:
			check(name)
		for item in fromlist or ():
```

- [ ] **Step 4: Run the guard's users to see green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_runtime_import_guard.py tests/test_index_ledger.py tests/test_runtime_adapter_contract.py tests/test_runtime_playback_context.py`
Expected: `122 passed`.

Run: `python3 -m pytest -q -p no:cacheprovider tests` → `3224 passed`, 0 skipped.

- [ ] **Step 5: Commit**

```bash
git add tests/test_runtime_import_guard.py tests/runtime_harness.py
git diff --cached --stat   # 2 files
git commit -q -F - <<'MSG'
test: make the runtime import guard resolve relative imports

forbid_legacy_runtime_imports checked the name __import__ receives, so
"from .voiceFacade import VoiceFacade" inside bridge/indexLedger.py or
bridge/nvdaEvents.py, or a re-export in bridge/__init__.py, passed as
"voiceFacade". Before phase 36 the same dependency had to name compat
and was rejected. Resolve a relative name against the importing
package before checking it, and pin the rule with tests that build a
probe bridge/ package, plus a check that both new package __init__.py
files stay empty.
MSG
git rev-parse HEAD:addon HEAD:tests
```

Expected after the commit: `HEAD:addon` = `9d4a7b01a9c558f4a984051b6f28c6a9be17b109`, `HEAD:tests` = `e10dab88fd1df193b0cce662a4dcd8c63bf8eb2b`

### Task F2: Rename the `bridge` fixture to `bridge_modules` (M1)

**Files:**
- Modify: `tests/conftest.py` (fixture), `tests/test_completion_characterization.py`, `tests/test_f4_engine_session.py`, `tests/test_runtime_legacy_adapter.py`, `tests/test_runtime_voice_facade.py`, `tests/test_voice_parameter_guards.py`

**Interfaces:**
- Consumes: Task F1's tree.
- Produces: fixture `bridge_modules` (`.adapter`, `.facade`); the alias `worldvoice_bridge_test` is unchanged. No test added or removed.

- [ ] **Step 1: Rename the fixture and its users**

The blocks are as prek leaves them: the longer name pushes one call in `test_completion_characterization.py` over the line length, so it is split with a trailing comma.

**Edit:** `tests/conftest.py` (1/1)

Replace:

```text
def bridge(monkeypatch, rt):
	"""The bridge engine adapter and voice facade, bound to this test's runtime."""
```

With:

```text
def bridge_modules(monkeypatch, rt):
	"""The bridge engine adapter and voice facade modules, bound to this test's runtime."""
```

**Edit:** `tests/test_completion_characterization.py` (1/2)

Replace:

```text
def adapter_env(monkeypatch, bridge, rt, nvda_commands):
```

With:

```text
def adapter_env(monkeypatch, bridge_modules, rt, nvda_commands):
```

**Edit:** `tests/test_completion_characterization.py` (2/2)

Replace:

```text
		adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls(), index_ledger=index_ledger)
```

With:

```text
		adapter = bridge_modules.adapter.LegacyEngineAdapter(
			cls,
			lambda key: cls(),
			index_ledger=index_ledger,
		)
```

**Edit:** `tests/test_f4_engine_session.py` (1/2)

Replace:

```text
def engine(session_module, bridge, rt):
```

With:

```text
def engine(session_module, bridge_modules, rt):
```

**Edit:** `tests/test_f4_engine_session.py` (2/2)

Replace:

```text
		return bridge.adapter.LegacyEngineAdapter(
```

With:

```text
		return bridge_modules.adapter.LegacyEngineAdapter(
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (1/25)

Replace:

```text
def test_lifecycle_metadata_and_apply_order(bridge, rt):
	core = Core()
	cls = legacy_class(core)
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
```

With:

```text
def test_lifecycle_metadata_and_apply_order(bridge_modules, rt):
	core = Core()
	cls = legacy_class(core)
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls())
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (2/25)

Replace:

```text
def test_voice_metadata_defaults_and_canonical_key(bridge, rt, extra):
	cls = legacy_class(Core())
	cls.voices = classmethod(lambda cls, core: [dict(engine="Fake", id="a", language="en_US", **extra)])
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
```

With:

```text
def test_voice_metadata_defaults_and_canonical_key(bridge_modules, rt, extra):
	cls = legacy_class(Core())
	cls.voices = classmethod(lambda cls, core: [dict(engine="Fake", id="a", language="en_US", **extra)])
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls())
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (3/25)

Replace:

```text
def test_malformed_voice_metadata_does_not_hide_valid_voices(bridge, rt):
```

With:

```text
def test_malformed_voice_metadata_does_not_hide_valid_voices(bridge_modules, rt):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (4/25)

Replace:

```text
	cls.voices = classmethod(lambda cls, core: [malformed, valid])
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	assert adapter.list_voices() == (rt.models.VoiceSpec("a", "Fake:a", "A", "en", "Fake", "en"),)
```

With:

```text
	cls.voices = classmethod(lambda cls, core: [malformed, valid])
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	assert adapter.list_voices() == (rt.models.VoiceSpec("a", "Fake:a", "A", "en", "Fake", "en"),)
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (5/25)

Replace:

```text
def test_token_support_comes_from_actual_core(bridge, support):
```

With:

```text
def test_token_support_comes_from_actual_core(bridge_modules, support):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (6/25)

Replace:

```text
	cls.supportsCancellationToken = True  # Class claims are not authoritative.
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

With:

```text
	cls.supportsCancellationToken = True  # Class claims are not authoritative.
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (7/25)

Replace:

```text
def test_unsupported_generic_settings_are_not_written(bridge, rt):
```

With:

```text
def test_unsupported_generic_settings_are_not_written(bridge_modules, rt):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (8/25)

Replace:

```text
	cls.supportedSettings = classmethod(lambda cls: ["rate"])
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

With:

```text
	cls.supportedSettings = classmethod(lambda cls: ["rate"])
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (9/25)

Replace:

```text
def test_failed_core_creation_leaves_nothing_to_clean(bridge, rt):
```

With:

```text
def test_failed_core_creation_leaves_nothing_to_clean(bridge_modules, rt):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (10/25)

Replace:

```text
	cls.create_core = classmethod(fail_open)
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	session = rt.session.EngineSession(adapter, rt.settings.VoiceSettingsStore(MemoryRepository()))
```

With:

```text
	cls.create_core = classmethod(fail_open)
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	session = rt.session.EngineSession(adapter, rt.settings.VoiceSettingsStore(MemoryRepository()))
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (11/25)

Replace:

```text
def test_close_releases_adapter_state_even_when_destroy_core_fails(bridge):
```

With:

```text
def test_close_releases_adapter_state_even_when_destroy_core_fails(bridge_modules):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (12/25)

Replace:

```text
	cls.destroy_core = classmethod(fail_destroy)
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

With:

```text
	cls.destroy_core = classmethod(fail_destroy)
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (13/25)

Replace:

```text
def test_each_adapter_owns_its_own_core(bridge):
	first_core, second_core = Core(), Core()
	first_cls, second_cls = legacy_class(first_core), legacy_class(second_core)
	first = bridge.adapter.LegacyEngineAdapter(first_cls, lambda key: first_cls())
	second = bridge.adapter.LegacyEngineAdapter(second_cls, lambda key: second_cls())
```

With:

```text
def test_each_adapter_owns_its_own_core(bridge_modules):
	first_core, second_core = Core(), Core()
	first_cls, second_cls = legacy_class(first_core), legacy_class(second_core)
	first = bridge_modules.adapter.LegacyEngineAdapter(first_cls, lambda key: first_cls())
	second = bridge_modules.adapter.LegacyEngineAdapter(second_cls, lambda key: second_cls())
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (14/25)

Replace:

```text
def test_onecore_cached_a_b_a_restores_language(bridge, rt):
```

With:

```text
def test_onecore_cached_a_b_a_restores_language(bridge_modules, rt):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (15/25)

Replace:

```text
	store.ensure(make_spec("OneCore:b", "zh_TW")).update(rate=31)
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	session = rt.session.EngineSession(adapter, store)
```

With:

```text
	store.ensure(make_spec("OneCore:b", "zh_TW")).update(rate=31)
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	session = rt.session.EngineSession(adapter, store)
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (16/25)

Replace:

```text
def test_real_variant_and_waitfactor_hooks(bridge, rt, monkeypatch, engine):
```

With:

```text
def test_real_variant_and_waitfactor_hooks(bridge_modules, rt, monkeypatch, engine):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (17/25)

Replace:

```text
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: voice)
```

With:

```text
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: voice)
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (18/25)

Replace:

```text
def marker_env(monkeypatch, bridge, rt, nvda_commands):
```

With:

```text
def marker_env(monkeypatch, bridge_modules, rt, nvda_commands):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (19/25)

Replace:

```text
	adapter = bridge.adapter.LegacyEngineAdapter(
```

With:

```text
	adapter = bridge_modules.adapter.LegacyEngineAdapter(
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (20/25)

Replace:

```text
def test_legacy_without_context_preserves_commands(bridge, monkeypatch):
```

With:

```text
def test_legacy_without_context_preserves_commands(bridge_modules, monkeypatch):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (21/25)

Replace:

```text
	cls = legacy_class(core)
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

With:

```text
	cls = legacy_class(core)
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	adapter.open()
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (22/25)

Replace:

```text
def drain_env(monkeypatch, bridge, rt, nvda_commands, request):
```

With:

```text
def drain_env(monkeypatch, bridge_modules, rt, nvda_commands, request):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (23/25)

Replace:

```text
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls(), index_ledger=ledger)
```

With:

```text
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls(), index_ledger=ledger)
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (24/25)

Replace:

```text
def test_segment_event_configuration_rejects_wrong_lifecycle_phase(bridge, rt, phase):
```

With:

```text
def test_segment_event_configuration_rejects_wrong_lifecycle_phase(bridge_modules, rt, phase):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (25/25)

Replace:

```text
	adapter = bridge.adapter.LegacyEngineAdapter(cls, lambda key: cls())
```

With:

```text
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls())
```

**Edit:** `tests/test_runtime_voice_facade.py` (1/3)

Replace:

```text
def setup(bridge, rt):
```

With:

```text
def setup(bridge_modules, rt):
```

**Edit:** `tests/test_runtime_voice_facade.py` (2/3)

Replace:

```text
	binding = bridge.facade.LegacyVoiceBinding(store, session, None)

	class Voice(bridge.facade.VoiceFacade):
```

With:

```text
	binding = bridge_modules.facade.LegacyVoiceBinding(store, session, None)

	class Voice(bridge_modules.facade.VoiceFacade):
```

**Edit:** `tests/test_runtime_voice_facade.py` (3/3)

Replace:

```text
def test_facade_reads_its_engine_core_from_the_binding(setup, bridge):
	core = object()
	binding = bridge.facade.LegacyVoiceBinding(setup.store, setup.session, core)
```

With:

```text
def test_facade_reads_its_engine_core_from_the_binding(setup, bridge_modules):
	core = object()
	binding = bridge_modules.facade.LegacyVoiceBinding(setup.store, setup.session, core)
```

**Edit:** `tests/test_voice_parameter_guards.py` (1/1)

Replace:

```text
def test_the_adapter_applies_every_copyable_parameter_rate_boost_first(rt, bridge):
	order = bridge.adapter.APPLY_ORDER
```

With:

```text
def test_the_adapter_applies_every_copyable_parameter_rate_boost_first(rt, bridge_modules):
	order = bridge_modules.adapter.APPLY_ORDER
```

- [ ] **Step 2: Check that no test still asks for the old fixture**

Run: `git grep -n -E "\bbridge[,)]|\bbridge\.(adapter|facade)\b" -- tests/test_completion_characterization.py tests/test_f4_engine_session.py tests/test_runtime_legacy_adapter.py tests/test_runtime_voice_facade.py tests/test_voice_parameter_guards.py`
Expected: no output.

- [ ] **Step 3: Full suite**

Run: `python3 -m pytest -q -p no:cacheprovider tests` → `3224 passed`, 0 skipped.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_completion_characterization.py tests/test_f4_engine_session.py tests/test_runtime_legacy_adapter.py tests/test_runtime_voice_facade.py tests/test_voice_parameter_guards.py
git diff --cached --stat   # 6 files
git commit -q -F - <<'MSG'
test: rename the bridge fixture to bridge_modules

The fixture that hands tests the bridge engine adapter and voice facade
modules was called bridge, the word the tests already use for an
NvdaEventBridge instance (composition.bridge, bridge_bindings(bridge)).
Name it after what it returns so the two cannot be confused.
MSG
git rev-parse HEAD:addon HEAD:tests
```

Expected after the commit: `HEAD:addon` = `9d4a7b01a9c558f4a984051b6f28c6a9be17b109`, `HEAD:tests` = `85401e928c5697030cd8cc258beba179e7c9b658`

### Task F3: Verification

- [ ] `python3 -m pytest -q -p no:cacheprovider tests` → `3224 passed`, 0 skipped (3219 + 5 in `tests/test_runtime_import_guard.py`).
- [ ] `prek run --all-files` all Passed; `git diff --check master` prints nothing; both protected-path commands of Task 5 print nothing; `HEAD:addon` is still `9d4a7b01a9c558f4a984051b6f28c6a9be17b109`.

### 修正 dry run record

2026-10-26, fresh clone of the task branch at `f715f51` (the review commit; Task 4's tree) in the scratchpad, `ref` symlinked, `prek install`, every step applied from this section's text:

| Commit | Files | Focused run | Full suite | Tree ids |
| --- | --- | --- | --- | --- |
| Task F1 | 2 | red `2 failed, 3 passed` (`DID NOT RAISE`), then `122 passed` | 3224 passed | match |
| Task F2 | 6 | grep: no output | 3224 passed | match |

Both commits passed the hooks on the first try and left a clean tree. `prek run --all-files` all Passed; both protected-path commands printed nothing. `git diff --check c94623b` reported only the review document's code block (`docs/superpowers/finish/2026-10-26-phase36-bridge-voices-review.md:51-57`, "space before tab in indent"), which the review commit added; the 修正記錄 commit re-indents those lines with spaces. The first attempt stopped at Task F1 Step 2 only because the Expected text quoted pytest's message as `<class 'AssertionError'>`; the text was corrected and the dry run redone from `f715f51`.
