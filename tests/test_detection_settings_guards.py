"""The language detection keys have one home, and the settings UI leaves the synth alone."""

from pathlib import Path
import re

ADDON = Path(__file__).resolve().parents[1] / "addon"
SETTINGS = "synthDrivers/WorldVoice/languageDetection/settings.py"
PANELS = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"
DETECTOR = ADDON / "synthDrivers/WorldVoice/languageDetection/__init__.py"
DETECTION_KEY = re.compile(
	r"[\"'](ignoreNumbersInLanguageDetection|latinCharactersLanguage|CJKCharactersLanguage"
	r"|arabicCharactersLanguage|DetectLanguageTiming)[\"']",
)


def addon_sources():
	for path in ADDON.rglob("*.py"):
		parts = path.relative_to(ADDON).parts
		if parts[:3] == ("synthDrivers", "WorldVoice", "driver") and (
			parts[3] == "sonic" or len(parts) > 5 and parts[4] == "driver"
		):
			continue
		yield path, path.read_text(encoding="utf-8")


def test_detection_keys_are_named_only_in_the_settings_module():
	found = {path.relative_to(ADDON).as_posix() for path, text in addon_sources() if DETECTION_KEY.search(text)}
	assert found == {SETTINGS}


def test_the_unicode_panel_neither_refreshes_the_synth_nor_maps_config_keys():
	source = PANELS.read_text(encoding="utf-8")
	assert "refresh_language_detection" not in source
	assert "SCRIPT_CONFIG_KEYS" not in source


def test_the_detector_no_longer_maps_config_keys():
	assert "SCRIPT_CONFIG_KEYS" not in DETECTOR.read_text(encoding="utf-8")
