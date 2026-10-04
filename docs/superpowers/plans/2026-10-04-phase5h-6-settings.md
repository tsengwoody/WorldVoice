# Phase 5½ + 6 Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the phase 5½ quick fixes, and make `config.conf["WorldVoice"]["pipeline"]` the single source of truth for pipeline settings, driven by one settings table, one service, one `STAGES` registry, a `SpeechContext`, and a `PipelineScope`.

**Architecture:**
- `pipeline/settings.py` owns three things: the `PIPELINE_SETTINGS` table, the frozen `PipelineSettings`, and `PipelineSettingsService`, which reads and writes the config and notifies subscribers.
- `pipeline/__init__.py` stages take `(sequence, settings, ctx)`. They are registered through `STAGES`, whose bound handlers resolve `ctx` from `pipeline/context.py` and the effective settings from the service.
- `pipeline/scope.py` decides when the stages are registered.
- The main driver exposes the pipeline settings as `useConfig=False` descriptors over the service.

**Tech Stack:** Python 3.11 NVDA add-on; pytest with stubbed NVDA modules; ruff format (tabs).

**Spec:** `docs/superpowers/specs/2026-10-04-phase5h-6-settings-design.md`

## Global Constraints

- Never edit `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/` or `driver/sonic`.
- VE and Cerence stay separate copies; no shared code between engine packages.
- `addon/` stays `ruff format`-clean with tabs (`ruff format --check addon`). `tests/` is not formatted, but new test files use tabs.
- `git add` explicit paths only. Never stage the deletion of `docs/superpowers/finish_task.md` or `refactor.md`. Add spec and plan with `git add -f`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- New runtime/pipeline APIs use snake_case; NVDA-facing names (`_get_x`, `loadSettings`) stay mixedCase.
- Keep `with_order_log`, its commented `# @with_order_log(...)` lines, `order_move_to_end_register` and `synth.order`.
- Full suite command: `python3 -m pytest tests -q` (baseline 1395 passed).

## Review Focus

1. **Voice waitfactor after restart.** VoiceManager starts at waitfactor 0. The driver must re-apply `min(global // 10, 9)` on init and on every `loadSettings`, even when the value is unchanged, or per-voice stored waitfactors go stale. Test in Task 6.
2. **NVDA voice dialog Cancel.** Pipeline values changed live in the NVDA Voice panel must be restored on discard, because `loadSettings` no longer restores them. Test in Task 7.
3. **Profile switch.** `loadSettings(onlyChanged=True)` must read pipeline values from the new profile without writing any `pipeline` key. Test in Task 6.
4. **Synth half-built or terminated.** `speech_context()` must not raise when `_voiceManager` is None or `_numlan`/`speechSymbols` are not set yet. Stages may run while the synth is starting or after it terminated. Test in Task 6.
5. **Scope "all" with WorldVoice start/stop.** The stages must stay registered exactly once: no second `speech_dictionary.install()` and no unregister gap. Test in Task 5.

---

### Task 1: VE/Cerence stop failures latch, and Cerence engine name (D8, D9, VE/Cerence F401)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py` (`_stop_player` ~674, `cancel` ~686–716, imports lines 1–12)
- Modify: `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py` (`_stop_player` ~683, `cancel` ~695–725, `voices` ~993, imports lines 1–12)
- Test: `tests/test_vocalizer_segment_drain.py`, `tests/test_f4_engine_adapters.py`

**Interfaces:** Produces nothing new; behavior only.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_vocalizer_segment_drain.py`)

```python
def test_cancel_player_stop_failure_rejects_successor(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    error = OSError("stop failed")
    def stop():
        raise error
    env.core._real_player.stop = stop
    with pytest.raises(OSError):
        env.core.cancel()
    monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
    _, context, call = speak(env)
    finish(call)
    assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_FAILED]
    assert env.events[0].source_id is context.source_id


def test_stop_player_failure_rejects_successor(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    error = OSError("stop failed")
    def stop():
        raise error
    env.core._real_player.stop = stop
    with pytest.raises(OSError):
        env.core._stop_player()
    monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
    _, context, call = speak(env)
    finish(call)
    assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_FAILED]
```

Append to `tests/test_f4_engine_adapters.py`:

```python
@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_voice_metadata_names_the_declaring_engine(monkeypatch, engine):
	harness = load_real_driver_with_native_stubs(monkeypatch, engine)
	voice_class = harness.module.Voice
	monkeypatch.setattr(voice_class, "ready", classmethod(lambda cls: True))
	monkeypatch.setattr(voice_class, "engine", "Renamed")
	monkeypatch.setattr(harness.module, "languageHandler",
		types.SimpleNamespace(getLanguageDescription=lambda locale: "English"))
	core = types.SimpleNamespace(availableVoices={
		"x": types.SimpleNamespace(id="x", language="en", displayName="x"),
	})
	[metadata] = voice_class.voices(core)
	assert metadata["engine"] == "Renamed"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_vocalizer_segment_drain.py -k "stop_failure" tests/test_f4_engine_adapters.py -k "declaring_engine or stop_failure" -q`
Expected:
- the stop-failure tests FAIL: the successor gets `SEGMENT_DRAINED` or `SEGMENT_DONE`, not `SEGMENT_FAILED`;
- the Cerence metadata test FAILS with `'Cerence' != 'Renamed'`;
- the VE metadata test passes.

- [ ] **Step 3: Implement (VE, then the identical edit in Cerence)**

In both files, `_stop_player` becomes:

```python
	def _stop_player(self):
		with self._speechStateLock:
			self._stops += 1
			self._speechStateLock.notify_all()
		try:
			with self._player_operation():
				self._real_player.stop()
		except Exception as error:
			# A failed stop leaves the player state unknown: reject successors.
			self._segmentHost.latch_control_error(error)
			raise
		finally:
			with self._speechStateLock:
				self._stops -= 1
				self._speechStateLock.notify_all()
```

In both `cancel` methods, replace the trailing block

```python
		try:
			self._real_player.stop()
		finally:
```

with

```python
		try:
			self._real_player.stop()
		except Exception as error:
			host.latch_control_error(error)
			raise
		finally:
```

In Cerence `voices`, `"engine": "Cerence",` becomes `"engine": cls.engine,`.

Delete the unused imports in both files: `import locale`, `c_size_t` from the `ctypes` import list, and `LanguageInfo` from the `synthDriverHandler` import list. Confirm with `ruff check addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py --select F401`.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_f4_engine_adapters.py tests/test_engine_segment_contract.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
ruff format addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
git add addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py tests/test_vocalizer_segment_drain.py tests/test_f4_engine_adapters.py
git commit -m "fix(VE, Cerence): latch a control error when the player stop fails

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: GlobalPlugin terminate completes cleanup (D3)

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/__init__.py:42-71`
- Test: `tests/test_global_plugin_lifecycle.py` (create)

**Interfaces:** Produces `GlobalPlugin.submenu_item` set in `__init__`. Task 5 later replaces the pipeline calls in `__init__` and `terminate`.

- [ ] **Step 1: Write the failing test**

```python
"""GlobalPlugin terminate always runs its later cleanup steps."""

import ast
from pathlib import Path
import types

import pytest


PLUGIN_PATH = Path(__file__).resolve().parents[1] / "addon/globalPlugins/WorldVoice/__init__.py"


def load_plugin_class(environment):
	tree = ast.parse(PLUGIN_PATH.read_text(encoding="utf-8"))
	node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GlobalPlugin")
	exec(compile(ast.Module(body=[node], type_ignores=[]), str(PLUGIN_PATH), "exec"), environment)
	return environment["GlobalPlugin"]


def plugin_environment(calls, *, secure, menu_error=None):
	class Base:
		def __init__(self):
			pass

	class Menu:
		def Remove(self, item):
			if menu_error is not None:
				raise menu_error

	def record(name):
		return lambda *args, **kwargs: calls.append(name)

	tray = types.SimpleNamespace(menu=Menu(), Bind=lambda *args: None)
	return {
		"globalPluginHandler": types.SimpleNamespace(GlobalPlugin=Base),
		"script": lambda **kwargs: (lambda function: function),
		"_": lambda text: text,
		"ADDON_SUMMARY": "WorldVoice",
		"globalVars": types.SimpleNamespace(appArgs=types.SimpleNamespace(secure=secure)),
		"gui": types.SimpleNamespace(mainFrame=types.SimpleNamespace(sysTrayIcon=tray)),
		"wx": types.SimpleNamespace(CallAfter=lambda *args: None, ID_ANY=-1),
		"patch": record("patch"),
		"unpatch": record("unpatch"),
		"getSynth": lambda: types.SimpleNamespace(name="eSpeak"),
		"load_pipeline_settings": lambda: types.SimpleNamespace(scope="WorldVoice"),
		"apply_global_pipeline_scope": record("apply scope"),
		"clear_global_pipeline_scope": record("clear scope"),
		"on_worldvoice_start": object(),
		"on_worldvoice_end": object(),
		"WVStart": types.SimpleNamespace(register=record("start register"), unregister=record("start unregister")),
		"WVEnd": types.SimpleNamespace(register=record("end register"), unregister=record("end unregister")),
		"pipeline_scope": types.SimpleNamespace(
			attach_global=record("attach"),
			detach_global=record("detach"),
		),
	}


def test_secure_mode_terminate_runs_every_cleanup_step():
	calls = []
	plugin = load_plugin_class(plugin_environment(calls, secure=True))()
	assert plugin.submenu_item is None

	plugin.terminate()

	assert "unpatch" in calls
	assert calls[-1] in {"end unregister", "detach"}


def test_dead_menu_runtime_error_does_not_stop_cleanup():
	calls = []
	environment = plugin_environment(calls, secure=True, menu_error=RuntimeError("wrapped C/C++ object deleted"))
	plugin = load_plugin_class(environment)()
	plugin.submenu_item = types.SimpleNamespace(Destroy=lambda: calls.append("destroy"))

	plugin.terminate()

	assert "unpatch" in calls
	assert calls[-1] in {"end unregister", "detach"}
```

The `calls[-1]` assertion accepts both the pre-Task-5 last step (`WVEnd.unregister`) and the post-Task-5 one (`detach_global`), so the test survives Task 5 unchanged.

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_global_plugin_lifecycle.py -q`
Expected: FAIL. The first test gets `AttributeError: ... submenu_item`. The second gets `AttributeError: ... PyDeadObjectError` while evaluating the `except` clause.

- [ ] **Step 3: Implement**

In `GlobalPlugin.__init__`, add right after `super().__init__()`:

```python
		self.submenu_item = None
```

In `terminate`, replace `except wx.PyDeadObjectError:` with:

```python
		except RuntimeError:
			# wxPython raises RuntimeError for a menu whose C++ object is gone.
```

(keep the `pass` body).

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_global_plugin_lifecycle.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
ruff format addon/globalPlugins/WorldVoice/__init__.py
git add addon/globalPlugins/WorldVoice/__init__.py tests/test_global_plugin_lifecycle.py
git commit -m "fix(globalPlugin): finish terminate cleanup in secure mode and after a dead menu

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Remaining F401, and D14 type references

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py:1-27` (drop `importlib`, `SpeechCommand`)
- Modify: `addon/synthDrivers/WorldVoice/driver/__init__.py:6` (drop the `VOICE_PARAMETERS, boolean` import line)
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py:1-21` (drop `string`; D14)
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:2` (drop `importlib`)

**Interfaces:** none.

- [ ] **Step 1: Confirm the current findings**

Run: `ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select F401,F821 --output-format concise`
Expected: 9 lines (6 F401 + 3 F821) after Task 1.

- [ ] **Step 2: Edit**

- Remove the listed imports. If `driver/__init__.py` still imports `VOICE_PARAMETERS` or `boolean`, delete the whole `from ..runtime.settings import ...` line.
- In `pipeline/__init__.py`:
  - change `from typing import Iterable, Iterator, Union` to `from typing import TYPE_CHECKING, Iterable, Iterator, Union`;
  - after the relative imports add:

```python
if TYPE_CHECKING:
	from speech.commands import SpeechCommand

	from ..driver import Voice
	from ..voiceManager import VoiceManager
```

  - change `SpeechCmd = Union[str, "BaseSpeechCommand"]` to `SpeechCmd = Union[str, "SpeechCommand"]`.

- [ ] **Step 3: Verify**

Run: the Step 1 ruff command → `All checks passed!`.
Then run `python3 -m pytest tests -q` → all pass.

- [ ] **Step 4: Commit**

```bash
ruff format addon/synthDrivers/WorldVoice/__init__.py addon/synthDrivers/WorldVoice/driver/__init__.py addon/synthDrivers/WorldVoice/pipeline/__init__.py addon/globalPlugins/WorldVoice/speechSettingsDialog.py
git add addon/synthDrivers/WorldVoice/__init__.py addon/synthDrivers/WorldVoice/driver/__init__.py addon/synthDrivers/WorldVoice/pipeline/__init__.py addon/globalPlugins/WorldVoice/speechSettingsDialog.py
git commit -m "chore: drop unused imports and name real types in pipeline annotations

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Pipeline settings table, repository and service (additive)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (add the new API next to the old one; old functions stay until Task 8)
- Test: `tests/test_pipeline_settings_service.py` (create)

**Interfaces:**
- Produces, in `pipeline/settings.py`:
  - `PipelineSettingSpec(key, kind, default, driver_id=None, label=None, display_name=None, ring=True, min_step=1, normalize=None)`, with `.convert(value)` and `.confspec`;
  - `PIPELINE_SETTINGS: tuple[PipelineSettingSpec, ...]`;
  - `PIPELINE_SETTING_BY_KEY: dict[str, PipelineSettingSpec]`;
  - `DEFAULT_PIPELINE_SETTINGS: dict`, `PIPELINE_CONFIG_KEYS: tuple[str, ...]`, `PIPELINE_CONFSPEC: dict[str, str]`;
  - frozen `PipelineSettings` with `.effective(supports_roles: bool) -> PipelineSettings`;
  - `ConfigPipelineRepository(conf_provider=lambda: config.conf)`, with `.load()` and `.save(changes)`;
  - `PipelineSettingsService(repository)`, with `.get()`, `.effective(supports_roles)`, `.update(**changes) -> PipelineSettings`, `.subscribe(listener)` and `.unsubscribe(listener)`;
  - the singleton `pipeline_settings`.

- [ ] **Step 1: Write the failing tests**

```python
"""The pipeline settings table, repository and service."""

from dataclasses import fields
import importlib.util
import sys
from types import ModuleType, SimpleNamespace

import pytest


def load_settings_module(monkeypatch, conf, errors=None):
	config = ModuleType("config")
	config.conf = conf
	monkeypatch.setitem(sys.modules, "config", config)
	addon_handler = ModuleType("addonHandler")
	addon_handler.initTranslation = lambda: None
	monkeypatch.setitem(sys.modules, "addonHandler", addon_handler)
	log_handler = ModuleType("logHandler")
	log_handler.log = SimpleNamespace(error=lambda *args, **kwargs: (errors if errors is not None else []).append(args))
	monkeypatch.setitem(sys.modules, "logHandler", log_handler)
	synth_driver_handler = ModuleType("synthDriverHandler")
	synth_driver_handler.getSynth = lambda: None
	monkeypatch.setitem(sys.modules, "synthDriverHandler", synth_driver_handler)
	import builtins
	monkeypatch.setattr(builtins, "_", lambda text: text, raising=False)
	spec = importlib.util.spec_from_file_location(
		"pipeline_settings_under_test",
		"addon/synthDrivers/WorldVoice/pipeline/settings.py",
	)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module


OLD_DEFAULTS = {
	"scope": "WorldVoice",
	"ignore_comma_between_number": False,
	"number_mode": "value",
	"global_wait_factor": 10,
	"number_wait_factor": 10,
	"item_wait_factor": 10,
	"sayall_wait_factor": 10,
	"chinesespace_wait_factor": 10,
	"punctuation_wait_factor": 0,
	"punctuation_pause_enabled": True,
	"remove_punctuation_characters": False,
	"punctuation_pause_characters": "،؛,.;:!؟?…",
	"pair_wait_factor": 0,
}


def test_table_drives_fields_defaults_keys_and_confspec(monkeypatch):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	keys = [spec.key for spec in module.PIPELINE_SETTINGS]
	assert sorted(keys) == sorted(field.name for field in fields(module.PipelineSettings))
	assert module.DEFAULT_PIPELINE_SETTINGS == OLD_DEFAULTS
	assert module.PIPELINE_CONFIG_KEYS == tuple(keys)
	assert module.PIPELINE_CONFSPEC["global_wait_factor"] == "integer(default=10,min=0,max=100)"
	assert module.PIPELINE_CONFSPEC["punctuation_pause_enabled"] == "boolean(default=true)"
	assert module.PIPELINE_CONFSPEC["scope"] == 'string(default="WorldVoice")'
	assert module.PIPELINE_CONFSPEC["punctuation_pause_characters"] == 'string(default="،؛,.;:!؟?…")'
	driver_ids = [spec.driver_id for spec in module.PIPELINE_SETTINGS if spec.driver_id]
	assert driver_ids == [
		"cni", "nummod", "globalwaitfactor", "numberwaitfactor", "pairwaitfactor", "itemwaitfactor",
		"sayallwaitfactor", "chinesespacewaitfactor", "punctuationpauseenabled",
		"removepunctuationcharacters", "punctuationwaitfactor",
	]
	assert [spec.ring for spec in module.PIPELINE_SETTINGS if spec.driver_id].count(False) == 1
	assert module.PIPELINE_SETTING_BY_KEY["ignore_comma_between_number"].ring is False


def test_get_reads_defaults_and_current_profile(monkeypatch):
	profiles = {"normal": {"WorldVoice": {"pipeline": {}}}, "app": {"WorldVoice": {"pipeline": {"item_wait_factor": 40}}}}
	active = ["normal"]
	module = load_settings_module(monkeypatch, profiles["normal"])
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: profiles[active[0]]))
	assert service.get() == module.PipelineSettings(**OLD_DEFAULTS)
	active[0] = "app"
	assert service.get().item_wait_factor == 40


def test_update_converts_normalizes_and_writes_only_changes(monkeypatch):
	class Section(dict):
		writes = []
		def __setitem__(self, key, value):
			Section.writes.append((key, value))
			super().__setitem__(key, value)
	conf = {"WorldVoice": {"pipeline": Section()}}
	module = load_settings_module(monkeypatch, conf)
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))

	result = service.update(global_wait_factor="57", item_wait_factor=10, punctuation_pause_characters="  .,  ")

	assert Section.writes == [("global_wait_factor", 50), ("punctuation_pause_characters", ".,")]
	assert result.global_wait_factor == 50
	assert result.punctuation_pause_characters == ".,"


def test_update_rejects_unknown_keys_before_writing(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	module = load_settings_module(monkeypatch, conf)
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))
	with pytest.raises(KeyError):
		service.update(item_wait_factor=30, no_such_setting=1)
	assert conf["WorldVoice"]["pipeline"] == {}


def test_update_notifies_subscribers_and_survives_a_failing_one(monkeypatch):
	errors = []
	conf = {"WorldVoice": {"pipeline": {}}}
	module = load_settings_module(monkeypatch, conf, errors)
	service = module.PipelineSettingsService(module.ConfigPipelineRepository(lambda: conf))
	seen = []
	def failing(settings):
		raise RuntimeError("listener failed")
	service.subscribe(failing)
	service.subscribe(seen.append)
	service.subscribe(seen.append)

	service.update(scope="all")
	service.update(scope="all")
	service.unsubscribe(seen.append)
	service.update(scope="WorldVoice")

	assert [settings.scope for settings in seen] == ["all"]
	assert len(errors) == 2


def test_effective_matches_the_old_synth_scoping(monkeypatch):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	settings = module.PipelineSettings(**{
		**OLD_DEFAULTS, "ignore_comma_between_number": True, "remove_punctuation_characters": True,
		"punctuation_wait_factor": 30, "pair_wait_factor": 20, "global_wait_factor": 0,
	})
	assert settings.effective(True) is settings
	scoped = settings.effective(False)
	assert (scoped.ignore_comma_between_number, scoped.number_wait_factor, scoped.item_wait_factor,
		scoped.sayall_wait_factor, scoped.chinesespace_wait_factor, scoped.punctuation_wait_factor,
		scoped.punctuation_pause_enabled, scoped.remove_punctuation_characters, scoped.pair_wait_factor) == (
		False, 0, 0, 0, 0, 0, False, False, 0)
	global_scope = module.PipelineSettings(**{**OLD_DEFAULTS, "scope": "all", "ignore_comma_between_number": True,
		"global_wait_factor": 0, "remove_punctuation_characters": True}).effective(False)
	assert global_scope.ignore_comma_between_number is False
	assert global_scope.remove_punctuation_characters is True
	assert module.PipelineSettings(**{**OLD_DEFAULTS, "scope": "all", "ignore_comma_between_number": True,
		"global_wait_factor": 10}).effective(False).ignore_comma_between_number is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_pipeline_settings_service.py -q`
Expected: FAIL with `AttributeError: module ... has no attribute 'PIPELINE_SETTINGS'`.

- [ ] **Step 3: Implement**

Replace the top of `pipeline/settings.py`, from the imports through the end of `class PipelineSettings` and `_get_value`, with the following. Keep every function below `_get_value` unchanged for now; `load_pipeline_settings` and `save_pipeline_settings` keep working because they use `_get_value`, `PIPELINE_CONFIG_KEYS` and the dataclass. Change `load_pipeline_settings` to `return ConfigPipelineRepository(lambda: conf).load()`. In `get_effective_pipeline_settings`, the non-WorldVoice branch mutates `settings`; replace that branch with `return settings.effective(False)`. Its WorldVoice branch already builds a new instance, so frozen is safe.

```python
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

import addonHandler
import config
from logHandler import log
from synthDriverHandler import getSynth

addonHandler.initTranslation()


# Maximum pause (in milliseconds) injected after a punctuation mark.
# The pause is intentionally capped so the voice never falls fully silent
# at punctuation, no matter how high the configured factor is.
MAX_PUNCTUATION_WAIT_MS = 500

# Milliseconds of pause per unit of punctuation_wait_factor (0..100),
# so the full slider range maps to 0..500ms on its own, independent of the
# global wait factor. This keeps the punctuation pause audible even when the
# global wait factor is 0.
PUNCTUATION_WAIT_UNIT_MS = 5

# Pair pauses use the same unit scaling as punctuation pauses so that both
# pause families behave consistently and remain audible regardless of the
# global wait factor.
PAIR_WAIT_UNIT_MS = 5


def _floor_to_ten(value: Any) -> int:
	return int(value) // 10 * 10


def _strip(value: Any) -> str:
	return str(value).strip()


@dataclass(frozen=True)
class PipelineSettingSpec:
	"""One pipeline setting: its config key, type, default and synth-setting metadata."""

	key: str
	kind: type
	default: Any
	driver_id: str | None = None
	label: str | None = None
	display_name: str | None = None
	ring: bool = True
	min_step: int = 1
	normalize: Callable[[Any], Any] | None = None

	def convert(self, value: Any) -> Any:
		if self.normalize is not None:
			return self.normalize(value)
		return self.kind(value)

	@property
	def confspec(self) -> str:
		if self.kind is bool:
			return f"boolean(default={str(self.default).lower()})"
		if self.kind is int:
			return f"integer(default={self.default},min=0,max=100)"
		return f'string(default="{self.default}")'


# Synth settings appear in the voice settings dialog in this order.
PIPELINE_SETTINGS: tuple[PipelineSettingSpec, ...] = (
	PipelineSettingSpec(
		"ignore_comma_between_number",
		bool,
		False,
		driver_id="cni",
		label=_("Ignore comma between number"),
		ring=False,
	),
	PipelineSettingSpec(
		"number_mode",
		str,
		"value",
		driver_id="nummod",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Number &Mode"),
		# Translators: Label for a setting in synth settings ring.
		display_name=_("Number Mode"),
	),
	PipelineSettingSpec(
		"global_wait_factor",
		int,
		10,
		driver_id="globalwaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Global wait factor"),
		min_step=10,
		normalize=_floor_to_ten,
	),
	PipelineSettingSpec(
		"number_wait_factor",
		int,
		10,
		driver_id="numberwaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Number wait factor"),
	),
	PipelineSettingSpec(
		"pair_wait_factor",
		int,
		0,
		driver_id="pairwaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Pair wait factor"),
	),
	PipelineSettingSpec(
		"item_wait_factor",
		int,
		10,
		driver_id="itemwaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("item wait factor"),
	),
	PipelineSettingSpec(
		"sayall_wait_factor",
		int,
		10,
		driver_id="sayallwaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Say all wait factor"),
	),
	PipelineSettingSpec(
		"chinesespace_wait_factor",
		int,
		10,
		driver_id="chinesespacewaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Chinese space wait factor"),
	),
	PipelineSettingSpec(
		"punctuation_pause_enabled",
		bool,
		True,
		driver_id="punctuationpauseenabled",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Enable punctuation pause control"),
		# Translators: Label for a setting in synth settings ring.
		display_name=_("Punctuation pauses"),
	),
	PipelineSettingSpec(
		"remove_punctuation_characters",
		bool,
		False,
		driver_id="removepunctuationcharacters",
		label=_("Remove configured punctuation at pause points"),
		display_name=_("Remove punctuation at pause points"),
	),
	PipelineSettingSpec(
		"punctuation_wait_factor",
		int,
		0,
		driver_id="punctuationwaitfactor",
		# Translators: Label for a setting in voice settings dialog.
		label=_("Punctuation wait factor"),
	),
	PipelineSettingSpec("scope", str, "WorldVoice"),
	PipelineSettingSpec("punctuation_pause_characters", str, "،؛,.;:!؟?…", normalize=_strip),
)

PIPELINE_SETTING_BY_KEY = {spec.key: spec for spec in PIPELINE_SETTINGS}
DEFAULT_PIPELINE_SETTINGS = {spec.key: spec.default for spec in PIPELINE_SETTINGS}
PIPELINE_CONFIG_KEYS = tuple(spec.key for spec in PIPELINE_SETTINGS)
PIPELINE_CONFSPEC = {spec.key: spec.confspec for spec in PIPELINE_SETTINGS}


@dataclass(frozen=True)
class PipelineSettings:
	scope: str
	ignore_comma_between_number: bool
	number_mode: str
	global_wait_factor: int
	number_wait_factor: int
	item_wait_factor: int
	sayall_wait_factor: int
	chinesespace_wait_factor: int
	punctuation_wait_factor: int
	punctuation_pause_enabled: bool
	remove_punctuation_characters: bool
	punctuation_pause_characters: str
	pair_wait_factor: int

	# keep global_factor_units and the six scaled_* methods exactly as they are today

	def effective(self, supports_roles: bool) -> "PipelineSettings":
		"""The settings a synthesizer actually speaks with.

		WorldVoice uses them as stored. Other synthesizers get the pipeline
		only with scope "all"; otherwise every pause and removal is off.
		"""
		if supports_roles:
			return self
		if self.scope != "all":
			return replace(
				self,
				ignore_comma_between_number=False,
				number_wait_factor=0,
				item_wait_factor=0,
				sayall_wait_factor=0,
				chinesespace_wait_factor=0,
				punctuation_wait_factor=0,
				punctuation_pause_enabled=False,
				remove_punctuation_characters=False,
				pair_wait_factor=0,
			)
		return replace(
			self,
			ignore_comma_between_number=bool(self.global_factor_units * self.ignore_comma_between_number),
		)


def _get_value(section: Any, key: str) -> Any:
	# keep the existing body


class ConfigPipelineRepository:
	"""Read and write the pipeline section of the active NVDA configuration profile."""

	def __init__(self, conf_provider: Callable[[], Any] = lambda: config.conf):
		self._conf_provider = conf_provider

	def _section(self) -> Any:
		return self._conf_provider()["WorldVoice"]["pipeline"]

	def load(self) -> PipelineSettings:
		section = self._section()
		return PipelineSettings(
			**{spec.key: spec.convert(_get_value(section, spec.key)) for spec in PIPELINE_SETTINGS},
		)

	def save(self, changes: Mapping[str, Any]) -> None:
		section = self._section()
		for key, value in changes.items():
			section[key] = value


class PipelineSettingsService:
	"""The only reader and writer of pipeline settings; notifies subscribers on change."""

	def __init__(self, repository: ConfigPipelineRepository):
		self._repository = repository
		self._listeners: list[Callable[[PipelineSettings], None]] = []

	def get(self) -> PipelineSettings:
		return self._repository.load()

	def effective(self, supports_roles: bool) -> PipelineSettings:
		return self.get().effective(supports_roles)

	def update(self, **changes: Any) -> PipelineSettings:
		converted = {}
		for key, value in changes.items():
			try:
				spec = PIPELINE_SETTING_BY_KEY[key]
			except KeyError:
				raise KeyError(f"Unknown pipeline setting: {key}") from None
			converted[key] = spec.convert(value)
		current = self.get()
		changed = {key: value for key, value in converted.items() if getattr(current, key) != value}
		if not changed:
			return current
		self._repository.save(changed)
		settings = self.get()
		for listener in tuple(self._listeners):
			try:
				listener(settings)
			except Exception:
				log.error("WorldVoice: pipeline settings listener failed", exc_info=True)
		return settings

	def subscribe(self, listener: Callable[[PipelineSettings], None]) -> None:
		if listener not in self._listeners:
			self._listeners.append(listener)

	def unsubscribe(self, listener: Callable[[PipelineSettings], None]) -> None:
		try:
			self._listeners.remove(listener)
		except ValueError:
			pass


pipeline_settings = PipelineSettingsService(ConfigPipelineRepository())
```

Delete the old `DEFAULT_PIPELINE_SETTINGS` and `PIPELINE_CONFIG_KEYS` literals and the old non-frozen dataclass; the table replaces them. Keep `_last_scope_application` and the scope functions until Task 5.

Update the two existing tests in `tests/test_punctuation_removal_settings.py` that load this module. Their loader must also stub `addonHandler`, `logHandler` and builtins `_`, exactly as `load_settings_module` above does. In `test_removal_defaults_off_and_round_trips_independently_of_pause`, replace the mutation `settings.remove_punctuation_characters = True` with `settings = dataclasses.replace(settings, remove_punctuation_characters=True)` and `import dataclasses`. The file is deleted in Task 8.

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_pipeline_settings_service.py tests/test_punctuation_removal_settings.py tests/test_pipeline_punctuation_pause.py -q`
Expected: all PASS.
Then run `python3 -m pytest tests -q` → all pass.

- [ ] **Step 5: Commit**

```bash
ruff format addon/synthDrivers/WorldVoice/pipeline/settings.py
git add addon/synthDrivers/WorldVoice/pipeline/settings.py tests/test_pipeline_settings_service.py tests/test_punctuation_removal_settings.py
git commit -m "refactor(pipeline): drive pipeline settings from one table behind a service

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: SpeechContext, stages with explicit settings, STAGES registry, PipelineScope

**Files:**
- Create: `addon/synthDrivers/WorldVoice/pipeline/context.py`
- Create: `addon/synthDrivers/WorldVoice/pipeline/scope.py`
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (all stages, registration)
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (delete the scope functions and `_last_scope_application`)
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`. Changes:
  - imports;
  - `_initialize`: pipeline register;
  - `terminate`: pipeline cleanup;
  - `speak`;
  - `_set_cni` and `_set_itemwaitfactor` register/unregister lines;
  - new `speech_context()`.
- Modify: `addon/globalPlugins/WorldVoice/__init__.py` (scope calls)
- Modify: `addon/synthDrivers/WorldVoice/sayAll.py`
- Test: `tests/test_pipeline_stages.py` and `tests/test_pipeline_scope.py` (create); update `tests/test_pipeline_punctuation_pause.py`, `tests/test_worldvoice_lifecycle.py`, `tests/test_runtime_composition.py`

**Interfaces:**
- Consumes: `pipeline_settings.effective(supports_roles)` and `PipelineSettings` (Task 4).
- Produces:
  - `pipeline/context.py`: `SpeechContext(supports_roles, language, number_language, speech_symbols=None, default_voice=None, voice_for_language=lambda language: None)`, `GENERIC_CONTEXT`, `current_context() -> SpeechContext`.
  - `pipeline/__init__.py`: `Stage(log_key, fn)` with `.handler`; `STAGES`; `register_stages()`; `unregister_stages()`; `order_move_to_start_register()`; `order_move_to_end_register()`; `deduplicate_language_command(seq, ctx)`. Every stage is `fn(seq, settings, ctx)`.
  - `pipeline/scope.py`: `PipelineScope(settings, register, unregister)` with `worldvoice_started()`, `worldvoice_ended()`, `attach_global()`, `detach_global()`, `.registered`; the singleton `pipeline_scope`.
  - Main driver: `SynthDriver.speech_context() -> SpeechContext`.

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline_scope.py`:

```python
"""PipelineScope registers the stages exactly while an owner wants them."""

import importlib.util
import sys
from types import ModuleType, SimpleNamespace


def load_scope_module(monkeypatch):
	package = ModuleType("scope_pkg")
	package.__path__ = []
	package.register_stages = lambda: None
	package.unregister_stages = lambda: None
	monkeypatch.setitem(sys.modules, "scope_pkg", package)
	settings = ModuleType("scope_pkg.settings")
	settings.pipeline_settings = SimpleNamespace(subscribe=lambda listener: None)
	monkeypatch.setitem(sys.modules, "scope_pkg.settings", settings)
	spec = importlib.util.spec_from_file_location("scope_pkg.scope", "addon/synthDrivers/WorldVoice/pipeline/scope.py")
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module


class FakeSettings:
	def __init__(self, scope):
		self.scope = scope
		self.listeners = []

	def get(self):
		return SimpleNamespace(scope=self.scope)

	def subscribe(self, listener):
		self.listeners.append(listener)

	def change(self, scope):
		self.scope = scope
		for listener in self.listeners:
			listener(SimpleNamespace(scope=scope))


def make_scope(monkeypatch, scope):
	module = load_scope_module(monkeypatch)
	calls = []
	settings = FakeSettings(scope)
	pipeline = module.PipelineScope(settings, lambda: calls.append("register"), lambda: calls.append("unregister"))
	return pipeline, settings, calls


def test_global_scope_all_registers_once_across_worldvoice_start_and_end(monkeypatch):
	pipeline, settings, calls = make_scope(monkeypatch, "all")
	pipeline.attach_global()
	pipeline.worldvoice_started()
	pipeline.worldvoice_ended()
	assert calls == ["register"]
	assert pipeline.registered
	pipeline.detach_global()
	assert calls == ["register", "unregister"]


def test_worldvoice_scope_registers_only_while_worldvoice_runs(monkeypatch):
	pipeline, settings, calls = make_scope(monkeypatch, "WorldVoice")
	pipeline.attach_global()
	assert calls == []
	pipeline.worldvoice_started()
	pipeline.worldvoice_ended()
	assert calls == ["register", "unregister"]


def test_scope_changes_apply_through_the_subscription(monkeypatch):
	pipeline, settings, calls = make_scope(monkeypatch, "WorldVoice")
	pipeline.attach_global()
	settings.change("all")
	settings.change("WorldVoice")
	assert calls == ["register", "unregister"]
	pipeline.worldvoice_started()
	settings.change("all")
	settings.change("WorldVoice")
	assert calls == ["register", "unregister", "register"]


def test_plugin_detach_keeps_running_worldvoice_registered(monkeypatch):
	pipeline, settings, calls = make_scope(monkeypatch, "all")
	pipeline.attach_global()
	pipeline.worldvoice_started()
	pipeline.detach_global()
	assert calls == ["register"]
	pipeline.worldvoice_ended()
	assert calls == ["register", "unregister"]
```

`tests/test_pipeline_stages.py`. It reuses the punctuation test loader, extended in Step 3.

```python
"""STAGES is the single order and log-key source, and stages read settings from their arguments."""

import ast
from pathlib import Path
import sys
from types import SimpleNamespace

from test_pipeline_punctuation_pause import load_pipeline_module, punctuation_settings


PIPELINE = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/pipeline/__init__.py"
SYNTH = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/__init__.py"

ORDER = [
	"apply_speech_dictionaries", "ignore_comma_between_number", "number_language", "number_mode",
	"chinesespace_wait_factor", "item_wait_factor", "punctuation_wait_factor", "number_wait_factor",
	"speech_viewer",
]


class OrderedFilter:
	def __init__(self):
		self.handlers = []

	def register(self, handler):
		if handler not in self.handlers:
			self.handlers.append(handler)

	def unregister(self, handler):
		if handler in self.handlers:
			self.handlers.remove(handler)

	def moveToEnd(self, handler, last=False):
		if handler not in self.handlers:
			return False
		self.handlers.remove(handler)
		if last:
			self.handlers.append(handler)
		else:
			self.handlers.insert(0, handler)
		return True


def test_stages_order_and_log_keys(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	assert [stage.log_key for stage in module.STAGES] == ORDER


def test_register_puts_stages_first_in_order_and_unregister_removes_them(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	fake = OrderedFilter()
	other = lambda sequence: sequence
	fake.register(other)
	monkeypatch.setattr(module, "filter_speechSequence", fake)
	installs = []
	monkeypatch.setattr(module.speech_dictionary, "install", lambda: installs.append("install"))
	monkeypatch.setattr(module.speech_dictionary, "uninstall", lambda: installs.append("uninstall"))

	module.register_stages()
	assert fake.handlers == [stage.handler for stage in module.STAGES] + [other]
	module.order_move_to_end_register()
	assert fake.handlers == [other] + [stage.handler for stage in module.STAGES]
	module.unregister_stages()
	assert fake.handlers == [other]
	assert installs == ["install", "uninstall"]


def test_handler_passes_effective_settings_and_context(monkeypatch):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	seen = []
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: seen.append((s, ctx)) or list(sequence))
	assert stage.handler(["a"]) == ["a"]
	assert seen == [(settings, module.GENERIC_CONTEXT)]


def test_handler_logs_before_and_after_when_enabled(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	sys.modules["config"].conf["WorldVoice"]["log"] = {"enable": True, "speech_viewer": True}
	writes = []
	monkeypatch.setattr(module, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: [item.upper() for item in sequence])
	assert stage.handler(["a"]) == ["A"]
	assert writes == [("speech_viewer", "before"), ("speech_viewer", "after")]


def test_zero_number_wait_keeps_spaces(monkeypatch):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	assert list(module.number_wait_factor([" 1 ", "  ", "2"], settings, module.GENERIC_CONTEXT)) == [" 1 ", "  ", "2"]


def test_positive_number_wait_breaks_between_numbers(monkeypatch):
	settings = punctuation_settings(0)
	settings.scaled_number_wait = lambda: 40
	module, BreakCommand = load_pipeline_module(monkeypatch, settings)
	result = list(module.number_wait_factor([" 1 ", "  ", "2"], settings, module.GENERIC_CONTEXT))
	assert result[0] == "1" and result[2] == "2" and result[1].time == 40


def test_number_mode_reads_symbols_from_context(monkeypatch):
	settings = punctuation_settings(0)
	settings.number_mode = "number"
	module, _ = load_pipeline_module(monkeypatch, settings)
	symbols = SimpleNamespace(symbols={"1": SimpleNamespace(language="zh", replacement="一")})
	ctx = module.SpeechContext(supports_roles=True, language="zh", number_language="zh", speech_symbols=symbols)
	assert list(module.inject_number_mode(["11"], settings, ctx)) == ["一 一"]
	assert list(module.inject_number_mode(["11"], settings, module.GENERIC_CONTEXT)) == ["1 1"]


def test_number_language_wraps_numbers_for_worldvoice_only(monkeypatch):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	english, german = object(), object()
	ctx = module.SpeechContext(
		supports_roles=True, language="en", number_language="de", default_voice=english,
		voice_for_language=lambda language: {"en": english, "de": german}.get(language),
	)
	result = list(module.inject_number_language(["a 1 b"], settings, ctx))
	assert [getattr(item, "lang", item) for item in result] == ["a ", "de", "1", "en", " b"]
	command = module.WVLangChangeCommand("de")
	assert list(module.inject_number_language([command, "x"], settings, module.GENERIC_CONTEXT)) == ["x"]


def test_only_the_order_log_debug_tool_asks_for_the_synth():
	tree = ast.parse(PIPELINE.read_text(encoding="utf-8"))
	users = {
		node.name for node in tree.body
		if isinstance(node, ast.FunctionDef)
		and any(isinstance(inner, ast.Name) and inner.id == "getSynth" for inner in ast.walk(node))
	}
	assert users == {"with_order_log"}
```

Note on `test_number_language_wraps_numbers_for_worldvoice_only`: `deduplicate_language_command` drops a switch that maps to the voice already speaking. The expected list therefore keeps both switches: `de` maps to `german` and `en` maps back to `english`.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_pipeline_scope.py tests/test_pipeline_stages.py -q`
Expected: FAIL (`scope.py` is missing; there is no `STAGES` attribute).

- [ ] **Step 3: Implement**

**3a. `pipeline/context.py`:**

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from synthDriverHandler import getSynth


@dataclass(frozen=True)
class SpeechContext:
	"""What a pipeline stage may know about the synthesizer that speaks."""

	supports_roles: bool
	language: str | None
	number_language: str
	speech_symbols: Any = None
	default_voice: Any = None
	voice_for_language: Callable[[str], Any] = lambda language: None


GENERIC_CONTEXT = SpeechContext(supports_roles=False, language=None, number_language="Windows")


def current_context() -> SpeechContext:
	try:
		synth = getSynth()
	except Exception:
		return GENERIC_CONTEXT
	if getattr(synth, "name", None) != "WorldVoice":
		return GENERIC_CONTEXT
	return synth.speech_context()
```

**3b. `pipeline/__init__.py`.** Make each change below.

- Imports (keep `from synthDriverHandler import getSynth` for `with_order_log`). Add:
  - `from dataclasses import dataclass, field`;
  - `from typing import TYPE_CHECKING, Callable, Iterable, Iterator, Union`;
  - `from .context import GENERIC_CONTEXT, SpeechContext, current_context`;
  - `from .settings import pipeline_settings` (replaces the `get_effective_pipeline_settings` import).

  `GENERIC_CONTEXT` and `SpeechContext` are re-exported for the tests and the main driver. Under `TYPE_CHECKING` also import `from .settings import PipelineSettings`.
- `with_order_log`: change only its wrapper to `def wrapper(speechSequence, *args, **kwargs):` and `return func(speechSequence, *args, **kwargs)`. It keeps reading `getSynth().order` (phase 8 user decision), so keep `from synthDriverHandler import getSynth`; it is the only allowed `getSynth` user in this module.
- Delete `with_speech_sequence_log` and the 10 `get_*` accessors (`get_ignore_comma_between_number`, `get_number_mode`, `get_item_wait_factor`, `get_number_wait_factor`, `get_chinesespace_wait_factor`, `get_punctuation_wait_factor`, `get_punctuation_pause_chars`, `get_punctuation_pause_enabled`, `get_pair_wait_factor`). Rewrite `get_translate_table` as:

```python
def get_translate_table(ctx: SpeechContext) -> dict[int, str]:
	# Build translation table for single digits
	translate_table: dict[int, str] = {}
	if ctx.speech_symbols:
		for d in "0123456789":
			if d in ctx.speech_symbols.symbols:
				sym = ctx.speech_symbols.symbols[d]
				if sym.language in (ctx.number_language, "Windows"):
					translate_table[ord(d)] = sym.replacement or d
	return translate_table
```

- Remove every `@with_speech_sequence_log(...)` decorator line; keep the `# @with_order_log(...)` comment lines. Change each stage signature and its settings reads:
  - `speech_viewer(speechSequence, settings, ctx)`.
  - `ignore_comma_between_number(speechSequence, settings, ctx)`: `if settings.ignore_comma_between_number:`.
  - `apply_speech_dictionaries(speechSequence, settings, ctx)`.
  - `item_wait_factor(speechSequence, settings, ctx)`: `wait_factor = settings.scaled_item_wait()`.
  - `_insert_BreakCommand_between_number(speechSequence, wait_factor)`: delete its `get_number_wait_factor()` call and its `<= 0` early return. Fix the docstring's stale `synth._itemwaitfactor × 5` sentence to read: "The inserted pause length is the scaled number wait factor."
  - `number_wait_factor` (D12):

```python
def number_wait_factor(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	wait_factor = settings.scaled_number_wait()
	if wait_factor <= 0:
		yield from speechSequence
		return
	yield from _insert_BreakCommand_between_number(_remove_space(speechSequence), wait_factor)
```

  - `_insert_WVLangChangeCommand_between_number(speechSequence, ctx)`:
    - `number_language = ctx.number_language`;
    - `current_lang = ctx.language`;
    - `default_lang = ctx.language`;
    - the inner call becomes `deduplicate_language_command(iter_number_speech_segments_language(item, current_lang, number_language), ctx)`.
  - `inject_number_language(speechSequence, settings, ctx)`:

```python
	if ctx.supports_roles:
		if ctx.number_language == "default":
			# (keep the existing comment)
			yield from speechSequence
			return
		yield from _insert_WVLangChangeCommand_between_number(speechSequence, ctx)
		return
	yield from remove_language_command(speechSequence)
```

  - `_translate_number(raw, mode, table, pair_pause=0)`: replace `pause = get_pair_wait_factor()` with `pause = pair_pause`.
  - `iter_number_speech_segments_mode(item, mode, translate_table, pair_pause=0, number_re=_NUMBER_RE)`: pass `pair_pause` to `_translate_number`.
  - `inject_number_mode(speechSequence, settings, ctx)`:

```python
	mode = settings.number_mode
	translate_table = get_translate_table(ctx)
	pair_pause = settings.scaled_pair_wait()
	for item in speechSequence:
		if not isinstance(item, str):
			yield item
			continue
		segments = iter_number_speech_segments_mode(item, mode, translate_table, pair_pause)
		if ctx.supports_roles:
			segments = deduplicate_language_command(segments, ctx)
		yield from merge_consecutive_strings(segments)
```

  - `inject_chinese_space_pause(speechSequence, settings, ctx)`: `waitfactor = settings.scaled_chinesespace_wait()`.
  - `inject_punctuation_pause(speechSequence, settings, ctx)`: delete the line `settings = get_effective_pipeline_settings()`.
  - `deduplicate_language_command(speechSequence, ctx)`:
    - `voice_instance = default_instance = ctx.default_voice`;
    - `current_language = default_language = ctx.language`;
    - `new_instance = ctx.voice_for_language(command.lang)`.
- Replace `order_move_to_start_register`, `order_move_to_end_register`, `static_register`, `dynamic_register` and `unregister` (end of file) with:

```python
def _run_logged(label, fn, speechSequence, settings, ctx):
	debug = config.conf["general"]["loggingLevel"] == "DEBUG"
	recording = config.conf["WorldVoice"]["log"]["enable"]
	if not ((debug or recording) and config.conf["WorldVoice"]["log"][label]):
		return fn(speechSequence, settings, ctx)
	_id = uuid.uuid4().hex
	speechSequence = list(speechSequence)
	if debug:
		log.debug(f"speech sequence before {label} pipeline: {speechSequence}")
	if recording:
		pl.write(_id, label, "before", speechSequence)
	speechSequence = list(fn(speechSequence, settings, ctx))
	if debug:
		log.debug(f"speech sequence after {label} pipeline: {speechSequence}")
	if recording:
		pl.write(_id, label, "after", speechSequence)
	return speechSequence


def _stage_handler(log_key, fn):
	@wraps(fn)
	def handler(speechSequence):
		ctx = current_context()
		return _run_logged(log_key, fn, speechSequence, pipeline_settings.effective(ctx.supports_roles), ctx)

	return handler


@dataclass(frozen=True)
class Stage:
	"""One speech-sequence filter. Its handler is bound once, so NVDA's weak registry keeps it."""

	log_key: str
	fn: Callable[..., Iterable[SpeechCmd]]
	handler: Callable[[Iterable[SpeechCmd]], Iterable[SpeechCmd]] = field(init=False, repr=False, compare=False)

	def __post_init__(self):
		object.__setattr__(self, "handler", _stage_handler(self.log_key, self.fn))


# The order NVDA runs the filters in; register, reorder and the log switches derive from it.
STAGES: tuple[Stage, ...] = (
	Stage("apply_speech_dictionaries", apply_speech_dictionaries),
	Stage("ignore_comma_between_number", ignore_comma_between_number),
	Stage("number_language", inject_number_language),
	Stage("number_mode", inject_number_mode),
	Stage("chinesespace_wait_factor", inject_chinese_space_pause),
	Stage("item_wait_factor", item_wait_factor),
	Stage("punctuation_wait_factor", inject_punctuation_pause),
	Stage("number_wait_factor", number_wait_factor),
	Stage("speech_viewer", speech_viewer),
)


def order_move_to_start_register():
	# Move to the front in reverse, so STAGES runs first and in order.
	for stage in reversed(STAGES):
		filter_speechSequence.moveToEnd(stage.handler, False)


def order_move_to_end_register():
	for stage in STAGES:
		filter_speechSequence.moveToEnd(stage.handler, True)


def register_stages():
	log.debug("register pipeline stages")
	speech_dictionary.install()
	for stage in STAGES:
		filter_speechSequence.register(stage.handler)
	order_move_to_start_register()


def unregister_stages():
	log.debug("unregister pipeline stages")
	for stage in STAGES:
		filter_speechSequence.unregister(stage.handler)
	speech_dictionary.uninstall()
```

`_run_logged` reproduces `with_speech_sequence_log` exactly, including leaving the result a generator when logging is off.

**3c. `pipeline/scope.py`:**

```python
from collections.abc import Callable

from . import register_stages, unregister_stages
from .settings import PipelineSettings, PipelineSettingsService, pipeline_settings


class PipelineScope:
	"""Keep the speech pipeline registered exactly while an owner wants it.

	WorldVoice always runs its pipeline. With scope "all", the global plugin
	also runs it for every other synthesizer.
	"""

	def __init__(
		self,
		settings: PipelineSettingsService,
		register: Callable[[], None],
		unregister: Callable[[], None],
	):
		self._settings = settings
		self._register = register
		self._unregister = unregister
		self._worldvoice = False
		self._global = False
		self._registered = False
		settings.subscribe(self._sync)

	@property
	def registered(self) -> bool:
		return self._registered

	def worldvoice_started(self) -> None:
		self._worldvoice = True
		self._sync()

	def worldvoice_ended(self) -> None:
		self._worldvoice = False
		self._sync()

	def attach_global(self) -> None:
		self._global = True
		self._sync()

	def detach_global(self) -> None:
		self._global = False
		self._sync()

	def _sync(self, settings: PipelineSettings | None = None) -> None:
		if self._worldvoice:
			wanted = True
		elif self._global:
			wanted = (settings or self._settings.get()).scope == "all"
		else:
			wanted = False
		if wanted == self._registered:
			return
		if wanted:
			self._register()
		else:
			self._unregister()
		self._registered = wanted


pipeline_scope = PipelineScope(pipeline_settings, register_stages, unregister_stages)
```

`test_pipeline_scope.py`'s loader stubs the package with `register_stages`, `unregister_stages` and `settings.pipeline_settings`; `scope.py` imports only those names plus the two types. Add `PipelineSettings = object` and `PipelineSettingsService = object` to that stub module.

**3d. `pipeline/settings.py`.** Delete `_last_scope_application`, `_load_scope_functions`, `clear_pipeline`, `clear_global_pipeline_scope`, `apply_worldvoice_pipeline`, `apply_global_pipeline_scope`, `apply_pipeline_after_worldvoice_end`, and the now unused `Callable` import if ruff flags it.

**3e. Main driver.**
- Imports from `.pipeline`: `inject_langchange_reorder`, `deduplicate_language_command`, `lang_cmd_to_voice`, `order_move_to_start_register`, `listable`. Drop `ignore_comma_between_number` and `item_wait_factor`.
- Import `from .pipeline.context import GENERIC_CONTEXT, SpeechContext` and `from .pipeline.scope import pipeline_scope`.
- Imports from `.pipeline.settings` become `get_effective_pipeline_settings, save_pipeline_settings` (both removed in Task 6).
- `_initialize`: replace `apply_worldvoice_pipeline()` with `pipeline_scope.worldvoice_started()`.
- `terminate`: replace `_run_cleanup("pipeline cleanup", clear_pipeline)` with `_run_cleanup("pipeline cleanup", pipeline_scope.worldvoice_ended)`.
- `speak`: `speechSequence = deduplicate_language_command(speechSequence, self.speech_context())`.
- `_set_cni`: delete the `if value: ... register ... else: ... unregister` block. `_set_itemwaitfactor`: delete its register/unregister block. Both stages are now always registered while the pipeline is; the config writes stay until Task 6.
- Add after `pause`:

```python
	def speech_context(self) -> SpeechContext:
		manager = self._voiceManager
		if manager is None:
			return GENERIC_CONTEXT
		return SpeechContext(
			supports_roles=True,
			language=self.language,
			number_language=getattr(self, "_numlan", "default"),
			speech_symbols=getattr(self, "speechSymbols", None),
			default_voice=manager.defaultVoiceInstance,
			voice_for_language=manager.getVoiceInstanceForLanguage,
		)
```

**3f. GlobalPlugin.**
- Delete the `WVStart, WVEnd` import, the `apply_global_pipeline_scope`, `apply_pipeline_after_worldvoice_end`, `clear_global_pipeline_scope` and `load_pipeline_settings` imports, the functions `on_worldvoice_start`/`on_worldvoice_end`, and their register/unregister calls.
- Add `from synthDrivers.WorldVoice.pipeline.scope import pipeline_scope`.
- `__init__`, after `patch()`: `pipeline_scope.attach_global()`, replacing the `if getSynth().name != "WorldVoice": apply_global_pipeline_scope(...)` lines.
- `terminate`, after `unpatch()`: `pipeline_scope.detach_global()`, replacing the clear lines.
- Remove `getSynth` from imports if it becomes unused.

**3g. `sayAll.py`:**

```python
from .pipeline.context import current_context
from .pipeline.settings import pipeline_settings
...
		waitFactor = pipeline_settings.effective(current_context().supports_roles).scaled_sayall_wait()
```

**3h. Tests.**
- `tests/test_pipeline_punctuation_pause.py`:
  - add `"synthDrivers.WorldVoice.pipeline.context"` and `"synthDrivers.WorldVoice.pipeline.scope"` to the pop list;
  - replace `settingsModule.get_effective_pipeline_settings = lambda: settings` with `settingsModule.pipeline_settings = SimpleNamespace(effective=lambda supports_roles: settings)`;
  - after `exec_module` add `module._test_settings = settings`;
  - `run_punctuation_filters` returns `list(module.inject_punctuation_pause(speech_sequence, module._test_settings, module.GENERIC_CONTEXT))`;
  - `test_positive_punctuation_wait_factor_inserts_a_punctuation_break` calls `run_punctuation_filters(module, ["Hello. World"])`;
  - the last test calls `module.register_stages()` and asserts `next(stage.handler for stage in module.STAGES if stage.log_key == "punctuation_wait_factor") in ...registered`;
  - `punctuation_settings` gains `number_mode="value"` (already there) and `scope="WorldVoice"`.
- `tests/test_worldvoice_lifecycle.py` (the first test's environment):
  - replace `"apply_worldvoice_pipeline": apply_pipeline, "clear_pipeline": clear_pipeline` with `"pipeline_scope": types.SimpleNamespace(worldvoice_started=apply_pipeline, worldvoice_ended=clear_pipeline)`;
  - search the file for other `clear_pipeline` keys and replace them the same way.
- `tests/test_runtime_composition.py:571-575`. Stub:
  - `.pipeline` with names `("inject_langchange_reorder", "deduplicate_language_command", "lang_cmd_to_voice", "order_move_to_start_register", "listable")`;
  - `.pipeline.settings` with `("get_effective_pipeline_settings", "save_pipeline_settings")`;
  - `stub(package + ".pipeline.context", GENERIC_CONTEXT=object(), SpeechContext=object)`;
  - `stub(package + ".pipeline.scope", pipeline_scope=SimpleNamespace())`.

- [ ] **Step 4: Run to verify**

Run: `python3 -m pytest tests/test_pipeline_scope.py tests/test_pipeline_stages.py tests/test_pipeline_punctuation_pause.py -q`
Expected: PASS.
Then run `python3 -m pytest tests -q`: all pass. Fix any remaining test stub that names a deleted function, using the same substitutions.

- [ ] **Step 5: Commit**

```bash
ruff format addon
git add addon/synthDrivers/WorldVoice/pipeline/__init__.py addon/synthDrivers/WorldVoice/pipeline/context.py addon/synthDrivers/WorldVoice/pipeline/scope.py addon/synthDrivers/WorldVoice/pipeline/settings.py addon/synthDrivers/WorldVoice/__init__.py addon/synthDrivers/WorldVoice/sayAll.py addon/globalPlugins/WorldVoice/__init__.py tests/test_pipeline_scope.py tests/test_pipeline_stages.py tests/test_pipeline_punctuation_pause.py tests/test_worldvoice_lifecycle.py tests/test_runtime_composition.py
git commit -m "refactor(pipeline): register stages from one STAGES table under a PipelineScope

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Main driver settings: descriptors, one settings builder, voice-parameter helper

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`. Changes:
  - confspec;
  - `supportedSettings`/`allSupportedSettings`;
  - `_initialize`;
  - `terminate`;
  - `loadSettings`/`saveSettings`;
  - the voice-parameter setters;
  - the 11 pipeline getters/setters.
- Test: `tests/test_worldvoice_pipeline_settings.py` (create); update `tests/test_worldvoice_lifecycle.py`, `tests/test_runtime_composition.py` (attributes set on `object.__new__` drivers)

**Interfaces:**
- Consumes: `PIPELINE_SETTINGS`, `PIPELINE_CONFSPEC`, `pipeline_settings` (Task 4); `STAGES`, `pipeline_scope`, `SpeechContext` (Task 5).
- Produces:
  - `SynthDriver._driver_settings(capabilities) -> list`;
  - `SynthDriver._pipeline_driver_setting(spec)` (staticmethod);
  - `SynthDriver._apply_pipeline_settings(settings)`;
  - `SynthDriver._set_voice_parameter(name, value)`;
  - module class `_PipelineSetting(key)`, installed on `SynthDriver` for each `spec.driver_id`;
  - instance flag `_pipelineSubscribed`.

- [ ] **Step 1: Write the failing tests**

```python
"""The WorldVoice synth exposes pipeline settings stored only in the pipeline config."""

import ast
from pathlib import Path
import types

import pytest

from test_pipeline_settings_service import load_settings_module


SYNTH = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/__init__.py"


class Setting:
	def __init__(self, kind, id, label=None, **options):
		self.kind, self.id, self.label, self.options = kind, id, label, options


def setting_factory(kind):
	return lambda id, label=None, **options: Setting(kind, id, label, **options)


class Base:
	@classmethod
	def VoiceSetting(cls): return Setting("voice", "voice")
	@classmethod
	def VariantSetting(cls): return Setting("variant", "variant")
	@classmethod
	def RateSetting(cls): return Setting("rate", "rate")
	@classmethod
	def RateBoostSetting(cls): return Setting("rateBoost", "rateBoost")
	@classmethod
	def PitchSetting(cls): return Setting("pitch", "pitch")
	@classmethod
	def InflectionSetting(cls): return Setting("inflection", "inflection")
	@classmethod
	def VolumeSetting(cls): return Setting("volume", "volume")

	def loadSettings(self, *args, **kwargs):
		self.loaded = True


def load_synth(monkeypatch, conf):
	settings_module = load_settings_module(monkeypatch, conf)
	tree = ast.parse(SYNTH.read_text(encoding="utf-8"))
	wanted = [
		node for node in tree.body
		if isinstance(node, ast.ClassDef) and node.name in {"_PipelineSetting", "SynthDriver"}
		or isinstance(node, ast.For) and ast.unparse(node.iter) == "PIPELINE_SETTINGS"
	]
	environment = {
		"SynthDriver": Base,
		"PIPELINE_SETTINGS": settings_module.PIPELINE_SETTINGS,
		"pipeline_settings": settings_module.pipeline_settings,
		"BooleanDriverSetting": setting_factory("bool"),
		"NumericDriverSetting": setting_factory("int"),
		"DriverSetting": setting_factory("str"),
		"_": lambda text: text,
		"config": types.SimpleNamespace(conf=conf),
		**{name: type(name, (), {}) for name in (
			"IndexCommand", "CharacterModeCommand", "LangChangeCommand", "BreakCommand",
			"PitchCommand", "RateCommand", "VolumeCommand")},
		"synthIndexReached": object(),
		"synthDoneSpeaking": object(),
	}
	exec(compile(ast.Module(body=wanted, type_ignores=[]), str(SYNTH), "exec"), environment)
	return environment["SynthDriver"], settings_module


def manager(capabilities=frozenset()):
	recorded = []
	return types.SimpleNamespace(
		defaultVoiceName="v",
		getVoiceCapabilities=lambda name: types.SimpleNamespace(settings=capabilities),
		reload=lambda: recorded.append("reload"),
		recorded=recorded,
	)


EXPECTED_IDS = [
	"voice", "variant", "rate", "rateBoost", "pitch", "inflection", "volume", "uwv",
	"cni", "numlan", "nummod", "globalwaitfactor", "numberwaitfactor", "pairwaitfactor",
	"itemwaitfactor", "sayallwaitfactor", "chinesespacewaitfactor", "punctuationpauseenabled",
	"removepunctuationcharacters", "punctuationwaitfactor",
]


def test_settings_lists_keep_their_order_and_store_pipeline_values_outside_speech_config(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, _ = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	synth._voiceManager = manager()
	assert [s.id for s in synth.allSupportedSettings] == EXPECTED_IDS
	assert [s.id for s in synth.supportedSettings] == [i for i in EXPECTED_IDS if i not in {"rateBoost", "inflection"}]
	synth._voiceManager = manager(frozenset({"rateBoost", "inflection"}))
	assert [s.id for s in synth.supportedSettings] == EXPECTED_IDS
	pipeline_ids = set(EXPECTED_IDS[8:]) - {"numlan"}
	for setting in synth.allSupportedSettings:
		assert setting.options.get("useConfig", True) is (setting.id not in pipeline_ids)
	cni = next(s for s in synth.allSupportedSettings if s.id == "cni")
	assert cni.options["availableInSettingsRing"] is False
	wait = next(s for s in synth.allSupportedSettings if s.id == "globalwaitfactor")
	assert (wait.kind, wait.options["minStep"], wait.options["defaultVal"]) == ("int", 10, 10)


def test_descriptors_read_and_write_through_the_service(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, _ = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	assert synth.itemwaitfactor == 10
	synth.itemwaitfactor = 30
	synth.globalwaitfactor = 57
	synth.nummod = "pair"
	assert conf["WorldVoice"]["pipeline"] == {"item_wait_factor": 30, "global_wait_factor": 50, "number_mode": "pair"}
	assert (synth.itemwaitfactor, synth.globalwaitfactor, synth.nummod) == (30, 50, "pair")
	assert "speech" not in conf


def test_load_settings_reapplies_waitfactor_without_writing_pipeline(monkeypatch):
	class Section(dict):
		def __setitem__(self, key, value):
			raise AssertionError(f"loadSettings wrote {key}")
	conf = {"WorldVoice": {"pipeline": Section(global_wait_factor=0)}}
	synth_class, _ = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	synth._voiceManager = manager()
	writes = []
	type(synth._voiceManager).waitfactor = property(lambda self: 0, lambda self, value: writes.append(value))
	synth.loadSettings(onlyChanged=True)
	assert writes == [0]
	assert synth._voiceManager.recorded == ["reload"]


def test_global_wait_change_reaches_the_voice_manager(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, settings_module = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	synth._voiceManager = types.SimpleNamespace(waitfactor=None)
	settings_module.pipeline_settings.subscribe(synth._apply_pipeline_settings)
	synth.globalwaitfactor = 100
	assert synth._voiceManager.waitfactor == 9
	synth._voiceManager = None
	synth.globalwaitfactor = 30


@pytest.mark.parametrize("name", ["volume", "rate", "pitch", "inflection", "variant", "rateBoost"])
@pytest.mark.parametrize("consistent", [False, True])
def test_voice_parameters_commit_and_follow_the_consistency_policy(monkeypatch, name, consistent):
	conf = {"WorldVoice": {"pipeline": {}, "autoLanguageSwitching": {"KeepMainLocaleParameterConsistent": consistent}}}
	synth_class, _ = load_synth(monkeypatch, conf)
	synth = object.__new__(synth_class)
	calls = []
	instance = types.SimpleNamespace(commit=lambda: calls.append("commit"))
	synth._voiceManager = types.SimpleNamespace(
		defaultVoiceInstance=instance,
		onVoiceParameterConsistent=lambda voice: calls.append(("consistent", voice)),
	)
	setattr(synth, name, 42)
	assert getattr(instance, name) == 42
	assert calls == ["commit"] + ([("consistent", instance)] if consistent else [])


def test_speech_context_falls_back_while_the_synth_is_not_running(monkeypatch):
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, _ = load_synth(monkeypatch, conf)
	generic = object()
	monkeypatch.setitem(synth_class.speech_context.__globals__, "GENERIC_CONTEXT", generic)
	monkeypatch.setitem(synth_class.speech_context.__globals__, "SpeechContext", lambda **kwargs: kwargs)
	synth = object.__new__(synth_class)
	synth._voiceManager = None
	assert synth.speech_context() is generic
	voice = object()
	synth._voiceManager = types.SimpleNamespace(defaultVoiceInstance=voice, getVoiceInstanceForLanguage=lambda lang: None)
	synth.language = "en"
	context = synth.speech_context()
	assert (context["number_language"], context["speech_symbols"], context["default_voice"]) == ("default", None, voice)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_worldvoice_pipeline_settings.py -q`
Expected: FAIL (no `_PipelineSetting`, no `_driver_settings`).

- [ ] **Step 3: Implement**

- Imports:
  - `from .pipeline import STAGES, ...` (keep the Task 5 names);
  - `from .pipeline.settings import PIPELINE_CONFSPEC, PIPELINE_SETTINGS, pipeline_settings` (drop `get_effective_pipeline_settings` and `save_pipeline_settings`).
- confspec: `"pipeline": dict(PIPELINE_CONFSPEC),` and

```python
	"log": {
		"enable": "boolean(default=false)",
		**{stage.log_key: "boolean(default=false)" for stage in STAGES},
	},
```

- Replace both settings properties (lines 142–381) with:

```python
	@staticmethod
	def _pipeline_driver_setting(spec):
		options = {"availableInSettingsRing": spec.ring, "defaultVal": spec.default, "useConfig": False}
		if spec.display_name is not None:
			options["displayName"] = spec.display_name
		if spec.kind is bool:
			return BooleanDriverSetting(spec.driver_id, spec.label, **options)
		if spec.kind is int:
			return NumericDriverSetting(spec.driver_id, spec.label, minStep=spec.min_step, **options)
		return DriverSetting(spec.driver_id, spec.label, **options)

	def _driver_settings(self, capabilities):
		"""The synth settings; ``capabilities`` None lists every optional voice setting."""
		settings = [SynthDriver.VoiceSetting(), SynthDriver.VariantSetting(), SynthDriver.RateSetting()]
		if capabilities is None or "rateBoost" in capabilities:
			settings.append(SynthDriver.RateBoostSetting())
		settings.append(SynthDriver.PitchSetting())
		if capabilities is None or "inflection" in capabilities:
			settings.append(SynthDriver.InflectionSetting())
		settings.append(SynthDriver.VolumeSetting())
		settings.append(
			BooleanDriverSetting(
				"uwv",
				_("Detect language based on Unicode characters"),
				availableInSettingsRing=True,
				defaultVal=True,
				displayName=_("Detect language based on Unicode characters"),
			),
		)
		for spec in PIPELINE_SETTINGS:
			if spec.driver_id is None:
				continue
			settings.append(self._pipeline_driver_setting(spec))
			if spec.driver_id == "cni":
				settings.append(
					DriverSetting(
						"numlan",
						# Translators: Label for a setting in voice settings dialog.
						_("Number &Language"),
						availableInSettingsRing=True,
						defaultVal="default",
						# Translators: Label for a setting in synth settings ring.
						displayName=_("Number Language"),
					),
				)
		return settings

	@property
	def supportedSettings(self):
		capabilities = self._voiceManager.getVoiceCapabilities(self._voiceManager.defaultVoiceName)
		return self._driver_settings(capabilities.settings)

	@property
	def allSupportedSettings(self):
		return self._driver_settings(None)
```

- `__init__`: add `self._pipelineSubscribed = False` beside `self._pipelineRegistered = False`.
- `_initialize`: after `self._voiceManager = VoiceManager(...)` and its debug line, add:

```python
		self._apply_pipeline_settings(pipeline_settings.get())
		pipeline_settings.subscribe(self._apply_pipeline_settings)
		self._pipelineSubscribed = True
```

- `terminate`: before `voiceManager = self._voiceManager`, add:

```python
		if self._pipelineSubscribed:
			_run_cleanup(
				"pipeline settings unsubscribe",
				lambda: pipeline_settings.unsubscribe(self._apply_pipeline_settings),
			)
			self._pipelineSubscribed = False
```

- `loadSettings` and `saveSettings`: replace both with:

```python
	def loadSettings(self, *args, **kwargs):
		super().loadSettings(*args, **kwargs)
		# Pipeline settings are not NVDA driver config; re-read them for this profile.
		self._apply_pipeline_settings(pipeline_settings.get())
		self._voiceManager.reload()

	def _apply_pipeline_settings(self, settings):
		manager = self._voiceManager
		if manager is not None:
			manager.waitfactor = min(settings.global_wait_factor // 10, 9)
```

- Voice setters (`_set_volume`, `_set_rate`, `_set_pitch`, `_set_inflection`, `_set_variant`, `_set_rateBoost`): each body becomes one call, e.g. `self._set_voice_parameter("volume", value)` (`"rateBoost"` and `enable` for the last one). Add:

```python
	def _set_voice_parameter(self, name, value):
		instance = self._voiceManager.defaultVoiceInstance
		setattr(instance, name, value)
		instance.commit()
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]:
			self._voiceManager.onVoiceParameterConsistent(instance)
```

- Delete the 11 pipeline `_get_x`/`_set_x` pairs: cni, nummod, globalwaitfactor, numberwaitfactor, pairwaitfactor, itemwaitfactor, sayallwaitfactor, chinesespacewaitfactor, punctuationpauseenabled, removepunctuationcharacters, punctuationwaitfactor. Keep `_get_availableNummods`, `_get_availableNumlans`, `_get_numlan`/`_set_numlan`.
- After the class:

```python
class _PipelineSetting:
	"""A synth attribute stored only in the pipeline config, never in NVDA's speech config."""

	def __init__(self, key):
		self._key = key

	def __get__(self, synth, owner=None):
		if synth is None:
			return self
		return getattr(pipeline_settings.get(), self._key)

	def __set__(self, synth, value):
		pipeline_settings.update(**{self._key: value})


for _spec in PIPELINE_SETTINGS:
	if _spec.driver_id is not None:
		setattr(SynthDriver, _spec.driver_id, _PipelineSetting(_spec.key))
```

  The test loader executes the `_PipelineSetting` class node, which must therefore come before the loop and after the class. Place it right after `class SynthDriver` ends.
- `BooleanDriverSetting`, `DriverSetting` and `NumericDriverSetting` imports stay.
- Tests:
  - every test that builds a driver with `object.__new__` and then calls `terminate()` must set `driver._pipelineSubscribed = False`. These are `tests/test_worldvoice_lifecycle.py` (~line 370) and `tests/test_runtime_composition.py` (~line 276);
  - in the first lifecycle test environment add `"pipeline_settings": types.SimpleNamespace(get=lambda: types.SimpleNamespace(global_wait_factor=10), subscribe=lambda listener: None, unsubscribe=lambda listener: None)`;
  - `tests/test_runtime_composition.py:574` stub of `.pipeline.settings` becomes `PIPELINE_CONFSPEC={}`, `PIPELINE_SETTINGS=()`, `pipeline_settings=SimpleNamespace()`;
  - the `.pipeline` stub adds `STAGES=()`.

- [ ] **Step 4: Run to verify**

Run: `python3 -m pytest tests/test_worldvoice_pipeline_settings.py -q` → PASS.
Then run `python3 -m pytest tests -q` → all pass.

- [ ] **Step 5: Commit**

```bash
ruff format addon/synthDrivers/WorldVoice/__init__.py
git add addon/synthDrivers/WorldVoice/__init__.py tests/test_worldvoice_pipeline_settings.py tests/test_worldvoice_lifecycle.py tests/test_runtime_composition.py
git commit -m "refactor(WorldVoice): expose pipeline settings as descriptors over the settings service

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: UI panels write through the service (D2, D5, dead handlers, dialog Cancel)

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py`. Changes:
  - imports 15–24;
  - `SpeechPipelinePanel` 104–387;
  - `LogSettingsPanel` 1059–1075.
- Modify: `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py`
- Test: `tests/test_pipeline_panels.py` (create)

**Interfaces:**
- Consumes: `pipeline_settings` and `PIPELINE_CONFIG_KEYS` (Task 4); `STAGES` (Task 5).
- Produces: `speechSettingsDialog._LOG_LABELS: dict[str, str]`.

- [ ] **Step 1: Write the failing tests**

```python
"""Pipeline UI panels save through the pipeline settings service."""

import ast
from collections import OrderedDict
from pathlib import Path
import types

from test_pipeline_stages import ORDER


ROOT = Path(__file__).resolve().parents[1]
PANELS = ROOT / "addon/globalPlugins/WorldVoice/speechSettingsDialog.py"
VOICE_PANEL = ROOT / "addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py"
SYNTH = ROOT / "addon/synthDrivers/WorldVoice/__init__.py"


def load(path, names, environment):
	tree = ast.parse(path.read_text(encoding="utf-8"))
	nodes = [
		node for node in tree.body
		if isinstance(node, ast.ClassDef) and node.name in names
		or isinstance(node, ast.Assign) and any(getattr(t, "id", None) in names for t in node.targets)
	]
	exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), environment)
	return environment


class Widget:
	def __init__(self, value=None, selection=0):
		self.value, self.selection = value, selection

	def GetValue(self):
		return self.value

	def GetCurrentSelection(self):
		return self.selection


def test_log_labels_match_stages_and_confspec():
	environment = load(PANELS, {"_LOG_LABELS"}, {"_": lambda text: text})
	assert list(environment["_LOG_LABELS"]) == ORDER
	tree = ast.parse(SYNTH.read_text(encoding="utf-8"))
	source = ast.unparse(tree)
	assert "stage.log_key: 'boolean(default=false)' for stage in STAGES" in source


def test_pipeline_panel_saves_once_through_the_service():
	updates = []
	environment = load(PANELS, {"SpeechPipelinePanel"}, {
		"SettingsPanel": object,
		"_": lambda text: text,
		"pipeline_settings": types.SimpleNamespace(update=lambda **changes: updates.append(changes)),
	})
	panel = object.__new__(environment["SpeechPipelinePanel"])
	panel._scope_value = ["all", "WorldVoice"]
	panel._scope_choice = Widget(selection=0)
	panel.number_mode_value = ["value", "number", "pair"]
	panel._number_mode_choice = Widget(selection=2)
	panel._ignore_comma_between_number_checkbox = Widget(True)
	panel._global_wait_factor_slider = Widget(3)
	for name in ("number", "item", "sayall", "chinesespace", "punctuation", "pair"):
		setattr(panel, f"_{name}_wait_factor_slider", Widget(7))
	panel._punctuation_pause_enabled_checkbox = Widget(False)
	panel._remove_punctuation_characters_checkbox = Widget(True)
	panel._punctuation_pause_characters_edit = Widget(" .,")

	panel.onSave()

	assert updates == [{
		"scope": "all", "ignore_comma_between_number": True, "number_mode": "pair", "global_wait_factor": 30,
		"number_wait_factor": 7, "item_wait_factor": 7, "sayall_wait_factor": 7, "chinesespace_wait_factor": 7,
		"punctuation_wait_factor": 7, "punctuation_pause_enabled": False, "remove_punctuation_characters": True,
		"punctuation_pause_characters": " .,", "pair_wait_factor": 7,
	}]
	for name in ("onGlobalWaitFactorSliderScroll", "sliderEnable", "onScopeSelectionChange"):
		assert not hasattr(panel, name)


def test_voice_panel_discard_restores_live_pipeline_changes():
	state = {"item_wait_factor": 10, "number_mode": "value"}
	updates = []
	def update(**changes):
		updates.append(changes)
		state.update(changes)

	class Base:
		def onDiscard(self):
			updates.append("nvda discard")

	environment = load(VOICE_PANEL, {"WorldVoiceVoiceSettingsPanel"}, {
		"VoiceSettingsPanel": Base,
		"pipeline_settings": types.SimpleNamespace(get=lambda: types.SimpleNamespace(**state), update=update),
		"PIPELINE_CONFIG_KEYS": ("item_wait_factor", "number_mode"),
	})
	panel = object.__new__(environment["WorldVoiceVoiceSettingsPanel"])
	panel._pipelineSnapshot = types.SimpleNamespace(**state)
	type(panel).driver = property(lambda self: types.SimpleNamespace(name="WorldVoice"))
	state["item_wait_factor"] = 40

	panel.onDiscard()

	assert updates == ["nvda discard", {"item_wait_factor": 10}]
	assert state["item_wait_factor"] == 10
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_pipeline_panels.py -q`
Expected: FAIL (`_LOG_LABELS` missing, `onSave` calls `PipelineSettings`, no `onDiscard`).

- [ ] **Step 3: Implement**

`speechSettingsDialog.py`:
- Replace the `.pipeline.settings` import block with `from synthDrivers.WorldVoice.pipeline.settings import pipeline_settings`, and the `pl` import with `from synthDrivers.WorldVoice.pipeline import STAGES, pl`.
- After `addonHandler.initTranslation()`, add:

```python
# Labels for the per-stage log switches; the switches themselves come from STAGES.
_LOG_LABELS = {
	"apply_speech_dictionaries": _("apply_speech_dictionaries"),
	"ignore_comma_between_number": _("Ignore comma between number"),
	"number_language": _("Number language"),
	"number_mode": _("Number mode"),
	"chinesespace_wait_factor": _("chinese space wait factor"),
	"item_wait_factor": _("item wait factor"),
	"punctuation_wait_factor": _("punctuation wait factor"),
	"number_wait_factor": _("number wait factor"),
	"speech_viewer": _("speech viewer"),
}
```

- `LogSettingsPanel.settings` becomes:

```python
	settings = OrderedDict(
		(stage.log_key, {"label": _LOG_LABELS.get(stage.log_key, stage.log_key)}) for stage in STAGES
	)
```

- `SpeechPipelinePanel.makeSettings`:
  - `pipeline_settings = load_pipeline_settings()` → `settings = pipeline_settings.get()`; rename later reads from `pipeline_settings.x` to `settings.x`;
  - scope selection: `self._scope_choice.Select(self._scope_value.index(settings.scope))` in the existing try/except; delete `self._scope = ...`;
  - delete the `self.Bind(...)` calls for `onIgnoreCommaBetweenNumberCheckboxChange`, `onGlobalWaitFactorSliderScroll`, `onNumberWaitFactorSliderScroll`, `onPairWaitFactorSliderScroll`, `onItemWaitFactorSliderScroll`, `onSayallWaitFactorSliderScroll`, `onChinesespaceWaitFactorSliderScroll` and `onPunctuationWaitFactorSliderScroll`, including their multi-line forms;
  - keep the binds for `onPunctuationPauseEnabledChange` and `onRemovePunctuationCharactersChange`.
- Delete the methods `onScopeSelectionChange`, the 8 `pass` handlers, `sliderEnable` and `sliderDisable` (of `SpeechPipelinePanel` only).
- `onSave`:

```python
	def onSave(self):
		pipeline_settings.update(
			scope=self._scope_value[self._scope_choice.GetCurrentSelection()],
			ignore_comma_between_number=self._ignore_comma_between_number_checkbox.GetValue(),
			number_mode=self.number_mode_value[self._number_mode_choice.GetCurrentSelection()],
			global_wait_factor=self._global_wait_factor_slider.GetValue() * 10,
			number_wait_factor=self._number_wait_factor_slider.GetValue(),
			item_wait_factor=self._item_wait_factor_slider.GetValue(),
			sayall_wait_factor=self._sayall_wait_factor_slider.GetValue(),
			chinesespace_wait_factor=self._chinesespace_wait_factor_slider.GetValue(),
			punctuation_wait_factor=self._punctuation_wait_factor_slider.GetValue(),
			punctuation_pause_enabled=self._punctuation_pause_enabled_checkbox.GetValue(),
			remove_punctuation_characters=self._remove_punctuation_characters_checkbox.GetValue(),
			punctuation_pause_characters=self._punctuation_pause_characters_edit.GetValue(),
			pair_wait_factor=self._pair_wait_factor_slider.GetValue(),
		)
```

`VoiceSettingsDialogs.py`:
- import `from .pipeline.settings import PIPELINE_CONFIG_KEYS, pipeline_settings` instead of `DEFAULT_PIPELINE_SETTINGS`; drop `import config` if unused.
- `makeSettings` begins with `self._pipelineSnapshot = pipeline_settings.get() if self._isWorldVoice() else None`.
- `_addPunctuationPauseCharactersControl`: `self.punctuationPauseCharactersEdit.SetValue(pipeline_settings.get().punctuation_pause_characters)`.
- `onSave`:

```python
	def onSave(self):
		pipeline_settings.update(punctuation_pause_characters=self.punctuationPauseCharactersEdit.GetValue())
		super().onSave()
```

- Add:

```python
	def _isWorldVoice(self):
		return getattr(self.driver, "name", None) == "WorldVoice"

	def onDiscard(self):
		super().onDiscard()
		# Pipeline settings are not NVDA driver config, so loadSettings cannot
		# restore values changed while this panel was open.
		snapshot = getattr(self, "_pipelineSnapshot", None)
		if snapshot is None or not self._isWorldVoice():
			return
		current = pipeline_settings.get()
		changes = {
			key: getattr(snapshot, key)
			for key in PIPELINE_CONFIG_KEYS
			if getattr(current, key) != getattr(snapshot, key)
		}
		if changes:
			pipeline_settings.update(**changes)
```

- [ ] **Step 4: Run to verify**

Run: `python3 -m pytest tests/test_pipeline_panels.py -q` → PASS.
Then run `python3 -m pytest tests -q` → all pass.

- [ ] **Step 5: Commit**

```bash
ruff format addon/globalPlugins/WorldVoice/speechSettingsDialog.py addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py
git add addon/globalPlugins/WorldVoice/speechSettingsDialog.py addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py tests/test_pipeline_panels.py
git commit -m "refactor(ui): save pipeline panels through the settings service and derive log switches from STAGES

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Delete the old settings API, and add guards

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py`. Delete:
  - `load_pipeline_settings`, `save_pipeline_settings`;
  - `_runtime_value`, `get_effective_pipeline_settings`;
  - `apply_pipeline_settings_to_synth`, `apply_pipeline_settings_to_speech_config`;
  - `_pipeline_section`, and the `getSynth` import.
- Delete: `tests/test_punctuation_removal_settings.py` (covered by `test_pipeline_settings_service.py`)
- Test: `tests/test_pipeline_settings_guards.py` (create)

**Interfaces:** none new.

- [ ] **Step 1: Write the guard test**

```python
"""Pipeline settings have one reader/writer and the retired API stays gone."""

from pathlib import Path
import re

ADDON = Path(__file__).resolve().parents[1] / "addon"
SETTINGS = ADDON / "synthDrivers/WorldVoice/pipeline/settings.py"
RETIRED = [
	"get_effective_pipeline_settings", "_runtime_value", "apply_pipeline_settings_to_synth",
	"apply_pipeline_settings_to_speech_config", "apply_global_pipeline_scope",
	"apply_pipeline_after_worldvoice_end", "clear_global_pipeline_scope", "apply_worldvoice_pipeline",
	"clear_pipeline", "_last_scope_application", "static_register", "dynamic_register",
	"with_speech_sequence_log", "load_pipeline_settings", "save_pipeline_settings",
	"get_ignore_comma_between_number", "get_number_mode", "get_item_wait_factor", "get_number_wait_factor",
	"get_chinesespace_wait_factor", "get_punctuation_wait_factor", "get_punctuation_pause_chars",
	"get_punctuation_pause_enabled", "get_pair_wait_factor",
]


def addon_sources():
	for path in ADDON.rglob("*.py"):
		parts = path.relative_to(ADDON).parts
		if "driver" in parts and parts.index("driver") + 2 < len(parts) and parts[parts.index("driver") + 2] in {"driver", "sonic"}:
			continue
		if parts[:4] == ("synthDrivers", "WorldVoice", "driver", "sonic"):
			continue
		yield path, path.read_text(encoding="utf-8")


def test_retired_pipeline_api_is_gone():
	found = [
		(str(path), name)
		for path, text in addon_sources()
		for name in RETIRED
		if re.search(rf"\b{re.escape(name)}\b", text)
	]
	assert found == []


def test_only_the_settings_module_touches_the_pipeline_config_section():
	pattern = re.compile(r"\[\s*[\"']pipeline[\"']\s*\]")
	found = [str(path) for path, text in addon_sources() if pattern.search(text) and path != SETTINGS]
	assert found == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_pipeline_settings_guards.py -q`
Expected: FAIL, listing `pipeline/settings.py` names (`load_pipeline_settings` and others).

- [ ] **Step 3: Delete and verify**

- Delete the listed functions from `pipeline/settings.py`.
- `git rm tests/test_punctuation_removal_settings.py`.
- Run `grep -rn "load_pipeline_settings\|save_pipeline_settings" addon tests` and fix any leftover caller to use `pipeline_settings.get()` / `.update(...)`.

- [ ] **Step 4: Verify everything**

Run each and check the result:

```bash
python3 -m pytest tests -q
ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select F401,F821
ruff format --check addon
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver' addon/synthDrivers/WorldVoice/driver/sonic
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
```

Expected:
- the test suite is all green;
- ruff reports `All checks passed!` and the format check is clean;
- the `git diff --stat` is empty;
- `git ls-files` prints nothing.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/pipeline/settings.py tests/test_pipeline_settings_guards.py
git commit -m "refactor(pipeline): retire the reflective settings readers and mirrors

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(`git rm` already staged the deleted test file.)
