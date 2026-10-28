# Phase 51: NVDA-name check for eSpeak, SAPI5, OneCore — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** `Voice.ready()` of the eSpeak, SAPI5 and OneCore wrappers checks each wrapper's NVDA-name lists against the running NVDA and skips the engine with one warning when a name is missing; tests check the same lists against every NVDA feature release 2024.1 → 2026.3beta6 and the `ref/nvda` dev tree.

**Architecture:** A core module `runtime/hostNames.py` defines "exists" for module names (`hasattr`) and class names (`hasattr` or a `STORE_ATTR` in the class's function code) and the skip log. Each wrapper's port carries `NVDA_MODULE_NAMES`, `NVDA_PRIVATES`, `NVDA_OVERRIDES`; its `Voice.ready()` calls `host_names_ready`. A test helper builds the same view statically from a release's compiled source (`git show <tag>:…`).

**Tech Stack:** Python 3.11+ (tests run on 3.14), `dis`, `ast`, pytest, git (read-only on `ref/nvda`).

**Spec:** `docs/superpowers/specs/2026-10-28-phase51-nvda-private-check-design.md`

## Global Constraints

- No behaviour change where every name exists (spec §2 anti-goals): same classes, same construction, no log line.
- Runtime check never stricter than the static test (spec §4.2): live sees the MRO, static sees one class and one module body.
- Log: one `logger.warning` of the form `Skipping %s engine candidate: %s lacks names this engine needs: %s` (engine, host label, `", "`-joined sorted qualified names); host label `f"NVDA {versionInfo.version}"`, `versionInfo` imported only inside `_nvdaLabel()`.
- Versions (spec §5): `release-2024.1`, `-2024.2`, `-2024.3`, `-2024.4`, `-2025.1`, `-2025.2`, `-2025.3`, `-2026.1`, `-2026.2`, `-2026.3beta6`, plus the working tree. `FIRST_COMPLETE = {"Espeak": "2024.1", "SAPI5": "2025.3", "OneCore": "2024.1"}`. A missing tag fails (no skip).
- Never checkout/switch in `ref/nvda`; only `git -C ref/nvda show` / `rev-parse`. Nothing under `ref/` is modified or staged.
- Do not modify inner drivers: `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*'` and the other workflow §7 protected paths stay empty; `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` empty.
- Drivers stay independently installable: no import between `driver/<Engine>/` packages; shared code only in `runtime/`. `driver/__init__.py`, discovery and the voice manager unchanged.
- Naming (refactor9 §6.1, `tests/test_naming_layers.py`): `runtime/` snake_case; wrappers mixedCase (`_nvdaLabel`, `_nvdaBase`).
- ruff pinned `0.16.3`; `prek run --all-files` passes; commits `<type>: <summary>` + body, no Co-Authored-By, explicit paths, re-stage hook edits, no `--no-verify`, no push/merge, no `git stash`.
- Tests serial with the MemAvailable < 3 GB watchdog (`cd /workspace/WorldVoice-phase51 || exit 1; ( while sleep 5; do …; done ) & W=$!; python3 -m pytest -p no:cacheprovider tests; kill $W`). Mutation runs on a scratch copy, `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`, output to a file, per-run timeout.
- Baseline at `2fff780`: 3363 passed, 0 skipped. No readme/changelog/translation changes.

## Review Focus

1. A listed NVDA name exists only as a class-level default or property (`_get_x`), not as a `self.x =` store: must count as present at run time. Task 1 `test_class_level_and_property_names_are_present`.
2. A name NVDA creates in a base class's `__init__` (moved up the hierarchy in a future NVDA): runtime must not skip (no false skip); the static test may fail. Task 1 `test_inherited_instance_attribute_is_present_live`, Task 2 `test_static_view_does_not_see_out_of_file_bases`.
3. SAPI5 on NVDA 2024.x, where `sapi5.SynthDriverAudioStream` is missing at import: the wrapper must import and `ready()` must log, not discovery's import error. Task 4 `test_sapi5_imports_and_skips_without_audio_stream_class`.
4. All names present (every supported NVDA ≥ 2025.3): `ready()` true, `versionInfo` never imported, no log. Task 1 `test_ready_does_not_call_label_or_log_when_complete`, Task 4 `test_ready_on_ref_nvda_is_true_and_silent`.
5. An NVDA tag absent from another checkout: the multi-version test fails with a message naming the tag and `git -C ref/nvda fetch --tags`. Task 5 `test_missing_release_tag_fails_with_fetch_hint`.

---

### Task 1: Core `runtime/hostNames.py`

**Files:**
- Create: `addon/synthDrivers/WorldVoice/runtime/hostNames.py`
- Test: `tests/test_runtime_host_names.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `stored_attribute_names(code: types.CodeType) -> frozenset[str]`
  - `missing_host_names(module, host_class, *, module_names: Iterable[str], class_names: Iterable[str]) -> tuple[str, ...]` — sorted; entries `f"{module.__name__}.{n}"` and `f"{host_class.__module__}.{host_class.__qualname__}.{n}"`.
  - `host_names_ready(engine: str, module, host_class, *, module_names, class_names, host_label: Callable[[], str], logger) -> bool`

- [ ] **Step 1: Write the failing tests** (load the module with `addon_loader.load_source(None, "hostNames_under_test", path, register=False)`; synthetic modules via `types.ModuleType` + `exec(source, module.__dict__)`):
  - `test_stored_attribute_names_finds_stores_in_methods_nested_functions_and_lambdas`: for code compiled from a class with `self.a = 1` in `__init__`, `self.b` in another method, `self.c` inside an inner function, and a default-argument lambda `lambda s, v=1: [s.__dict__]` (a load only) — assert `{"a","b","c"} <= result` and `"loaded"` (only read as `self.loaded`) not in result.
  - `test_stored_attribute_names_reports_mangled_form`: `self.__x = 1` in class `K` → `"_K__x" in result`.
  - `test_missing_module_names_are_qualified_and_sorted`: module `fake.mod` with `b = 1` → `missing_host_names(mod, Cls, module_names={"b","z","a"}, class_names=())` == `("fake.mod.a", "fake.mod.z")`.
  - `test_instance_attributes_from_init_and_other_methods_are_present`.
  - `test_class_level_and_property_names_are_present`: class attribute `_flag = False`, method `_m`, `_get_rate` with `rate = property(_get_rate)`, `staticmethod`/`classmethod` whose body stores `obj._s = 1` → all present.
  - `test_inherited_instance_attribute_is_present_live`: base class stores `self._base = 1` in `__init__`; check against the subclass → present.
  - `test_missing_class_names_are_qualified_with_module_and_qualname` → `("fake.mod.Cls._gone",)`.
  - `test_ready_does_not_call_label_or_log_when_complete`: label raising `AssertionError` if called, recording logger → returns `True`, no records.
  - `test_ready_logs_one_warning_and_returns_false_when_missing`: → `False`; logger got exactly one `warning` call whose formatted text is `"Skipping SAPI5 engine candidate: NVDA 2025.1.0 lacks names this engine needs: fake.mod.a, fake.mod.Cls._gone"`.

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest -p no:cacheprovider -q tests/test_runtime_host_names.py`: errors (file not found).

- [ ] **Step 3: Implement** the three functions in `runtime/hostNames.py` (module docstring: what "exists" means, spec §4.2). Live class view: for each class in `host_class.__mro__` except `object`, each value in `vars(cls)`; take `__code__` from the value or from its `__func__`, `fget`, `fset`, `fdel`; union `stored_attribute_names`. `stored_attribute_names` walks `co_consts` recursively and collects `argval` of `STORE_ATTR` from `dis.get_instructions`. Imports: standard library only.

- [ ] **Step 4: Run, expect PASS** — the file passes (9 tests); full suite 3372 passed, 0 skipped. `prek run --all-files` Passed (naming guard accepts the snake_case core names).

- [ ] **Step 5: Commit** — `feat: add the core host-name existence check` (paths: the two files).

### Task 2: Static release view and agreement with the live view

**Files:**
- Create: `tests/nvda_releases.py`
- Test: `tests/test_nvda_release_names.py` (agreement part)

**Interfaces:**
- Consumes: `stored_attribute_names` (Task 1).
- Produces (in `tests/nvda_releases.py`):
  - `NVDA = REF / "nvda"`; `RELEASES: tuple[str, ...]` (the ten tags of Global Constraints, oldest first); `WORKING_TREE = "working-tree"`.
  - `release_source(version: str, file: str) -> str` — working tree reads `NVDA/source/synthDrivers/<file>`; a tag uses `git -C NVDA show release-<version>:source/synthDrivers/<file>`; a missing tag raises `pytest.fail(...)` with `release-<version>` and `git -C ref/nvda fetch --tags` in the message; cached (`functools.cache`).
  - `static_missing(source: str, module_label: str, class_name: str, class_label: str, *, module_names, class_names) -> tuple[str, ...]` — same qualified, sorted format as `missing_host_names`; module names = top-level `STORE_NAME` of the compiled module; class names = `STORE_NAME` of the class body code (found in the module's `co_consts` by `co_name == class_name`) ∪ `stored_attribute_names(body)`. Compile with `SyntaxWarning`s suppressed. A class absent from the source makes every class name missing.

- [ ] **Step 1: Write the failing tests** in `tests/test_nvda_release_names.py`:
  - `test_static_and_live_views_agree_on_synthetic_source`: one source with top-level assignment, `def`, `class`, `import`, a name inside a top-level `if`, a class with class attribute, method, instance attributes in `__init__`/other method/nested function, property, mangled name; a name list with present and absent entries of both kinds → `static_missing(...) == missing_host_names(live module, live class, ...)`.
  - `test_static_view_does_not_see_out_of_file_bases`: class `Child(base_from_namespace)` where the base stores `self._base` → live: present; static: `("m.Child._base",)`. (Pins spec §4.2's asymmetry.)
  - `test_static_view_ignores_globals_bound_only_inside_functions`: `def f(): global late; late = 1` → static reports `late` missing, live (body run, `f` not called) agrees.

- [ ] **Step 2: Run, expect FAIL** — import error on `nvda_releases`.

- [ ] **Step 3: Implement** `tests/nvda_releases.py` per Interfaces.

- [ ] **Step 4: Run, expect PASS** — 3 tests; full suite 3375 passed, 0 skipped.

- [ ] **Step 5: Commit** — `test: add a static NVDA release view that agrees with the live check`.

### Task 3: The three name lists and their guards

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py:59-64` (`_EspeakPort` constants)
- Modify: `addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py:39-62` (`_Sapi5Port`)
- Modify: `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py:29-53` (`_OneCorePort`)
- Modify: `tests/test_native_strategy_guards.py:23-35`, `:65-118`, `:176-201`

**Interfaces:**
- Consumes: nothing.
- Produces: on each port, `NVDA_MODULE_NAMES`, `NVDA_PRIVATES`, `NVDA_OVERRIDES` as `frozenset({...})` literals with the values of spec §3 (eSpeak `NVDA_PRIVATES = frozenset()`; `_class_constant` returns `set()` for a call without arguments). Test helper `_module_reads(tree, alias) -> set[str]`.

- [ ] **Step 1: Write the failing tests** (in `tests/test_native_strategy_guards.py`):
  - `test_espeak_nvda_names_are_listed_and_exist_in_nvda`: `NVDA_MODULE_NAMES == _module_reads(tree, "_espeak") == {"EE_OK","_execWhenDone","espeakDLL","isSpeaking","onIndexReached","player"}`; `NVDA_PRIVATES == set()`; overridden underscore methods of the wrapper `SynthDriver` that `ref/nvda` `espeak.py` defines (`def name(`) `== NVDA_OVERRIDES == {"_onIndexReached"}`.
  - In `test_sapi5_nvda_privates_are_listed_and_exist_in_nvda`: add `NVDA_MODULE_NAMES == _module_reads(tree, "sapi5")`; remove `"sapi5"` from the accessed-alias set for privates; keep the whole-word existence and override equality.
  - In `test_onecore_parent_privates_are_listed_and_exist`: same with `"oneCore"`.
  - The regex existence checks stay until Task 5 replaces them with the static view.

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest -p no:cacheprovider -q tests/test_native_strategy_guards.py`: 3 failures (`NVDA_MODULE_NAMES` missing).

- [ ] **Step 3: Implement** the constants (spec §3 values; `_EspeakPort` docstring keeps the existing text and says which NVDA class the overrides belong to). No other wrapper change.

- [ ] **Step 4: Run, expect PASS** — guards pass; full suite 3376 passed, 0 skipped.

- [ ] **Step 5: Commit** — `refactor: list every NVDA name the eSpeak, SAPI5 and OneCore wrappers use`.

### Task 4: `Voice.ready()` checks the lists; SAPI5 imports on every NVDA

**Files:**
- Modify: the three wrappers (imports; `_nvdaLabel()`; `Voice.ready`; SAPI5 `_nvdaBase` and the class statements at `:135`, `:243`)
- Test: `tests/test_nvda_ready.py` (new), `tests/test_native_strategy_guards.py` (import-time guard)

**Interfaces:**
- Consumes: `host_names_ready` (Task 1); port constants (Task 3); `static_missing`, `release_source` (Task 2); harnesses `load_espeak(monkeypatch, tmp_path)`, `load_sapi5(monkeypatch)`, `load_onecore(monkeypatch)` returning `.outer` (wrapper module), `.base`, `.inner` (eSpeak `_espeak`).
- Produces: `Voice.ready() -> bool` on the three wrappers; module-level `_nvdaLabel() -> str` in each; SAPI5 `_nvdaBase(name: str) -> type`.

- [ ] **Step 1: Write the failing tests** (`tests/test_nvda_ready.py`, parametrized over the three engines with a small table: harness, NVDA module object, NVDA class object, one module name and one class name to delete):
  - `test_ready_on_ref_nvda_is_true_and_silent[engine]`: `env.outer.Voice.ready() is True`; recording logger (monkeypatched `env.outer.log`) has no records; `"versionInfo"` not newly in `sys.modules`.
  - `test_ready_skips_with_one_warning_when_a_module_name_is_missing[engine]`: `monkeypatch.delattr(module, name)`, `versionInfo` stubbed with `version="2025.1.0"` → `False`; exactly one warning containing `"Skipping <engine> engine candidate: NVDA 2025.1.0 lacks names this engine needs: "` and the qualified name.
  - `test_ready_skips_when_a_class_name_is_missing[engine]`: delete a listed method from NVDA's class (eSpeak `_onIndexReached`, SAPI5 `_speakThread`, OneCore `_processQueue`) → `False`, name qualified with NVDA's class (`synthDrivers.oneCore.OneCoreSynthDriver._processQueue`).
  - `test_live_and_static_views_agree_on_ref_nvda[engine]`: `missing_host_names(...)` with the port lists `== static_missing(release_source("working-tree", file), ...) == ()`.
  - `test_sapi5_imports_and_skips_without_audio_stream_class`: load SAPI5 harness pieces with `sapi5.SynthDriverAudioStream` removed before the wrapper module loads (harness variant or reload of `outer` via `load_source`) → module loads; `ready()` is `False` naming `synthDrivers.sapi5.SynthDriverAudioStream`.
  - In `tests/test_native_strategy_guards.py`, `test_wrappers_read_no_nvda_module_attribute_at_import`: for the three wrappers, walking the module AST but not into function/lambda bodies, every `<alias>.X` (`_espeak`, `sapi5`, `oneCore`) is the argument of a `_nvdaBase("X")` call instead → none found; and SAPI5 has exactly the two `_nvdaBase` class bases.

- [ ] **Step 2: Run, expect FAIL** — ready is the base `True`/object has no `ready`; the guard reports SAPI5 `:135`, `:243`.

- [ ] **Step 3: Implement** per spec §4.1/§4.3: `from ...runtime.hostNames import host_names_ready`; `_nvdaLabel()`; `Voice.ready` classmethod (eSpeak: module `_espeak`, class `BaseSynthDriver`; SAPI5: `sapi5`, `BaseSynthDriver`; OneCore: `oneCore`, `oneCore.SynthDriver`); `class_names=NVDA_PRIVATES | NVDA_OVERRIDES`; SAPI5 `_nvdaBase` with the spec's comment. If the harness needs `ready` reachable with `voice_base=object`, nothing else changes there.

- [ ] **Step 4: Run, expect PASS** — new tests pass; naming, drift, contract and drain suites unchanged; full suite ≈ 3376 + 13 (= 3 × 4 + 1) + 1 = 3390 passed, 0 skipped (record the real count).

- [ ] **Step 5: Commit** — `feat: skip eSpeak, SAPI5 or OneCore when NVDA lacks a name they use`.

### Task 5: Multi-version test

**Files:**
- Modify: `tests/test_nvda_release_names.py`
- Modify: `tests/test_native_strategy_guards.py` (drop the regex existence lines superseded here; keep listing/override rules)

**Interfaces:**
- Consumes: `RELEASES`, `release_source`, `static_missing` (Task 2); port constants read by AST (reuse `_class_constant` logic — move it to `tests/nvda_releases.py` as `port_names(engine) -> tuple[set, set, set]` if both files need it).
- Produces: nothing.

- [ ] **Step 1: Write the tests**:
  - `ENGINES = {"Espeak": (("_espeak.py", "synthDrivers._espeak"), ("espeak.py", "SynthDriver", "synthDrivers.espeak.SynthDriver")), "SAPI5": (("sapi5.py", "synthDrivers.sapi5"), ("sapi5.py", "SynthDriver", "synthDrivers.sapi5.SynthDriver")), "OneCore": (("oneCore.py", "synthDrivers.oneCore"), ("oneCore.py", "OneCoreSynthDriver", "synthDrivers.oneCore.OneCoreSynthDriver"))}`.
  - `test_nvda_names_exist_from_the_first_complete_release[engine-version]` over `ENGINES × (*RELEASES, WORKING_TREE)`: `missing == ()` when version ≥ `FIRST_COMPLETE[engine]` (working tree counts as newest), else `missing != ()`; failure message lists the missing names.
  - `test_missing_release_tag_fails_with_fetch_hint`: `release_source("1999.1", "sapi5.py")` raises `pytest.fail.Exception` whose message contains `release-1999.1` and `git -C ref/nvda fetch --tags`.
  - `test_release_table_covers_the_supported_range`: `RELEASES[0] == "2024.1"`, versions strictly increasing, and `buildVars.py`'s `addon_minimumNVDAVersion` equals `RELEASES[0]`.

- [ ] **Step 2: Run** — the SAPI5 rows for 2024.1–2025.2 must report names (expected by the table), everything else `()`. If any other row reports names, stop and record it as a finding (spec §1.1 says none).

- [ ] **Step 3:** Remove the regex whole-word existence assertions from the SAPI5/OneCore guard tests (the static view checks existence now, on every version).

- [ ] **Step 4: Run, expect PASS** — 33 + 2 tests; full suite ≈ 3425 passed, 0 skipped (record the real count).

- [ ] **Step 5: Commit** — `test: check the NVDA names against every supported NVDA release`.

### Task 6: Mutation proof, verification, spec notes

**Files:**
- Modify: spec §10 (implementation notes); ledger `.superpowers/sdd/2026-10-28-phase51-nvda-private-check/progress.md`.
- Scratch only: `<scratchpad>/p51/mutants.py`, output file.

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: mutant table for the report.

- [ ] **Step 1:** Copy the worktree to scratch (`cp -a`, keep `ref` symlink), apply one textual mutant at a time to `runtime/hostNames.py` (drop the MRO walk to `host_class` only; drop nested-code recursion; `STORE_ATTR`→`LOAD_ATTR`; drop `fget`/`__func__`; `hasattr` negated for module names; skip sorting; log `error` instead of `warning`; call label eagerly; return `True` on missing) and to one wrapper `ready()` (wrong list union, e.g. privates only), run `tests/test_runtime_host_names.py tests/test_nvda_release_names.py tests/test_nvda_ready.py -x` with `timeout 300`, `PYTHONDONTWRITEBYTECODE=1`, results to a file. Record killed/survived + killing test.
- [ ] **Step 2:** For each survivor add a test (TDD) or record why it is equivalent.
- [ ] **Step 3:** Full verification (workflow §7): suite count vs 3363, `prek run --all-files`, `git diff --check`, protected paths, Neural.
- [ ] **Step 4:** Fill spec §10 (rulings, mutants, counts, per-version table) and commit `docs: record the phase 51 implementation notes`.
