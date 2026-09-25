import importlib.util
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/driver/engineSession.py"


@pytest.fixture
def module(monkeypatch):
    spec = importlib.util.spec_from_file_location("worldvoice_engine_session_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def snap(module):
    def make_snapshot(id, rev):
        return module.VoiceSnapshot(
            voice_id=id,
            revision=rev,
            language="en",
            rate=50,
            pitch=50,
            volume=50,
            variant="default",
            inflection=50,
            rateBoost=False,
            waitfactor=0,
        )

    return make_snapshot


class FakeCore:
    def __init__(self, supported=("rate", "pitch", "volume")):
        object.__setattr__(self, "writes", [])
        object.__setattr__(self, "fail_on", None)
        object.__setattr__(
            self, "supportedSettings", [SimpleNamespace(id=name) for name in supported]
        )

    def __setattr__(self, name, value):
        if name in {"voice", "rateBoost", "rate", "pitch", "volume", "inflection"}:
            self.writes.append((name, value))
            if name == self.fail_on:
                raise RuntimeError(name)
        object.__setattr__(self, name, value)


@pytest.fixture
def session(module):
    return module.EngineSession(FakeCore())


def test_snapshot_is_immutable(snap):
    snapshot = snap("a", 0)
    with pytest.raises(FrozenInstanceError):
        snapshot.rate = 60


def test_first_activation_writes_supported_settings_in_order(session, snap):
    snapshot = snap("a", 0)
    applied = []

    assert session.activate(snapshot, lambda core, value: applied.append((core, value))) is True
    assert session.core.writes == [
        ("voice", "a"), ("rate", 50), ("pitch", 50), ("volume", 50)
    ]
    assert applied == [(session.core, snapshot)]


def test_same_stamp_skips_setters_and_voice_switch_reapplies(session, snap):
    a = snap("a", 0)
    b = snap("b", 0)
    applied = []
    callback = lambda core, value: applied.append(value.voice_id)

    assert session.activate(a, callback) is True
    before = len(session.core.writes)
    assert session.activate(a, callback) is False
    assert len(session.core.writes) == before
    assert applied == ["a"]
    assert session.activate(b, callback) is True
    assert session.activate(a, callback) is True
    assert applied == ["a", "b", "a"]


def test_revision_change_reapplies_same_voice(session, snap):
    assert session.activate(snap("a", 0), lambda core, value: None) is True
    before = len(session.core.writes)

    assert session.activate(snap("a", 1), lambda core, value: None) is True
    assert len(session.core.writes) > before


def test_replace_core_reapplies_same_snapshot(session, snap):
    snapshot = snap("a", 0)
    assert session.activate(snapshot, lambda core, value: None) is True
    new_core = FakeCore()

    session.replace_core(new_core)

    assert session.activate(snapshot, lambda core, value: None) is True
    assert new_core.writes == [
        ("voice", "a"), ("rate", 50), ("pitch", 50), ("volume", 50)
    ]


def test_partial_failure_invalidates_stamp(session, snap):
    a = snap("a", 0)
    session.activate(a, lambda core, value: None)
    changed = snap("a", 1)

    with pytest.raises(RuntimeError, match="variant"):
        session.activate(changed, lambda core, value: (_ for _ in ()).throw(RuntimeError("variant")))

    assert session.activate(a, lambda core, value: None) is True


def test_setter_failure_invalidates_stamp(session, snap):
    a = snap("a", 0)
    session.activate(a, lambda core, value: None)
    session.core.fail_on = "pitch"

    with pytest.raises(RuntimeError, match="pitch"):
        session.activate(snap("a", 1), lambda core, value: None)

    session.core.fail_on = None
    assert session.activate(a, lambda core, value: None) is True


def test_explicit_invalidate_reapplies_snapshot(session, snap):
    a = snap("a", 0)
    session.activate(a, lambda core, value: None)
    session.invalidate()

    assert session.activate(a, lambda core, value: None) is True
