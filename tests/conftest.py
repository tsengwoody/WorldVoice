"""Shared fixtures for every test module."""

import sys

import pytest


@pytest.fixture(autouse=True)
def fresh_completion_rules(monkeypatch):
	"""Bind runtime.completion to the models each test loads.

	Harnesses reload runtime.models per test, often under an alias package. A
	completion module imported by an earlier test would keep that test's enums.
	"""
	for name, module in tuple(sys.modules.items()):
		if (getattr(module, "__file__", None) or "").replace("\\", "/").endswith("runtime/completion.py"):
			monkeypatch.delitem(sys.modules, name)
