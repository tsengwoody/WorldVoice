# Phase 11 Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Make ruff recognise NVDA's logger.
- Justify every remaining blind except inline.
- Sort imports.
- Give the tests one shared NVDA stub helper.

**Architecture:** Configuration and comment-only edits in `addon/`; a new `tests/nvda_stubs.py` plus a `conftest.py` fixture; guard tests that keep both in place.

**Tech Stack:** Python 3.11; pytest; ruff.

**Spec:** `docs/superpowers/specs/2026-10-05-phase11-hygiene-design.md`

## Global Constraints

- Never edit `driver/<Engine>/driver/` or `driver/sonic`; every ruff command passes `--exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic'`.
- No behavior change: BLE001 handling is comment-only, and I001 only reorders imports inside contiguous blocks.
- `git add` explicit paths; never stage the `docs/superpowers/finish_task.md` deletion or `refactor.md`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full suite: `python3 -m pytest tests -q` (baseline 1528).

## Review Focus

1. **An import moved by I001 past a statement it depends on**: `sys.path.insert` in the main driver, `addonHandler.initTranslation()` order, `from .driver import SynthDriver` in engine wrappers before `Voice`. Read each changed file's import block in the diff.
2. **A `# noqa: BLE001` whose reason does not match what the handler does.** The guard checks presence only; the review checks truth.
3. **A migrated harness whose stub now lands under a different module name**, or loses `__path__`. The full suite covers it; also run the harness-heavy files 5×.

---

### Task 1: Logger config and BLE001 reasons

**Files:** `pyproject.toml`; the 45 sites in `addon/`; `tests/test_hygiene_guards.py` (create)

- [ ] **Step 1: Guard test (failing)**

```python
"""Hygiene rules that ruff alone does not express."""

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"
RUFF_SCOPE = [
	"--exclude", "addon/synthDrivers/WorldVoice/driver/*/driver",
	"--exclude", "addon/synthDrivers/WorldVoice/driver/sonic",
]


def _addon_sources():
	for path in ADDON.rglob("*.py"):
		parts = path.relative_to(ADDON).parts
		if parts[:3] == ("synthDrivers", "WorldVoice", "driver") and (
			parts[3] == "sonic" or len(parts) > 5 and parts[4] == "driver"
		):
			continue
		yield path


def test_every_blind_except_says_where_the_error_goes():
	missing = []
	for path in _addon_sources():
		for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
			if "noqa: BLE001" in line and not re.search(r"noqa: BLE001 - \S", line):
				missing.append(f"{path.relative_to(ROOT)}:{number}")
	assert missing == []


def test_ruff_reports_no_blind_except_or_unsorted_import():
	result = subprocess.run(
		["ruff", "check", "addon", *RUFF_SCOPE, "--select", "BLE001,I001", "--output-format", "concise"],
		cwd=ROOT, capture_output=True, text=True,
	)
	assert result.returncode == 0, result.stdout
```

If `ruff` is not on PATH in some environment, skip the second test with `pytest.importorskip`-style logic: `shutil.which("ruff") is None` → `pytest.skip`.

- [ ] **Step 2: Run** → the ruff test fails (45 BLE001 + 29 I001).

- [ ] **Step 3: Implement**
- `pyproject.toml`, under `[tool.ruff.lint]`: `logger-objects = ["logHandler.log"]`.
- Apply the reason table from the spec with a script. For each BLE001 site reported by ruff, classify the handler by its first lines (spec table), and append `  # noqa: BLE001 - <reason>` to the `except` line. The 10 unclassified sites get their hand-written reasons from the spec.
- Run `ruff format addon` (comments stay on the line).

- [ ] **Step 4: Run** `ruff check ... --select BLE001` → 0. The guard's first test passes; the second still fails on I001 until Task 2.
- [ ] **Step 5: Commit** `chore: recognise NVDA's logger and justify each remaining blind except`.

---

### Task 2: Import order

- [ ] **Step 1:** `ruff check addon <scope> --select I001 --fix --unsafe-fixes`
- [ ] **Step 2:** `git diff --stat`. For each file, read the import-block hunk and confirm no import crossed a non-import statement. The main driver's `sys.path.insert` block, `addonHandler.initTranslation()` and module constants must stay in place. Ledger the files.
- [ ] **Step 3:** `ruff format addon`; full suite; `ruff check <scope> --select BLE001,I001,F401,F821` → 0; the hygiene guard passes.
- [ ] **Step 4: Commit** `style: sort imports`.

---

### Task 3: Shared NVDA stubs for tests

**Files:** `tests/nvda_stubs.py` (create), `tests/conftest.py`, the 10 test files listed in the spec, `tests/test_hygiene_guards.py`

- [ ] **Step 1: Guard (failing)** — append to `tests/test_hygiene_guards.py`:

```python
def test_tests_share_one_module_stub_helper():
	local = []
	for path in (ROOT / "tests").glob("*.py"):
		if path.name == "nvda_stubs.py":
			continue
		for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
			if re.match(r"\s*def (module|package|stub)\(name", line):
				local.append(f"{path.name}:{number}")
	assert local == []
```

- [ ] **Step 2: Run** → FAIL (6 files).

- [ ] **Step 3: Implement**

`tests/nvda_stubs.py`:

```python
"""Stand-ins for NVDA modules, registered in sys.modules for one test."""

import builtins
import sys
from types import ModuleType


class StubModules:
	"""Create stub modules through monkeypatch, so each test restores sys.modules."""

	def __init__(self, monkeypatch):
		self._monkeypatch = monkeypatch

	def module(self, name, **attrs):
		result = ModuleType(name)
		result.__dict__.update(attrs)
		self._monkeypatch.setitem(sys.modules, name, result)
		return result

	def package(self, name, path, **attrs):
		result = self.module(name, **attrs)
		result.__path__ = [str(path)]
		return result

	def translation(self):
		"""Install the identity ``_`` that NVDA add-ons get from initTranslation."""
		self._monkeypatch.setattr(builtins, "_", lambda text: text, raising=False)
```

`tests/conftest.py`: add

```python
@pytest.fixture
def stub_modules(monkeypatch):
	return StubModules(monkeypatch)
```

with `from nvda_stubs import StubModules`.

Migrate:
- In each harness and in `test_runtime_composition.py`, replace the local `def module(...)` and `def package(...)` (or `stub`) definitions with `stubs = StubModules(monkeypatch)` and `module, package = stubs.module, stubs.package` (or `stub = stubs.module`). Leave every call site untouched.
- In `test_pipeline_settings_service.py`, `test_pipeline_log.py`, `test_core_archive.py` and `test_pipeline_punctuation_pause.py`, replace each `X = ModuleType("x"); X.attr = ...; monkeypatch.setitem(sys.modules, "x", X)` with `stubs.module("x", attr=...)`, and each `monkeypatch.setattr(builtins, "_", ...)` with `stubs.translation()`. Keep everything else. A stub that later code mutates (`conf` dicts, fake objects) is passed as the same object, so identity is preserved.

- [ ] **Step 4: Run**
- the full suite;
- each migrated file 5×;
- the guard → PASS.
- [ ] **Step 5: Commit** `test: share one NVDA stub helper`.

Final verification:

```bash
python3 -m pytest tests -q
ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select BLE001,I001,F401,F821
ruff format --check addon
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver' addon/synthDrivers/WorldVoice/driver/sonic
```
