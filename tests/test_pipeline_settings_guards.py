"""Pipeline settings have one reader/writer and the retired API stays gone."""

from pathlib import Path
import re

ADDON = Path(__file__).resolve().parents[1] / "addon"
SETTINGS = ADDON / "synthDrivers/WorldVoice/pipeline/settings.py"
RETIRED = [
	"get_effective_pipeline_settings", "_runtime_value", "apply_pipeline_settings_to_synth",
	"apply_pipeline_settings_to_speech_config", "apply_global_pipeline_scope",
	"apply_pipeline_after_worldvoice_end", "clear_global_pipeline_scope", "apply_worldvoice_pipeline",
	"clear_pipeline", "_last_scope_application", "static_register", "dynamic_register",
	"with_speech_sequence_log", "load_pipeline_settings", "save_pipeline_settings",
	"get_ignore_comma_between_number", "get_number_mode", "get_item_wait_factor", "get_number_wait_factor",
	"get_chinesespace_wait_factor", "get_punctuation_wait_factor", "get_punctuation_pause_chars",
	"get_punctuation_pause_enabled", "get_pair_wait_factor",
]


def addon_sources():
	"""Every add-on source except the unmodified vendor drivers."""
	for path in ADDON.rglob("*.py"):
		parts = path.relative_to(ADDON).parts
		if parts[:3] == ("synthDrivers", "WorldVoice", "driver") and (
			parts[3] == "sonic" or len(parts) > 5 and parts[4] == "driver"
		):
			continue
		yield path, path.read_text(encoding="utf-8")


def test_retired_pipeline_api_is_gone():
	found = [
		(str(path), name)
		for path, text in addon_sources()
		for name in RETIRED
		if re.search(rf"\b{re.escape(name)}\b", text)
	]
	assert found == []


def test_only_the_settings_module_touches_the_pipeline_config_section():
	pattern = re.compile(r"\[\s*[\"']pipeline[\"']\s*\]")
	found = [str(path) for path, text in addon_sources() if pattern.search(text) and path != SETTINGS]
	assert found == []
