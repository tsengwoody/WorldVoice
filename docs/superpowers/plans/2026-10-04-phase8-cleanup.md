# Phase 8: Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the compatibility shims, `SpeechFuture.then` and the contextual legacy completion mode, and move scattered old records into `docs/history/`. User-visible behavior stays the same.

**Architecture:**
- **Task 1** deletes the three re-export modules and `SpeechFuture.then`:
  - the shims are `taskManager.py`, `requestBuilder.py` and `driver/engineSession.py`;
  - the main driver imports from `runtime` directly;
  - test loaders follow.
- **Task 2** removes contextual legacy from:
  - the models and the rule table, whose key becomes `CompletionMode`;
  - the adapter, the bridge and the voice manager.
- **Task 3** archives the old records and adds `docs/README.md`.
- **Task 4** is the final verification.

The pipeline (`order_move_to_end_register`, `with_order_log`, `self.order`) is untouched by decision.

**Tech Stack:** Python 3, pytest, ruff, git.

**Spec:** `docs/superpowers/specs/2026-10-04-phase8-cleanup-design.md`

## Global Constraints

- Work on branch `phase8-cleanup`, cut from `master` at `d7dca69`. The spec commits `cca83d6` and `2dc5483` and the plan commit are on it.
- **User-visible behavior is unchanged:** no in-repo engine and neither the MSC nor the Natural plugin implements `speak_legacy_segment`, and nothing imports the shims except the main driver and tests.
- **Do not change** `addon/synthDrivers/WorldVoice/pipeline/`, the main driver's `self.order`, any inner driver, or any outer wrapper under `driver/<Engine>/`. Only `driver/engineSession.py` is deleted under `driver/`.
- Never stage the user's unstaged deletion of `docs/superpowers/finish_task.md`. Never touch the untracked `refactor.md` or `git stash`. Stage explicit paths only.
- `docs/` is gitignored: add or move files there with `git add -f`/`git mv -f`.
- Every changed `addon/` file passes `ruff format --check`. Never commit `driver/Neural/`.
- Baseline before Task 1: `python3 -m pytest tests -q` → `1423 passed`.
- Each code step applies a patch saved verbatim from this plan. Set `PATCHES=$(mktemp -d)` once, save the block to the named file, then run `git apply`.
- **Mutation steps come after the commit step.** They end with `git checkout -- addon`.
- Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Nothing outside tests imported a shim.**
   - Search the add-on for `taskManager`, `requestBuilder` and `engineSession` as module names. The attribute `self.taskManager` is unrelated.
   - Check the NVDA entry points (`__init__.py`, `globalPlugins/`) and any `importlib` string paths.
2. **Removing `legacy_contextual` from `CompletionContract` changes its equality and constructor.**
   - Check that every `CompletionContract(...)` call site passes only `mode`/`index_range`.
   - The bridge's `existing.completion != completion` rebind check and the ledger's contract comparisons still compare what they did for the remaining modes.
3. **The bridge's plain-legacy path.**
   - `_receive` now forwards every non-correlated event to the handler. Before, contextual bindings returned early.
   - Check that no remaining binding is non-correlated yet expects segment-scoped delivery.
4. **The rule table keyed by `CompletionMode`.**
   - `rule_for` raises `KeyError` only for a mode with no row.
   - Check that the table covers every `CompletionMode` member; `test_every_completion_mode_has_exactly_one_rule` pins it.
5. **The archive moves.**
   - `git mv` keeps history for `review_gpt1.md` and the three validation reports.
   - The two `.superpowers/sdd/...` files leave the index but stay on disk. In the main checkout they are ignored by the local `.superpowers/sdd/.gitignore` (`*`), so they must not reappear as untracked.

---

### Task 1: Delete the compatibility shims and `SpeechFuture.then`

Spec §1 and §2.

**Files:**
- Delete:
  - `addon/synthDrivers/WorldVoice/taskManager.py`
  - `addon/synthDrivers/WorldVoice/requestBuilder.py`
  - `addon/synthDrivers/WorldVoice/driver/engineSession.py`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py` (two imports)
- Modify: `addon/synthDrivers/WorldVoice/runtime/scheduler.py` (`SpeechFuture` keeps its class, loses `then`, gets a new docstring)
- Test: `tests/test_cleanup_guards.py` (new)
- Test (follow the new paths):
  - `tests/test_f4_engine_session.py`: the `module` fixture reads `rt.session`/`rt.models`;
  - `tests/test_f4_engine_adapters.py`: its own `DRIVERS` path instead of `MODULE_PATH`;
  - `tests/test_legacy_speech_commands.py`;
  - `tests/test_worldvoice_request_builder.py`;
  - `tests/test_worldvoice_request_manager.py`.
- Test: `tests/test_runtime_scheduler.py`:
  - delete `test_then_flattens_results_errors_and_cancellation` and `test_then_public_cancel_racing_settlement_has_no_callback_error`;
  - `test_future_callback_can_cancel_and_submit` uses `add_done_callback`;
  - add `test_settle_future_lets_a_racing_public_cancel_win`, so `_settle_future`'s race branch keeps direct coverage.

**Interfaces:**
- Produces: the main driver imports `TaskManager` from `runtime.scheduler` and `queue_speech_sequence` from `runtime.requestBuilder`. `SpeechFuture` has no methods of its own.

- [ ] **Step 1: Write the guards and move the tests to the runtime paths**

Save as `$PATCHES/t1-tests.patch`, then run `git apply $PATCHES/t1-tests.patch`:

```diff
diff --git a/tests/test_cleanup_guards.py b/tests/test_cleanup_guards.py
new file mode 100644
index 0000000..f3fd7fc
--- /dev/null
+++ b/tests/test_cleanup_guards.py
@@ -0,0 +1,20 @@
+"""Removed compatibility layers and dead APIs stay removed."""
+
+import ast
+from pathlib import Path
+
+ADDON = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"
+
+
+def test_compatibility_shims_are_gone():
+	for shim in ("taskManager.py", "requestBuilder.py", "driver/engineSession.py"):
+		assert not (ADDON / shim).exists(), shim
+	text = (ADDON / "__init__.py").read_text(encoding="utf-8")
+	assert "from .runtime.scheduler import TaskManager\n" in text
+	assert "from .runtime.requestBuilder import queue_speech_sequence\n" in text
+
+
+def test_speech_future_has_no_then():
+	tree = ast.parse((ADDON / "runtime/scheduler.py").read_text(encoding="utf-8"))
+	future = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SpeechFuture")
+	assert [node.name for node in future.body if isinstance(node, ast.FunctionDef)] == []
diff --git a/tests/test_f4_engine_adapters.py b/tests/test_f4_engine_adapters.py
index 5f81cc9..b7d28a8 100644
--- a/tests/test_f4_engine_adapters.py
+++ b/tests/test_f4_engine_adapters.py
@@ -1,12 +1,15 @@
 import ast
+from pathlib import Path
 from dataclasses import replace
 import types
 
 import pytest
 
-from test_f4_engine_session import MODULE_PATH, module, snap, rt
+from test_f4_engine_session import module, snap, rt
 from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs
 
+DRIVERS = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/driver"
+
 
 @pytest.mark.parametrize("engine", ["VE", "Cerence"])
 def test_wrapper_settings_are_pending_until_activation(monkeypatch, engine, snap):
@@ -72,7 +75,7 @@ def test_variant_metadata_read_preserves_playback_state(monkeypatch, engine):
 
 
 def test_onecore_language_is_applied_only_on_activation():
-	path = MODULE_PATH.parent / "OneCore/__init__.py"
+	path = DRIVERS / "OneCore/__init__.py"
 	tree = ast.parse(path.read_text(encoding="utf-8"))
 	voice_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Voice")
 	class BaseVoice:
diff --git a/tests/test_f4_engine_session.py b/tests/test_f4_engine_session.py
index 3672de0..b847f31 100644
--- a/tests/test_f4_engine_session.py
+++ b/tests/test_f4_engine_session.py
@@ -10,22 +10,9 @@ from runtime_harness import MemoryRepository, make_spec, rt
 from test_runtime_legacy_adapter import compat
 
 
-MODULE_PATH = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/driver/engineSession.py"
-
-
 @pytest.fixture
-def module(monkeypatch, rt):
-    package = ModuleType("f4_session_boundary")
-    package.__path__ = [str(MODULE_PATH.parent.parent)]
-    driver = ModuleType("f4_session_boundary.driver")
-    driver.__path__ = [str(MODULE_PATH.parent)]
-    monkeypatch.setitem(sys.modules, package.__name__, package)
-    monkeypatch.setitem(sys.modules, driver.__name__, driver)
-    for suffix, value in (("", rt.package), (".models", rt.models), (".session", rt.session)):
-        monkeypatch.setitem(sys.modules, package.__name__ + ".runtime" + suffix, value)
-    name = driver.__name__ + ".engineSession"
-    monkeypatch.delitem(sys.modules, name, raising=False)
-    return importlib.import_module(name)
+def module(rt):
+    return SimpleNamespace(EngineSession=rt.session.EngineSession, VoiceSnapshot=rt.models.VoiceSnapshot)
 
 
 @pytest.fixture
diff --git a/tests/test_legacy_speech_commands.py b/tests/test_legacy_speech_commands.py
index 5ec3ce6..cad4dcc 100644
--- a/tests/test_legacy_speech_commands.py
+++ b/tests/test_legacy_speech_commands.py
@@ -22,7 +22,7 @@ def legacy(monkeypatch, rt, nvda_commands):
     monkeypatch.setitem(sys.modules, "languageHandler", SimpleNamespace())
     monkeypatch.setitem(sys.modules, "synthDriverHandler", SimpleNamespace(getSynth=lambda: None))
 
-    for suffix in ("driver", "driver.engineSession", "compat", "compat.commands", "_speechcommand"):
+    for suffix in ("driver", "compat", "compat.commands", "_speechcommand"):
         monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
     driver = importlib.import_module(name + ".driver")
     commands = importlib.import_module(name + ".compat.commands")
diff --git a/tests/test_runtime_scheduler.py b/tests/test_runtime_scheduler.py
index 65c568c..0db7445 100644
--- a/tests/test_runtime_scheduler.py
+++ b/tests/test_runtime_scheduler.py
@@ -284,12 +284,11 @@ def test_future_callback_can_cancel_and_submit(manager, port, rt, output):
         manager.append_speech(new, other, "Fake:b", ("new",))
         assert manager.submit_request(new)
         callback_done.set()
-    chained = future.then(callback)
+    future.add_done_callback(callback)
     assert manager.submit_request(request)
     assert port.entered.wait(1)
     event(manager, rt, port)
     assert callback_done.wait(1)
-    assert chained.result(1) is None
     assert output.wait_done() == 1
 
 
@@ -508,26 +507,6 @@ def test_direct_playback_stop_does_not_cancel_request(manager, port, rt, output)
     assert not request.token.is_cancelled()
 
 
-def test_then_flattens_results_errors_and_cancellation(scheduler):
-    future = scheduler.SpeechFuture()
-    chained = future.then(lambda f: f.result() + 1)
-    future.set_result(3)
-    assert chained.result(1) == 4
-    cancelled = scheduler.SpeechFuture()
-    next_future = cancelled.then(lambda _: 1)
-    cancelled.cancel()
-    assert next_future.cancelled()
-    inner = scheduler.SpeechFuture()
-    flattened = future.then(lambda _: inner)
-    inner.set_result(8)
-    assert flattened.result(1) == 8
-    failed = scheduler.SpeechFuture()
-    propagated = failed.then(lambda f: f.result())
-    failed.set_exception(ValueError("failed"))
-    with pytest.raises(ValueError, match="failed"):
-        propagated.result(1)
-
-
 def test_token_cancellation_inside_speak_suppresses_done(manager, port, output, scheduler):
     request = manager.new_request()
     future = manager.append_speech(request, port, "Fake:a", ())
@@ -715,31 +694,21 @@ def test_public_cancel_racing_abort_settles_remaining_futures(manager, monkeypat
     assert request.request_id not in manager._requests
 
 
-@pytest.mark.parametrize("flatten", [False, True])
-@pytest.mark.parametrize("outcome", ["result", "exception"])
-def test_then_public_cancel_racing_settlement_has_no_callback_error(
-        scheduler, monkeypatch, caplog, flatten, outcome):
-    source = scheduler.SpeechFuture()
-    inner = scheduler.SpeechFuture()
-    def callback(future):
-        if flatten:
-            return inner
-        if outcome == "exception":
-            raise ValueError("callback failed")
-        return 42
-    following = source.then(callback)
-    setter = getattr(following, "set_" + outcome)
-    def settle(value):
-        assert following.cancel()
-        setter(value)
-    monkeypatch.setattr(following, "set_" + outcome, settle)
-    source.set_result(None)
-    if flatten:
-        if outcome == "exception":
-            inner.set_exception(ValueError("inner failed"))
-        else:
-            inner.set_result(42)
-    assert following.cancelled()
+@pytest.mark.parametrize("outcome", ["result", "error"])
+def test_settle_future_lets_a_racing_public_cancel_win(scheduler, monkeypatch, caplog, outcome):
+    future = scheduler.SpeechFuture()
+    setter = "set_exception" if outcome == "error" else "set_result"
+    original = getattr(future, setter)
+    def cancel_then_settle(value):
+        # Public cancellation lands after _settle_future checked done().
+        assert future.cancel()
+        original(value)
+    monkeypatch.setattr(future, setter, cancel_then_settle)
+    if outcome == "error":
+        scheduler._settle_future(future, error=ValueError("late"))
+    else:
+        scheduler._settle_future(future, result=42)
+    assert future.cancelled()
     assert not caplog.records
 
 
diff --git a/tests/test_worldvoice_request_builder.py b/tests/test_worldvoice_request_builder.py
index f3be0f5..f61c940 100644
--- a/tests/test_worldvoice_request_builder.py
+++ b/tests/test_worldvoice_request_builder.py
@@ -47,8 +47,8 @@ def modules(monkeypatch, nvda_commands):
     def load(name):
         return importlib.import_module(package_name + "." + name)
     return types.SimpleNamespace(
-        driver=load("driver"), manager_module=load("taskManager"),
-        builder=load("requestBuilder"), models=load("runtime.models"),
+        driver=load("driver"), manager_module=load("runtime.scheduler"),
+        builder=load("runtime.requestBuilder"), models=load("runtime.models"),
         settings=load("runtime.settings"), session=load("runtime.session"),
         adapter=load("compat.engineAdapter"), facade=load("compat.voiceFacade"),
         commands=load("compat.commands"), bridge=load("nvdaEventBridge"),
diff --git a/tests/test_worldvoice_request_manager.py b/tests/test_worldvoice_request_manager.py
index 736ab60..f55009b 100644
--- a/tests/test_worldvoice_request_manager.py
+++ b/tests/test_worldvoice_request_manager.py
@@ -74,7 +74,7 @@ def task_module(monkeypatch, buses):
 	package = types.ModuleType(package_name)
 	package.__path__ = [str(root)]
 	monkeypatch.setitem(sys.modules, package_name, package)
-	module = importlib.import_module(package_name + ".taskManager")
+	module = importlib.import_module(package_name + ".runtime.scheduler")
 	bridge_module = importlib.import_module(package_name + ".nvdaEventBridge")
 	module.test_bridge_class = bridge_module.NvdaEventBridge
 	return module
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|^[0-9]+ (passed|failed)" | sed 's/ - .*//'`
Expected: `2 failed, 1420 passed`:
- `tests/test_cleanup_guards.py::test_compatibility_shims_are_gone`
- `tests/test_cleanup_guards.py::test_speech_future_has_no_then`

- [ ] **Step 3: Delete the shims and `then`**

Save as `$PATCHES/t1-impl.patch`, then run `git apply $PATCHES/t1-impl.patch`. The patch deletes the three shim files:

```diff
diff --git a/addon/synthDrivers/WorldVoice/__init__.py b/addon/synthDrivers/WorldVoice/__init__.py
index 2ce34f5..fef0937 100644
--- a/addon/synthDrivers/WorldVoice/__init__.py
+++ b/addon/synthDrivers/WorldVoice/__init__.py
@@ -50,8 +50,8 @@ from .nvdaEventBridge import NvdaEventBridge
 from .indexLedger import IndexLedger
 from .compat.completionPolicies import CompletionPolicy
 from .compat.commands import normalize_legacy_commands
-from .taskManager import TaskManager
-from .requestBuilder import queue_speech_sequence
+from .runtime.scheduler import TaskManager
+from .runtime.requestBuilder import queue_speech_sequence
 from .voiceManager import VoiceManager
 from .VoiceSettingsDialogs import WorldVoiceVoiceSettingsPanel
 
diff --git a/addon/synthDrivers/WorldVoice/driver/engineSession.py b/addon/synthDrivers/WorldVoice/driver/engineSession.py
deleted file mode 100644
index 1557150..0000000
--- a/addon/synthDrivers/WorldVoice/driver/engineSession.py
+++ /dev/null
@@ -1,6 +0,0 @@
-"""Compatibility imports; engine ownership lives in runtime.session."""
-
-from ..runtime.models import VoiceSnapshot
-from ..runtime.session import EngineSession
-
-__all__ = ["EngineSession", "VoiceSnapshot"]
diff --git a/addon/synthDrivers/WorldVoice/requestBuilder.py b/addon/synthDrivers/WorldVoice/requestBuilder.py
deleted file mode 100644
index 4284130..0000000
--- a/addon/synthDrivers/WorldVoice/requestBuilder.py
+++ /dev/null
@@ -1,5 +0,0 @@
-"""Legacy module path for the normalized runtime request builder."""
-
-from .runtime.requestBuilder import queue_speech_sequence
-
-__all__ = ["queue_speech_sequence"]
diff --git a/addon/synthDrivers/WorldVoice/runtime/scheduler.py b/addon/synthDrivers/WorldVoice/runtime/scheduler.py
index 373e2e9..10969a1 100644
--- a/addon/synthDrivers/WorldVoice/runtime/scheduler.py
+++ b/addon/synthDrivers/WorldVoice/runtime/scheduler.py
@@ -112,38 +112,7 @@ def _settle_future(future, *, result=None, error=None):
 
 
 class SpeechFuture(Future):
-	"""Future with the legacy callback-taking, Future-flattening then API."""
-
-	def then(self, fn):
-		following = SpeechFuture()
-
-		def transfer(result):
-			if following.done():
-				return
-			if result.cancelled():
-				following.cancel()
-			elif result.exception() is not None:
-				_settle_future(following, error=result.exception())
-			else:
-				_settle_future(following, result=result.result())
-
-		def callback(future):
-			if following.done():
-				return
-			if future.cancelled():
-				following.cancel()
-				return
-			try:
-				result = fn(future)
-				if isinstance(result, Future):
-					result.add_done_callback(transfer)
-				else:
-					_settle_future(following, result=result)
-			except Exception as error:
-				_settle_future(following, error=error)
-
-		self.add_done_callback(callback)
-		return following
+	"""The Future a speech or break task settles when it finishes."""
 
 
 class RequestState(Enum):
diff --git a/addon/synthDrivers/WorldVoice/taskManager.py b/addon/synthDrivers/WorldVoice/taskManager.py
deleted file mode 100644
index ed704ac..0000000
--- a/addon/synthDrivers/WorldVoice/taskManager.py
+++ /dev/null
@@ -1,21 +0,0 @@
-"""Compatibility exports for the independent runtime scheduler."""
-
-from .runtime.scheduler import (
-	CancellationToken,
-	InvalidRequestState,
-	NotificationOutput,
-	RequestState,
-	SpeechFuture,
-	SpeechRequest,
-	TaskManager,
-)
-
-__all__ = [
-	"CancellationToken",
-	"InvalidRequestState",
-	"NotificationOutput",
-	"RequestState",
-	"SpeechFuture",
-	"SpeechRequest",
-	"TaskManager",
-]
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1; ruff format --check addon | tail -1`
Expected: `1422 passed`, then `51 files already formatted`.

- [ ] **Step 5: Commit**

```bash
A=addon/synthDrivers/WorldVoice
git add $A/taskManager.py $A/requestBuilder.py $A/driver/engineSession.py $A/__init__.py $A/runtime/scheduler.py \
	tests/test_cleanup_guards.py tests/test_f4_engine_session.py tests/test_f4_engine_adapters.py \
	tests/test_legacy_speech_commands.py tests/test_worldvoice_request_builder.py \
	tests/test_worldvoice_request_manager.py tests/test_runtime_scheduler.py
git commit -m "refactor: drop the compatibility shims and SpeechFuture.then

taskManager.py, requestBuilder.py and driver/engineSession.py only
re-exported runtime modules; the driver now imports runtime directly.
SpeechFuture.then had no caller in the add-on.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the guards bite (mutations M1a–M1c, after the commit)**

```bash
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
A=addon/synthDrivers/WorldVoice
check() { timeout 600 python3 -m pytest tests -q -p no:cacheprovider 2>&1 | grep -E '^FAILED|^[0-9]+ (passed|failed)' | sed 's/ - .*//;s/ in .*//'; rm -f $A/taskManager.py; git checkout -- addon; }

echo M1a; printf 'from .runtime.scheduler import TaskManager\n' > $A/taskManager.py; check
echo M1b; mutate $A/runtime/scheduler.py '	"""The Future a speech or break task settles when it finishes."""
' '	"""The Future a speech or break task settles when it finishes."""

	def then(self, fn):
		return self
'; check
echo M1c; mutate $A/runtime/scheduler.py '	except InvalidStateError:
		if not future.cancelled():
			raise' '	except InvalidStateError:
		raise'; check
git status --short | grep addon
```

Expected (full-suite counts):
- M1a: a shim returns. `1 failed, 1421 passed`: `test_compatibility_shims_are_gone`.
- M1b: `SpeechFuture.then` returns. `1 failed, 1421 passed`: `test_speech_future_has_no_then`.
- M1c: `_settle_future` no longer lets a racing cancel win. `5 failed, 1417 passed`: two `test_public_cancel_racing_settlement_keeps_worker_alive` cases, `test_public_cancel_racing_abort_settles_remaining_futures`, and both `test_settle_future_lets_a_racing_public_cancel_win` cases.

The final `git status --short | grep addon` prints nothing.

---

### Task 2: Remove the contextual legacy completion mode

Spec §4.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/models.py` (drop `CompletionContract.legacy_contextual` and its check)
- Modify: `addon/synthDrivers/WorldVoice/runtime/completion.py`:
  - drop `SpeakEntry.LEGACY_SEGMENT` and the contextual row;
  - key `_RULES` by `CompletionMode`.
- Modify: `addon/synthDrivers/WorldVoice/compat/engineAdapter.py`:
  - drop `_speak_legacy_segment` and its `_ENTRIES` row, `_legacy_events` and `configure_legacy_segment_events`;
  - drop the two contextual checks and the legacy sink branch in `speak`.
- Modify: `addon/synthDrivers/WorldVoice/nvdaEventBridge.py`:
  - drop `legacy_segment_sink`;
  - drop the batch-handler check for contextual binds;
  - drop the contextual early return in `_receive`.
- Modify: `addon/synthDrivers/WorldVoice/voiceManager.py`:
  - drop `_resource_completion` (`_bind` calls `self._completion_for`);
  - drop the legacy sink branch and the unused `replace`/`CompletionMode` imports.
- Test: `tests/test_cleanup_guards.py` (contextual guard)
- Test: `tests/test_completion_rules.py`:
  - the table is keyed by mode;
  - `test_every_completion_mode_has_exactly_one_rule`;
  - `ALLOWED` drops `voiceManager.py`.
- Test: `tests/test_completion_characterization.py` (drop the contextual contract, entry and precondition rows)
- Test (delete the contextual tests):
  - `tests/test_runtime_legacy_adapter.py`: 3 tests;
  - `tests/test_nvda_event_bridge.py`: 2;
  - `tests/test_runtime_scheduler.py`: 2;
  - `tests/test_runtime_completion_policies.py`: 1.

**Interfaces:**
- Consumes: Task 1's tree.
- Produces: `CompletionContract(mode, index_range)` and `rule_for(contract) -> _RULES[contract.mode]`.

- [ ] **Step 1: Write the guard and update the tests**

Save as `$PATCHES/t2-tests.patch`, then run `git apply $PATCHES/t2-tests.patch`:

```diff
diff --git a/tests/test_cleanup_guards.py b/tests/test_cleanup_guards.py
index f3fd7fc..d6a867d 100644
--- a/tests/test_cleanup_guards.py
+++ b/tests/test_cleanup_guards.py
@@ -18,3 +18,23 @@ def test_speech_future_has_no_then():
 	tree = ast.parse((ADDON / "runtime/scheduler.py").read_text(encoding="utf-8"))
 	future = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SpeechFuture")
 	assert [node.name for node in future.body if isinstance(node, ast.FunctionDef)] == []
+
+
+CONTEXTUAL_LEGACY = (
+	"legacy_contextual",
+	"speak_legacy_segment",
+	"LEGACY_SEGMENT",
+	"legacy_segment_sink",
+	"configure_legacy_segment_events",
+)
+
+
+def test_contextual_legacy_mode_is_gone():
+	found = []
+	for path in sorted(ADDON.rglob("*.py")):
+		name = path.relative_to(ADDON).as_posix()
+		if name.startswith("driver/Neural/"):
+			continue  # Untracked, restored locally from storage/; not part of the add-on.
+		text = path.read_text(encoding="utf-8")
+		found.extend(f"{name}: {word}" for word in CONTEXTUAL_LEGACY if word in text)
+	assert found == []
diff --git a/tests/test_completion_characterization.py b/tests/test_completion_characterization.py
index c3c8e4a..d7da9f1 100644
--- a/tests/test_completion_characterization.py
+++ b/tests/test_completion_characterization.py
@@ -12,15 +12,13 @@ from runtime_harness import FakePlayback, RecordingOutput, load_index_support, l
 from test_runtime_legacy_adapter import Core, compat, legacy_class
 from test_worldvoice_index_command import nvda_commands
 
-CONTRACTS = ("plain", "contextual", "END_INDEX", "END_INDEX_AND_DRAIN", "DRAIN")
+CONTRACTS = ("plain", "END_INDEX", "END_INDEX_AND_DRAIN", "DRAIN")
 
 
 def contract(rt, name):
 	models = rt.models
 	if name == "plain":
 		return models.CompletionContract()
-	if name == "contextual":
-		return models.CompletionContract(legacy_contextual=True)
 	return models.CompletionContract(getattr(models.CompletionMode, name), models.IndexRange(1, 1000))
 
 
@@ -62,17 +60,6 @@ OUTCOMES = {
 		"drained_then_end": "pending",
 		"other_segment": "pending",
 	},
-	"contextual": {
-		"done_anonymous": "pending",
-		"done_own": "complete",
-		"end_own": "pending",
-		"drained_own": "pending",
-		"failed_own": "failed",
-		"failed_anonymous": "pending",
-		"end_then_drained": "pending",
-		"drained_then_end": "pending",
-		"other_segment": "pending",
-	},
 	"END_INDEX": {
 		"done_anonymous": "pending",
 		"done_own": "pending",
@@ -170,16 +157,13 @@ class EntryCore(Core):
 	def speak_segment(self, commands, token, *, context, on_event):
 		self.entries.append(("speak_segment", commands, on_event))
 
-	def speak_legacy_segment(self, commands, token, *, context, on_event):
-		self.entries.append(("speak_legacy_segment", commands, on_event))
-
 
 @pytest.fixture
 def adapter_env(monkeypatch, compat, rt, nvda_commands):
 	support = load_index_support(monkeypatch, rt, "worldvoice_compat_test")
 	ledgers = []
 
-	def make(name, *, ledger=True, segment_events=True, legacy_events=True):
+	def make(name, *, ledger=True, segment_events=True):
 		core = EntryCore()
 		cls = legacy_class(core)
 		index_ledger = support.ledger.IndexLedger() if ledger else None
@@ -194,12 +178,10 @@ def adapter_env(monkeypatch, compat, rt, nvda_commands):
 				index_ledger.bind(core, source_id, chosen)
 		else:
 			ledgers.append((adapter, None))
-		sinks = SimpleNamespace(segment=lambda event: None, legacy=lambda event: None)
+		sinks = SimpleNamespace(segment=lambda event: None)
 		if segment_events and chosen.mode in (rt.models.CompletionMode.DRAIN,
 				rt.models.CompletionMode.END_INDEX_AND_DRAIN):
 			adapter.configure_segment_events(lambda context: sinks.segment)
-		if legacy_events and chosen.legacy_contextual:
-			adapter.configure_legacy_segment_events(lambda context: sinks.legacy)
 		return SimpleNamespace(adapter=adapter, core=core, sinks=sinks,
 			context=rt.models.PlaybackContext(source_id, 1))
 
@@ -214,7 +196,6 @@ def adapter_env(monkeypatch, compat, rt, nvda_commands):
 # (native entry, markers encoded, event sink) per contract.
 ENTRIES = {
 	"plain": ("speak", False, None),
-	"contextual": ("speak_legacy_segment", False, "legacy"),
 	"END_INDEX": ("speak", True, None),
 	"END_INDEX_AND_DRAIN": ("speak_segment", True, "segment"),
 	"DRAIN": ("speak_segment", True, "segment"),
@@ -240,18 +221,14 @@ def test_adapter_entry_per_contract(adapter_env, name):
 
 
 @pytest.mark.parametrize("name,missing,error,message", [
-	("contextual", "context", ValueError, "Contextual legacy completion requires a playback context"),
 	("END_INDEX", "context", ValueError, "Correlated completion requires a playback context"),
 	("DRAIN", "context", ValueError, "Correlated completion requires a playback context"),
 	("END_INDEX", "ledger", ValueError, "Marker completion requires an index ledger"),
 	("DRAIN", "segment_events", RuntimeError, "Drain completion requires a segment event factory"),
 	("END_INDEX_AND_DRAIN", "segment_events", RuntimeError, "Drain completion requires a segment event factory"),
-	("contextual", "legacy_events", RuntimeError,
-		"Contextual legacy completion requires a segment event factory"),
 ])
 def test_adapter_precondition_errors_per_contract(adapter_env, name, missing, error, message):
-	env = adapter_env.make(name, ledger=missing != "ledger", segment_events=missing != "segment_events",
-		legacy_events=missing != "legacy_events")
+	env = adapter_env.make(name, ledger=missing != "ledger", segment_events=missing != "segment_events")
 	context = None if missing == "context" else env.context
 	with pytest.raises(error) as caught:
 		env.adapter.speak(("hello",), adapter_env.token, context=context)
diff --git a/tests/test_completion_rules.py b/tests/test_completion_rules.py
index e8d3cef..e2b7745 100644
--- a/tests/test_completion_rules.py
+++ b/tests/test_completion_rules.py
@@ -19,28 +19,27 @@ def completion(monkeypatch, rt):
 	return module
 
 
-def _contract(rt, mode, contextual=False):
+def _contract(rt, mode):
 	models = rt.models
 	mode = getattr(models.CompletionMode, mode)
 	if mode is models.CompletionMode.LEGACY_DONE:
-		return models.CompletionContract(legacy_contextual=contextual)
+		return models.CompletionContract()
 	return models.CompletionContract(mode, models.IndexRange(1, 10))
 
 
 # correlated, segment_scoped, end_event, drain_event, fails_on_segment_failed,
 # requires_end, requires_drain, entry
 TABLE = {
-	("LEGACY_DONE", False): (False, False, "DONE", None, False, True, False, "PLAIN"),
-	("LEGACY_DONE", True): (False, True, "DONE", None, True, True, False, "LEGACY_SEGMENT"),
-	("END_INDEX", False): (True, True, "SEGMENT_END", None, True, True, False, "PLAIN"),
-	("END_INDEX_AND_DRAIN", False): (True, True, "SEGMENT_END", "SEGMENT_DRAINED", True, True, True, "SEGMENT"),
-	("DRAIN", False): (True, True, "SEGMENT_END", "SEGMENT_DRAINED", True, False, True, "SEGMENT"),
+	"LEGACY_DONE": (False, False, "DONE", None, False, True, False, "PLAIN"),
+	"END_INDEX": (True, True, "SEGMENT_END", None, True, True, False, "PLAIN"),
+	"END_INDEX_AND_DRAIN": (True, True, "SEGMENT_END", "SEGMENT_DRAINED", True, True, True, "SEGMENT"),
+	"DRAIN": (True, True, "SEGMENT_END", "SEGMENT_DRAINED", True, False, True, "SEGMENT"),
 }
 
 
 @pytest.mark.parametrize("key", TABLE)
 def test_rule_table_rows(completion, rt, key):
-	rule = completion.rule_for(_contract(rt, *key))
+	rule = completion.rule_for(_contract(rt, key))
 	kinds = rt.models.EventKind
 	correlated, scoped, end, drain, fails, requires_end, requires_drain, entry = TABLE[key]
 	assert rule == completion.CompletionRule(
@@ -55,16 +54,15 @@ def test_rule_table_rows(completion, rt, key):
 	)
 
 
-def test_every_valid_contract_has_exactly_one_rule(completion, rt):
-	modes = rt.models.CompletionMode
-	valid = {(mode.name, False) for mode in modes} | {("LEGACY_DONE", True)}
-	assert set(TABLE) == valid
-	assert len({id(completion.rule_for(_contract(rt, *key))) for key in valid}) == len(valid)
+def test_every_completion_mode_has_exactly_one_rule(completion, rt):
+	modes = {mode.name for mode in rt.models.CompletionMode}
+	assert set(TABLE) == modes
+	assert len({id(completion.rule_for(_contract(rt, mode))) for mode in modes}) == len(modes)
 
 
 @pytest.mark.parametrize("key", TABLE)
 def test_rule_queries_read_only_the_rule_fields(completion, rt, key):
-	rule = completion.rule_for(_contract(rt, *key))
+	rule = completion.rule_for(_contract(rt, key))
 	kinds, signal = rt.models.EventKind, completion.Signal
 	assert rule.accepts_segment(7, 7) is rule.segment_scoped
 	assert rule.accepts_segment(7, None) is not rule.segment_scoped
@@ -117,7 +115,6 @@ ALLOWED = {
 	"runtime/completion.py": None,
 	"runtime/models.py": {"__post_init__"},
 	"compat/completionPolicies.py": None,
-	"voiceManager.py": {"_resource_completion"},
 }
 
 
diff --git a/tests/test_nvda_event_bridge.py b/tests/test_nvda_event_bridge.py
index ce2a8f9..3862074 100644
--- a/tests/test_nvda_event_bridge.py
+++ b/tests/test_nvda_event_bridge.py
@@ -76,42 +76,6 @@ def test_routes_bound_source_index_and_done(env):
     assert all(event.source_id is source_id for event in env.received)
 
 
-@pytest.mark.parametrize("release", ["unchanged", "unbind", "rebind", "close"])
-def test_contextual_legacy_supplier_rechecks_source_binding(env, release):
-    source, source_id, suppliers = object(), object(), []
-    contract = env.models.CompletionContract(legacy_contextual=True)
-    env.bridge.start(env.received.append, batch_handler=suppliers.append)
-    env.bridge.bind(source, source_id, completion=contract)
-    context = env.models.PlaybackContext(source_id, 7)
-    sink = env.bridge.legacy_segment_sink(source, context)
-    event = env.models.PlaybackEvent(env.models.EventKind.DONE, source_id, segment_id=7)
-    sink(event)
-    assert env.received == []
-    assert len(suppliers) == 1
-    if release == "close":
-        env.bridge.close()
-    elif release != "unchanged":
-        env.bridge.unbind(source_id)
-        if release == "rebind":
-            env.bridge.bind(source, source_id, completion=contract)
-    assert suppliers[0]() == ((event,) if release == "unchanged" else ())
-
-
-@pytest.mark.parametrize("mismatch", ["source", "segment", "anonymous", "drain"])
-def test_contextual_legacy_sink_rejects_unrelated_events(env, mismatch):
-    source, source_id, suppliers = object(), object(), []
-    env.bridge.start(env.received.append, batch_handler=suppliers.append)
-    env.bridge.bind(source, source_id, completion=env.models.CompletionContract(legacy_contextual=True))
-    context = env.models.PlaybackContext(source_id, 7)
-    sink = env.bridge.legacy_segment_sink(source, context)
-    event = env.models.PlaybackEvent(
-        env.models.EventKind.SEGMENT_DRAINED if mismatch == "drain" else env.models.EventKind.DONE,
-        object() if mismatch == "source" else source_id,
-        segment_id=8 if mismatch == "segment" else None if mismatch == "anonymous" else 7)
-    sink(event)
-    assert suppliers == []
-
-
 def test_unknown_and_owner_sources_are_ignored(env):
     env.bridge.bind(env.owner, object())
     env.bridge.start(env.received.append)
diff --git a/tests/test_runtime_completion_policies.py b/tests/test_runtime_completion_policies.py
index b919b68..3635a14 100644
--- a/tests/test_runtime_completion_policies.py
+++ b/tests/test_runtime_completion_policies.py
@@ -157,13 +157,6 @@ def test_invalid_range_is_rejected(env, minimum, maximum):
         env.models.IndexRange(minimum, maximum)
 
 
-@pytest.mark.parametrize("mode", ["END_INDEX", "DRAIN"])
-def test_contextual_legacy_option_cannot_change_marker_completion(env, mode):
-    with pytest.raises(ValueError):
-        env.models.CompletionContract(getattr(env.models.CompletionMode, mode),
-            env.models.IndexRange(1, 9999), legacy_contextual=True)
-
-
 def make_adapter(env):
     class Voice:
         @classmethod
diff --git a/tests/test_runtime_legacy_adapter.py b/tests/test_runtime_legacy_adapter.py
index a18e030..7b07a45 100644
--- a/tests/test_runtime_legacy_adapter.py
+++ b/tests/test_runtime_legacy_adapter.py
@@ -122,30 +122,6 @@ def test_lifecycle_metadata_and_apply_order(compat, rt):
     assert (cls.opens, cls.closes) == (2, 2)
 
 
-def test_contextual_legacy_reopen_reconfigures_segment_events(compat, rt):
-    core = Core()
-    core.speak_legacy_segment = lambda commands, token, *, context, on_event: core.spoken.append(
-        (commands, context, token, on_event))
-    cls = legacy_class(core)
-    adapter = compat.adapter.LegacyEngineAdapter(
-        cls, lambda key: cls(), completion=rt.models.CompletionContract(
-            mode=rt.models.CompletionMode.LEGACY_DONE, legacy_contextual=True))
-    first_context = rt.models.PlaybackContext(11, 21)
-    first_sink = lambda event: None
-    adapter.open()
-    adapter.configure_legacy_segment_events(lambda context: first_sink)
-    token = SimpleNamespace(is_cancelled=lambda: False)
-    adapter.speak(("first",), token, context=first_context)
-    adapter.close()
-
-    adapter.open()
-    second_context = rt.models.PlaybackContext(12, 22)
-    second_sink = lambda event: None
-    adapter.configure_legacy_segment_events(lambda context: second_sink)
-    adapter.speak(("second",), token, context=second_context)
-    assert core.spoken[-1] == (("second",), second_context, token, second_sink)
-
-
 @pytest.mark.parametrize("extra", [{}, {"name": "noncanonical", "description": "", "locale": "en_US"}])
 def test_voice_metadata_defaults_and_canonical_key(compat, rt, extra):
     cls = legacy_class(Core())
@@ -416,48 +392,6 @@ def test_legacy_without_context_preserves_commands(compat, monkeypatch):
     assert core.spoken[0][0] is commands
 
 
-def test_contextual_legacy_entry_preserves_commands_and_original_context(compat, rt):
-    core, calls, events = Core(), [], []
-
-    def speak_legacy_segment(commands, token, *, context, on_event):
-        calls.append((commands, token, context))
-        on_event(rt.models.PlaybackEvent(rt.models.EventKind.DONE, context.source_id,
-                                        segment_id=context.segment_id))
-
-    core.speak_legacy_segment = speak_legacy_segment
-    cls = legacy_class(core)
-    adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
-    adapter.open()
-    adapter.configure_completion(rt.models.CompletionContract(legacy_contextual=True))
-    adapter.configure_legacy_segment_events(lambda context: events.append)
-    commands = ("hello", object())
-    token = SimpleNamespace(is_cancelled=lambda: False)
-    context = rt.models.PlaybackContext(object(), 4)
-    try:
-        adapter.speak(commands, token, context=context)
-        assert calls == [(commands, token, context)]
-        assert calls[0][0] is commands and calls[0][2] is context
-        assert events == [rt.models.PlaybackEvent(rt.models.EventKind.DONE, context.source_id, segment_id=4)]
-        assert core.spoken == []
-    finally:
-        adapter.close()
-
-
-def test_contextual_legacy_requires_context_instead_of_anonymous_fallback(compat, rt):
-    core = Core()
-    core.speak_legacy_segment = lambda *args, **kwargs: pytest.fail("Missing context reached native entry")
-    cls = legacy_class(core)
-    adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
-    adapter.open()
-    adapter.configure_completion(rt.models.CompletionContract(legacy_contextual=True))
-    try:
-        with pytest.raises(ValueError, match="context"):
-            adapter.speak(("hello",), SimpleNamespace(is_cancelled=lambda: False))
-        assert core.spoken == []
-    finally:
-        adapter.close()
-
-
 def test_marker_mode_requires_context(marker_env):
     env = marker_env
     with pytest.raises(ValueError, match="context"):
diff --git a/tests/test_runtime_scheduler.py b/tests/test_runtime_scheduler.py
index 0db7445..a159e77 100644
--- a/tests/test_runtime_scheduler.py
+++ b/tests/test_runtime_scheduler.py
@@ -63,35 +63,6 @@ def test_synchronous_done_finishes_once(manager, port, output, rt, scheduler):
     assert port.spoken == [(("hello",), request.token)]
 
 
-def test_contextual_legacy_completion_requires_exact_segment_identity(manager, port, output, rt):
-    port.completion = rt.models.CompletionContract(legacy_contextual=True)
-    request, future = speech(manager, port)
-    task = request.tasks[0]
-    for source, segment in ((port.source_id, None), (port.source_id, task.segment_id + 1),
-                            (object(), task.segment_id)):
-        manager.on_event(rt.models.PlaybackEvent(rt.models.EventKind.DONE, source, segment_id=segment))
-        assert not future.done()
-    manager.on_event(rt.models.PlaybackEvent(rt.models.EventKind.DONE, port.source_id,
-                                            segment_id=task.segment_id))
-    assert future.result(1) is True
-    assert output.wait_done() == 1
-
-
-def test_contextual_legacy_segment_failure_fails_request(manager, port, output, rt, scheduler):
-    # A contextual legacy segment that fails (e.g. a pause/resume fault) must
-    # fail its request instead of waiting for a DONE that never comes.
-    port.completion = rt.models.CompletionContract(legacy_contextual=True)
-    request, future = speech(manager, port)
-    task = request.tasks[0]
-    error = OSError("audio control failed")
-    manager.on_event(rt.models.PlaybackEvent(rt.models.EventKind.SEGMENT_FAILED, port.source_id,
-                                            segment_id=task.segment_id, error=error))
-    with pytest.raises(OSError, match="audio control failed"):
-        future.result(1)
-    assert output.wait_done() == 1
-    assert request.state is scheduler.RequestState.FAILED
-
-
 def test_synchronous_done_advances_only_after_speak_returns(manager, port, output, rt):
     second = FakePlayback()
     release = Event()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|^[0-9]+ (passed|failed)" | sed 's/ - .*//'`
Expected: `2 failed, 1392 passed`:
- `tests/test_cleanup_guards.py::test_contextual_legacy_mode_is_gone`
- `tests/test_completion_rules.py::test_completion_mode_is_compared_only_where_contracts_are_built`: `voiceManager._resource_completion` is no longer allowed to compare modes.

- [ ] **Step 3: Remove contextual legacy**

Save as `$PATCHES/t2-impl.patch`, then run `git apply $PATCHES/t2-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/compat/engineAdapter.py b/addon/synthDrivers/WorldVoice/compat/engineAdapter.py
index de0806d..26b33e9 100644
--- a/addon/synthDrivers/WorldVoice/compat/engineAdapter.py
+++ b/addon/synthDrivers/WorldVoice/compat/engineAdapter.py
@@ -26,10 +26,6 @@ def _speak_segment(adapter, commands, token, context, on_event):
 	adapter._core.speak_segment(commands, token, context=context, on_event=on_event)
 
 
-def _speak_legacy_segment(adapter, commands, token, context, on_event):
-	adapter._core.speak_legacy_segment(commands, token, context=context, on_event=on_event)
-
-
 def _speak_plain(adapter, commands, token, context, on_event):
 	if adapter.capabilities.supports_cancellation_token:
 		adapter._core.speak(commands, cancellationToken=token)
@@ -40,7 +36,6 @@ def _speak_plain(adapter, commands, token, context, on_event):
 # The completion rule names the core entry; each entry has its own signature.
 _ENTRIES = {
 	SpeakEntry.SEGMENT: _speak_segment,
-	SpeakEntry.LEGACY_SEGMENT: _speak_legacy_segment,
 	SpeakEntry.PLAIN: _speak_plain,
 }
 
@@ -60,7 +55,6 @@ class LegacyEngineAdapter:
 		self._completion = completion or CompletionContract()
 		self._completion_configured = completion is not None
 		self._segment_events: Callable[[PlaybackContext], SegmentEventSink] | None = None
-		self._legacy_events: Callable[[PlaybackContext], SegmentEventSink] | None = None
 		self._spoken = False
 		self._source_id = None
 		self._opened = False
@@ -98,18 +92,6 @@ class LegacyEngineAdapter:
 			raise TypeError("Segment event factory must be callable")
 		self._segment_events = factory
 
-	def configure_legacy_segment_events(self, factory: Callable[[PlaybackContext], SegmentEventSink]) -> None:
-		"""Connect software-correlated legacy events without certifying drain."""
-		if not self._opened or not self._completion_configured or self._spoken:
-			raise RuntimeError("Legacy events must be configured after completion and before speech")
-		if not self._completion.legacy_contextual or not callable(
-			getattr(self._core, "speak_legacy_segment", None),
-		):
-			raise ValueError("Contextual legacy events require a callable speak_legacy_segment entry")
-		if not callable(factory):
-			raise TypeError("Legacy segment event factory must be callable")
-		self._legacy_events = factory
-
 	def close(self) -> None:
 		if not self._opened:
 			return
@@ -118,7 +100,6 @@ class LegacyEngineAdapter:
 		self._core = None
 		self.notification_source = None
 		self._segment_events = None
-		self._legacy_events = None
 		self._spoken = False
 		self._voice_class.destroy_core(core)
 
@@ -173,9 +154,6 @@ class LegacyEngineAdapter:
 	) -> None:
 		self._spoken = True
 		rule = rule_for(self._completion)
-		contextual = rule.entry is SpeakEntry.LEGACY_SEGMENT
-		if contextual and context is None:
-			raise ValueError("Contextual legacy completion requires a playback context")
 		if rule.correlated:
 			if context is None:
 				raise ValueError("Correlated completion requires a playback context")
@@ -184,8 +162,6 @@ class LegacyEngineAdapter:
 			self._source_id = context.source_id
 		if rule.drain_event is not None and self._segment_events is None:
 			raise RuntimeError("Drain completion requires a segment event factory")
-		if contextual and self._legacy_events is None:
-			raise RuntimeError("Contextual legacy completion requires a segment event factory")
 		if token.is_cancelled():
 			if rule.correlated:
 				self.finish_segment(context)
@@ -196,11 +172,7 @@ class LegacyEngineAdapter:
 				from .indexCodec import encode_segment
 
 				commands = encode_segment(commands, context, self._index_ledger)
-			on_event = None
-			if rule.entry is SpeakEntry.SEGMENT:
-				on_event = self._segment_events(context)
-			elif contextual:
-				on_event = self._legacy_events(context)
+			on_event = self._segment_events(context) if rule.entry is SpeakEntry.SEGMENT else None
 			if token.is_cancelled():
 				if rule.correlated:
 					self.finish_segment(context)
diff --git a/addon/synthDrivers/WorldVoice/nvdaEventBridge.py b/addon/synthDrivers/WorldVoice/nvdaEventBridge.py
index c374610..fd53053 100644
--- a/addon/synthDrivers/WorldVoice/nvdaEventBridge.py
+++ b/addon/synthDrivers/WorldVoice/nvdaEventBridge.py
@@ -105,8 +105,6 @@ class NvdaEventBridge:
 				if existing.completion != completion:
 					raise ValueError("Notification source cannot change its completion contract")
 				return
-			if completion.legacy_contextual and self._batch_handler is None:
-				raise ValueError("Contextual legacy completion requires a batch handler")
 			ledger_token = None
 			if rule_for(completion).correlated:
 				if self._index_ledger is None or self._batch_handler is None:
@@ -176,40 +174,6 @@ class NvdaEventBridge:
 
 		return receive
 
-	def legacy_segment_sink(self, source: object, context: PlaybackContext) -> SegmentEventSink:
-		"""Capture legacy event identity without claiming native drain support."""
-		with self._lock:
-			binding = self._sources.get(id(source))
-			if (
-				self._closed
-				or source is self._owner
-				or binding is None
-				or binding.source is not source
-				or binding.source_id is not context.source_id
-				or not binding.completion.legacy_contextual
-				or self._batch_handler is None
-			):
-				raise ValueError("Legacy segment events require a matching contextual legacy binding")
-			batch_handler = self._batch_handler
-
-		def receive(event: PlaybackEvent) -> None:
-			if (
-				event.kind not in (EventKind.INDEX, EventKind.DONE, EventKind.SEGMENT_FAILED)
-				or event.source_id is not context.source_id
-				or event.segment_id != context.segment_id
-				or not self._binding_is_active(binding)
-			):
-				return
-
-			def load_events() -> tuple[PlaybackEvent, ...]:
-				if not self._binding_is_active(binding):
-					return ()
-				return _BindingEvents((event,), lambda: self._binding_is_active(binding))
-
-			batch_handler(load_events)
-
-		return receive
-
 	def close(self) -> None:
 		with self._lock:
 			if self._closed:
@@ -254,8 +218,6 @@ class NvdaEventBridge:
 			handler = self._handler
 			batch_handler = self._batch_handler
 		if not rule_for(binding.completion).correlated:
-			if binding.completion.legacy_contextual:
-				return  # Only the context-bound sink may complete this source.
 			if handler is not None:
 				handler(PlaybackEvent(kind, binding.source_id, index))
 		elif kind is EventKind.INDEX and batch_handler is not None:
diff --git a/addon/synthDrivers/WorldVoice/runtime/completion.py b/addon/synthDrivers/WorldVoice/runtime/completion.py
index 9f5cc4e..2d14e7b 100644
--- a/addon/synthDrivers/WorldVoice/runtime/completion.py
+++ b/addon/synthDrivers/WorldVoice/runtime/completion.py
@@ -15,7 +15,6 @@ class SpeakEntry(Enum):
 	"""Which core entry the adapter calls; runtime never calls a core itself."""
 
 	SEGMENT = "segment"  # speak_segment(commands, token, context=, on_event=)
-	LEGACY_SEGMENT = "legacy_segment"  # speak_legacy_segment(commands, token, context=, on_event=)
 	PLAIN = "plain"  # speak(commands[, cancellationToken=])
 
 
@@ -64,7 +63,7 @@ class CompletionRule:
 
 
 _RULES = {
-	(CompletionMode.LEGACY_DONE, False): CompletionRule(
+	CompletionMode.LEGACY_DONE: CompletionRule(
 		correlated=False,
 		segment_scoped=False,
 		end_event=EventKind.DONE,
@@ -74,18 +73,7 @@ _RULES = {
 		requires_drain=False,
 		entry=SpeakEntry.PLAIN,
 	),
-	# Contextual legacy: software-correlated DONE without a native drain barrier.
-	(CompletionMode.LEGACY_DONE, True): CompletionRule(
-		correlated=False,
-		segment_scoped=True,
-		end_event=EventKind.DONE,
-		drain_event=None,
-		fails_on_segment_failed=True,
-		requires_end=True,
-		requires_drain=False,
-		entry=SpeakEntry.LEGACY_SEGMENT,
-	),
-	(CompletionMode.END_INDEX, False): CompletionRule(
+	CompletionMode.END_INDEX: CompletionRule(
 		correlated=True,
 		segment_scoped=True,
 		end_event=EventKind.SEGMENT_END,
@@ -95,7 +83,7 @@ _RULES = {
 		requires_drain=False,
 		entry=SpeakEntry.PLAIN,
 	),
-	(CompletionMode.END_INDEX_AND_DRAIN, False): CompletionRule(
+	CompletionMode.END_INDEX_AND_DRAIN: CompletionRule(
 		correlated=True,
 		segment_scoped=True,
 		end_event=EventKind.SEGMENT_END,
@@ -106,7 +94,7 @@ _RULES = {
 		entry=SpeakEntry.SEGMENT,
 	),
 	# A drain segment has no terminal marker; SEGMENT_END is recorded but never required.
-	(CompletionMode.DRAIN, False): CompletionRule(
+	CompletionMode.DRAIN: CompletionRule(
 		correlated=True,
 		segment_scoped=True,
 		end_event=EventKind.SEGMENT_END,
@@ -120,4 +108,4 @@ _RULES = {
 
 
 def rule_for(contract: CompletionContract) -> CompletionRule:
-	return _RULES[(contract.mode, contract.legacy_contextual)]
+	return _RULES[contract.mode]
diff --git a/addon/synthDrivers/WorldVoice/runtime/models.py b/addon/synthDrivers/WorldVoice/runtime/models.py
index a2a1467..6c842a8 100644
--- a/addon/synthDrivers/WorldVoice/runtime/models.py
+++ b/addon/synthDrivers/WorldVoice/runtime/models.py
@@ -75,12 +75,8 @@ class CompletionContract:
 
 	mode: CompletionMode = CompletionMode.LEGACY_DONE
 	index_range: IndexRange | None = None
-	# Software event identity does not certify a native drain barrier.
-	legacy_contextual: bool = False
 
 	def __post_init__(self):
-		if self.legacy_contextual and self.mode is not CompletionMode.LEGACY_DONE:
-			raise ValueError("Contextual legacy events require legacy completion")
 		if self.mode is CompletionMode.LEGACY_DONE:
 			if self.index_range is not None:
 				raise ValueError("Legacy completion cannot declare an index range")
diff --git a/addon/synthDrivers/WorldVoice/voiceManager.py b/addon/synthDrivers/WorldVoice/voiceManager.py
index dcecc0e..11147d2 100644
--- a/addon/synthDrivers/WorldVoice/voiceManager.py
+++ b/addon/synthDrivers/WorldVoice/voiceManager.py
@@ -1,6 +1,6 @@
 from collections import OrderedDict, defaultdict
 from collections.abc import Mapping
-from dataclasses import dataclass, replace
+from dataclasses import dataclass
 from operator import attrgetter
 from typing import Callable, TypeVar, Dict, List
 import re
@@ -13,7 +13,7 @@ from synthDriverHandler import VoiceInfo
 from .compat.engineAdapter import LegacyEngineAdapter
 from .compat.voiceFacade import LegacyVoiceBinding
 from .runtime.completion import rule_for
-from .runtime.models import VoiceSpec, EngineCapabilities, CompletionContract, CompletionMode
+from .runtime.models import VoiceSpec, EngineCapabilities, CompletionContract
 from .indexLedger import IndexLedger
 from .runtime.session import EngineSession, PlaybackPort
 from .runtime.scheduler import TaskManager
@@ -143,7 +143,7 @@ class VoiceManager(object):
 	def _bind(self, resource: EngineResource) -> None:
 		adapter, session = resource.adapter, resource.session
 		source = adapter.notification_source
-		completion = self._resource_completion(resource.voice_class, source)
+		completion = self._completion_for(resource.voice_class, source)
 		adapter.configure_completion(completion)
 		# Claim ownership before binding, since bind may register then raise.
 		self._bridge.bind(source, session.source_id, completion=completion)
@@ -151,10 +151,6 @@ class VoiceManager(object):
 			adapter.configure_segment_events(
 				lambda context: self._bridge.segment_sink(source, context),
 			)
-		elif completion.legacy_contextual:
-			adapter.configure_legacy_segment_events(
-				lambda context: self._bridge.legacy_segment_sink(source, context),
-			)
 
 	def _publish(self, resource: EngineResource) -> None:
 		# Only bound, operational resources become visible to resolvers.
@@ -163,14 +159,6 @@ class VoiceManager(object):
 		for spec in resource.adapter.list_voices():
 			self._specs[spec.name] = spec
 
-	def _resource_completion(self, cls, source):
-		completion = self._completion_for(cls, source)
-		if completion.mode is CompletionMode.LEGACY_DONE and callable(
-			getattr(source, "speak_legacy_segment", None),
-		):
-			completion = replace(completion, legacy_contextual=True)
-		return completion
-
 	def terminate(self, *, commit=True):
 		if self._terminated:
 			return
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1; ruff format --check addon | tail -1; grep -rn -i "contextual legacy\|legacy_contextual" addon/synthDrivers/WorldVoice --include=*.py | grep -v driver/Neural`
Expected: `1394 passed`, then `51 files already formatted`, then no grep output.

- [ ] **Step 5: Commit**

```bash
A=addon/synthDrivers/WorldVoice
git add $A/runtime/models.py $A/runtime/completion.py $A/compat/engineAdapter.py $A/nvdaEventBridge.py $A/voiceManager.py \
	tests/test_cleanup_guards.py tests/test_completion_rules.py tests/test_completion_characterization.py \
	tests/test_runtime_legacy_adapter.py tests/test_nvda_event_bridge.py tests/test_runtime_scheduler.py \
	tests/test_runtime_completion_policies.py
git commit -m "refactor: remove the contextual legacy completion mode

Only the Neural driver ever implemented speak_legacy_segment, and it no
longer loads. The contract flag, its rule row and speak entry, the
adapter and bridge plumbing and the voice manager's selection branch are
gone; the completion rule table is keyed by CompletionMode alone.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the guards bite (mutations M2a–M2b, after the commit)**

```bash
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
A=addon/synthDrivers/WorldVoice
check() { timeout 600 python3 -m pytest tests -q -p no:cacheprovider 2>&1 | grep -E '^FAILED|^[0-9]+ (passed|failed)' | sed 's/ - .*//;s/ in .*//'; git checkout -- addon; }

echo M2a; mutate $A/runtime/models.py '	index_range: IndexRange | None = None
' '	index_range: IndexRange | None = None
	legacy_contextual: bool = False
'; check
echo M2b; printf '\n\ndef _legacy_completion(completion):\n\treturn completion.mode is CompletionMode.LEGACY_DONE\n' >> $A/voiceManager.py; check
git status --short | grep addon
```

Expected (full-suite counts):
- M2a: `legacy_contextual` returns to the contract. `1 failed, 1393 passed`: `test_contextual_legacy_mode_is_gone`.
- M2b: the voice manager compares a `CompletionMode` again. `1 failed, 1393 passed`: `test_completion_mode_is_compared_only_where_contracts_are_built`.

The final `git status --short | grep addon` prints nothing.

---

### Task 3: Archive the old records

Spec §5. This task moves documents only; its checks are the commands below.

**Files:**
- Move: `review_gpt1.md` → `docs/history/review_gpt1.md`
- Move: `docs/superpowers/finish/*.md` (3 files) → `docs/history/`
- Untrack: `.superpowers/sdd/2026-09-30-worldvoice-shared-segment-lifecycle/task-10-report.md` and `task-4-followup-report.md` (files stay on disk)
- Create: `docs/README.md`

- [ ] **Step 1: Move and untrack**

```bash
mkdir -p docs/history
git mv review_gpt1.md docs/history/review_gpt1.md
for f in docs/superpowers/finish/*.md; do git mv -f "$f" docs/history/; done
git rm -q --cached .superpowers/sdd/2026-09-30-worldvoice-shared-segment-lifecycle/task-10-report.md \
	.superpowers/sdd/2026-09-30-worldvoice-shared-segment-lifecycle/task-4-followup-report.md
```

- [ ] **Step 2: Add `docs/README.md`**

Create `docs/README.md` with exactly this content, then run `git add -f docs/README.md`:

```markdown
# Development records

These documents record how WorldVoice was developed. They are not the current
specification: the code and its tests are.

- `superpowers/specs/` and `superpowers/plans/`: the design spec and the
  implementation plan of each refactoring phase.
- `history/`: earlier reviews and validation reports, kept for reference.
```

- [ ] **Step 3: Check the index**

Run: `git status --short`
Expected, in any order:
- `D  .superpowers/sdd/2026-09-30-worldvoice-shared-segment-lifecycle/task-10-report.md`
- `D  .superpowers/sdd/2026-09-30-worldvoice-shared-segment-lifecycle/task-4-followup-report.md`
- `A  docs/README.md`
- `R  docs/superpowers/finish/2026-09-26-voice-runtime-boundaries-validation.md -> docs/history/2026-09-26-voice-runtime-boundaries-validation.md`
- `R  docs/superpowers/finish/2026-09-27-worldvoice-segment-index-validation.md -> docs/history/2026-09-27-worldvoice-segment-index-validation.md`
- `R  docs/superpowers/finish/2026-09-28-worldvoice-correlated-drain-validation.md -> docs/history/2026-09-28-worldvoice-correlated-drain-validation.md`
- `R  review_gpt1.md -> docs/history/review_gpt1.md`
- the user's ` D docs/superpowers/finish_task.md` (unstaged, untouched)
- `?? refactor.md`

No new `??` line for the two `.superpowers/sdd` files: the local `.superpowers/sdd/.gitignore` ignores them. Both files still exist on disk (`ls .superpowers/sdd/2026-09-30-worldvoice-shared-segment-lifecycle/`).

- [ ] **Step 4: Commit**

```bash
git commit -m "docs: archive old review and validation records under docs/history

Move review_gpt1.md and the validation reports out of the active
docs/superpowers tree, stop tracking two stray execution ledgers, and
explain in docs/README.md that these are development records.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

The commit takes only the staged paths. Do not `git add -A`: that would stage the user's deletion of `docs/superpowers/finish_task.md`.

---

### Task 4: Final verification

**Files:** none modified.

- [ ] **Step 1: Stability**

Run: `for i in 1 2 3 4 5; do python3 -m pytest tests/test_cleanup_guards.py tests/test_completion_rules.py tests/test_completion_characterization.py tests/test_runtime_scheduler.py tests/test_runtime_legacy_adapter.py tests/test_nvda_event_bridge.py tests/test_runtime_completion_policies.py tests/test_worldvoice_request_builder.py tests/test_worldvoice_request_manager.py tests/test_f4_engine_session.py tests/test_f4_engine_adapters.py tests/test_legacy_speech_commands.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `5 401 passed`.

Run: `for i in $(seq 1 20); do python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `20 233 passed`.

- [ ] **Step 2: Scope**

Run:
```bash
git diff master --stat -- addon/synthDrivers/WorldVoice/driver addon/synthDrivers/WorldVoice/pipeline | cat
git diff master -- addon/synthDrivers/WorldVoice/__init__.py | grep '^[-+]' | grep -v '^+++\|^---'
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
ruff format --check addon | tail -1
```
Expected:
- Only `addon/synthDrivers/WorldVoice/driver/engineSession.py | 6 ------`.
- The main driver diff is exactly the two import lines (`taskManager` → `runtime.scheduler`, `requestBuilder` → `runtime.requestBuilder`).
- No `ls-files` output, then `51 files already formatted`.

- [ ] **Step 3: Full suite and history**

Run: `python3 -m pytest tests -q 2>&1 | tail -1; git log --oneline master..HEAD`
Expected: `1394 passed`. The log lists, oldest at the bottom:
1. `docs: add phase 8 cleanup design spec`
2. `docs: keep the pipeline unchanged in the phase 8 spec`
3. `docs: add phase 8 implementation plan and amend its spec`
4. `refactor: drop the compatibility shims and SpeechFuture.then`
5. `refactor: remove the contextual legacy completion mode`
6. `docs: archive old review and validation records under docs/history`
