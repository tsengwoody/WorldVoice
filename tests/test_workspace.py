"""One source for the WorldVoice-workspace directory."""

import os
from types import SimpleNamespace

from addon_loader import WORLDVOICE, load_source
from core_archive_harness import INSTALL, load

WORKSPACE = WORLDVOICE / "workspace.py"


def test_workspace_lives_in_nvdas_config_directory(stub_modules, tmp_path):
	stub_modules.module("globalVars", appArgs=SimpleNamespace(configPath=str(tmp_path)))
	module = load_source(None, "workspace_under_test", WORKSPACE, register=False)
	assert module.workspace_path() == os.path.join(str(tmp_path), "WorldVoice-workspace")


def test_install_tasks_load_the_same_module_by_path(stub_modules, monkeypatch, tmp_path):
	stub_modules.module("config", conf={})
	stub_modules.module("globalVars", appArgs=SimpleNamespace(configPath=str(tmp_path)))
	module = load(INSTALL, "install_tasks_workspace_test", monkeypatch, [])
	assert module._workspace_path() == os.path.join(str(tmp_path), "WorldVoice-workspace")


def test_install_without_core_files_does_not_load_the_workspace(stub_modules, monkeypatch, tmp_path):
	stub_modules.module("config", conf={"WorldVoice": {}})
	stub_modules.module("globalVars", appArgs=SimpleNamespace(configPath=str(tmp_path)))
	module = load(INSTALL, "install_tasks_no_core_test", monkeypatch, [])

	def unexpected():
		raise AssertionError("the workspace is only needed to extract core files")

	monkeypatch.setattr(module, "_workspace_path", unexpected)
	monkeypatch.setattr(module.os.path, "isdir", lambda path: False)
	module.onInstall()
