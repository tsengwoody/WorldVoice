# Hide Unavailable Engines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** The WorldVoice Speech Engine panel shows only engines whose readiness check passes, and VE/Cerence report not ready (without loading a DLL) when a DLL their inner `initialize` loads is missing.

**Architecture:** `engineRegistry/discovery.py` gets `load_engine_class(spec, logger)`, the per-spec check factored out of `load_enabled_engine_classes`; `engineRegistry/__init__.py` gets `available_engine_specs()` over all specs. The VE and Cerence wrappers each get a file-existence `Voice.ready()` over the paths their inner `initialize` derives. The panel builds its checkboxes and `previousActiveEngine` from the available specs only.

**Tech Stack:** Python 3 (NVDA add-on, tabs, ruff `==0.16.3`), pytest, prek, gettext (no string changes).

**Spec:** `docs/superpowers/specs/2026-11-07-hide-unavailable-engines-design.md` (G1–G2 user; D1–D8 orchestrator defaults; §-numbers below refer to it).

## Global Constraints

- Baseline `master` `d352a06` in the worktree: `python3 -m pytest -q -p no:cacheprovider tests` → 3744 passed, 0 skipped; `prek run --all-files` all Passed.
- VE checks `msvcr110.dll`, `ve.dll`, `vplatform.dll` in `<ws>/lib/<os.environ["PROCESSOR_ARCHITECTURE"]>`; Cerence checks `ve.dll`, `vplatform.dll` in `<ws>/lib/<"x64" if sys.maxsize > 2**32 else "x32">`; `<ws>` = nine `os.path.dirname`s above `ve2.__file__` / `ttsapi.__file__`, joined with `WorldVoice-workspace/VE` / `WorldVoice-workspace/Cerence` (D1, D2). `os.path.isfile` only; never `LoadLibrary`.
- Unavailable log line (info): `"WorldVoice %s engine is unavailable: missing %s"` with `cls.engine` and the missing paths joined by `", "` (D4). Missing `PROCESSOR_ARCHITECTURE` raises `KeyError` out of VE `ready()` (D3).
- `available_engine_specs()` is not cached (D5) and ignores the enabled flag (D6). `load_enabled_engine_classes` output, warnings, errors and timing lines unchanged.
- Panel: no new UI strings; hidden engines' stored flags never written; "no speech engine is enabled" only when the panel has at least one checkbox (D7).
- Docs: only `addon/doc/zh_TW/readme.md` (§5 text verbatim); never the root `readme.md`, other languages, or `nvda.po` (no string change). `.pot`/`.mo` never committed.
- §8 fixed constraints: never edit `addon/synthDrivers/WorldVoice/driver/*/driver/*`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; engine drivers stay independently installable (no driver imports another driver's package; VE/Cerence code duplicated on purpose; shared code only in core); no Neural; ruff `0.16.3`, tabs; NVDA-free modules snake_case (`engineRegistry/`), NVDA-layer camelCase (wrappers, panels).
- §8 git: stage explicit paths, `git diff --cached --stat` before every commit; English `<type>: <summary>` with a why-body; no `Co-Authored-By`; never `--no-verify`, never `git stash`, no push; never touch `/workspace/WorldVoice`; `ref` symlink never staged. `docs/` files need `git add -f`.
- §8 resources: a single `pytest -q tests` run (no parallel workers); never `ulimit -v`.

## Review Focus

1. **Engine hidden but still enabled in the stored config** (VE on by default, files deleted): OK without changes must neither prompt for a restart nor rewrite the VE flag; restoring the files must bring VE back checked. Covered by Task 4 (`test_engine_panel_hides_an_unavailable_engine`, `test_engine_panel_keeps_a_hidden_engine_flag_on_save`).
2. **Partial VE install** (only `msvcr110.dll` missing, or the folder present without `lib/<arch>`): hidden, and the log names exactly the missing paths. Covered by Task 3 (`test_ready_names_each_missing_file`, `test_ready_without_the_workspace_names_every_file`).
3. **Check and loader disagree on the path** (inner driver updated, architecture name, 32-bit Cerence): `ready()` must test exactly what `initialize` opens. Covered by Task 3 (`test_ready_checks_exactly_what_initialize_loads`, VE with `PROCESSOR_ARCHITECTURE`, Cerence for both `sys.maxsize` cases).
4. **A disabled engine that raises on import or in `ready()`** (broken plugin, no `PROCESSOR_ARCHITECTURE`): the panel still opens, that engine is hidden and one error line is logged. Covered by Task 1 (`test_load_engine_class_gives_none_for_each_failure`) and Task 2 (`test_available_engine_specs_keeps_ready_engines_in_order_enabled_or_not`).
5. **No engine available at all:** the settings dialog must not be trapped by "no speech engine is enabled". Covered by Task 4 (`test_engine_panel_without_available_engines_saves_without_asking`).

---

### Task 1: `load_engine_class` in discovery

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/engineRegistry/discovery.py:160-223`
- Test: `tests/test_engine_discovery.py`

**Interfaces:**
- Consumes: `EngineSpec`, `_load_module`, `_pre_rename_contract_names`, `timed` (unchanged).
- Produces: `load_engine_class(spec: EngineSpec, logger: Any = None) -> type | None`; `load_enabled_engine_classes` unchanged signature and output.

- [ ] **Step 1: Write the failing tests** (reuse the file's `Log`, `engine_module`, `spec` helpers)

```python
def test_load_engine_class_returns_the_ready_voice_whatever_the_flag(discovery, monkeypatch, tmp_path):
	ready = type("Voice", (), {"engine": "Off", "ready": classmethod(lambda cls: True)})
	engine_module(monkeypatch, "fake_off_ready", ready)
	log = Log()
	assert discovery.load_engine_class(spec(discovery, "Off", "fake_off_ready", tmp_path, enabled=False), logger=log) is ready
	assert [level for level, _ in log.lines] == ["debug"] * 4  # the four timing lines only

@pytest.mark.parametrize(("voice", "line"), [
	pytest.param(None, ("warning", "Skipping X engine candidate: Voice export missing"), id="no-voice"),
	pytest.param(type("Voice", (), {"engine": "Y", "ready": classmethod(lambda cls: True)}), ("warning", "Skipping X engine candidate: Voice.engine mismatch (Y)"), id="mismatch"),
	pytest.param(type("Voice", (), {"engine": "X", "ready": classmethod(lambda cls: False)}), None, id="unready"),
	pytest.param(type("Voice", (), {"engine": "X", "ready": classmethod(lambda cls: 1 / 0)}), ("error", "Failed to load ready state for X: division by zero"), id="raises"),
])
def test_load_engine_class_gives_none_for_each_failure(discovery, monkeypatch, tmp_path, voice, line):
	engine_module(monkeypatch, "fake_x", voice)
	log = Log()
	assert discovery.load_engine_class(spec(discovery, "X", "fake_x", tmp_path), logger=log) is None
	assert [entry for entry in log.lines if entry[0] != "debug"] == ([line] if line else [])
```

- [ ] **Step 2: Run to verify red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_engine_discovery.py`
Expected: 5 failed (`AttributeError: ... has no attribute 'load_engine_class'`), the rest passed.

- [ ] **Step 3: Implement `load_engine_class(spec: EngineSpec, logger: Any = None) -> type | None` in `discovery.py`**

Move the loop body of `load_enabled_engine_classes` (`timed` total block through the `except`) verbatim into it, `continue` → `return None`, `ready[spec.name] = voice` → `return voice`, and the `except` logs then returns None. `load_enabled_engine_classes` keeps `logger = logger or _LOG`, skips disabled specs, and stores non-None results.

- [ ] **Step 4: Run to verify green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_engine_discovery.py tests/test_engine_registry.py` → all passed. Full suite: 3749 passed, 0 skipped.

- [ ] **Step 5: Commit** `refactor: check one engine spec in load_engine_class` (stage `discovery.py`, `tests/test_engine_discovery.py`).

### Task 2: `available_engine_specs`

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/engineRegistry/__init__.py:14-42`
- Test: `tests/test_engine_registry.py`

**Interfaces:**
- Consumes: `load_engine_class` (Task 1), `ENGINE_SPECS`.
- Produces: `available_engine_specs() -> tuple[EngineSpec, ...]` (reads the module-global `ENGINE_SPECS` at call time; no cache).

- [ ] **Step 1: Write the failing test** (fake modules in `sys.modules` via `monkeypatch.setitem`; specs built with `dataclasses.replace` of the discovered external spec; `module.ENGINE_SPECS` monkeypatched)

```python
def test_available_engine_specs_keeps_ready_engines_in_order_enabled_or_not(engines, monkeypatch):
	# specs: off (ready, default_enabled False), unready, broken (ready raises RuntimeError("boom")), the real external
	monkeypatch.setattr(engines.module, "ENGINE_SPECS", (off, unready, broken, external))
	assert engines.module.available_engine_specs() == (off, external)
	assert engines.logged == [("error", "Failed to load ready state for %s: %s", "Broken", error)]  # the RuntimeError instance
```

- [ ] **Step 2: Run to verify red** — `python3 -m pytest -q -p no:cacheprovider tests/test_engine_registry.py` → 1 failed (`AttributeError: ... 'available_engine_specs'`).

- [ ] **Step 3: Implement `available_engine_specs()`** in `engineRegistry/__init__.py`, importing `load_engine_class`; docstring states D5/D6 (no cache, enabled flag ignored).

- [ ] **Step 4: Run to verify green** — that file passes; full suite 3750 passed, 0 skipped.

- [ ] **Step 5: Commit** `feat: list the engines whose ready check passes` (stage `engineRegistry/__init__.py`, `tests/test_engine_registry.py`).

### Task 3: VE and Cerence `ready()`

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py` (imports; module functions before `class Voice`; `Voice.ready`)
- Modify: `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py` (same; plus `import sys`)
- Create: `tests/test_vocalizer_ready.py`
- Modify: `tests/test_vocalizer_drift.py:6,36` (allow `_nativeFiles` and Cerence-only `import:import sys`)

**Interfaces:**
- Consumes: `load_real_driver_with_native_stubs(monkeypatch, engine)` from `tests/worldvoice_cancel_wrapper_harness.py` (`.module` wrapper, `.native` inner `ve2`/`ttsapi`), `load_source` from `tests/addon_loader.py`.
- Produces: in each wrapper `_engineWorkspace() -> str`, `_nativeFiles() -> list[str]` (inner load order), `Voice.ready() -> bool` (classmethod).

- [ ] **Step 1: Write the failing tests** (fixture `engine` parametrized `["VE", "Cerence"]` loads the harness with `PROCESSOR_ARCHITECTURE=AMD64` set and `PROCESSOR`-independent for Cerence; `module.log` replaced by a recorder of `(level, message % args)`; `os.path.isfile` monkeypatched to a set of present paths; `FILES = {"VE": ["msvcr110.dll", "ve.dll", "vplatform.dll"], "Cerence": ["ve.dll", "vplatform.dll"]}`; `LIB = {"VE": "lib/AMD64", "Cerence": "lib/x64"}`)

```python
def test_ready_with_every_file(engine):  # all of _nativeFiles() present
	assert engine.Voice.ready() is True and engine.logged == []
	assert engine.files == [os.path.join(engine.workspace, LIB[engine.name], f) for f in FILES[engine.name]]
	assert engine.workspace.endswith(os.path.join("WorldVoice-workspace", engine.name))

@pytest.mark.parametrize(("name", "missing"), [("VE", "msvcr110.dll"), ("VE", "ve.dll"), ("VE", "vplatform.dll"), ("Cerence", "ve.dll"), ("Cerence", "vplatform.dll")])
def test_ready_names_each_missing_file(..., name, missing):
	assert Voice.ready() is False
	assert logged == [("info", f"WorldVoice {name} engine is unavailable: missing {path_of(missing)}")]

def test_ready_without_the_workspace_names_every_file(engine):  # isfile always False
	assert ready() is False and logged == [("info", "WorldVoice X engine is unavailable: missing " + ", ".join(all paths))]

def test_ready_never_loads_a_library(engine, monkeypatch):  # ctypes.cdll.LoadLibrary patched to raise AssertionError
	ready() in both the present and the missing case

def test_ve_ready_without_processor_architecture_raises_like_initialize(monkeypatch):
	monkeypatch.delenv("PROCESSOR_ARCHITECTURE"); pytest.raises(KeyError): VE Voice.ready()

@pytest.mark.parametrize(("name", "maxsize", "lib"), [("VE", sys.maxsize, "AMD64"), ("Cerence", 2**63 - 1, "x64"), ("Cerence", 2**31 - 1, "x32")])
def test_ready_checks_exactly_what_initialize_loads(monkeypatch, name, maxsize, lib):
	# load the real inner module afresh over the harness's patched one (load_source, same dotted name),
	# give it a cdll whose LoadLibrary records the path and returns a MagicMock, set sys.maxsize,
	# call fresh.initialize([]) and assert recorded == wrapper._nativeFiles() and every path contains lib
```

- [ ] **Step 2: Run to verify red** — `python3 -m pytest -q -p no:cacheprovider tests/test_vocalizer_ready.py` → 15 failed (`AttributeError: ... '_nativeFiles'` / `ready() is True`).

- [ ] **Step 3: Implement in both wrappers** `_engineWorkspace()`, `_nativeFiles()` and `Voice.ready()` per spec §4.2; `_engineWorkspace` and `Voice.ready` text identical after `Cerence→VE`, `ttsapi→ve2`. Comment cites the inner lines (VE `ve2/__init__.py:86-97`, Cerence `ttsapi/__init__.py:82-91`). In `tests/test_vocalizer_drift.py` add `"_nativeFiles"` to `ALLOWED` and compare keys with Cerence's `import:import sys` removed (named constant with a comment).

- [ ] **Step 4: Run to verify green** — `tests/test_vocalizer_ready.py`, `tests/test_vocalizer_drift.py`, `tests/test_vocalizer_resource_paths.py`, `tests/test_worldvoice_cancel_wrappers.py`, `tests/test_naming_layers.py`, `tests/test_hygiene_guards.py` pass; full suite 3765 passed, 0 skipped.

- [ ] **Step 5: Commit** `feat: report VE and Cerence unavailable when their DLLs are missing` (stage the two wrappers and the two test files).

### Task 4: Panel shows available engines only

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/panels/engine.py:11,38-56`
- Modify: `tests/ui_harness.py:806-828` (`env.unavailable_engines = set()`; stub `available_engine_specs=lambda: tuple(s for s in env.engine_specs if s.name not in env.unavailable_engines)`; docstring)
- Test: `tests/test_settings_panels.py` (SpeechEngineSettingsPanel section)

**Interfaces:**
- Consumes: `available_engine_specs()` (Task 2), `get_engine_enabled(name, section)`.
- Produces: panel attributes unchanged (`settings`, `previousActiveEngine`, `activeEngine`, `confirm`, `<name>CheckBox`).

- [ ] **Step 1: Write the failing tests** (`engine_env` gains `unavailable=()` and sets `env.unavailable_engines`)

```python
def test_engine_panel_hides_an_unavailable_engine(monkeypatch):
	env = engine_env(monkeypatch, {"VE": True}, unavailable={"VE"})
	panel, sizer = build(env, "SpeechEngineSettingsPanel")
	assert [box.label for box in sizer.items[1].item.controls()] == ["OneCore voices", "SAPI5 voices"]
	assert not hasattr(panel, "VECheckBox") and list(panel.settings) == ["OneCore", "SAPI5"]
	assert panel.previousActiveEngine == {"OneCore"}

def test_engine_panel_keeps_a_hidden_engine_flag_on_save(monkeypatch):
	env = engine_env(monkeypatch, {"VE": True}, unavailable={"VE"}, answers=[0x2])
	panel, _ = build(env, ...); assert panel.isValid() is True; panel.onSave()
	assert env.shown == [] and env.conf["WorldVoice"]["engine"] == {"VE": True} and env.queued == []
	panel.SAPI5CheckBox.SetValue(True); assert panel.isValid() is True; panel.onSave()
	assert env.conf["WorldVoice"]["engine"] == {"OneCore": True, "SAPI5": True, "VE": True}

def test_engine_panel_refuses_when_only_a_hidden_engine_is_enabled(monkeypatch):
	env = engine_env(monkeypatch, {"VE": True}, unavailable={"VE"}); uncheck OneCore
	assert panel.isValid() is False and [c for _m, c, _s in env.shown] == ["No Speech Engine Enabled"]

def test_engine_panel_without_available_engines_saves_without_asking(monkeypatch):
	env = engine_env(monkeypatch, {"VE": True}, unavailable={"OneCore", "SAPI5", "VE"})
	assert sizer.items[1].item.controls() == [] and panel.isValid() is True; panel.onSave()
	assert env.shown == [] and env.conf["WorldVoice"]["engine"] == {"VE": True} and env.queued == []
```

- [ ] **Step 2: Run to verify red** — `python3 -m pytest -q -p no:cacheprovider tests/test_settings_panels.py -k engine_panel` → 4 failed (VE checkbox present / restart prompt / no-engine message), 5 passed.

- [ ] **Step 3: Implement** in `engine.py`: import `available_engine_specs` (drop `ENGINE_SPECS`); one `available` tuple feeds `self.settings` and `self.previousActiveEngine`; `isValid` shows the no-engine message only `if not self.activeEngine and self.settings`.

- [ ] **Step 4: Run to verify green** — `tests/test_settings_panels.py`, `tests/test_settings_panel_save.py`, `tests/test_translator_comments.py`, `tests/test_ui_structure.py` pass; full suite 3769 passed, 0 skipped.

- [ ] **Step 5: Commit** `feat: show only loadable engines in the Speech Engine panel` (stage `engine.py`, `tests/ui_harness.py`, `tests/test_settings_panels.py`).

### Task 5: zh_TW user guide

**Files:**
- Modify: `addon/doc/zh_TW/readme.md:89` (new bullet after it) and `## 下一版更新` (new last bullet), texts verbatim from spec §5.

- [ ] **Step 1:** Insert both bullets; `git diff --check`.
- [ ] **Step 2:** Full suite 3769 passed, 0 skipped (docs tests such as `tests/test_locales.py` unaffected).
- [ ] **Step 3: Commit** `docs: tell zh_TW users that engines which cannot load are hidden`.

### Final verification (§7)

- [ ] `python3 -m pytest -q -p no:cacheprovider tests` → 3769 passed, 0 skipped (record the actual number in the ledger if a step's count differs; note the reason as a `Ruling:`).
- [ ] `prek run --all-files` → all Passed; `git diff --check master` → nothing.
- [ ] Protected paths: `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py` and `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` → both print nothing.
- [ ] Windows/NVDA manual items M1–M5 (spec §8) listed as unverified in the report.
