"""Every engine strategy is a NativeStrategy, and the host never probes for hooks."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"
ENGINES = ("Espeak", "SAPI5", "RHVoice", "OneCore", "VE", "Cerence")


def test_every_strategy_subclasses_native_strategy():
	for engine in ENGINES:
		tree = ast.parse((ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
		strategies = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name.endswith("Strategy")]
		assert strategies, engine
		for node in strategies:
			assert [ast.unparse(base) for base in node.bases] == ["NativeStrategy"], (engine, node.name)


def test_host_has_no_optional_hook_probing_or_failure_switch():
	host = (ROOT / "runtime/segmentHost.py").read_text(encoding="utf-8")
	assert "getattr(self._strategy" not in host
	for path in ROOT.rglob("*.py"):
		assert "fail_accepted_on_control_error" not in path.read_text(encoding="utf-8"), path
