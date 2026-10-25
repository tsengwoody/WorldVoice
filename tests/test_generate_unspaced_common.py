"""tools/generate_unspaced_common.py derives the Common characters that count as unspaced.

The rule (decided by the user, 2026-10-25): a Common character whose General Category is a letter,
number or symbol, and whose Script_Extensions name at least one unspaced script.
"""

import pytest
from addon_loader import ROOT, load_source
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
		"02C7",
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


@pytest.mark.parametrize("category", ["Po", "Ps", "Pd", "Zs", "Cf", "Mn", "Cn"])
def test_select_drops_other_categories(tool, category):
	assert _select(tool, {0x10: {"Hani"}}, {0x10: "Common"}, {0x10: category}) == []


@pytest.mark.parametrize("script", ["Inherited", "Latin", "Han", None])
def test_select_drops_characters_that_are_not_common(tool, script):
	assert _select(tool, {0x10: {"Hani"}}, {0x10: script}, {0x10: "Lo"}) == []


@pytest.mark.parametrize("extension", [{"Latn"}, {"Hang", "Yiii"}, {"Zyyy"}])
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


def test_render_module_is_loadable_and_names_its_source(tool):
	ranges = [(0x02C7, 0x02C7, "Lm"), (0x3220, 0x3229, "No")]
	text = tool.render_module(ranges, "16.0.0", "ab" * 32)
	namespace = {}
	exec(compile(text, "generated", "exec"), namespace)  # noqa: S102 - the module the tool writes
	assert namespace["UNICODE_VERSION"] == "16.0.0"
	assert namespace["SOURCE_SHA256"] == "ab" * 32
	assert namespace["UNSPACED_COMMON_RANGES"] == ((0x02C7, 0x02C7), (0x3220, 0x3229))
	assert namespace["UNSPACED_COMMON"] == frozenset("ˇ㈠㈡㈢㈣㈤㈥㈦㈧㈨㈩")
	assert text.startswith('"""Generated by tools/generate_unspaced_common.py. Do not edit by hand.')
	assert "\t(0x3220, 0x3229),  # ㈠..㈩ No\n" in text
	assert text.endswith("\n") and not text.endswith("\n\n")


def test_check_versions_needs_one_unicode_version(tool):
	tool.check_versions("16.0.0", script_data="16.0.0", unicodedata_version="16.0.0")
	with pytest.raises(SystemExit, match="unicodedata"):
		tool.check_versions("16.0.0", script_data="16.0.0", unicodedata_version="15.1.0")
	with pytest.raises(SystemExit, match="script_data"):
		tool.check_versions("16.0.0", script_data="15.1.0", unicodedata_version="16.0.0")
