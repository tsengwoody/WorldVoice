"""VE and Cerence are hand-kept copies; any new divergence must be deliberate."""

import ast
from pathlib import Path

DRIVERS = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/driver"
ALLOWED = {
	"_PROFILE",
	"_ContextualVECallback._process",
	"SynthDriver._callbackAdmission",
	"Voice.variants",
	# Each inner initialize loads its own DLLs from its own architecture folder.
	"_nativeFiles",
}
# Cerence names its architecture folder from sys.maxsize, as its inner initialize does.
CERENCE_ONLY = {"import:import sys"}


def _definitions(source):
	tree = ast.parse(source)
	result = {}
	for node in tree.body:
		if isinstance(node, ast.ClassDef):
			for item in node.body:
				if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
					result[f"{node.name}.{item.name}"] = ast.dump(item)
				elif isinstance(item, (ast.Assign, ast.AnnAssign)):
					result[
						f"{node.name}.{ast.unparse(item.targets[0] if isinstance(item, ast.Assign) else item.target)}"
					] = ast.dump(item)
			result[node.name + ".<bases>"] = ast.dump(ast.Tuple(elts=node.bases, ctx=ast.Load()))
		elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
			result[node.name] = ast.dump(node)
		elif isinstance(node, ast.Assign):
			result[ast.unparse(node.targets[0])] = ast.dump(node)
		elif isinstance(node, (ast.Import, ast.ImportFrom)):
			result["import:" + ast.unparse(node)] = ""
	return result


def test_cerence_differs_from_ve_only_where_allowed():
	ve = (DRIVERS / "VE/__init__.py").read_text(encoding="utf-8")
	cerence = (DRIVERS / "Cerence/__init__.py").read_text(encoding="utf-8")
	cerence = cerence.replace("Cerence", "VE").replace("ttsapi", "ve2")
	left, right = _definitions(ve), _definitions(cerence)
	assert CERENCE_ONLY <= right.keys()
	right = {name: value for name, value in right.items() if name not in CERENCE_ONLY}
	assert left.keys() == right.keys()
	differing = {name for name in left if left[name] != right[name]}
	assert differing == ALLOWED
