from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from threading import Event

import pytest

from runtime_harness import make_spec, rt


def test_pending_state_is_atomic_and_snapshot_is_immutable(rt):
    state = rt.settings.VoiceState(make_spec(), {})
    before = state.snapshot()
    state.update(rate=72, pitch=63)
    assert (before.rate, before.pitch, before.revision) == (50, 50, 0)
    assert (state.snapshot().rate, state.snapshot().pitch) == (72, 63)
    assert state.snapshot().revision == 2
    with pytest.raises(FrozenInstanceError):
        before.rate = 12
    state.rollback()
    assert state.get("rate") == 50
    assert state.snapshot().revision == 4


def test_initial_values_are_copied_and_supply_the_rollback_baseline(rt):
    values = {"rate": 62, "variant": "fast", "waitfactor": 2}
    state = rt.settings.VoiceState(make_spec(language="zh_TW"), values)
    values["rate"] = 99
    snapshot = state.snapshot()
    assert (snapshot.voice_id, snapshot.language, snapshot.revision) == ("a", "zh_TW", 0)
    assert (snapshot.rate, snapshot.pitch, snapshot.volume, snapshot.inflection) == (62, 50, 50, 50)
    assert (snapshot.variant, snapshot.rateBoost, snapshot.waitfactor) == ("fast", False, 2)
    state.update(rate=72, variant="default", waitfactor=5)
    state.rollback()
    assert (state.get("rate"), state.get("variant"), state.get("waitfactor")) == (62, "fast", 2)


def test_unknown_setting_update_changes_nothing(rt):
    state = rt.settings.VoiceState(make_spec(), {})
    with pytest.raises(ValueError, match="Unknown voice setting"):
        state.update(rate=72, unknown=1)
    assert (state.get("rate"), state.snapshot().revision) == (50, 0)


def test_unknown_initial_setting_is_rejected(rt):
    with pytest.raises(ValueError, match="Unknown voice setting"):
        rt.settings.VoiceState(make_spec(), {"unknown": 1})


def test_same_value_does_not_increase_revision(rt):
    state = rt.settings.VoiceState(make_spec(), {})
    state.update(rate=50, pitch=50, variant="default", rateBoost=False, waitfactor=0)
    state.rollback()
    assert state.snapshot().revision == 0
    state.update(rate=72, pitch=50)
    state.update(rate=72)
    assert state.snapshot().revision == 1


def test_checkpoint_keeps_pending_values_and_revision(rt):
    state = rt.settings.VoiceState(make_spec(), {})
    state.update(rate=72, pitch=63)
    state.checkpoint()
    assert (state.baseline("rate"), state.baseline("pitch"), state.snapshot().revision) == (72, 63, 2)
    state.update(rate=81)
    saved = {"rate": 75}
    state.checkpoint(saved)
    saved["rate"] = 99
    assert (state.get("rate"), state.baseline("rate"), state.snapshot().revision) == (81, 75, 3)
    state.rollback()
    assert (state.get("rate"), state.get("pitch"), state.snapshot().revision) == (75, 63, 4)


def test_unknown_checkpoint_changes_nothing(rt):
    state = rt.settings.VoiceState(make_spec(), {})
    state.update(rate=81)
    with pytest.raises(ValueError, match="Unknown voice setting"):
        state.checkpoint({"rate": 72, "unknown": 1})
    assert (state.baseline("rate"), state.get("rate"), state.snapshot().revision) == (50, 81, 1)


def test_snapshot_never_observes_half_a_batch(rt):
    comparing_pitch = Event()
    finish_update = Event()
    reading = Event()
    read_done = Event()

    class BlockingPitch(int):
        def __ne__(self, other):
            comparing_pitch.set()
            assert finish_update.wait(2)
            return super().__ne__(other)

    state = rt.settings.VoiceState(make_spec(), {"pitch": BlockingPitch(50)})

    def read():
        reading.set()
        snapshot = state.snapshot()
        read_done.set()
        return snapshot

    with ThreadPoolExecutor(max_workers=2) as executor:
        update = executor.submit(state.update, rate=72, pitch=63)
        try:
            assert comparing_pitch.wait(2)
            snapshot = executor.submit(read)
            assert reading.wait(2)
            assert not read_done.wait(0.05)
        finally:
            finish_update.set()
        update.result(timeout=2)
        result = snapshot.result(timeout=2)
    assert (result.rate, result.pitch, result.revision) == (72, 63, 2)


@pytest.mark.parametrize("value, expected", [
    ("False", False), ("false", False), ("True", True),
    ("0", True), ("", True), (False, False), (0, False), (1, True),
])
def test_boolean_preserves_existing_config_conversion(rt, value, expected):
    assert rt.settings.boolean(value) is expected


def test_parameter_definitions_provide_persisted_defaults(rt):
    values = {name: convert(default) for name, convert, default in rt.settings.VOICE_PARAMETERS}
    assert values == {"rate": 50, "pitch": 50, "volume": 50, "variant": "default", "inflection": 50, "rateBoost": False}
    assert rt.settings.VoiceState(make_spec(), values).snapshot().waitfactor == 0


def test_runtime_values_are_immutable_and_preserve_event_source(rt):
    source = object()
    models = rt.models
    values = [
        (make_spec(), "name", "changed"),
        (models.SelectVoice("Fake:a"), "voice_key", "Fake:b"),
        (models.Pause(0.5), "seconds", 1.0),
        (models.EngineCapabilities(frozenset({"rate"})), "supports_variants", True),
        (models.PlaybackEvent(models.EventKind.INDEX, source, 4), "index", 5),
    ]
    for value, name, replacement in values:
        with pytest.raises(FrozenInstanceError):
            setattr(value, name, replacement)
    event = models.PlaybackEvent(models.EventKind.DONE, source)
    assert event.source_id is source
    assert event.index is None
    capabilities = values[3][0]
    assert not capabilities.supports_waitfactor
    assert not capabilities.supports_variants
    assert not capabilities.supports_cancellation_token
