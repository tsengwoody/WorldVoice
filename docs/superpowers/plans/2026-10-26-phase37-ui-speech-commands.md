# Phase 37: `ui/` and `speechCommands.py` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice complex flow (DEVELOPMENT_WORKFLOW.md §4): one implementer runs every task in order,
> applying the `File:`/`Edit:` blocks byte for byte; every commit's tree ids must match this plan.
> The orchestrator dispatches the final Fable 5.1 review (§3.3, §4.5).

**Goal:** Gather the synth-side settings UI in one package `ui/` (`panelLayout.py`, `controls.py` ← `pipelineControls.py`, `voicePanel.py` ← `VoiceSettingsDialogs.py`) with an empty `__init__.py`, rename `_speechcommand.py` to `speechCommands.py`, prove with a guard test that `synthDrivers.WorldVoice.ui.panelLayout` imports by its package path without wx or NVDA, and say in `worldvoice_synth`'s docstring who uses it — with no behavior change.

**Architecture:** Pure moves with `git mv`; only import lines, path strings in tests, `pyproject.toml` mutmut paths, the listed docstrings/comments and one new guard test change. Dependency direction afterwards: `ui.voicePanel → ui.controls → ui.panelLayout`, `ui.voicePanel → pipeline.settings`, `pipeline`/`languageDetection`/`bridge → speechCommands`; `pipeline/` never imports `ui/`. `ui/__init__.py` is empty.

**Tech Stack:** Python 3 (NVDA add-on), pytest, ruff `==0.16.3` and add-trailing-comma through prek.

**Spec:** `docs/superpowers/specs/2026-10-26-phase37-ui-speech-commands-design.md`

**Base:** `master` `1f7fa46` — `HEAD:addon` = `9d4a7b01a9c558f4a984051b6f28c6a9be17b109`, `HEAD:tests` = `85401e928c5697030cd8cc258beba179e7c9b658`; `python3 -m pytest -q -p no:cacheprovider tests` → 3224 passed, 0 skipped; `prek run --all-files` all Passed. The spec and this plan are committed under `docs/` before Task 1 (`git add -f`, `docs/` is git-ignored but tracked); `docs/` does not enter the tree ids.

**Dry run:** see the end of this plan.

## Global Constraints

- Apply every `Edit:` block as one exact replacement (the "Replace" text occurs exactly once in the file at that point). Block text is whole lines; an empty "With" block deletes the "Replace" text. The blocks are already in the form prek leaves them (ruff's isort order included), so each commit passes the hooks on the first try. If a hook still changes a file, stop: the tree ids will not match (§4.4).
- Public import paths do not change: `synthDrivers.WorldVoice.driver` (`Voice`, `getVoiceKey`), `runtime.{engineControl, models, playbackWork, segmentHost, session}`, `text.arabic`, `text.chunker`, `driver.sonic._sonic`. `tests/test_plugin_voice_contract.py` is not edited and stays green.
- Never modify `driver/<Engine>/driver/`, `driver/sonic/`, `languageDetection/script_data.py`, `pipeline/unspaced_common_data.py`; engine drivers stay independently installable; never stage Neural or `ref`.
- No class, function, attribute or test-helper renames; no UI string changes (spec §3).
- `ui/__init__.py` stays empty (spec §2.1).
- ruff pinned `0.16.3`; tabs. Commits: English `<type>: <summary>` with a body saying why, no `Co-Authored-By`, `git add` with explicit paths only (after `git mv`, name only the new paths), check `git diff --cached --stat` first, never `--no-verify`, never `git stash`, no push, never touch the main checkout.
- Tests: one pytest process at a time (at most 3 workers), with a memory guard that kills pytest when MemAvailable < 3 GB.

## Review Focus

1. **NVDA's Voice settings panel still gets WorldVoice's class.** `__init__.py` must import `WorldVoiceVoiceSettingsPanel` from `ui.voicePanel` and patch it into `gui.settingsDialogs.VoiceSettingsPanel` (`__init__.py:209`, unchanged); the panel's relative imports are one level deeper (`..pipeline.settings`). Covered by `tests/test_runtime_composition.py` (stubs `ui.voicePanel` and loads the real entry point), `tests/test_voice_settings_panel.py` and `tests/test_settings_order.py` (load the real `ui/voicePanel.py` under the alias package) in Task 2.
2. **The global plugin's dialog imports from the new paths** (`synthDrivers.WorldVoice.ui.controls`, `.ui.panelLayout`). Covered by `tests/test_pipeline_panels.py`, `tests/test_role_panel.py`, `tests/test_unicode_panel.py` (load the real dialog after `ui_harness` registers the modules under their new dotted names) in Task 2.
3. **A real package import of `ui.panelLayout` without wx/NVDA.** The A2 guard must fail if `ui/__init__.py` ever imports `controls` or anything from the add-on. Task 2 Step 1 (red before the move) and Step 6 (uncommitted red check with `from . import controls`).
4. **Language and index markers after the `speechCommands` rename.** `WVLangChangeCommand` from detection and the pipeline, and `WorldVoiceIndexCommand` in `bridge.commands`/`bridge.indexCodec`, must still be the same classes the runtime and NVDA filters see. Covered by `tests/test_speech_command_contract.py`, `tests/test_worldvoice_index_command.py`, `tests/test_legacy_speech_commands.py`, `tests/test_runtime_adapter_contract.py`, `tests/test_worldvoice_speak.py` in Task 1.
5. **The pipeline does not come to depend on `ui/`.** `worldvoice_synth` stays in `pipeline/context.py` (spec §5.3); `tests/test_pipeline_structure.py::test_only_the_context_asks_nvda_for_the_synth` and `tests/test_lint_rewrites.py::test_worldvoice_synth_returns_only_worldvoice` stay green unchanged (Task 3).

Also watched: `pyproject.toml` mutmut `source_paths` follow the files (Task 2); `tests/test_hygiene_guards.py::test_ruff_reports_nothing` stays green.

---

### Task 1: Rename `_speechcommand.py` to `speechCommands.py` (F7)

**Files:**
- Move: `addon/synthDrivers/WorldVoice/_speechcommand.py` → `addon/synthDrivers/WorldVoice/speechCommands.py` (content unchanged)
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py`, `addon/synthDrivers/WorldVoice/languageDetection/__init__.py`, `addon/synthDrivers/WorldVoice/bridge/commands.py`, `addon/synthDrivers/WorldVoice/bridge/indexCodec.py` (one import line each, moved to its isort place)
- Test: `tests/test_speech_command_contract.py`, `tests/test_worldvoice_index_command.py`, `tests/test_format_outputs.py`, `tests/test_legacy_speech_commands.py`, `tests/test_worldvoice_speak.py`, `tests/detector_harness.py`, `tests/pipeline_harness.py`, `tests/runtime_harness.py`

**Interfaces:**
- Consumes: the base tree.
- Produces: module `speechCommands` with `WVLangChangeCommand`, `WorldVoiceIndexCommand` (names unchanged); `_speechcommand` no longer exists.

- [ ] **Step 1: Point the tests at the new module**

**Edit:** `tests/test_speech_command_contract.py` (1/1)

Replace:

```text
SPEECH_COMMAND = ADDON / "synthDrivers/WorldVoice/_speechcommand.py"
```

With:

```text
SPEECH_COMMAND = ADDON / "synthDrivers/WorldVoice/speechCommands.py"
```

**Edit:** `tests/test_worldvoice_index_command.py` (1/1)

Replace:

```text
	return load_source(monkeypatch, "worldvoice_index_command_test", RUNTIME.parent / "_speechcommand.py")
```

With:

```text
	return load_source(monkeypatch, "worldvoice_index_command_test", RUNTIME.parent / "speechCommands.py")
```

**Edit:** `tests/test_format_outputs.py` (1/1)

Replace:

```text
	commands = importlib.import_module(env.module.__name__.rsplit(".", 1)[0] + "._speechcommand")
```

With:

```text
	commands = importlib.import_module(env.module.__name__.rsplit(".", 1)[0] + ".speechCommands")
```

**Edit:** `tests/test_legacy_speech_commands.py` (1/2)

Replace:

```text
	for suffix in ("driver", "bridge", "bridge.commands", "_speechcommand"):
```

With:

```text
	for suffix in ("driver", "bridge", "bridge.commands", "speechCommands"):
```

**Edit:** `tests/test_legacy_speech_commands.py` (2/2)

Replace:

```text
	speechcommand = importlib.import_module(name + "._speechcommand")
```

With:

```text
	speechcommand = importlib.import_module(name + ".speechCommands")
```

**Edit:** `tests/test_worldvoice_speak.py` (1/1)

Replace:

```text
		WV=load("_speechcommand").WVLangChangeCommand,
```

With:

```text
		WV=load("speechCommands").WVLangChangeCommand,
```

**Edit:** `tests/detector_harness.py` (1/2)

Replace:

```text
"""Load the real languageDetection package and _speechcommand under NVDA stubs."""
```

With:

```text
"""Load the real languageDetection package and speechCommands under NVDA stubs."""
```

**Edit:** `tests/detector_harness.py` (2/2)

Replace:

```text
		WV=importlib.import_module(PACKAGE + "._speechcommand").WVLangChangeCommand,
```

With:

```text
		WV=importlib.import_module(PACKAGE + ".speechCommands").WVLangChangeCommand,
```

**Edit:** `tests/pipeline_harness.py` (1/2)

Replace:

```text
		"synthDrivers.WorldVoice._speechcommand",
```

With:

```text
		"synthDrivers.WorldVoice.speechCommands",
```

**Edit:** `tests/pipeline_harness.py` (2/2)

Replace:

```text
	speechcommand = stubs.module("synthDrivers.WorldVoice._speechcommand")
```

With:

```text
	speechcommand = stubs.module("synthDrivers.WorldVoice.speechCommands")
```

**Edit:** `tests/runtime_harness.py` (1/4)

Replace:

```text
		"_speechcommand",
```

With:

```text
		"speechCommands",
```

**Edit:** `tests/runtime_harness.py` (2/4)

Replace:

```text
			core.marker_type = importlib.import_module(name + "._speechcommand").WorldVoiceIndexCommand
```

With:

```text
			core.marker_type = importlib.import_module(name + ".speechCommands").WorldVoiceIndexCommand
```

**Edit:** `tests/runtime_harness.py` (3/4)

Replace:

```text
	for suffix in ("bridge.indexLedger", "_speechcommand", "bridge.indexCodec"):
```

With:

```text
	for suffix in ("bridge.indexLedger", "speechCommands", "bridge.indexCodec"):
```

**Edit:** `tests/runtime_harness.py` (4/4)

Replace:

```text
		commands=importlib.import_module(package_name + "._speechcommand"),
```

With:

```text
		commands=importlib.import_module(package_name + ".speechCommands"),
```

- [ ] **Step 2: Run them to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_speech_command_contract.py tests/test_worldvoice_index_command.py tests/test_format_outputs.py tests/test_legacy_speech_commands.py tests/test_worldvoice_speak.py tests/test_runtime_adapter_contract.py tests/test_index_codec.py`
Expected: `164 failed, 24 passed, 35 errors` — every test that loads the module by its new name or path (`FileNotFoundError` for `speechCommands.py`, `ModuleNotFoundError` for `….speechCommands`).

- [ ] **Step 3: Rename the module and fix its importers**

```bash
W=addon/synthDrivers/WorldVoice
git mv $W/_speechcommand.py $W/speechCommands.py
```

ruff's isort orders `..speechCommands` after `..runtime.…` and `..numberLanguage`.

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (1/1)

Replace:

```text
from .._speechcommand import WVLangChangeCommand
from ..languageDetection.scripts import get_script
from ..log import PipelineLog
from ..numberLanguage import FOLLOW, MAIN
from ..runtime.models import SelectVoice
```

With:

```text
from ..languageDetection.scripts import get_script
from ..log import PipelineLog
from ..numberLanguage import FOLLOW, MAIN
from ..runtime.models import SelectVoice
from ..speechCommands import WVLangChangeCommand
```

**Edit:** `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (1/1)

Replace:

```text
from .._speechcommand import WVLangChangeCommand
from ..locales import primary_language
from ..numberLanguage import FOLLOW, MAIN
```

With:

```text
from ..locales import primary_language
from ..numberLanguage import FOLLOW, MAIN
from ..speechCommands import WVLangChangeCommand
```

**Edit:** `addon/synthDrivers/WorldVoice/bridge/commands.py` (1/1)

Replace:

```text
from .._speechcommand import WorldVoiceIndexCommand
from ..runtime.models import Pause
```

With:

```text
from ..runtime.models import Pause
from ..speechCommands import WorldVoiceIndexCommand
```

**Edit:** `addon/synthDrivers/WorldVoice/bridge/indexCodec.py` (1/1)

Replace:

```text
from .._speechcommand import WorldVoiceIndexCommand
from ..runtime.models import PlaybackContext, SpeechCommands
```

With:

```text
from ..runtime.models import PlaybackContext, SpeechCommands
from ..speechCommands import WorldVoiceIndexCommand
```

- [ ] **Step 4: Run them to see green**

Run: the Step 2 command.
Expected: `223 passed`.

Run: `python3 -m pytest -q -p no:cacheprovider tests` → `3224 passed`, 0 skipped.

- [ ] **Step 5: Commit**

```bash
W=addon/synthDrivers/WorldVoice
git add $W/speechCommands.py $W/pipeline/__init__.py $W/languageDetection/__init__.py $W/bridge/commands.py $W/bridge/indexCodec.py tests/detector_harness.py tests/pipeline_harness.py tests/runtime_harness.py tests/test_format_outputs.py tests/test_legacy_speech_commands.py tests/test_speech_command_contract.py tests/test_worldvoice_index_command.py tests/test_worldvoice_speak.py
git diff --cached --stat   # 13 files: 1 rename, 12 modified
git commit -q -F - <<'EOF'
refactor: rename _speechcommand to speechCommands

The leading underscore marked the module private, yet pipeline,
languageDetection and two bridge modules import it, and the
all-lower-case singular name broke the package's camelCase module
names. Pure rename: WVLangChangeCommand and WorldVoiceIndexCommand keep
their names and content; tests and harnesses follow the new path.
EOF
git rev-parse HEAD:addon HEAD:tests
```

Expected after the commit: `HEAD:addon` = `5a8cee35c8e13fb351e9cf1987be30bf618f36a1`, `HEAD:tests` = `0e8ab84ffe217d851b93bec968e1fb2de7c0f090`

---

### Task 2: Gather the settings UI in `ui/` (F3) with the A2 import guard (test first)

**Files:**
- Create: `addon/synthDrivers/WorldVoice/ui/__init__.py` (empty)
- Move: `pipeline/panelLayout.py` → `ui/panelLayout.py` (content unchanged), `pipelineControls.py` → `ui/controls.py`, `VoiceSettingsDialogs.py` → `ui/voicePanel.py` (under `addon/synthDrivers/WorldVoice/`)
- Modify: `addon/synthDrivers/WorldVoice/__init__.py` (one import line), `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (imports), the moved `ui/controls.py` and `ui/voicePanel.py`, `pyproject.toml` (mutmut `source_paths`)
- Test: `tests/test_ui_structure.py` (new guard test, path constants, import-source assertion), `tests/ui_harness.py`, `tests/test_panel_layout.py`, `tests/test_settings_table_guard.py`, `tests/test_pipeline_controls.py`, `tests/test_pipeline_panels.py`, `tests/test_voice_settings_panel.py`, `tests/test_runtime_composition.py`

**Interfaces:**
- Consumes: Task 1's tree.
- Produces: package `ui` with modules `panelLayout`, `controls`, `voicePanel` (every name unchanged); `ui/__init__.py` empty. `ui_harness` registers them as `synthDrivers.WorldVoice.ui.{panelLayout,controls,voicePanel}` under an alias package `synthDrivers.WorldVoice.ui`. Test `test_panel_layout_imports_by_its_package_path_without_wx_or_nvda`.

- [ ] **Step 1: Write the failing guard test**

The three blocks below add the imports and the test; the path constants follow in Step 4.

**Edit:** `tests/test_ui_structure.py` (1/3)

Replace:

```text
import ast
from types import SimpleNamespace
```

With:

```text
import ast
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
```

**Edit:** `tests/test_ui_structure.py` (2/3)

Replace:

```text
from addon_loader import ADDON, WORLDVOICE, load_definitions
```

With:

```text
from addon_loader import ADDON, WORLDVOICE, alias_package, load_definitions
```

**Edit:** `tests/test_ui_structure.py` (3/3)

Replace:

```text
		assert "getSynth" not in names, str(path.relative_to(ADDON))
```

With:

```text
		assert "getSynth" not in names, str(path.relative_to(ADDON))


def test_panel_layout_imports_by_its_package_path_without_wx_or_nvda(monkeypatch):
	# The global plugin imports synthDrivers.WorldVoice.ui.panelLayout, so Python runs
	# ui/__init__.py first; the layout tests load the file on their own and would miss an import
	# there. ui/__init__.py stays empty and the layout rules import nothing from the add-on, wx
	# or NVDA, so the rules load without any of them.
	for name in [name for name in sys.modules if name.split(".")[0] == "synthDrivers"]:
		monkeypatch.delitem(sys.modules, name)
	# None in sys.modules makes an import of that name fail.
	for name in ("wx", "gui", "config", "speech", "synthDriverHandler", "logHandler", "addonHandler"):
		monkeypatch.setitem(sys.modules, name, None)
	alias_package(monkeypatch, "synthDrivers")
	alias_package(monkeypatch, "synthDrivers.WorldVoice", WORLDVOICE)
	try:
		layout = importlib.import_module("synthDrivers.WorldVoice.ui.panelLayout")
		loaded = sorted(name for name in sys.modules if name.split(".")[0] == "synthDrivers")
	finally:
		# The import registered these itself, so monkeypatch would leave them behind.
		for name in ("synthDrivers.WorldVoice.ui.panelLayout", "synthDrivers.WorldVoice.ui"):
			sys.modules.pop(name, None)
	assert Path(layout.__file__) == WORLDVOICE / "ui/panelLayout.py"
	assert loaded == [
		"synthDrivers",
		"synthDrivers.WorldVoice",
		"synthDrivers.WorldVoice.ui",
		"synthDrivers.WorldVoice.ui.panelLayout",
	]
```

- [ ] **Step 2: Run it to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_ui_structure.py`
Expected: `1 failed, 5 passed`; the failure is `ModuleNotFoundError: No module named 'synthDrivers.WorldVoice.ui'`.

- [ ] **Step 3: Move the files and fix the add-on imports**

```bash
W=addon/synthDrivers/WorldVoice
mkdir $W/ui
: > $W/ui/__init__.py
git mv $W/pipeline/panelLayout.py $W/ui/panelLayout.py
git mv $W/pipelineControls.py $W/ui/controls.py
git mv $W/VoiceSettingsDialogs.py $W/ui/voicePanel.py
```

`ui/panelLayout.py` keeps its content. ruff's isort orders `..pipeline.settings` before `.controls` before `.panelLayout`, and in the dialog `…pipeline.settings` before `…ui.controls` before `…ui.panelLayout`.

**Edit:** `addon/synthDrivers/WorldVoice/ui/controls.py` (1/2)

Replace:

```text
pipeline/panelLayout.py. No engine driver imports this.
```

With:

```text
ui/panelLayout.py. No engine driver imports this.
```

**Edit:** `addon/synthDrivers/WorldVoice/ui/controls.py` (2/2)

Replace:

```text
from .pipeline.panelLayout import (
```

With:

```text
from .panelLayout import (
```

**Edit:** `addon/synthDrivers/WorldVoice/ui/voicePanel.py` (1/1)

Replace:

```text
from .pipeline.panelLayout import (
	VOICE_PANEL,
	controller_keys,
	creation_followers,
	driver_attribute,
	panel_specs,
	voice_attribute,
)
from .pipeline.settings import PIPELINE_CONFIG_KEYS, PIPELINE_SETTINGS, pipeline_settings
from .pipelineControls import (
	CHANGE_EVENTS,
	apply_dependencies,
	control_row,
	control_value,
	make_control,
	read_control,
```

With:

```text
from ..pipeline.settings import PIPELINE_CONFIG_KEYS, PIPELINE_SETTINGS, pipeline_settings
from .controls import (
	CHANGE_EVENTS,
	apply_dependencies,
	control_row,
	control_value,
	make_control,
	read_control,
)
from .panelLayout import (
	VOICE_PANEL,
	controller_keys,
	creation_followers,
	driver_attribute,
	panel_specs,
	voice_attribute,
```

**Edit:** `addon/synthDrivers/WorldVoice/__init__.py` (1/1)

Replace:

```text
from .voices.manager import VoiceManager
from .voices.settingsRepository import VOICE_CONFSPEC, ConfigVoiceSettingsRepository
from .VoiceSettingsDialogs import WorldVoiceVoiceSettingsPanel
```

With:

```text
from .ui.voicePanel import WorldVoiceVoiceSettingsPanel
from .voices.manager import VoiceManager
from .voices.settingsRepository import VOICE_CONFSPEC, ConfigVoiceSettingsRepository
```

**Edit:** `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (1/1)

Replace:

```text
from synthDrivers.WorldVoice.pipeline.panelLayout import (
	PIPELINE_PANEL,
	controller_keys,
	panel_specs,
	pipeline_attribute,
)
from synthDrivers.WorldVoice.pipeline.settings import PIPELINE_SETTINGS, pipeline_settings, read_stored
from synthDrivers.WorldVoice.pipelineControls import (
	CHANGE_EVENTS,
	apply_dependencies,
	control_value,
	make_control,
	read_control,
```

With:

```text
from synthDrivers.WorldVoice.pipeline.settings import PIPELINE_SETTINGS, pipeline_settings, read_stored
from synthDrivers.WorldVoice.ui.controls import (
	CHANGE_EVENTS,
	apply_dependencies,
	control_value,
	make_control,
	read_control,
)
from synthDrivers.WorldVoice.ui.panelLayout import (
	PIPELINE_PANEL,
	controller_keys,
	panel_specs,
	pipeline_attribute,
```

**Edit:** `pyproject.toml` (1/1)

Replace:

```text
	"addon/synthDrivers/WorldVoice/pipeline/panelLayout.py",
	"addon/synthDrivers/WorldVoice/pipelineControls.py",
```

With:

```text
	"addon/synthDrivers/WorldVoice/ui/panelLayout.py",
	"addon/synthDrivers/WorldVoice/ui/controls.py",
```

- [ ] **Step 4: Point the remaining tests at the new paths**

**Edit:** `tests/test_ui_structure.py` (1/3)

Replace:

```text
VOICE_PANEL = WORLDVOICE / "VoiceSettingsDialogs.py"
PIPELINE_CONTROLS = WORLDVOICE / "pipelineControls.py"
```

With:

```text
VOICE_PANEL = WORLDVOICE / "ui/voicePanel.py"
PIPELINE_CONTROLS = WORLDVOICE / "ui/controls.py"
```

**Edit:** `tests/test_ui_structure.py` (2/3)

Replace:

```text
	# The depends_on loop and the controller read live in pipelineControls; each panel passes in
```

With:

```text
	# The depends_on loop and the controller read live in ui/controls.py; each panel passes in
```

**Edit:** `tests/test_ui_structure.py` (3/3)

Replace:

```text
			assert (node.level, node.module) == (1, "pipeline.panelLayout"), ast.unparse(node)
```

With:

```text
			assert (node.level, node.module) == (1, "panelLayout"), ast.unparse(node)
```

**Edit:** `tests/ui_harness.py` (1/6)

Replace:

```text
	alias_package(monkeypatch, "synthDrivers.WorldVoice.pipeline")
	load_source(monkeypatch, "synthDrivers.WorldVoice.numberLanguage", WORLDVOICE / "numberLanguage.py")
```

With:

```text
	alias_package(monkeypatch, "synthDrivers.WorldVoice.pipeline")
	alias_package(monkeypatch, "synthDrivers.WorldVoice.ui")
	load_source(monkeypatch, "synthDrivers.WorldVoice.numberLanguage", WORLDVOICE / "numberLanguage.py")
```

**Edit:** `tests/ui_harness.py` (2/6)

Replace:

```text
		"synthDrivers.WorldVoice.pipeline.panelLayout",
		WORLDVOICE / "pipeline/panelLayout.py",
```

With:

```text
		"synthDrivers.WorldVoice.ui.panelLayout",
		WORLDVOICE / "ui/panelLayout.py",
```

**Edit:** `tests/ui_harness.py` (3/6)

Replace:

```text
		"synthDrivers.WorldVoice.pipelineControls",
		WORLDVOICE / "pipelineControls.py",
```

With:

```text
		"synthDrivers.WorldVoice.ui.controls",
		WORLDVOICE / "ui/controls.py",
```

**Edit:** `tests/ui_harness.py` (4/6)

Replace:

```text
	"""The real pipelineControls.py and the pipeline settings it builds controls for."""
```

With:

```text
	"""The real ui/controls.py and the pipeline settings it builds controls for."""
```

**Edit:** `tests/ui_harness.py` (5/6)

Replace:

```text
	"""The real synthDrivers/WorldVoice/VoiceSettingsDialogs.py with real pipeline settings."""
```

With:

```text
	"""The real synthDrivers/WorldVoice/ui/voicePanel.py with real pipeline settings."""
```

**Edit:** `tests/ui_harness.py` (6/6)

Replace:

```text
		"synthDrivers.WorldVoice.VoiceSettingsDialogs",
		WORLDVOICE / "VoiceSettingsDialogs.py",
```

With:

```text
		"synthDrivers.WorldVoice.ui.voicePanel",
		WORLDVOICE / "ui/voicePanel.py",
```

**Edit:** `tests/test_panel_layout.py` (1/2)

Replace:

```text
"""The pure layout rules both settings panels follow (pipeline/panelLayout.py).
```

With:

```text
"""The pure layout rules both settings panels follow (ui/panelLayout.py).
```

**Edit:** `tests/test_panel_layout.py` (2/2)

Replace:

```text
layout = load_source(None, "panel_layout_under_test", WORLDVOICE / "pipeline/panelLayout.py", register=False)
```

With:

```text
layout = load_source(None, "panel_layout_under_test", WORLDVOICE / "ui/panelLayout.py", register=False)
```

**Edit:** `tests/test_settings_table_guard.py` (1/1)

Replace:

```text
layout = load_source(None, "guard_panel_layout", WORLDVOICE / "pipeline/panelLayout.py", register=False)
```

With:

```text
layout = load_source(None, "guard_panel_layout", WORLDVOICE / "ui/panelLayout.py", register=False)
```

**Edit:** `tests/test_pipeline_controls.py` (1/2)

Replace:

```text
The real pipelineControls.py runs against ui_harness's fake wx, with specs from the real table.
```

With:

```text
The real ui/controls.py runs against ui_harness's fake wx, with specs from the real table.
```

**Edit:** `tests/test_pipeline_controls.py` (2/2)

Replace:

```text
	env.layout = sys.modules["synthDrivers.WorldVoice.pipeline.panelLayout"]
```

With:

```text
	env.layout = sys.modules["synthDrivers.WorldVoice.ui.panelLayout"]
```

**Edit:** `tests/test_pipeline_panels.py` (1/1)

Replace:

```text
VOICE_PANEL = WORLDVOICE / "VoiceSettingsDialogs.py"
```

With:

```text
VOICE_PANEL = WORLDVOICE / "ui/voicePanel.py"
```

**Edit:** `tests/test_voice_settings_panel.py` (1/1)

Replace:

```text
The real VoiceSettingsDialogs.py runs over ui_harness's stand-in for NVDA's VoiceSettingsPanel,
```

With:

```text
The real ui/voicePanel.py runs over ui_harness's stand-in for NVDA's VoiceSettingsPanel,
```

**Edit:** `tests/test_runtime_composition.py` (1/1)

Replace:

```text
	stub(package + ".VoiceSettingsDialogs", WorldVoiceVoiceSettingsPanel=object)
```

With:

```text
	stub(package + ".ui.voicePanel", WorldVoiceVoiceSettingsPanel=object)
```

- [ ] **Step 5: Run them to see green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_ui_structure.py tests/test_panel_layout.py tests/test_settings_table_guard.py tests/test_pipeline_controls.py tests/test_pipeline_panels.py tests/test_voice_settings_panel.py tests/test_runtime_composition.py tests/test_settings_order.py tests/test_role_panel.py tests/test_unicode_panel.py`
Expected: `280 passed`.

- [ ] **Step 6: Check that the guard catches an import in `ui/__init__.py` (not committed)**

```bash
W=addon/synthDrivers/WorldVoice
printf 'from . import controls\n' > $W/ui/__init__.py
python3 -m pytest -q -p no:cacheprovider tests/test_ui_structure.py::test_panel_layout_imports_by_its_package_path_without_wx_or_nvda || echo "red as expected"
: > $W/ui/__init__.py
python3 -m pytest -q -p no:cacheprovider tests/test_ui_structure.py
```

Expected: the first run `1 failed` (then `red as expected`) with `ModuleNotFoundError: import of wx halted; None in sys.modules` raised at `ui/controls.py:13`; the second `6 passed`. `ui/__init__.py` is empty again (`test ! -s $W/ui/__init__.py`).

- [ ] **Step 7: Full suite**

Run: `python3 -m pytest -q -p no:cacheprovider tests` → `3225 passed`, 0 skipped (baseline 3224 + the guard).

- [ ] **Step 8: Commit**

The old paths are already staged by `git mv`; name only the new ones.

```bash
W=addon/synthDrivers/WorldVoice
git add $W/ui $W/__init__.py addon/globalPlugins/WorldVoice/speechSettingsDialog.py pyproject.toml tests/ui_harness.py tests/test_ui_structure.py tests/test_panel_layout.py tests/test_settings_table_guard.py tests/test_pipeline_controls.py tests/test_pipeline_panels.py tests/test_voice_settings_panel.py tests/test_runtime_composition.py
git diff --cached --stat   # 15 files: 1 new, 3 renames, 11 modified
git commit -q -F - <<'EOF'
refactor: gather the synth-side settings UI in ui/

The Voice panel, the control builder both panels share and their pure
layout rules sat in three places: VoiceSettingsDialogs.py (one panel,
not dialogs, and the only PascalCase file), pipelineControls.py at the
root, and pipeline/panelLayout.py, which nothing in pipeline/ imports.
ui/ now holds them as voicePanel, controls and panelLayout. Its
__init__.py stays empty, so the global plugin's import of
ui.panelLayout runs no wx or NVDA code; a new guard test imports it by
its package path with wx and NVDA blocked. Under pipeline/ that import
ran pipeline/__init__.py and with it NVDA's config and speech modules.
Pure move otherwise: names, behaviour and UI strings are unchanged;
tests, harnesses and the mutmut source paths follow the new paths.
EOF
git rev-parse HEAD:addon HEAD:tests
```

Expected after the commit: `HEAD:addon` = `33880423bb6c5bc8e0eca2672293e47229970097`, `HEAD:tests` = `08f6907fb671bfcf0badeafd32664dcba29d8369`

---

### Task 3: Say who uses `worldvoice_synth` (F11)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/context.py:25-26` (docstring only)

**Interfaces:**
- Consumes: Task 2's tree.
- Produces: docstring only; `worldvoice_synth()` stays in `pipeline/context.py` (spec §5.3).

- [ ] **Step 1: Rewrite the docstring**

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/context.py` (1/1)

Replace:

```text
	"""NVDA's current synth when it is WorldVoice, otherwise None."""
```

With:

```text
	"""NVDA's current synth when it is WorldVoice, otherwise None.

	current_context() below asks through it, and so does the global plugin's settings dialog,
	which reaches the voice manager this way. It stays here, not in ui/, so the pipeline never
	imports the settings UI.
	"""
```

- [ ] **Step 2: Full suite**

Run: `python3 -m pytest -q -p no:cacheprovider tests` → `3225 passed`, 0 skipped.

- [ ] **Step 3: Commit**

```bash
git add addon/synthDrivers/WorldVoice/pipeline/context.py
git diff --cached --stat   # 1 file
git commit -q -F - <<'EOF'
docs: say who uses worldvoice_synth and why it stays in pipeline

The global plugin's settings dialog reaches the voice manager through
worldvoice_synth(), so the function read as pipeline-only code in the
wrong place. Moving it to ui/ would make the pipeline's
current_context() import the settings UI, and a new root module would
save the dialog no import (it already imports pipeline). The docstring
now names both users and the reason it stays.
EOF
git rev-parse HEAD:addon HEAD:tests
```

Expected after the commit: `HEAD:addon` = `14d90d18692c58304d4997f2e3e02bc7c9cdb439`, `HEAD:tests` = `08f6907fb671bfcf0badeafd32664dcba29d8369`

---

### Task 4: Full verification (DEVELOPMENT_WORKFLOW.md §7)

- [ ] **Step 1:** `python3 -m pytest -q -p no:cacheprovider tests` → `3225 passed`, 0 skipped (baseline 3224; +1 guard from Task 2).
- [ ] **Step 2:** `prek run --all-files` → every hook Passed.
- [ ] **Step 3:** `git diff --check master` → no output.
- [ ] **Step 4:** protected paths → both commands print nothing:

```bash
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py addon/synthDrivers/WorldVoice/pipeline/unspaced_common_data.py
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
```

- [ ] **Step 5:** `git diff master --stat -- tests/test_plugin_voice_contract.py` → no output (the plugin contract test is unchanged).
- [ ] **Step 6:** `git diff -M master --stat -- addon/synthDrivers/WorldVoice/ui/panelLayout.py addon/synthDrivers/WorldVoice/pipeline/panelLayout.py addon/synthDrivers/WorldVoice/speechCommands.py addon/synthDrivers/WorldVoice/_speechcommand.py` shows two pure renames (`=> ` with `0` changes), and `git grep -n -E "_speechcommand|pipelineControls|VoiceSettingsDialogs|pipeline\.panelLayout|pipeline/panelLayout" -- addon tests pyproject.toml` prints nothing.
- [ ] **Step 7:** final `git rev-parse HEAD:addon HEAD:tests` equals Task 3's ids. Not packaged, not verified on Windows (no behavior change).

---

## Dry run record

2026-10-26, fresh clone of `/workspace/WorldVoice` at `1f7fa46` in the scratchpad (`ref` symlinked, `prek install`), every step applied from this plan's text (blocks by exact replacement, shell blocks as written), pytest under a MemAvailable < 3 GB guard:

| Commit | Files | Focused run | Full suite | Tree ids |
| --- | --- | --- | --- | --- |
| Task 1 | 13 (1 rename) | red `164 failed, 24 passed, 35 errors` (6 `FileNotFoundError`, 193 `ModuleNotFoundError` lines), then `223 passed` | 3224 passed | match |
| Task 2 | 15 (1 new, 3 renames) | red `1 failed, 5 passed` (`No module named 'synthDrivers.WorldVoice.ui'`), then `280 passed`; Step 6 `import of wx halted` at `ui/controls.py:13`, then `6 passed` with `ui/__init__.py` empty again | 3225 passed | match |
| Task 3 | 1 | — | 3225 passed | match |

Every commit passed the hooks on the first try and left a clean tree. Task 4 in the clone: `prek run --all-files` all Passed; `git diff --check 1f7fa46`, both protected-path commands, the `test_plugin_voice_contract.py` diff and the old-name `git grep` printed nothing; `git diff -M --stat` shows `_speechcommand.py => speechCommands.py` and `{pipeline => ui}/panelLayout.py` with 0 changes; `git log --follow` of `ui/voicePanel.py` reaches the first commit of the repository.

The first attempt stopped at Task 2 Step 6: run as one `bash -e` script, the expected pytest failure ended the block before `: > $W/ui/__init__.py` restored the empty file, so the commit carried `from . import controls` and ruff (F401) rejected it. The block now ends that pytest line with `|| echo "red as expected"`, and the dry run was redone from `1f7fa46`; the result above is that second run.
