"""Translator comments must sit directly above a gettext call (NVDA codingStandards.md)."""

import re
from pathlib import Path


ADDON = Path(__file__).resolve().parents[1] / "addon"
# Same exclusions as pyproject.toml and .pre-commit-config.yaml.
EXCLUDED = re.compile(r"^synthDrivers/WorldVoice/(driver/[^/]+/driver/|languageDetection/script_data\.py$)")
GETTEXT_CALL = re.compile(r"\b(_|pgettext|ngettext|npgettext)\(")
# NVDA's multi-line form places the comment inside the call's parentheses.
GETTEXT_OPEN = re.compile(r"\b(_|pgettext|ngettext|npgettext)\($")


def _misplaced_lines(lines):
	"""Return 1-based line numbers of translator comments not followed by a gettext call."""
	misplaced = []
	for number, line in enumerate(lines):
		if not line.lstrip().startswith("# Translators:"):
			continue
		if number > 0 and GETTEXT_OPEN.search(lines[number - 1].rstrip()):
			continue
		following = number + 1
		while following < len(lines) and lines[following].lstrip().startswith("#"):
			following += 1
		if following == len(lines) or not GETTEXT_CALL.search(lines[following]):
			misplaced.append(number + 1)
	return misplaced


def test_scanner_accepts_nvda_multiline_comment_and_rejects_separated_comment():
	nvda_example = [
		"self.copySettingsButton = wx.Button(",
		"	self,",
		"	label=_(",
		"		# Translators: The label for a button in general settings to copy",
		"		# current user settings to system settings.",
		'		"Use currently saved settings during sign-in and on secure screens"',
		"	)",
		")",
		"# Translators: The name of a category of NVDA commands.",
		'SCRCAT_TEXTREVIEW = _("Text review")',
	]
	assert _misplaced_lines(nvda_example) == []
	assert _misplaced_lines(["# Translators: Title.", "gui.mainFrame,", 'message=_("Export")']) == [1]
	assert _misplaced_lines(["# Translators: Dangling at end of file."]) == [1]


def test_translator_comments_precede_gettext_calls():
	misplaced = []
	for path in sorted(ADDON.rglob("*.py")):
		relative = path.relative_to(ADDON).as_posix()
		if EXCLUDED.search(relative):
			continue
		lines = path.read_text(encoding="utf-8").splitlines()
		misplaced.extend(f"{relative}:{number}" for number in _misplaced_lines(lines))
	assert misplaced == []
