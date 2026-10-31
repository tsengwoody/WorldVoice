"""The engineRegistry package: the specs found at import, and what the driver and panels ask of them.

The package discovers the add-on's own drivers and the engines in the WorldVoice-workspace
when it is imported. Here the workspace lives in a temporary NVDA config directory and
holds one external engine, so the ready check imports that engine for real and no
internal driver is imported.
"""

import importlib
import sys
from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, alias_package

PACKAGE = "engine_registry_test_worldvoice"
EXTERNAL = "wv_registry_external_engine"
VOICE_SOURCE = """
class Voice:
	engine = "{name}"

	@classmethod
	def ready(cls):
		return True
"""


@pytest.fixture
def engines(stub_modules, monkeypatch, tmp_path):
	for name in tuple(sys.modules):
		if name.startswith(PACKAGE + "."):
			monkeypatch.delitem(sys.modules, name)
	package = tmp_path / "WorldVoice-workspace" / EXTERNAL / EXTERNAL
	package.mkdir(parents=True)
	(package / "__init__.py").write_text(VOICE_SOURCE.format(name=EXTERNAL), encoding="utf-8")
	(package / "manifest.json").write_text('{"label": "External", "defaultEnabled": true}', encoding="utf-8")
	logged = []
	stub_modules.module("addonHandler", initTranslation=lambda: None)
	stub_modules.module(
		"logHandler",
		log=SimpleNamespace(
			debug=lambda *args: None,
			warning=lambda *args: logged.append(("warning", *args)),
			error=lambda *args: logged.append(("error", *args)),
		),
	)
	stub_modules.module("globalVars", appArgs=SimpleNamespace(configPath=str(tmp_path)))
	monkeypatch.setattr(sys, "path", list(sys.path))
	alias_package(monkeypatch, PACKAGE, WORLDVOICE)
	module = importlib.import_module(PACKAGE + ".engineRegistry")
	yield SimpleNamespace(module=module, logged=logged)
	sys.modules.pop(EXTERNAL, None)


def test_import_discovers_the_bundled_drivers_then_the_workspace_engines(engines):
	specs = engines.module.ENGINE_SPECS
	internal = [spec for spec in specs if spec.source == "internal"]
	assert {"Espeak", "OneCore", "RHVoice", "SAPI5"} <= {spec.name for spec in internal}
	assert all(spec.module_name == f"{PACKAGE}.driver.{spec.name}" for spec in internal)
	assert specs[-1].name == EXTERNAL and specs[-1].source == "external"
	assert engines.module.ENGINE_SPEC_INDEX[EXTERNAL] is specs[-1]


def test_ready_engine_classes_loads_only_the_enabled_ready_engines(engines):
	module = engines.module
	# Every bundled driver off: only the workspace engine, on by its manifest, is loaded.
	config = {spec.name: False for spec in module.ENGINE_SPECS if spec.source == "internal"}
	ready = module.ready_engine_classes(config)
	assert list(ready) == [EXTERNAL]
	assert ready[EXTERNAL].__module__ == EXTERNAL
	assert engines.logged == []
	assert module.ready_engine_classes({**config, EXTERNAL: "False"}) == {}


@pytest.mark.parametrize(
	("name", "config", "enabled"),
	[
		# A discovered engine: the config wins, otherwise its manifest default.
		(EXTERNAL, {}, True),
		(EXTERNAL, {EXTERNAL: "False"}, False),
		# An engine nobody discovered is on only when the config says so.
		("Gone", {}, False),
		("Gone", {"Gone": "True"}, True),
		("Gone", {"Gone": "0"}, False),
	],
)
def test_engine_enabled_reads_the_config_then_the_manifest(engines, name, config, enabled):
	assert engines.module.get_engine_enabled(name, config) is enabled


def test_labels_and_defaults_come_from_the_manifest(engines):
	module = engines.module
	assert module.get_engine_label(EXTERNAL) == "External"
	assert module.get_engine_label("RHVoice") == "RHVoice"
	assert module.get_engine_label("Gone") == "Gone"
	assert module.get_engine_default_enabled(EXTERNAL) is True
	assert module.get_engine_default_enabled("RHVoice") is False
	assert module.get_engine_default_enabled("Gone") is False
