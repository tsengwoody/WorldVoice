# Phase 39: naming cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice complex flow (DEVELOPMENT_WORKFLOW.md §4): one implementer runs every task in order,
> applying the `File:`/`Edit:` blocks byte for byte; every commit's tree ids must match this plan.
> The orchestrator dispatches the final Fable 5.1 review (§3.3, §4.5). 8 tasks: no batch reviews (§3.2).

**Goal:** Rename `engine/` to `engineRegistry/`, `assembly.py` to `bringup.py`, `pipeline/speech_dictionary.py` to `pipeline/speechDictionary.py` and `runtime/settings.py` to `runtime/voiceSettings.py`; gather the script lookup and both generated Unicode data files in a new `unicodeScripts/` package (the data files byte-identical); name the test helpers after the modules they load; and add `recorder` to the pipeline structure guard — with no behavior change.

**Architecture:** Pure moves with `git mv`; only import lines, path strings and dotted names in tests and tools, the ruff/coverage/pre-commit exclusions, two docstrings, test-local names and four guard tests change. Afterwards `languageDetection → unicodeScripts` and `pipeline → unicodeScripts`; `pipeline/` imports nothing from `languageDetection`; `unicodeScripts/__init__.py` is empty.

**Tech Stack:** Python 3 (NVDA add-on), pytest, ruff `==0.16.3` and add-trailing-comma through prek.

**Spec:** `docs/superpowers/specs/2026-10-26-phase39-naming-cleanup-design.md`

**Base:** `master` `e54d804` — `HEAD:addon` = `eb87b28e2eee4ec6c4a3c03249b182e3a6d3f05d`, `HEAD:tests` = `9542603a6c29a74efab7d0211af3ae08d49dfcee`; `python3 -m pytest -q -p no:cacheprovider tests` → 3236 passed, 0 skipped; `prek run --all-files` all Passed. The spec and this plan are committed under `docs/` before Task 1 (`git add -f`, `docs/` is git-ignored but tracked); `docs/` does not enter the tree ids. Task 5's `tools/`, `pyproject.toml` and `.pre-commit-config.yaml` changes are outside the two compared trees; their blob ids after Task 5 are listed there as well.

**Dry run:** see the end of this plan.

## Global Constraints

- Every command runs from the repository root of the worktree. `$SCRATCH` is the session scratchpad directory.
- Apply every `Edit:` block as one exact replacement (the "Replace" text occurs exactly once in the file at that point), in document order. Block text is whole lines. The blocks are already in the form prek leaves them (ruff's isort order and format, add-trailing-comma), so each commit passes the hooks on the first try. If a hook still changes a file, stop: the tree ids will not match (§4.4).
- Public import paths do not change: `synthDrivers.WorldVoice.driver` (`Voice`, `getVoiceKey`), `runtime.{engineControl, models, playbackWork, segmentHost, session}`, `text.arabic`, `text.chunker`, `driver.sonic._sonic`. `tests/test_plugin_voice_contract.py` is not edited and stays green.
- Never modify `driver/<Engine>/driver/` or `driver/sonic/`. The generated `script_data.py` and `unspaced_common_data.py` are moved with `git mv` only: no edit, no regeneration (authorized move, spec §2 goal 5). Engine drivers stay independently installable; never stage Neural or `ref`.
- No rename of an add-on class, function, constant or attribute; no UI string change (spec §3).
- `unicodeScripts/__init__.py` is empty (0 bytes).
- ruff pinned `0.16.3`; tabs. Commits: English `<type>: <summary>` with a body saying why, no `Co-Authored-By`, `git add` with explicit paths only (after `git mv`, name only the new paths), check `git diff --cached --stat` first, never `--no-verify`, never `git stash`, no push, never touch the main checkout.
- Tests: one pytest process at a time (at most 3 workers), with a memory guard that kills pytest when MemAvailable < 3 GB, for example `$SCRATCH/runtests.sh . tests` (polls `/proc/meminfo` every 2 s while pytest runs and kills it below 3 000 000 kB).

## Review Focus

1. **Engine discovery after the package rename.** `engineRegistry/__init__.py` derives the add-on root from `__file__` and the driver package from `__package__`; at the wrong depth NVDA would find no bundled engine. Task 1: `tests/test_engine_registry.py::test_import_discovers_the_bundled_drivers_then_the_workspace_engines` (asserts `spec.module_name == f"{PACKAGE}.driver.{spec.name}"` for every internal spec) and the real dialog's engine list in `tests/test_settings_panels.py`.
2. **The global plugin imports from the new paths.** `speechSettingsDialog.py` (`engineRegistry`) and `rolePresenter.py` (`runtime.voiceSettings`) are imported by NVDA by absolute name. Task 1: `tests/test_settings_panels.py`, `tests/test_pipeline_panels.py`, `tests/test_role_panel.py`, `tests/test_unicode_panel.py` (the real dialog); Task 4: `tests/test_role_presenter.py` (the real presenter against the manager's own `voiceSettings` module).
3. **The generated data moves without a byte of change and stays the generators' output.** Task 5 Step 5: `cmp` against the base blobs and `R100` in `git diff --cached -M100% --name-status`; `tests/test_generated_unicode_data.py` re-renders both files at their new paths; `test_without_script_data_the_tool_reads_the_committed_one` keeps the unspaced generator's default `--script-data` on the moved file.
4. **Script lookups in detection and in the space pause.** Both now go through `unicodeScripts.lookup`; the pipeline must not load the detector any more. Task 5: `tests/test_language_detector.py`, `tests/test_unicode_scripts.py`, `tests/test_pipeline_unspaced_space.py` (incl. `test_pipeline_harness_loads_the_script_lookup_fresh`), `test_the_pipeline_does_not_import_language_detection`.
5. **Bring-up and the speech dictionary bypass.** The driver's teardown order and the `processText` patch come from the renamed `bringup`/`speechDictionary` modules. Task 2: `tests/test_bringup.py`, `tests/test_worldvoice_lifecycle.py`, `tests/test_runtime_composition.py` (the real `__init__.py`); Task 3: `tests/test_speech_dictionary.py`, `tests/test_pipeline_stages.py::test_register_puts_stages_first_in_order_and_unregister_removes_them`.

---

### Task 1: Rename `engine/` to `engineRegistry/` (F4)

**Files:**
- Move: `addon/synthDrivers/WorldVoice/engine/` → `addon/synthDrivers/WorldVoice/engineRegistry/` (`discovery.py` unchanged; `__init__.py` gains a module docstring)
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`, `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (one import line each)
- Test: `tests/test_engine_discovery.py`, `tests/test_engine_registry.py`, `tests/test_runtime_composition.py`, `tests/ui_harness.py`

**Interfaces:**
- Consumes: the base tree.
- Produces: package `engineRegistry` with `ENGINE_SPECS`, `ENGINE_SPEC_INDEX`, `ready_engine_classes`, `get_engine_enabled`, `get_engine_label`, `get_engine_default_enabled` and module `engineRegistry.discovery` (names unchanged); `engine` no longer exists.

- [ ] **Step 1: Point the tests at the new package**

**Edit:** `tests/test_engine_discovery.py` (1/1)

Replace:

```text
	stub_modules.package(PACKAGE, WORLDVOICE)
	stub_modules.package(PACKAGE + ".engine", WORLDVOICE / "engine")
	monkeypatch.setattr(sys, "path", list(sys.path))
	return importlib.import_module(PACKAGE + ".engine.discovery")

```

With:

```text
	stub_modules.package(PACKAGE, WORLDVOICE)
	stub_modules.package(PACKAGE + ".engineRegistry", WORLDVOICE / "engineRegistry")
	monkeypatch.setattr(sys, "path", list(sys.path))
	return importlib.import_module(PACKAGE + ".engineRegistry.discovery")

```

**Edit:** `tests/test_engine_registry.py` (1/2)

Replace:

```text
"""The engine package: the specs found at import, and what the driver and panels ask of them.

```

With:

```text
"""The engineRegistry package: the specs found at import, and what the driver and panels ask of them.

```

**Edit:** `tests/test_engine_registry.py` (2/2)

Replace:

```text
	alias_package(monkeypatch, PACKAGE, WORLDVOICE)
	module = importlib.import_module(PACKAGE + ".engine")
	yield SimpleNamespace(module=module, logged=logged)
```

With:

```text
	alias_package(monkeypatch, PACKAGE, WORLDVOICE)
	module = importlib.import_module(PACKAGE + ".engineRegistry")
	yield SimpleNamespace(module=module, logged=logged)
```

**Edit:** `tests/test_runtime_composition.py` (1/1)

Replace:

```text
	stub(package + ".pipeline.scope", pipeline_scope=SimpleNamespace())
	stub(package + ".engine", ready_engine_classes=lambda engine_config: {})
	stub(package + ".ui.voicePanel", WorldVoiceVoiceSettingsPanel=object)
```

With:

```text
	stub(package + ".pipeline.scope", pipeline_scope=SimpleNamespace())
	stub(package + ".engineRegistry", ready_engine_classes=lambda engine_config: {})
	stub(package + ".ui.voicePanel", WorldVoiceVoiceSettingsPanel=object)
```

**Edit:** `tests/ui_harness.py` (1/3)

Replace:

```text
	alias_package(monkeypatch, "worldvoice_ui_engines", WORLDVOICE)
	alias_package(monkeypatch, "worldvoice_ui_engines.engine", WORLDVOICE / "engine")
	load_source(monkeypatch, "worldvoice_ui_engines.assembly", WORLDVOICE / "assembly.py")
```

With:

```text
	alias_package(monkeypatch, "worldvoice_ui_engines", WORLDVOICE)
	alias_package(monkeypatch, "worldvoice_ui_engines.engineRegistry", WORLDVOICE / "engineRegistry")
	load_source(monkeypatch, "worldvoice_ui_engines.assembly", WORLDVOICE / "assembly.py")
```

**Edit:** `tests/ui_harness.py` (2/3)

Replace:

```text
		monkeypatch,
		"worldvoice_ui_engines.engine.discovery",
		WORLDVOICE / "engine/discovery.py",
	)
```

With:

```text
		monkeypatch,
		"worldvoice_ui_engines.engineRegistry.discovery",
		WORLDVOICE / "engineRegistry/discovery.py",
	)
```

**Edit:** `tests/ui_harness.py` (3/3)

Replace:

```text
	stubs.module(
		"synthDrivers.WorldVoice.engine",
		ENGINE_SPECS=env.engine_specs,
```

With:

```text
	stubs.module(
		"synthDrivers.WorldVoice.engineRegistry",
		ENGINE_SPECS=env.engine_specs,
```

- [ ] **Step 2: Run them to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_engine_discovery.py tests/test_engine_registry.py tests/test_runtime_composition.py tests/test_settings_panels.py tests/test_pipeline_panels.py tests/test_role_panel.py tests/test_unicode_panel.py`
Expected: `74 failed, 77 passed, 23 errors` — `FileNotFoundError` for `engineRegistry/discovery.py` (the dialog harness loads it by path), `ModuleNotFoundError: No module named 'discovery_test_worldvoice.engineRegistry.discovery'`, and `AttributeError`s on the empty `engine_registry_test_worldvoice.engineRegistry` namespace package.

- [ ] **Step 3: Move the package and its importers**

```bash
W=addon/synthDrivers/WorldVoice
git mv $W/engine $W/engineRegistry
```

**Edit:** `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (1/1)

Replace:

```text
from synthDrivers.WorldVoice import languageDetection
from synthDrivers.WorldVoice.engine import ENGINE_SPECS, get_engine_enabled
from synthDrivers.WorldVoice.languageDetection.settings import detection_settings
```

With:

```text
from synthDrivers.WorldVoice import languageDetection
from synthDrivers.WorldVoice.engineRegistry import ENGINE_SPECS, get_engine_enabled
from synthDrivers.WorldVoice.languageDetection.settings import detection_settings
```

**Edit:** `addon/synthDrivers/WorldVoice/__init__.py` (1/1)

Replace:

```text
from .bridge.nvdaEvents import NvdaEventBridge
from .engine import ready_engine_classes
from .languageDetection.settings import DETECTION_CONFSPEC, detection_settings
```

With:

```text
from .bridge.nvdaEvents import NvdaEventBridge
from .engineRegistry import ready_engine_classes
from .languageDetection.settings import DETECTION_CONFSPEC, detection_settings
```

**Edit:** `addon/synthDrivers/WorldVoice/engineRegistry/__init__.py` (1/1)

Replace:

```text
import os
```

With:

```text
"""The known engines: found at import, with whether each is enabled, its label and its default.

The engine wrappers themselves live in driver/<Engine>/ (bundled) and in the WorldVoice-workspace
(plugins); discovery.py finds and loads them. Not part of driver/: a plugin's import of
synthDrivers.WorldVoice.driver must not scan the disk or initialize translations.
"""

import os
```

- [ ] **Step 4: Run the tests to see green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_engine_discovery.py tests/test_engine_registry.py tests/test_runtime_composition.py tests/test_settings_panels.py tests/test_pipeline_panels.py tests/test_role_panel.py tests/test_unicode_panel.py`
Expected: `174 passed`.

Run: `$SCRATCH/runtests.sh . tests` → `3236 passed`, 0 skipped.

- [ ] **Step 5: Commit**

```bash
W=addon/synthDrivers/WorldVoice
git add $W/engineRegistry/__init__.py $W/engineRegistry/discovery.py $W/__init__.py addon/globalPlugins/WorldVoice/speechSettingsDialog.py tests/test_engine_discovery.py tests/test_engine_registry.py tests/test_runtime_composition.py tests/ui_harness.py
git diff --cached --stat
git commit -q -F - <<'EOF'
refactor: rename the engine package to engineRegistry

engine/ and driver/ read as the same thing: the wrappers live in
driver/<Engine>/, while engine/ holds the list of known engines with
their enabled flags, labels and defaults. The new name says that, and
a docstring points from the registry to the wrappers it finds. The
package stays one level below the synth, so the driver package name
and root it derives from __package__ and __file__ are unchanged.
EOF
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `git status --short` prints nothing; `HEAD:addon` = `79a271022284b383742bbee3aee7af252754952a`, `HEAD:tests` = `d8af32b8205450b18c62b50e02299b31af6bb4ad`.

---

### Task 2: Rename `assembly.py` to `bringup.py` (F11)

**Files:**
- Move: `addon/synthDrivers/WorldVoice/assembly.py` → `addon/synthDrivers/WorldVoice/bringup.py` (content unchanged); `tests/test_assembly.py` → `tests/test_bringup.py`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py` (import moves after `.bridge.*`), `addon/synthDrivers/WorldVoice/engineRegistry/discovery.py`, `addon/synthDrivers/WorldVoice/pipeline/speech_dictionary.py` (one import line each)
- Test: `tests/test_bringup.py` (fixture `bringup`), `tests/test_worldvoice_lifecycle.py` (`_bringup`), `tests/test_runtime_composition.py` (local `bringup`), `tests/ui_harness.py`

**Interfaces:**
- Consumes: Task 1's tree (`engineRegistry/discovery.py`).
- Produces: module `bringup` with `Teardown`, `timed`, `patch_attribute` (names unchanged); `assembly` no longer exists.

- [ ] **Step 1: Point the tests at the new module**

```bash
git mv tests/test_assembly.py tests/test_bringup.py
```

**Edit:** `tests/test_bringup.py` (1/12)

Replace:

```text
@pytest.fixture
def assembly():
	return load_source(None, "assembly_under_test", WORLDVOICE / "assembly.py", register=False)

```

With:

```text
@pytest.fixture
def bringup():
	return load_source(None, "bringup_under_test", WORLDVOICE / "bringup.py", register=False)

```

**Edit:** `tests/test_bringup.py` (2/12)

Replace:

```text

def test_teardown_runs_in_declared_order_not_registration_order(assembly):
	ran = []
	teardown = assembly.Teardown(("a", "b", "c"), Log())
	teardown.add("c", lambda: ran.append("c"))
```

With:

```text

def test_teardown_runs_in_declared_order_not_registration_order(bringup):
	ran = []
	teardown = bringup.Teardown(("a", "b", "c"), Log())
	teardown.add("c", lambda: ran.append("c"))
```

**Edit:** `tests/test_bringup.py` (3/12)

Replace:

```text

def test_teardown_rejects_unknown_and_duplicate_names(assembly):
	teardown = assembly.Teardown(("a",), Log())
	with pytest.raises(ValueError):
```

With:

```text

def test_teardown_rejects_unknown_and_duplicate_names(bringup):
	teardown = bringup.Teardown(("a",), Log())
	with pytest.raises(ValueError):
```

**Edit:** `tests/test_bringup.py` (4/12)

Replace:

```text

def test_teardown_logs_a_failure_and_continues(assembly):
	ran, log = [], Log()
	teardown = assembly.Teardown(("a", "b"), log)
	teardown.add("a", lambda: 1 / 0)
```

With:

```text

def test_teardown_logs_a_failure_and_continues(bringup):
	ran, log = [], Log()
	teardown = bringup.Teardown(("a", "b"), log)
	teardown.add("a", lambda: 1 / 0)
```

**Edit:** `tests/test_bringup.py` (5/12)

Replace:

```text

def test_teardown_lets_interrupts_through(assembly):
	ran = []
```

With:

```text

def test_teardown_lets_interrupts_through(bringup):
	ran = []
```

**Edit:** `tests/test_bringup.py` (6/12)

Replace:

```text

	teardown = assembly.Teardown(("a", "b"), Log())
	teardown.add("a", interrupt)
```

With:

```text

	teardown = bringup.Teardown(("a", "b"), Log())
	teardown.add("a", interrupt)
```

**Edit:** `tests/test_bringup.py` (7/12)

Replace:

```text

def test_teardown_runs_once(assembly):
	ran = []
	teardown = assembly.Teardown(("a",), Log())
	teardown.add("a", lambda: ran.append("a"))
```

With:

```text

def test_teardown_runs_once(bringup):
	ran = []
	teardown = bringup.Teardown(("a",), Log())
	teardown.add("a", lambda: ran.append("a"))
```

**Edit:** `tests/test_bringup.py` (8/12)

Replace:

```text

def test_timed_logs_label_and_seconds(assembly, monkeypatch):
	clock = iter([1.0, 1.25])
	monkeypatch.setattr(assembly.time, "perf_counter", lambda: next(clock))
	log = Log()
	with assembly.timed(log, "TaskManager"):
		pass
```

With:

```text

def test_timed_logs_label_and_seconds(bringup, monkeypatch):
	clock = iter([1.0, 1.25])
	monkeypatch.setattr(bringup.time, "perf_counter", lambda: next(clock))
	log = Log()
	with bringup.timed(log, "TaskManager"):
		pass
```

**Edit:** `tests/test_bringup.py` (9/12)

Replace:

```text

def test_timed_logs_and_reraises_on_failure(assembly):
	log = Log()
	with pytest.raises(ZeroDivisionError), assembly.timed(log, "step"):
		raise ZeroDivisionError
```

With:

```text

def test_timed_logs_and_reraises_on_failure(bringup):
	log = Log()
	with pytest.raises(ZeroDivisionError), bringup.timed(log, "step"):
		raise ZeroDivisionError
```

**Edit:** `tests/test_bringup.py` (10/12)

Replace:

```text

def test_timed_without_logger(assembly):
	with assembly.timed(None, "step"):
		pass
```

With:

```text

def test_timed_without_logger(bringup):
	with bringup.timed(None, "step"):
		pass
```

**Edit:** `tests/test_bringup.py` (11/12)

Replace:

```text

def test_patch_attribute_restores_once(assembly):
	owner = SimpleNamespace(value="original")
	restore = assembly.patch_attribute(owner, "value", "patched")
	assert owner.value == "patched"
```

With:

```text

def test_patch_attribute_restores_once(bringup):
	owner = SimpleNamespace(value="original")
	restore = bringup.patch_attribute(owner, "value", "patched")
	assert owner.value == "patched"
```

**Edit:** `tests/test_bringup.py` (12/12)

Replace:

```text

def test_teardown_refuses_registration_after_it_ran(assembly):
	teardown = assembly.Teardown(("a",), Log())
	teardown.run()
```

With:

```text

def test_teardown_refuses_registration_after_it_ran(bringup):
	teardown = bringup.Teardown(("a",), Log())
	teardown.run()
```

**Edit:** `tests/test_runtime_composition.py` (1/3)

Replace:

```text
def make_synth(c, manager):
	assembly = importlib.import_module(c.package + ".assembly")
	commands = {
```

With:

```text
def make_synth(c, manager):
	bringup = importlib.import_module(c.package + ".bringup")
	commands = {
```

**Edit:** `tests/test_runtime_composition.py` (2/3)

Replace:

```text
			**commands,
			**{name: getattr(assembly, name) for name in ("Teardown", "timed", "patch_attribute")},
		},
```

With:

```text
			**commands,
			**{name: getattr(bringup, name) for name in ("Teardown", "timed", "patch_attribute")},
		},
```

**Edit:** `tests/test_runtime_composition.py` (3/3)

Replace:

```text
	# Register the runtime cleanups as _initialize does once each object exists.
	synth._teardown = assembly.Teardown(root._TEARDOWN_ORDER, log)
	synth._teardown.add("index ledger close", c.ledger.close)
```

With:

```text
	# Register the runtime cleanups as _initialize does once each object exists.
	synth._teardown = bringup.Teardown(root._TEARDOWN_ORDER, log)
	synth._teardown.add("index ledger close", c.ledger.close)
```

**Edit:** `tests/test_worldvoice_lifecycle.py` (1/2)

Replace:

```text

def _assembly():
	module = load_source(None, "lifecycle_assembly", WORLDVOICE / "assembly.py", register=False)
	return {name: getattr(module, name) for name in ("Teardown", "timed", "patch_attribute")}
```

With:

```text

def _bringup():
	module = load_source(None, "lifecycle_bringup", WORLDVOICE / "bringup.py", register=False)
	return {name: getattr(module, name) for name in ("Teardown", "timed", "patch_attribute")}
```

**Edit:** `tests/test_worldvoice_lifecycle.py` (2/2)

Replace:

```text
		"listable": lambda function: function,
		**_assembly(),
		**commands,
```

With:

```text
		"listable": lambda function: function,
		**_bringup(),
		**commands,
```

**Edit:** `tests/ui_harness.py` (1/1)

Replace:

```text
	alias_package(monkeypatch, "worldvoice_ui_engines.engineRegistry", WORLDVOICE / "engineRegistry")
	load_source(monkeypatch, "worldvoice_ui_engines.assembly", WORLDVOICE / "assembly.py")
	discovery = load_source(
```

With:

```text
	alias_package(monkeypatch, "worldvoice_ui_engines.engineRegistry", WORLDVOICE / "engineRegistry")
	load_source(monkeypatch, "worldvoice_ui_engines.bringup", WORLDVOICE / "bringup.py")
	discovery = load_source(
```

- [ ] **Step 2: Run them to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_bringup.py tests/test_worldvoice_lifecycle.py tests/test_runtime_composition.py tests/test_settings_panels.py tests/test_engine_discovery.py tests/test_speech_dictionary.py`
Expected: `83 failed, 74 passed, 11 errors` — `FileNotFoundError` for `bringup.py` (the fixture and the dialog harness load it by path) and `ModuleNotFoundError: No module named 'lifecycle_test_worldvoice.bringup'` (the composition tests import it from the alias package).

- [ ] **Step 3: Move the module and its importers**

```bash
W=addon/synthDrivers/WorldVoice
git mv $W/assembly.py $W/bringup.py
```

**Edit:** `addon/synthDrivers/WorldVoice/__init__.py` (1/2)

Replace:

```text
from . import languageDetection
from .assembly import Teardown, patch_attribute, timed
from .bridge.commands import normalize_legacy_commands
```

With:

```text
from . import languageDetection
from .bridge.commands import normalize_legacy_commands
```

**Edit:** `addon/synthDrivers/WorldVoice/__init__.py` (2/2)

Replace:

```text
from .bridge.nvdaEvents import NvdaEventBridge
from .engineRegistry import ready_engine_classes
```

With:

```text
from .bridge.nvdaEvents import NvdaEventBridge
from .bringup import Teardown, patch_attribute, timed
from .engineRegistry import ready_engine_classes
```

**Edit:** `addon/synthDrivers/WorldVoice/engineRegistry/discovery.py` (1/1)

Replace:

```text

from ..assembly import timed

```

With:

```text

from ..bringup import timed

```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/speech_dictionary.py` (1/1)

Replace:

```text

from ..assembly import patch_attribute

```

With:

```text

from ..bringup import patch_attribute

```

- [ ] **Step 4: Run the tests to see green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_bringup.py tests/test_worldvoice_lifecycle.py tests/test_runtime_composition.py tests/test_settings_panels.py tests/test_engine_discovery.py tests/test_speech_dictionary.py`
Expected: `167 passed`.

Run: `$SCRATCH/runtests.sh . tests` → `3236 passed`, 0 skipped.

- [ ] **Step 5: Commit**

```bash
W=addon/synthDrivers/WorldVoice
git add $W/bringup.py $W/__init__.py $W/engineRegistry/discovery.py $W/pipeline/speech_dictionary.py tests/test_bringup.py tests/test_worldvoice_lifecycle.py tests/test_runtime_composition.py tests/ui_harness.py
git diff --cached --stat
git commit -q -F - <<'EOF'
refactor: rename assembly.py to bringup.py

The module holds the driver's bring-up helpers (fixed-order teardown,
step timing, attribute patches), as its docstring says; "assembly"
read as a component or a .NET assembly. Its test file and the test
helpers that load it follow the new name.
EOF
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `git status --short` prints nothing; `HEAD:addon` = `bcaa84b7616204550797c10480264ce6164fd33e`, `HEAD:tests` = `f9744cdd93ef5e39a27c786ad451babf6f2aefe1`.

---

### Task 3: Rename `pipeline/speech_dictionary.py` to `pipeline/speechDictionary.py` (A3)

**Files:**
- Move: `addon/synthDrivers/WorldVoice/pipeline/speech_dictionary.py` → `addon/synthDrivers/WorldVoice/pipeline/speechDictionary.py` (content unchanged)
- Modify: `addon/synthDrivers/WorldVoice/pipeline/registry.py` (import and the two calls)
- Test: `tests/pipeline_harness.py`, `tests/test_pipeline_stages.py`, `tests/test_speech_dictionary.py`

**Interfaces:**
- Consumes: Task 2's tree (`speech_dictionary.py` imports `..bringup`).
- Produces: module `pipeline.speechDictionary` with `install`, `uninstall`; the `PipelineModules` view exposes it as `module.speechDictionary`.

- [ ] **Step 1: Point the tests at the new module**

**Edit:** `tests/pipeline_harness.py` (1/2)

Replace:

```text
	"symbols",
	"speech_dictionary",
	"unspaced_common_data",
```

With:

```text
	"symbols",
	"speechDictionary",
	"unspaced_common_data",
```

**Edit:** `tests/pipeline_harness.py` (2/2)

Replace:

```text
		"synthDrivers.WorldVoice.pipeline.recorder",
		"synthDrivers.WorldVoice.pipeline.speech_dictionary",
		"synthDrivers.WorldVoice.pipeline.settings",
```

With:

```text
		"synthDrivers.WorldVoice.pipeline.recorder",
		"synthDrivers.WorldVoice.pipeline.speechDictionary",
		"synthDrivers.WorldVoice.pipeline.settings",
```

**Edit:** `tests/test_pipeline_stages.py` (1/1)

Replace:

```text
	installs = []
	monkeypatch.setattr(module.speech_dictionary, "install", lambda: installs.append("install"))
	monkeypatch.setattr(module.speech_dictionary, "uninstall", lambda: installs.append("uninstall"))

```

With:

```text
	installs = []
	monkeypatch.setattr(module.speechDictionary, "install", lambda: installs.append("install"))
	monkeypatch.setattr(module.speechDictionary, "uninstall", lambda: installs.append("uninstall"))

```

**Edit:** `tests/test_speech_dictionary.py` (1/1)

Replace:

```text
	speech = stub_modules.module("speech", speech=SimpleNamespace(processText=process_text))
	module = importlib.import_module(PACKAGE + ".pipeline.speech_dictionary")
	return SimpleNamespace(module=module, speech=speech, globalVars=global_vars)
```

With:

```text
	speech = stub_modules.module("speech", speech=SimpleNamespace(processText=process_text))
	module = importlib.import_module(PACKAGE + ".pipeline.speechDictionary")
	return SimpleNamespace(module=module, speech=speech, globalVars=global_vars)
```

- [ ] **Step 2: Run them to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_speech_dictionary.py tests/test_pipeline_stages.py tests/test_pipeline_structure.py`
Expected: `54 failed, 14 passed, 1 error` — `KeyError: 'synthDrivers.WorldVoice.pipeline.speechDictionary'` (the `PipelineModules` view) and `ModuleNotFoundError: No module named 'speech_dictionary_test_worldvoice.pipeline.speechDictionary'`.

- [ ] **Step 3: Move the module**

```bash
W=addon/synthDrivers/WorldVoice
git mv $W/pipeline/speech_dictionary.py $W/pipeline/speechDictionary.py
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/registry.py` (1/3)

Replace:

```text

from . import speech_dictionary
from .breaks import _plain_breaks
```

With:

```text

from . import speechDictionary
from .breaks import _plain_breaks
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/registry.py` (2/3)

Replace:

```text
	log.debug("register pipeline stages")
	speech_dictionary.install()
	for stage in STAGES:
```

With:

```text
	log.debug("register pipeline stages")
	speechDictionary.install()
	for stage in STAGES:
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/registry.py` (3/3)

Replace:

```text
		filter_speechSequence.unregister(stage.handler)
	speech_dictionary.uninstall()
```

With:

```text
		filter_speechSequence.unregister(stage.handler)
	speechDictionary.uninstall()
```

- [ ] **Step 4: Run the tests to see green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_speech_dictionary.py tests/test_pipeline_stages.py tests/test_pipeline_structure.py`
Expected: `69 passed`.

Run: `$SCRATCH/runtests.sh . tests` → `3236 passed`, 0 skipped.

- [ ] **Step 5: Commit**

```bash
W=addon/synthDrivers/WorldVoice
git add $W/pipeline/speechDictionary.py $W/pipeline/registry.py tests/pipeline_harness.py tests/test_pipeline_stages.py tests/test_speech_dictionary.py
git diff --cached --stat
git commit -q -F - <<'EOF'
refactor: rename pipeline/speech_dictionary.py to speechDictionary.py

WorldVoice's own modules are named in camelCase; this was the one
snake_case name besides the generated Unicode data files (refactor8
A3).
EOF
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `git status --short` prints nothing; `HEAD:addon` = `b910738c3f8a9634a822edc6d666fa67384f6df3`, `HEAD:tests` = `abd56a8ea5fef042c476e70546e14ca3dae53f69`.

---

### Task 4: Rename `runtime/settings.py` to `runtime/voiceSettings.py` (F9)

**Files:**
- Move: `addon/synthDrivers/WorldVoice/runtime/settings.py` → `addon/synthDrivers/WorldVoice/runtime/voiceSettings.py` (content unchanged)
- Modify (one line each): `addon/synthDrivers/WorldVoice/__init__.py`, `runtime/session.py`, `bridge/voiceFacade.py`, `bridge/engineAdapter.py` (comment), `voices/mainLocalePolicy.py`, `voices/manager.py`, `voices/settingsRepository.py` (under `addon/synthDrivers/WorldVoice/`), `addon/globalPlugins/WorldVoice/rolePresenter.py`
- Test: `tests/runtime_harness.py`, `tests/conftest.py`, `tests/voice_binding_harness.py`, `tests/runtime_drain_integration_harness.py`, `tests/test_worldvoice_request_builder.py`, `tests/test_role_presenter.py`, and the `rt.settings` users `tests/test_f4_engine_session.py`, `tests/test_runtime_legacy_adapter.py`, `tests/test_runtime_session.py`, `tests/test_runtime_settings_store.py`, `tests/test_runtime_voice_facade.py`, `tests/test_runtime_voice_state.py`, `tests/test_voice_parameter_guards.py`

**Interfaces:**
- Consumes: Task 3's tree.
- Produces: module `runtime.voiceSettings` with `boolean`, `VOICE_PARAMETERS`, `PARAMETER_NAMES`, `VoiceState`, `VoiceSettingsStore`, `VoiceEditSession` (names unchanged); `runtime.settings` no longer exists. Test namespaces: `rt.voice_settings` (was `rt.settings`), `modules.voice_settings` in `tests/test_worldvoice_request_builder.py`.

- [ ] **Step 1: Point the tests at the new module**

**Edit:** `tests/conftest.py` (1/3)

Replace:

```text
		(".models", rt.models),
		(".settings", rt.settings),
		(".session", rt.session),
```

With:

```text
		(".models", rt.models),
		(".voiceSettings", rt.voice_settings),
		(".session", rt.session),
```

**Edit:** `tests/conftest.py` (2/3)

Replace:

```text
	driver = importlib.import_module(package + ".driver")
	settings = importlib.import_module(package + ".runtime.settings")
	scheduler = importlib.import_module(package + ".runtime.scheduler")
```

With:

```text
	driver = importlib.import_module(package + ".driver")
	voice_settings = importlib.import_module(package + ".runtime.voiceSettings")
	scheduler = importlib.import_module(package + ".runtime.scheduler")
```

**Edit:** `tests/conftest.py` (3/3)

Replace:

```text
	repo = MemoryRepository()
	store = settings.VoiceSettingsStore(repo)
	done, index = EventStub(), EventStub()
```

With:

```text
	repo = MemoryRepository()
	store = voice_settings.VoiceSettingsStore(repo)
	done, index = EventStub(), EventStub()
```

**Edit:** `tests/runtime_drain_integration_harness.py` (1/1)

Replace:

```text
	repo = MemoryRepository()
	store = rt.settings.VoiceSettingsStore(repo)

```

With:

```text
	repo = MemoryRepository()
	store = rt.voice_settings.VoiceSettingsStore(repo)

```

**Edit:** `tests/runtime_harness.py` (1/5)

Replace:

```text
	models = load(f"{package_name}.models", RUNTIME / "models.py")
	settings = load(f"{package_name}.settings", RUNTIME / "settings.py")
	session = load(f"{package_name}.session", RUNTIME / "session.py")
```

With:

```text
	models = load(f"{package_name}.models", RUNTIME / "models.py")
	voice_settings = load(f"{package_name}.voiceSettings", RUNTIME / "voiceSettings.py")
	session = load(f"{package_name}.session", RUNTIME / "session.py")
```

**Edit:** `tests/runtime_harness.py` (2/5)

Replace:

```text
		models=models,
		settings=settings,
		session=session,
```

With:

```text
		models=models,
		voice_settings=voice_settings,
		session=session,
```

**Edit:** `tests/runtime_harness.py` (3/5)

Replace:

```text
	monkeypatch.setitem(sys.modules, f"{package_name}.runtime.models", rt.models)
	monkeypatch.setitem(sys.modules, f"{package_name}.runtime.settings", rt.settings)
	return load_source(
```

With:

```text
	monkeypatch.setitem(sys.modules, f"{package_name}.runtime.models", rt.models)
	monkeypatch.setitem(sys.modules, f"{package_name}.runtime.voiceSettings", rt.voice_settings)
	return load_source(
```

**Edit:** `tests/runtime_harness.py` (4/5)

Replace:

```text
		(".models", rt.models),
		(".settings", rt.settings),
		(".session", rt.session),
```

With:

```text
		(".models", rt.models),
		(".voiceSettings", rt.voice_settings),
		(".session", rt.session),
```

**Edit:** `tests/runtime_harness.py` (5/5)

Replace:

```text
	repo = MemoryRepository()
	store = rt.settings.VoiceSettingsStore(repo)
	session = rt.session.EngineSession(adapter, store)
```

With:

```text
	repo = MemoryRepository()
	store = rt.voice_settings.VoiceSettingsStore(repo)
	session = rt.session.EngineSession(adapter, store)
```

**Edit:** `tests/test_f4_engine_session.py` (1/1)

Replace:

```text
def engine(session_module, bridge_modules, rt):
	store = rt.settings.VoiceSettingsStore(MemoryRepository())
	for key in ("Fake:a", "Fake:b"):
```

With:

```text
def engine(session_module, bridge_modules, rt):
	store = rt.voice_settings.VoiceSettingsStore(MemoryRepository())
	for key in ("Fake:a", "Fake:b"):
```

**Edit:** `tests/test_role_presenter.py` (1/3)

Replace:

```text

def load_presenter(monkeypatch, runtime_settings):
	"""Load the presenter against the runtime settings module the manager under test uses."""
	stub = StubModules(monkeypatch)
```

With:

```text

def load_presenter(monkeypatch, voice_settings):
	"""Load the presenter against the runtime voiceSettings module the manager under test uses."""
	stub = StubModules(monkeypatch)
```

**Edit:** `tests/test_role_presenter.py` (2/3)

Replace:

```text
		stub.module(package, __path__=[])
	monkeypatch.setitem(sys.modules, "synthDrivers.WorldVoice.runtime.settings", runtime_settings)
	package = runtime_settings.__name__.rsplit(".", 2)[0]
	monkeypatch.setitem(
```

With:

```text
		stub.module(package, __path__=[])
	monkeypatch.setitem(sys.modules, "synthDrivers.WorldVoice.runtime.voiceSettings", voice_settings)
	package = voice_settings.__name__.rsplit(".", 2)[0]
	monkeypatch.setitem(
```

**Edit:** `tests/test_role_presenter.py` (3/3)

Replace:

```text

	runtime_settings = sys.modules[module.__package__.removesuffix(".voices") + ".runtime.settings"]
	presenter = load_presenter(monkeypatch, runtime_settings)(
		manager,
```

With:

```text

	voice_settings = sys.modules[module.__package__.removesuffix(".voices") + ".runtime.voiceSettings"]
	presenter = load_presenter(monkeypatch, voice_settings)(
		manager,
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (1/5)

Replace:

```text
	assert core.writes == []
	snapshot = rt.settings.VoiceState(spec, {"rate": 72, "rateBoost": True}).snapshot()
	adapter.apply(spec, snapshot)
```

With:

```text
	assert core.writes == []
	snapshot = rt.voice_settings.VoiceState(spec, {"rate": 72, "rateBoost": True}).snapshot()
	adapter.apply(spec, snapshot)
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (2/5)

Replace:

```text
	adapter.open()
	state = rt.settings.VoiceState(make_spec(), {})
	adapter.apply(state.spec, state.snapshot())
```

With:

```text
	adapter.open()
	state = rt.voice_settings.VoiceState(make_spec(), {})
	adapter.apply(state.spec, state.snapshot())
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (3/5)

Replace:

```text
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	session = rt.session.EngineSession(adapter, rt.settings.VoiceSettingsStore(MemoryRepository()))
	with pytest.raises(ValueError, match="open failed"):
```

With:

```text
	adapter = bridge_modules.adapter.LegacyEngineAdapter(cls, lambda key: cls())
	session = rt.session.EngineSession(adapter, rt.voice_settings.VoiceSettingsStore(MemoryRepository()))
	with pytest.raises(ValueError, match="open failed"):
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (4/5)

Replace:

```text
	cls = env["Voice"]
	store = rt.settings.VoiceSettingsStore(MemoryRepository())
	store.ensure(make_spec("OneCore:a", "en")).update(rate=72)
```

With:

```text
	cls = env["Voice"]
	store = rt.voice_settings.VoiceSettingsStore(MemoryRepository())
	store.ensure(make_spec("OneCore:a", "en")).update(rate=72)
```

**Edit:** `tests/test_runtime_legacy_adapter.py` (5/5)

Replace:

```text
	assert core.writes == []
	state = rt.settings.VoiceState(make_spec(engine + ":a"), {"variant": "bright", "waitfactor": 4})
	adapter.apply(state.spec, state.snapshot())
```

With:

```text
	assert core.writes == []
	state = rt.voice_settings.VoiceState(make_spec(engine + ":a"), {"variant": "bright", "waitfactor": 4})
	adapter.apply(state.spec, state.snapshot())
```

**Edit:** `tests/test_runtime_session.py` (1/1)

Replace:

```text
def store(rt):
	return rt.settings.VoiceSettingsStore(MemoryRepository())

```

With:

```text
def store(rt):
	return rt.voice_settings.VoiceSettingsStore(MemoryRepository())

```

**Edit:** `tests/test_runtime_settings_store.py` (1/1)

Replace:

```text
def store(rt, repo):
	return rt.settings.VoiceSettingsStore(repo)

```

With:

```text
def store(rt, repo):
	return rt.voice_settings.VoiceSettingsStore(repo)

```

**Edit:** `tests/test_runtime_voice_facade.py` (1/1)

Replace:

```text
	repo = MemoryRepository()
	store = rt.settings.VoiceSettingsStore(repo)
	adapter = FakeAdapter()
```

With:

```text
	repo = MemoryRepository()
	store = rt.voice_settings.VoiceSettingsStore(repo)
	adapter = FakeAdapter()
```

**Edit:** `tests/test_runtime_voice_state.py` (1/11)

Replace:

```text
def test_pending_state_is_atomic_and_snapshot_is_immutable(rt):
	state = rt.settings.VoiceState(make_spec(), {})
	before = state.snapshot()
```

With:

```text
def test_pending_state_is_atomic_and_snapshot_is_immutable(rt):
	state = rt.voice_settings.VoiceState(make_spec(), {})
	before = state.snapshot()
```

**Edit:** `tests/test_runtime_voice_state.py` (2/11)

Replace:

```text
	values = {"rate": 62, "variant": "fast", "waitfactor": 2}
	state = rt.settings.VoiceState(make_spec(language="zh_TW"), values)
	values["rate"] = 99
```

With:

```text
	values = {"rate": 62, "variant": "fast", "waitfactor": 2}
	state = rt.voice_settings.VoiceState(make_spec(language="zh_TW"), values)
	values["rate"] = 99
```

**Edit:** `tests/test_runtime_voice_state.py` (3/11)

Replace:

```text
def test_unknown_setting_update_changes_nothing(rt):
	state = rt.settings.VoiceState(make_spec(), {})
	with pytest.raises(ValueError, match="Unknown voice setting"):
```

With:

```text
def test_unknown_setting_update_changes_nothing(rt):
	state = rt.voice_settings.VoiceState(make_spec(), {})
	with pytest.raises(ValueError, match="Unknown voice setting"):
```

**Edit:** `tests/test_runtime_voice_state.py` (4/11)

Replace:

```text
	with pytest.raises(ValueError, match="Unknown voice setting"):
		rt.settings.VoiceState(make_spec(), {"unknown": 1})

```

With:

```text
	with pytest.raises(ValueError, match="Unknown voice setting"):
		rt.voice_settings.VoiceState(make_spec(), {"unknown": 1})

```

**Edit:** `tests/test_runtime_voice_state.py` (5/11)

Replace:

```text
def test_same_value_does_not_increase_revision(rt):
	state = rt.settings.VoiceState(make_spec(), {})
	state.update(rate=50, pitch=50, variant="default", rateBoost=False, waitfactor=0)
```

With:

```text
def test_same_value_does_not_increase_revision(rt):
	state = rt.voice_settings.VoiceState(make_spec(), {})
	state.update(rate=50, pitch=50, variant="default", rateBoost=False, waitfactor=0)
```

**Edit:** `tests/test_runtime_voice_state.py` (6/11)

Replace:

```text
def test_checkpoint_keeps_pending_values_and_revision(rt):
	state = rt.settings.VoiceState(make_spec(), {})
	state.update(rate=72, pitch=63)
```

With:

```text
def test_checkpoint_keeps_pending_values_and_revision(rt):
	state = rt.voice_settings.VoiceState(make_spec(), {})
	state.update(rate=72, pitch=63)
```

**Edit:** `tests/test_runtime_voice_state.py` (7/11)

Replace:

```text
def test_unknown_checkpoint_changes_nothing(rt):
	state = rt.settings.VoiceState(make_spec(), {})
	state.update(rate=81)
```

With:

```text
def test_unknown_checkpoint_changes_nothing(rt):
	state = rt.voice_settings.VoiceState(make_spec(), {})
	state.update(rate=81)
```

**Edit:** `tests/test_runtime_voice_state.py` (8/11)

Replace:

```text

	state = rt.settings.VoiceState(make_spec(), {"pitch": BlockingPitch(50)})

```

With:

```text

	state = rt.voice_settings.VoiceState(make_spec(), {"pitch": BlockingPitch(50)})

```

**Edit:** `tests/test_runtime_voice_state.py` (9/11)

Replace:

```text
def test_boolean_preserves_existing_config_conversion(rt, value, expected):
	assert rt.settings.boolean(value) is expected

```

With:

```text
def test_boolean_preserves_existing_config_conversion(rt, value, expected):
	assert rt.voice_settings.boolean(value) is expected

```

**Edit:** `tests/test_runtime_voice_state.py` (10/11)

Replace:

```text
def test_parameter_definitions_provide_persisted_defaults(rt):
	values = {name: convert(default) for name, convert, default in rt.settings.VOICE_PARAMETERS}
	assert values == {
```

With:

```text
def test_parameter_definitions_provide_persisted_defaults(rt):
	values = {name: convert(default) for name, convert, default in rt.voice_settings.VOICE_PARAMETERS}
	assert values == {
```

**Edit:** `tests/test_runtime_voice_state.py` (11/11)

Replace:

```text
	}
	assert rt.settings.VoiceState(make_spec(), values).snapshot().waitfactor == 0

```

With:

```text
	}
	assert rt.voice_settings.VoiceState(make_spec(), values).snapshot().waitfactor == 0

```

**Edit:** `tests/test_voice_parameter_guards.py` (1/3)

Replace:

```text
def test_copyable_parameters_are_every_voice_parameter_but_the_variant(rt):
	assert rt.settings.PARAMETER_NAMES == ("rate", "pitch", "volume", "inflection", "rateBoost")
	names = {name for name, _, _ in rt.settings.VOICE_PARAMETERS}
	assert set(rt.settings.PARAMETER_NAMES) == names - {"variant"}

```

With:

```text
def test_copyable_parameters_are_every_voice_parameter_but_the_variant(rt):
	assert rt.voice_settings.PARAMETER_NAMES == ("rate", "pitch", "volume", "inflection", "rateBoost")
	names = {name for name, _, _ in rt.voice_settings.VOICE_PARAMETERS}
	assert set(rt.voice_settings.PARAMETER_NAMES) == names - {"variant"}

```

**Edit:** `tests/test_voice_parameter_guards.py` (2/3)

Replace:

```text
	order = bridge_modules.adapter.APPLY_ORDER
	assert sorted(order) == sorted(rt.settings.PARAMETER_NAMES)
	assert order[0] == "rateBoost"
```

With:

```text
	order = bridge_modules.adapter.APPLY_ORDER
	assert sorted(order) == sorted(rt.voice_settings.PARAMETER_NAMES)
	assert order[0] == "rateBoost"
```

**Edit:** `tests/test_voice_parameter_guards.py` (3/3)

Replace:

```text
	spec = load_config_repository(monkeypatch, rt).VOICE_CONFSPEC
	assert set(spec) == {name for name, _, _ in rt.settings.VOICE_PARAMETERS}
	for name in ("rate", "pitch", "volume", "inflection"):
```

With:

```text
	spec = load_config_repository(monkeypatch, rt).VOICE_CONFSPEC
	assert set(spec) == {name for name, _, _ in rt.voice_settings.VOICE_PARAMETERS}
	for name in ("rate", "pitch", "volume", "inflection"):
```

**Edit:** `tests/test_worldvoice_request_builder.py` (1/2)

Replace:

```text
		models=load("runtime.models"),
		settings=load("runtime.settings"),
		session=load("runtime.session"),
```

With:

```text
		models=load("runtime.models"),
		voice_settings=load("runtime.voiceSettings"),
		session=load("runtime.session"),
```

**Edit:** `tests/test_worldvoice_request_builder.py` (2/2)

Replace:

```text
	bridge.start(manager.on_event)
	store = modules.settings.VoiceSettingsStore(MemoryRepository())
	ports, voices = {}, {}
```

With:

```text
	bridge.start(manager.on_event)
	store = modules.voice_settings.VoiceSettingsStore(MemoryRepository())
	ports, voices = {}, {}
```

**Edit:** `tests/voice_binding_harness.py` (1/2)

Replace:

```text
	models = importlib.import_module(package + ".runtime.models")
	settings = importlib.import_module(package + ".runtime.settings")
	sessions = importlib.import_module(package + ".runtime.session")
```

With:

```text
	models = importlib.import_module(package + ".runtime.models")
	voice_settings = importlib.import_module(package + ".runtime.voiceSettings")
	sessions = importlib.import_module(package + ".runtime.session")
```

**Edit:** `tests/voice_binding_harness.py` (2/2)

Replace:

```text
	repository = importlib.import_module(package + ".voices.settingsRepository")
	store = settings.VoiceSettingsStore(repository.ConfigVoiceSettingsRepository(config.conf))
	session = sessions.EngineSession(FakeAdapter(), store)
```

With:

```text
	repository = importlib.import_module(package + ".voices.settingsRepository")
	store = voice_settings.VoiceSettingsStore(repository.ConfigVoiceSettingsRepository(config.conf))
	session = sessions.EngineSession(FakeAdapter(), store)
```

- [ ] **Step 2: Run them to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_runtime_voice_state.py tests/test_runtime_settings_store.py tests/test_runtime_session.py tests/test_runtime_voice_facade.py tests/test_runtime_legacy_adapter.py tests/test_f4_engine_session.py tests/test_voice_parameter_guards.py tests/test_voice_config_repository.py tests/test_role_presenter.py tests/test_worldvoice_request_builder.py`
Expected: `132 errors` — `FileNotFoundError` for `runtime/voiceSettings.py` (`load_runtime` loads it by path) and `ModuleNotFoundError: No module named '….runtime.voiceSettings'`.

- [ ] **Step 3: Move the module and its importers**

```bash
W=addon/synthDrivers/WorldVoice
git mv $W/runtime/settings.py $W/runtime/voiceSettings.py
```

**Edit:** `addon/globalPlugins/WorldVoice/rolePresenter.py` (1/1)

Replace:

```text

from synthDrivers.WorldVoice.runtime.settings import PARAMETER_NAMES
from synthDrivers.WorldVoice.voices.roles import prune_assignments
```

With:

```text

from synthDrivers.WorldVoice.runtime.voiceSettings import PARAMETER_NAMES
from synthDrivers.WorldVoice.voices.roles import prune_assignments
```

**Edit:** `addon/synthDrivers/WorldVoice/__init__.py` (1/1)

Replace:

```text
from .runtime.scheduler import TaskManager
from .runtime.settings import VoiceSettingsStore
from .ui.voicePanel import WorldVoiceVoiceSettingsPanel
```

With:

```text
from .runtime.scheduler import TaskManager
from .runtime.voiceSettings import VoiceSettingsStore
from .ui.voicePanel import WorldVoiceVoiceSettingsPanel
```

**Edit:** `addon/synthDrivers/WorldVoice/bridge/engineAdapter.py` (1/1)

Replace:

```text

# runtime.settings.PARAMETER_NAMES in the order engines receive them. rateBoost comes first:
# eSpeak converts the rate through the current rate boost (NVDA synthDrivers/espeak.py _set_rate).
```

With:

```text

# runtime.voiceSettings.PARAMETER_NAMES in the order engines receive them. rateBoost comes first:
# eSpeak converts the rate through the current rate boost (NVDA synthDrivers/espeak.py _set_rate).
```

**Edit:** `addon/synthDrivers/WorldVoice/bridge/voiceFacade.py` (1/1)

Replace:

```text
from ..runtime.session import EngineSession
from ..runtime.settings import VoiceSettingsStore

```

With:

```text
from ..runtime.session import EngineSession
from ..runtime.voiceSettings import VoiceSettingsStore

```

**Edit:** `addon/synthDrivers/WorldVoice/runtime/session.py` (1/1)

Replace:

```text
)
from .settings import VoiceSettingsStore

```

With:

```text
)
from .voiceSettings import VoiceSettingsStore

```

**Edit:** `addon/synthDrivers/WorldVoice/voices/mainLocalePolicy.py` (1/1)

Replace:

```text
from ..locales import primary_language
from ..runtime.settings import PARAMETER_NAMES

```

With:

```text
from ..locales import primary_language
from ..runtime.voiceSettings import PARAMETER_NAMES

```

**Edit:** `addon/synthDrivers/WorldVoice/voices/manager.py` (1/1)

Replace:

```text
from ..runtime.session import EngineSession, PlaybackPort
from ..runtime.settings import VoiceEditSession, VoiceSettingsStore
from .catalog import EMPTY_CATALOG, VoiceCatalog, group_by_primary_locale
```

With:

```text
from ..runtime.session import EngineSession, PlaybackPort
from ..runtime.voiceSettings import VoiceEditSession, VoiceSettingsStore
from .catalog import EMPTY_CATALOG, VoiceCatalog, group_by_primary_locale
```

**Edit:** `addon/synthDrivers/WorldVoice/voices/settingsRepository.py` (1/1)

Replace:

```text
from ..runtime.models import SettingValue, VoiceSpec, VoiceValues
from ..runtime.settings import VOICE_PARAMETERS, boolean

```

With:

```text
from ..runtime.models import SettingValue, VoiceSpec, VoiceValues
from ..runtime.voiceSettings import VOICE_PARAMETERS, boolean

```

- [ ] **Step 4: Run the tests to see green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_runtime_voice_state.py tests/test_runtime_settings_store.py tests/test_runtime_session.py tests/test_runtime_voice_facade.py tests/test_runtime_legacy_adapter.py tests/test_f4_engine_session.py tests/test_voice_parameter_guards.py tests/test_voice_config_repository.py tests/test_role_presenter.py tests/test_worldvoice_request_builder.py`
Expected: `132 passed`.

Run: `$SCRATCH/runtests.sh . tests` → `3236 passed`, 0 skipped.

- [ ] **Step 5: Commit**

```bash
W=addon/synthDrivers/WorldVoice
git add $W/runtime/voiceSettings.py $W/__init__.py $W/runtime/session.py $W/bridge/voiceFacade.py $W/bridge/engineAdapter.py $W/voices/mainLocalePolicy.py $W/voices/manager.py $W/voices/settingsRepository.py addon/globalPlugins/WorldVoice/rolePresenter.py tests/runtime_harness.py tests/conftest.py tests/voice_binding_harness.py tests/runtime_drain_integration_harness.py tests/test_worldvoice_request_builder.py tests/test_role_presenter.py tests/test_f4_engine_session.py tests/test_runtime_legacy_adapter.py tests/test_runtime_session.py tests/test_runtime_settings_store.py tests/test_runtime_voice_facade.py tests/test_runtime_voice_state.py tests/test_voice_parameter_guards.py
git diff --cached --stat
git commit -q -F - <<'EOF'
refactor: rename runtime/settings.py to runtime/voiceSettings.py

The add-on had three settings.py files for three different things; the
runtime one holds the per-voice parameter state (VoiceSettingsStore,
VoiceState, the parameter table), not settings of the runtime. No engine
wrapper or WorldVoice-workspace plugin imports it, so the public
runtime paths are unchanged. The test namespaces name the module
voice_settings, as they name every other runtime module.
EOF
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `git status --short` prints nothing; `HEAD:addon` = `127b3a6e34c92423b0bd65860c70868f0a331055`, `HEAD:tests` = `2e41077c263a76683b9c0048dbf48792bb565cd9`.

---

### Task 5: Gather the Unicode script data in `unicodeScripts/` (F10, test first)

**Files:**
- Create: `addon/synthDrivers/WorldVoice/unicodeScripts/__init__.py` (empty)
- Move: `languageDetection/scripts.py` → `unicodeScripts/lookup.py` (+ module docstring), `languageDetection/script_data.py` → `unicodeScripts/script_data.py` and `pipeline/unspaced_common_data.py` → `unicodeScripts/unspaced_common_data.py` (both byte-identical) (under `addon/synthDrivers/WorldVoice/`); `tests/test_language_scripts.py` → `tests/test_unicode_scripts.py`
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py`, `addon/synthDrivers/WorldVoice/pipeline/unspaced.py` (imports, one comment), `tools/generate_unicode_scripts.py` (docstring), `tools/generate_unspaced_common.py` (docstring, `SCRIPT_DATA`), `pyproject.toml` (coverage omit, ruff exclude), `.pre-commit-config.yaml` (exclude)
- Test: `tests/test_runtime_import_guard.py` (new parameter), `tests/test_pipeline_structure.py` (new guard), `tests/test_generate_unspaced_common.py` (new guard), `tests/test_unicode_scripts.py`, `tests/test_generated_unicode_data.py`, `tests/test_generate_unicode_scripts.py`, `tests/test_pipeline_unspaced_space.py`, `tests/test_translator_comments.py`, `tests/pipeline_harness.py`

**Interfaces:**
- Consumes: Task 4's tree.
- Produces: package `unicodeScripts` (empty `__init__.py`) with `lookup.get_script(codepoint: int) -> str | None`, `script_data` (`UNICODE_VERSION`, `SOURCE_SHA256`, `SCRIPT_RANGES`, `SCRIPT_RANGE_STARTS`) and `unspaced_common_data` (`UNSPACED_COMMON`, …), names unchanged; `languageDetection.scripts`, `languageDetection.script_data` and `pipeline.unspaced_common_data` no longer exist. `PIPELINE_MODULES` in `tests/pipeline_harness.py` no longer lists `unspaced_common_data`. Tests `test_package_init_stays_empty[unicodeScripts]`, `test_the_pipeline_does_not_import_language_detection`, `test_without_script_data_the_tool_reads_the_committed_one`, `test_pipeline_harness_loads_the_script_lookup_fresh` (renamed).

- [ ] **Step 1: Write the failing guards and point the tests at the new package**

```bash
git mv tests/test_language_scripts.py tests/test_unicode_scripts.py
```

**Edit:** `tests/pipeline_harness.py` (1/3)

Replace:

```text
	"speechDictionary",
	"unspaced_common_data",
)
```

With:

```text
	"speechDictionary",
)
```

**Edit:** `tests/pipeline_harness.py` (2/3)

Replace:

```text
		"synthDrivers.WorldVoice.languageDetection",
		"synthDrivers.WorldVoice.languageDetection.scripts",
		"synthDrivers.WorldVoice.pipeline",
```

With:

```text
		"synthDrivers.WorldVoice.languageDetection",
		"synthDrivers.WorldVoice.unicodeScripts.lookup",
		"synthDrivers.WorldVoice.pipeline",
```

**Edit:** `tests/pipeline_harness.py` (3/3)

Replace:

```text
		"synthDrivers.WorldVoice.pipeline.symbols",
		"synthDrivers.WorldVoice.pipeline.unspaced_common_data",
	]:
```

With:

```text
		"synthDrivers.WorldVoice.pipeline.symbols",
		"synthDrivers.WorldVoice.unicodeScripts.unspaced_common_data",
	]:
```

**Edit:** `tests/test_generate_unicode_scripts.py` (1/1)

Replace:

```text
"""tools/generate_unicode_scripts.py turns Unicode's Scripts.txt into languageDetection/script_data.py.

```

With:

```text
"""tools/generate_unicode_scripts.py turns Unicode's Scripts.txt into unicodeScripts/script_data.py.

```

**Edit:** `tests/test_generate_unspaced_common.py` (1/2)

Replace:

```text
import pytest
from addon_loader import ROOT, load_source
from pipeline_harness import load_pipeline_module, punctuation_settings
```

With:

```text
import pytest
from addon_loader import ROOT, WORLDVOICE, load_source
from pipeline_harness import load_pipeline_module, punctuation_settings
```

**Edit:** `tests/test_generate_unspaced_common.py` (2/2)

Replace:

```text

def _select(tool, extensions, scripts, categories):
```

With:

```text

def test_without_script_data_the_tool_reads_the_committed_one(tool):
	# --script-data defaults to the add-on's own generated file, wherever that file is moved.
	assert tool.SCRIPT_DATA == WORLDVOICE / "unicodeScripts" / "script_data.py"
	assert tool.SCRIPT_DATA.is_file()


def _select(tool, extensions, scripts, categories):
```

**Edit:** `tests/test_generated_unicode_data.py` (1/2)

Replace:

```text

languageDetection/script_data.py and pipeline/unspaced_common_data.py change only by running
tools/generate_unicode_scripts.py and tools/generate_unspaced_common.py (decided by the user,
```

With:

```text

unicodeScripts/script_data.py and unicodeScripts/unspaced_common_data.py change only by running
tools/generate_unicode_scripts.py and tools/generate_unspaced_common.py (decided by the user,
```

**Edit:** `tests/test_generated_unicode_data.py` (2/2)

Replace:

```text

SCRIPT_DATA = WORLDVOICE / "languageDetection" / "script_data.py"
UNSPACED_COMMON_DATA = WORLDVOICE / "pipeline" / "unspaced_common_data.py"
# The comment the unspaced Common generator writes after each range: the characters, then the
```

With:

```text

SCRIPT_DATA = WORLDVOICE / "unicodeScripts" / "script_data.py"
UNSPACED_COMMON_DATA = WORLDVOICE / "unicodeScripts" / "unspaced_common_data.py"
# The comment the unspaced Common generator writes after each range: the characters, then the
```

**Edit:** `tests/test_pipeline_structure.py` (1/1)

Replace:

```text

# mutmut's rewritten copy imports its own trampoline into every mutated module; the guard judges
```

With:

```text

def test_the_pipeline_does_not_import_language_detection():
	# The pipeline needs only the Unicode data, which unicodeScripts/ holds (refactor8 F10); an import
	# of languageDetection would load the detector, and NVDA's speech commands with it.
	for path in sorted((WORLDVOICE / "pipeline").glob("*.py")):
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
			if isinstance(node, ast.ImportFrom):
				names = [*(node.module or "").split("."), *(alias.name for alias in node.names)]
			elif isinstance(node, ast.Import):
				names = [part for alias in node.names for part in alias.name.split(".")]
			else:
				continue
			assert "languageDetection" not in names, f"{path.name}: {ast.unparse(node)}"


# mutmut's rewritten copy imports its own trampoline into every mutated module; the guard judges
```

**Edit:** `tests/test_pipeline_unspaced_space.py` (1/4)

Replace:

```text

LANGUAGE_DETECTION_SCRIPTS = "synthDrivers.WorldVoice.languageDetection.scripts"

```

With:

```text

SCRIPT_LOOKUP = "synthDrivers.WorldVoice.unicodeScripts.lookup"

```

**Edit:** `tests/test_pipeline_unspaced_space.py` (2/4)

Replace:

```text
	"""The General Category of each UNSPACED_COMMON character, as unspaced_common_data.py records it."""
	data = sys.modules["synthDrivers.WorldVoice.pipeline.unspaced_common_data"]
	source = Path(data.__file__).read_text(encoding="utf-8")
```

With:

```text
	"""The General Category of each UNSPACED_COMMON character, as unspaced_common_data.py records it."""
	data = sys.modules["synthDrivers.WorldVoice.unicodeScripts.unspaced_common_data"]
	source = Path(data.__file__).read_text(encoding="utf-8")
```

**Edit:** `tests/test_pipeline_unspaced_space.py` (3/4)

Replace:

```text
def test_unspaced_common_data_matches_the_script_data(env):
	data = sys.modules["synthDrivers.WorldVoice.pipeline.unspaced_common_data"]
	scripts = sys.modules["synthDrivers.WorldVoice.languageDetection.script_data"]
	assert data.UNICODE_VERSION == scripts.UNICODE_VERSION == "18.0.0"
```

With:

```text
def test_unspaced_common_data_matches_the_script_data(env):
	data = sys.modules["synthDrivers.WorldVoice.unicodeScripts.unspaced_common_data"]
	scripts = sys.modules["synthDrivers.WorldVoice.unicodeScripts.script_data"]
	assert data.UNICODE_VERSION == scripts.UNICODE_VERSION == "18.0.0"
```

**Edit:** `tests/test_pipeline_unspaced_space.py` (4/4)

Replace:

```text

def test_pipeline_harness_loads_language_detection_fresh(monkeypatch):
	# D5: each load imports the script lookup again, never one cached against an earlier test's stubs.
	load_pipeline_module(monkeypatch, punctuation_settings(0))
	first = sys.modules[LANGUAGE_DETECTION_SCRIPTS]
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	second = sys.modules[LANGUAGE_DETECTION_SCRIPTS]
	assert second is not first
```

With:

```text

def test_pipeline_harness_loads_the_script_lookup_fresh(monkeypatch):
	# D5: each load imports the script lookup again, never one cached against an earlier test's stubs.
	load_pipeline_module(monkeypatch, punctuation_settings(0))
	first = sys.modules[SCRIPT_LOOKUP]
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	second = sys.modules[SCRIPT_LOOKUP]
	assert second is not first
```

**Edit:** `tests/test_runtime_import_guard.py` (1/1)

Replace:

```text

@pytest.mark.parametrize("package", ["bridge", "voices", "ui", "pipeline"])
def test_package_init_stays_empty(package):
```

With:

```text

@pytest.mark.parametrize("package", ["bridge", "voices", "ui", "pipeline", "unicodeScripts"])
def test_package_init_stays_empty(package):
```

**Edit:** `tests/test_translator_comments.py` (1/1)

Replace:

```text
# Same exclusions as pyproject.toml and .pre-commit-config.yaml.
EXCLUDED = re.compile(r"^synthDrivers/WorldVoice/(driver/[^/]+/driver/|languageDetection/script_data\.py$)")
GETTEXT_CALL = re.compile(r"\b(_|pgettext|ngettext|npgettext)\(")
```

With:

```text
# Same exclusions as pyproject.toml and .pre-commit-config.yaml.
EXCLUDED = re.compile(r"^synthDrivers/WorldVoice/(driver/[^/]+/driver/|unicodeScripts/script_data\.py$)")
GETTEXT_CALL = re.compile(r"\b(_|pgettext|ngettext|npgettext)\(")
```

**Edit:** `tests/test_unicode_scripts.py` (1/3)

Replace:

```text

PACKAGE = "language_scripts_test_worldvoice"

```

With:

```text

PACKAGE = "unicode_scripts_test_worldvoice"

```

**Edit:** `tests/test_unicode_scripts.py` (2/3)

Replace:

```text
	alias_package(monkeypatch, PACKAGE, WORLDVOICE)
	# The detection package without its __init__, which needs NVDA's speech commands.
	alias_package(monkeypatch, PACKAGE + ".languageDetection", WORLDVOICE / "languageDetection")
	return importlib.import_module(PACKAGE + ".languageDetection.scripts")

```

With:

```text
	alias_package(monkeypatch, PACKAGE, WORLDVOICE)
	return importlib.import_module(PACKAGE + ".unicodeScripts.lookup")

```

**Edit:** `tests/test_unicode_scripts.py` (3/3)

Replace:

```text
def test_script_data_is_of_unicode_18(scripts):
	data = sys.modules[PACKAGE + ".languageDetection.script_data"]
	assert data.UNICODE_VERSION == "18.0.0"
```

With:

```text
def test_script_data_is_of_unicode_18(scripts):
	data = sys.modules[PACKAGE + ".unicodeScripts.script_data"]
	assert data.UNICODE_VERSION == "18.0.0"
```

- [ ] **Step 2: Run them to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_unicode_scripts.py tests/test_generated_unicode_data.py tests/test_generate_unicode_scripts.py tests/test_generate_unspaced_common.py tests/test_pipeline_unspaced_space.py tests/test_pipeline_structure.py tests/test_runtime_import_guard.py tests/test_translator_comments.py tests/test_language_detector.py`
Expected: `21 failed, 335 passed, 23 errors` — `ModuleNotFoundError: No module named 'unicode_scripts_test_worldvoice.unicodeScripts.lookup'`, `FileNotFoundError` for `unicodeScripts/script_data.py` and `unicodeScripts/unspaced_common_data.py`, `KeyError: 'synthDrivers.WorldVoice.unicodeScripts.unspaced_common_data'`, and the three new guards: `test_package_init_stays_empty[unicodeScripts]`, `test_the_pipeline_does_not_import_language_detection` (`unspaced.py: from ..languageDetection.scripts import get_script`) and `test_without_script_data_the_tool_reads_the_committed_one`.

- [ ] **Step 3: Create the package, move the three modules and update their users**

```bash
W=addon/synthDrivers/WorldVoice
mkdir $W/unicodeScripts
: > $W/unicodeScripts/__init__.py
git mv $W/languageDetection/scripts.py $W/unicodeScripts/lookup.py
git mv $W/languageDetection/script_data.py $W/unicodeScripts/script_data.py
git mv $W/pipeline/unspaced_common_data.py $W/unicodeScripts/unspaced_common_data.py
```

**Edit:** `.pre-commit-config.yaml` (1/1)

Replace:

```text
    # Generated by tools/generate_unicode_scripts.py.
    languageDetection/script_data\.py$
  )
```

With:

```text
    # Generated by tools/generate_unicode_scripts.py.
    unicodeScripts/script_data\.py$
  )
```

**Edit:** `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (1/1)

Replace:

```text
from ..speechCommands import WVLangChangeCommand
from .scripts import get_script

```

With:

```text
from ..speechCommands import WVLangChangeCommand
from ..unicodeScripts.lookup import get_script

```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/unspaced.py` (1/2)

Replace:

```text

from ..languageDetection.scripts import get_script
from .context import SpeechContext
from .sequence import SpeechCmd
from .unspaced_common_data import UNSPACED_COMMON

```

With:

```text

from ..unicodeScripts.lookup import get_script
from ..unicodeScripts.unspaced_common_data import UNSPACED_COMMON
from .context import SpeechContext
from .sequence import SpeechCmd

```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/unspaced.py` (2/2)

Replace:

```text
# pause (decided by the user, 2026-10-25). To extend the rule, add a script here and to
# UNSPACED_SCRIPT_CODES in tools/generate_unspaced_common.py, then regenerate unspaced_common_data.py.
UNSPACED_SCRIPTS = frozenset({"Han", "Hiragana", "Katakana", "Bopomofo", "Thai", "Lao", "Khmer", "Myanmar"})
```

With:

```text
# pause (decided by the user, 2026-10-25). To extend the rule, add a script here and to
# UNSPACED_SCRIPT_CODES in tools/generate_unspaced_common.py, then regenerate
# unicodeScripts/unspaced_common_data.py.
UNSPACED_SCRIPTS = frozenset({"Han", "Hiragana", "Katakana", "Bopomofo", "Thai", "Lao", "Khmer", "Myanmar"})
```

**Edit:** `addon/synthDrivers/WorldVoice/unicodeScripts/lookup.py` (1/1)

Replace:

```text
from bisect import bisect_right
```

With:

```text
"""The Unicode Script of a code point, looked up in the generated script_data.py."""

from bisect import bisect_right
```

**Edit:** `pyproject.toml` (1/2)

Replace:

```text
	"addon/synthDrivers/WorldVoice/driver/sonic/*",
	"addon/synthDrivers/WorldVoice/languageDetection/script_data.py",
]
```

With:

```text
	"addon/synthDrivers/WorldVoice/driver/sonic/*",
	"addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py",
]
```

**Edit:** `pyproject.toml` (2/2)

Replace:

```text
	# Generated by tools/generate_unicode_scripts.py.
	"./addon/synthDrivers/WorldVoice/languageDetection/script_data.py",
]
```

With:

```text
	# Generated by tools/generate_unicode_scripts.py.
	"./addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py",
]
```

**Edit:** `tools/generate_unicode_scripts.py` (1/3)

Replace:

```text
"""Generate languageDetection/script_data.py from Unicode's Scripts.txt.

```

With:

```text
"""Generate unicodeScripts/script_data.py from Unicode's Scripts.txt.

```

**Edit:** `tools/generate_unicode_scripts.py` (2/3)

Replace:

```text
	python3 tools/generate_unicode_scripts.py \
		addon/synthDrivers/WorldVoice/languageDetection/script_data.py \
		--unicode-version 16.0.0 --expected-sha256 <sha256>
```

With:

```text
	python3 tools/generate_unicode_scripts.py \
		addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py \
		--unicode-version 16.0.0 --expected-sha256 <sha256>
```

**Edit:** `tools/generate_unicode_scripts.py` (3/3)

Replace:

```text
	python3 tools/generate_unicode_scripts.py \
		addon/synthDrivers/WorldVoice/languageDetection/script_data.py --source Scripts.txt \
		--unicode-version 16.0.0 --expected-sha256 <sha256>
```

With:

```text
	python3 tools/generate_unicode_scripts.py \
		addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py --source Scripts.txt \
		--unicode-version 16.0.0 --expected-sha256 <sha256>
```

**Edit:** `tools/generate_unspaced_common.py` (1/4)

Replace:

```text
the General Category from Unicode's UnicodeData.txt and the Script from
languageDetection/script_data.py. ScriptExtensions.txt and script_data.py must be of
--unicode-version; UnicodeData.txt has no version header, so its sha256 pins it. Python's
```

With:

```text
the General Category from Unicode's UnicodeData.txt and the Script from
unicodeScripts/script_data.py. ScriptExtensions.txt and script_data.py must be of
--unicode-version; UnicodeData.txt has no version header, so its sha256 pins it. Python's
```

**Edit:** `tools/generate_unspaced_common.py` (2/4)

Replace:

```text
	python3 tools/generate_unspaced_common.py \
		addon/synthDrivers/WorldVoice/pipeline/unspaced_common_data.py --unicode-version 16.0.0 \
		--expected-sha256 <ScriptExtensions.txt sha256> --unicode-data-sha256 <UnicodeData.txt sha256>
```

With:

```text
	python3 tools/generate_unspaced_common.py \
		addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py --unicode-version 16.0.0 \
		--expected-sha256 <ScriptExtensions.txt sha256> --unicode-data-sha256 <UnicodeData.txt sha256>
```

**Edit:** `tools/generate_unspaced_common.py` (3/4)

Replace:

```text
	python3 tools/generate_unspaced_common.py \
		addon/synthDrivers/WorldVoice/pipeline/unspaced_common_data.py --unicode-version 16.0.0 \
		--source ScriptExtensions.txt --expected-sha256 <ScriptExtensions.txt sha256> \
```

With:

```text
	python3 tools/generate_unspaced_common.py \
		addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py --unicode-version 16.0.0 \
		--source ScriptExtensions.txt --expected-sha256 <ScriptExtensions.txt sha256> \
```

**Edit:** `tools/generate_unspaced_common.py` (4/4)

Replace:

```text
ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DATA = ROOT / "addon/synthDrivers/WorldVoice/languageDetection/script_data.py"

```

With:

```text
ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DATA = ROOT / "addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py"

```

- [ ] **Step 4: Run the tests to see green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_unicode_scripts.py tests/test_generated_unicode_data.py tests/test_generate_unicode_scripts.py tests/test_generate_unspaced_common.py tests/test_pipeline_unspaced_space.py tests/test_pipeline_structure.py tests/test_runtime_import_guard.py tests/test_translator_comments.py tests/test_language_detector.py`
Expected: `379 passed`.

Run: `$SCRATCH/runtests.sh . tests` → `3239 passed`, 0 skipped.

- [ ] **Step 5: Stage, prove the generated files unchanged, commit**

```bash
W=addon/synthDrivers/WorldVoice
git add $W/unicodeScripts/__init__.py $W/unicodeScripts/lookup.py $W/unicodeScripts/script_data.py $W/unicodeScripts/unspaced_common_data.py $W/languageDetection/__init__.py $W/pipeline/unspaced.py tools/generate_unicode_scripts.py tools/generate_unspaced_common.py pyproject.toml .pre-commit-config.yaml tests/pipeline_harness.py tests/test_generate_unicode_scripts.py tests/test_generate_unspaced_common.py tests/test_generated_unicode_data.py tests/test_pipeline_structure.py tests/test_pipeline_unspaced_space.py tests/test_runtime_import_guard.py tests/test_translator_comments.py tests/test_unicode_scripts.py
git diff --cached --stat
git show HEAD:$W/languageDetection/script_data.py | cmp - $W/unicodeScripts/script_data.py && echo "script_data.py identical"
git show HEAD:$W/pipeline/unspaced_common_data.py | cmp - $W/unicodeScripts/unspaced_common_data.py && echo "unspaced_common_data.py identical"
git diff --cached -M100% --name-status -- $W/languageDetection/script_data.py $W/pipeline/unspaced_common_data.py $W/unicodeScripts/script_data.py $W/unicodeScripts/unspaced_common_data.py
git commit -q -F - <<'EOF'
refactor: gather the Unicode script data in unicodeScripts/

The two generated Unicode data files come from the same Unicode release
but sat in two packages, and the pipeline imported languageDetection
only to look up a code point's script. unicodeScripts/ now holds the
lookup (lookup.py, formerly languageDetection/scripts.py) and both
generated files, moved byte for byte (authorized by the user for this
phase). The generators, their tests, the ruff, coverage and pre-commit
exclusions follow the new paths. New guards: the package's __init__.py
stays empty, the pipeline imports nothing from languageDetection, and
the unspaced generator's default --script-data is the moved file.
EOF
git status --short
git rev-parse HEAD:addon HEAD:tests HEAD:tools HEAD:pyproject.toml HEAD:.pre-commit-config.yaml
```

Expected: both `identical` lines; the `--name-status` output is exactly

```text
R100	addon/synthDrivers/WorldVoice/languageDetection/script_data.py	addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py
R100	addon/synthDrivers/WorldVoice/pipeline/unspaced_common_data.py	addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py
```

`git status --short` prints nothing; `HEAD:addon` = `d19e2d9895d023ff1fa2b222091edea9220a11e9`, `HEAD:tests` = `c7e77aeb55976e5931c01ce74dae3d99aa1f6da1`, `HEAD:tools` = `e0b77368e8b00b5e007d89900717663342c88914`, `HEAD:pyproject.toml` = `ffcc33ea055f6a7a3a6b3d62a724bff896409452`, `HEAD:.pre-commit-config.yaml` = `7b0c8e0bced20a6a3054b9b7444cab5c89aced91`.

---

### Task 6: Name the test helpers after the modules they load (phase 37 review M4)

**Files:**
- Move: `tests/test_pipeline_controls.py` → `tests/test_ui_controls.py`, `tests/test_voice_config_repository.py` → `tests/test_voice_settings_repository.py`
- Modify: `tests/ui_harness.py` (`load_voice_panel`, `load_ui_controls`), `tests/runtime_harness.py` (`load_settings_repository`), `tests/pipeline_harness.py`, `tests/test_legacy_speech_commands.py`, `tests/test_worldvoice_index_command.py` (`speech_commands`), `tests/test_ui_structure.py` (`UI_CONTROLS`, `test_ui_controls_imports_only_wx_and_the_layout_rules`), and the helpers' users `tests/test_pipeline_panels.py`, `tests/test_settings_order.py`, `tests/test_voice_settings_panel.py`, `tests/test_voice_parameter_guards.py`, `tests/test_ui_controls.py`, `tests/test_voice_settings_repository.py`

**Interfaces:**
- Consumes: Task 5's tree.
- Produces: `ui_harness.load_voice_panel(monkeypatch, *, conf=None)` (was `load_voice_settings_dialogs`), `ui_harness.load_ui_controls(monkeypatch, *, conf=None)` (was `load_pipeline_controls`), `runtime_harness.load_settings_repository(monkeypatch, rt)` (was `load_config_repository`); signatures unchanged. Fixture `speech_commands` (was `speechcommand`).

- [ ] **Step 1: Rename the helpers, their users and two test files**

```bash
git mv tests/test_pipeline_controls.py tests/test_ui_controls.py
git mv tests/test_voice_config_repository.py tests/test_voice_settings_repository.py
```

**Edit:** `tests/pipeline_harness.py` (1/2)

Replace:

```text

	speechcommand = stubs.module("synthDrivers.WorldVoice.speechCommands")

```

With:

```text

	speech_commands = stubs.module("synthDrivers.WorldVoice.speechCommands")

```

**Edit:** `tests/pipeline_harness.py` (2/2)

Replace:

```text

	speechcommand.WVLangChangeCommand = WVLangChangeCommand

```

With:

```text

	speech_commands.WVLangChangeCommand = WVLangChangeCommand

```

**Edit:** `tests/runtime_harness.py` (1/1)

Replace:

```text

def load_config_repository(monkeypatch, rt):
	# Supply only the package namespace: never execute the NVDA entry point.
```

With:

```text

def load_settings_repository(monkeypatch, rt):
	# Supply only the package namespace: never execute the NVDA entry point.
```

**Edit:** `tests/test_legacy_speech_commands.py` (1/4)

Replace:

```text
	commands = importlib.import_module(name + ".bridge.commands")
	speechcommand = importlib.import_module(name + ".speechCommands")
	return SimpleNamespace(
```

With:

```text
	commands = importlib.import_module(name + ".bridge.commands")
	speech_commands = importlib.import_module(name + ".speechCommands")
	return SimpleNamespace(
```

**Edit:** `tests/test_legacy_speech_commands.py` (2/4)

Replace:

```text
		commands=commands,
		speechcommand=speechcommand,
	)
```

With:

```text
		commands=commands,
		speech_commands=speech_commands,
	)
```

**Edit:** `tests/test_legacy_speech_commands.py` (3/4)

Replace:

```text
def test_normalizer_rejects_external_marker(legacy):
	marker = legacy.speechcommand.WorldVoiceIndexCommand(502)
	normalized = legacy.commands.normalize_legacy_commands(["before", marker, "after"])
```

With:

```text
def test_normalizer_rejects_external_marker(legacy):
	marker = legacy.speech_commands.WorldVoiceIndexCommand(502)
	normalized = legacy.commands.normalize_legacy_commands(["before", marker, "after"])
```

**Edit:** `tests/test_legacy_speech_commands.py` (4/4)

Replace:

```text
	assert index.index == 123
	assert not any(isinstance(command, legacy.speechcommand.WorldVoiceIndexCommand) for command in result)
```

With:

```text
	assert index.index == 123
	assert not any(isinstance(command, legacy.speech_commands.WorldVoiceIndexCommand) for command in result)
```

**Edit:** `tests/test_pipeline_panels.py` (1/2)

Replace:

```text
from pipeline_harness import LOG_SWITCH_ORDER
from ui_harness import load_settings_dialog, load_voice_settings_dialogs

```

With:

```text
from pipeline_harness import LOG_SWITCH_ORDER
from ui_harness import load_settings_dialog, load_voice_panel

```

**Edit:** `tests/test_pipeline_panels.py` (2/2)

Replace:

```text
	"""The real Voice panel over ui_harness's NVDA panel, without makeSettings."""
	module = load_voice_settings_dialogs(monkeypatch).module
	module.pipeline_settings = pipeline_settings
```

With:

```text
	"""The real Voice panel over ui_harness's NVDA panel, without makeSettings."""
	module = load_voice_panel(monkeypatch).module
	module.pipeline_settings = pipeline_settings
```

**Edit:** `tests/test_settings_order.py` (1/3)

Replace:

```text
	load_settings_dialog,
	load_voice_settings_dialogs,
	make_panel,
```

With:

```text
	load_settings_dialog,
	load_voice_panel,
	make_panel,
```

**Edit:** `tests/test_settings_order.py` (2/3)

Replace:

```text
def voice_panel(monkeypatch):
	env = load_voice_settings_dialogs(monkeypatch)
	panel = env.module.WorldVoiceVoiceSettingsPanel(TableDriver(env.module.PIPELINE_SETTINGS))
```

With:

```text
def voice_panel(monkeypatch):
	env = load_voice_panel(monkeypatch)
	panel = env.module.WorldVoiceVoiceSettingsPanel(TableDriver(env.module.PIPELINE_SETTINGS))
```

**Edit:** `tests/test_settings_order.py` (3/3)

Replace:

```text
	"""A WorldVoice Voice panel after the scenario; returns (env, panel, specs, windows before it)."""
	env = load_voice_settings_dialogs(monkeypatch)
	table_driver = TableDriver(env.module.PIPELINE_SETTINGS)
```

With:

```text
	"""A WorldVoice Voice panel after the scenario; returns (env, panel, specs, windows before it)."""
	env = load_voice_panel(monkeypatch)
	table_driver = TableDriver(env.module.PIPELINE_SETTINGS)
```

**Edit:** `tests/test_ui_controls.py` (1/4)

Replace:

```text
	TextCtrl,
	load_pipeline_controls,
	make_panel,
```

With:

```text
	TextCtrl,
	load_ui_controls,
	make_panel,
```

**Edit:** `tests/test_ui_controls.py` (2/4)

Replace:

```text
def build(monkeypatch, key, value, **changes):
	env = load_pipeline_controls(monkeypatch)
	spec = replace(env.settings.PIPELINE_SETTING_BY_KEY[key], **changes)
```

With:

```text
def build(monkeypatch, key, value, **changes):
	env = load_ui_controls(monkeypatch)
	spec = replace(env.settings.PIPELINE_SETTING_BY_KEY[key], **changes)
```

**Edit:** `tests/test_ui_controls.py` (3/4)

Replace:

```text
def test_change_events_cover_the_controller_kinds(monkeypatch):
	env = load_pipeline_controls(monkeypatch)
	assert env.controls.CHANGE_EVENTS == {"checkbox": "EVT_CHECKBOX", "choice": "EVT_CHOICE"}
```

With:

```text
def test_change_events_cover_the_controller_kinds(monkeypatch):
	env = load_ui_controls(monkeypatch)
	assert env.controls.CHANGE_EVENTS == {"checkbox": "EVT_CHECKBOX", "choice": "EVT_CHOICE"}
```

**Edit:** `tests/test_ui_controls.py` (4/4)

Replace:

```text
def helpers(monkeypatch):
	env = load_pipeline_controls(monkeypatch)
	env.layout = sys.modules["synthDrivers.WorldVoice.ui.panelLayout"]
```

With:

```text
def helpers(monkeypatch):
	env = load_ui_controls(monkeypatch)
	env.layout = sys.modules["synthDrivers.WorldVoice.ui.panelLayout"]
```

**Edit:** `tests/test_ui_structure.py` (1/2)

Replace:

```text
VOICE_PANEL = WORLDVOICE / "ui/voicePanel.py"
PIPELINE_CONTROLS = WORLDVOICE / "ui/controls.py"

```

With:

```text
VOICE_PANEL = WORLDVOICE / "ui/voicePanel.py"
UI_CONTROLS = WORLDVOICE / "ui/controls.py"

```

**Edit:** `tests/test_ui_structure.py` (2/2)

Replace:

```text
@pytest.mark.skipif(running_under_mutmut(), reason="mutmut's copy imports mutmut")
def test_pipeline_controls_imports_only_wx_and_the_layout_rules():
	# The main driver imports the Voice panel, which imports this module: reaching back into the
	# driver package, the panels or globalPlugins would close a cycle.
	tree = ast.parse(PIPELINE_CONTROLS.read_text(encoding="utf-8"))
	for node in ast.walk(tree):
```

With:

```text
@pytest.mark.skipif(running_under_mutmut(), reason="mutmut's copy imports mutmut")
def test_ui_controls_imports_only_wx_and_the_layout_rules():
	# The main driver imports the Voice panel, which imports this module: reaching back into the
	# driver package, the panels or globalPlugins would close a cycle.
	tree = ast.parse(UI_CONTROLS.read_text(encoding="utf-8"))
	for node in ast.walk(tree):
```

**Edit:** `tests/test_voice_parameter_guards.py` (1/2)

Replace:

```text

from runtime_harness import load_config_repository

```

With:

```text

from runtime_harness import load_settings_repository

```

**Edit:** `tests/test_voice_parameter_guards.py` (2/2)

Replace:

```text
def test_voice_confspec_lists_exactly_the_stored_parameters(monkeypatch, rt):
	spec = load_config_repository(monkeypatch, rt).VOICE_CONFSPEC
	assert set(spec) == {name for name, _, _ in rt.voice_settings.VOICE_PARAMETERS}
```

With:

```text
def test_voice_confspec_lists_exactly_the_stored_parameters(monkeypatch, rt):
	spec = load_settings_repository(monkeypatch, rt).VOICE_CONFSPEC
	assert set(spec) == {name for name, _, _ in rt.voice_settings.VOICE_PARAMETERS}
```

**Edit:** `tests/test_voice_settings_panel.py` (1/9)

Replace:

```text
	StaticText,
	fire,
	load_voice_settings_dialogs,
	pipeline_snapshot,
)
```

With:

```text
	StaticText,
	fire,
	load_voice_panel,
	pipeline_snapshot,
)
```

**Edit:** `tests/test_voice_settings_panel.py` (2/9)

Replace:

```text

def open_panel(monkeypatch, driver, **pipeline):
	env = load_voice_settings_dialogs(monkeypatch, conf=worldvoice_conf(pipeline=pipeline))
	panel = env.module.WorldVoiceVoiceSettingsPanel(driver)
	panel.makeSettings(panel.settingsSizer)
```

With:

```text

def open_panel(monkeypatch, driver, **pipeline):
	env = load_voice_panel(monkeypatch, conf=worldvoice_conf(pipeline=pipeline))
	panel = env.module.WorldVoiceVoiceSettingsPanel(driver)
	panel.makeSettings(panel.settingsSizer)
```

**Edit:** `tests/test_voice_settings_panel.py` (3/9)

Replace:

```text
def test_a_control_after_a_checkbox_row_lands_after_the_checkbox(monkeypatch):
	settings = (DriverSetting("voice"), BooleanDriverSetting("punctuationpauseenabled"))
	env = load_voice_settings_dialogs(monkeypatch, conf=worldvoice_conf())
	env.module.PIPELINE_SETTINGS = table_with(
		env,
```

With:

```text
def test_a_control_after_a_checkbox_row_lands_after_the_checkbox(monkeypatch):
	settings = (DriverSetting("voice"), BooleanDriverSetting("punctuationpauseenabled"))
	env = load_voice_panel(monkeypatch, conf=worldvoice_conf())
	env.module.PIPELINE_SETTINGS = table_with(
		env,
```

**Edit:** `tests/test_voice_settings_panel.py` (4/9)

Replace:

```text
def test_adjacent_non_driver_controls_keep_table_order(monkeypatch):
	settings = (DriverSetting("voice"), DriverSetting("nummod"))
	env = load_voice_settings_dialogs(monkeypatch, conf=worldvoice_conf())
	env.module.PIPELINE_SETTINGS = table_with(
		env,
```

With:

```text
def test_adjacent_non_driver_controls_keep_table_order(monkeypatch):
	settings = (DriverSetting("voice"), DriverSetting("nummod"))
	env = load_voice_panel(monkeypatch, conf=worldvoice_conf())
	env.module.PIPELINE_SETTINGS = table_with(
		env,
```

**Edit:** `tests/test_voice_settings_panel.py` (5/9)

Replace:

```text
	# one is kept and the other controls are still saved.
	settings = (DriverSetting("voice"), BooleanDriverSetting("punctuationpauseenabled"))
	env = load_voice_settings_dialogs(monkeypatch, conf=worldvoice_conf(pipeline={"number_mode": "group"}))
	env.module.PIPELINE_SETTINGS = table_with(
		env,
```

With:

```text
	# one is kept and the other controls are still saved.
	settings = (DriverSetting("voice"), BooleanDriverSetting("punctuationpauseenabled"))
	env = load_voice_panel(monkeypatch, conf=worldvoice_conf(pipeline={"number_mode": "group"}))
	env.module.PIPELINE_SETTINGS = table_with(
		env,
```

**Edit:** `tests/test_voice_settings_panel.py` (6/9)

Replace:

```text
def test_a_non_driver_checkbox_controls_its_dependent(monkeypatch):
	settings = (DriverSetting("voice"), BooleanDriverSetting("punctuationpauseenabled"))
	env = load_voice_settings_dialogs(
		monkeypatch,
		conf=worldvoice_conf(pipeline={"remove_punctuation_characters": False}),
```

With:

```text
def test_a_non_driver_checkbox_controls_its_dependent(monkeypatch):
	settings = (DriverSetting("voice"), BooleanDriverSetting("punctuationpauseenabled"))
	env = load_voice_panel(
		monkeypatch,
		conf=worldvoice_conf(pipeline={"remove_punctuation_characters": False}),
```

**Edit:** `tests/test_voice_settings_panel.py` (7/9)

Replace:

```text

def test_the_named_rule_and_placement_helpers_are_gone(monkeypatch):
	panel_class = load_voice_settings_dialogs(monkeypatch).module.WorldVoiceVoiceSettingsPanel
	for name in (
		"_bindNumberModeChoice",
```

With:

```text

def test_the_named_rule_and_placement_helpers_are_gone(monkeypatch):
	panel_class = load_voice_panel(monkeypatch).module.WorldVoiceVoiceSettingsPanel
	for name in (
		"_bindNumberModeChoice",
```

**Edit:** `tests/test_voice_settings_panel.py` (8/9)

Replace:

```text

def test_a_follower_of_a_failed_driver_control_follows_the_row_before(monkeypatch):
	env = load_voice_settings_dialogs(monkeypatch, conf=worldvoice_conf())

	class Panel(env.module.WorldVoiceVoiceSettingsPanel):
```

With:

```text

def test_a_follower_of_a_failed_driver_control_follows_the_row_before(monkeypatch):
	env = load_voice_panel(monkeypatch, conf=worldvoice_conf())

	class Panel(env.module.WorldVoiceVoiceSettingsPanel):
```

**Edit:** `tests/test_voice_settings_panel.py` (9/9)

Replace:

```text
def test_a_first_entry_without_a_driver_setting_comes_after_the_driver_rows(monkeypatch):
	settings = (DriverSetting("voice"), DriverSetting("nummod"))
	env = load_voice_settings_dialogs(monkeypatch, conf=worldvoice_conf())
	env.module.PIPELINE_SETTINGS = table_with(
		env,
```

With:

```text
def test_a_first_entry_without_a_driver_setting_comes_after_the_driver_rows(monkeypatch):
	settings = (DriverSetting("voice"), DriverSetting("nummod"))
	env = load_voice_panel(monkeypatch, conf=worldvoice_conf())
	env.module.PIPELINE_SETTINGS = table_with(
		env,
```

**Edit:** `tests/test_voice_settings_repository.py` (1/3)

Replace:

```text
from nvda_stubs import worldvoice_conf
from runtime_harness import load_config_repository, make_spec

```

With:

```text
from nvda_stubs import worldvoice_conf
from runtime_harness import load_settings_repository, make_spec

```

**Edit:** `tests/test_voice_settings_repository.py` (2/3)

Replace:

```text
def repository(monkeypatch, rt, conf):
	module = load_config_repository(monkeypatch, rt)
	return module.ConfigVoiceSettingsRepository(conf)
```

With:

```text
def repository(monkeypatch, rt, conf):
	module = load_settings_repository(monkeypatch, rt)
	return module.ConfigVoiceSettingsRepository(conf)
```

**Edit:** `tests/test_voice_settings_repository.py` (3/3)

Replace:

```text
	monkeypatch.setattr(builtins, "__import__", guarded_import)
	repository = load_config_repository(monkeypatch, rt).ConfigVoiceSettingsRepository(conf)
	values = repository.load(make_spec())
```

With:

```text
	monkeypatch.setattr(builtins, "__import__", guarded_import)
	repository = load_settings_repository(monkeypatch, rt).ConfigVoiceSettingsRepository(conf)
	values = repository.load(make_spec())
```

**Edit:** `tests/test_worldvoice_index_command.py` (1/3)

Replace:

```text
@pytest.fixture
def speechcommand(monkeypatch, nvda_commands):
	return load_source(monkeypatch, "worldvoice_index_command_test", RUNTIME.parent / "speechCommands.py")
```

With:

```text
@pytest.fixture
def speech_commands(monkeypatch, nvda_commands):
	return load_source(monkeypatch, "worldvoice_index_command_test", RUNTIME.parent / "speechCommands.py")
```

**Edit:** `tests/test_worldvoice_index_command.py` (2/3)

Replace:

```text

def test_marker_is_an_index_command(speechcommand, nvda_commands):
	marker = speechcommand.WorldVoiceIndexCommand(502)
	assert isinstance(marker, nvda_commands.IndexCommand)
```

With:

```text

def test_marker_is_an_index_command(speech_commands, nvda_commands):
	marker = speech_commands.WorldVoiceIndexCommand(502)
	assert isinstance(marker, nvda_commands.IndexCommand)
```

**Edit:** `tests/test_worldvoice_index_command.py` (3/3)

Replace:

```text

def test_marker_rejects_non_integer(speechcommand):
	with pytest.raises(ValueError):
		speechcommand.WorldVoiceIndexCommand("502")
```

With:

```text

def test_marker_rejects_non_integer(speech_commands):
	with pytest.raises(ValueError):
		speech_commands.WorldVoiceIndexCommand("502")
```

**Edit:** `tests/ui_harness.py` (1/2)

Replace:

```text

def load_pipeline_controls(monkeypatch, *, conf=None):
	"""The real ui/controls.py and the pipeline settings it builds controls for."""
```

With:

```text

def load_ui_controls(monkeypatch, *, conf=None):
	"""The real ui/controls.py and the pipeline settings it builds controls for."""
```

**Edit:** `tests/ui_harness.py` (2/2)

Replace:

```text

def load_voice_settings_dialogs(monkeypatch, *, conf=None):
	"""The real synthDrivers/WorldVoice/ui/voicePanel.py with real pipeline settings."""
```

With:

```text

def load_voice_panel(monkeypatch, *, conf=None):
	"""The real synthDrivers/WorldVoice/ui/voicePanel.py with real pipeline settings."""
```

- [ ] **Step 2: Run the renamed tests**

No add-on code changes, so there is no red state: the run checks that every renamed name resolves.

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_ui_controls.py tests/test_voice_settings_repository.py tests/test_ui_structure.py tests/test_pipeline_panels.py tests/test_settings_order.py tests/test_voice_settings_panel.py tests/test_voice_parameter_guards.py tests/test_legacy_speech_commands.py tests/test_worldvoice_index_command.py tests/test_pipeline_stages.py`
Expected: `178 passed`.

Run: `$SCRATCH/runtests.sh . tests` → `3239 passed`, 0 skipped.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ui_controls.py tests/test_voice_settings_repository.py tests/ui_harness.py tests/runtime_harness.py tests/pipeline_harness.py tests/test_legacy_speech_commands.py tests/test_worldvoice_index_command.py tests/test_ui_structure.py tests/test_pipeline_panels.py tests/test_settings_order.py tests/test_voice_settings_panel.py tests/test_voice_parameter_guards.py
git diff --cached --stat
git commit -q -F - <<'EOF'
test: name the test helpers after the modules they load

Phases 36 and 37 moved and renamed modules but kept the helpers that
load them: load_voice_settings_dialogs loads ui/voicePanel.py (one
panel), load_pipeline_controls ui/controls.py, load_config_repository
voices/settingsRepository.py, and the speechcommand names hold the
speechCommands module. The helpers, two test files and a structure
test now carry the new module names.
EOF
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `git status --short` prints nothing; `HEAD:addon` = `d19e2d9895d023ff1fa2b222091edea9220a11e9` (unchanged), `HEAD:tests` = `4509351fe7faa3e414e40448f60bfdfd134ee250`.

---

### Task 7: Check `recorder.py` with the stage modules (phase 38 review M2)

**Files:**
- Test: `tests/test_pipeline_structure.py` (`STAGE_MODULES`, its comment)

**Interfaces:**
- Consumes: Task 6's tree.
- Produces: test `test_pipeline_package_keeps_only_stages_logging_and_registry[recorder]`.

- [ ] **Step 1: Add `recorder` to the list**

**Edit:** `tests/test_pipeline_structure.py` (1/2)

Replace:

```text

# The modules pipeline/__init__.py was split into (phase 38): the stages, logging and registry.
STAGE_MODULES = [
```

With:

```text

# The modules pipeline/__init__.py was split into (phase 38) and the log's recorder.py: the stages,
# logging and registry.
STAGE_MODULES = [
```

**Edit:** `tests/test_pipeline_structure.py` (2/2)

Replace:

```text
	"languageCommands",
]
```

With:

```text
	"languageCommands",
	"recorder",
]
```

- [ ] **Step 2: Run the structure tests**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_structure.py`
Expected: `16 passed`.

- [ ] **Step 3: See the new parameter catch an `os` import (not committed)**

```bash
sed -i 's/^import csv$/import csv\nimport os/' addon/synthDrivers/WorldVoice/pipeline/recorder.py
python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_structure.py 2>&1 | tail -1
git checkout -- addon/synthDrivers/WorldVoice/pipeline/recorder.py
git status --short
```

Expected: `1 failed, 15 passed` (`test_pipeline_package_keeps_only_stages_logging_and_registry[recorder]`: `os` in the forbidden set); then `git status --short` prints only ` M tests/test_pipeline_structure.py`.

Run: `$SCRATCH/runtests.sh . tests` → `3240 passed`, 0 skipped.

- [ ] **Step 4: Commit**

```bash
git add tests/test_pipeline_structure.py
git diff --cached --stat
git commit -q -F - <<'EOF'
test: check the pipeline recorder with the stage modules

test_pipeline_package_keeps_only_stages_logging_and_registry says it
covers logging, but recorder.py, which writes the log file, was not in
its list; an os or NVDA import added there went unnoticed.
EOF
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `git status --short` prints nothing; `HEAD:addon` = `d19e2d9895d023ff1fa2b222091edea9220a11e9` (unchanged), `HEAD:tests` = `2d59af184cf6ad97b7a962ea876fe853fff42cde`.

---

### Task 8: Full verification (DEVELOPMENT_WORKFLOW.md §7)

**Files:** none.

**Interfaces:**
- Consumes: Task 7's tree.
- Produces: the verification record of the hand-off.

- [ ] **Step 1: Run every check**

```bash
$SCRATCH/runtests.sh . tests                         # 3240 passed, 0 skipped
prek run --all-files                               # every hook Passed
git diff --check e54d804                           # no output
git diff --stat e54d804 -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/   # no output
git ls-files addon/synthDrivers/WorldVoice/driver/Neural   # no output
git diff e54d804 -- tests/test_plugin_voice_contract.py   # no output
git diff -M100% --name-status e54d804 -- addon/synthDrivers/WorldVoice/languageDetection/script_data.py addon/synthDrivers/WorldVoice/pipeline/unspaced_common_data.py addon/synthDrivers/WorldVoice/unicodeScripts/
git grep -n -E 'WorldVoice/engine\b|WorldVoice\.engine\b|engine/(__init__|discovery)|assembly\.py|\.assembly\b|speech_dictionary\.py|pipeline\.speech_dictionary|runtime/settings\.py|runtime\.settings\b|languageDetection/scripts|languageDetection\.scripts|languageDetection/script_data|languageDetection\.script_data|pipeline/unspaced_common_data|pipeline\.unspaced_common_data|load_voice_settings_dialogs|load_pipeline_controls|load_config_repository|\bspeechcommand\b' -- . ':!docs'   # no output
```

The `-M100%` command lists the two generated files as `R100` and `unicodeScripts/__init__.py` as `A`, `unicodeScripts/lookup.py` as `A` (it is a rename below 100% because of its docstring; `git diff -M --stat e54d804` shows it as `{languageDetection/scripts.py => unicodeScripts/lookup.py}`). The §7 protected-path command with the old generated-file paths shows them deleted — the authorized move; `DEVELOPMENT_WORKFLOW.md` §7/§8 are updated by the orchestrator after merge.

---

## Dry run record

2026-10-26, fresh clone of `/workspace/WorldVoice` at `e54d804` in the scratchpad (`ref` symlinked, `prek install`), every step applied from this plan's text by a script that runs the step's bash blocks and applies its `Edit:` blocks by exact replacement in document order; the focused runs and full suites under a MemAvailable < 3 GB guard:

| Commit | Focused run (red, then green) | Full suite | Tree ids |
| --- | --- | --- | --- |
| Task 1 | `74 failed, 77 passed, 23 errors`, then `174 passed` | 3236 passed | match |
| Task 2 | `83 failed, 74 passed, 11 errors`, then `167 passed` | 3236 passed | match |
| Task 3 | `54 failed, 14 passed, 1 error`, then `69 passed` | 3236 passed | match |
| Task 4 | `132 errors`, then `132 passed` | 3236 passed | match |
| Task 5 | `21 failed, 335 passed, 23 errors`, then `379 passed`; both `identical` lines and the two `R100` lines | 3239 passed | match (also `tools`, `pyproject.toml`, `.pre-commit-config.yaml`) |
| Task 6 | `178 passed` | 3239 passed | match |
| Task 7 | `16 passed`; the uncommitted `import os` check `1 failed, 15 passed` | 3240 passed | match |

Every commit passed the hooks on the first try and left a clean tree. Task 8 in the clone: `prek run --all-files` all Passed; `git diff --check e54d804`, the protected-path command for `driver/*/driver/` and `driver/sonic/`, `git ls-files …/driver/Neural`, the `test_plugin_voice_contract.py` diff and the stale-name `git grep` printed nothing; the `-M100%` listing is the four lines described in Task 8.

The plan's blocks were generated from a prototype branch built in a separate clone (same commits); the clone's final root tree (`e81e389cedc091f73dd96e2eba0391b14c722c7e`, which also covers `tools/`, `pyproject.toml` and `.pre-commit-config.yaml`) equals the prototype's. An earlier dry run of the same plan text (before the red/green outputs were filled in) gave the same outputs and tree ids.

## 修正

Fix for the Fable review `docs/superpowers/finish/2026-10-26-phase39-naming-cleanup-review.md` (M1 in `tests/`; M2 is documentation outside the branch, done by the orchestrator after merge). It starts from the Task 7 tree — `HEAD:addon` = `d19e2d9895d023ff1fa2b222091edea9220a11e9`, `HEAD:tests` = `2d59af184cf6ad97b7a962ea876fe853fff42cde` — and touches `tests/` only, so `HEAD:addon` stays the same. Same block rules and Global Constraints as Tasks 1–8.

### Task F1: Drop the dead `languageDetection` reload from the pipeline harness (M1)

**Files:**
- Test: `tests/pipeline_harness.py` (the list of modules `load_pipeline_module` pops)

**Interfaces:**
- Consumes: the Task 7 tree.
- Produces: `load_pipeline_module` no longer pops `synthDrivers.WorldVoice.languageDetection`; everything else unchanged.

- [ ] **Step 1: Remove the entry**

The pipeline imports `unicodeScripts.lookup` and never loads the detector since Task 5 (`test_the_pipeline_does_not_import_language_detection`), so the entry pops a name this harness never puts in `sys.modules`.

**Edit:** `tests/pipeline_harness.py` (1/1)

Replace:

```text
		"synthDrivers.WorldVoice.numberLanguage",
		"synthDrivers.WorldVoice.languageDetection",
		"synthDrivers.WorldVoice.unicodeScripts.lookup",
```

With:

```text
		"synthDrivers.WorldVoice.numberLanguage",
		"synthDrivers.WorldVoice.unicodeScripts.lookup",
```

- [ ] **Step 2: Run the pipeline tests and the full suite**

No red state exists (the removed `pop(name, None)` never found the name).

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_unspaced_space.py tests/test_pipeline_stages.py tests/test_pipeline_structure.py tests/test_generate_unspaced_common.py tests/test_language_detector.py`
Expected: `364 passed`.

Run: `$SCRATCH/runtests.sh . tests` → `3240 passed`, 0 skipped.

- [ ] **Step 3: Commit**

```bash
git add tests/pipeline_harness.py
git diff --cached --stat   # 1 file, 1 deletion
git commit -q -F - <<'EOF'
test: drop the dead languageDetection reload from the pipeline harness

The harness pops the modules a pipeline load imports so that each load
gets them fresh. languageDetection was on that list only because
pipeline/unspaced.py reached the script lookup through it; since phase
39 the pipeline imports unicodeScripts.lookup and never loads the
detector, so the entry popped a name the harness never puts there and
suggested a dependency that no longer exists (phase 39 review M1).
EOF
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `git status --short` prints nothing; `HEAD:addon` = `d19e2d9895d023ff1fa2b222091edea9220a11e9` (unchanged), `HEAD:tests` = `cb49dbafec3e4df9e263eb7962947cafaaa9846a`.

### Task F2: Verification

- [ ] `$SCRATCH/runtests.sh . tests` → `3240 passed`, 0 skipped; `prek run --all-files` all Passed; `git diff --check master` prints nothing; Task 8's protected-path, Neural, contract and stale-name checks print nothing.

### 修正 dry run record

2026-10-26, the dry-run clone of this plan (`$SCRATCH/p39/final`, at the Task 7 tree `d19e2d98…`/`2d59af18…`, `ref` symlinked, hooks installed), the Edit block above applied by exact replacement, pytest under a MemAvailable < 3 GB guard:

| Commit | Files | Focused run | Full suite | Tree ids |
| --- | --- | --- | --- | --- |
| Task F1 | 1 (1 deletion) | `364 passed` | 3240 passed | `d19e2d98…`/`cb49dbaf…` |

The commit passed the hooks on the first try and left a clean tree.
