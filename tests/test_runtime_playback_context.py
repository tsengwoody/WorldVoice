"""Immutable segment identity and explicit completion capability contracts."""

from dataclasses import FrozenInstanceError

import pytest
from runtime_harness import forbid_legacy_runtime_imports, load_runtime


def test_models_load_without_nvda_or_bridge(monkeypatch):
	with forbid_legacy_runtime_imports(monkeypatch):
		load_runtime(monkeypatch, "worldvoice_context_pure_test")


@pytest.mark.parametrize("minimum,maximum", [(0, 5), (5, 4)])
def test_index_range_rejects_invalid_bounds(rt, minimum, maximum):
	with pytest.raises(ValueError):
		rt.models.IndexRange(minimum, maximum)


@pytest.mark.parametrize("minimum,maximum", [(1, 1)])
def test_index_range_accepts_inclusive_positive_bounds_and_is_frozen(rt, minimum, maximum):
	index_range = rt.models.IndexRange(minimum, maximum)
	assert (index_range.minimum, index_range.maximum) == (minimum, maximum)
	with pytest.raises(FrozenInstanceError):
		index_range.maximum = maximum + 1


@pytest.mark.parametrize("mode", ["END_INDEX"])
def test_correlated_completion_requires_range(rt, mode):
	mode = getattr(rt.models.CompletionMode, mode)
	with pytest.raises(ValueError):
		rt.models.CompletionContract(mode)
	index_range = rt.models.IndexRange(1, 502)
	contract = rt.models.CompletionContract(mode, index_range)
	assert contract.mode is mode
	assert contract.index_range is index_range


def test_legacy_completion_rejects_range(rt):
	with pytest.raises(ValueError):
		rt.models.CompletionContract(rt.models.CompletionMode.LEGACY_DONE, rt.models.IndexRange(1, 502))


# Runtime values cross threads (scheduler, engine callbacks, bridge), so each one is a frozen dataclass.
FROZEN_VALUES = (
	"VoiceSpec",
	"SelectVoice",
	"Pause",
	"PlaybackContext",
	"CompletionContract",
	"EngineCapabilities",
	"PlaybackEvent",
)


def test_runtime_value_classes_are_frozen(rt):
	assert [name for name in FROZEN_VALUES if not getattr(rt.models, name).__dataclass_params__.frozen] == []
