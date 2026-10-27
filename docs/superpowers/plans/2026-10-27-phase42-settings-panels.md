# Phase 42: settings dialog split into `panels/` and `dialog.py` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice complex flow (DEVELOPMENT_WORKFLOW.md §4): one implementer runs every task in order,
> applying the `File:`/`Edit:` blocks byte for byte; every commit's tree ids must match this plan.
> The orchestrator dispatches the final Fable 5.1 review (§3.3, §4.5).
> 4 tasks: no batch reviews (§3.2). **Task 3 is gated** on the user's answer to spec §9 question 1.

**Goal:** Split the 737-line `globalPlugins/WorldVoice/speechSettingsDialog.py` into one module per panel under `panels/` (empty `__init__.py`) and `dialog.py` for the dialog, verbatim, then share the duplicated "not WorldVoice" notice and the duplicated settings error dialog — with no user-visible change apart from the one spec §9 asks the user about.

**Architecture:** Task 1 is a verbatim split done by a deterministic script embedded below: it slices the old module by top-level definition and writes each new module with a fixed header (docstring, the imports it uses, its own `addonHandler.initTranslation()`); importers and tests name the new modules; `buildVars.py` hands the subpackage to `scons pot`. Task 2 adds `panels/base.notWorldVoiceNotice(panel, sizer)`; Task 3 adds `utils.reportError(error)`. Dependency direction afterwards: `__init__ → dialog → panels.{pipeline, role, detection, engine, log}`; `panels.{engine, log} → panels.base`; `panels.role → panels.base, utils, rolePresenter`; `panels.log → pipelineLog`; no panel imports another panel module except `base`, and `utils` imports no panel.

**Tech Stack:** Python 3 (NVDA add-on), wxPython (faked in `tests/ui_harness.py`), pytest, ruff `==0.16.3` and add-trailing-comma through prek.

**Spec:** `docs/superpowers/specs/2026-10-27-phase42-settings-panels-design.md`

**Base:** `master` `a7bd115` — `HEAD:addon` = `708b3088fb75a0ac8e93f3b134b645f9401abe45`, `HEAD:tests` = `124beda7a0826836f6aba9ed5f2032bac8c16fd5`; `python3 -m pytest -q -p no:cacheprovider tests` → 3260 passed, 0 skipped; `prek run --all-files` all Passed; `git diff --check` clean. The spec and this plan are committed under `docs/` before Task 1 (`git add -f`, `docs/` is git-ignored but tracked); `docs/` and `buildVars.py` do not enter the tree ids (the dry run also compares `buildVars.py` by content).

**Dry run:** see the end of this plan.

## Global Constraints

- Shell variables used below: `$SCRATCH` is the session scratchpad directory (`/tmp/claude-0/-workspace-WorldVoice/<session>/scratchpad`); every command runs from the repository root of the worktree. `$SCRATCH/runtests.sh <repo> <pytest args>` runs one pytest process and kills it when MemAvailable < 3 GB.
- Apply every `Edit:` block as one exact replacement (the "Replace" text occurs exactly once in the file at that point). Block text is whole lines. The blocks are already in the form prek leaves them (ruff's isort order and format, add-trailing-comma), so each commit passes the hooks on the first try. If a hook still changes a file, stop: the tree ids will not match (§4.4).
- No user-visible change in Tasks 1–2: panel list and order, controls, labels, msgids, focus, saved values, prompts and restart behavior stay identical; no `.po`, readme or changelog change. Task 3 changes only the language of the error dialog of a failing Speech Role handler (spec §9) and lands only after the user chose option (a).
- Moves are verbatim: apart from the module headers, Task 1 adds and removes no line of the old module (Task 1 Step 6 checks it). No rename of an existing name (phase 47 does that); new add-on names are mixedCase (`notWorldVoiceNotice`, `reportError`, refactor9 §6.1).
- `panels/__init__.py` stays empty (0 bytes). No compatibility module for `speechSettingsDialog`. The dialog gains no import of `engineRegistry.discovery`; `_as_bool` stays in `panels/base.py`.
- Never modify `driver/<Engine>/driver/`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; engine drivers stay independently installable; never stage Neural or `ref`.
- ruff pinned `0.16.3`; tabs; line length 110. Commits: English `<type>: <summary>` with a body saying why, no `Co-Authored-By`, `git add` with explicit paths only, check `git diff --cached --stat` first, never `--no-verify`, never `git stash`, no push, never touch the main checkout.
- Tests: one pytest process at a time, under `$SCRATCH/runtests.sh`.
- Deviations go to `.superpowers/sdd/2026-10-27-phase42-settings-panels/progress.md` as `Ruling: <decision> — <reason> — <cost if wrong>`.

## Review Focus

1. **A moved panel that NVDA shows in English.** NVDA's `initTranslation()` binds `_` only in the module that calls it (`ref/nvda/source/addonHandler/__init__.py:975-981`); a split module without its own call silently falls back to NVDA's catalog, and the tests' identity `_` cannot tell. Task 1: `test_every_translated_module_installs_the_add_on_catalog` and the Step 5 probe that deletes the call from `panels/role.py`; Task 3 removes the guard's `utils.py` exemption.
2. **Panel strings dropping out of the translation template.** `scons pot` reads only `buildVars.pythonSources`. Task 1: `test_every_translated_module_is_a_pot_source`, red after the split (Step 3) until the glob is added (Step 4).
3. **A test patch that no longer reaches the code it means to change.** `RolePanelPresenter`, `pipeline_log`, `PIPELINE_SETTINGS` and `pipeline_settings` are now looked up in a panel module's globals; a patch on the dialog module would leave the real object in place. Task 1: the patches name `env.panels.<module>`, and each patched test asserts the patched effect (`tests/test_role_panel_ui.py` fixture builds the panel with the fake presenter, `test_log_panel_save_fixes_an_invalid_enable_flag` writes through the real service, `test_pipeline_panel_never_saves_an_entry_pipeline_config_does_not_store`, `test_pipeline_panel_saves_once_through_the_service`).
4. **Another synthesizer than WorldVoice.** The Speech Role and Unicode Detection panels must still show exactly the read-only notice (same flags, background, sizer item), disable themselves and save nothing; the dialog must still offer only Speech Pipeline, Speech Engine, Log Record. Task 2: `test_panels_for_another_synth_show_the_same_read_only_notice[…]` (green before and after), `test_panels_share_the_not_worldvoice_notice`; existing `test_panel_for_another_synth_only_says_so`, `test_unicode_panel_for_another_synth_only_says_so`, `test_dialog_offers_role_and_unicode_panels_only_for_worldvoice`.
5. **A failed Speech Role save.** It must still log, show the same message, title and style, and raise `ValueError` so NVDA keeps its dialog open; a failing handler's dialog and callback stay as `tests/test_guard_errors.py` pins them. Task 3: `test_a_failed_save_reports_the_error_and_keeps_the_dialog_open` (real `utils`, green before and after), `test_settings_errors_share_one_dialog`, `tests/test_role_panel.py::test_failed_apply_shows_error_and_raises_value_error`.

Also watched: opening the dialog from the NVDA menu (`__init__.py` imports `.dialog`; `tests/test_global_plugin_menu.py` loads the real `__init__.py` against a stub `.dialog`); `tests/test_hygiene_guards.py::test_ruff_reports_nothing` stays green.

---

### Task 1: Split the dialog into `panels/` and `dialog.py` (F2) with the translation guards

**Files:**
- Delete: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py`
- Create (by the split script): `addon/globalPlugins/WorldVoice/dialog.py`, `addon/globalPlugins/WorldVoice/panels/{__init__,base,pipeline,role,detection,engine,log}.py`
- Modify: `addon/globalPlugins/WorldVoice/__init__.py:21-22`, `buildVars.py:63`
- Test: `tests/test_translator_comments.py` (two guards), `tests/ui_harness.py`, `tests/test_ui_structure.py`, `tests/test_role_guards.py`, `tests/test_role_panel.py`, `tests/test_unicode_panel.py`, `tests/test_settings_panel_save.py`, `tests/test_pipeline_log.py`, `tests/test_pipeline_panels.py`, `tests/test_settings_panels.py`, `tests/test_role_panel_ui.py`, `tests/test_settings_order.py`

**Interfaces:**
- Consumes: the base tree.
- Produces: modules `globalPlugins.WorldVoice.dialog` (`WorldVoiceSettingsDialog`, plus the five panel classes it imports) and `globalPlugins.WorldVoice.panels.{base,pipeline,role,detection,engine,log}` with the definitions of spec §2 goal 1, names unchanged; `speechSettingsDialog` no longer exists. `tests/ui_harness.load_settings_dialog(...)` returns `env.module` (dialog) and `env.panels.<name>` (each panel module); `ui_harness.PANEL_MODULES`.

- [ ] **Step 1: Write the translation guards** (they pass on the base tree; Steps 3 and 5 show them fail)

**Edit:** `tests/test_translator_comments.py` (1/2)

Replace:

```text
import re
from pathlib import Path
```

With:

```text
import ast
import re
from pathlib import Path
```

**Edit:** `tests/test_translator_comments.py` (2/2)

Replace:

```text
def test_zh_tw_catalog_follows_the_labels():
	catalog = _catalog(ZH_TW_CATALOG)
	assert {msgid: catalog.get(msgid, "") for msgid in CHANGED_LABEL_MSGIDS if not catalog.get(msgid)} == {}
	assert [msgid for msgid in DEAD_MSGIDS if msgid in catalog] == []
```

With:

```text
def test_zh_tw_catalog_follows_the_labels():
	catalog = _catalog(ZH_TW_CATALOG)
	assert {msgid: catalog.get(msgid, "") for msgid in CHANGED_LABEL_MSGIDS if not catalog.get(msgid)} == {}
	assert [msgid for msgid in DEAD_MSGIDS if msgid in catalog] == []


GETTEXT_NAMES = {"_", "pgettext", "ngettext", "npgettext"}
# Modules that call _() without addonHandler.initTranslation(): the _ they reach is NVDA's own
# catalog, which has none of their strings, so NVDA shows those in English.
UNTRANSLATED = ("globalPlugins/WorldVoice/utils.py",)


def _translated_modules():
	"""(relative path, path, tree) of each add-on module with a gettext call."""
	for path in sorted(ADDON.rglob("*.py")):
		relative = path.relative_to(ADDON).as_posix()
		if EXCLUDED.search(relative):
			continue
		tree = ast.parse(path.read_text(encoding="utf-8"))
		if any(
			isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in GETTEXT_NAMES
			for node in ast.walk(tree)
		):
			yield relative, path, tree


def test_every_translated_module_installs_the_add_on_catalog():
	# initTranslation() sets _ in the calling module only, so a module split off another needs its own.
	missing = [
		relative
		for relative, _path, tree in _translated_modules()
		if "addonHandler.initTranslation()" not in {ast.unparse(node) for node in tree.body}
	]
	assert missing == list(UNTRANSLATED)


def test_every_translated_module_is_a_pot_source():
	# buildVars.pythonSources is what scons pot hands to xgettext; a module it misses drops out of
	# the catalog template.
	root = ADDON.parent
	tree = ast.parse((root / "buildVars.py").read_text(encoding="utf-8"))
	(sources,) = [
		node.value
		for node in tree.body
		if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "pythonSources"
	]
	covered = {path for pattern in ast.literal_eval(sources) for path in root.glob(pattern)}
	assert [relative for relative, path, _tree in _translated_modules() if path not in covered] == []
```

```bash
$SCRATCH/runtests.sh . tests/test_translator_comments.py
```

Expected: `6 passed` (the four existing tests and the two guards).

- [ ] **Step 2: Point the tests at the new modules**

**Edit:** `tests/ui_harness.py` (1/4)

Replace:

```text
PLUGIN_DIR = ADDON / "globalPlugins/WorldVoice"
```

With:

```text
PLUGIN_DIR = ADDON / "globalPlugins/WorldVoice"
# The settings panel modules under PLUGIN_DIR / "panels", each after the ones it imports.
PANEL_MODULES = ("base", "pipeline", "role", "detection", "engine", "log")
```

**Edit:** `tests/ui_harness.py` (2/4)

Replace:

```text
	"""The real speechSettingsDialog.py, its real utils, pipeline settings and pipeline context.

	conf defaults to a fresh WorldVoice profile plus an empty speech section; synth is what
	getSynth returns (``env.current[0]`` changes it later). engines are (name, label, default)
	for ENGINE_SPECS, and get_engine_enabled reads the stored flag. The pipeline log service and
	its prompts are recorded in ``env.log_calls``; tests replace RolePanelPresenter on the module.
	"""
```

With:

```text
	"""The real dialog.py and panels/, their real utils, pipeline settings and pipeline context.

	``env.module`` is the dialog module, which imports every panel class it offers;
	``env.panels.<name>`` is each panel module of PANEL_MODULES, where a test replaces a name the
	panel looks up. conf defaults to a fresh WorldVoice profile plus an empty speech section;
	synth is what getSynth returns (``env.current[0]`` changes it later). engines are (name,
	label, default) for ENGINE_SPECS, and get_engine_enabled reads the stored flag. The pipeline
	log service and its prompts are recorded in ``env.log_calls``; tests replace
	RolePanelPresenter on ``env.panels.role``.
	"""
```

**Edit:** `tests/ui_harness.py` (3/4)

Replace:

```text
	# Loaded here, not by the dialog's relative import, so it leaves sys.modules after the test.
	load_source(monkeypatch, package + ".utils", PLUGIN_DIR / "utils.py")
	env.module = load_source(
		monkeypatch,
		package + ".speechSettingsDialog",
		PLUGIN_DIR / "speechSettingsDialog.py",
	)
	return env
```

With:

```text
	# Loaded here, not by the relative imports, so they leave sys.modules after the test.
	load_source(monkeypatch, package + ".utils", PLUGIN_DIR / "utils.py")
	alias_package(monkeypatch, package + ".panels", PLUGIN_DIR / "panels")
	env.panels = SimpleNamespace(
		**{
			name: load_source(monkeypatch, f"{package}.panels.{name}", PLUGIN_DIR / "panels" / f"{name}.py")
			for name in PANEL_MODULES
		},
	)
	env.module = load_source(monkeypatch, package + ".dialog", PLUGIN_DIR / "dialog.py")
	return env
```

**Edit:** `tests/ui_harness.py` (4/4)

Replace:

```text
	stubs.module(package + ".speechSettingsDialog", WorldVoiceSettingsDialog=env.settings_dialog)
```

With:

```text
	stubs.module(package + ".dialog", WorldVoiceSettingsDialog=env.settings_dialog)
```

**Edit:** `tests/test_ui_structure.py` (1/4)

Replace:

```text
DIALOG = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"
```

With:

```text
PLUGIN = ADDON / "globalPlugins/WorldVoice"
ROLE_PANEL = PLUGIN / "panels/role.py"
PIPELINE_PANEL = PLUGIN / "panels/pipeline.py"
```

**Edit:** `tests/test_ui_structure.py` (2/4)

Replace:

```text
	return load_definitions(DIALOG, ["SpeechRoleSettingsPanel.onSave"], env)["onSave"]
```

With:

```text
	return load_definitions(ROLE_PANEL, ["SpeechRoleSettingsPanel.onSave"], env)["onSave"]
```

**Edit:** `tests/test_ui_structure.py` (3/4)

Replace:

```text
def test_panels_apply_dependencies_through_one_path():
	# The depends_on loop and the controller read live in ui/controls.py; each panel passes in
	# only its own lookups.
	panels = {DIALOG: "SpeechPipelinePanel", VOICE_PANEL: "WorldVoiceVoiceSettingsPanel"}
	for path, cls in panels.items():
		tree = ast.parse(path.read_text(encoding="utf-8"))
		referred = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
			alias.asname or alias.name
			for n in ast.walk(tree)
			if isinstance(n, (ast.Import, ast.ImportFrom))
			for alias in n.names
		}
		assert referred & {"dependent_states", "ABSENT", "selected_value"} == set(), path.name
		apply = method(path, cls, "_applyDependencies")
```

With:

```text
def referred_names(path):
	tree = ast.parse(path.read_text(encoding="utf-8"))
	return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
		alias.asname or alias.name
		for n in ast.walk(tree)
		if isinstance(n, (ast.Import, ast.ImportFrom))
		for alias in n.names
	}


def test_panels_apply_dependencies_through_one_path():
	# The depends_on loop and the controller read live in ui/controls.py; each panel passes in
	# only its own lookups, and no other module of the settings UI reads dependencies itself.
	for path in [*PLUGIN.rglob("*.py"), VOICE_PANEL]:
		assert referred_names(path) & {"dependent_states", "ABSENT", "selected_value"} == set(), path.name
	panels = {PIPELINE_PANEL: "SpeechPipelinePanel", VOICE_PANEL: "WorldVoiceVoiceSettingsPanel"}
	for path, cls in panels.items():
		apply = method(path, cls, "_applyDependencies")
```

**Edit:** `tests/test_ui_structure.py` (4/4)

Replace:

```text
def test_settings_ui_asks_for_worldvoice_not_for_the_synth():
```

With:

```text
def test_panels_package_init_stays_empty():
	# As in the synth's packages (tests/test_runtime_import_guard.py): importing one panel module
	# must not load the others.
	assert (PLUGIN / "panels/__init__.py").read_bytes() == b""


def test_settings_ui_asks_for_worldvoice_not_for_the_synth():
```

**Edit:** `tests/test_role_guards.py` (1/2)

Replace:

```text
PANELS = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"


def test_error_callback_finds_its_dialog_without_a_class_registry():
	assert ".wvd" not in PANELS.read_text(encoding="utf-8")
```

With:

```text
PLUGIN = ADDON / "globalPlugins/WorldVoice"
ROLE_PANEL = PLUGIN / "panels/role.py"


def test_error_callback_finds_its_dialog_without_a_class_registry():
	for path in PLUGIN.rglob("*.py"):
		assert ".wvd" not in path.read_text(encoding="utf-8"), path.name
```

**Edit:** `tests/test_role_guards.py` (2/2)

Replace:

```text
	load_definitions(PANELS, ["got_error_callback"], environment)
```

With:

```text
	load_definitions(ROLE_PANEL, ["got_error_callback"], environment)
```

**Edit:** `tests/test_role_panel.py` (1/1)

Replace:

```text
PANEL = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"
```

With:

```text
PANEL = ADDON / "globalPlugins/WorldVoice/panels/role.py"
```

**Edit:** `tests/test_unicode_panel.py` (1/2)

Replace:

```text
PANEL = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"
```

With:

```text
PLUGIN = ADDON / "globalPlugins/WorldVoice"
PANEL = PLUGIN / "panels/detection.py"
```

**Edit:** `tests/test_unicode_panel.py` (2/2)

Replace:

```text
	# The panel needs the script table and the settings service, not the detector module.
	allowed = {
		"synthDrivers.WorldVoice.languageDetection.settings",
		"synthDrivers.WorldVoice.languageDetection.scriptLanguages",
	}
	for node in ast.walk(ast.parse(PANEL.read_text(encoding="utf-8"))):
		if isinstance(node, ast.ImportFrom):
			names = [node.module or "", *(f"{node.module}.{alias.name}" for alias in node.names)]
		elif isinstance(node, ast.Import):
			names = [alias.name for alias in node.names]
		else:
			continue
		if any("languageDetection" in name for name in names):
			assert isinstance(node, ast.ImportFrom) and node.module in allowed, ast.unparse(node)
```

With:

```text
	# The panel needs the script table and the settings service, not the detector module; no other
	# module of the settings UI imports more of languageDetection.
	allowed = {
		"synthDrivers.WorldVoice.languageDetection.settings",
		"synthDrivers.WorldVoice.languageDetection.scriptLanguages",
	}
	for path in PLUGIN.rglob("*.py"):
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
			if isinstance(node, ast.ImportFrom):
				names = [node.module or "", *(f"{node.module}.{alias.name}" for alias in node.names)]
			elif isinstance(node, ast.Import):
				names = [alias.name for alias in node.names]
			else:
				continue
			if any("languageDetection" in name for name in names):
				assert isinstance(node, ast.ImportFrom) and node.module in allowed, ast.unparse(node)
```

**Edit:** `tests/test_settings_panel_save.py` (1/2)

Replace:

```text
PANEL_PATH = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"
```

With:

```text
PANELS = ADDON / "globalPlugins/WorldVoice/panels"
```

**Edit:** `tests/test_settings_panel_save.py` (2/2)

Replace:

```text
	load_definitions(PANEL_PATH, ["BaseSettingsPanel", "SpeechEngineSettingsPanel"], environment)
```

With:

```text
	load_definitions(PANELS / "base.py", ["BaseSettingsPanel"], environment)
	load_definitions(PANELS / "engine.py", ["SpeechEngineSettingsPanel"], environment)
```

**Edit:** `tests/test_pipeline_log.py` (1/1)

Replace:

```text
PANEL = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"
```

With:

```text
PANEL = ADDON / "globalPlugins/WorldVoice/panels/log.py"
```

**Edit:** `tests/test_pipeline_panels.py` (1/8)

Replace:

```text
PANELS = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"
```

With:

```text
PLUGIN = ADDON / "globalPlugins/WorldVoice"
# The settings dialog and its panels.
DIALOG_FILES = (PLUGIN / "dialog.py", *sorted((PLUGIN / "panels").glob("*.py")))
```

**Edit:** `tests/test_pipeline_panels.py` (2/8)

Replace:

```text
	assert list(load_settings_dialog(monkeypatch).module._LOG_LABELS) == LOG_SWITCH_ORDER
```

With:

```text
	assert list(load_settings_dialog(monkeypatch).panels.log._LOG_LABELS) == LOG_SWITCH_ORDER
```

**Edit:** `tests/test_pipeline_panels.py` (3/8)

Replace:

```text
	labels = load_settings_dialog(monkeypatch).module._LOG_LABELS
```

With:

```text
	labels = load_settings_dialog(monkeypatch).panels.log._LOG_LABELS
```

**Edit:** `tests/test_pipeline_panels.py` (4/8)

Replace:

```text
	labels = env.module._LOG_LABELS
	table = {spec.key: spec for spec in env.module.PIPELINE_SETTINGS}
```

With:

```text
	labels = env.panels.log._LOG_LABELS
	table = {spec.key: spec for spec in env.panels.log.PIPELINE_SETTINGS}
```

**Edit:** `tests/test_pipeline_panels.py` (5/8)

Replace:

```text
	updates = []
	module = load_settings_dialog(monkeypatch).module
```

With:

```text
	updates = []
	module = load_settings_dialog(monkeypatch).panels.pipeline
```

**Edit:** `tests/test_pipeline_panels.py` (6/8)

Replace:

```text
	# The string constant of every _() call in the dialog.
	tree = ast.parse(PANELS.read_text(encoding="utf-8"))
	return {
		node.args[0].value
		for node in ast.walk(tree)
```

With:

```text
	# The string constant of every _() call in the dialog and its panels.
	return {
		node.args[0].value
		for path in DIALOG_FILES
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
```

**Edit:** `tests/test_pipeline_panels.py` (7/8)

Replace:

```text
	module = load_settings_dialog(monkeypatch).module
	table = {spec.key: spec for spec in module.PIPELINE_SETTINGS}
```

With:

```text
	module = load_settings_dialog(monkeypatch).panels.log
	table = {spec.key: spec for spec in module.PIPELINE_SETTINGS}
```

**Edit:** `tests/test_pipeline_panels.py` (8/8)

Replace:

```text
	module = load_settings_dialog(monkeypatch).module
	table = {spec.key for spec in module.PIPELINE_SETTINGS}
```

With:

```text
	module = load_settings_dialog(monkeypatch).panels.log
	table = {spec.key for spec in module.PIPELINE_SETTINGS}
```

**Edit:** `tests/test_settings_panels.py` (1/4)

Replace:

```text
	env.module.PIPELINE_SETTINGS = tuple(
```

With:

```text
	env.panels.pipeline.PIPELINE_SETTINGS = tuple(
```

**Edit:** `tests/test_settings_panels.py` (2/4)

Replace:

```text
	labels = env.module._LOG_LABELS
```

With:

```text
	labels = env.panels.log._LOG_LABELS
```

**Edit:** `tests/test_settings_panels.py` (3/4)

Replace:

```text
	monkeypatch.setattr(env.module, "pipeline_log", service_module.PipelineLogService(lambda: env.conf))
```

With:

```text
	monkeypatch.setattr(env.panels.log, "pipeline_log", service_module.PipelineLogService(lambda: env.conf))
```

**Edit:** `tests/test_settings_panels.py` (4/4)

Replace:

```text
	class Panel(env.module.BaseSettingsPanel):
```

With:

```text
	class Panel(env.panels.base.BaseSettingsPanel):
```

**Edit:** `tests/test_role_panel_ui.py` (1/1)

Replace:

```text
	monkeypatch.setattr(env.module, "RolePanelPresenter", Presenter)
```

With:

```text
	monkeypatch.setattr(env.panels.role, "RolePanelPresenter", Presenter)
```

**Edit:** `tests/test_settings_order.py` (1/1)

Replace:

```text
	specs = env.module.panel_specs(env.module.PIPELINE_SETTINGS, "pipeline")
	controls = {spec.key: getattr(panel, env.module.pipeline_attribute(spec)) for spec in specs}
```

With:

```text
	specs = env.panels.pipeline.panel_specs(env.panels.pipeline.PIPELINE_SETTINGS, "pipeline")
	controls = {spec.key: getattr(panel, env.panels.pipeline.pipeline_attribute(spec)) for spec in specs}
```

```bash
$SCRATCH/runtests.sh . tests/test_translator_comments.py tests/test_ui_structure.py tests/test_role_guards.py tests/test_role_panel.py tests/test_unicode_panel.py tests/test_settings_panel_save.py tests/test_pipeline_log.py tests/test_pipeline_panels.py tests/test_settings_panels.py tests/test_role_panel_ui.py tests/test_settings_order.py tests/test_global_plugin_menu.py tests/test_global_plugin_lifecycle.py tests/test_guard_errors.py 2>&1 | tail -1
```

Expected (red): `116 failed, 46 passed, 14 errors` — the loaders and `load_definitions` look for `dialog.py` and `panels/*.py`, which do not exist yet, and `__init__.py` still imports `.speechSettingsDialog`, which the global-plugin harness no longer stubs.

- [ ] **Step 3: Split the module with the script, and import the dialog from its new home**

**File:** `$SCRATCH/split_dialog.py` (not committed)

```python
"""Split addon/globalPlugins/WorldVoice/speechSettingsDialog.py into dialog.py and panels/ (phase 42).

Usage: python3 -I split_dialog.py <repository root>

Every top-level definition of the old module moves verbatim, with the comment lines right above
it, into the module named in MODULES, in its original order; each module gets the fixed HEADERS
text. Definitions with no blank line between them stay one chunk. The imports and the
initTranslation() call are dropped: each header restates the ones its module needs. The old
module is deleted and panels/__init__.py is written empty. The script refuses any input other
than the file it was written for.
"""

import ast
import hashlib
import sys
from pathlib import Path

INPUT_SHA256 = "b79ba33dc2aad15f6c1c658b45bec4dd2792741602fb82cd383a829afabaab2a"

MODULES = {
	"panels/base.py": ["_as_bool", "BaseSettingsPanel"],
	"panels/pipeline.py": ["SpeechPipelinePanel"],
	"panels/role.py": ["got_error_callback", "SpeechRoleSettingsPanel"],
	"panels/detection.py": ["UnicodeDetectionSettingsPanel"],
	"panels/engine.py": ["SpeechEngineSettingsPanel"],
	"panels/log.py": ["_STAGE_LOG_LABELS", "_SETTING_NAMES", "_LOG_LABELS", "LogSettingsPanel"],
	"dialog.py": ["WorldVoiceSettingsDialog"],
}

HEADERS = {
	"panels/base.py": '''"""Shared parts of the WorldVoice settings panels."""

from collections import OrderedDict

import addonHandler
import config
import tones
import wx
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel
from logHandler import log
from synthDrivers.WorldVoice.pipeline.settings import read_stored

addonHandler.initTranslation()
''',
	"panels/pipeline.py": '''"""The Speech Pipeline panel, built from the pipeline settings table."""

import addonHandler
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel
from synthDrivers.WorldVoice.pipeline.settings import PIPELINE_SETTINGS, pipeline_settings
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
)

addonHandler.initTranslation()
''',
	"panels/role.py": '''"""The Speech Role panel: the wx side of RolePanelPresenter."""

import addonHandler
import config
import gui
import wx
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel
from logHandler import log
from synthDrivers.WorldVoice.pipeline.context import worldvoice_synth

from ..rolePresenter import RolePanelPresenter
from ..utils import guard_errors

addonHandler.initTranslation()
''',
	"panels/detection.py": '''"""The Unicode Detection panel: the language assumed for each script of the detection table."""

import addonHandler
import wx
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel
from synthDrivers.WorldVoice.languageDetection.scriptLanguages import DETECTION_SCRIPTS, SCRIPT_LANGUAGES
from synthDrivers.WorldVoice.languageDetection.settings import detection_settings
from synthDrivers.WorldVoice.pipeline.context import worldvoice_synth

addonHandler.initTranslation()
''',
	"panels/engine.py": '''"""The Speech Engine panel: which engines WorldVoice loads, applied by restarting NVDA."""

from collections import OrderedDict

import addonHandler
import config
import core
import gui
import queueHandler
import wx
from synthDrivers.WorldVoice.engineRegistry import ENGINE_SPECS, get_engine_enabled

from .base import BaseSettingsPanel

addonHandler.initTranslation()
''',
	"panels/log.py": '''"""The Log Record panel: the speech pipeline log and a switch for each logged stage."""

from collections import OrderedDict

import addonHandler
import wx
from synthDrivers.WorldVoice.pipeline.registry import LOG_SWITCHES
from synthDrivers.WorldVoice.pipeline.settings import PIPELINE_SETTINGS

from ..pipelineLog import ask_export, confirm_enable, pipeline_log
from .base import BaseSettingsPanel

addonHandler.initTranslation()
''',
	"dialog.py": '''"""The WorldVoice settings dialog and the panels it offers."""

import addonHandler
from gui.settingsDialogs import MultiCategorySettingsDialog
from synthDrivers.WorldVoice.pipeline.context import worldvoice_synth

from .panels.detection import UnicodeDetectionSettingsPanel
from .panels.engine import SpeechEngineSettingsPanel
from .panels.log import LogSettingsPanel
from .panels.pipeline import SpeechPipelinePanel
from .panels.role import SpeechRoleSettingsPanel

addonHandler.initTranslation()
''',
}


def defined_names(node):
	if isinstance(node, ast.ClassDef | ast.FunctionDef):
		return (node.name,)
	if isinstance(node, ast.Assign):
		return tuple(target.id for target in node.targets)
	return ()


def dropped(node):
	if isinstance(node, ast.Import | ast.ImportFrom):
		return True
	return isinstance(node, ast.Expr) and ast.unparse(node) == "addonHandler.initTranslation()"


def chunks(source):
	"""(names, text) of each run of top-level statements with no blank line between them."""
	lines = source.split("\n")
	runs = []
	for node in ast.parse(source).body:
		start = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))]) - 1
		while start > 0 and lines[start - 1].lstrip().startswith("#"):
			start -= 1
		if runs and runs[-1]["end"] == start:
			runs[-1]["nodes"].append(node)
			runs[-1]["end"] = node.end_lineno
		else:
			runs.append({"start": start, "end": node.end_lineno, "nodes": [node]})
	for run in runs:
		nodes = run["nodes"]
		if all(dropped(node) for node in nodes):
			continue
		if any(dropped(node) for node in nodes):
			sys.exit(f"line {run['start'] + 1}: an import shares a chunk with a definition")
		names = [name for node in nodes for name in defined_names(node)]
		yield names, "\n".join(lines[run["start"] : run["end"]])


def main():
	root = Path(sys.argv[1])
	plugin = root / "addon/globalPlugins/WorldVoice"
	old = plugin / "speechSettingsDialog.py"
	data = old.read_bytes()
	if hashlib.sha256(data).hexdigest() != INPUT_SHA256:
		sys.exit(f"{old} is not the file this script was written for")
	owner = {name: module for module, names in MODULES.items() for name in names}
	texts = {module: [] for module in MODULES}
	seen = []
	for names, text in chunks(data.decode("utf-8")):
		(module,) = {owner[name] for name in names}
		texts[module].append(text)
		seen.extend(names)
	if sorted(seen) != sorted(owner):
		sys.exit(f"definitions do not match MODULES: {sorted(set(seen) ^ set(owner))}")
	(plugin / "panels").mkdir()
	(plugin / "panels/__init__.py").write_bytes(b"")
	for module, parts in texts.items():
		text = HEADERS[module] + "\n\n" + "\n\n\n".join(parts) + "\n"
		(plugin / module).write_text(text, encoding="utf-8", newline="\n")
	old.unlink()


main()
```

```bash
python3 -I $SCRATCH/split_dialog.py .
git status --short addon/globalPlugins
```

Expected:

```text
 D addon/globalPlugins/WorldVoice/speechSettingsDialog.py
?? addon/globalPlugins/WorldVoice/dialog.py
?? addon/globalPlugins/WorldVoice/panels/
```

**Edit:** `addon/globalPlugins/WorldVoice/__init__.py` (1/1)

Replace:

```text
from .pipelineLog import ask_disable_on_start, ask_export, confirm_enable, pipeline_log
from .speechSettingsDialog import WorldVoiceSettingsDialog
```

With:

```text
from .dialog import WorldVoiceSettingsDialog
from .pipelineLog import ask_disable_on_start, ask_export, confirm_enable, pipeline_log
```

```bash
$SCRATCH/runtests.sh . tests/test_translator_comments.py tests/test_ui_structure.py tests/test_role_guards.py tests/test_role_panel.py tests/test_unicode_panel.py tests/test_settings_panel_save.py tests/test_pipeline_log.py tests/test_pipeline_panels.py tests/test_settings_panels.py tests/test_role_panel_ui.py tests/test_settings_order.py tests/test_global_plugin_menu.py tests/test_global_plugin_lifecycle.py tests/test_guard_errors.py 2>&1 | tail -3
```

Expected (red, only the template guard): `FAILED tests/test_translator_comments.py::test_every_translated_module_is_a_pot_source` and `1 failed, 175 passed`.

- [ ] **Step 4: Hand the panels to `scons pot`**

**Edit:** `buildVars.py` (1/1)

Replace:

```text
	'addon/globalPlugins/*/*.py',
```

With:

```text
	'addon/globalPlugins/*/*.py',
	'addon/globalPlugins/*/*/*.py',
```

```bash
$SCRATCH/runtests.sh . tests/test_translator_comments.py tests/test_ui_structure.py tests/test_role_guards.py tests/test_role_panel.py tests/test_unicode_panel.py tests/test_settings_panel_save.py tests/test_pipeline_log.py tests/test_pipeline_panels.py tests/test_settings_panels.py tests/test_role_panel_ui.py tests/test_settings_order.py tests/test_global_plugin_menu.py tests/test_global_plugin_lifecycle.py tests/test_guard_errors.py 2>&1 | tail -1
```

Expected: `176 passed`.

- [ ] **Step 5: Probe (not committed): the catalog guard sees a split module without `initTranslation()`**

```bash
cp addon/globalPlugins/WorldVoice/panels/role.py $SCRATCH/role.py.keep
sed -i '/^addonHandler.initTranslation()$/d' addon/globalPlugins/WorldVoice/panels/role.py
$SCRATCH/runtests.sh . tests/test_translator_comments.py 2>&1 | grep -E "^E  +(Right contains|At index)|passed|failed"
cp $SCRATCH/role.py.keep addon/globalPlugins/WorldVoice/panels/role.py
rm $SCRATCH/role.py.keep
```

Expected: `E      At index 0 diff: 'globalPlugins/WorldVoice/panels/role.py' != 'globalPlugins/WorldVoice/utils.py'` and `1 failed, 5 passed`; afterwards `git status --short addon/globalPlugins` still shows only the three lines of Step 3 plus ` M addon/globalPlugins/WorldVoice/__init__.py`.

- [ ] **Step 6: Check that the split is a pure move**

**File:** `$SCRATCH/check_move.py` (not committed)

```python
"""Check that the new modules hold the old speechSettingsDialog.py and add only module headers.

Usage: python3 -I check_move.py <repository root> <base commit>

Compares the non-blank lines of the old module at the base commit with those of dialog.py and
the panel modules in the working tree: every line either survives the split or is a header line
(a module docstring, an import line or the initTranslation() call).
"""

import subprocess
import sys
from collections import Counter
from pathlib import Path

PLUGIN = "addon/globalPlugins/WorldVoice/"
MODULES = ["dialog.py", *(f"panels/{name}.py" for name in ("base", "pipeline", "role", "detection", "engine", "log"))]


def header(line):
	return line.startswith(('"""', "import ", "from ")) or line == "addonHandler.initTranslation()"


def main():
	root, base = sys.argv[1:]
	old = subprocess.run(
		["git", "-C", root, "show", f"{base}:{PLUGIN}speechSettingsDialog.py"],
		capture_output=True,
		text=True,
		check=True,
	).stdout
	new = "".join((Path(root) / PLUGIN / module).read_text(encoding="utf-8") for module in MODULES)
	before = Counter(line for line in old.splitlines() if line.strip())
	after = Counter(line for line in new.splitlines() if line.strip())
	removed = sorted((before - after).elements())
	added = sorted((after - before).elements())
	print(f"{len(removed)} old lines not kept, {len(added)} lines added")
	other = [line for line in removed + added if not header(line)]
	print("pure move: OK" if not other else f"not a pure move: {other}")


main()
```

```bash
python3 -I $SCRATCH/check_move.py . a7bd115
```

Expected:

```text
5 old lines not kept, 52 lines added
pure move: OK
```

The five are the old module's import lines that no new module repeats word for word (`MultiCategorySettingsDialog, SettingsPanel`, the three-name `pipeline.settings` import and the three single-dot relative imports); the 52 are the seven module docstrings and the header imports and `initTranslation()` calls.

- [ ] **Step 7: Run the suite and commit**

```bash
$SCRATCH/runtests.sh . tests 2>&1 | tail -1
```

Expected: `3263 passed` (3260 + `test_every_translated_module_installs_the_add_on_catalog`, `test_every_translated_module_is_a_pot_source`, `test_panels_package_init_stays_empty`).

```bash
git add addon/globalPlugins/WorldVoice/__init__.py addon/globalPlugins/WorldVoice/speechSettingsDialog.py addon/globalPlugins/WorldVoice/dialog.py addon/globalPlugins/WorldVoice/panels/__init__.py addon/globalPlugins/WorldVoice/panels/base.py addon/globalPlugins/WorldVoice/panels/pipeline.py addon/globalPlugins/WorldVoice/panels/role.py addon/globalPlugins/WorldVoice/panels/detection.py addon/globalPlugins/WorldVoice/panels/engine.py addon/globalPlugins/WorldVoice/panels/log.py buildVars.py tests/test_translator_comments.py tests/ui_harness.py tests/test_ui_structure.py tests/test_role_guards.py tests/test_role_panel.py tests/test_unicode_panel.py tests/test_settings_panel_save.py tests/test_pipeline_log.py tests/test_pipeline_panels.py tests/test_settings_panels.py tests/test_role_panel_ui.py tests/test_settings_order.py
git diff --cached --stat | tail -1
git commit -q -m "refactor: split the settings dialog into panels" -m "speechSettingsDialog.py held six settings panels and the dialog in 737 lines. Each panel now has its own module under panels/ and the dialog lives in dialog.py; every definition moved verbatim, and each module names only the imports it uses and installs the add-on's translations itself. buildVars.py hands the new subpackage to scons pot. New guards check that every translated module calls initTranslation() and is a pot source, and that panels/__init__.py stays empty (phase 42 spec, goal 1)."
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: the stat line `23 files changed, 938 insertions(+), 798 deletions(-)`; every hook Passed (yaml Skipped); `git status --short` prints nothing.

Expected after the commit: `HEAD:addon` = `8bdac220145f2f7af3c8ad752342608295cd0161`, `HEAD:tests` = `f1c758abe508fd695cc9f114a7a38a7d1319a001`

---

### Task 2: Share the "not WorldVoice" notice

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/panels/base.py` (new `notWorldVoiceNotice`), `addon/globalPlugins/WorldVoice/panels/role.py`, `addon/globalPlugins/WorldVoice/panels/detection.py`
- Test: `tests/test_ui_structure.py`, `tests/test_settings_panels.py`

**Interfaces:**
- Consumes: Task 1's modules.
- Produces: `panels.base.notWorldVoiceNotice(panel, sizer) -> None` — adds to `sizer` a `wx.TextCtrl(panel, value=_("Your current speech synthesizer is not WorldVoice."), style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE)` with the panel's background colour, `proportion=1`, `flag=wx.EXPAND`. `tests/test_ui_structure.string_constants(text) -> list[str]`.

- [ ] **Step 1: Write the tests**

**Edit:** `tests/test_ui_structure.py` (1/2)

Replace:

```text
VOICE_PANEL = WORLDVOICE / "ui/voicePanel.py"
```

With:

```text
VOICE_PANEL = WORLDVOICE / "ui/voicePanel.py"
NOT_WORLDVOICE = "Your current speech synthesizer is not WorldVoice."
```

**Edit:** `tests/test_ui_structure.py` (2/2)

Replace:

```text
def test_settings_ui_asks_for_worldvoice_not_for_the_synth():
```

With:

```text
def string_constants(text):
	"""Where the global plugin writes the string text: its module, relative to the plugin, per copy."""
	return [
		path.relative_to(PLUGIN).as_posix()
		for path in sorted(PLUGIN.rglob("*.py"))
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
		if isinstance(node, ast.Constant) and node.value == text
	]


def test_panels_share_the_not_worldvoice_notice():
	# The Speech Role and Unicode Detection panels show the same notice for another synthesizer;
	# one copy keeps the two from drifting apart.
	assert string_constants(NOT_WORLDVOICE) == ["panels/base.py"]


def test_settings_ui_asks_for_worldvoice_not_for_the_synth():
```

**Edit:** `tests/test_settings_panels.py` (1/1)

Replace:

```text
	panel.onSave()  # detection_settings is None in this harness: saving must not reach it
```

With:

```text
	panel.onSave()  # detection_settings is None in this harness: saving must not reach it


@pytest.mark.parametrize("name", ["SpeechRoleSettingsPanel", "UnicodeDetectionSettingsPanel"])
def test_panels_for_another_synth_show_the_same_read_only_notice(monkeypatch, name):
	env = load_settings_dialog(monkeypatch, synth=SimpleNamespace(name="espeak"))
	wx = env.wx
	panel, sizer = build(env, name)
	(item,) = sizer.items
	info = item.item
	assert isinstance(info, TextCtrl) and info.parent is panel
	assert info.value == "Your current speech synthesizer is not WorldVoice."
	assert info.kwargs == {"style": wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE}
	assert info.background == "panel colour"
	assert (item.proportion, item.flag, item.border) == (1, wx.EXPAND, 0)
```

```bash
$SCRATCH/runtests.sh . tests/test_ui_structure.py tests/test_settings_panels.py 2>&1 | tail -3
```

Expected (red): `FAILED tests/test_ui_structure.py::test_panels_share_the_not_worldvoice_notice` and `1 failed, 76 passed` — the guard finds `['panels/detection.py', 'panels/role.py']`; the two characterization cases already pass.

- [ ] **Step 2: Add the helper and use it in both panels**

**Edit:** `addon/globalPlugins/WorldVoice/panels/base.py` (1/1)

Replace:

```text
			log.error("WorldVoice: failed to save %s settings", self.field, exc_info=True)
			tones.beep(100, 100)
			return False
		return True
```

With:

```text
			log.error("WorldVoice: failed to save %s settings", self.field, exc_info=True)
			tones.beep(100, 100)
			return False
		return True


def notWorldVoiceNotice(panel, sizer):
	"""Show the read-only note that WorldVoice is not the synthesizer in a panel that needs it."""
	infoCtrl = wx.TextCtrl(
		panel,
		# Translators: Shown in place of a settings panel that needs WorldVoice as the speech synthesizer.
		value=_("Your current speech synthesizer is not WorldVoice."),
		style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE,
	)
	infoCtrl.SetBackgroundColour(panel.GetBackgroundColour())
	sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)
```

**Edit:** `addon/globalPlugins/WorldVoice/panels/role.py` (1/2)

Replace:

```text
from ..utils import guard_errors
```

With:

```text
from ..utils import guard_errors
from .base import notWorldVoiceNotice
```

**Edit:** `addon/globalPlugins/WorldVoice/panels/role.py` (2/2)

Replace:

```text
		if synth is None:
			infoCtrl = wx.TextCtrl(
				self,
				value=_("Your current speech synthesizer is not WorldVoice."),
				style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE,
			)
			infoCtrl.SetBackgroundColour(self.GetBackgroundColour())
			sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)
			self.disable = True
```

With:

```text
		if synth is None:
			notWorldVoiceNotice(self, sizer)
			self.disable = True
```

**Edit:** `addon/globalPlugins/WorldVoice/panels/detection.py` (1/2)

Replace:

```text
from synthDrivers.WorldVoice.pipeline.context import worldvoice_synth
```

With:

```text
from synthDrivers.WorldVoice.pipeline.context import worldvoice_synth

from .base import notWorldVoiceNotice
```

**Edit:** `addon/globalPlugins/WorldVoice/panels/detection.py` (2/2)

Replace:

```text
		if synth is None:
			infoCtrl = wx.TextCtrl(
				self,
				value=_("Your current speech synthesizer is not WorldVoice."),
				style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE,
			)
			infoCtrl.SetBackgroundColour(self.GetBackgroundColour())
			sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)
			self.disable = True
```

With:

```text
		if synth is None:
			notWorldVoiceNotice(self, sizer)
			self.disable = True
```

```bash
$SCRATCH/runtests.sh . tests/test_ui_structure.py tests/test_settings_panels.py tests/test_role_panel.py tests/test_role_panel_ui.py tests/test_unicode_panel.py tests/test_translator_comments.py 2>&1 | tail -1
```

Expected: `111 passed`.

- [ ] **Step 3: Run the suite and commit**

```bash
$SCRATCH/runtests.sh . tests 2>&1 | tail -1
```

Expected: `3266 passed` (+ `test_panels_share_the_not_worldvoice_notice` and the two characterization cases).

```bash
git add addon/globalPlugins/WorldVoice/panels/base.py addon/globalPlugins/WorldVoice/panels/role.py addon/globalPlugins/WorldVoice/panels/detection.py tests/test_ui_structure.py tests/test_settings_panels.py
git diff --cached --stat | tail -1
git commit -q -m "refactor: share the not-WorldVoice notice" -m "The Speech Role and Unicode Detection panels built the same read-only notice for another synthesizer. panels/base.py now builds it once in notWorldVoiceNotice; a guard keeps the string to one copy and a test pins the control both panels show (phase 42 spec, goal 2)."
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `5 files changed, 48 insertions(+), 14 deletions(-)`; every hook Passed; clean status.

Expected after the commit: `HEAD:addon` = `db934584e8c0a5de4f42fa7f350de1adb3c7afae`, `HEAD:tests` = `bc002dfddc972791ed816a9a2bc32d57dfc3695c`

---

### Task 3: Share the settings error dialog (gated on spec §9 question 1, option (a))

Do not start this task until the orchestrator relays the user's choice of option (a). With option (b) the task is dropped (a `Ruling:` in the ledger) and Task 2's tree ids are the final ones.

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/utils.py` (new `reportError`, `initTranslation()`), `addon/globalPlugins/WorldVoice/panels/role.py`
- Test: `tests/test_translator_comments.py`, `tests/test_ui_structure.py`, `tests/test_role_panel_ui.py`, `tests/test_role_panel.py`

**Interfaces:**
- Consumes: Task 2's modules.
- Produces: `utils.reportError(error) -> None` — `gui.messageBox(<the existing message with Details: str(error)>, "WorldVoice Setting Dialog - Error", wx.OK | wx.ICON_ERROR)`; `guard_errors` and `SpeechRoleSettingsPanel.onSave` call it.

- [ ] **Step 1: Write the tests**

**Edit:** `tests/test_translator_comments.py` (1/2)

Replace:

```text
GETTEXT_NAMES = {"_", "pgettext", "ngettext", "npgettext"}
# Modules that call _() without addonHandler.initTranslation(): the _ they reach is NVDA's own
# catalog, which has none of their strings, so NVDA shows those in English.
UNTRANSLATED = ("globalPlugins/WorldVoice/utils.py",)
```

With:

```text
GETTEXT_NAMES = {"_", "pgettext", "ngettext", "npgettext"}
```

**Edit:** `tests/test_translator_comments.py` (2/2)

Replace:

```text
	# initTranslation() sets _ in the calling module only, so a module split off another needs its own.
	missing = [
		relative
		for relative, _path, tree in _translated_modules()
		if "addonHandler.initTranslation()" not in {ast.unparse(node) for node in tree.body}
	]
	assert missing == list(UNTRANSLATED)
```

With:

```text
	# initTranslation() sets _ in the calling module only, so a module split off another needs its own.
	# Without it, _ is NVDA's own catalog, which has none of the add-on's strings: NVDA shows them in
	# English.
	missing = [
		relative
		for relative, _path, tree in _translated_modules()
		if "addonHandler.initTranslation()" not in {ast.unparse(node) for node in tree.body}
	]
	assert missing == []
```

**Edit:** `tests/test_ui_structure.py` (1/2)

Replace:

```text
NOT_WORLDVOICE = "Your current speech synthesizer is not WorldVoice."
```

With:

```text
NOT_WORLDVOICE = "Your current speech synthesizer is not WorldVoice."
ERROR_MESSAGE = (
	"An unexpected error occurred while processing your action.\n\n"
	"Details: {err}\n\n"
	"A full stack trace has been written to the NVDA log."
)
ERROR_TITLE = "WorldVoice Setting Dialog - Error"
```

**Edit:** `tests/test_ui_structure.py` (2/2)

Replace:

```text
def test_settings_ui_asks_for_worldvoice_not_for_the_synth():
```

With:

```text
def test_settings_errors_share_one_dialog():
	# A failing handler (guard_errors) and a failed Speech Role save show the same error dialog.
	assert string_constants(ERROR_MESSAGE) == ["utils.py"]
	assert string_constants(ERROR_TITLE) == ["utils.py"]


def test_settings_ui_asks_for_worldvoice_not_for_the_synth():
```

**Edit:** `tests/test_role_panel_ui.py` (1/1)

Replace:

```text
def test_save_applies_the_pending_edits(ui):
	ui.panel.onSave()
	assert ui.presenter.calls == [("apply",)]
```

With:

```text
def test_save_applies_the_pending_edits(ui):
	ui.panel.onSave()
	assert ui.presenter.calls == [("apply",)]


def test_a_failed_save_reports_the_error_and_keeps_the_dialog_open(ui):
	def broken():
		raise OSError("disk full")

	ui.presenter.apply = broken
	with pytest.raises(ValueError):  # NVDA keeps its settings dialog open only on ValueError
		ui.panel.onSave()

	((message, caption, style),) = ui.env.shown
	assert message.startswith("An unexpected error occurred while processing your action.")
	assert "Details: disk full" in message
	assert caption == "WorldVoice Setting Dialog - Error"
	assert style == ui.env.wx.OK | ui.env.wx.ICON_ERROR
	assert ("error", "Failed to save voice settings") in ui.env.logged
```

**Edit:** `tests/test_role_panel.py` (1/2)

Replace:

```text
			"guard_errors": lambda **kwargs: lambda method: method,
			"got_error_callback": None,
			"wx": types.SimpleNamespace(OK=1, ICON_ERROR=2),
			"gui": types.SimpleNamespace(messageBox=lambda *args: messages.append(args)),
			"log": types.SimpleNamespace(error=lambda *args, **kwargs: logged.append(args)),
```

With:

```text
			"guard_errors": lambda **kwargs: lambda method: method,
			"got_error_callback": None,
			"reportError": messages.append,
			"log": types.SimpleNamespace(error=lambda *args, **kwargs: logged.append(args)),
```

**Edit:** `tests/test_role_panel.py` (2/2)

Replace:

```text
	assert messages and "save failed" in messages[0][0]
```

With:

```text
	assert [str(error) for error in messages] == ["save failed"]
```

```bash
$SCRATCH/runtests.sh . tests/test_ui_structure.py tests/test_translator_comments.py tests/test_role_panel.py tests/test_role_panel_ui.py tests/test_guard_errors.py 2>&1 | tail -5
```

Expected (red): `3 failed, 37 passed` — `test_settings_errors_share_one_dialog` (two copies: `panels/role.py`, `utils.py`), `test_every_translated_module_installs_the_add_on_catalog` (`utils.py` listed), `test_failed_apply_shows_error_and_raises_value_error` (`NameError` for `gui`, which the test no longer supplies); `test_a_failed_save_reports_the_error_and_keeps_the_dialog_open` already passes.

- [ ] **Step 2: Add `reportError` and use it in both places**

**Edit:** `addon/globalPlugins/WorldVoice/utils.py` (1/2)

Replace:

```text
from functools import wraps

import gui
import wx
from logHandler import log


def guard_errors(callback=None):
```

With:

```text
from functools import wraps

import addonHandler
import gui
import wx
from logHandler import log

addonHandler.initTranslation()


def reportError(error):
	"""Show the settings error dialog for error; the caller has written the stack trace to the log."""
	gui.messageBox(
		# Translators: The message of the dialog shown when a WorldVoice settings action fails.
		_(
			"An unexpected error occurred while processing your action.\n\n"
			"Details: {err}\n\n"
			"A full stack trace has been written to the NVDA log.",
		).format(err=str(error)),
		# Translators: The title of the dialog shown when a WorldVoice settings action fails.
		_("WorldVoice Setting Dialog - Error"),
		wx.OK | wx.ICON_ERROR,
	)


def guard_errors(callback=None):
```

**Edit:** `addon/globalPlugins/WorldVoice/utils.py` (2/2)

Replace:

```text
				# show a modal error dialog
				gui.messageBox(
					# Body text
					_(
						"An unexpected error occurred while processing your action.\n\n"
						"Details: {err}\n\n"
						"A full stack trace has been written to the NVDA log.",
					).format(err=str(e)),
					# Caption
					_("WorldVoice Setting Dialog - Error"),
					# Style flags
					wx.OK | wx.ICON_ERROR,
				)
```

With:

```text
				# show a modal error dialog
				reportError(e)
```

**Edit:** `addon/globalPlugins/WorldVoice/panels/role.py` (1/2)

Replace:

```text
from ..utils import guard_errors
```

With:

```text
from ..utils import guard_errors, reportError
```

**Edit:** `addon/globalPlugins/WorldVoice/panels/role.py` (2/2)

Replace:

```text
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
```

With:

```text
			log.error("Failed to save voice settings", exc_info=True)
			reportError(error)
```

```bash
$SCRATCH/runtests.sh . tests/test_ui_structure.py tests/test_translator_comments.py tests/test_role_panel.py tests/test_role_panel_ui.py tests/test_guard_errors.py 2>&1 | tail -1
```

Expected: `40 passed`.

- [ ] **Step 3: Run the suite and commit**

```bash
$SCRATCH/runtests.sh . tests 2>&1 | tail -1
```

Expected: `3268 passed` (+ `test_settings_errors_share_one_dialog`, `test_a_failed_save_reports_the_error_and_keeps_the_dialog_open`).

```bash
git add addon/globalPlugins/WorldVoice/utils.py addon/globalPlugins/WorldVoice/panels/role.py tests/test_translator_comments.py tests/test_ui_structure.py tests/test_role_panel_ui.py tests/test_role_panel.py
git diff --cached --stat | tail -1
git commit -q -m "fix: share the settings error dialog and translate it" -m "guard_errors and the Speech Role save built the same error dialog; utils.py now builds it once in reportError. utils.py never installed the add-on's translations, so the dialog of a failing Speech Role handler was English in every language although every catalog translates it; it now calls initTranslation() like every other translated module (phase 42 spec, goal 4 and section 9)."
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `6 files changed, 54 insertions(+), 29 deletions(-)`; every hook Passed; clean status.

Expected after the commit: `HEAD:addon` = `b62ed75314a91f666f195771ec025f77886d128c`, `HEAD:tests` = `76da7b1ca08375c278df4dd9b6b67477ca5f2574`

---

### Task 4: Full verification (DEVELOPMENT_WORKFLOW.md §7)

**Files:** none.

**Interfaces:**
- Consumes: Task 3's tree (or Task 2's while Task 3 waits for the user).
- Produces: the verification record of the hand-off.

- [ ] **Step 1: Run every check**

```bash
$SCRATCH/runtests.sh . tests 2>&1 | tail -1
prek run --all-files
git diff --check a7bd115
git diff --stat a7bd115 -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
git grep -n "speechSettingsDialog" -- addon ':!addon/locale' tests buildVars.py pyproject.toml
git rev-parse HEAD:addon HEAD:tests
```

Expected: `3268 passed` after Task 3 (`3266 passed` after Task 2), 0 skipped; every hook Passed; the `git diff --check`, protected-path, Neural and `git grep` commands print nothing; the tree ids are Task 3's (or Task 2's). The catalogs' `#:` source references in `addon/locale/*/LC_MESSAGES/nvda.po` still name `speechSettingsDialog.py`; `scons pot` and the translators' merge rewrite them, so they are not edited by hand (spec §7). `git diff --color-moved=dimmed-zebra HEAD~N HEAD~N+1` of the Task 1 commit shows the panels as moved lines apart from the module headers.

---

## Dry run record

2026-10-27, fresh clone of `/workspace/WorldVoice` at `a7bd115` in the scratchpad (`ref` symlinked, `prek install`), every step applied from this plan's text by a script that runs the step's bash blocks, writes its `File:` blocks and applies its `Edit:` blocks by exact replacement in document order; pytest under the MemAvailable < 3 GB guard:

| Commit | Files | Focused runs | Full suite | Tree ids |
| --- | --- | --- | --- | --- |
| Task 1 | 23 (8 new, 1 deleted) | `6 passed`; red `116 failed, 46 passed, 14 errors`; red `1 failed, 175 passed` (template guard); `176 passed`; probe `1 failed, 5 passed`; `5 old lines not kept, 52 lines added`, `pure move: OK` | 3263 passed | match |
| Task 2 | 5 | red `1 failed, 76 passed`, then `111 passed` | 3266 passed | match |
| Task 3 | 6 | red `3 failed, 37 passed`, then `40 passed` | 3268 passed | match |

Every commit passed the hooks on the first try and left a clean tree. `buildVars.py` after Task 1: blob `89f0c1c0fbc3563b5ab71cf876706e4c024f04fb`. Task 4 in the clone: `3268 passed`, 0 skipped; `prek run --all-files` all Passed; `git diff --check a7bd115`, both protected-path commands and the `git grep` printed nothing; final tree ids as Task 3.

The plan text was produced from a prototype branch (same tree ids) and first replayed in a calibration clone that filled in the expected outputs; this record is the replay of the final text.

## 修正

Review: `docs/superpowers/finish/2026-10-27-phase42-settings-panels-review.md` (`d5313ff`): 0 Critical, 0 Important, 2 Minor. M2 is fixed below. M1 (Step 6's `check_move.py` compares line multisets, so it cannot prove order) needs no code change: the reviewer's order-sensitive check passed, and the review's fix log records it.

Starts from the end of Task 4: `654ef07` (`HEAD:addon` = `b62ed75314a91f666f195771ec025f77886d128c`, `HEAD:tests` = `76da7b1ca08375c278df4dd9b6b67477ca5f2574`; the review commit `d5313ff` changes only `docs/`). 3268 passed, 0 skipped.

### Task 5: Read the dialog's msgids from a fixed module list (review M2)

**Files:**
- Test: `tests/test_pipeline_panels.py`

**Interfaces:**
- Consumes: Task 3's tree; `tests/ui_harness.PANEL_MODULES`.
- Produces: `DIALOG_FILES` = `dialog.py` plus `panels/<name>.py` for each name of `PANEL_MODULES`, in that order; new test `test_dialog_msgids_come_from_the_dialog_and_every_panel`.

- [ ] **Step 1: Probe (not committed): the overlap check passes when the glob finds no panel**

```bash
sed -i 's|(PLUGIN / "panels").glob("\*.py")|(PLUGIN / "missing").glob("*.py")|' tests/test_pipeline_panels.py
grep -c '"missing"' tests/test_pipeline_panels.py
$SCRATCH/runtests.sh . "tests/test_pipeline_panels.py::test_log_labels_come_from_the_table" 2>&1 | tail -1
git checkout -- tests/test_pipeline_panels.py
```

Expected: `1`, then `1 passed` — with no panel read, `dialog_msgids()` holds only `dialog.py`'s two msgids, and `dialog_msgids() & strings == set()` passes vacuously.

- [ ] **Step 2: Write the test that every module of the dialog was read**

**Edit:** `tests/test_pipeline_panels.py` (1/1)

Replace:

```text
def test_log_labels_come_from_the_table(monkeypatch):
```

With:

```text
def test_dialog_msgids_come_from_the_dialog_and_every_panel():
	# The overlap check below would pass on an empty set; each module's title shows it was read.
	titles = {
		"Settings",
		"WorldVoice",
		"Speech Pipeline",
		"Speech Role",
		"Unicode Detection",
		"Speech Engine",
		"Log Record",
	}
	assert titles <= dialog_msgids()


def test_log_labels_come_from_the_table(monkeypatch):
```

```bash
$SCRATCH/runtests.sh . tests/test_pipeline_panels.py 2>&1 | tail -1
cp tests/test_pipeline_panels.py $SCRATCH/test_pipeline_panels.py.keep
sed -i 's|(PLUGIN / "panels").glob("\*.py")|(PLUGIN / "missing").glob("*.py")|' tests/test_pipeline_panels.py
$SCRATCH/runtests.sh . "tests/test_pipeline_panels.py::test_dialog_msgids_come_from_the_dialog_and_every_panel" 2>&1 | tail -1
cp $SCRATCH/test_pipeline_panels.py.keep tests/test_pipeline_panels.py
rm $SCRATCH/test_pipeline_panels.py.keep
```

Expected: `10 passed` (the new test passes on the real tree); with the glob pointed at a missing folder, red `1 failed` — the guard catches the vacuous case.

- [ ] **Step 3: List the modules instead of globbing**

**Edit:** `tests/test_pipeline_panels.py` (1/2)

Replace:

```text
from ui_harness import load_settings_dialog, load_voice_panel
```

With:

```text
from ui_harness import PANEL_MODULES, load_settings_dialog, load_voice_panel
```

**Edit:** `tests/test_pipeline_panels.py` (2/2)

Replace:

```text
# The settings dialog and its panels.
DIALOG_FILES = (PLUGIN / "dialog.py", *sorted((PLUGIN / "panels").glob("*.py")))
```

With:

```text
# The settings dialog and its panels, listed so that a missing module fails instead of reading nothing.
DIALOG_FILES = (PLUGIN / "dialog.py", *(PLUGIN / "panels" / f"{name}.py" for name in PANEL_MODULES))
```

```bash
$SCRATCH/runtests.sh . tests/test_pipeline_panels.py 2>&1 | tail -1
cp tests/test_pipeline_panels.py $SCRATCH/test_pipeline_panels.py.keep
sed -i 's|PLUGIN / "panels" / f"{name}.py"|PLUGIN / "missing" / f"{name}.py"|' tests/test_pipeline_panels.py
$SCRATCH/runtests.sh . "tests/test_pipeline_panels.py::test_log_labels_come_from_the_table" 2>&1 | grep -E "^E +FileNotFoundError|passed|failed" | tail -2
cp $SCRATCH/test_pipeline_panels.py.keep tests/test_pipeline_panels.py
rm $SCRATCH/test_pipeline_panels.py.keep
grep -c '"missing"' tests/test_pipeline_panels.py
```

Expected: `10 passed`; with the listed panels pointed at a missing folder, `test_log_labels_come_from_the_table` itself is red (`E       FileNotFoundError: [Errno 2] No such file or directory: '<repo>/addon/globalPlugins/WorldVoice/missing/base.py'`, `1 failed`) instead of passing; after the restore `0`.

- [ ] **Step 4: Run the suite and commit**

```bash
$SCRATCH/runtests.sh . tests 2>&1 | tail -1
```

Expected: `3269 passed` (3268 + `test_dialog_msgids_come_from_the_dialog_and_every_panel`).

```bash
git add tests/test_pipeline_panels.py
git diff --cached --stat | tail -1
git commit -q -m "test: read the dialog's msgids from a fixed module list" -m "DIALOG_FILES globbed panels/*.py, so if the panels moved, dialog_msgids() would read only dialog.py and the overlap check in test_log_labels_come_from_the_table would pass on nothing. The list now comes from ui_harness.PANEL_MODULES, so a missing module fails, and a new test checks that every module's title is among the msgids (phase 42 review M2)."
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `1 file changed, 17 insertions(+), 3 deletions(-)`; every hook Passed; clean status.

Expected after the commit: `HEAD:addon` = `b62ed75314a91f666f195771ec025f77886d128c` (unchanged), `HEAD:tests` = `0cbb15eaac511bddf3d7969c0b8049b709814b72`

### Task 6: Full verification after the fix

**Files:** none.

- [ ] **Step 1: Run every check**

```bash
$SCRATCH/runtests.sh . tests 2>&1 | tail -1
prek run --all-files
git diff --check a7bd115
git diff --stat a7bd115 -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
git rev-parse HEAD:addon HEAD:tests
```

Expected: `3269 passed`, 0 skipped; every hook Passed; the diff-check, protected-path and Neural commands print nothing; the tree ids of Task 5.

### Dry run record (修正)

2026-10-27, fresh clone of `/workspace/WorldVoice` at `654ef07` (`ref` symlinked, `prek install`), Tasks 5–6 applied from this section's text with the same step runner; pytest under the MemAvailable < 3 GB guard:

| Commit | Files | Focused runs | Full suite | Tree ids |
| --- | --- | --- | --- | --- |
| Task 5 | 1 | probe: vacuous `1 passed`; `10 passed`, probe red `1 failed`; `10 passed`, probe red `FileNotFoundError` … `missing/base.py`, `1 failed`; restore `0` | 3269 passed | match |

The commit passed the hooks on the first try and left a clean tree. Task 6: `3269 passed`, 0 skipped; `prek run --all-files` all Passed; `git diff --check a7bd115`, both protected-path commands printed nothing. A calibration clone filled in the expected outputs first; this record is the replay of the final text.
