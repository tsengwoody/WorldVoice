"""The driver settings, the settings ring and both settings panels follow the pipeline table's order."""

import types

from pipeline_harness import load_synth

STANDARD = ["voice", "variant", "rate", "rateBoost", "pitch", "inflection", "volume", "uwv"]
TABLE_DRIVER_IDS = [
	"globalwaitfactor",
	"cni",
	"numlan",
	"nummod",
	"groupwaitfactor",
	"numberwaitfactor",
	"itemwaitfactor",
	"sayallwaitfactor",
	"chinesespacewaitfactor",
	"punctuationpauseenabled",
	"removepunctuationcharacters",
	"punctuationwaitfactor",
]


def synth_and_table(monkeypatch):
	synth_class, settings_module = load_synth(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	synth = object.__new__(synth_class)
	synth._voiceManager = types.SimpleNamespace(
		defaultVoiceName="v",
		getVoiceCapabilities=lambda name: types.SimpleNamespace(settings=frozenset()),
	)
	return synth, settings_module.PIPELINE_SETTINGS


def test_driver_settings_follow_the_table(monkeypatch):
	synth, table = synth_and_table(monkeypatch)
	ids = [setting.id for setting in synth.allSupportedSettings]
	assert ids[: len(STANDARD)] == STANDARD
	assert ids[len(STANDARD) :] == [
		spec.driver_id for spec in table if spec.driver_id and "voice" in spec.panels
	]
	assert ids[len(STANDARD) :] == TABLE_DRIVER_IDS


def test_ring_follows_the_table_after_the_standard_settings(monkeypatch):
	# NVDA's ring lists supportedSettings in order, skipping availableInSettingsRing=False.
	synth, _table = synth_and_table(monkeypatch)
	ring = [
		setting.id for setting in synth.supportedSettings if setting.options.get("availableInSettingsRing")
	]
	assert ring == ["uwv", *(id for id in TABLE_DRIVER_IDS if id != "cni")]


def test_ring_names_follow_the_label_rule(monkeypatch):
	# Without a displayName NVDA shows the label with its accelerator removed.
	synth, _table = synth_and_table(monkeypatch)
	names = {
		setting.id: setting.options.get("displayName", (setting.label or "").replace("&", ""))
		for setting in synth.supportedSettings
		if setting.id in TABLE_DRIVER_IDS and setting.options.get("availableInSettingsRing")
	}
	assert names == {
		"globalwaitfactor": "Global wait factor",
		"numlan": "Number language",
		"nummod": "Number mode",
		"groupwaitfactor": "Group wait factor",
		"numberwaitfactor": "Number wait factor",
		"itemwaitfactor": "Item wait factor",
		"sayallwaitfactor": "Say all wait factor",
		"chinesespacewaitfactor": "Chinese space wait factor",
		"punctuationpauseenabled": "Punctuation pauses",
		"removepunctuationcharacters": "Remove punctuation at pause points",
		"punctuationwaitfactor": "Punctuation wait factor",
	}
