"""The shared segment-barrier kinds every wrapper names its barriers by."""

import ast

from addon_loader import WORLDVOICE, load_source

BARRIERS = WORLDVOICE / "runtime/barriers.py"


def test_shared_barrier_values():
	module = load_source(None, "segment_barriers_under_test", BARRIERS, register=False)
	# The values are the meanings, so a missing-barrier error reads the same for every engine.
	assert (module.SYNTHESIZED, module.ENGINE_DONE, module.PLAYED_OUT) == (
		"synthesized",
		"engine_done",
		"played_out",
	)


def test_shared_barriers_are_the_only_public_names():
	module = load_source(None, "segment_barriers_under_test", BARRIERS, register=False)
	public = {name for name in vars(module) if not name.startswith("_")}
	assert public == {"SYNTHESIZED", "ENGINE_DONE", "PLAYED_OUT"}


def test_barrier_module_imports_nothing():
	# Portable core: the constants module depends on nothing, so any layer may import it.
	tree = ast.parse(BARRIERS.read_text(encoding="utf-8"))
	assert not [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]
