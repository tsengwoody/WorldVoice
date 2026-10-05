# Phase 12 Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Replace the main driver's flags, hand-written cleanup and timing code with:
  - a fixed-order `Teardown`;
  - `timed`;
  - `patch_attribute`.
- Register pipeline stages last.
- Keep the voice settings panel's NVDA copy in sync under a guard.
- Move the log export UI out of the synth layer.

**Architecture:**
- New pure-Python `synthDrivers/WorldVoice/assembly.py`, used by:
  - the main driver;
  - `pipeline/speech_dictionary.py`;
  - `engine/discovery.py`.
- `log.py` keeps CSV writing and `move_to`. `globalPlugins/WorldVoice/pipelineLog.py` owns the export dialogs.

**Tech Stack:** Python 3.11; pytest with NVDA stubs; ruff (tabs, ref/nvda style).

**Spec:** `docs/superpowers/specs/2026-10-05-phase12-assembly-design.md`

## Global Constraints

- Never edit `driver/<Engine>/driver/` or `driver/sonic`. Ruff scope:

  ```
  --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic'
  ```

- User-visible behavior must not change:
  - voice settings panel controls and order;
  - log export dialogs and messages;
  - cleanup order;
  - numlan and symbols in the pipeline.
- Teardown order is exactly the current `terminate` order (spec §1 `_TEARDOWN_ORDER`). Cleanup log text stays `"WorldVoice terminate: %s"`.
- Timing labels stay byte-identical to today's strings.
- `git add` explicit paths only. Never stage the `docs/superpowers/finish_task.md` deletion or `refactor.md`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full suite: `python3 -m pytest tests -q` (baseline 1555).
- Lint gate: `ruff check addon <scope> --select F401,F821,BLE001,I001` → 0, and `ruff format --check addon`.

## Review Focus

1. **Failure part-way through `_initialize`.** Every side effect acquired so far must be undone, and nothing not acquired. For example, if `VoiceManager` raises, the panel and pipeline-register cleanups must not run for steps never reached. Pipeline register now runs last, so a failure before it must not call `worldvoice_ended`. Task 2 tests it through the lifecycle harness.
2. **`terminate()` called twice, or after a failed construction.** The second call does nothing; no cleanup runs twice. Task 1 tests `Teardown.run` twice; Task 2 relies on `_terminated`.
3. **`terminate()` while another thread calls `speak()`.** `speak` checks `_terminated` first. Attributes go to `None` only after `run`, so no `None` is dereferenced mid-teardown. Covered by the existing `_terminated` check; the review reads it.
4. **Restore function called twice by re-entrant cleanup.** The second call must not overwrite a newer patch. Task 1 tests it.
5. **The first pipeline log write on a machine with no log directory** must create the directory and header. Task 4 tests it.

---

### Task 1: `assembly.py`

**Files:**
- Create: `addon/synthDrivers/WorldVoice/assembly.py`, `tests/test_assembly.py`

**Interfaces:**
- Produces:
  - `Teardown(order: Sequence[str], logger)`, with `.add(name, cleanup)` and `.run()`;
  - `timed(logger, label)`, a context manager;
  - `patch_attribute(owner, name, value) -> Callable[[], None]`.

- [ ] **Step 1: Failing tests** `tests/test_assembly.py`. Load the module with `importlib.util.spec_from_file_location("assembly_under_test", WORLDVOICE / "assembly.py")`; it has no package-relative imports.

```python
class Log:
	def __init__(self):
		self.debugs, self.errors = [], []
	def debug(self, *args):
		self.debugs.append(args)
	def error(self, *args, **kwargs):
		self.errors.append((args, kwargs))

def test_teardown_runs_in_declared_order_not_registration_order(assembly):
	ran = []
	teardown = assembly.Teardown(("a", "b", "c"), Log())
	teardown.add("c", lambda: ran.append("c"))
	teardown.add("a", lambda: ran.append("a"))
	teardown.run()
	assert ran == ["a", "c"]

def test_teardown_rejects_unknown_and_duplicate_names(assembly):
	teardown = assembly.Teardown(("a",), Log())
	with pytest.raises(ValueError):
		teardown.add("z", lambda: None)
	teardown.add("a", lambda: None)
	with pytest.raises(ValueError):
		teardown.add("a", lambda: None)

def test_teardown_logs_a_failure_and_continues(assembly):
	ran, log = [], Log()
	teardown = assembly.Teardown(("a", "b"), log)
	teardown.add("a", lambda: 1 / 0)
	teardown.add("b", lambda: ran.append("b"))
	teardown.run()
	assert ran == ["b"]
	assert log.errors == [(("WorldVoice terminate: %s", "a"), {"exc_info": True})]

def test_teardown_lets_interrupts_through(assembly):
	ran = []
	def interrupt():
		raise KeyboardInterrupt
	teardown = assembly.Teardown(("a", "b"), Log())
	teardown.add("a", interrupt)
	teardown.add("b", lambda: ran.append("b"))
	with pytest.raises(KeyboardInterrupt):
		teardown.run()
	assert ran == []

def test_teardown_runs_once(assembly):
	ran = []
	teardown = assembly.Teardown(("a",), Log())
	teardown.add("a", lambda: ran.append("a"))
	teardown.run()
	teardown.run()
	assert ran == ["a"]

def test_timed_logs_label_and_seconds(assembly, monkeypatch):
	clock = iter([1.0, 1.25])
	monkeypatch.setattr(assembly.time, "perf_counter", lambda: next(clock))
	log = Log()
	with assembly.timed(log, "TaskManager"):
		pass
	assert log.debugs == [("WorldVoice init timing: %s %.3fs", "TaskManager", 0.25)]

def test_timed_logs_and_reraises_on_failure(assembly):
	log = Log()
	with pytest.raises(ZeroDivisionError):
		with assembly.timed(log, "step"):
			1 / 0
	assert [entry[1] for entry in log.debugs] == ["step"]

def test_timed_without_logger(assembly):
	with assembly.timed(None, "step"):
		pass

def test_patch_attribute_restores_once(assembly):
	owner = SimpleNamespace(value="original")
	restore = assembly.patch_attribute(owner, "value", "patched")
	assert owner.value == "patched"
	restore()
	assert owner.value == "original"
	owner.value = "newer"
	restore()
	assert owner.value == "newer"
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_assembly.py -q` → FAIL (file missing).
- [ ] **Step 3: Implement**

```python
"""Bring-up helpers for the driver: fixed-order teardown, step timing, attribute patches."""

import time
from collections.abc import Callable, Sequence
from contextlib import contextmanager


class Teardown:
	"""Cleanups registered as resources come up, run once in one fixed order."""

	def __init__(self, order: Sequence[str], logger):
		self._order = tuple(order)
		self._logger = logger
		self._cleanups: dict[str, Callable[[], object]] = {}

	def add(self, name: str, cleanup: Callable[[], object]) -> None:
		if name not in self._order:
			raise ValueError(f"{name!r} has no place in the teardown order")
		if name in self._cleanups:
			raise ValueError(f"{name!r} is already registered")
		self._cleanups[name] = cleanup

	def run(self) -> None:
		cleanups, self._cleanups = self._cleanups, {}
		for name in self._order:
			cleanup = cleanups.get(name)
			if cleanup is None:
				continue
			try:
				cleanup()
			except Exception:
				self._logger.error("WorldVoice terminate: %s", name, exc_info=True)


@contextmanager
def timed(logger, label: str):
	start = time.perf_counter()
	try:
		yield
	finally:
		if logger is not None:
			logger.debug("WorldVoice init timing: %s %.3fs", label, time.perf_counter() - start)


def patch_attribute(owner, name: str, value) -> Callable[[], None]:
	"""Set owner.name to value; the returned function restores the original once."""
	original = getattr(owner, name)
	setattr(owner, name, value)
	restored = False

	def restore() -> None:
		nonlocal restored
		if restored:
			return
		restored = True
		setattr(owner, name, original)

	return restore
```

  The `except Exception` in `run` already logs with `exc_info`, so ruff's BLE001 does not flag it (logger-objects config). If it is flagged, add `# noqa: BLE001 - logged; the remaining cleanups still run` and add that reason to the hygiene guard's reason table.
- [ ] **Step 4: Run** the test file, the full suite and the lint gate → PASS.
- [ ] **Step 5: Commit** `feat: add fixed-order teardown, step timing and attribute patch helpers`.

---

### Task 2: Main driver assembly

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`
- Test: `tests/test_worldvoice_lifecycle.py`, `tests/test_runtime_composition.py` (`make_synth`), create `tests/test_assembly_structure.py`

**Interfaces:**
- Consumes: Task 1's `Teardown`, `timed`, `patch_attribute`.
- Produces:
  - `SynthDriver._TEARDOWN_ORDER` (class attribute, spec §1);
  - `SynthDriver._new_teardown() -> Teardown`, with the four runtime cleanups registered;
  - `self._teardown`, `self._terminateCommit`, `self._numlan = "default"` set in `__init__`.

- [ ] **Step 1: Failing tests.**
  - `tests/test_assembly_structure.py` with the main-driver forbidden list from spec success criterion 2 (`ADDON / "synthDrivers/WorldVoice/__init__.py"`, substring checks).
  - In `tests/test_worldvoice_lifecycle.py`:
    - add the assembly helpers to every exec environment: load the real module via `importlib.util.spec_from_file_location`, put it in a module-level helper `_assembly()`, and add `"Teardown"`, `"timed"` and `"patch_attribute"` to each environment dict;
    - change `test_failed_synth_construction_releases_acquired_resources`'s `SpeechSymbols` stub to record `"symbols loaded"` in `changes` from `load`, and `LanguageDetector` to record `"detector built"`;
    - its `apply_pipeline` (the `worldvoice_started` stub) already records `"pipeline started"`, or make it do so;
    - add the C2 test:

```python
def test_stages_register_after_symbols_and_detector(monkeypatch):
	changes = run_successful_construction(...)  # reuse the failure test's environment builder with no failure
	assert changes.index("symbols loaded") < changes.index("pipeline started")
	assert changes.index("detector built") < changes.index("pipeline started")
```

  If the existing test builds its environment inline, extract it into `_construction_environment(failure, changes)` first, without changing assertions, so both tests share it. With `failure=None`, construction succeeds.
  - For failures before the last step (`"manager"`, `"symbols"`), assert `"pipeline stopped"` is **not** in `changes`, because the pipeline was never started. That replaces the current `assert "pipeline stopped" in changes` for those two parameters. For `"bridge"` the same holds.
  - This is the one intended assertion change: it follows from moving registration last. Ledger it.
  - Replace the flag-setting blocks in `test_terminate_cleanup_logs_errors_but_lets_interrupts_through` (lines ~370-381) and in `test_runtime_composition.make_synth` with `synth._terminated = False; synth._terminateCommit = True; synth._teardown = synth._new_teardown()`, keeping the attribute assignments for `taskManager`/`_eventBridge`/`_voiceManager`/`_indexLedger`.
- [ ] **Step 2: Run** → FAIL (structure guard; C2 order; `_new_teardown` missing).
- [ ] **Step 3: Implement** in `__init__.py`:
  - imports: `from .assembly import Teardown, patch_attribute, timed`; drop `time` if unused.
  - class attribute `_TEARDOWN_ORDER` from the spec.
  - `__init__`:

```python
	def __init__(self):
		self._terminated = False
		self._terminateCommit = True
		self._numlan = "default"
		self.speechSymbols = None
		self._realSpellingFunc = None
		self.taskManager = None
		self._voiceManager = None
		self._eventBridge = None
		self._settingsStore = None
		self._indexLedger = None
		self._teardown = self._new_teardown()
		try:
			self._initialize()
		except BaseException:
			# Release acquired resources even on KeyboardInterrupt, then re-raise.
			self.terminate(commit=False)
			raise

	def _new_teardown(self):
		"""A teardown that already owns the runtime objects, whichever of them exist."""
		teardown = Teardown(self._TEARDOWN_ORDER, nvdaLog)

		def shutdown_tasks():
			if self.taskManager is not None:
				manager = self._voiceManager
				self.taskManager.shutdown(manager.playback_ports if manager is not None else ())

		def close_bridge():
			if self._eventBridge is not None:
				self._eventBridge.close()

		def terminate_voices():
			if self._voiceManager is not None:
				self._voiceManager.terminate(commit=self._terminateCommit)

		def close_ledger():
			if self._indexLedger is not None:
				self._indexLedger.close()

		teardown.add("task manager shutdown", shutdown_tasks)
		teardown.add("event bridge close", close_bridge)
		teardown.add("voice manager terminate", terminate_voices)
		teardown.add("index ledger close", close_ledger)
		return teardown
```

  - `_initialize`. The order is the spec's; pipeline register goes last.

```python
	def _initialize(self):
		with timed(nvdaLog, "total"):
			with timed(nvdaLog, "WVStart.notify"):
				self._teardown.add("end notification", WVEnd.notify)
				WVStart.notify()
			self.order = 0
			with timed(nvdaLog, "voice settings panel patch"):
				self._teardown.add("voice settings panel restore", patch_attribute(
					gui.settingsDialogs, "VoiceSettingsPanel", WorldVoiceVoiceSettingsPanel))
			with timed(nvdaLog, "TaskManager"):
				... # unchanged body: repository, store, ledger, bridge, TaskManager, bridge.start
			with timed(nvdaLog, "VoiceManager"):
				... # unchanged body
			self._apply_pipeline_settings(pipeline_settings.get())
			pipeline_settings.subscribe(self._apply_pipeline_settings)
			self._teardown.add("pipeline settings unsubscribe",
				lambda: pipeline_settings.unsubscribe(self._apply_pipeline_settings))
			with timed(nvdaLog, "speakSpelling patch"):
				self._realSpellingFunc = speech.speech.speakSpelling
				self._teardown.add("spelling function restore",
					patch_attribute(speech.speech, "speakSpelling", self.patchedSpeakSpelling))
			with timed(nvdaLog, "SpeechSymbols construct"):
				self.speechSymbols = SpeechSymbols()
			with timed(nvdaLog, "SpeechSymbols.load unicode.dic"):
				self.speechSymbols.load("unicode.dic")
			with timed(nvdaLog, "LanguageDetector"):
				self._languageDetector = languageDetection.LanguageDetector(
					list(self._voiceManager.allLanguages), self.speechSymbols)
				self.add_detected_language_commands = listable(self._languageDetector.add_detected_language_commands)
				self._teardown.add("language detection unregister",
					lambda: filter_speechSequence.unregister(self.add_detected_language_commands))
			self._voice = None
			# Stages see a fully built synth: symbols, detector and number language exist.
			with timed(nvdaLog, "pipeline register"):
				self._teardown.add("pipeline cleanup", pipeline_scope.worldvoice_ended)
				pipeline_scope.worldvoice_started()
```

  Today the flag is set before the call, so a failing `worldvoice_started` still runs `worldvoice_ended`. Register before calling, as the snippet does. Do the same for `WVStart`, which is already shown that way.

  - `terminate` from the spec. Delete `_run_cleanup`, every flag and `OriginVoiceSettingsPanel`.
  - `speech_context`: `number_language=self._numlan`, `speech_symbols=self.speechSymbols`.
  - Update every exec environment and synth builder in tests that loads the class (grep `_load_synth_class(`) so it has the three helper names. `test_runtime_completion_policies` no longer uses it after phase 10a; verify with grep.
- [ ] **Step 4: Run** the lifecycle and composition files 5×, the full suite and the lint gate → PASS.
- [ ] **Step 5: Commit** `refactor: assemble the driver through a fixed-order teardown and register stages last`.

---

### Task 3: `processText` patch and discovery timing

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/speech_dictionary.py`, `addon/synthDrivers/WorldVoice/engine/discovery.py`
- Test: create `tests/test_speech_dictionary.py`; append to `tests/test_assembly_structure.py`

**Interfaces:**
- Consumes: `patch_attribute`, `timed` (Task 1).

- [ ] **Step 1: Failing tests.**
  - `tests/test_speech_dictionary.py` loads the real module under a stub package whose `__path__` is `[WORLDVOICE]`, so `..assembly` resolves. Stub `speech` with `speech.speech.processText` and `globalVars.speechDictionaryProcessing = True`.

```python
def test_install_bypasses_dictionaries_and_uninstall_restores(env):
	original = env.speech.speech.processText
	env.module.install()
	env.module.install()  # idempotent
	wrapped = env.speech.speech.processText
	assert wrapped is not original
	assert wrapped("text") == ("text", False)  # original returns (text, flag seen)
	assert env.globalVars.speechDictionaryProcessing is True
	env.module.uninstall()
	env.module.uninstall()
	assert env.speech.speech.processText is original
```

  Make the stub `processText` return `(text, globalVars.speechDictionaryProcessing)`.
  - Structure guard: `speech_dictionary.py` has exactly one module-level `global` name, `_restore`: parse the AST and collect module-level `AnnAssign`/`Assign` targets.
- [ ] **Step 2: Run** → the guard FAILS (two globals). The behavior test passes; it pins existing behavior.
- [ ] **Step 3: Implement**

```python
from functools import wraps
from typing import Callable

import globalVars
import speech

from ..assembly import patch_attribute

_restore: Callable[[], None] | None = None


def install() -> None:
	global _restore

	if _restore is not None:
		return

	original_process_text = speech.speech.processText

	@wraps(original_process_text)
	def process_text_without_dictionaries(*args, **kwargs):
		previous = globalVars.speechDictionaryProcessing
		globalVars.speechDictionaryProcessing = False
		try:
			return original_process_text(*args, **kwargs)
		finally:
			globalVars.speechDictionaryProcessing = previous

	_restore = patch_attribute(speech.speech, "processText", process_text_without_dictionaries)


def uninstall() -> None:
	global _restore

	if _restore is None:
		return

	restore, _restore = _restore, None
	restore()
```

  `discovery.py`:
  - `from ..assembly import timed`;
  - replace the four timing blocks:
    - `with timed(logger, f"ready check {spec.name} module import"): module = _load_module(...)`;
    - the same for `Voice lookup` and `voice.ready`;
    - an outer `with timed(logger, f"ready check {spec.name} total"):` around the per-engine `try`.
  - Keep the `except Exception` (noqa reason unchanged) and `_log` for the warning and error messages. The `continue` statements inside `with` blocks are fine.
  - Tests that load `discovery` standalone (grep `discovery.py` in tests) must load it inside a package whose parent contains `assembly.py`. If one loads it by file path without a package, give it the stub package the way `test_speech_dictionary.py` does.
- [ ] **Step 4: Run** the full suite and the lint gate → PASS.
- [ ] **Step 5: Commit** `refactor: patch processText and time discovery through the assembly helpers`.

---

### Task 4: Log layering

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/log.py`, `addon/globalPlugins/WorldVoice/pipelineLog.py`
- Test: `tests/test_pipeline_log.py`; append to `tests/test_assembly_structure.py`

**Interfaces:**
- Produces:
  - `PipelineLog.move_to(dst: Path) -> None`;
  - `globalPlugins.WorldVoice.pipelineLog.export_with_dialog(log=None)`, where `None` means the pipeline's `pl`.

- [ ] **Step 1: Failing tests.** In `tests/test_pipeline_log.py`:
  - load the real `log.py` by path, with `addonHandler` *not* stubbed, to prove it no longer imports it. Point its `log_dir` at `tmp_path / "missing" / "log"` via `monkeypatch.setattr(module, "log_dir", ...)` before constructing;
  - test that constructing does not create the directory and the first `write` creates directory and header;
  - test that `move_to(dst)` moves the file to `dst` (creating `dst.parent`) and recreates an empty-header log;
  - `export_with_dialog` with a wx stub, for three cases:
    - dialog cancelled → no `move_to`;
    - OK → `move_to(Path(path))` and one `MessageBox`;
    - `move_to` raising → one `LogError` and no `MessageBox`.
  - Stub `wx.FileDialog` as a context manager whose `ShowModal` returns the scripted answer and `GetPath` returns `str(tmp_path / "out.csv")`.
  - Structure guard: `log.py`'s AST imports contain none of `wx`, `gui`, `addonHandler`, and its module body has no `mkdir` call.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - `log.py`:
    - remove the `addonHandler`, `gui` and `wx` imports, `initTranslation` and the module-level `mkdir`;
    - `_ensure_log_file` starts with `self.log_file.parent.mkdir(parents=True, exist_ok=True)`;
    - `_rotate_if_needed` is unchanged;
    - replace `export` with:

```python
	def move_to(self, dst: Path) -> None:
		"""Move the current log to dst and start a new, empty one."""
		dst.parent.mkdir(parents=True, exist_ok=True)
		shutil.move(str(self.log_file), str(dst))
		self._ensure_log_file()
```

    `__init__` only sets `self.log_file`.
  - `pipelineLog.py`: add `from pathlib import Path`, then:

```python
def export_with_dialog(log=None):
	log = log or pl
	with wx.FileDialog(
		gui.mainFrame,
		# Translators: The title of the Export pipeline log file window
		message=_("Export pipeline log files..."),
		defaultDir="",
		defaultFile="pipeline_log.csv",
		wildcard="csv files (*.csv)|*.csv",
		style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
	) as entryDialog:
		if entryDialog.ShowModal() != wx.ID_OK:
			return
		dst = Path(entryDialog.GetPath())

	try:
		log.move_to(dst)
		wx.MessageBox(
			_("Log exported to:\n{}").format(dst),
			_("Success"),
			style=wx.OK | wx.ICON_INFORMATION,
		)
	except Exception as e:  # noqa: BLE001 - reported to the user
		wx.LogError(
			_("Cannot export log to {}:\n{}").format(dst, e),
		)
```

    `PipelineLogService.__init__`: `self._exporter = exporter or export_with_dialog`. The hygiene guard's reason table already accepts `reported to the user`; check it with the guard test.
  - `export_with_dialog` is defined after `PipelineLogService`, but it is only looked up when `__init__` runs, so `pipeline_log = PipelineLogService()` must come after `export_with_dialog`'s definition. Move the `pipeline_log = ...` line below it.
  - The old stub in `load_service` (`pl=SimpleNamespace(export=...)`) changes to `pl=SimpleNamespace(move_to=...)`. Existing service tests that inject their own exporter are unchanged.
- [ ] **Step 4: Run** the full suite and the lint gate → PASS.
- [ ] **Step 5: Commit** `refactor: keep the pipeline log free of UI and disk work at import`.

---

### Task 5: Voice settings panel stays in sync with NVDA

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py`
- Create: `tests/test_nvda_settings_copy.py`

- [ ] **Step 1: Failing test** `tests/test_nvda_settings_copy.py`:

```python
ROOT = Path(__file__).resolve().parents[1]
NVDA = ROOT / "ref/nvda/source/gui/settingsDialogs.py"
COPY = ROOT / "addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py"
# ref/nvda 1406f9f8a: AutoSettingsMixin._updateValueForControl. WorldVoice's override reloads string
# options on purpose, so only a change on NVDA's side is detected; review the override when it fails.
UPDATE_VALUE_FINGERPRINT = "<sha256 computed in step 3>"

def method(path, cls, name):
	tree = ast.parse(path.read_text(encoding="utf-8"))
	(owner,) = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls]
	(fn,) = [n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == name]
	return fn

def without_docstring(fn):
	body = fn.body[1:] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) else fn.body
	return body

@pytest.fixture
def nvda():
	if not NVDA.is_file():
		pytest.skip("ref/nvda is not checked out")

def test_create_driver_settings_is_nvdas_update_driver_settings_over_all_settings(nvda):
	theirs = without_docstring(method(NVDA, "AutoSettingsMixin", "updateDriverSettings"))
	ours = [s for s in without_docstring(method(COPY, "WorldVoiceVoiceSettingsPanel", "createDriverSettings"))
		if not (isinstance(s, ast.Assign) and [t.id for t in s.targets if isinstance(t, ast.Name)] == ["supportedSettings"])]
	class AllSettings(ast.NodeTransformer):
		def visit_For(self, node):
			self.generic_visit(node)
			if ast.unparse(node.iter) == "settingsInst.supportedSettings":
				node.iter = ast.Name("supportedSettings", ast.Load())
			return node
	theirs = [AllSettings().visit(s) for s in theirs]
	assert [ast.dump(s) for s in ours] == [ast.dump(s) for s in theirs]

def test_nvda_update_value_for_control_is_the_reviewed_version(nvda):
	fn = method(NVDA, "AutoSettingsMixin", "_updateValueForControl")
	assert hashlib.sha256(ast.dump(fn).encode()).hexdigest() == UPDATE_VALUE_FINGERPRINT
```

- [ ] **Step 2: Run.** The structural test FAILS: the copy lacks NVDA's `startswith("_")` branch.
- [ ] **Step 3: Implement.** In `createDriverSettings`:
  - replace the comment with the spec's wording;
  - extend the docstring with the spec's purpose sentence;
  - add NVDA's branch between the update and create branches:

```python
			if setting.id in self.sizerDict:  # update a value
				self._updateValueForControl(setting, settingsStorage)
			elif setting.id.startswith("_"):
				# Skip private settings.
				continue
			else:  # create a new control
				self._createNewControl(setting, settingsStorage)
```

  - Compute the fingerprint with `python3 -c` using the same `method()` and paste it into the test.
  - If the structural comparison still differs in something else (for example the `gui._isDebug()` block), make the copy match NVDA's statement exactly. The spec requires identity apart from the settings source.
- [ ] **Step 4: Run** the test, the full suite and the lint gate → PASS. Then mutate one NVDA line in a scratch copy, by pointing `NVDA` at a temp file through `monkeypatch`, and confirm the structural test fails. Discard the mutation.
- [ ] **Step 5: Commit** `fix: keep the voice settings panel's NVDA copy in sync and guard it`.

---

Final verification:

```bash
python3 -m pytest tests -q
ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select F401,F821,BLE001,I001
ruff format --check addon
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver' addon/synthDrivers/WorldVoice/driver/sonic
```
