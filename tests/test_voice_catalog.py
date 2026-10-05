"""VoiceCatalog: the immutable view of published voices."""

import dataclasses
import importlib
import sys
from collections import OrderedDict, namedtuple
from pathlib import Path

import pytest

WORLDVOICE = Path(__file__).resolve().parents[1] / "addon" / "synthDrivers" / "WorldVoice"
PACKAGE = "catalog_test_worldvoice"
VoiceInfo = namedtuple("VoiceInfo", "id displayName language")


@pytest.fixture
def descriptions():
	return {}


@pytest.fixture
def catalog_module(stub_modules, descriptions, monkeypatch):
	for name in tuple(sys.modules):
		if name.startswith(PACKAGE + "."):
			monkeypatch.delitem(sys.modules, name)
	stub_modules.package(PACKAGE, WORLDVOICE)
	stub_modules.module("languageHandler", getLanguageDescription=descriptions.get)
	stub_modules.module("synthDriverHandler", VoiceInfo=VoiceInfo)
	return importlib.import_module(PACKAGE + ".voiceCatalog")


@pytest.fixture
def spec():
	models = importlib.import_module(PACKAGE + ".runtime.models")

	def make(id, name, engine, language):
		return models.VoiceSpec(id=id, name=name, description=name, language=language, engine=engine, locale=language)

	return make


def test_catalog_sorts_by_engine_language_name_and_last_duplicate_wins(catalog_module, spec):
	replacement = spec("x", "B:x", "B", "fr")
	catalog = catalog_module.VoiceCatalog.from_specs(
		[spec("y", "A:y", "A", "en_US"), spec("x", "B:x", "B", "de"), replacement],
	)
	assert [v.name for v in catalog.table] == ["A:y", "B:x"]
	assert catalog.by_name["B:x"] is replacement
	assert list(catalog.voice_infos) == ["A:y", "B:x"]
	assert isinstance(catalog.voice_infos, OrderedDict)
	assert catalog.voice_infos["B:x"] == VoiceInfo("B:x", "B:x", "fr")
	assert catalog.all_languages == ("en", "fr")


def test_catalog_is_immutable(catalog_module, spec):
	catalog = catalog_module.VoiceCatalog.from_specs([spec("y", "A:y", "A", "en")])
	with pytest.raises(dataclasses.FrozenInstanceError):
		catalog.table = ()
	with pytest.raises(TypeError):
		catalog.by_name["z"] = None


def test_empty_catalog_has_no_voices(catalog_module):
	empty = catalog_module.EMPTY_CATALOG
	assert (empty.table, dict(empty.by_name), list(empty.voice_infos), empty.all_languages) == ((), {}, [], ())


def test_group_by_primary_locale(catalog_module, spec):
	specs = [spec("a", "A:a", "A", "en_US"), spec("b", "A:b", "A", "en_GB"), spec("c", "A:c", "A", "fr")]
	assert catalog_module.group_by_primary_locale(specs) == {"en": ["A:a", "A:b"], "fr": ["A:c"]}


def test_readable_name(catalog_module, descriptions):
	descriptions["en"] = "English"
	assert catalog_module.EMPTY_CATALOG.readable_name("en") == "English - en"
	assert catalog_module.EMPTY_CATALOG.readable_name("xx") == "xx"
