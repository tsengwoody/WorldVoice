"""The base engine Voice: the metadata and settings an engine gets unless it overrides them."""

import importlib
import sys
from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, alias_package

PACKAGE = "driver_base_test_worldvoice"


@pytest.fixture
def driver(stub_modules, monkeypatch):
	for name in tuple(sys.modules):
		if name.startswith(PACKAGE + "."):
			monkeypatch.delitem(sys.modules, name)
	descriptions = {"en": "English"}
	stub_modules.module("languageHandler", getLanguageDescription=descriptions.get)
	alias_package(monkeypatch, PACKAGE, WORLDVOICE)
	module = importlib.import_module(PACKAGE + ".driver")

	class Voice(module.Voice):
		engine = "Test"

	return Voice


@pytest.mark.parametrize(
	("language", "display_name", "description"),
	[
		("en", "Anna - Deutsch", "English"),
		# Without a description, the part of the display name after " - " names the language.
		("de", "Anna - Deutsch", "Deutsch"),
		("de", "Anna", "de"),
		(None, "Anna", "unknown"),
	],
)
def test_voice_metadata_finds_a_language_description(driver, language, display_name, description):
	metadata = driver.voiceInfoToMetadata(
		SimpleNamespace(id="anna", language=language, displayName=display_name),
	)
	locale = language or "unknown"
	assert metadata == {
		"id": "anna",
		"name": "Test:anna",
		"locale": locale,
		"language": locale,
		"langDescription": description,
		"description": f"{display_name} - {description} [Test]",
		"engine": "Test",
	}


def test_settings_come_from_the_synth_driver_class(driver):
	assert driver.supportedSettings() == []
	driver.synthDriverClass = type(
		"Core",
		(),
		{"supportedSettings": [SimpleNamespace(id="rate"), SimpleNamespace(id="pitch")]},
	)
	assert driver.supportedSettings() == ["rate", "pitch"]


def test_settings_declared_as_an_instance_property_are_not_listed(driver):
	# NVDA's OneCore driver computes supportedSettings in _get_supportedSettings: on the class
	# that is a property, which cannot be iterated.
	driver.synthDriverClass = type("Core", (), {"supportedSettings": property(lambda self: [])})
	assert driver.supportedSettings() == []


def test_an_engine_is_ready_unless_it_says_otherwise(driver):
	assert driver.ready() is True
