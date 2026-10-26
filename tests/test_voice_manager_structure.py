"""The voice manager gets config and language injected instead of importing them."""

import ast
from pathlib import Path

ADDON = Path(__file__).resolve().parents[1] / "addon"


def test_voice_manager_gets_config_and_language_injected():
	tree = ast.parse((ADDON / "synthDrivers/WorldVoice/voices/manager.py").read_text(encoding="utf-8"))
	imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
	imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
	assert not imported & {"config", "languageHandler"}
