"""The shared segment-barrier kinds every wrapper names its barriers by."""

import ast

from addon_loader import WORLDVOICE

BARRIERS = WORLDVOICE / "runtime/barriers.py"


def test_barrier_module_imports_nothing():
	# Portable core: the constants module depends on nothing, so any layer may import it.
	tree = ast.parse(BARRIERS.read_text(encoding="utf-8"))
	assert not [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]
