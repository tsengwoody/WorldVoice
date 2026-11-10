"""Translator comments must sit directly above a gettext call (NVDA codingStandards.md).

The zh_TW catalog must translate exactly the source strings: every one, and nothing else.
"""

import ast
import re
from pathlib import Path

ADDON = Path(__file__).resolve().parents[1] / "addon"
# Same exclusions as pyproject.toml and .pre-commit-config.yaml.
EXCLUDED = re.compile(r"^synthDrivers/WorldVoice/(driver/[^/]+/driver/|unicodeScripts/script_data\.py$)")
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


ZH_TW_CATALOG = ADDON / "locale/zh_TW/LC_MESSAGES/nvda.po"


def _catalog(path):
	"""msgid -> msgstr of the catalog's active entries (obsolete #~ entries and the header left out).

	A fuzzy entry's msgstr reads as "": msgfmt leaves fuzzy translations out, so NVDA would show it in
	English.
	"""
	entries, field, parts, fuzzy = {}, None, {"msgid": [], "msgstr": []}, False
	for line in [*path.read_text(encoding="utf-8").splitlines(), ""]:
		if line.startswith("#,") and "fuzzy" in line:
			fuzzy = True
		elif line.startswith(("msgid ", "msgstr ")):
			field, text = line.split(" ", 1)
			parts[field] = [text]
		elif line.startswith('"') and field is not None:
			parts[field].append(line)
		elif not line.strip() and field is not None:
			msgid = "".join(eval(part) for part in parts["msgid"])
			if msgid:
				entries[msgid] = "" if fuzzy else "".join(eval(part) for part in parts["msgstr"])
			field, parts, fuzzy = None, {"msgid": [], "msgstr": []}, False
	return entries


GETTEXT_NAMES = {"_", "pgettext", "ngettext", "npgettext"}


def _translated_modules():
	"""(relative path, path, tree) of each add-on module with a gettext call."""
	for path in sorted(ADDON.rglob("*.py")):
		relative = path.relative_to(ADDON).as_posix()
		if EXCLUDED.search(relative):
			continue
		tree = ast.parse(path.read_text(encoding="utf-8"))
		if any(
			isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in GETTEXT_NAMES
			for node in ast.walk(tree)
		):
			yield relative, path, tree


def test_every_translated_module_installs_the_add_on_catalog():
	# initTranslation() sets _ in the calling module only, so a module split off another needs its own.
	# Without it, _ is NVDA's own catalog, which has none of the add-on's strings: NVDA shows them in
	# English.
	missing = [
		relative
		for relative, _path, tree in _translated_modules()
		if "addonHandler.initTranslation()" not in {ast.unparse(node) for node in tree.body}
	]
	assert missing == []


def test_every_translated_module_is_a_pot_source():
	# buildVars.pythonSources is what scons pot hands to xgettext; a module it misses drops out of
	# the catalog template.
	root = ADDON.parent
	tree = ast.parse((root / "buildVars.py").read_text(encoding="utf-8"))
	(sources,) = [
		node.value
		for node in tree.body
		if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "pythonSources"
	]
	covered = {path for pattern in ast.literal_eval(sources) for path in root.glob(pattern)}
	assert [relative for relative, path, _tree in _translated_modules() if path not in covered] == []


def _source_msgids():
	"""(msgid -> its call locations, unsupported call locations) of every string scons pot extracts.

	The sources are the add-on modules with a gettext call and buildVars.py, whose summary,
	description and changelog are in the catalog too (buildVars.i18nSources). Only _("literal") is
	read; any other gettext call is unsupported, because _catalog reads neither msgctxt nor plurals.
	"""
	build_vars = ast.parse((ADDON.parent / "buildVars.py").read_text(encoding="utf-8"))
	sources = [(relative, tree) for relative, _path, tree in _translated_modules()]
	source, unsupported = {}, []
	for relative, tree in [*sources, ("buildVars.py", build_vars)]:
		for node in ast.walk(tree):
			if not (
				isinstance(node, ast.Call)
				and isinstance(node.func, ast.Name)
				and node.func.id in GETTEXT_NAMES
			):
				continue
			location = f"{relative}:{node.lineno}"
			(literal,) = node.args if len(node.args) == 1 else (None,)
			if (
				node.func.id == "_"
				and not node.keywords
				and isinstance(literal, ast.Constant)
				and isinstance(literal.value, str)
			):
				source.setdefault(literal.value, []).append(location)
			else:
				unsupported.append(location)
	return source, unsupported


def test_every_source_msgid_has_a_zh_tw_translation():
	source, unsupported = _source_msgids()
	catalog = _catalog(ZH_TW_CATALOG)
	assert unsupported == []
	assert {msgid: locations for msgid, locations in source.items() if not catalog.get(msgid)} == {}


def test_the_zh_tw_catalog_has_no_unused_entry():
	source, _unsupported = _source_msgids()
	assert sorted(set(_catalog(ZH_TW_CATALOG)) - set(source)) == []
