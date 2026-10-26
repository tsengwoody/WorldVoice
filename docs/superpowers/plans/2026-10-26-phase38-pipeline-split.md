# Phase 38: split `pipeline/__init__.py`, recorder and Say All into `pipeline/` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice complex flow (DEVELOPMENT_WORKFLOW.md §4): one implementer runs every task in order,
> applying the `File:`/`Edit:` blocks byte for byte; every commit's tree ids must match this plan.
> The orchestrator dispatches the final Fable 5.1 review (§3.3, §4.5).

**Goal:** Split the 1125-line `pipeline/__init__.py` into eight focused modules with an empty `__init__.py` (F1), move `log.py` to `pipeline/recorder.py` with the log file passed in (F6), move `sayAll.py` to `pipeline/sayAll.py` with a WorldVoice header (F8), and prove with a guard test that `synthDrivers.WorldVoice.pipeline.numbers` imports by its package path without NVDA (A2) — with no behavior change.

**Architecture:** Two `git mv` moves with small edits (Tasks 1–2), then one verbatim split (Task 3) done by a deterministic script that slices the old `__init__.py` by top-level definition and writes each new module with a fixed header; importers name the owning module. Tests read the pipeline through a `PipelineModules` view in `tests/pipeline_harness.py` that refuses attribute writes, and every patch moves to `module.registry`, where the stage handler looks the names up.

**Tech Stack:** Python 3 (NVDA add-on), pytest, ruff `==0.16.3` and add-trailing-comma through prek.

**Spec:** `docs/superpowers/specs/2026-10-26-phase38-pipeline-split-design.md`

**Base:** `master` `9f77382` — `HEAD:addon` = `0ce05e80f67d077c311702467f09befadba10bd5`, `HEAD:tests` = `4c484c956bfa897ef5c52740a8004ce66df01446`; `python3 -m pytest -q -p no:cacheprovider tests` → 3226 passed, 0 skipped; `prek run --all-files` all Passed. The spec and this plan are committed under `docs/` before Task 1 (`git add -f`, `docs/` is git-ignored but tracked); `docs/` does not enter the tree ids.

**Dry run:** see the end of this plan.

## Global Constraints

- Shell variables used below: `$SCRATCH` is the session scratchpad directory (`/tmp/claude-0/-workspace-WorldVoice/<session>/scratchpad`); every command runs from the repository root of the worktree.
- Apply every `Edit:` block as one exact replacement (the "Replace" text occurs exactly once in the file at that point). Block text is whole lines. The blocks are already in the form prek leaves them (ruff's isort order and format, add-trailing-comma), so each commit passes the hooks on the first try. If a hook still changes a file, stop: the tree ids will not match (§4.4).
- Public import paths do not change: `synthDrivers.WorldVoice.driver` (`Voice`, `getVoiceKey`), `runtime.{engineControl, models, playbackWork, segmentHost, session}`, `text.arabic`, `text.chunker`, `driver.sonic._sonic`. `tests/test_plugin_voice_contract.py` is not edited and stays green.
- Never modify `driver/<Engine>/driver/`, `driver/sonic/`, `languageDetection/script_data.py`, `pipeline/unspaced_common_data.py`; engine drivers stay independently installable; never stage Neural or `ref`.
- No rename of a moved class, function, constant or attribute; no UI string change; test assertions do not change (spec §3, §4).
- `pipeline/__init__.py` ends empty (0 bytes) (spec §5.1).
- ruff pinned `0.16.3`; tabs. Commits: English `<type>: <summary>` with a body saying why, no `Co-Authored-By`, `git add` with explicit paths only (after `git mv`, name only the new paths), check `git diff --cached --stat` first, never `--no-verify`, never `git stash`, no push, never touch the main checkout.
- Tests: one pytest process at a time (at most 3 workers), with a memory guard that kills pytest when MemAvailable < 3 GB, for example `$SCRATCH/runtests.sh` (a loop that polls `/proc/meminfo` every 2 s while pytest runs and `pkill`s it below 3 000 000 kB).

## Review Focus

1. **A patch that no longer reaches the code it means to change.** After the split, `current_context`, `pipeline_settings`, `pl`, `log`, `filter_speechSequence` and `read_stored` are looked up in `pipeline/registry.py`'s globals; a patch on any other module object would pass silently while testing the real function. Task 3: `PipelineModules.__setattr__` raises (so the suite proves no patch targets the view), every patch names `module.registry`, and Step 7's throw-away probe shows each patched value is read.
2. **Registering and unregistering exactly the handlers NVDA holds.** `STAGES` and its bound `Stage.handler`s must exist once; `unregister_stages` must remove the same objects `register_stages` added, around one `speech_dictionary.install`/`uninstall` pair. Task 3: `tests/test_pipeline_stages.py::test_register_puts_stages_first_in_order_and_unregister_removes_them` with `filter_speechSequence` patched on `module.registry`; `tests/test_pipeline_scope.py`.
3. **The log the user exports is the log the stages write, at `addon/log/pipeline.csv`.** The global plugin's export uses `pipeline.registry.pl`, the object `_LogWriter` writes through. Task 1: `test_the_pipeline_log_is_written_to_the_add_on_log_folder`; Task 3: `tests/test_pipeline_log.py` (service over the `pipeline.registry` stub) and `tests/test_settings_panels.py` (real `pipelineLog.py` importing `pl` from the registry stub).
4. **Import order at NVDA start: no cycle, no missing name.** The synth imports `pipeline.context`, `.languageCommands`, `.numberStages`, `.registry`, `.scope`; the global plugin imports `pipeline.sayAll` and `pipeline.scope`; `numberStages` imports `languageCommands`, never the reverse. Task 3: `tests/test_worldvoice_speak.py` (real imports of the three modules), `tests/test_runtime_composition.py` (the real `__init__.py` over per-module stubs), `test_number_lexing_imports_by_its_package_path_without_nvda`; Task 2: `tests/test_global_plugin_lifecycle.py`.
5. **Say All still adds `sayall_wait_factor` after each sequence.** Task 2: `tests/test_say_all.py` loads `pipeline.sayAll` by its package path inside the alias package.

---

### Task 1: Move `log.py` to `pipeline/recorder.py` with the log file passed in (F6, test first)

**Files:**
- Move: `addon/synthDrivers/WorldVoice/log.py` → `addon/synthDrivers/WorldVoice/pipeline/recorder.py` (module docstring, class docstring, `PipelineLog(log_file)`; no import-time path)
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (import of `PipelineLog`, `Path`; `pl` built from `addon/log/pipeline.csv`)
- Test: `tests/pipeline_harness.py` (stub `synthDrivers.WorldVoice.pipeline.recorder`), `tests/test_pipeline_log.py` (new path test, recorder path, fixture), `tests/test_pipeline_log_rotation.py`

**Interfaces:**
- Consumes: the base tree.
- Produces: `pipeline.recorder.PipelineLog(log_file: Path)` with `.log_file`, `FIELDNAMES`, `write`, `move_to` unchanged; module constant `MAX_LOG_SIZE`. `pl` in the pipeline package is `PipelineLog(<addon>/log/pipeline.csv)`. The harness stub's `PipelineLog` keeps `.args`. Test `test_the_pipeline_log_is_written_to_the_add_on_log_folder`.

- [ ] **Step 1: Write the failing tests and point the recorder tests at the new path**

**Edit:** `tests/pipeline_harness.py` (1/2)

Replace:

```text
		"synthDrivers.WorldVoice.languageDetection.scripts",
		"synthDrivers.WorldVoice.log",
		"synthDrivers.WorldVoice.pipeline",
		"synthDrivers.WorldVoice.pipeline.speech_dictionary",
```

With:

```text
		"synthDrivers.WorldVoice.languageDetection.scripts",
		"synthDrivers.WorldVoice.pipeline",
		"synthDrivers.WorldVoice.pipeline.recorder",
		"synthDrivers.WorldVoice.pipeline.speech_dictionary",
```

**Edit:** `tests/pipeline_harness.py` (2/2)

Replace:

```text

	worldVoiceLog = stubs.module("synthDrivers.WorldVoice.log")

	class PipelineLog:
		def __init__(self, *args, **kwargs):
			pass

	worldVoiceLog.PipelineLog = PipelineLog

```

With:

```text

	recorder = stubs.module("synthDrivers.WorldVoice.pipeline.recorder")

	class PipelineLog:
		"""Keeps what the pipeline passes; it has no write, so a test that logs must replace pl."""

		def __init__(self, *args):
			self.args = args

	recorder.PipelineLog = PipelineLog

```

**Edit:** `tests/test_pipeline_log.py` (1/5)

Replace:

```text
from nvda_stubs import RefusingSection, StubModules, worldvoice_conf
from pipeline_harness import load_settings_module

LOG = WORLDVOICE / "log.py"
SERVICE = ADDON / "globalPlugins/WorldVoice/pipelineLog.py"
```

With:

```text
from nvda_stubs import RefusingSection, StubModules, worldvoice_conf
from pipeline_harness import load_pipeline_module, load_settings_module, punctuation_settings

RECORDER = WORLDVOICE / "pipeline/recorder.py"
SERVICE = ADDON / "globalPlugins/WorldVoice/pipelineLog.py"
```

**Edit:** `tests/test_pipeline_log.py` (2/5)

Replace:

```text
@pytest.fixture
def log_module(monkeypatch, tmp_path):
	module = load_source(monkeypatch, "worldvoice_log_under_test", LOG)
	monkeypatch.setattr(module, "log_dir", tmp_path / "missing" / "log")
	return module

```

With:

```text
@pytest.fixture
def log_module(monkeypatch):
	return load_source(monkeypatch, "worldvoice_log_under_test", RECORDER)


def test_the_pipeline_log_is_written_to_the_add_on_log_folder(monkeypatch):
	# The recorder moved into pipeline/ (phase 38); the file it writes stays addon/log/pipeline.csv.
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	recorder = load_source(monkeypatch, "worldvoice_recorder_path_under_test", RECORDER)
	assert recorder.PipelineLog(*module.pl.args).log_file == ADDON / "log" / "pipeline.csv"

```

**Edit:** `tests/test_pipeline_log.py` (3/5)

Replace:

```text
def test_pipeline_log_touches_the_disk_only_when_written(log_module, tmp_path):
	pipeline = log_module.PipelineLog("pipeline.csv")
	assert not (tmp_path / "missing").exists()
```

With:

```text
def test_pipeline_log_touches_the_disk_only_when_written(log_module, tmp_path):
	pipeline = log_module.PipelineLog(tmp_path / "missing" / "log" / "pipeline.csv")
	assert not (tmp_path / "missing").exists()
```

**Edit:** `tests/test_pipeline_log.py` (4/5)

Replace:

```text
def test_move_to_hands_over_the_log_and_starts_a_new_one(log_module, tmp_path):
	pipeline = log_module.PipelineLog("pipeline.csv")
	pipeline.write("id", "label", "before", ["text"])
```

With:

```text
def test_move_to_hands_over_the_log_and_starts_a_new_one(log_module, tmp_path):
	pipeline = log_module.PipelineLog(tmp_path / "missing" / "log" / "pipeline.csv")
	pipeline.write("id", "label", "before", ["text"])
```

**Edit:** `tests/test_pipeline_log.py` (5/5)

Replace:

```text
def test_move_to_exports_a_log_that_was_never_written(log_module, tmp_path):
	pipeline = log_module.PipelineLog("pipeline.csv")
	dst = tmp_path / "exported" / "out.csv"
```

With:

```text
def test_move_to_exports_a_log_that_was_never_written(log_module, tmp_path):
	pipeline = log_module.PipelineLog(tmp_path / "missing" / "log" / "pipeline.csv")
	dst = tmp_path / "exported" / "out.csv"
```

**Edit:** `tests/test_pipeline_log_rotation.py` (1/1)

Replace:

```text
from addon_loader import WORLDVOICE, load_source


@pytest.fixture
def pipeline_log(monkeypatch, tmp_path):
	module = load_source(monkeypatch, "worldvoice_log_rotation_under_test", WORLDVOICE / "log.py")
	monkeypatch.setattr(module, "log_dir", tmp_path)
	monkeypatch.setattr(module, "MAX_LOG_SIZE", 200)
	return module.PipelineLog("pipeline.csv")


```

With:

```text
from addon_loader import WORLDVOICE, load_source

RECORDER = WORLDVOICE / "pipeline/recorder.py"


@pytest.fixture
def pipeline_log(monkeypatch, tmp_path):
	module = load_source(monkeypatch, "worldvoice_log_rotation_under_test", RECORDER)
	monkeypatch.setattr(module, "MAX_LOG_SIZE", 200)
	return module.PipelineLog(tmp_path / "pipeline.csv")


```

- [ ] **Step 2: Run them to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_log.py tests/test_pipeline_log_rotation.py tests/test_pipeline_stages.py`
Expected: `1 failed, 62 passed, 5 errors` — `test_the_pipeline_log_is_written_to_the_add_on_log_folder` fails and the five recorder tests error, all with `FileNotFoundError` for `pipeline/recorder.py`.

- [ ] **Step 3: Move the recorder and let the pipeline name its file**

```bash
W=addon/synthDrivers/WorldVoice
git mv $W/log.py $W/pipeline/recorder.py
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/recorder.py` (1/3)

Replace:

```text
import csv
```

With:

```text
"""The speech pipeline's log: a CSV file of each logged stage's sequence before and after it ran."""

import csv
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/recorder.py` (2/3)

Replace:

```text

script_dir = Path(__file__).resolve().parent
parent_dir = script_dir.parent.parent

log_dir = parent_dir / "log"
MAX_LOG_SIZE = 5 * 1024 * 1024
```

With:

```text

MAX_LOG_SIZE = 5 * 1024 * 1024
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/recorder.py` (3/3)

Replace:

```text
class PipelineLog:
	FIELDNAMES = ("id", "label", "timing", "timestamp", "sequence")

	def __init__(self, log_name):
		self.log_file = log_dir / log_name

```

With:

```text
class PipelineLog:
	"""Rows in *log_file*, which moves aside to ".old" once it reaches MAX_LOG_SIZE.

	The pipeline passes addon/log/pipeline.csv; nothing here depends on where this module lies.
	"""

	FIELDNAMES = ("id", "label", "timing", "timestamp", "sequence")

	def __init__(self, log_file: Path):
		self.log_file = log_file

```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (1/4)

Replace:

```text
from functools import wraps
from typing import TYPE_CHECKING, Literal, Union
```

With:

```text
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Union
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (2/4)

Replace:

```text
from ..languageDetection.scripts import get_script
from ..log import PipelineLog
from ..numberLanguage import FOLLOW, MAIN
```

With:

```text
from ..languageDetection.scripts import get_script
from ..numberLanguage import FOLLOW, MAIN
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (3/4)

Replace:

```text
from .numbers import NUMBER_RE, number_pieces, split_spaced_numbers, strip_thousands
from .settings import pipeline_settings, read_stored
```

With:

```text
from .numbers import NUMBER_RE, number_pieces, split_spaced_numbers, strip_thousands
from .recorder import PipelineLog
from .settings import pipeline_settings, read_stored
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (4/4)

Replace:

```text
SpeechCmd = Union[str, "SpeechCommand"]
pl = PipelineLog("pipeline.csv")

```

With:

```text
SpeechCmd = Union[str, "SpeechCommand"]
# The pipeline log is addon/log/pipeline.csv; parents[3] of a module in pipeline/ is addon/.
pl = PipelineLog(Path(__file__).resolve().parents[3] / "log" / "pipeline.csv")

```

- [ ] **Step 4: Run the tests to see green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_log.py tests/test_pipeline_log_rotation.py tests/test_pipeline_stages.py`
Expected: `68 passed`.

Run: `python3 -m pytest -q -p no:cacheprovider tests` → `3227 passed`, 0 skipped.

- [ ] **Step 5: Commit**

```bash
W=addon/synthDrivers/WorldVoice
git add $W/pipeline/recorder.py $W/pipeline/__init__.py tests/pipeline_harness.py tests/test_pipeline_log.py tests/test_pipeline_log_rotation.py
git diff --cached --stat   # 5 files: 1 rename, 4 modified
git commit -q -F - <<'EOF'
refactor: move the pipeline log recorder into pipeline/

log.py held only PipelineLog, whose one user is the pipeline, and its
name read like the add-on's logger. It now lives in pipeline/recorder.py.
It found the log folder from its own depth, so a move would have moved
the log; the recorder now takes its file, and the pipeline passes
addon/log/pipeline.csv. A test pins that path.
EOF
git rev-parse HEAD:addon HEAD:tests
```

Expected after the commit: `HEAD:addon` = `0477c569b0e3188cae78f11110cf682991476e46`, `HEAD:tests` = `603bce91eefae72539fcf06c81067070b9b9d3f5`

---

### Task 2: Move `sayAll.py` to `pipeline/sayAll.py` with a WorldVoice header (F8, test first)

**Files:**
- Move: `addon/synthDrivers/WorldVoice/sayAll.py` → `addon/synthDrivers/WorldVoice/pipeline/sayAll.py` (module docstring instead of NVDA's header; relative imports one level up)
- Modify: `addon/globalPlugins/WorldVoice/__init__.py` (one import line, moved to its isort place)
- Test: `tests/test_say_all.py`, `tests/ui_harness.py`

**Interfaces:**
- Consumes: Task 1's tree.
- Produces: module `synthDrivers.WorldVoice.pipeline.sayAll` with `patch()`, `unpatch()` (names and behavior unchanged); nothing re-exports it.

- [ ] **Step 1: Point the tests at the new module**

**Edit:** `tests/test_say_all.py` (1/1)

Replace:

```text
	return SimpleNamespace(
		module=importlib.import_module(PACKAGE + ".sayAll"),
		nvda=nvda_speech,
```

With:

```text
	return SimpleNamespace(
		module=importlib.import_module(PACKAGE + ".pipeline.sayAll"),
		nvda=nvda_speech,
```

**Edit:** `tests/ui_harness.py` (1/1)

Replace:

```text
	)
	stubs.module("synthDrivers.WorldVoice.sayAll", patch=record("patch"), unpatch=record("unpatch"))
	env.workspace = ["workspace"]
```

With:

```text
	)
	stubs.module("synthDrivers.WorldVoice.pipeline.sayAll", patch=record("patch"), unpatch=record("unpatch"))
	env.workspace = ["workspace"]
```

- [ ] **Step 2: Run them to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_say_all.py tests/test_global_plugin_lifecycle.py tests/test_global_plugin_menu.py`
Expected: `16 failed, 2 passed, 5 errors` — `ModuleNotFoundError: No module named 'say_all_test_worldvoice.pipeline.sayAll'` (5 errors, `test_say_all.py`) and `No module named 'synthDrivers.WorldVoice.sayAll'` at `addon/globalPlugins/WorldVoice/__init__.py:15` (16 failures: the global plugin harness now stubs only the new name).

- [ ] **Step 3: Move the module and fix its importer**

```bash
W=addon/synthDrivers/WorldVoice
git mv $W/sayAll.py $W/pipeline/sayAll.py
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/sayAll.py` (1/2)

Replace:

```text
# A part of NonVisual Desktop Access (NVDA)
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.


```

With:

```text
"""Say All's pause after each speech sequence, the pipeline setting sayall_wait_factor.

patch() hands NVDA's say-all a getTextInfoSpeech that adds the pause, through the same
speech.sayAll.initialize call NVDA makes when speech starts (speech.initialize in
ref/nvda/source/speech/__init__.py); unpatch() makes that call with NVDA's own functions again.
"""

```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/sayAll.py` (2/2)

Replace:

```text

from .pipeline.context import current_context
from .pipeline.settings import pipeline_settings

```

With:

```text

from .context import current_context
from .settings import pipeline_settings

```

**Edit:** `addon/globalPlugins/WorldVoice/__init__.py` (1/1)

Replace:

```text
# `generics`, on sys.path; keep these before the generics imports.
from synthDrivers.WorldVoice.pipeline.scope import pipeline_scope
from synthDrivers.WorldVoice.sayAll import patch, unpatch
from synthDrivers.WorldVoice.workspace import workspace_path
```

With:

```text
# `generics`, on sys.path; keep these before the generics imports.
from synthDrivers.WorldVoice.pipeline.sayAll import patch, unpatch
from synthDrivers.WorldVoice.pipeline.scope import pipeline_scope
from synthDrivers.WorldVoice.workspace import workspace_path
```

- [ ] **Step 4: Run the tests to see green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_say_all.py tests/test_global_plugin_lifecycle.py tests/test_global_plugin_menu.py`
Expected: `23 passed`.

Run: `python3 -m pytest -q -p no:cacheprovider tests` → `3227 passed`, 0 skipped.

- [ ] **Step 5: Commit**

```bash
W=addon/synthDrivers/WorldVoice
git add $W/pipeline/sayAll.py addon/globalPlugins/WorldVoice/__init__.py tests/test_say_all.py tests/ui_harness.py
git diff --cached --stat   # 4 files: 1 rename, 3 modified
git commit -q -F - <<'EOF'
refactor: move the Say All patch into pipeline/

sayAll.py applies the pipeline setting sayall_wait_factor, yet sat at
the package root under NVDA's copyright header, so a reader of the
pipeline settings could not find where the setting takes effect. It now
lives in pipeline/sayAll.py with a docstring saying what it patches and
that it makes the same sayAll.initialize call NVDA makes. The global
plugin imports it from there; nothing re-exports it.
EOF
git rev-parse HEAD:addon HEAD:tests
```

Expected after the commit: `HEAD:addon` = `b13d70ab99812164fc59fae72469ac8ab4f50211`, `HEAD:tests` = `335a0318c18d8ba1cdccd541c830ed0a34c8a21a`

---

### Task 3: Split `pipeline/__init__.py` into its stage modules (F1) with the A2 guard (test first)

**Files:**
- Create (by the script below): `addon/synthDrivers/WorldVoice/pipeline/{sequence,breaks,items,numberStages,punctuation,unspaced,languageCommands,registry}.py`; empty `addon/synthDrivers/WorldVoice/pipeline/__init__.py`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`, `addon/synthDrivers/WorldVoice/pipeline/scope.py`, `addon/globalPlugins/WorldVoice/pipelineLog.py`, `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (imports), `pyproject.toml` (mutmut `source_paths`)
- Test: `tests/test_pipeline_structure.py` (A2 guard, structure test per module), `tests/test_runtime_import_guard.py` (empty `pipeline/__init__.py`), `tests/pipeline_harness.py` (`PipelineModules`), `tests/test_pipeline_stages.py`, `tests/test_pipeline_filters.py`, `tests/test_pipeline_nvda_ssml.py`, `tests/test_pipeline_number_edges.py`, `tests/test_settings_panels.py` (patch targets), `tests/nvda_stubs.py`, `tests/ui_harness.py`, `tests/test_pipeline_log.py`, `tests/test_runtime_composition.py`, `tests/test_pipeline_scope.py`, `tests/test_worldvoice_speak.py` (module names)

**Interfaces:**
- Consumes: Tasks 1–2 (`pl` line and `from .recorder import PipelineLog` in `pipeline/__init__.py`, which the script checks by SHA-256).
- Produces: the modules of spec §2.1, every name unchanged: `pipeline.languageCommands.{remove_language_command, deduplicate_language_command, lang_cmd_to_voice, inject_langchange_reorder}`, `pipeline.numberStages.{inject_numbers, number_wait_factor, remove_thousands_separators, wrap_numbers_for_detection, detect_with_number_language, merge_consecutive_strings, …}`, `pipeline.registry.{pl, LOG_SWITCHES, STAGES, Stage, listable, order_move_to_start_register, register_stages, unregister_stages, …}`, `pipeline.breaks.{NumberBreakCommand, NumberEdgeBreakCommand, NumberItemEdgeBreakCommand, PunctuationBreakCommand, _merge_edge_breaks, _plain_breaks, …}`, `pipeline.sequence.SpeechCmd`. `tests/pipeline_harness.load_pipeline_module` returns `(PipelineModules, BreakCommand)`; `module.registry` etc. are the modules. Tests `test_number_lexing_imports_by_its_package_path_without_nvda`, `test_package_init_stays_empty[pipeline]`, `test_pipeline_package_keeps_only_stages_logging_and_registry[<module>]`.

- [ ] **Step 1: Write the failing guards**

**Edit:** `tests/test_pipeline_structure.py` (1/4)

Replace:

```text
import ast
import sys
```

With:

```text
import ast
import importlib
import sys
```

**Edit:** `tests/test_pipeline_structure.py` (2/4)

Replace:

```text
import pytest
from addon_loader import load_source
from mutation_support import running_under_mutmut
```

With:

```text
import pytest
from addon_loader import alias_package, load_source
from mutation_support import running_under_mutmut
```

**Edit:** `tests/test_pipeline_structure.py` (3/4)

Replace:

```text

def test_pipeline_package_keeps_only_stages_logging_and_registry():
	package = WORLDVOICE / "pipeline" / "__init__.py"
	assert top_level_names(package) & {*MOVED, *(f"_{name}" for name in MOVED)} == set()
```

With:

```text

# The modules pipeline/__init__.py was split into (phase 38): the stages, logging and registry.
STAGE_MODULES = [
	"registry",
	"sequence",
	"breaks",
	"items",
	"numberStages",
	"punctuation",
	"unspaced",
	"languageCommands",
]


@pytest.mark.parametrize("module", STAGE_MODULES)
def test_pipeline_package_keeps_only_stages_logging_and_registry(module):
	package = WORLDVOICE / "pipeline" / f"{module}.py"
	assert top_level_names(package) & {*MOVED, *(f"_{name}" for name in MOVED)} == set()
```

**Edit:** `tests/test_pipeline_structure.py` (4/4)

Replace:

```text

def test_speech_context_holds_only_plain_values():
```

With:

```text

def test_number_lexing_imports_by_its_package_path_without_nvda(monkeypatch):
	# The number rules claim to need only the standard library, and the tests load the file on its
	# own; an import by the package path runs pipeline/__init__.py first, which must stay empty for
	# that claim to hold there too (refactor8 A2).
	for name in [name for name in sys.modules if name.split(".")[0] == "synthDrivers"]:
		monkeypatch.delitem(sys.modules, name)
	# None in sys.modules makes an import of that name fail, even when another test left a stub
	# under that name: every NVDA module forbid_legacy_runtime_imports rejects, and the two the
	# stages import besides.
	for name in (
		"config",
		"speech",
		"synthDriverHandler",
		"logHandler",
		"languageHandler",
		"globalVars",
		"addonHandler",
		"gui",
		"nvwave",
		"winKernel",
		"api",
		"speechDictHandler",
		"characterProcessing",
	):
		monkeypatch.setitem(sys.modules, name, None)
	alias_package(monkeypatch, "synthDrivers")
	alias_package(monkeypatch, "synthDrivers.WorldVoice", WORLDVOICE)
	try:
		numbers = importlib.import_module("synthDrivers.WorldVoice.pipeline.numbers")
		loaded = sorted(name for name in sys.modules if name.split(".")[0] == "synthDrivers")
	finally:
		# The import registered these itself, so monkeypatch would leave them behind.
		for name in ("synthDrivers.WorldVoice.pipeline.numbers", "synthDrivers.WorldVoice.pipeline"):
			sys.modules.pop(name, None)
	assert Path(numbers.__file__) == WORLDVOICE / "pipeline/numbers.py"
	assert loaded == [
		"synthDrivers",
		"synthDrivers.WorldVoice",
		"synthDrivers.WorldVoice.pipeline",
		"synthDrivers.WorldVoice.pipeline.numbers",
	]


def test_speech_context_holds_only_plain_values():
```

**Edit:** `tests/test_runtime_import_guard.py` (1/1)

Replace:

```text

@pytest.mark.parametrize("package", ["bridge", "voices", "ui"])
def test_package_init_stays_empty(package):
	# Importing one module of the package must not load the others (spec phase 36, section 2);
	# ui/__init__.py runs before ui.panelLayout, which loads without wx (spec phase 37, 2.1).
	assert (WORLDVOICE / package / "__init__.py").read_bytes() == b""
```

With:

```text

@pytest.mark.parametrize("package", ["bridge", "voices", "ui", "pipeline"])
def test_package_init_stays_empty(package):
	# Importing one module of the package must not load the others (spec phase 36, section 2);
	# ui/__init__.py runs before ui.panelLayout, which loads without wx (spec phase 37, 2.1), and
	# pipeline/__init__.py before pipeline.numbers, which loads without NVDA (spec phase 38).
	assert (WORLDVOICE / package / "__init__.py").read_bytes() == b""
```

- [ ] **Step 2: Run them to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_structure.py tests/test_runtime_import_guard.py`
Expected: `10 failed, 11 passed` — the eight `test_pipeline_package_keeps_only_stages_logging_and_registry[<module>]` (`FileNotFoundError` for each new module), `test_number_lexing_imports_by_its_package_path_without_nvda` (the package `__init__.py` imports NVDA's `config`, which the guard made unimportable) and `test_package_init_stays_empty[pipeline]`.

- [ ] **Step 3: Split the package with the extraction script**

**File:** `$SCRATCH/split_pipeline.py` (not committed)

```python
"""Split addon/synthDrivers/WorldVoice/pipeline/__init__.py into its stage modules (phase 38, F1).

Usage: python3 -I split_pipeline.py <repository root>

Every top-level definition of the package moves verbatim, with the comment lines right above it,
into the module named in MODULES, in its original order; each module gets the fixed HEADERS text.
Definitions with no blank line between them stay one chunk. The package __init__.py is left empty.
The script refuses any input other than the file it was written for.
"""

import ast
import hashlib
import sys
from pathlib import Path

INPUT_SHA256 = "a1531e9639472559f4df37bee0ad84d581fe7ff97c2cbd566e3bacff22bb1e8b"

# The chunks that do not move as they are: the imports, the TYPE_CHECKING block, and the
# SpeechCmd/pl pair, which the headers of sequence.py and registry.py restate.
DROPPED = (
	"import re",
	"import uuid",
	"from collections.abc",
	"from dataclasses",
	"from functools",
	"from pathlib",
	"from typing",
	"import config",
	"import speechDictHandler",
	"from logHandler",
	"from speech.commands",
	"from speech.extensions",
	"from ..languageDetection.scripts",
	"from ..numberLanguage",
	"from ..runtime.models",
	"from ..speechCommands",
	"from . import speech_dictionary",
	"from .context",
	"from .numbers",
	"from .recorder",
	"from .settings",
	"from .symbols",
	"from .unspaced_common_data",
	"if TYPE_CHECKING:",
	'SpeechCmd = Union[str, "SpeechCommand"]',
)

MODULES = {
	"sequence": ["_MISSING", "_both_text"],
	"breaks": [
		"NumberBreakCommand",
		"NumberEdgeBreakCommand",
		"NumberItemEdgeBreakCommand",
		"_EDGE_MARKER",
		"_edge_kind",
		"_is_edge_break",
		"_is_item_edge_break",
		"PunctuationBreakCommand",
		"_merge_edge_breaks",
		"_merged_run",
		"_plain_breaks",
		"_plain_break",
	],
	"items": ["item_wait_factor", "_insert_item_breaks"],
	"numberStages": [
		"remove_thousands_separators",
		"_WORD_CHARACTER_RE",
		"_split_numbers_for_language",
		"_both_numbers",
		"_remove_space",
		"_split_numbers",
		"number_wait_factor",
		"_insert_number_breaks",
		"wrap_numbers_for_detection",
		"detect_with_number_language",
		"_translate_number",
		"inject_numbers",
		"_is_spoken",
		"_ends_utterance",
		"_spoken_later",
		"_inject_item_numbers",
		"_number_item_segments",
		"merge_consecutive_strings",
	],
	"punctuation": [
		"_split_by",
		"_PUNCTUATION_RE_CACHE",
		"_get_punctuation_regex",
		"_split_punctuation_segments",
		"inject_punctuation_pause",
		"_punctuation_pauses",
	],
	"unspaced": [
		"_WHITESPACE_RE",
		"UNSPACED_SCRIPTS",
		"_is_unspaced",
		"_pauses_between",
		"inject_unspaced_script_space_pause",
	],
	"languageCommands": [
		"remove_language_command",
		"deduplicate_language_command",
		"lang_cmd_to_voice",
		"inject_langchange_reorder",
	],
	"registry": [
		"listable",
		"speech_viewer",
		"apply_speech_dictionaries",
		"_LogWriter",
		"_log_writer",
		"_run_logged",
		"_stage_handler",
		"Stage",
		"STAGES",
		"_log_switches",
		"LOG_SWITCHES",
		"order_move_to_start_register",
		"register_stages",
		"unregister_stages",
	],
}

HEADERS = {
	"sequence": '''"""The items of a speech sequence as the stages see them, and the checks several stages share."""

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
	from speech.commands import SpeechCommand

SpeechCmd = Union[str, "SpeechCommand"]
''',
	"breaks": '''"""The pauses the stages add, how an edge break next to a number stays recognizable, and how
pauses that meet around one are merged."""

from collections.abc import Iterable, Iterator

from speech.commands import BreakCommand

from .sequence import SpeechCmd
''',
	"items": '''"""The item pause (item_wait_factor): a break between two text items."""

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

from speech.commands import BreakCommand

from .breaks import _is_item_edge_break, _merge_edge_breaks
from .context import SpeechContext
from .sequence import _MISSING, SpeechCmd, _both_text

if TYPE_CHECKING:
	from .settings import PipelineSettings
''',
	"numberStages": '''"""The number stages: the thousands step, number mode and number language (inject_numbers) and
the pause between numbers (number_wait_factor); and the number language for language detection."""

import re
from collections.abc import Callable, Iterable, Iterator
from typing import TYPE_CHECKING

from speech.commands import ConfigProfileTriggerCommand, EndUtteranceCommand, LangChangeCommand

from ..numberLanguage import FOLLOW, MAIN
from ..speechCommands import WVLangChangeCommand
from .breaks import NumberBreakCommand, NumberEdgeBreakCommand, NumberItemEdgeBreakCommand, _merge_edge_breaks
from .context import SpeechContext
from .languageCommands import deduplicate_language_command, remove_language_command
from .numbers import NUMBER_RE, number_pieces, split_spaced_numbers, strip_thousands
from .sequence import _MISSING, SpeechCmd, _both_text
from .symbols import symbol_namer

if TYPE_CHECKING:
	from .settings import PipelineSettings
''',
	"punctuation": '''"""The punctuation pause (punctuation_wait_factor): a break at each configured punctuation mark,
which the stage may also remove."""

import re
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Literal

from speech.commands import BreakCommand

from .breaks import NumberBreakCommand, PunctuationBreakCommand, _is_edge_break, _merge_edge_breaks
from .context import SpeechContext
from .sequence import SpeechCmd

if TYPE_CHECKING:
	from .settings import PipelineSettings
''',
	"unspaced": '''"""The space pause of unspaced scripts (unspaced_script_space_wait_factor): a space between two
characters of scripts written without spaces between words is a break."""

import re
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

from speech.commands import BreakCommand

from ..languageDetection.scripts import get_script
from .context import SpeechContext
from .sequence import SpeechCmd
from .unspaced_common_data import UNSPACED_COMMON

if TYPE_CHECKING:
	from .settings import PipelineSettings
''',
	"languageCommands": '''"""The language commands of a speech sequence: SynthDriver.speak reorders, deduplicates and turns
them into voices with these, and the number stage drops them for a synth without roles."""

from collections.abc import Iterable, Iterator

from speech.commands import LangChangeCommand

from ..runtime.models import SelectVoice
from ..speechCommands import WVLangChangeCommand
from .context import SpeechContext
from .sequence import SpeechCmd
''',
	"registry": '''"""The stage table: the filter stages in NVDA's order, each run with the settings and context of the
synth that speaks and logged on request, and registered with NVDA's filter_speechSequence as one set.

Here too are the two stages too small for a module of their own (apply_speech_dictionaries and
speech_viewer), and listable, with which the synth makes language detection a filter.
"""

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING

import config
import speechDictHandler
from logHandler import log
from speech.extensions import filter_speechSequence

from . import speech_dictionary
from .breaks import _plain_breaks
from .context import SpeechContext, current_context
from .items import item_wait_factor
from .numberStages import inject_numbers, number_wait_factor, remove_thousands_separators
from .punctuation import inject_punctuation_pause
from .recorder import PipelineLog
from .sequence import SpeechCmd
from .settings import pipeline_settings, read_stored
from .unspaced import inject_unspaced_script_space_pause

if TYPE_CHECKING:
	from .settings import PipelineSettings

# The pipeline log is addon/log/pipeline.csv; parents[3] of a module in pipeline/ is addon/.
pl = PipelineLog(Path(__file__).resolve().parents[3] / "log" / "pipeline.csv")
''',
}


def chunks(source):
	"""(first line of the chunk, names it defines, text) for each top-level chunk of *source*."""
	lines = source.splitlines(keepends=True)
	spans = []
	for node in ast.parse(source).body:
		start = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
		while start > 1 and lines[start - 2].startswith("#"):
			start -= 1
		if isinstance(node, ast.FunctionDef | ast.ClassDef):
			names = [node.name]
		elif isinstance(node, ast.Assign):
			names = [target.id for target in node.targets]
		elif isinstance(node, ast.AnnAssign):
			names = [node.target.id]
		else:
			names = []
		if spans and start == spans[-1][1] + 1:
			# No blank line between the two: one chunk.
			spans[-1] = (spans[-1][0], node.end_lineno, spans[-1][2] + names)
		else:
			spans.append((start, node.end_lineno, names))
	return [(names, "".join(lines[start - 1 : end])) for start, end, names in spans]


def main(root):
	package = root / "addon/synthDrivers/WorldVoice/pipeline"
	init = package / "__init__.py"
	source = init.read_text(encoding="utf-8")
	if hashlib.sha256(source.encode("utf-8")).hexdigest() != INPUT_SHA256:
		sys.exit(f"{init} is not the file this script splits")
	by_first_name = {}
	for names, text in chunks(source):
		if any(text.startswith(prefix) for prefix in DROPPED):
			continue
		by_first_name[names[0]] = text
	placed = [name for module in MODULES.values() for name in module]
	if sorted(placed) != sorted(by_first_name) or len(set(placed)) != len(placed):
		sys.exit(f"chunks left over or missing: {set(by_first_name) ^ set(placed)}")
	for module, names in MODULES.items():
		body = "\n\n\n".join(by_first_name[name].rstrip("\n") for name in names)
		text = HEADERS[module].rstrip("\n") + "\n\n\n" + body + "\n"
		(package / f"{module}.py").write_text(text, encoding="utf-8", newline="\n")
	init.write_bytes(b"")


if __name__ == "__main__":
	main(Path(sys.argv[1]))
```

```bash
python3 -I "$SCRATCH/split_pipeline.py" "$PWD"
wc -c addon/synthDrivers/WorldVoice/pipeline/__init__.py   # 0
```

The script exits with a message, and writes nothing, if `pipeline/__init__.py` is not the file Tasks 1–2 leave (its SHA-256) or if a top-level chunk is unplaced or placed twice.

- [ ] **Step 4: Import from the owning modules**

ruff's isort wraps the `languageCommands` import (it is longer than 110 columns on one line) and orders `pipeline.registry` after `pipeline.context`, and `.registry` before `.settings`.

**Edit:** `addon/synthDrivers/WorldVoice/__init__.py` (1/1)

Replace:

```text
from .numberLanguage import FOLLOW, MAIN
from .pipeline import (
	LOG_SWITCHES,
	deduplicate_language_command,
	detect_with_number_language,
	inject_langchange_reorder,
	lang_cmd_to_voice,
	listable,
	order_move_to_start_register,
)
from .pipeline.context import GENERIC_CONTEXT, SpeechContext
from .pipeline.scope import pipeline_scope
```

With:

```text
from .numberLanguage import FOLLOW, MAIN
from .pipeline.context import GENERIC_CONTEXT, SpeechContext
from .pipeline.languageCommands import (
	deduplicate_language_command,
	inject_langchange_reorder,
	lang_cmd_to_voice,
)
from .pipeline.numberStages import detect_with_number_language
from .pipeline.registry import LOG_SWITCHES, listable, order_move_to_start_register
from .pipeline.scope import pipeline_scope
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/scope.py` (1/1)

Replace:

```text

from . import register_stages, unregister_stages
from .settings import PipelineSettings, PipelineSettingsService, pipeline_settings
```

With:

```text

from .registry import register_stages, unregister_stages
from .settings import PipelineSettings, PipelineSettingsService, pipeline_settings
```

**Edit:** `addon/globalPlugins/WorldVoice/pipelineLog.py` (1/1)

Replace:

```text
from logHandler import log
from synthDrivers.WorldVoice.pipeline import pl
from synthDrivers.WorldVoice.pipeline.settings import read_stored
```

With:

```text
from logHandler import log
from synthDrivers.WorldVoice.pipeline.registry import pl
from synthDrivers.WorldVoice.pipeline.settings import read_stored
```

**Edit:** `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (1/1)

Replace:

```text
from synthDrivers.WorldVoice.languageDetection.settings import detection_settings
from synthDrivers.WorldVoice.pipeline import LOG_SWITCHES
from synthDrivers.WorldVoice.pipeline.context import worldvoice_synth
from synthDrivers.WorldVoice.pipeline.settings import PIPELINE_SETTINGS, pipeline_settings, read_stored
```

With:

```text
from synthDrivers.WorldVoice.languageDetection.settings import detection_settings
from synthDrivers.WorldVoice.pipeline.context import worldvoice_synth
from synthDrivers.WorldVoice.pipeline.registry import LOG_SWITCHES
from synthDrivers.WorldVoice.pipeline.settings import PIPELINE_SETTINGS, pipeline_settings, read_stored
```

**Edit:** `pyproject.toml` (1/1)

Replace:

```text
	"addon/synthDrivers/WorldVoice/voices/mainLocalePolicy.py",
	"addon/synthDrivers/WorldVoice/pipeline/__init__.py",
	"addon/synthDrivers/WorldVoice/pipeline/numbers.py",
```

With:

```text
	"addon/synthDrivers/WorldVoice/voices/mainLocalePolicy.py",
	"addon/synthDrivers/WorldVoice/pipeline/registry.py",
	"addon/synthDrivers/WorldVoice/pipeline/breaks.py",
	"addon/synthDrivers/WorldVoice/pipeline/sequence.py",
	"addon/synthDrivers/WorldVoice/pipeline/items.py",
	"addon/synthDrivers/WorldVoice/pipeline/numberStages.py",
	"addon/synthDrivers/WorldVoice/pipeline/punctuation.py",
	"addon/synthDrivers/WorldVoice/pipeline/unspaced.py",
	"addon/synthDrivers/WorldVoice/pipeline/languageCommands.py",
	"addon/synthDrivers/WorldVoice/pipeline/numbers.py",
```

- [ ] **Step 5: Read the pipeline through `PipelineModules` and patch where the names are looked up**

Every patch of `current_context`, `pl`, `log`, `pipeline_settings`, `filter_speechSequence` and `read_stored` names `module.registry` (spec §5.5); assertions are unchanged.

**Edit:** `tests/pipeline_harness.py` (1/4)

Replace:

```text
import builtins
import sys
```

With:

```text
import builtins
import importlib
import sys
```

**Edit:** `tests/pipeline_harness.py` (2/4)

Replace:

```text

def load_pipeline_module(monkeypatch, settings):
```

With:

```text

# The pipeline's modules, in the order PipelineModules looks a name up in.
PIPELINE_MODULES = (
	"registry",
	"sequence",
	"breaks",
	"items",
	"numberStages",
	"punctuation",
	"unspaced",
	"languageCommands",
	"context",
	"settings",
	"numbers",
	"symbols",
	"speech_dictionary",
	"unspaced_common_data",
)


class PipelineModules:
	"""The pipeline's modules read as one namespace by the tests; pipeline/__init__.py is empty.

	module.<name of a module in PIPELINE_MODULES> is that module; any other name comes from the
	first module there that defines or imports it. A patch goes to the module that looks the name
	up, as module.registry for the stage handler's current_context, pipeline_settings, pl, log and
	filter_speechSequence: setting an attribute here raises, so a patch can never silently miss.
	"""

	def __init__(self, test_settings):
		modules = {name: sys.modules[f"synthDrivers.WorldVoice.pipeline.{name}"] for name in PIPELINE_MODULES}
		object.__setattr__(self, "_modules", modules)
		object.__setattr__(self, "_test_settings", test_settings)

	def __getattr__(self, name):
		if name in self._modules:
			return self._modules[name]
		for module in self._modules.values():
			if name in vars(module):
				return vars(module)[name]
		raise AttributeError(name)

	def __setattr__(self, name, value):
		raise AttributeError(f"patch {name} on the pipeline module that looks it up, as module.registry")


def load_pipeline_module(monkeypatch, settings):
```

**Edit:** `tests/pipeline_harness.py` (3/4)

Replace:

```text
		"synthDrivers.WorldVoice.pipeline",
		"synthDrivers.WorldVoice.pipeline.recorder",
```

With:

```text
		"synthDrivers.WorldVoice.pipeline",
		"synthDrivers.WorldVoice.pipeline.registry",
		"synthDrivers.WorldVoice.pipeline.sequence",
		"synthDrivers.WorldVoice.pipeline.breaks",
		"synthDrivers.WorldVoice.pipeline.items",
		"synthDrivers.WorldVoice.pipeline.numberStages",
		"synthDrivers.WorldVoice.pipeline.punctuation",
		"synthDrivers.WorldVoice.pipeline.unspaced",
		"synthDrivers.WorldVoice.pipeline.languageCommands",
		"synthDrivers.WorldVoice.pipeline.recorder",
```

**Edit:** `tests/pipeline_harness.py` (4/4)

Replace:

```text

	module = load_source(monkeypatch, "synthDrivers.WorldVoice.pipeline", WORLDVOICE / "pipeline/__init__.py")
	module._test_settings = settings
	return module, BreakCommand

```

With:

```text

	load_source(monkeypatch, "synthDrivers.WorldVoice.pipeline", WORLDVOICE / "pipeline/__init__.py")
	# The stage table imports every stage module.
	importlib.import_module("synthDrivers.WorldVoice.pipeline.registry")
	return PipelineModules(settings), BreakCommand

```

**Edit:** `tests/test_pipeline_stages.py` (1/15)

Replace:

```text
		"number_mode": True,
	}
	writes = []
	monkeypatch.setattr(module, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["12,345"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
```

With:

```text
		"number_mode": True,
	}
	writes = []
	monkeypatch.setattr(module.registry, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["12,345"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
```

**Edit:** `tests/test_pipeline_stages.py` (2/15)

Replace:

```text
		**dict.fromkeys(on, True),
	}
	writes = []
	monkeypatch.setattr(module, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage(
		"number_mode",
		lambda sequence, s, ctx: list(sequence),
```

With:

```text
		**dict.fromkeys(on, True),
	}
	writes = []
	monkeypatch.setattr(module.registry, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage(
		"number_mode",
		lambda sequence, s, ctx: list(sequence),
```

**Edit:** `tests/test_pipeline_stages.py` (3/15)

Replace:

```text
		**dict.fromkeys(on, True),
	}
	writes = []
	monkeypatch.setattr(module, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["12,345"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
```

With:

```text
		**dict.fromkeys(on, True),
	}
	writes = []
	monkeypatch.setattr(module.registry, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["12,345"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
```

**Edit:** `tests/test_pipeline_stages.py` (4/15)

Replace:

```text
	fake = OrderedFilter()
	other = lambda sequence: sequence
	fake.register(other)
	monkeypatch.setattr(module, "filter_speechSequence", fake)
	installs = []
	monkeypatch.setattr(module.speech_dictionary, "install", lambda: installs.append("install"))
	monkeypatch.setattr(module.speech_dictionary, "uninstall", lambda: installs.append("uninstall"))
```

With:

```text
	fake = OrderedFilter()
	other = lambda sequence: sequence
	fake.register(other)
	monkeypatch.setattr(module.registry, "filter_speechSequence", fake)
	installs = []
	monkeypatch.setattr(module.speech_dictionary, "install", lambda: installs.append("install"))
	monkeypatch.setattr(module.speech_dictionary, "uninstall", lambda: installs.append("uninstall"))
```

**Edit:** `tests/test_pipeline_stages.py` (5/15)

Replace:

```text
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	seen = []
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: seen.append((s, ctx)) or list(sequence))
	assert stage.handler(["a"]) == ["a"]
	assert seen == [(settings, module.GENERIC_CONTEXT)]
```

With:

```text
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	seen = []
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: seen.append((s, ctx)) or list(sequence))
	assert stage.handler(["a"]) == ["a"]
	assert seen == [(settings, module.GENERIC_CONTEXT)]
```

**Edit:** `tests/test_pipeline_stages.py` (6/15)

Replace:

```text
	module, _ = load_pipeline_module(monkeypatch, settings)
	asked = []
	monkeypatch.setattr(
		module,
		"pipeline_settings",
		SimpleNamespace(effective=lambda roles: asked.append(roles) or settings),
	)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: list(sequence))
	roles = module.SpeechContext(supports_roles=True, language="en", number_language="default")
	for ctx in [module.GENERIC_CONTEXT, roles]:
		monkeypatch.setattr(module, "current_context", lambda ctx=ctx: ctx)
		stage.handler(["a"])
	assert asked == [False, True]

```

With:

```text
	module, _ = load_pipeline_module(monkeypatch, settings)
	asked = []
	monkeypatch.setattr(
		module.registry,
		"pipeline_settings",
		SimpleNamespace(effective=lambda roles: asked.append(roles) or settings),
	)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: list(sequence))
	roles = module.SpeechContext(supports_roles=True, language="en", number_language="default")
	for ctx in [module.GENERIC_CONTEXT, roles]:
		monkeypatch.setattr(module.registry, "current_context", lambda ctx=ctx: ctx)
		stage.handler(["a"])
	assert asked == [False, True]

```

**Edit:** `tests/test_pipeline_stages.py` (7/15)

Replace:

```text
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	sys.modules["config"].conf["WorldVoice"]["log"] = {"enable": True, "speech_viewer": True}
	writes = []
	monkeypatch.setattr(module, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: [item.upper() for item in sequence])
	assert stage.handler(["a"]) == ["A"]
	assert writes == [("speech_viewer", "before"), ("speech_viewer", "after")]
```

With:

```text
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	sys.modules["config"].conf["WorldVoice"]["log"] = {"enable": True, "speech_viewer": True}
	writes = []
	monkeypatch.setattr(module.registry, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: [item.upper() for item in sequence])
	assert stage.handler(["a"]) == ["A"]
	assert writes == [("speech_viewer", "before"), ("speech_viewer", "after")]
```

**Edit:** `tests/test_pipeline_stages.py` (8/15)

Replace:

```text
			raise failing[0]

	errors = []
	monkeypatch.setattr(module, "pl", SimpleNamespace(write=write))
	monkeypatch.setattr(module, "log", SimpleNamespace(error=lambda *a, **k: errors.append(a), debug=print))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: [item.upper() for item in sequence])
	assert stage.handler(iter(["a"])) == ["A"]
	assert stage.handler(iter(["b"])) == ["B"]
```

With:

```text
			raise failing[0]

	errors = []
	monkeypatch.setattr(module.registry, "pl", SimpleNamespace(write=write))
	monkeypatch.setattr(
		module.registry,
		"log",
		SimpleNamespace(error=lambda *a, **k: errors.append(a), debug=print),
	)
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: [item.upper() for item in sequence])
	assert stage.handler(iter(["a"])) == ["A"]
	assert stage.handler(iter(["b"])) == ["B"]
```

**Edit:** `tests/test_pipeline_stages.py` (9/15)

Replace:

```text
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E"}.get,
	)
	monkeypatch.setattr(module, "current_context", lambda: ctx)
	sequence = ["1 2"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
```

With:

```text
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E"}.get,
	)
	monkeypatch.setattr(module.registry, "current_context", lambda: ctx)
	sequence = ["1 2"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
```

**Edit:** `tests/test_pipeline_stages.py` (10/15)

Replace:

```text
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E"}.get,
	)
	monkeypatch.setattr(module, "current_context", lambda: ctx)
	sequence = ["12,345,678"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
```

With:

```text
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E"}.get,
	)
	monkeypatch.setattr(module.registry, "current_context", lambda: ctx)
	sequence = ["12,345,678"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
```

**Edit:** `tests/test_pipeline_stages.py` (11/15)

Replace:

```text
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E"}.get,
	)
	monkeypatch.setattr(module, "current_context", lambda: ctx)
	sequence = [f"10{space}000"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
```

With:

```text
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E"}.get,
	)
	monkeypatch.setattr(module.registry, "current_context", lambda: ctx)
	sequence = [f"10{space}000"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
```

**Edit:** `tests/test_pipeline_stages.py` (12/15)

Replace:

```text
		voice_name_for_language=lambda language: "Z",
		voice_locale_for_language=lambda language: "zh_TW",
	)
	monkeypatch.setattr(module, "current_context", lambda: ctx)
	sequence = ["2\u00d73"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
```

With:

```text
		voice_name_for_language=lambda language: "Z",
		voice_locale_for_language=lambda language: "zh_TW",
	)
	monkeypatch.setattr(module.registry, "current_context", lambda: ctx)
	sequence = ["2\u00d73"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
```

**Edit:** `tests/test_pipeline_stages.py` (13/15)

Replace:

```text
)
def test_other_synths_get_only_plain_breaks_from_the_stages(monkeypatch, number_mode, expected):
	module, _ = load_pipeline_module(monkeypatch, pause_settings(number_mode))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	assert break_types(run_stages(module, ["共 12 34 個. 5678 and 3"])) == expected


```

With:

```text
)
def test_other_synths_get_only_plain_breaks_from_the_stages(monkeypatch, number_mode, expected):
	module, _ = load_pipeline_module(monkeypatch, pause_settings(number_mode))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	assert break_types(run_stages(module, ["共 12 34 個. 5678 and 3"])) == expected


```

**Edit:** `tests/test_pipeline_stages.py` (14/15)

Replace:

```text
def test_worldvoice_keeps_the_break_subclasses_from_the_stages(monkeypatch, number_mode, expected):
	module, _ = load_pipeline_module(monkeypatch, pause_settings(number_mode))
	ctx = module.SpeechContext(supports_roles=True, language="zh", number_language="default")
	monkeypatch.setattr(module, "current_context", lambda: ctx)
	assert break_types(run_stages(module, ["共 12 34 個. 5678 and 3"])) == expected


```

With:

```text
def test_worldvoice_keeps_the_break_subclasses_from_the_stages(monkeypatch, number_mode, expected):
	module, _ = load_pipeline_module(monkeypatch, pause_settings(number_mode))
	ctx = module.SpeechContext(supports_roles=True, language="zh", number_language="default")
	monkeypatch.setattr(module.registry, "current_context", lambda: ctx)
	assert break_types(run_stages(module, ["共 12 34 個. 5678 and 3"])) == expected


```

**Edit:** `tests/test_pipeline_stages.py` (15/15)

Replace:

```text
	settings = punctuation_settings(50, remove_characters=remove)
	settings.punctuation_pause_characters = "。，."
	module, _ = load_pipeline_module(monkeypatch, settings)
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	commands = {"E": module.NumberEdgeBreakCommand(10), "NB": module.NumberBreakCommand(10)}
	plain = module._plain_breaks([commands.get(item, item) for item in sequence])
	(stage,) = [stage for stage in module.STAGES if stage.log_key == "punctuation_wait_factor"]
```

With:

```text
	settings = punctuation_settings(50, remove_characters=remove)
	settings.punctuation_pause_characters = "。，."
	module, _ = load_pipeline_module(monkeypatch, settings)
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	commands = {"E": module.NumberEdgeBreakCommand(10), "NB": module.NumberBreakCommand(10)}
	plain = module._plain_breaks([commands.get(item, item) for item in sequence])
	(stage,) = [stage for stage in module.STAGES if stage.log_key == "punctuation_wait_factor"]
```

**Edit:** `tests/test_pipeline_filters.py` (1/3)

Replace:

```text
	context = roles_context(env.module, "zh_TW", "default") if roles else env.module.GENERIC_CONTEXT
	monkeypatch.setattr(env.module, "current_context", lambda: context)
	sequence = ["12.5"]
```

With:

```text
	context = roles_context(env.module, "zh_TW", "default") if roles else env.module.GENERIC_CONTEXT
	monkeypatch.setattr(env.module.registry, "current_context", lambda: context)
	sequence = ["12.5"]
```

**Edit:** `tests/test_pipeline_filters.py` (2/3)

Replace:

```text
	monkeypatch.setattr(
		env.module,
		"pl",
```

With:

```text
	monkeypatch.setattr(
		env.module.registry,
		"pl",
```

**Edit:** `tests/test_pipeline_filters.py` (3/3)

Replace:

```text
	settings_module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	monkeypatch.setattr(env.module, "read_stored", settings_module.read_stored)
	error = sys.modules["configobj.validate"].VdtTypeError("maybe")
```

With:

```text
	settings_module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	monkeypatch.setattr(env.module.registry, "read_stored", settings_module.read_stored)
	error = sys.modules["configobj.validate"].VdtTypeError("maybe")
```

**Edit:** `tests/test_pipeline_nvda_ssml.py` (1/3)

Replace:

```text
	module, _ = load_pipeline_module(monkeypatch, pause_settings(number_mode))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = [TEXT]
```

With:

```text
	module, _ = load_pipeline_module(monkeypatch, pause_settings(number_mode))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = [TEXT]
```

**Edit:** `tests/test_pipeline_nvda_ssml.py` (2/3)

Replace:

```text
	module, _ = load_pipeline_module(monkeypatch, pause_settings("group"))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["12.5"]
```

With:

```text
	module, _ = load_pipeline_module(monkeypatch, pause_settings("group"))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["12.5"]
```

**Edit:** `tests/test_pipeline_nvda_ssml.py` (3/3)

Replace:

```text
	module, _ = load_pipeline_module(monkeypatch, pause_settings("number"))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["第3章"]
```

With:

```text
	module, _ = load_pipeline_module(monkeypatch, pause_settings("number"))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["第3章"]
```

**Edit:** `tests/test_pipeline_number_edges.py` (1/2)

Replace:

```text
def shape(sequence):
	module = sys.modules["synthDrivers.WorldVoice.pipeline"]
	BreakCommand = sys.modules["speech.commands"].BreakCommand
```

With:

```text
def shape(sequence):
	module = sys.modules["synthDrivers.WorldVoice.pipeline.breaks"]
	BreakCommand = sys.modules["speech.commands"].BreakCommand
```

**Edit:** `tests/test_pipeline_number_edges.py` (2/2)

Replace:

```text
	ctx = ctx_of(module)
	monkeypatch.setattr(module, "current_context", lambda: ctx)
	sequence = list(sequence(module)) if callable(sequence) else list(sequence)
```

With:

```text
	ctx = ctx_of(module)
	monkeypatch.setattr(module.registry, "current_context", lambda: ctx)
	sequence = list(sequence(module)) if callable(sequence) else list(sequence)
```

**Edit:** `tests/test_settings_panels.py` (1/1)

Replace:

```text
	env.conf["WorldVoice"]["log"] = section
	monkeypatch.setattr(sys.modules["synthDrivers.WorldVoice.pipeline"], "pl", None, raising=False)
	service_module = load_source(
```

With:

```text
	env.conf["WorldVoice"]["log"] = section
	monkeypatch.setattr(sys.modules["synthDrivers.WorldVoice.pipeline.registry"], "pl", None, raising=False)
	service_module = load_source(
```

- [ ] **Step 6: Follow the modules by name in the other harnesses and tests**

**Edit:** `tests/nvda_stubs.py` (1/1)

Replace:

```text
		# and one per key of a stage's also_logged_by.
		stages = _top_level_value(WORLDVOICE / "pipeline/__init__.py", "STAGES")
		value = _value_default(node.value)
```

With:

```text
		# and one per key of a stage's also_logged_by.
		stages = _top_level_value(WORLDVOICE / "pipeline/registry.py", "STAGES")
		value = _value_default(node.value)
```

**Edit:** `tests/ui_harness.py` (1/1)

Replace:

```text
	)
	stubs.module("synthDrivers.WorldVoice.pipeline").LOG_SWITCHES = tuple(LOG_SWITCH_ORDER)
	load_source(monkeypatch, "synthDrivers.WorldVoice.pipeline.context", WORLDVOICE / "pipeline/context.py")
```

With:

```text
	)
	stubs.module("synthDrivers.WorldVoice.pipeline.registry").LOG_SWITCHES = tuple(LOG_SWITCH_ORDER)
	load_source(monkeypatch, "synthDrivers.WorldVoice.pipeline.context", WORLDVOICE / "pipeline/context.py")
```

**Edit:** `tests/test_pipeline_log.py` (1/1)

Replace:

```text
		"synthDrivers.WorldVoice": types.SimpleNamespace(__path__=[]),
		"synthDrivers.WorldVoice.pipeline": types.SimpleNamespace(
			pl=types.SimpleNamespace(move_to=lambda dst: asked.append(("moved", dst))),
```

With:

```text
		"synthDrivers.WorldVoice": types.SimpleNamespace(__path__=[]),
		"synthDrivers.WorldVoice.pipeline": types.SimpleNamespace(__path__=[]),
		"synthDrivers.WorldVoice.pipeline.registry": types.SimpleNamespace(
			pl=types.SimpleNamespace(move_to=lambda dst: asked.append(("moved", dst))),
```

**Edit:** `tests/test_runtime_composition.py` (1/1)

Replace:

```text
	stub(package + ".languageDetection.settings", DETECTION_CONFSPEC={}, detection_settings=SimpleNamespace())
	stub(
		package + ".pipeline",
		LOG_SWITCHES=(),
		**{
			name: lambda *args: None
			for name in (
				"inject_langchange_reorder",
				"deduplicate_language_command",
				"detect_with_number_language",
				"lang_cmd_to_voice",
				"order_move_to_start_register",
				"listable",
			)
		},
	)
	stub(
```

With:

```text
	stub(package + ".languageDetection.settings", DETECTION_CONFSPEC={}, detection_settings=SimpleNamespace())
	stub(package + ".pipeline", __path__=[])
	stub(
		package + ".pipeline.languageCommands",
		**{
			name: lambda *args: None
			for name in ("inject_langchange_reorder", "deduplicate_language_command", "lang_cmd_to_voice")
		},
	)
	stub(package + ".pipeline.numberStages", detect_with_number_language=lambda *args: None)
	stub(
		package + ".pipeline.registry",
		LOG_SWITCHES=(),
		**{name: lambda *args: None for name in ("order_move_to_start_register", "listable")},
	)
	stub(
```

**Edit:** `tests/test_pipeline_scope.py` (1/1)

Replace:

```text
def load_scope_module(monkeypatch):
	package = alias_package(monkeypatch, "scope_pkg")
	package.register_stages = lambda: None
	package.unregister_stages = lambda: None
	settings = ModuleType("scope_pkg.settings")
```

With:

```text
def load_scope_module(monkeypatch):
	alias_package(monkeypatch, "scope_pkg")
	registry = ModuleType("scope_pkg.registry")
	registry.register_stages = lambda: None
	registry.unregister_stages = lambda: None
	monkeypatch.setitem(sys.modules, "scope_pkg.registry", registry)
	settings = ModuleType("scope_pkg.settings")
```

**Edit:** `tests/test_worldvoice_speak.py` (1/2)

Replace:

```text
	return SimpleNamespace(
		pipeline=load("pipeline"),
		settings=load("pipeline.settings"),
```

With:

```text
	return SimpleNamespace(
		pipeline=load("pipeline.registry"),
		language_commands=load("pipeline.languageCommands"),
		number_stages=load("pipeline.numberStages"),
		settings=load("pipeline.settings"),
```

**Edit:** `tests/test_worldvoice_speak.py` (2/2)

Replace:

```text
		"synthDoneSpeaking": object(),
		"inject_langchange_reorder": pipeline.inject_langchange_reorder,
		"deduplicate_language_command": pipeline.deduplicate_language_command,
		"lang_cmd_to_voice": pipeline.lang_cmd_to_voice,
		"detect_with_number_language": pipeline.detect_with_number_language,
		"queue_speech_sequence": modules.builder.queue_speech_sequence,
```

With:

```text
		"synthDoneSpeaking": object(),
		"inject_langchange_reorder": modules.language_commands.inject_langchange_reorder,
		"deduplicate_language_command": modules.language_commands.deduplicate_language_command,
		"lang_cmd_to_voice": modules.language_commands.lang_cmd_to_voice,
		"detect_with_number_language": modules.number_stages.detect_with_number_language,
		"queue_speech_sequence": modules.builder.queue_speech_sequence,
```

- [ ] **Step 7: Run the tests to see green, and check that every patch is read**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_structure.py tests/test_runtime_import_guard.py`
Expected: `21 passed`.

Run: `python3 -m pytest -q -p no:cacheprovider tests` → `3236 passed`, 0 skipped.

Probe (not committed): every value patched onto a `*.pipeline.registry` module is wrapped so that a call or an attribute read marks it used.

**File:** `$SCRATCH/probe/probe_patches.py` (not committed)

```python
"""pytest plugin: prove that every patch on pipeline.registry is read by the code under test.

Each value patched onto a module named *.pipeline.registry is wrapped so that a call (for a
function) or an attribute read (for an object) marks it as used; after each test, the patches
that were never used are appended to $PROBE_REPORT.
"""

import os
import types

import pytest

_patches = []


class _Used:
	def __init__(self, label):
		self.label = label
		self.used = False


def _wrap(value, used):
	if isinstance(value, types.FunctionType):

		def wrapper(*args, **kwargs):
			used.used = True
			return value(*args, **kwargs)

		return wrapper

	class Proxy:
		def __getattr__(self, name):
			used.used = True
			return getattr(value, name)

	return Proxy()


_original = pytest.MonkeyPatch.setattr


def setattr(self, target, name, value=None, raising=True):  # noqa: A001
	module_name = getattr(target, "__name__", "")
	if isinstance(target, types.ModuleType) and module_name.endswith(".pipeline.registry") and value is not None:
		used = _Used(f"{module_name}.{name}")
		_patches.append(used)
		value = _wrap(value, used)
	return _original(self, target, name, value, raising)


pytest.MonkeyPatch.setattr = setattr


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
	_patches.clear()
	yield
	with open(os.environ["PROBE_REPORT"], "a", encoding="utf-8") as report:
		for used in _patches:
			report.write(f"{'USED' if used.used else 'UNUSED'} {item.nodeid} {used.label}\n")
```

```bash
rm -f "$SCRATCH/probe/report.txt"
PROBE_REPORT="$SCRATCH/probe/report.txt" PYTHONPATH="$SCRATCH/probe" python3 -m pytest -q -p no:cacheprovider -p probe_patches tests/test_pipeline_stages.py tests/test_pipeline_filters.py tests/test_pipeline_nvda_ssml.py tests/test_pipeline_number_edges.py tests/test_settings_panels.py
awk '{print $1}' "$SCRATCH/probe/report.txt" | sort | uniq -c
grep UNUSED "$SCRATCH/probe/report.txt"
```

Expected: `57 USED`, `4 UNUSED`; the four unused are all `pl`, in exactly the parametrizations whose test asserts that nothing is written (`test_a_stage_logs_under_each_of_its_switches[none]`, `test_run_logged_records_only_when_switched_on[INFO-False-True-writes0]`, `[INFO-True-False-writes1]`, `[DEBUG-False-True-writes3]`); every other parametrization of those tests reads its `pl`.

- [ ] **Step 8: Commit**

```bash
W=addon/synthDrivers/WorldVoice
git add $W/pipeline/__init__.py $W/pipeline/sequence.py $W/pipeline/breaks.py $W/pipeline/items.py $W/pipeline/numberStages.py $W/pipeline/punctuation.py $W/pipeline/unspaced.py $W/pipeline/languageCommands.py $W/pipeline/registry.py $W/pipeline/scope.py $W/__init__.py addon/globalPlugins/WorldVoice/pipelineLog.py addon/globalPlugins/WorldVoice/speechSettingsDialog.py pyproject.toml tests/pipeline_harness.py tests/test_pipeline_stages.py tests/test_pipeline_filters.py tests/test_pipeline_nvda_ssml.py tests/test_pipeline_number_edges.py tests/test_settings_panels.py tests/nvda_stubs.py tests/ui_harness.py tests/test_pipeline_log.py tests/test_runtime_composition.py tests/test_pipeline_scope.py tests/test_worldvoice_speak.py tests/test_pipeline_structure.py tests/test_runtime_import_guard.py
git diff --cached --stat   # 28 files: 8 new, 20 modified
git commit -q -F - <<'EOF'
refactor: split pipeline/__init__.py into its stage modules

The package entry point held every stage, the break commands, the
language-command helpers SynthDriver.speak calls, the log writer and the
stage table, 1125 lines in one file, and importing pipeline.numbers ran
all of it with NVDA's config and speech modules. Each definition now
moves verbatim, in order, into sequence, breaks, items, numberStages,
punctuation, unspaced, languageCommands or registry, and __init__.py is
empty like bridge/, voices/ and ui/; importers name the owning module.

The tests read the modules through a view that refuses attribute writes,
and every patch now names pipeline.registry, where the stage handler
looks the names up. A guard imports pipeline.numbers by its package path
without NVDA.
EOF
git rev-parse HEAD:addon HEAD:tests
```

Expected after the commit: `HEAD:addon` = `eb87b28e2eee4ec6c4a3c03249b182e3a6d3f05d`, `HEAD:tests` = `9542603a6c29a74efab7d0211af3ae08d49dfcee`

---

### Task 4: Full verification (DEVELOPMENT_WORKFLOW.md §7)

**Files:** none.

**Interfaces:**
- Consumes: Task 3's tree.
- Produces: the verification record of the hand-off.

- [ ] **Step 1: Run every check**

```bash
python3 -m pytest -q -p no:cacheprovider tests     # 3236 passed, 0 skipped
prek run --all-files                               # every hook Passed
git diff --check 9f77382                           # no output
git diff --stat 9f77382 -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py addon/synthDrivers/WorldVoice/pipeline/unspaced_common_data.py   # no output
git ls-files addon/synthDrivers/WorldVoice/driver/Neural   # no output
git diff 9f77382 -- tests/test_plugin_voice_contract.py   # no output
git grep -n "WorldVoice/log\.py\|WorldVoice\.log\b\|WorldVoice\.sayAll\|from \.\.log import\|pipeline import\|pipeline/__init__\.py" -- addon tests pyproject.toml   # only the five lines below
git diff -M --stat 9f77382 -- addon/synthDrivers/WorldVoice/log.py addon/synthDrivers/WorldVoice/sayAll.py addon/synthDrivers/WorldVoice/pipeline/recorder.py addon/synthDrivers/WorldVoice/pipeline/sayAll.py
```

Expected `git grep` output — comments that name the empty file, and the harness's load of it:

```text
tests/pipeline_harness.py:66:	"""The pipeline's modules read as one namespace by the tests; pipeline/__init__.py is empty.
tests/pipeline_harness.py:212:	load_source(monkeypatch, "synthDrivers.WorldVoice.pipeline", WORLDVOICE / "pipeline/__init__.py")
tests/test_pipeline_structure.py:103:# The modules pipeline/__init__.py was split into (phase 38): the stages, logging and registry.
tests/test_pipeline_structure.py:143:	# own; an import by the package path runs pipeline/__init__.py first, which must stay empty for
tests/test_runtime_import_guard.py:59:	# pipeline/__init__.py before pipeline.numbers, which loads without NVDA (spec phase 38).
```

The last command shows `log.py => pipeline/recorder.py` and `{ => pipeline}/sayAll.py` as renames. `git diff --color-moved=dimmed-zebra HEAD~1 HEAD -- addon/synthDrivers/WorldVoice/pipeline/` shows the split as moved lines apart from the eight module headers.

---

## Dry run record

2026-10-26, fresh clone of `/workspace/WorldVoice` at `9f77382` in the scratchpad (`ref` symlinked, `prek install`), every step applied from this plan's text by a script that runs the step's bash blocks, writes its `File:` blocks and applies its `Edit:` blocks by exact replacement in document order; pytest under a MemAvailable < 3 GB guard:

| Commit | Files | Focused run | Full suite | Tree ids |
| --- | --- | --- | --- | --- |
| Task 1 | 5 (1 rename) | red `1 failed, 62 passed, 5 errors`, then `68 passed` | 3227 passed | match |
| Task 2 | 4 (1 rename) | red `16 failed, 2 passed, 5 errors`, then `23 passed` | 3227 passed | match |
| Task 3 | 28 (8 new) | red `10 failed, 11 passed`, then `21 passed`; probe `57 USED`, `4 UNUSED` (the four listed in Step 7) | 3236 passed | match |

Every commit passed the hooks on the first try and left a clean tree. Task 4 in the clone: `prek run --all-files` all Passed; `git diff --check 9f77382`, both protected-path commands and the `test_plugin_voice_contract.py` diff printed nothing; the `git grep` printed the five lines above; `git diff -M --stat` shows the two renames. Pure move: over the Task 3 commit, the non-blank lines removed from `pipeline/__init__.py` all reappear in the eight new modules except three import lines (`from typing import TYPE_CHECKING, Literal, Union`, the `speech.commands` import, the `.context` import with the `GENERIC_CONTEXT` re-export); the 69 other added lines are the eight module headers (docstrings and imports).

The plan text was produced from a prototype branch (same tree ids) and first replayed in two throw-away clones; the second of those and this record agree on every output and tree id.
