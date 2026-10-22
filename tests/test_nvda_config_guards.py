"""NVDA facts the pipeline settings fallback relies on, read from ref/nvda.

The stored-value fallback (pipeline/settings.py read_stored) assumes NVDA validates each stored
value when it is read, lets the validation error through get, and raises configobj's
ValidateError. A new NVDA that changes any of these fails here first.
"""

import ast

import pytest
from addon_loader import REF

SOURCE = REF / "nvda/source"


def _source(relative):
	path = SOURCE / relative
	if not path.is_file():
		pytest.skip("ref/nvda is not checked out")
	return path.read_text(encoding="utf-8")


def _method(tree, class_name, method_name):
	for node in ast.walk(tree):
		if isinstance(node, ast.ClassDef) and node.name == class_name:
			for item in node.body:
				if isinstance(item, ast.FunctionDef) and item.name == method_name:
					return item
	raise LookupError(f"{class_name}.{method_name}")


def test_nvda_validates_a_leaf_on_read_and_get_passes_the_error_on():
	tree = ast.parse(_source("config/__init__.py"))
	cache_leaf = ast.unparse(_method(tree, "AggregatedSection", "_cacheLeaf"))
	assert "val = self.manager.validator.check(spec, val)" in cache_leaf
	get = _method(tree, "AggregatedSection", "get")
	handlers = [handler for node in ast.walk(get) if isinstance(node, ast.Try) for handler in node.handlers]
	assert [ast.unparse(handler.type) for handler in handlers] == ["KeyError"]


def test_nvda_imports_validate_error_from_configobj_validate():
	tree = ast.parse(_source("argsParsing.py"))
	imports = [
		node
		for node in ast.walk(tree)
		if isinstance(node, ast.ImportFrom) and node.module == "configobj.validate"
	]
	assert any("ValidateError" in {alias.name for alias in node.names} for node in imports)
