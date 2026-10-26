"""The pure-runtime import guard sees through relative imports inside bridge/."""

import importlib
import sys

import pytest
from addon_loader import WORLDVOICE, alias_package
from runtime_harness import forbid_legacy_runtime_imports


@pytest.fixture
def probe_package(monkeypatch, tmp_path):
	"""An alias package with a bridge/ of its own; returns (name, bridge directory)."""
	name = "worldvoice_guard_probe"
	bridge = tmp_path / "bridge"
	bridge.mkdir()
	(bridge / "__init__.py").write_text("", encoding="utf-8")
	(bridge / "voiceFacade.py").write_text("class VoiceFacade:\n\tpass\n", encoding="utf-8")
	alias_package(monkeypatch, name, tmp_path)
	yield name, bridge
	for module in tuple(sys.modules):
		if module.startswith(name + "."):
			del sys.modules[module]


def test_guard_rejects_a_relative_import_of_a_legacy_sibling(monkeypatch, probe_package):
	name, bridge = probe_package
	(bridge / "indexLedger.py").write_text("from .voiceFacade import VoiceFacade\n", encoding="utf-8")
	with forbid_legacy_runtime_imports(monkeypatch), pytest.raises(AssertionError, match="voiceFacade"):
		importlib.import_module(name + ".bridge.indexLedger")


def test_guard_rejects_a_legacy_re_export_in_the_bridge_package(monkeypatch, probe_package):
	name, bridge = probe_package
	(bridge / "__init__.py").write_text("from .voiceFacade import VoiceFacade\n", encoding="utf-8")
	(bridge / "nvdaEvents.py").write_text("", encoding="utf-8")
	with forbid_legacy_runtime_imports(monkeypatch), pytest.raises(AssertionError, match="voiceFacade"):
		importlib.import_module(name + ".bridge.nvdaEvents")


def test_guard_allows_the_ledger_and_the_event_bridge(monkeypatch, rt):
	name = "worldvoice_guard_allowed"
	alias_package(monkeypatch, name, WORLDVOICE)
	for suffix, module in (("", rt.package), (".models", rt.models)):
		monkeypatch.setitem(sys.modules, name + ".runtime" + suffix, module)
	for suffix in ("bridge", "bridge.indexLedger", "bridge.nvdaEvents"):
		monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
	with forbid_legacy_runtime_imports(monkeypatch):
		ledger = importlib.import_module(name + ".bridge.indexLedger")
		events = importlib.import_module(name + ".bridge.nvdaEvents")
	assert ledger.IndexLedger.__name__ == "IndexLedger"
	assert events.NvdaEventBridge.__name__ == "NvdaEventBridge"


@pytest.mark.parametrize("package", ["bridge", "voices", "ui", "pipeline"])
def test_package_init_stays_empty(package):
	# Importing one module of the package must not load the others (spec phase 36, section 2);
	# ui/__init__.py runs before ui.panelLayout, which loads without wx (spec phase 37, 2.1), and
	# pipeline/__init__.py before pipeline.numbers, which loads without NVDA (spec phase 38).
	assert (WORLDVOICE / package / "__init__.py").read_bytes() == b""
