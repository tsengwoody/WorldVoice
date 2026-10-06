"""Load add-on source files under the module names each test chooses.

Tests load add-on modules from their files rather than importing them: each test gets fresh
module objects, often under an alias package, so one test's module state never reaches
another and the NVDA entry point in ``synthDrivers/WorldVoice/__init__.py`` never runs. The
caller names the module, the package it belongs to and how it is registered; these helpers
only remove the repeated steps.
"""

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"
WORLDVOICE = ADDON / "synthDrivers/WorldVoice"


def load_source(monkeypatch, name, path, *, register=True):
	"""Load the module at path as name and return it.

	With register, the module is in sys.modules while its body runs, as relative imports and
	dataclasses need, and monkeypatch removes it when the test ends. Without register the
	module is never in sys.modules, and monkeypatch may be None.
	"""
	if register and monkeypatch is None:
		raise ValueError("Registering a module needs monkeypatch to remove it after the test")
	spec = importlib.util.spec_from_file_location(name, path)
	module = importlib.util.module_from_spec(spec)
	if register:
		monkeypatch.setitem(sys.modules, name, module)
	spec.loader.exec_module(module)
	return module


def alias_package(monkeypatch, name, path=None):
	"""Register an empty package called name whose submodules load from path.

	``name.sub`` then imports path/sub.py with its relative imports resolved inside the alias,
	without running path/__init__.py. With no path the package has no submodules of its own.
	"""
	package = ModuleType(name)
	package.__path__ = [] if path is None else [str(path)]
	monkeypatch.setitem(sys.modules, name, package)
	return package


def load_definitions(path, names, namespace, *, members=None):
	"""Run the named top-level definitions of path in namespace and return namespace.

	Tests use this for code that cannot be imported without wx or the whole of NVDA: namespace
	supplies whatever the definitions refer to. A name is a class, function or assigned
	variable, or ``Class.method`` for one method run as a plain function. Definitions run in
	source order. With members, each class keeps only those methods and loses its bases and
	decorators, so a class whose base needs NVDA can still run.
	"""
	tree = ast.parse(path.read_text(encoding="utf-8"))
	wanted = set(names)
	found = set()
	nodes = []
	for node in tree.body:
		if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
			defined = (node.name,)
		elif isinstance(node, ast.Assign):
			defined = tuple(getattr(target, "id", None) for target in node.targets)
		elif isinstance(node, ast.AnnAssign):
			defined = (getattr(node.target, "id", None),)
		else:
			defined = ()
		if wanted.intersection(defined):
			found.update(wanted.intersection(defined))
			if isinstance(node, ast.ClassDef) and members is not None:
				node.body = [
					item
					for item in node.body
					if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and item.name in members
				]
				node.bases = []
				node.decorator_list = []
			nodes.append(node)
		if isinstance(node, ast.ClassDef):
			for item in node.body:
				qualified = f"{node.name}.{getattr(item, 'name', '')}"
				if qualified in wanted and isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
					found.add(qualified)
					nodes.append(item)
	missing = wanted - found
	if missing:
		raise LookupError(f"{path.name} defines none of {sorted(missing)}")
	exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
	return namespace
