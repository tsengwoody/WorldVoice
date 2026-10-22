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
# Labels that are new or changed with the shared, sentence-case labels (2026-10-21).
CHANGED_LABEL_MSGIDS = (
	"Number &mode",
	"Number mode",
	"Number &language",
	"Number language",
	"Item wait factor",
	"Effect scope",
	"Group size",
	"Punctuation pause characters",
	"Apply speech dictionaries",
	"Speech viewer",
)
# msgids no _() call uses any more; the zh_TW catalog keeps none of them.
DEAD_MSGIDS = (
	"Effect Scope:",
	"Number mode:",
	"Group size:",
	"group wait factor:",
	"global wait factor:",
	"number wait factor:",
	"item wait factor:",
	"sayall wait factor:",
	"chinese space wait factor:",
	"punctuation wait factor:",
	"Punctuation pause characters:",
	"Number &Language",
	"Number Language",
	"Number &Mode",
	"Number Mode",
	"Ignore comma between number",
	"Ignore commas between numbers",
	"item wait factor",
	"apply_speech_dictionaries",
	"chinese space wait factor",
	"punctuation wait factor",
	"number wait factor",
	"speech viewer",
)
ZH_TW_CATALOG = ADDON / "locale/zh_TW/LC_MESSAGES/nvda.po"


def _gettext_calls(msgids):
	"""(locations of calls without a translator comment, number of calls found per msgid)."""
	calls = {msgid: re.compile(r"\b_\(" + re.escape(f'"{msgid}"') + r"\)") for msgid in msgids}
	found = dict.fromkeys(msgids, 0)
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
	return missing, found


def test_group_strings_have_translator_comments():
	"""Every _() call for a group-mode string has a # Translators: comment block right above it."""
	missing, found = _gettext_calls(GROUP_MODE_MSGIDS)
	assert missing == []
	assert all(found.values()), found


def test_changed_label_strings_have_translator_comments():
	missing, found = _gettext_calls(CHANGED_LABEL_MSGIDS)
	assert missing == []
	assert all(found.values()), found
	_missing, dead = _gettext_calls(DEAD_MSGIDS)
	assert not any(dead.values()), dead


def _catalog(path):
	"""msgid -> msgstr of the catalog's active entries (obsolete #~ entries and the header left out)."""
	entries, field, parts = {}, None, {"msgid": [], "msgstr": []}
	for line in [*path.read_text(encoding="utf-8").splitlines(), ""]:
		if line.startswith(("msgid ", "msgstr ")):
			field, text = line.split(" ", 1)
			parts[field] = [text]
		elif line.startswith('"') and field is not None:
			parts[field].append(line)
		elif not line.strip() and field is not None:
			msgid = "".join(eval(part) for part in parts["msgid"])
			if msgid:
				entries[msgid] = "".join(eval(part) for part in parts["msgstr"])
			field, parts = None, {"msgid": [], "msgstr": []}
	return entries


def test_zh_tw_catalog_follows_the_labels():
	catalog = _catalog(ZH_TW_CATALOG)
	assert {msgid: catalog.get(msgid, "") for msgid in CHANGED_LABEL_MSGIDS if not catalog.get(msgid)} == {}
	assert [msgid for msgid in DEAD_MSGIDS if msgid in catalog] == []
