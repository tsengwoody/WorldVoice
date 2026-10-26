"""One primary-language helper, shared by the voice roles and the language detector."""

import ast
import re

import pytest
from addon_loader import WORLDVOICE, load_source
from hypothesis import given, strategies as st


@pytest.fixture
def locales(monkeypatch):
	return load_source(monkeypatch, "locales_under_test", WORLDVOICE / "locales.py")


@pytest.mark.parametrize(
	"locale,primary",
	[
		("en_US", "en"),
		("en-US", "en"),
		("zh_TW", "zh"),
		("ar-WW", "ar"),
		("ZH-tw", "zh"),
		("ja", "ja"),
		("sr-Latn-RS", "sr"),
		("zh_Hant_TW", "zh"),
		("", ""),
		(None, None),
	],
)
def test_primary_language_is_the_first_subtag(locales, locale, primary):
	assert locales.primary_language(locale) == primary


@given(st.text(alphabet=st.sampled_from("aZ-_ßİ"), max_size=8))
def test_primary_language_matches_both_former_helpers(locale):
	# roles.getPrimaryLocale and languageDetection.get_primary_language before phase 36.
	module = load_source(None, "locales_under_test", WORLDVOICE / "locales.py", register=False)
	former_roles = re.split(r"[-_]", locale, maxsplit=1)[0].lower() if locale else locale
	former_detection = locale.replace("-", "_").split("_", maxsplit=1)[0].lower()
	assert module.primary_language(locale) == former_roles == former_detection


def test_locales_imports_nothing():
	# The detector and the voice roles both load it; neither may pull the other in.
	tree = ast.parse((WORLDVOICE / "locales.py").read_text(encoding="utf-8"))
	assert not [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]


def test_no_other_module_defines_a_primary_language_helper():
	defined = sorted(
		f"{path.relative_to(WORLDVOICE).as_posix()}:{node.name}"
		for path in WORLDVOICE.rglob("*.py")
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
		if isinstance(node, ast.FunctionDef)
		and node.name in {"primary_language", "getPrimaryLocale", "get_primary_language"}
	)
	assert defined == ["locales.py:primary_language"]
