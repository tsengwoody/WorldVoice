"""Installing core archives: corrupt archives, files in use and failures around them.

onInstall finds the core folder next to installTasks.py and loads coreArchive.py and
workspace.py by path from there. These tests copy those two files into a temporary add-on
folder and point the real installTasks module's __file__ into it.
"""

import shutil
from types import SimpleNamespace
from zipfile import ZIP_STORED, BadZipFile, ZipFile

import pytest
from addon_loader import ADDON
from core_archive_harness import INSTALL, load
from nvda_stubs import StubModules

ARCHIVE = ADDON / "generics/coreArchive.py"


def make_zip(path, **members):
	with ZipFile(path, "w", compression=ZIP_STORED) as archive:
		for name, data in members.items():
			archive.writestr(name, data)
	return path


@pytest.fixture
def archive_module(monkeypatch):
	logged = []
	module = load(ARCHIVE, "core_archive_errors_under_test", monkeypatch, logged)
	return SimpleNamespace(module=module, logged=logged)


def test_an_unreadable_archive_raises_bad_zip_and_extracts_nothing(archive_module, tmp_path, monkeypatch):
	archive = make_zip(tmp_path / "core.zip", **{"a.txt": "a"})
	failure = RuntimeError("File 'a.txt' is encrypted, password required for extraction")

	def encrypted(self):
		raise failure

	monkeypatch.setattr(ZipFile, "testzip", encrypted)
	with pytest.raises(BadZipFile, match="Corrupted archive 'core.zip': File 'a.txt' is encrypted") as raised:
		archive_module.module.extractCoreArchive(str(archive), str(tmp_path / "ws"))
	assert raised.value.__cause__ is failure
	assert not (tmp_path / "ws").exists()


def test_a_member_with_a_bad_checksum_raises_bad_zip_and_extracts_nothing(archive_module, tmp_path):
	archive = make_zip(tmp_path / "core.zip", **{"good.txt": "fine", "bad.txt": "hello world"})
	data = archive.read_bytes()
	archive.write_bytes(data.replace(b"hello world", b"jello world"))
	with pytest.raises(BadZipFile, match="Corrupted archive 'core.zip': bad member bad.txt"):
		archive_module.module.extractCoreArchive(str(archive), str(tmp_path / "ws"))
	assert not (tmp_path / "ws").exists()


def test_any_extraction_error_skips_only_that_file(archive_module, tmp_path, monkeypatch):
	archive = make_zip(tmp_path / "core.zip", **{"a.dll": "a", "b.txt": "b"})
	original = ZipFile.extract

	def sharing_violation(self, member, path=None, pwd=None):
		if member.filename == "a.dll":
			raise OSError(32, "The process cannot access the file")
		return original(self, member, path, pwd)

	monkeypatch.setattr(ZipFile, "extract", sharing_violation)
	assert archive_module.module.extractCoreArchive(str(archive), str(tmp_path / "ws")) == ["a.dll"]
	assert (tmp_path / "ws" / "b.txt").read_text() == "b"
	assert archive_module.logged[-1] == ("warning", "Update complete. Skipped 1 in-use file(s): ['a.dll']")


@pytest.fixture
def install(monkeypatch, tmp_path):
	"""installTasks placed in a temporary add-on folder, with NVDA's config in tmp_path/config."""
	addon = tmp_path / "addon"
	for relative in ("generics/coreArchive.py", "synthDrivers/WorldVoice/workspace.py"):
		(addon / relative).parent.mkdir(parents=True, exist_ok=True)
		shutil.copy(ADDON / relative, addon / relative)
	config_path = tmp_path / "config"
	config_path.mkdir()
	conf = {"WorldVoice": {}, "speech": {"autoLanguageSwitching": True}}
	stubs = StubModules(monkeypatch)
	stubs.module("config", conf=conf)
	stubs.module("globalVars", appArgs=SimpleNamespace(configPath=str(config_path)))
	logged = []
	# The copied coreArchive.py imports this logHandler too.
	module = load(INSTALL, "install_tasks_in_folder_under_test", monkeypatch, logged)
	monkeypatch.setattr(module, "__file__", str(addon / "installTasks.py"))
	return SimpleNamespace(
		module=module,
		conf=conf,
		core=addon / "core",
		workspace=config_path / "WorldVoice-workspace",
		config_path=config_path,
		logged=logged,
	)


def test_first_install_turns_nvdas_automatic_language_switching_off(install):
	del install.conf["WorldVoice"]
	install.module.onInstall()
	assert install.conf["speech"]["autoLanguageSwitching"] is False
	assert not install.workspace.exists()


def test_an_update_keeps_the_users_language_switching(install):
	install.module.onInstall()
	assert install.conf["speech"]["autoLanguageSwitching"] is True


def test_install_extracts_every_core_archive_in_order_and_removes_it(install):
	install.core.mkdir()
	make_zip(install.core / "b.zip", **{"Engine/shared.txt": "from b"})
	make_zip(install.core / "a.zip", **{"Engine/shared.txt": "from a", "Engine/a.txt": "a"})
	(install.core / "readme.txt").write_text("keep", encoding="utf-8")
	install.module.onInstall()
	# a.zip extracts first, so b.zip's copy of a shared file wins.
	assert (install.workspace / "Engine/shared.txt").read_text() == "from b"
	assert (install.workspace / "Engine/a.txt").read_text() == "a"
	assert sorted(path.name for path in install.core.iterdir()) == ["readme.txt"]
	assert not any(entry[0] in ("error", "exception", "warning") for entry in install.logged)


def test_an_empty_core_folder_needs_no_workspace(install):
	install.core.mkdir()
	(install.core / "readme.txt").write_text("keep", encoding="utf-8")
	install.module.onInstall()
	assert not install.workspace.exists()


def test_a_workspace_that_cannot_be_created_keeps_the_archives_for_next_time(install):
	install.core.mkdir()
	make_zip(install.core / "a.zip", **{"a.txt": "a"})
	# A file where the workspace folder should be.
	install.workspace.write_text("", encoding="utf-8")
	install.module.onInstall()
	assert (install.core / "a.zip").exists()
	assert install.logged[-1][0] == "exception"
	assert "preparing" in install.logged[-1][1]


def test_an_unexpected_failure_is_logged_and_the_next_archive_still_installs(install):
	install.core.mkdir()
	# A folder named like an archive: opening it fails, and so does removing it.
	(install.core / "a.zip").mkdir()
	make_zip(install.core / "b.zip", **{"b.txt": "b"})
	install.module.onInstall()
	levels = [entry[0] for entry in install.logged]
	assert "exception" in levels
	assert any(
		entry[0] == "warning" and entry[1].startswith("Could not remove source archive 'a.zip'")
		for entry in install.logged
	)
	assert (install.core / "a.zip").is_dir()
	assert (install.workspace / "b.txt").read_text() == "b"
	assert not (install.core / "b.zip").exists()


def test_install_loads_the_archive_code_from_its_own_folder(install, tmp_path):
	loaded = install.module._loadCoreArchive()
	assert loaded.__file__ == str(tmp_path / "addon" / "generics" / "coreArchive.py")
