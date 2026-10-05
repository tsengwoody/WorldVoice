"""The driver assembles through the shared helpers instead of flags and hand-written cleanup."""

from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[1] / "addon"

FORBIDDEN = {
	"synthDrivers/WorldVoice/__init__.py": [
		"_startNotified", "_pipelineRegistered", "_pipelineSubscribed", "_voicePanelPatched",
		"_spellingPatched", "_run_cleanup", "OriginVoiceSettingsPanel",
		'hasattr(self, "add_detected_language_commands")', 'getattr(self, "_numlan"',
		'getattr(self, "speechSymbols"', "step_start",
		# Each cleanup is registered once its resource exists, not ahead of it behind None checks.
		"_new_teardown",
	],
}


@pytest.mark.parametrize("path", sorted(FORBIDDEN))
def test_hand_written_assembly_stays_removed(path):
	source = (ADDON / path).read_text(encoding="utf-8")
	assert [name for name in FORBIDDEN[path] if name in source] == []
