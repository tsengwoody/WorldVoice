"""Loading enabled engine classes, with the same debug timing lines as before."""

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

WORLDVOICE = Path(__file__).resolve().parents[1] / "addon" / "synthDrivers" / "WorldVoice"
PACKAGE = "discovery_test_worldvoice"


@pytest.fixture
def discovery(stub_modules, monkeypatch):
	for name in tuple(sys.modules):
		if name.startswith(PACKAGE + "."):
			monkeypatch.delitem(sys.modules, name)
	stub_modules.package(PACKAGE, WORLDVOICE)
	stub_modules.package(PACKAGE + ".engine", WORLDVOICE / "engine")
	monkeypatch.setattr(sys, "path", list(sys.path))
	return importlib.import_module(PACKAGE + ".engine.discovery")


class Log:
	def __init__(self):
		self.lines = []

	def __getattr__(self, level):
		return lambda message, *args: self.lines.append((level, message % args))


def engine_module(monkeypatch, name, voice):
	module = ModuleType(name)
	if voice is not None:
		module.Voice = voice
	monkeypatch.setitem(sys.modules, name, module)


def spec(discovery, name, module_name, tmp_path, enabled=True):
	return discovery.EngineSpec(name, name, "internal", module_name, str(tmp_path), enabled)


def test_ready_engines_load_in_spec_order_with_timing(discovery, monkeypatch, tmp_path):
	ready = type("Voice", (), {"engine": "B", "ready": classmethod(lambda cls: True)})
	engine_module(monkeypatch, "fake_b", ready)
	engine_module(
		monkeypatch,
		"fake_a",
		type("Voice", (), {"engine": "A", "ready": classmethod(lambda cls: True)}),
	)
	log = Log()
	specs = [
		spec(discovery, "B", "fake_b", tmp_path),
		spec(discovery, "A", "fake_a", tmp_path),
		spec(discovery, "C", "fake_c", tmp_path, enabled=False),
	]
	loaded = discovery.load_enabled_engine_classes(specs, {}, logger=log)
	assert list(loaded) == ["B", "A"] and loaded["B"] is ready
	timings = [message.rsplit(" ", 1)[0] for level, message in log.lines if level == "debug"]
	assert timings[:4] == [
		"WorldVoice init timing: ready check B module import",
		"WorldVoice init timing: ready check B Voice lookup",
		"WorldVoice init timing: ready check B voice.ready",
		"WorldVoice init timing: ready check B total",
	]


def test_failures_are_logged_and_timed(discovery, monkeypatch, tmp_path):
	engine_module(monkeypatch, "fake_missing", None)

	def broken(cls):
		raise RuntimeError("boom")

	engine_module(
		monkeypatch,
		"fake_broken",
		type("Voice", (), {"engine": "Broken", "ready": classmethod(broken)}),
	)
	log = Log()
	specs = [
		spec(discovery, "Missing", "fake_missing", tmp_path),
		spec(discovery, "Broken", "fake_broken", tmp_path),
	]
	assert discovery.load_enabled_engine_classes(specs, {}, logger=log) == {}
	assert ("warning", "Skipping Missing engine candidate: Voice export missing") in log.lines
	assert ("error", "Failed to load ready state for Broken: boom") in log.lines
	timings = [message.rsplit(" ", 1)[0] for level, message in log.lines if level == "debug"]
	assert "WorldVoice init timing: ready check Broken voice.ready" in timings
	assert timings[-1] == "WorldVoice init timing: ready check Broken total"


def test_discovery_without_a_logger_reports_through_stdlib_logging(discovery, tmp_path, caplog):
	root = tmp_path / "internal"
	(root / "Broken").mkdir(parents=True)
	(root / "Broken" / "__init__.py").write_text("", encoding="utf-8")
	(root / "Broken" / "manifest.json").write_text("{", encoding="utf-8")
	with caplog.at_level("WARNING", logger=discovery.__name__):
		assert discovery.discover_engine_specs(root, "pkg.driver", tmp_path / "external") == []
	assert [record.name for record in caplog.records] == [discovery.__name__]
	assert "Skipping Broken engine candidate: invalid manifest" in caplog.records[0].getMessage()
