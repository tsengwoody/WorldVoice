"""Removed compatibility layers and dead APIs stay removed."""

import ast
from pathlib import Path

ADDON = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"


def test_compatibility_shims_are_gone():
	for shim in ("taskManager.py", "requestBuilder.py", "driver/engineSession.py"):
		assert not (ADDON / shim).exists(), shim
	text = (ADDON / "__init__.py").read_text(encoding="utf-8")
	assert "from .runtime.scheduler import TaskManager\n" in text
	assert "from .runtime.requestBuilder import queue_speech_sequence\n" in text


def test_speech_future_has_no_then():
	tree = ast.parse((ADDON / "runtime/scheduler.py").read_text(encoding="utf-8"))
	future = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SpeechFuture")
	assert [node.name for node in future.body if isinstance(node, ast.FunctionDef)] == []
