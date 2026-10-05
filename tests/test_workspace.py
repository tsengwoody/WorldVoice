"""One source for the WorldVoice-workspace directory."""

import importlib.util
import os
import re
from pathlib import Path
from types import SimpleNamespace

from test_core_archive import INSTALL, load

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "addon/synthDrivers/WorldVoice/workspace.py"
INNER_DRIVER = re.compile(r"synthDrivers/WorldVoice/driver/(sonic|[^/]+/driver)/")


def test_workspace_lives_in_nvdas_config_directory(stub_modules, tmp_path):
	stub_modules.module("globalVars", appArgs=SimpleNamespace(configPath=str(tmp_path)))
	spec = importlib.util.spec_from_file_location("workspace_under_test", WORKSPACE)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	assert module.workspace_path() == os.path.join(str(tmp_path), "WorldVoice-workspace")


def test_install_tasks_load_the_same_module_by_path(stub_modules, monkeypatch, tmp_path):
	stub_modules.module("config", conf={})
	stub_modules.module("globalVars", appArgs=SimpleNamespace(configPath=str(tmp_path)))
	module = load(INSTALL, "install_tasks_workspace_test", monkeypatch, [])
	assert module._workspace_path() == os.path.join(str(tmp_path), "WorldVoice-workspace")


def test_workspace_directory_name_has_one_home():
	homes = [
		path.relative_to(ROOT).as_posix()
		for path in (ROOT / "addon").rglob("*.py")
		# The vendored engine drivers are never edited; they keep their own copies.
		if not INNER_DRIVER.search(path.relative_to(ROOT).as_posix())
		and '"WorldVoice-workspace"' in path.read_text(encoding="utf-8")
	]
	assert homes == ["addon/synthDrivers/WorldVoice/workspace.py"]
