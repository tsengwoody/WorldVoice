from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest

from runtime_harness import FakeAdapter, MemoryRepository, make_spec, rt


@pytest.fixture
def store(rt):
    return rt.settings.VoiceSettingsStore(MemoryRepository())


@pytest.fixture
def adapter(rt):
    return FakeAdapter(rt.models.EngineCapabilities(frozenset({"rate", "pitch"})))


@pytest.fixture
def session(rt, adapter, store):
    result = rt.session.EngineSession(adapter, store)
    result.open()
    yield result
    adapter.close_error = None
    result.close()


def test_cached_voice_is_fully_reapplied(session, adapter, store):
    store.ensure(make_spec("Fake:a", "en")).update(rate=72)
    store.ensure(make_spec("Fake:b", "zh_TW")).update(pitch=63)
    for key in ("Fake:a", "Fake:b", "Fake:a"):
        assert session.activate(key) is True
    assert [(spec.name, snap.language, snap.rate, snap.pitch) for spec, snap in adapter.applied] == [
        ("Fake:a", "en", 72, 50), ("Fake:b", "zh_TW", 50, 63), ("Fake:a", "en", 72, 50),
    ]
    assert session.activate("Fake:a") is False
    assert len(adapter.applied) == 3


def test_next_activation_reads_latest_state(session, adapter, store):
    state = store.ensure(make_spec())
    applying = Event()
    finish_apply = Event()

    def block_apply(spec, snapshot):
        applying.set()
        assert finish_apply.wait(2)

    adapter.before_apply = block_apply
    with ThreadPoolExecutor(max_workers=1) as executor:
        activation = executor.submit(session.activate, "Fake:a")
        try:
            assert applying.wait(2)
            state.update(rate=72, pitch=63)
        finally:
            finish_apply.set()
        assert activation.result(timeout=2) is True
    adapter.before_apply = None
    assert session.activate("Fake:a") is True
    assert [(snap.rate, snap.pitch, snap.revision) for _, snap in adapter.applied] == [
        (50, 50, 0), (72, 63, 2),
    ]
    assert session.activate("Fake:a") is False


def test_failed_apply_invalidates_cache(session, adapter, store):
    store.ensure(make_spec("Fake:a"))
    store.ensure(make_spec("Fake:b"))
    session.activate("Fake:a")

    def fail_apply(spec, snapshot):
        raise ValueError("Partially applied")

    adapter.before_apply = fail_apply
    with pytest.raises(ValueError, match="Partially applied"):
        session.activate("Fake:b")
    adapter.before_apply = None
    assert session.activate("Fake:a") is True
    assert [spec.name for spec, _ in adapter.applied] == ["Fake:a", "Fake:b", "Fake:a"]


def test_explicit_invalidation_reapplies_same_revision(session, adapter, store):
    store.ensure(make_spec())
    session.activate("Fake:a")
    session.invalidate()
    assert session.activate("Fake:a") is True
    assert len(adapter.applied) == 2


def test_replace_adapter_changes_source_and_reapplies(session, adapter, store):
    store.ensure(make_spec())
    session.activate("Fake:a")
    source = session.source_id
    replacement = FakeAdapter(adapter.capabilities)
    session.replace_adapter(replacement)
    assert session.source_id is not source
    assert session.source_id is not replacement.notification_source
    assert adapter.close_count == 1
    assert replacement.open_count == 1
    assert session.activate("Fake:a") is True
    assert len(replacement.applied) == 1
    session.close()
    session.close()
    assert (adapter.close_count, replacement.close_count) == (1, 1)


def test_cancel_can_enter_while_speak_blocks(session, adapter):
    speaking = Event()
    finish_speak = Event()
    token = EventToken()
    commands = ("Hello", object())

    def block_speak(commands, token):
        speaking.set()
        assert finish_speak.wait(2)

    adapter.before_speak = block_speak
    with ThreadPoolExecutor(max_workers=2) as executor:
        speech = executor.submit(session.speak, commands, token)
        try:
            assert speaking.wait(2)
            cancellation = executor.submit(session.cancel)
            assert adapter.cancel_entered.wait(1)
            cancellation.result(timeout=1)
            assert not speech.done()
            assert not finish_speak.is_set()
        finally:
            finish_speak.set()
        speech.result(timeout=2)
    assert adapter.cancel_count == 1
    assert adapter.spoken[0][0] is commands
    assert adapter.spoken[0][1] is token


def test_pause_can_enter_while_speak_blocks(session, adapter):
    speaking = Event()
    finish_speak = Event()

    def block_speak(commands, token):
        speaking.set()
        assert finish_speak.wait(2)

    adapter.before_speak = block_speak
    with ThreadPoolExecutor(max_workers=2) as executor:
        speech = executor.submit(session.speak, ("Hello",), EventToken())
        try:
            assert speaking.wait(2)
            executor.submit(session.pause, True).result(timeout=1)
            executor.submit(session.pause, False).result(timeout=1)
            assert adapter.paused == [True, False]
            assert not speech.done()
        finally:
            finish_speak.set()
        speech.result(timeout=2)


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_open_failure_attempts_close(rt, adapter, store, cleanup_fails):
    adapter.open_error = ValueError("Open failed")
    if cleanup_fails:
        adapter.close_error = OSError("Close failed")
    session = rt.session.EngineSession(adapter, store)
    with pytest.raises(ValueError, match="Open failed") as failure:
        session.open()
    if cleanup_fails:
        assert failure.value.__cause__ is adapter.close_error
    session.close()
    assert (adapter.open_count, adapter.close_count) == (1, 1)


def test_close_is_idempotent_even_after_failure(session, adapter):
    adapter.close_error = OSError("Close failed")
    with pytest.raises(OSError, match="Close failed"):
        session.close()
    session.close()
    assert adapter.close_count == 1


def test_open_is_explicit_and_reopen_gets_new_source(rt, adapter, store):
    session = rt.session.EngineSession(adapter, store)
    assert adapter.open_count == 0
    session.close()
    assert adapter.close_count == 0
    session.open()
    source = session.source_id
    session.open()
    assert session.source_id is source
    assert adapter.open_count == 1
    store.ensure(make_spec())
    session.activate("Fake:a")
    session.close()
    session.open()
    assert session.source_id is not source
    assert session.activate("Fake:a") is True
    assert len(adapter.applied) == 2
    session.close()
    assert (adapter.open_count, adapter.close_count) == (2, 2)


def test_capability_and_metadata_queries_do_not_activate(session, adapter, store):
    adapter.voices = (make_spec(),)
    adapter.voice_variants = {"Fake:a": ({"id": "default", "name": "Default"},)}
    assert session.capabilities is adapter.capabilities
    assert session.list_voices() == adapter.voices
    assert session.variants("Fake:a") == ({"id": "default", "name": "Default"},)
    assert adapter.applied == []
    assert store.keys() == ()


class EventToken:
    """Minimal CancellationView: callbacks run once on cancel() and can be removed."""

    def __init__(self):
        self.cancelled = Event()
        self._callbacks = []

    def cancel(self):
        if self.cancelled.is_set():
            return
        self.cancelled.set()
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            callback()

    def is_cancelled(self):
        return self.cancelled.is_set()

    def add_callback(self, callback):
        if self.cancelled.is_set():
            callback()
            return lambda: None
        self._callbacks.append(callback)
        return lambda: callback in self._callbacks and self._callbacks.remove(callback)


@pytest.mark.parametrize("mode", ["LEGACY_DONE", "DRAIN"])
def test_cached_activation_still_speaks_two_distinct_segments(rt, session, adapter, store, mode):
    if mode != "LEGACY_DONE":
        contract = rt.models.CompletionContract(
            getattr(rt.models.CompletionMode, mode), rt.models.IndexRange(1, 9999))
        adapter.capabilities = rt.models.EngineCapabilities(frozenset(), completion=contract)
    store.ensure(make_spec())
    token = EventToken()
    assert session.activate("Fake:a") is True
    session.speak(("one",), token, context=rt.models.PlaybackContext(session.source_id, 1))
    assert session.activate("Fake:a") is False
    session.speak(("two",), token, context=rt.models.PlaybackContext(session.source_id, 2))
    assert len(adapter.applied) == 1
    assert [context.segment_id for context in adapter.contexts] == [1, 2]


@pytest.mark.parametrize("mode", ["LEGACY_DONE", "END_INDEX", "END_INDEX_AND_DRAIN", "DRAIN"])
def test_session_rejects_foreign_context(rt, session, adapter, mode):
    if mode != "LEGACY_DONE":
        contract = rt.models.CompletionContract(
            getattr(rt.models.CompletionMode, mode), rt.models.IndexRange(1, 9999))
        adapter.capabilities = rt.models.EngineCapabilities(frozenset(), completion=contract)
    with pytest.raises(ValueError, match="source"):
        session.speak(("hello",), EventToken(), context=rt.models.PlaybackContext(object(), 1))
    assert adapter.spoken == []


def test_session_completion_and_finish_follow_adapter(rt, session, adapter):
    contract = rt.models.CompletionContract(
        rt.models.CompletionMode.END_INDEX, rt.models.IndexRange(1, 100))
    adapter.capabilities = rt.models.EngineCapabilities(frozenset(), completion=contract)
    assert session.completion is contract
    context = rt.models.PlaybackContext(session.source_id, 1)
    session.finish_segment(context)
    assert adapter.finished == [context]


def test_context_speak_does_not_hold_activation_lock(rt, session, adapter, store):
    store.ensure(make_spec())
    speaking, finish = Event(), Event()

    def block(commands, token):
        speaking.set()
        assert finish.wait(2)

    adapter.before_speak = block
    context = rt.models.PlaybackContext(session.source_id, 1)
    with ThreadPoolExecutor(max_workers=2) as executor:
        speech = executor.submit(session.speak, ("hello",), EventToken(), context=context)
        try:
            assert speaking.wait(1)
            assert executor.submit(session.activate, "Fake:a").result(timeout=1) is True
            executor.submit(session.cancel).result(timeout=1)
            executor.submit(session.pause, True).result(timeout=1)
            assert not speech.done()
        finally:
            finish.set()
        speech.result(timeout=2)
    assert adapter.contexts == [context]
    assert adapter.cancel_count == 1
    assert adapter.paused == [True]


@pytest.mark.parametrize("mode", ["END_INDEX", "END_INDEX_AND_DRAIN", "DRAIN"])
def test_correlated_session_requires_context(rt, session, adapter, mode):
    contract = rt.models.CompletionContract(
        getattr(rt.models.CompletionMode, mode), rt.models.IndexRange(1, 9999))
    adapter.capabilities = rt.models.EngineCapabilities(frozenset(), completion=contract)
    with pytest.raises(ValueError, match="context"):
        session.speak(("hello",), EventToken())
    assert adapter.spoken == []


def test_drain_session_passes_original_context_commands_and_token(rt, session, adapter):
    contract = rt.models.CompletionContract(
        rt.models.CompletionMode.DRAIN, rt.models.IndexRange(1, 9999))
    adapter.capabilities = rt.models.EngineCapabilities(frozenset(), completion=contract)
    context = rt.models.PlaybackContext(session.source_id, 17)
    commands, token = ("hello",), EventToken()
    session.speak(commands, token, context=context)
    assert adapter.contexts[0] is context
    assert adapter.spoken[0][0] is commands
    assert adapter.spoken[0][1] is token


def test_session_rejects_finishing_foreign_context(rt, session, adapter):
    with pytest.raises(ValueError, match="source"):
        session.finish_segment(rt.models.PlaybackContext(object(), 1))
    assert adapter.finished == []


def test_speak_rejects_a_token_without_cancellation_callbacks(session, adapter):
    token = SimpleNamespace(is_cancelled=lambda: False)
    with pytest.raises(TypeError, match="add_callback"):
        session.speak(("hello",), token)
    assert adapter.spoken == []
