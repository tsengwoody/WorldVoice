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


def test_translator_comments_precede_gettext_calls():
	misplaced = []
	for path in sorted(ADDON.rglob("*.py")):
		relative = path.relative_to(ADDON).as_posix()
		if EXCLUDED.search(relative):
			continue
		lines = path.read_text(encoding="utf-8").splitlines()
		misplaced.extend(f"{relative}:{number}" for number in _misplaced_lines(lines))
	assert misplaced == []


GROUP_MODE_MSGIDS = ("group", "Group size", "Group wait factor")


def test_group_strings_have_translator_comments():
	"""Every _() call for a group-mode string has a # Translators: comment block right above it."""
	calls = {msgid: re.compile(r"\b_\(" + re.escape(f'"{msgid}"') + r"\)") for msgid in GROUP_MODE_MSGIDS}
	found = dict.fromkeys(GROUP_MODE_MSGIDS, 0)
	missing = []
	for path in sorted(ADDON.rglob("*.py")):
		relative = path.relative_to(ADDON).as_posix()
		if EXCLUDED.search(relative):
			continue
		lines = path.read_text(encoding="utf-8").splitlines()
		for number, line in enumerate(lines):
			for msgid, call in calls.items():
				if not call.search(line):
					continue
				found[msgid] += 1
				comments = []
				above = number - 1
				while above >= 0 and lines[above].lstrip().startswith("#"):
					comments.append(lines[above].lstrip())
					above -= 1
				if not any(comment.startswith("# Translators:") for comment in comments):
					missing.append(f"{relative}:{number + 1}")
	assert missing == []
	assert all(found.values()), found
