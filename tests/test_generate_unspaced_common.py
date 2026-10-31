"""tools/generate_unspaced_common.py derives the Common characters that count as unspaced.

The rule (decided by the user, 2026-10-25): a Common character whose General Category is a letter,
number or symbol, and whose Script_Extensions name at least one unspaced script. The General
Category comes from UnicodeData.txt, not from Python's unicodedata, so the tool works for any
Unicode version. Without --source or --unicode-data the tool downloads the file of
--unicode-version from unicode.org; these tests never touch the network: they replace the
downloader or urlopen.
"""

import ast
import hashlib
import urllib.error
from types import SimpleNamespace

import pytest
from addon_loader import ROOT, WORLDVOICE, load_source
from pipeline_harness import load_pipeline_module, punctuation_settings

TOOL = ROOT / "tools" / "generate_unspaced_common.py"


@pytest.fixture(scope="module")
def tool():
	return load_source(None, "generate_unspaced_common", TOOL, register=False)


SOURCE = """\
# ScriptExtensions-16.0.0.txt
# Date: 2024-07-30, 19:38:00 GMT
#
# @missing: 0000..10FFFF; <script>
02C7          ; Bopo Latn                      # Lm      CARON
02CD          ; Latn Lisu                      # Lm      MODIFIER LETTER LOW MACRON
3001..3002    ; Bopo Hang Hani Hira Kana Yiii  # Po   [2] IDEOGRAPHIC COMMA..IDEOGRAPHIC FULL STOP

3220..3229    ; Hani                           # No  [10] PARENTHESIZED IDEOGRAPH ONE..TEN
30FC          ; Hira Kana                      # Lm      KATAKANA-HIRAGANA PROLONGED SOUND MARK
"""


def test_parse_reads_every_code_point_of_each_range(tool):
	extensions = tool.parse_script_extensions(SOURCE.splitlines())
	assert extensions[0x02C7] == {"Bopo", "Latn"}
	assert extensions[0x3001] == extensions[0x3002] == {"Bopo", "Hang", "Hani", "Hira", "Kana", "Yiii"}
	assert set(extensions) == {0x02C7, 0x02CD, 0x3001, 0x3002, *range(0x3220, 0x322A), 0x30FC}


@pytest.mark.parametrize(
	"line",
	[
		"02C7 ; Bopo ; Latn",
		"3002..3001 ; Hani",
		"02C7 ;",
	],
)
def test_parse_rejects_malformed_lines(tool, line):
	with pytest.raises(ValueError, match="line 1"):
		tool.parse_script_extensions([line])


def test_parse_rejects_a_code_point_listed_twice(tool):
	with pytest.raises(ValueError, match="U\\+3002"):
		tool.parse_script_extensions(["3001..3002 ; Hani", "3002 ; Hira"])


def test_parse_version_reads_the_header(tool):
	assert tool.parse_version(SOURCE.splitlines()) == "16.0.0"


def test_parse_version_needs_the_header(tool):
	with pytest.raises(ValueError, match="version"):
		tool.parse_version(["02C7 ; Bopo Latn"])


def test_unspaced_codes_name_the_pipelines_scripts(tool):
	# The pipeline's UNSPACED_SCRIPTS, by ISO 15924 code as ScriptExtensions.txt writes them.
	assert tool.UNSPACED_SCRIPT_CODES == {
		"Hani": "Han",
		"Hira": "Hiragana",
		"Kana": "Katakana",
		"Bopo": "Bopomofo",
		"Thai": "Thai",
		"Laoo": "Lao",
		"Khmr": "Khmer",
		"Mymr": "Myanmar",
	}


def test_unspaced_codes_follow_the_pipeline(tool, monkeypatch):
	pipeline, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	assert set(tool.UNSPACED_SCRIPT_CODES.values()) == pipeline.UNSPACED_SCRIPTS


def test_without_script_data_the_tool_reads_the_committed_one(tool):
	# --script-data defaults to the add-on's own generated file, wherever that file is moved.
	assert tool.SCRIPT_DATA == WORLDVOICE / "unicodeScripts" / "script_data.py"
	assert tool.SCRIPT_DATA.is_file()


def _select(tool, extensions, scripts, categories):
	return tool.select_unspaced_common(extensions, scripts.__getitem__, categories.__getitem__)


def test_select_keeps_common_letters_numbers_and_symbols_with_an_unspaced_script(tool):
	extensions = {
		0x10: {"Bopo", "Latn"},
		0x11: {"Hani"},
		0x12: {"Thai", "Deva"},
		0x13: {"Mymr"},
	}
	scripts = dict.fromkeys(extensions, "Common")
	categories = {0x10: "Lm", 0x11: "No", 0x12: "Sk", 0x13: "So"}
	assert _select(tool, extensions, scripts, categories) == [0x10, 0x11, 0x12, 0x13]


@pytest.mark.parametrize("category", ["Po", "Zs"])
def test_select_drops_other_categories(tool, category):
	assert _select(tool, {0x10: {"Hani"}}, {0x10: "Common"}, {0x10: category}) == []


@pytest.mark.parametrize("script", ["Inherited", None])
def test_select_drops_characters_that_are_not_common(tool, script):
	assert _select(tool, {0x10: {"Hani"}}, {0x10: script}, {0x10: "Lo"}) == []


@pytest.mark.parametrize("extension", [{"Hang", "Yiii"}])
def test_select_drops_characters_without_an_unspaced_script(tool, extension):
	assert _select(tool, {0x10: extension}, {0x10: "Common"}, {0x10: "So"}) == []


def test_select_returns_code_points_in_order(tool):
	extensions = {0x30: {"Hani"}, 0x10: {"Hani"}, 0x20: {"Hani"}}
	scripts = dict.fromkeys(extensions, "Common")
	categories = dict.fromkeys(extensions, "So")
	assert _select(tool, extensions, scripts, categories) == [0x10, 0x20, 0x30]


def test_ranges_join_neighbours_of_one_category(tool):
	categories = {0x10: "So", 0x11: "So", 0x12: "No", 0x14: "No", 0x15: "No"}
	assert tool.to_ranges(sorted(categories), categories.__getitem__) == [
		(0x10, 0x11, "So"),
		(0x12, 0x12, "No"),
		(0x14, 0x15, "No"),
	]


def test_render_module_is_loadable_and_names_its_sources(tool):
	ranges = [(0x02C7, 0x02C7, "Lm"), (0x3220, 0x3229, "No")]
	text = tool.render_module(ranges, "16.0.0", "ab" * 32, "cd" * 32)
	namespace = {}
	exec(compile(text, "generated", "exec"), namespace)  # noqa: S102 - the module the tool writes
	assert namespace["UNICODE_VERSION"] == "16.0.0"
	assert namespace["SOURCE_SHA256"] == "ab" * 32
	assert namespace["UNICODE_DATA_SHA256"] == "cd" * 32
	assert namespace["UNSPACED_COMMON_RANGES"] == ((0x02C7, 0x02C7), (0x3220, 0x3229))
	assert namespace["UNSPACED_COMMON"] == frozenset("ˇ㈠㈡㈢㈣㈤㈥㈦㈧㈨㈩")
	assert text.startswith('"""Generated by tools/generate_unspaced_common.py. Do not edit by hand.')
	assert "\t(0x3220, 0x3229),  # ㈠..㈩ No\n" in text
	assert text.endswith("\n") and not text.endswith("\n\n")


def test_check_versions_needs_one_unicode_version(tool):
	tool.check_versions("16.0.0", requested="16.0.0", script_data="16.0.0")
	with pytest.raises(SystemExit, match="script_data"):
		tool.check_versions("16.0.0", requested="16.0.0", script_data="15.1.0")
	with pytest.raises(SystemExit, match="--unicode-version"):
		tool.check_versions("16.0.0", requested="15.1.0", script_data="16.0.0")


def test_the_tool_does_not_use_pythons_unicodedata(tool):
	# Python's unicodedata is of the Unicode version Python ships, not of --unicode-version.
	tree = ast.parse(TOOL.read_text(encoding="utf-8"))
	imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
	imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
	assert "unicodedata" not in imported
	assert "urllib.request" in imported


# UnicodeData.txt


UNICODE_DATA = "\n".join(
	[
		"02C7;CARON;Lm;0;ON;;;;;N;MODIFIER LETTER HACEK;;;;",
		"02CD;MODIFIER LETTER LOW MACRON;Lm;0;ON;;;;;N;;;;;",
		"3001;IDEOGRAPHIC COMMA;Po;0;ON;;;;;N;;;;;",
		"3002;IDEOGRAPHIC FULL STOP;Po;0;ON;;;;;N;IDEOGRAPHIC PERIOD;;;;",
		"30FC;KATAKANA-HIRAGANA PROLONGED SOUND MARK;Lm;0;L;;;;;N;;;;;",
		*(
			f"{0x3220 + index:04X};PARENTHESIZED IDEOGRAPH {index + 1};No;0;L;;;;{index + 1};N;;;;;"
			for index in range(10)
		),
		"4E00;<CJK Ideograph, First>;Lo;0;L;;;;;N;;;;;",
		"9FFF;<CJK Ideograph, Last>;Lo;0;L;;;;;N;;;;;",
		"",
	],
)


def test_parse_categories_reads_field_two(tool):
	categories = tool.parse_categories(UNICODE_DATA.splitlines())
	assert categories[0x02C7] == "Lm"
	assert categories[0x3001] == "Po"
	assert categories[0x3229] == "No"


def test_parse_categories_fills_first_last_ranges(tool):
	categories = tool.parse_categories(UNICODE_DATA.splitlines())
	assert {code for code, category in categories.items() if category == "Lo"} == set(range(0x4E00, 0xA000))


def test_parse_categories_leaves_unlisted_code_points_out(tool):
	# Unlisted code points are unassigned (Cn); the tool never selects them.
	categories = tool.parse_categories(UNICODE_DATA.splitlines())
	assert 0x02C8 not in categories
	assert 0xA000 not in categories


@pytest.mark.parametrize(
	("lines", "match"),
	[
		(["02C7;CARON;Lm"], "line 1"),
		(["4E00;<CJK Ideograph, First>;Lo;0;L;;;;;N;;;;;"], "First"),
		(["4E00;<CJK Ideograph, First>;Lo;0;L;;;;;N;;;;;", "4E01;CJK X;Lo;0;L;;;;;N;;;;;"], "line 2"),
		(["9FFF;<CJK Ideograph, Last>;Lo;0;L;;;;;N;;;;;"], "line 1"),
		(
			[
				"4E00;<CJK Ideograph, First>;Lo;0;L;;;;;N;;;;;",
				"9FFF;<Tangut Ideograph, Last>;Lo;0;L;;;;;N;;;;;",
			],
			"line 2",
		),
		(
			["4E00;<CJK Ideograph, First>;Lo;0;L;;;;;N;;;;;", "9FFF;<CJK Ideograph, Last>;So;0;L;;;;;N;;;;;"],
			"line 2",
		),
		(
			["9FFF;<CJK Ideograph, First>;Lo;0;L;;;;;N;;;;;", "4E00;<CJK Ideograph, Last>;Lo;0;L;;;;;N;;;;;"],
			"line 2",
		),
		(["02C7;CARON;Lm;0;ON;;;;;N;;;;;", "02C7;CARON;Lm;0;ON;;;;;N;;;;;"], "U\\+02C7"),
	],
)
def test_parse_categories_rejects_malformed_data(tool, lines, match):
	with pytest.raises(ValueError, match=match):
		tool.parse_categories(lines)


# Running the tool


SOURCE_BYTES = SOURCE.encode("utf-8")
SOURCE_SHA256 = hashlib.sha256(SOURCE_BYTES).hexdigest()
UNICODE_DATA_BYTES = UNICODE_DATA.encode("utf-8")
UNICODE_DATA_SHA256 = hashlib.sha256(UNICODE_DATA_BYTES).hexdigest()
# Every code point of SOURCE is Common in this script_data.py.
FAKE_SCRIPT_DATA = """\
UNICODE_VERSION = "16.0.0"
SCRIPT_RANGES = ((0x02C7, 0x02CD, "Common"), (0x3001, 0x3002, "Common"), (0x30FC, 0x30FC, "Common"), (0x3220, 0x3229, "Common"))
SCRIPT_RANGE_STARTS = tuple(start for start, _end, _script in SCRIPT_RANGES)
"""
SCRIPT_EXTENSIONS_URL = "https://www.unicode.org/Public/16.0.0/ucd/ScriptExtensions.txt"
UNICODE_DATA_URL = "https://www.unicode.org/Public/16.0.0/ucd/UnicodeData.txt"


@pytest.fixture
def script_data(tmp_path):
	path = tmp_path / "script_data.py"
	path.write_text(FAKE_SCRIPT_DATA, encoding="utf-8")
	return path


@pytest.fixture
def served(tool, monkeypatch):
	"""Replace the downloader with one serving these files by name; the list collects the URLs."""
	files = {"ScriptExtensions.txt": SOURCE_BYTES, "UnicodeData.txt": UNICODE_DATA_BYTES}
	urls = []

	def download(url, option):
		urls.append(url)
		return files[url.rpartition("/")[2]]

	monkeypatch.setattr(tool, "download", download)
	return SimpleNamespace(files=files, urls=urls)


def _run(
	tool,
	destination,
	script_data,
	*options,
	version="16.0.0",
	sha256=SOURCE_SHA256,
	unicode_data_sha256=UNICODE_DATA_SHA256,
):
	tool.main(
		[
			str(destination),
			"--script-data",
			str(script_data),
			"--unicode-version",
			version,
			"--expected-sha256",
			sha256,
			"--unicode-data-sha256",
			unicode_data_sha256,
			*options,
		],
	)


def _load_generated(path):
	namespace = {}
	exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102 - the module the tool writes
	return namespace


def test_without_files_downloads_both_of_the_version(tool, script_data, served, tmp_path):
	destination = tmp_path / "unspaced_common_data.py"
	_run(tool, destination, script_data)
	assert served.urls == [SCRIPT_EXTENSIONS_URL, UNICODE_DATA_URL]
	generated = _load_generated(destination)
	assert generated["UNICODE_VERSION"] == "16.0.0"
	assert generated["SOURCE_SHA256"] == SOURCE_SHA256
	assert generated["UNICODE_DATA_SHA256"] == UNICODE_DATA_SHA256
	assert generated["UNSPACED_COMMON_RANGES"] == ((0x02C7, 0x02C7), (0x30FC, 0x30FC), (0x3220, 0x3229))
	assert "\t(0x3220, 0x3229),  # ㈠..㈩ No\n" in destination.read_text(encoding="utf-8")


def test_given_files_are_read_and_not_downloaded(tool, script_data, served, tmp_path):
	source = tmp_path / "ScriptExtensions.txt"
	source.write_bytes(SOURCE_BYTES)
	unicode_data = tmp_path / "UnicodeData.txt"
	unicode_data.write_bytes(UNICODE_DATA_BYTES)
	destination = tmp_path / "unspaced_common_data.py"
	_run(tool, destination, script_data, "--source", str(source), "--unicode-data", str(unicode_data))
	assert served.urls == []
	generated = _load_generated(destination)
	assert generated["SOURCE_SHA256"] == SOURCE_SHA256
	assert generated["UNICODE_DATA_SHA256"] == UNICODE_DATA_SHA256


@pytest.mark.parametrize(
	("option", "downloaded"),
	[("--source", [UNICODE_DATA_URL]), ("--unicode-data", [SCRIPT_EXTENSIONS_URL])],
)
def test_each_file_is_downloaded_only_when_not_given(tool, script_data, served, tmp_path, option, downloaded):
	name = "ScriptExtensions.txt" if option == "--source" else "UnicodeData.txt"
	given = tmp_path / name
	given.write_bytes(served.files[name])
	_run(tool, tmp_path / "unspaced_common_data.py", script_data, option, str(given))
	assert served.urls == downloaded


def test_unlisted_code_points_are_never_selected(tool, script_data, served, tmp_path):
	# Without its UnicodeData.txt line ー is unassigned (Cn).
	served.files["UnicodeData.txt"] = UNICODE_DATA.replace(
		"30FC;KATAKANA-HIRAGANA PROLONGED SOUND MARK;Lm;0;L;;;;;N;;;;;\n",
		"",
	).encode("utf-8")
	destination = tmp_path / "unspaced_common_data.py"
	_run(
		tool,
		destination,
		script_data,
		unicode_data_sha256=hashlib.sha256(served.files["UnicodeData.txt"]).hexdigest(),
	)
	assert _load_generated(destination)["UNSPACED_COMMON_RANGES"] == ((0x02C7, 0x02C7), (0x3220, 0x3229))


def test_downloaded_source_must_match_its_checksum(tool, script_data, served, tmp_path):
	destination = tmp_path / "unspaced_common_data.py"
	with pytest.raises(SystemExit, match=f"ScriptExtensions.txt checksum mismatch: actual {SOURCE_SHA256}"):
		_run(tool, destination, script_data, sha256="0" * 64)
	assert not destination.exists()


def test_downloaded_unicode_data_must_match_its_checksum(tool, script_data, served, tmp_path):
	destination = tmp_path / "unspaced_common_data.py"
	with pytest.raises(SystemExit, match=f"UnicodeData.txt checksum mismatch: actual {UNICODE_DATA_SHA256}"):
		_run(tool, destination, script_data, unicode_data_sha256="0" * 64)
	assert not destination.exists()


def test_the_source_must_be_of_the_requested_version(tool, script_data, served, tmp_path):
	# The downloader hands back a 16.0.0 file whatever was asked for.
	destination = tmp_path / "unspaced_common_data.py"
	with pytest.raises(SystemExit, match="--unicode-version is 15.1.0, the source 16.0.0"):
		_run(tool, destination, script_data, version="15.1.0")
	# The mismatch shows before UnicodeData.txt is fetched.
	assert served.urls == ["https://www.unicode.org/Public/15.1.0/ucd/ScriptExtensions.txt"]
	assert not destination.exists()


def test_the_script_data_must_be_of_the_requested_version(tool, script_data, served, tmp_path):
	script_data.write_text(FAKE_SCRIPT_DATA.replace("16.0.0", "15.1.0"), encoding="utf-8")
	destination = tmp_path / "unspaced_common_data.py"
	with pytest.raises(SystemExit, match="script_data"):
		_run(tool, destination, script_data)
	assert not destination.exists()


@pytest.mark.parametrize("missing", ["--unicode-version", "--expected-sha256", "--unicode-data-sha256"])
def test_version_and_checksums_are_required(tool, served, tmp_path, capsys, missing):
	options = {
		"--unicode-version": "16.0.0",
		"--expected-sha256": SOURCE_SHA256,
		"--unicode-data-sha256": UNICODE_DATA_SHA256,
	}
	del options[missing]
	argv = [str(tmp_path / "unspaced_common_data.py"), *(item for pair in options.items() for item in pair)]
	with pytest.raises(SystemExit):
		tool.main(argv)
	assert missing in capsys.readouterr().err
	assert served.urls == []


def test_download_reads_the_response_into_memory(tool, monkeypatch):
	class Response:
		def __enter__(self):
			return self

		def __exit__(self, *exc_info):
			return False

		def read(self):
			return SOURCE_BYTES

	requested = []
	monkeypatch.setattr(tool, "urlopen", lambda url, timeout: requested.append(url) or Response())
	assert tool.download("https://example.invalid/ScriptExtensions.txt", "--source") == SOURCE_BYTES
	assert requested == ["https://example.invalid/ScriptExtensions.txt"]


@pytest.mark.parametrize(
	"error",
	[
		urllib.error.URLError("no route"),
		TimeoutError("timed out"),
	],
)
@pytest.mark.parametrize(
	("name", "option"),
	[("ScriptExtensions.txt", "--source"), ("UnicodeData.txt", "--unicode-data")],
)
def test_network_errors_name_the_url_and_suggest_a_local_file(tool, monkeypatch, error, name, option):
	def urlopen(url, timeout):
		raise error

	monkeypatch.setattr(tool, "urlopen", urlopen)
	url = tool.ucd_url("16.0.0", name)
	with pytest.raises(SystemExit) as raised:
		tool.download(url, option)
	message = str(raised.value.code)
	assert url in message
	assert f"Pass a local copy of {name} with {option} PATH" in message


def test_main_reports_a_download_failure(tool, script_data, monkeypatch, tmp_path):
	def urlopen(url, timeout):
		raise urllib.error.URLError("no route")

	monkeypatch.setattr(tool, "urlopen", urlopen)
	with pytest.raises(SystemExit, match=SCRIPT_EXTENSIONS_URL):
		_run(tool, tmp_path / "unspaced_common_data.py", script_data)


@pytest.mark.parametrize("make", [lambda path: None], ids=["missing"])
@pytest.mark.parametrize(
	("option", "name"),
	[("--source", "ScriptExtensions.txt"), ("--unicode-data", "UnicodeData.txt")],
)
def test_an_unreadable_local_file_names_the_path_and_option(
	tool,
	script_data,
	served,
	tmp_path,
	make,
	option,
	name,
):
	given = tmp_path / name
	make(given)
	destination = tmp_path / "unspaced_common_data.py"
	with pytest.raises(SystemExit) as raised:
		_run(tool, destination, script_data, option, str(given))
	assert f"Could not read {given} given with {option}" in str(raised.value.code)
	assert not destination.exists()
