"""The generated Unicode data files are exactly what their generators write.

languageDetection/script_data.py and pipeline/unspaced_common_data.py change only by running
tools/generate_unicode_scripts.py and tools/generate_unspaced_common.py (decided by the user,
2026-10-25). These tests re-render each committed module with its generator's own functions from
the module's own data (ranges, Unicode version and sha256 values) and require the result to be
byte-identical to the file on disk. That catches a hand edit that does not reproduce the generator's
exact output: a range changed without its comment, a range split in two, reformatting, an added
line. A hand edit that does reproduce it, such as another Script name on a range, is left to the
protected-path check in DEVELOPMENT_WORKFLOW.md §7. The tests never touch the network.
"""

import re

import pytest
from addon_loader import ROOT, WORLDVOICE, load_source

SCRIPT_DATA = WORLDVOICE / "languageDetection" / "script_data.py"
UNSPACED_COMMON_DATA = WORLDVOICE / "pipeline" / "unspaced_common_data.py"
# The comment the unspaced Common generator writes after each range: the characters, then the
# General Category it read from UnicodeData.txt.
RANGE_LINE = re.compile(r"^\t\(0x[0-9A-Fa-f]+, 0x[0-9A-Fa-f]+\),[ \t]*#.* (\S+)\r?$", re.MULTILINE)


@pytest.fixture(scope="module")
def scripts_tool():
	return load_source(
		None,
		"generate_unicode_scripts",
		ROOT / "tools" / "generate_unicode_scripts.py",
		register=False,
	)


@pytest.fixture(scope="module")
def unspaced_tool():
	return load_source(
		None,
		"generate_unspaced_common",
		ROOT / "tools" / "generate_unspaced_common.py",
		register=False,
	)


def _rerender_script_data(tool, path):
	"""script_data.py as the generator writes it from the data of the module at path."""
	data = load_source(None, "script_data_under_test", path, register=False)
	# Through the generator's parser, so neighbouring ranges of one script merge as they would.
	lines = [f"{start:04X}..{end:04X} ; {script}" for start, end, script in data.SCRIPT_RANGES]
	return tool.render_module(tool.parse_scripts(lines), data.UNICODE_VERSION, data.SOURCE_SHA256)


def _rerender_unspaced_common_data(tool, path):
	"""unspaced_common_data.py as the generator writes it from the data of the module at path.

	The General Categories are not module data: the generator writes them only in the comment after
	each range, so they are read from there, one per range.
	"""
	data = load_source(None, "unspaced_common_data_under_test", path, register=False)
	text = path.read_bytes().decode("utf-8")
	categories = [match.group(1) for match in RANGE_LINE.finditer(text)]
	assert len(categories) == len(data.UNSPACED_COMMON_RANGES), "a range without its category comment"
	category_by_code = {
		code: category
		for (start, end), category in zip(data.UNSPACED_COMMON_RANGES, categories, strict=True)
		for code in range(start, end + 1)
	}
	return tool.render_module(
		tool.to_ranges(sorted(category_by_code), category_by_code.__getitem__),
		data.UNICODE_VERSION,
		data.SOURCE_SHA256,
		data.UNICODE_DATA_SHA256,
	)


def test_script_data_is_the_generators_output(scripts_tool):
	assert _rerender_script_data(scripts_tool, SCRIPT_DATA) == SCRIPT_DATA.read_bytes().decode("utf-8")


def test_unspaced_common_data_is_the_generators_output(unspaced_tool):
	assert _rerender_unspaced_common_data(unspaced_tool, UNSPACED_COMMON_DATA) == (
		UNSPACED_COMMON_DATA.read_bytes().decode("utf-8")
	)


def _hand_edited(tmp_path, path, old, new):
	text = path.read_bytes().decode("utf-8")
	assert text.count(old) == 1
	copy = tmp_path / path.name
	copy.write_bytes(text.replace(old, new).encode("utf-8"))
	return copy


@pytest.mark.parametrize(
	("old", "new"),
	[
		# A range split in two: the generator merges neighbouring ranges of one script.
		('\t(0x41, 0x5a, "Latin"),\n', '\t(0x41, 0x4f, "Latin"),\n\t(0x50, 0x5a, "Latin"),\n'),
		# Reformatted: the generator writes lower-case hex.
		('\t(0x41, 0x5a, "Latin"),', '\t(0x41, 0x5A, "Latin"),'),
		# An added comment.
		('\t(0x41, 0x5a, "Latin"),', '\t(0x41, 0x5a, "Latin"),  # A..Z'),
		('"""Generated Unicode Script ranges. Do not edit by hand."""', '"""Unicode Script ranges."""'),
		("SCRIPT_RANGE_STARTS = tuple(start for start, _end, _script in SCRIPT_RANGES)\n", ""),
	],
)
def test_a_hand_edit_of_script_data_is_caught(scripts_tool, tmp_path, old, new):
	copy = _hand_edited(tmp_path, SCRIPT_DATA, old, new)
	assert _rerender_script_data(scripts_tool, copy) != copy.read_bytes().decode("utf-8")


@pytest.mark.parametrize(
	("old", "new"),
	[
		# A range widened without its comment.
		("\t(0x2BC, 0x2BC),  # ʼ Lm\n", "\t(0x2BC, 0x2BD),  # ʼ Lm\n"),
		# A comment changed without its range.
		("\t(0x2BC, 0x2BC),  # ʼ Lm\n", "\t(0x2BC, 0x2BC),  # ' Lm\n"),
		# A range split in two: the generator merges neighbouring code points of one category.
		("\t(0x2C9, 0x2CB),  # ˉ..ˋ Lm\n", "\t(0x2C9, 0x2C9),  # ˉ Lm\n\t(0x2CA, 0x2CB),  # ˊ..ˋ Lm\n"),
		# Reformatted: the generator writes upper-case hex and two spaces before the comment.
		("\t(0x2BC, 0x2BC),  # ʼ Lm\n", "\t(0x2bc, 0x2bc),  # ʼ Lm\n"),
		("\t(0x2BC, 0x2BC),  # ʼ Lm\n", "\t(0x2BC, 0x2BC), # ʼ Lm\n"),
	],
)
def test_a_hand_edit_of_unspaced_common_data_is_caught(unspaced_tool, tmp_path, old, new):
	copy = _hand_edited(tmp_path, UNSPACED_COMMON_DATA, old, new)
	assert _rerender_unspaced_common_data(unspaced_tool, copy) != copy.read_bytes().decode("utf-8")


def test_a_range_without_its_category_comment_is_caught(unspaced_tool, tmp_path):
	copy = _hand_edited(tmp_path, UNSPACED_COMMON_DATA, "\t(0x2BC, 0x2BC),  # ʼ Lm\n", "\t(0x2BC, 0x2BC),\n")
	with pytest.raises(AssertionError, match="without its category comment"):
		_rerender_unspaced_common_data(unspaced_tool, copy)


def test_other_line_endings_in_script_data_are_caught(scripts_tool, tmp_path):
	copy = tmp_path / SCRIPT_DATA.name
	copy.write_bytes(SCRIPT_DATA.read_bytes().replace(b"\n", b"\r\n"))
	assert _rerender_script_data(scripts_tool, copy) != copy.read_bytes().decode("utf-8")


def test_other_line_endings_in_unspaced_common_data_are_caught(unspaced_tool, tmp_path):
	copy = tmp_path / UNSPACED_COMMON_DATA.name
	copy.write_bytes(UNSPACED_COMMON_DATA.read_bytes().replace(b"\n", b"\r\n"))
	assert _rerender_unspaced_common_data(unspaced_tool, copy) != copy.read_bytes().decode("utf-8")
