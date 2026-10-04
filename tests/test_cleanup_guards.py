"""Removed compatibility layers and dead APIs stay removed."""

import ast
from pathlib import Path

ADDON = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"


def _relative_imports(path):
	tree = ast.parse(path.read_text(encoding="utf-8"))
	return {
		(node.module, alias.name)
		for node in ast.walk(tree)
		if isinstance(node, ast.ImportFrom) and node.level == 1
		for alias in node.names
	}


def test_compatibility_shims_are_gone():
	for shim in ("taskManager.py", "requestBuilder.py", "driver/engineSession.py"):
		assert not (ADDON / shim).exists(), shim
	imports = _relative_imports(ADDON / "__init__.py")
	assert {("runtime.scheduler", "TaskManager"), ("runtime.requestBuilder", "queue_speech_sequence")} <= imports
	assert not {module for module, _ in imports} & {"taskManager", "requestBuilder", "driver.engineSession"}


def test_execution_ledgers_are_ignored_in_every_checkout():
	# The plan executor writes ledgers under .superpowers/; a fresh clone has
	# no local ignore file there, so the root .gitignore must cover them.
	lines = (ADDON.parents[2] / ".gitignore").read_text(encoding="utf-8").splitlines()
	assert ".superpowers/" in lines


def test_speech_future_has_no_then():
	tree = ast.parse((ADDON / "runtime/scheduler.py").read_text(encoding="utf-8"))
	future = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SpeechFuture")
	assert [node.name for node in future.body if isinstance(node, ast.FunctionDef)] == []


CONTEXTUAL_LEGACY = (
	"legacy_contextual",
	"speak_legacy_segment",
	"LEGACY_SEGMENT",
	"legacy_segment_sink",
	"configure_legacy_segment_events",
)


def test_contextual_legacy_mode_is_gone():
	found = []
	for path in sorted(ADDON.rglob("*.py")):
		name = path.relative_to(ADDON).as_posix()
		if name.startswith("driver/Neural/"):
			continue  # Untracked, restored locally from storage/; not part of the add-on.
		text = path.read_text(encoding="utf-8")
		found.extend(f"{name}: {word}" for word in CONTEXTUAL_LEGACY if word in text)
	assert found == []
