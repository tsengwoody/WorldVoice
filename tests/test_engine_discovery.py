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


def write_engine(package_dir, manifest=None):
	"""A package directory with an __init__.py and, unless manifest is None, a manifest.json."""
	package_dir.mkdir(parents=True)
	(package_dir / "__init__.py").write_text("", encoding="utf-8")
	if manifest is not None:
		(package_dir / "manifest.json").write_text(manifest, encoding="utf-8")


def test_discovery_reads_internal_then_external_engines_and_their_manifests(discovery, tmp_path):
	internal = tmp_path / "src" / "pkg" / "driver"
	write_engine(internal / "Beta", '{"label": "", "defaultEnabled": "false"}')
	write_engine(internal / "Alpha", '{"label": "Alpha Engine"}')
	write_engine(internal / "NoManifest")
	write_engine(internal / "ListManifest", "[]")
	(internal / "NotPackage").mkdir()
	(internal / "notes.txt").write_text("", encoding="utf-8")
	external = tmp_path / "workspace"
	write_engine(external / "Ext" / "Ext", "{}")
	write_engine(external / "On" / "On", '{"label": "Switched on", "defaultEnabled": true}')
	write_engine(external / "Bare" / "Bare")
	write_engine(external / "Broken" / "Broken", "{")
	(external / "Loose").mkdir()
	(external / "readme.txt").write_text("", encoding="utf-8")
	log = Log()

	specs = discovery.discover_engine_specs(internal, "pkg.driver", external, logger=log)

	src = str(tmp_path / "src")
	assert specs == [
		discovery.EngineSpec("Alpha", "Alpha Engine", "internal", "pkg.driver.Alpha", src, True),
		# An empty label falls back to the name; a string flag is read as a boolean.
		discovery.EngineSpec("Beta", "Beta", "internal", "pkg.driver.Beta", src, False),
		# External engines import from their own folder and are off unless they say otherwise.
		discovery.EngineSpec("Ext", "Ext", "external", "Ext", str(external / "Ext"), False),
		discovery.EngineSpec("On", "Switched on", "external", "On", str(external / "On"), True),
	]
	assert ("debug", "Skipping NoManifest engine candidate: manifest missing") in log.lines
	assert ("debug", "Skipping Bare engine candidate: manifest missing") in log.lines
	assert ("warning", "Skipping ListManifest engine candidate: manifest must be a JSON object") in log.lines
	assert any(
		level == "warning" and message.startswith("Skipping Broken engine candidate: invalid manifest")
		for level, message in log.lines
	)


def test_discovery_without_engine_folders_finds_nothing(discovery, tmp_path):
	assert discovery.discover_engine_specs(tmp_path / "a" / "driver", "a.driver", tmp_path / "missing") == []


@pytest.mark.parametrize(
	("value", "enabled"),
	[(True, True), (False, False), ("True", True), ("false", False), ("0", False), ("", False), (0, False)],
)
def test_a_configured_engine_flag_overrides_the_manifest_default(discovery, tmp_path, value, enabled):
	engine = spec(discovery, "A", "fake_a", tmp_path, enabled=not enabled)
	assert discovery.get_engine_enabled({"A": value}, engine) is enabled
	assert discovery.get_engine_enabled({}, engine) is (not enabled)


@pytest.fixture
def imported():
	"""Names of modules a test imports for real; they leave sys.modules when it ends."""
	names = []
	yield names
	for name in names:
		sys.modules.pop(name, None)


def test_enabled_engines_import_from_their_root_and_must_be_ready_and_named(
	discovery,
	monkeypatch,
	tmp_path,
	imported,
):
	imported.append("wv_discovery_ready_engine")
	package = tmp_path / "root" / "wv_discovery_ready_engine"
	write_engine(package)
	(package / "__init__.py").write_text(
		"class Voice:\n\tengine = 'Ready'\n\n\t@classmethod\n\tdef ready(cls):\n\t\treturn True\n",
		encoding="utf-8",
	)
	engine_module(
		monkeypatch,
		"fake_renamed",
		type("Voice", (), {"engine": "Other", "ready": classmethod(lambda cls: True)}),
	)
	engine_module(
		monkeypatch,
		"fake_unready",
		type("Voice", (), {"engine": "Unready", "ready": classmethod(lambda cls: False)}),
	)
	engine_module(monkeypatch, "fake_off", type("Voice", (), {"ready": classmethod(lambda cls: True)}))
	log = Log()
	root = str(package.parent)
	specs = [
		discovery.EngineSpec("Ready", "Ready", "external", "wv_discovery_ready_engine", root, False),
		spec(discovery, "Renamed", "fake_renamed", tmp_path),
		spec(discovery, "Unready", "fake_unready", tmp_path),
		spec(discovery, "Off", "fake_off", tmp_path),
	]

	loaded = discovery.load_enabled_engine_classes(specs, {"Ready": "True", "Off": False}, logger=log)

	# The external engine is off by default; the config turns it on and its root joins sys.path.
	assert list(loaded) == ["Ready"]
	assert loaded["Ready"].__module__ == "wv_discovery_ready_engine"
	assert root in sys.path
	warnings = [message for level, message in log.lines if level == "warning"]
	assert warnings == ["Skipping Renamed engine candidate: Voice.engine mismatch (Other)"]
	assert any("ready check Unready voice.ready" in message for _, message in log.lines)
	assert not any("ready check Off" in message for _, message in log.lines)
