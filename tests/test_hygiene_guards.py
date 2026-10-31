"""Hygiene rules that ruff alone does not express."""

import ast
import re
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"


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
	for path in (*_addon_sources(), *(ROOT / "tests").glob("*.py")):
		for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
			if "noqa: BLE001" in line and not re.search(r"noqa: BLE001 - \S", line):
				missing.append(f"{path.relative_to(ROOT)}:{number}")
	assert missing == []


def test_ruff_version_matches_the_pre_commit_hook():
	pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
	config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
	required = re.search(r'^required-version = "==(\S+)"$', pyproject, re.MULTILINE)
	hook = re.search(r"ruff-pre-commit\n(?:\s*#.*\n)*\s*rev: v(\S+)", config)
	assert required and hook
	assert required.group(1) == hook.group(1)


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff is not installed")
def test_ruff_reports_nothing():
	# Every rule, as pyproject.toml configures it. No CLI --select or --exclude: either would
	# replace the pyproject lists, and --exclude would bring script_data.py back in.
	# pyproject has no `select`, so the rules are ruff's defaults minus the ignores; its
	# required-version makes any other ruff fail here instead of checking other rules.
	result = subprocess.run(
		["ruff", "check", "addon", "tests", "--output-format", "concise"],
		cwd=ROOT,
		capture_output=True,
		text=True,
		check=False,
	)
	assert result.returncode == 0, result.stdout + result.stderr


def test_deprecation_warnings_fail_the_suite():
	# pyproject.toml turns them into errors, so a deprecated call fails the test that makes it.
	with pytest.raises(DeprecationWarning, match="probe"):
		warnings.warn("probe", DeprecationWarning, stacklevel=1)


def test_pre_commit_runs_the_ruff_lint_hook():
	config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
	lint = config.index("- id: ruff\n")
	assert "args: [ --fix ]" in config[lint : config.index("- id: ruff-format")]
	assert "omits the lint hook" not in config


def test_pre_commit_hooks_cover_the_addon_and_the_tests():
	config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
	scopes = re.findall(r"^\s*files: (\S+)$", config, re.MULTILINE)
	assert scopes
	assert set(scopes) == {"^(addon|tests)/"}


def test_generics_is_imported_only_after_the_package_that_adds_its_path():
	# `generics` lives at the add-on root, which only the WorldVoice synth
	# package adds to sys.path; import sorting must not move it first.
	for path in _addon_sources():
		tree = ast.parse(path.read_text(encoding="utf-8"))
		imports = [
			node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module and node.level == 0
		]
		generics = [node.lineno for node in imports if node.module.split(".")[0] == "generics"]
		if not generics or path.relative_to(ADDON).parts[:2] == ("synthDrivers", "WorldVoice"):
			continue
		worldvoice = [node.lineno for node in imports if node.module.startswith("synthDrivers.WorldVoice")]
		assert worldvoice and min(worldvoice) < min(generics), path


# The spec's reason table: the first entry whose calls all appear in a handler's
# own body names where its error goes. Combined entries come first, so a handler
# that both latches and keeps its error says both.
_REASONS = (
	(("_failSegmentControl", "error = exc"), "latched, and kept to raise after the remaining cleanup"),
	(("record_error",), "recorded on the record; the segment fails"),
	(("_failSegmentControl",), "latched: the player or engine state is unknown"),
	(("_latch_fault",), "latched as a lifecycle fault"),
	(("_terminationError",), "kept and raised once termination finishes"),
	(("firstError",), "collected; the first is raised after every step ran"),
	(("error = exc",), "kept and raised after the remaining cleanup"),
	(("return unsupported",), "any failure means drain is unsupported"),
	(("return error",), "returned as the admission error"),
)


def _own_body(handler):
	"""The handler's statements, without the bodies of handlers nested inside it."""
	import copy

	body = copy.deepcopy(handler.body)
	for statement in body:
		for nested in ast.walk(statement):
			if isinstance(nested, ast.ExceptHandler):
				nested.body = [ast.Pass()]
	return "\n".join(ast.unparse(statement) for statement in body)


def _marked_handlers():
	"""(location, reason, the first matching _REASONS keys) for every handler with a BLE001 reason."""
	for path in _addon_sources():
		source = path.read_text(encoding="utf-8")
		lines = source.splitlines()
		for node in ast.walk(ast.parse(source)):
			if not isinstance(node, ast.ExceptHandler):
				continue
			match = re.search(r"noqa: BLE001 - (.+)$", lines[node.lineno - 1])
			if match is None:
				continue
			body = _own_body(node)
			keys = next((keys for keys, _reason in _REASONS if all(key in body for key in keys)), None)
			yield f"{path.relative_to(ROOT)}:{node.lineno}", match.group(1), keys


def test_blind_except_reasons_match_their_handlers():
	reasons = dict(_REASONS)
	wrong = [
		f"{where}: {reason!r} != {reasons[keys]!r}"
		for where, reason, keys in _marked_handlers()
		if keys is not None and reason != reasons[keys]
	]
	assert wrong == []


def test_every_reason_entry_still_checks_a_handler():
	# An entry no marked handler selects checks nothing: a renamed call it names silently ends
	# the check of its handlers.
	used = {keys for _where, _reason, keys in _marked_handlers()}
	assert [keys for keys, _reason in _REASONS if keys not in used] == []


@pytest.fixture(scope="module")
def test_sources():
	# Both scans below walk every test file: parse them once, and let the trees go with this module.
	return tuple(
		(path, ast.parse(path.read_text(encoding="utf-8"))) for path in (ROOT / "tests").glob("*.py")
	)


def test_only_the_addon_loader_loads_modules_from_files(test_sources):
	# Tests load add-on files through tests/addon_loader.py, so the loading steps have one copy.
	loaders = []
	for path, tree in test_sources:
		if path.name == "addon_loader.py":
			continue
		for node in ast.walk(tree):
			name = getattr(node, "attr", None) or (node.name if isinstance(node, ast.alias) else None)
			if name == "spec_from_file_location":
				loaders.append(f"{path.name}:{node.lineno}")
	assert loaders == []


def test_no_test_module_imports_another(test_sources):
	# Shared helpers live in harness modules and fixtures in conftest.py; pytest collects test
	# modules, so a helper kept in one is hard to find and is loaded under two names.
	imports = []
	for path, tree in test_sources:
		for node in ast.walk(tree):
			if isinstance(node, ast.ImportFrom):
				names = [node.module or ""]
			elif isinstance(node, ast.Import):
				names = [alias.name for alias in node.names]
			else:
				continue
			imports.extend(
				f"{path.name}:{node.lineno}" for name in names if name.split(".")[0].startswith("test_")
			)
	assert imports == []


# An engine is stopped only through the scheduler: TaskManager cancels the request token and
# then stops each playback port, EngineSession.cancel forwards to its adapter and
# VoiceClassAdapter.cancel to the engine core. In segment (drain) mode a stop that skips the
# scheduler silences the segment in flight without failing it, so the request waits for a
# drain that never comes; SynthDriver._set_voice once did that through a VoiceFacade.stop.
_ENGINE_CANCEL_HOPS = {
	("synthDrivers/WorldVoice/runtime/scheduler.py", "TaskManager._stop_playback"),
	("synthDrivers/WorldVoice/runtime/session.py", "EngineSession.cancel"),
	("synthDrivers/WorldVoice/bridge/engineAdapter.py", "VoiceClassAdapter.cancel"),
}
# The last word of a receiver's name that marks it as a voice or an engine playback endpoint:
# default_voice_instance, get_voice_instance(...), session, playback, port, _adapter, _core,
# and the usual aliases for a wrapper's SynthDriver core: driver, engine, synth.
_ENGINE_ENDPOINTS = frozenset(
	{
		"voice",
		"instance",
		"facade",
		"session",
		"playback",
		"port",
		"adapter",
		"core",
		"driver",
		"engine",
		"synth",
	},
)


def _last_word(node):
	"""The last word of the name an expression ends in: ``self._voiceManager`` -> ``manager``."""
	while isinstance(node, ast.Call | ast.Subscript):
		node = node.func if isinstance(node, ast.Call) else node.value
	name = node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
	words = re.findall(r"[a-z]+", re.sub(r"([a-z])([A-Z])", r"\1_\2", name).lower())
	return words[-1] if words else ""


def _engine_stops():
	"""(file, enclosing qualified name, line, call) for every stop()/cancel() on a voice or engine endpoint."""
	for path in _addon_sources():
		name = path.relative_to(ADDON).as_posix()
		if name.startswith("synthDrivers/WorldVoice/driver/Neural/"):
			# A locally restored, untracked Neural engine is not the add-on's own source.
			continue
		found = []

		def visit(node, scope, found=found):
			for child in ast.iter_child_nodes(node):
				inner = scope
				if isinstance(child, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
					inner = (*scope, child.name)
				elif (
					isinstance(child, ast.Call)
					and isinstance(child.func, ast.Attribute)
					and child.func.attr in ("stop", "cancel")
					and _last_word(child.func.value) in _ENGINE_ENDPOINTS
				):
					found.append((".".join(scope), child.lineno, ast.unparse(child)))
				visit(child, inner)

		visit(ast.parse(path.read_text(encoding="utf-8")), ())
		for scope, line, call in found:
			yield name, scope, line, call


def test_engines_are_stopped_only_through_the_scheduler():
	stray = [
		f"{name}:{line} {scope}: {call}"
		for name, scope, line, call in _engine_stops()
		if (name, scope) not in _ENGINE_CANCEL_HOPS
	]
	assert stray == []


def test_every_engine_cancel_hop_is_still_in_place():
	# A hop no call matches checks nothing: a rename would let a new direct stop through.
	found = {(name, scope) for name, scope, _line, _call in _engine_stops()}
	assert sorted(_ENGINE_CANCEL_HOPS - found) == []


def test_voices_offer_no_stop_or_cancel():
	# Voice objects are what callers outside the runtime hold; a stop there bypasses the scheduler.
	methods = [
		f"{path.relative_to(ADDON).as_posix()}:{item.lineno} {node.name}.{item.name}"
		for path in _addon_sources()
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
		if isinstance(node, ast.ClassDef) and node.name in ("Voice", "VoiceFacade")
		for item in node.body
		if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and item.name in ("stop", "cancel")
	]
	assert methods == []
