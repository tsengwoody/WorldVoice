"""One extraction routine serves installation and the Import menu."""

import types
from zipfile import BadZipFile, ZipFile

import pytest
from addon_loader import ADDON, load_definitions
from core_archive_harness import INSTALL, load
from nvda_stubs import StubModules

ARCHIVE = ADDON / "generics/coreArchive.py"
PLUGIN = ADDON / "globalPlugins/WorldVoice/__init__.py"


def make_zip(path, **members):
	with ZipFile(path, "w") as archive:
		for name, data in members.items():
			archive.writestr(name, data)
	return str(path)


def test_extracts_members_and_reports_skipped(tmp_path, monkeypatch):
	logged = []
	module = load(ARCHIVE, "core_archive_under_test", monkeypatch, logged)
	archive = make_zip(tmp_path / "core.zip", **{"Engine/a.txt": "a", "Engine/b.txt": "b"})
	workspace = tmp_path / "ws"
	assert module.extractCoreArchive(archive, str(workspace)) == []
	assert (workspace / "Engine/a.txt").read_text() == "a"
	original = ZipFile.extract

	def locked(self, member, path=None, pwd=None):
		if member.filename.endswith("b.txt"):
			raise PermissionError("in use")
		return original(self, member, path, pwd)

	monkeypatch.setattr(ZipFile, "extract", locked)
	assert module.extractCoreArchive(archive, str(workspace)) == ["Engine/b.txt"]


def test_corrupt_archive_raises_bad_zip(tmp_path, monkeypatch):
	module = load(ARCHIVE, "core_archive_under_test", monkeypatch, [])
	broken = tmp_path / "broken.zip"
	broken.write_bytes(b"not a zip")
	with pytest.raises(BadZipFile):
		module.extractCoreArchive(str(broken), str(tmp_path / "ws"))


@pytest.mark.parametrize("corrupt", [False, True])
def test_install_always_removes_the_archive(tmp_path, monkeypatch, corrupt):
	logged = []
	stubs = StubModules(monkeypatch)
	stubs.module("config", conf={})
	stubs.module("globalVars")
	module = load(INSTALL, "install_tasks_under_test", monkeypatch, logged)
	archive = tmp_path / "core.zip"
	if corrupt:
		archive.write_bytes(b"not a zip")
	else:
		make_zip(archive, **{"x.txt": "x"})
	module._extractCoreArchive(str(archive), str(tmp_path / "ws"))
	assert not archive.exists()
	assert any(entry[0] == "error" for entry in logged) is corrupt


def test_menu_import_reports_a_corrupt_archive(monkeypatch, tmp_path):
	broken = tmp_path / "broken.zip"
	broken.write_bytes(b"not a zip")
	shown = []

	class FileDialog:
		def __init__(self, *args, **kwargs):
			pass

		def __enter__(self):
			return self

		def __exit__(self, *args):
			return False

		def ShowModal(self):
			return 1

		def GetPath(self):
			return str(broken)

	environment = {
		"wx": types.SimpleNamespace(FileDialog=FileDialog, ID_OK=1, OK=4, CANCEL=16, ICON_WARNING=0),
		"gui": types.SimpleNamespace(mainFrame=None, messageBox=lambda *args: shown.append(args) or 16),
		"_": lambda text: text,
		"os": __import__("os"),
		"workspace_path": lambda: str(tmp_path / "workspace"),
		"log": types.SimpleNamespace(
			exception=lambda *a: None,
			info=lambda *a: None,
			warning=lambda *a: None,
		),
		"extractCoreArchive": load(
			ARCHIVE,
			"core_archive_for_plugin",
			monkeypatch,
			[],
		).extractCoreArchive,
	}
	load_definitions(PLUGIN, ["GlobalPlugin.onFileImport"], environment)
	environment["onFileImport"](None, None)
	assert shown and shown[0][0] == "Import fail"
