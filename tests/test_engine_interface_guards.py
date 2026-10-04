"""Engines declare what they can do; nothing proves it by reflection or shares state on classes."""

from pathlib import Path

ADDON = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"


def test_completion_policy_reads_declarations_instead_of_reflection():
	text = (ADDON / "compat/completionPolicies.py").read_text(encoding="utf-8")
	for removed in ("import sys", "signature", "sys.modules", "__module__", "FORCE_UNVERIFIED_DRAIN",
					"DRAIN_ENGINES", "_WASAPI_MODE_ENGINES", "def get_segment_drain_support",
					"def get_completion_contract", "def resolve_audio_mode"):
		assert removed not in text, removed
	assert "class CompletionPolicy" in text


def test_driver_selects_completion_through_its_policy():
	text = (ADDON / "__init__.py").read_text(encoding="utf-8")
	assert "from .compat.completionPolicies import CompletionPolicy\n" in text
	for removed in ("DRAIN_ENGINES", "get_completion_contract", "get_segment_drain_support", "resolve_audio_mode"):
		assert removed not in text, removed
