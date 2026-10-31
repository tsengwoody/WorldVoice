"""tools/generate_unicode_scripts.py turns Unicode's Scripts.txt into unicodeScripts/script_data.py.

Without --source the tool downloads Scripts.txt of --unicode-version from unicode.org (decided by
the user, 2026-10-25). These tests never touch the network: they replace the downloader or urlopen.
"""

import hashlib
import urllib.error

import pytest
from addon_loader import ROOT, load_source

TOOL = ROOT / "tools" / "generate_unicode_scripts.py"

SOURCE = b"""\
# Scripts-16.0.0.txt
# Date: 2024-04-30, 21:48:40 GMT

0000..001F    ; Common # Cc  [32] <control-0000>..<control-001F>
0020          ; Common # Zs       SPACE
0041..005A    ; Latin # L&  [26] LATIN CAPITAL LETTER A..LATIN CAPITAL LETTER Z
4E00..9FFF    ; Han # Lo [20992] CJK UNIFIED IDEOGRAPH-4E00..CJK UNIFIED IDEOGRAPH-9FFF
"""
SOURCE_SHA256 = hashlib.sha256(SOURCE).hexdigest()


@pytest.fixture
def tool():
	return load_source(None, "generate_unicode_scripts", TOOL, register=False)


@pytest.fixture
def downloads(tool, monkeypatch):
	"""Replace the downloader; the list collects the URLs it was asked for."""
	urls = []

	def download(url):
		urls.append(url)
		return SOURCE

	monkeypatch.setattr(tool, "download", download)
	return urls


def _load_generated(path):
	namespace = {}
	exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102 - the module the tool writes
	return namespace


def test_parse_merges_neighbouring_ranges_of_one_script(tool):
	assert tool.parse_scripts(SOURCE.decode().splitlines()) == [
		(0x0000, 0x0020, "Common"),
		(0x0041, 0x005A, "Latin"),
		(0x4E00, 0x9FFF, "Han"),
	]


@pytest.mark.parametrize("line", ["0041 ; Latin ; Greek", "005A..0041 ; Latin"])
def test_parse_rejects_malformed_lines(tool, line):
	with pytest.raises(ValueError, match="line 1"):
		tool.parse_scripts([line])


def test_parse_rejects_overlapping_ranges(tool):
	with pytest.raises(ValueError, match="overlap"):
		tool.parse_scripts(["0041..005A ; Latin", "005A ; Greek"])


def test_render_module_is_loadable_and_names_its_source(tool):
	text = tool.render_module([(0x41, 0x5A, "Latin")], "16.0.0", "ab" * 32)
	namespace = {}
	exec(compile(text, "generated", "exec"), namespace)  # noqa: S102 - the module the tool writes
	assert namespace["UNICODE_VERSION"] == "16.0.0"
	assert namespace["SOURCE_SHA256"] == "ab" * 32
	assert namespace["SCRIPT_RANGES"] == ((0x41, 0x5A, "Latin"),)
	assert namespace["SCRIPT_RANGE_STARTS"] == (0x41,)


def test_without_source_downloads_the_versions_file(tool, downloads, tmp_path):
	destination = tmp_path / "script_data.py"
	tool.main([str(destination), "--unicode-version", "16.0.0", "--expected-sha256", SOURCE_SHA256])
	assert downloads == ["https://www.unicode.org/Public/16.0.0/ucd/Scripts.txt"]
	generated = _load_generated(destination)
	assert generated["UNICODE_VERSION"] == "16.0.0"
	assert generated["SOURCE_SHA256"] == SOURCE_SHA256
	assert generated["SCRIPT_RANGES"][-1] == (0x4E00, 0x9FFF, "Han")


def test_with_source_reads_the_file_and_does_not_download(tool, downloads, tmp_path):
	source = tmp_path / "Scripts.txt"
	source.write_bytes(SOURCE)
	destination = tmp_path / "script_data.py"
	tool.main(
		[
			str(destination),
			"--source",
			str(source),
			"--unicode-version",
			"16.0.0",
			"--expected-sha256",
			SOURCE_SHA256,
		],
	)
	assert downloads == []
	assert _load_generated(destination)["SOURCE_SHA256"] == SOURCE_SHA256


def test_downloaded_bytes_must_match_the_checksum(tool, downloads, tmp_path):
	destination = tmp_path / "script_data.py"
	with pytest.raises(SystemExit, match=SOURCE_SHA256):
		tool.main([str(destination), "--unicode-version", "15.1.0", "--expected-sha256", "0" * 64])
	assert not destination.exists()
	# The URL names the requested version, not a fixed one.
	assert downloads == ["https://www.unicode.org/Public/15.1.0/ucd/Scripts.txt"]


@pytest.mark.parametrize("missing", ["--unicode-version", "--expected-sha256"])
def test_version_and_checksum_are_required(tool, downloads, tmp_path, capsys, missing):
	options = {"--unicode-version": "16.0.0", "--expected-sha256": SOURCE_SHA256}
	del options[missing]
	argv = [str(tmp_path / "script_data.py"), *(item for pair in options.items() for item in pair)]
	with pytest.raises(SystemExit):
		tool.main(argv)
	assert missing in capsys.readouterr().err
	assert downloads == []


def test_download_reads_the_response_into_memory(tool, monkeypatch):
	class Response:
		def __enter__(self):
			return self

		def __exit__(self, *exc_info):
			return False

		def read(self):
			return SOURCE

	requested = []
	monkeypatch.setattr(tool, "urlopen", lambda url, timeout: requested.append(url) or Response())
	assert tool.download("https://example.invalid/Scripts.txt") == SOURCE
	assert requested == ["https://example.invalid/Scripts.txt"]


@pytest.mark.parametrize(
	"error",
	[
		urllib.error.URLError("no route"),
		TimeoutError("timed out"),
	],
)
def test_network_errors_name_the_url_and_suggest_a_local_file(tool, monkeypatch, error):
	def urlopen(url, timeout):
		raise error

	monkeypatch.setattr(tool, "urlopen", urlopen)
	url = tool.source_url("16.0.0")
	with pytest.raises(SystemExit) as raised:
		tool.download(url)
	message = str(raised.value.code)
	assert url in message
	assert "--source" in message


@pytest.mark.parametrize("make", [lambda path: None], ids=["missing"])
def test_an_unreadable_source_names_the_path_and_option(tool, downloads, tmp_path, make):
	source = tmp_path / "Scripts.txt"
	make(source)
	argv = [
		str(tmp_path / "script_data.py"),
		"--source",
		str(source),
		"--unicode-version",
		"16.0.0",
		"--expected-sha256",
		SOURCE_SHA256,
	]
	with pytest.raises(SystemExit) as raised:
		tool.main(argv)
	message = str(raised.value.code)
	assert f"Could not read {source} given with --source" in message
	assert downloads == []
