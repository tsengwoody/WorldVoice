"""Encode only at the playback boundary and retain caller command objects."""

import importlib
from types import SimpleNamespace

import pytest

from runtime_harness import load_index_support, rt
from test_worldvoice_index_command import nvda_commands


@pytest.fixture
def codec_env(monkeypatch, rt, nvda_commands):
    support = load_index_support(monkeypatch, rt, "worldvoice_codec_test")
    contract = rt.models.CompletionContract(
        rt.models.CompletionMode.END_INDEX, rt.models.IndexRange(501, 510))
    ledger = support.ledger.IndexLedger()
    source_id = object()
    ledger.bind(object(), source_id, contract)
    # Import inside tests so missing implementation is a clear red assertion.
    return SimpleNamespace(support=support, ledger=ledger, source_id=source_id,
                           context=rt.models.PlaybackContext(source_id, 1),
                           commands=nvda_commands, models=rt.models)


def encode(env, commands):
    path = env.support.package + ".compat.indexCodec"
    assert importlib.util.find_spec(path) is not None, "Segment codec has not been implemented"
    return importlib.import_module(path).encode_segment(commands, env.context, env.ledger)


def test_codec_appends_one_marker_without_mutating_input(codec_env):
    env = codec_env
    original = env.commands.IndexCommand(123)
    other = object()
    commands = ["hello", original, other]
    encoded = encode(env, commands)
    assert isinstance(encoded, tuple)
    assert encoded is not commands
    assert len(encoded) == 4
    assert encoded[0] is commands[0]
    assert encoded[2] is other
    assert type(encoded[1]) is env.commands.IndexCommand
    assert encoded[1] is not original
    assert encoded[1].index == 501
    assert original.index == 123
    assert commands == ["hello", original, other]
    assert isinstance(encoded[-1], env.support.commands.WorldVoiceIndexCommand)
    assert encoded[-1].index == 502
    assert [event.index for event in env.ledger.receive_index(env.source_id, 502)] == [123, None]


def test_codec_rejects_preexisting_internal_marker(codec_env):
    env = codec_env
    marker = env.support.commands.WorldVoiceIndexCommand(123)
    with pytest.raises(ValueError):
        encode(env, ("hello", marker))
    assert env.ledger.prepare(env.context, ()).end_index == 501


def test_codec_scans_original_indexes_before_prepare(codec_env):
    env = codec_env
    original = env.commands.IndexCommand(123)
    original.index = "invalid"
    with pytest.raises((TypeError, ValueError)):
        encode(env, (original,))
    assert env.ledger.prepare(env.context, ()).end_index == 501


def test_codec_constructor_failure_retires_mapping(codec_env, monkeypatch):
    env = codec_env
    path = env.support.package + ".compat.indexCodec"
    assert importlib.util.find_spec(path) is not None, "Segment codec has not been implemented"
    module = importlib.import_module(path)

    def fail_marker(index):
        raise ValueError("constructor failed")

    monkeypatch.setattr(env.support.commands.WorldVoiceIndexCommand, "__init__",
                        lambda self, index: fail_marker(index))
    with pytest.raises(ValueError, match="constructor failed"):
        module.encode_segment((env.commands.IndexCommand(123),), env.context, env.ledger)
    assert env.ledger.receive_index(env.source_id, 501) == ()
    assert env.ledger.receive_index(env.source_id, 502) == ()
    assert env.ledger.prepare(env.context, ()).end_index == 503
