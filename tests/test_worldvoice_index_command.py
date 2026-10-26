"""Internal markers retain the NVDA index command boundary contract."""

import pytest
from addon_loader import load_source
from runtime_harness import RUNTIME


@pytest.fixture
def speech_commands(monkeypatch, nvda_commands):
	return load_source(monkeypatch, "worldvoice_index_command_test", RUNTIME.parent / "speechCommands.py")


def test_marker_is_an_index_command(speech_commands, nvda_commands):
	marker = speech_commands.WorldVoiceIndexCommand(502)
	assert isinstance(marker, nvda_commands.IndexCommand)
	assert marker.index == 502
	assert repr(marker) == "WorldVoiceIndexCommand(502)"


def test_marker_rejects_non_integer(speech_commands):
	with pytest.raises(ValueError):
		speech_commands.WorldVoiceIndexCommand("502")
