"""The stored number language and the one speech uses (phase 35 spec §7.1; review M2)."""

from types import SimpleNamespace

import pytest
from worldvoice_harness import number_language_choice_class


@pytest.fixture
def manager():
	# Offered: the voices the settings show now; all: every installed voice's locale.
	return SimpleNamespace(languages=("en", "zh_TW"), all_languages=("en", "zh_TW", "ja"))


@pytest.fixture
def choice(manager):
	return number_language_choice_class()(manager)


def test_a_new_choice_follows_the_text(choice):
	assert choice.stored == choice.spoken == "default"
	assert choice.listed_locales() == ["en", "zh_TW"]


@pytest.mark.parametrize("value", ["default", "main", "en", "ja"])
def test_storable_values(choice, value):
	assert choice.is_storable(value)
	assert choice.store(value) is True
	assert choice.stored == value


@pytest.mark.parametrize("value", ["zz", "fr"])
def test_a_refused_value_stores_follow(choice, value):
	choice.store("en")
	assert not choice.is_storable(value)
	assert choice.store(value) is False
	assert choice.stored == "default"


def test_a_hidden_locale_is_kept_and_listed_last(choice):
	# An installed voice speaks ja, but no offered one: the choice stays, speech follows the text.
	choice.store("ja")
	assert choice.stored == "ja"
	assert choice.spoken == "default"
	assert choice.listed_locales() == ["en", "zh_TW", "ja"]


def test_a_stored_locale_no_longer_installed_reads_as_follow(choice, manager):
	choice.store("zh_TW")
	manager.all_languages = manager.languages = ("en",)
	assert choice.stored == "default"
	assert choice.spoken == "default"
	assert choice.listed_locales() == ["en"]


def test_the_choice_reads_the_manager_each_time(choice, manager):
	choice.store("ja")
	manager.languages = ("en", "ja")
	assert choice.spoken == "ja"
	assert choice.listed_locales() == ["en", "ja"]
