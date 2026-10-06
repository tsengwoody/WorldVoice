"""Immutable segment identity and explicit completion capability contracts."""

from dataclasses import FrozenInstanceError

import pytest

from runtime_harness import forbid_legacy_runtime_imports, load_runtime


def test_models_load_without_nvda_or_compat(monkeypatch):
	with forbid_legacy_runtime_imports(monkeypatch):
		load_runtime(monkeypatch, "worldvoice_context_pure_test")


def test_playback_context_is_frozen(rt):
	source = object()
	context = rt.models.PlaybackContext(source, 17)
	assert context.source_id is source
	assert context.segment_id == 17
	with pytest.raises(FrozenInstanceError):
		context.segment_id = 18


@pytest.mark.parametrize("minimum,maximum", [(0, 5), (-1, 5), (5, 4)])
def test_index_range_rejects_invalid_bounds(rt, minimum, maximum):
	with pytest.raises(ValueError):
		rt.models.IndexRange(minimum, maximum)


@pytest.mark.parametrize("minimum,maximum", [(1, 1), (1, 502), (502, 503)])
def test_index_range_accepts_inclusive_positive_bounds_and_is_frozen(rt, minimum, maximum):
	index_range = rt.models.IndexRange(minimum, maximum)
	assert (index_range.minimum, index_range.maximum) == (minimum, maximum)
	with pytest.raises(FrozenInstanceError):
		index_range.maximum = maximum + 1


def test_completion_contract_defaults_to_legacy_and_is_frozen(rt):
	contract = rt.models.CompletionContract()
	assert contract.mode is rt.models.CompletionMode.LEGACY_DONE
	assert contract.index_range is None
	with pytest.raises(FrozenInstanceError):
		contract.mode = rt.models.CompletionMode.END_INDEX


@pytest.mark.parametrize("mode", ["END_INDEX", "END_INDEX_AND_DRAIN", "DRAIN"])
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


def test_engine_capabilities_preserve_old_positional_arguments(rt):
	capabilities = rt.models.EngineCapabilities(frozenset({"rate"}), True, True, True)
	assert capabilities.settings == frozenset({"rate"})
	assert capabilities.supports_waitfactor is True
	assert capabilities.supports_variants is True
	assert capabilities.supports_cancellation_token is True
	assert capabilities.completion == rt.models.CompletionContract()
	contract = rt.models.CompletionContract(rt.models.CompletionMode.END_INDEX, rt.models.IndexRange(1, 502))
	assert rt.models.EngineCapabilities(frozenset(), completion=contract).completion is contract


def test_playback_event_preserves_old_positional_arguments(rt):
	source = object()
	event = rt.models.PlaybackEvent(rt.models.EventKind.INDEX, source, 502)
	assert event.source_id is source
	assert event.index == 502
	assert event.segment_id is None
	assert event.error is None
	done = rt.models.PlaybackEvent(rt.models.EventKind.DONE, source)
	assert done.index is None


@pytest.mark.parametrize("kind", ["SEGMENT_END", "SEGMENT_DRAINED", "SEGMENT_FAILED"])
def test_segment_events_carry_identity_and_error(rt, kind):
	source = object()
	error = RuntimeError("playback failed")
	kind = getattr(rt.models.EventKind, kind)
	event = rt.models.PlaybackEvent(kind, source, None, 17, error)
	assert event.kind is kind
	assert event.source_id is source
	assert event.segment_id == 17
	assert event.error is error
	with pytest.raises(FrozenInstanceError):
		event.segment_id = 18
