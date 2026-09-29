"""Correlated drains across the real manager, adapters, bridge and wrappers."""

from concurrent.futures import TimeoutError
from pathlib import Path
import subprocess
import sys
from threading import Event

import pytest

from runtime_drain_integration_harness import ENGINES, assemble
from neural_drain_harness import in_thread


@pytest.fixture
def composition(monkeypatch, tmp_path):
    c = assemble(monkeypatch, tmp_path)
    yield c
    c.close()


@pytest.mark.parametrize("engine", ENGINES)
def test_wrapper_index_precedes_audio_drain_and_request_done(composition, engine):
    c = composition
    request = c.submit(("hello", c.commands.IndexCommand(703)), engine)
    control = c.controls[engine]
    barrier = control.tail()
    assert c.output.indexes == [703]
    assert c.output.drains == []
    assert c.output.dones == []
    assert not request.tasks[0].future.done()
    assert control.player.fed
    barrier.release.set()
    c.wait_done()
    assert request.tasks[0].future.result(timeout=1) is True
    assert [kind for kind, _ in c.output.timeline] == ["index", "drain", "done"]


@pytest.mark.parametrize("engines", [("OneCore", "Neural", "OneCore"), ("VE", "Cerence", "VE")])
def test_next_engine_starts_only_after_segment_drain(composition, engines):
    c = composition
    a, b, _ = engines
    request = c.submit(("first", c.rt.models.Pause(0.001),
        c.rt.models.SelectVoice(c.key(b)), "second",
        c.rt.models.SelectVoice(c.key(a)), "third"), a)
    first, second = c.controls[a], c.controls[b]
    barrier = first.tail()
    assert second.started.wait(0.03) is False
    assert second.calls == []
    assert c.output.dones == []
    barrier.release.set()
    second.wait_call()
    assert len(second.calls) == 1
    barrier = second.tail()
    assert len(first.calls) == 1
    assert c.output.dones == []
    barrier.release.set()
    first.wait_call(2)
    assert len(first.calls) == 2
    first.tail(2).release.set()
    c.wait_done()
    assert request.state is c.scheduler.RequestState.COMPLETED
    assert len(c.output.dones) == 1
    assert len(c.output.drains) == 3


@pytest.mark.parametrize("engine", ENGINES)
def test_cached_voice_still_has_two_segment_drains(composition, engine):
    c = composition
    request = c.submit(("first", c.rt.models.Pause(0.001), "second"), engine)
    control = c.controls[engine]
    first = control.tail()
    assert len(control.calls) == 1
    first.release.set()
    control.wait_call(2)
    second = control.tail(2)
    assert len(control.applied) == 1
    assert len(control.contexts) == 2
    assert control.contexts[0].segment_id != control.contexts[1].segment_id
    assert c.output.dones == []
    second.release.set()
    c.wait_done()
    assert len(c.output.drains) == 2
    assert len(c.output.dones) == 1
    assert request.state is c.scheduler.RequestState.COMPLETED


@pytest.mark.parametrize("engine", ENGINES)
def test_pause_resume_holds_request_after_actual_idle_returns(composition, engine):
    c = composition
    request = c.submit(("paused",), engine)
    control = c.controls[engine]
    barrier = control.tail()
    c.tasks.pause_current(True)
    barrier.release.set()
    assert barrier.returned.wait(1)
    with pytest.raises(TimeoutError):
        request.tasks[0].future.result(timeout=0.03)
    assert c.output.dones == []
    assert c.output.drains == []
    c.tasks.pause_current(False)
    c.wait_done()
    assert request.tasks[0].future.result(timeout=1) is True
    assert len(c.output.dones) == 1


@pytest.mark.parametrize("engine", ENGINES)
def test_cancel_and_stale_sink_cannot_release_new_same_source_segment(composition, engine):
    c = composition
    control = c.controls[engine]
    old = c.submit(("old", c.commands.IndexCommand(11)), engine)
    control.wait_call()
    control.feed_release.clear()
    control.complete_native()
    assert control.feed_entered.wait(1)
    old_context, old_sink = control.contexts[0], control.sinks[0]
    c.tasks.cancel(c.manager.playback_ports)
    fresh = c.submit(("fresh", c.commands.IndexCommand(22)), engine)
    old_sink(c.rt.models.PlaybackEvent(c.rt.models.EventKind.SEGMENT_DRAINED,
        old_context.source_id, segment_id=old_context.segment_id))
    assert len(control.calls) == 1
    assert not fresh.tasks[0].future.done()
    assert c.output.dones == []
    control.feed_release.set()
    control.wait_call(2)
    assert len(control.calls) == 2
    barrier = control.tail(2, idle_number=1)
    # Old context completion and anonymous NVDA DONE cannot satisfy fresh DRAIN.
    old_sink(c.rt.models.PlaybackEvent(c.rt.models.EventKind.SEGMENT_DRAINED,
        old_context.source_id, segment_id=old_context.segment_id))
    c.bridge._done_event.notify(synth=control.core)
    with pytest.raises(TimeoutError):
        fresh.tasks[0].future.result(timeout=0.03)
    assert c.output.indexes == [22]
    assert c.output.dones == []
    barrier.release.set()
    c.wait_done()
    assert old.state is c.scheduler.RequestState.CANCELLED
    assert old.tasks[0].future.cancelled()
    assert fresh.state is c.scheduler.RequestState.COMPLETED
    assert control.contexts[0].source_id is control.contexts[1].source_id
    assert control.contexts[0].segment_id != control.contexts[1].segment_id
    assert len(c.output.dones) == 1


def test_old_sink_is_revoked_across_unbind_rebind(composition):
    c = composition
    control = c.controls["OneCore"]
    old = c.submit(("old",), "OneCore")
    barrier = control.tail()
    context = control.contexts[0]
    old_sink = c.bridge.segment_sink(control.core, context)
    c.tasks.cancel(c.manager.playback_ports)
    c.bridge.unbind(control.session.source_id)
    c.bridge.bind(control.core, control.session.source_id, completion=control.session.completion)
    fresh = c.submit(("fresh",), "OneCore")
    control.wait_call(2)
    current = control.contexts[1]
    # Even a sink captured for the current context becomes invalid on rebinding
    # the identical source/context. This makes generation protection observable.
    revoked = c.bridge.segment_sink(control.core, current)
    c.bridge.unbind(control.session.source_id)
    c.bridge.bind(control.core, control.session.source_id, completion=control.session.completion)
    c.ledger.prepare(current, ())
    old_sink(c.rt.models.PlaybackEvent(c.rt.models.EventKind.SEGMENT_DRAINED,
        context.source_id, segment_id=context.segment_id))
    revoked(c.rt.models.PlaybackEvent(c.rt.models.EventKind.SEGMENT_DRAINED,
        current.source_id, segment_id=current.segment_id))
    with pytest.raises(TimeoutError):
        fresh.tasks[0].future.result(timeout=0.03)
    assert c.output.dones == []
    # The wrapper retains the revoked sink too; install a freshly bound sink at
    # the same actual work boundary to let this deliberately rebound job retire.
    live = c.bridge.segment_sink(control.core, current)
    barrier = control.tail(2, idle_number=2)
    assert not fresh.tasks[0].future.done()
    barrier.release.set()
    assert barrier.returned.wait(1)
    live(c.rt.models.PlaybackEvent(c.rt.models.EventKind.SEGMENT_DRAINED,
        current.source_id, segment_id=current.segment_id))
    c.wait_done()
    assert fresh.state is c.scheduler.RequestState.COMPLETED
    assert old.state is c.scheduler.RequestState.CANCELLED


@pytest.mark.parametrize("engine", ENGINES)
def test_setting_revision_reapplies_without_reusing_segment_context(composition, engine):
    c = composition
    request = c.submit(("first", c.rt.models.Pause(0.001), "second"), engine)
    control = c.controls[engine]
    barrier = control.tail()
    c.store.state(c.key(engine)).update(rate=72, pitch=61, volume=83)
    barrier.release.set()
    control.wait_call(2)
    barrier = control.tail(2)
    assert len(control.applied) == 2
    assert [(s.rate, s.pitch, s.volume) for s in control.applied] == [(50, 50, 50), (72, 61, 83)]
    assert control.contexts[0].segment_id != control.contexts[1].segment_id
    assert not request.tasks[-1].future.done()
    barrier.release.set()
    c.wait_done()
    assert len(c.output.dones) == 1


def test_voice_switch_reapplies_native_settings_and_keeps_distinct_drains(composition):
    c = composition
    a, b = "Neural:voice1", "Neural:voice2"
    c.manager.resolve_playback(b)
    c.store.state(b).update(rate=31)
    request = c.submit(("english", c.rt.models.SelectVoice(b), "french",
        c.rt.models.SelectVoice(a), "english again"), "Neural")
    control = c.controls["Neural"]
    for number in (1, 2, 3):
        barrier = control.tail(number)
        assert len(control.calls) == number
        barrier.release.set()
    c.wait_done()
    assert [snapshot.voice_id for snapshot in control.applied] == ["voice1", "voice2", "voice1"]
    assert [snapshot.rate for snapshot in control.applied] == [50, 31, 50]
    assert control.calls[0].instance != control.calls[1].instance
    assert control.calls[0].instance == control.calls[2].instance
    assert len({context.segment_id for context in control.contexts}) == 3
    assert len(c.output.drains) == 3
    assert request.state is c.scheduler.RequestState.COMPLETED


@pytest.mark.parametrize("engine", ["Neural", "VE", "Cerence"])
def test_language_change_active_native_call_cannot_escape_cancel(composition, monkeypatch, engine):
    c = composition
    control = c.controls[engine]
    if engine in ("VE", "Cerence"):
        monkeypatch.setattr(control.core, "getVoiceNameForLanguage", lambda language: "fr", raising=False)
    old = c.submit(("hello", c.commands.LangChangeCommand("fr"), "bonjour"), engine)
    first = control.wait_call()
    control.complete_native()
    second = control.wait_call(2)
    first_id = first.instance if engine == "Neural" else first.instance.pHandleData
    second_id = second.instance if engine == "Neural" else second.instance.pHandleData
    saved_bookmark = control.env.native.synths[second_id].bookmark if engine == "Neural" else None
    assert first_id != second_id
    assert len(control.contexts) == 1
    assert c.output.drains == []
    if engine == "Neural":
        control.env.native.stop_start_entered.clear()
    c.tasks.cancel(c.manager.playback_ports)
    if engine == "Neural":
        assert control.env.native.stop_start_entered.wait(1)
        with control.env.native.condition:
            assert any(synth == second_id for _, synth in control.env.native.operations)
    second.release.set()
    fresh = c.submit(("new default voice",), engine)
    control.wait_call(3)
    assert len(control.calls) == 3
    assert (control.calls[2].instance if engine == "Neural" else control.calls[2].instance.pHandleData) == first_id
    fed_before = list(control.player.fed)
    if engine == "Neural":
        control.env.native.bookmark("9999", saved=saved_bookmark)
    else:
        from test_vocalizer_segment_drain import emit
        assert emit(control.env, second.instance, payload=b"stale", index=9999) == [
            control.env.types.NUAN_E_TTS_USERSTOP]
    assert control.player.fed == fed_before
    assert c.output.indexes == []
    assert not fresh.tasks[0].future.done()
    barrier = control.tail(3, idle_number=1)
    assert not fresh.tasks[0].future.done()
    barrier.release.set()
    c.wait_done()
    assert old.state is c.scheduler.RequestState.CANCELLED
    assert fresh.state is c.scheduler.RequestState.COMPLETED
    assert len(c.output.dones) == 1


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("content", ["blank", "index", "break"])
def test_blank_index_only_and_break_only_finish_via_drain(composition, engine, content):
    c = composition
    sequence = {"blank": ("   ",), "index": (c.commands.IndexCommand(809),),
                "break": (c.commands.BreakCommand(8),)}[content]
    request = c.submit(sequence, engine)
    control = c.controls[engine]
    # Vocalizer can omit native submission for blank speech, but its real final
    # player idle still owns completion of this scheduler segment.
    if content == "blank" and engine in ("VE", "Cerence"):
        barrier = control.wait_idle()
        assert control.calls == []
    else:
        barrier = control.tail(frames=0 if content in ("blank", "index") else 8)
    assert c.output.dones == []
    assert not request.tasks[0].future.done()
    assert c.output.indexes == ([809] if content == "index" else [])
    barrier.release.set()
    c.wait_done()
    assert len(c.output.drains) == 1
    assert request.tasks[0].future.result(timeout=1) is True


@pytest.mark.parametrize("engine", ENGINES)
def test_unsupported_profile_uses_legacy_from_first_segment(monkeypatch, tmp_path, engine):
    c = assemble(monkeypatch, tmp_path, supported=False)
    try:
        control = c.controls[engine]
        assert control.session.completion.mode is c.rt.models.CompletionMode.LEGACY_DONE
        request = c.submit(("legacy first", c.rt.models.Pause(0.001), "legacy second"), engine)
        first = control.wait_call()
        assert first.context is None
        assert control.contexts == []
        # Native still enters through the real legacy outer wrapper; the policy
        # did not wait for failure before switching the completion contract.
        barrier = control.tail()
        assert len(control.calls) == 1
        barrier.release.set()
        if engine == "OneCore":
            control.wait_idle(2).release.set()
        second = control.wait_call(2)
        assert second.context is None
        assert control.contexts == []
        control.tail(2, idle_number=3 if engine == "OneCore" else 2).release.set()
        if engine == "OneCore":
            control.wait_idle(4).release.set()
        c.wait_done()
        assert c.output.drains == []
        assert request.state is c.scheduler.RequestState.COMPLETED
        assert len(c.output.dones) == 1
    finally:
        c.close()


def test_unsupported_neural_sdk_failure_releases_legacy_request(monkeypatch, tmp_path):
    c = assemble(monkeypatch, tmp_path, supported=False)
    try:
        control = c.controls["Neural"]
        assert control.session.completion.mode is c.rt.models.CompletionMode.LEGACY_DONE
        control.env.native.result = 1
        request = c.submit(("SDK failure",), "Neural")
        call = control.wait_call()
        assert call.context is None
        call.release.set()
        with pytest.raises(RuntimeError, match="Neural SDK synthesis failed"):
            request.tasks[0].future.result(timeout=1)
        c.wait_done()
        assert request.state is c.scheduler.RequestState.FAILED
        assert c.output.drains == []
        assert len(c.output.dones) == 1
        assert control.env.logs
    finally:
        c.close()


def test_contextual_legacy_control_failure_fails_request(monkeypatch, tmp_path):
    c = assemble(monkeypatch, tmp_path, supported=False)
    try:
        control = c.controls["Neural"]
        control.player.error = "pause"
        request = c.submit(("pause failure",), "Neural")
        control.wait_call()
        barrier = control.tail()
        pausing = in_thread(lambda: c.tasks.pause_current(True))
        pausing.done.wait(1)
        barrier.release.set()
        with pytest.raises(OSError, match="audio control failed"):
            request.tasks[0].future.result(timeout=2)
        assert pausing.errors and isinstance(pausing.errors[0], OSError)
        c.wait_done()
        assert request.state is c.scheduler.RequestState.FAILED
        assert c.output.drains == []
        assert len(c.output.dones) == 1
    finally:
        c.close()


def test_neural_legacy_done_acceptance_cannot_release_successor_after_cancel(monkeypatch, tmp_path):
    c = assemble(monkeypatch, tmp_path, supported=False)
    release = Event()
    try:
        control = c.controls["Neural"]
        old = c.submit(("old legacy",), "Neural")
        control.wait_call()
        work = next(iter(control.core._segmentWorks))
        accepted = Event()
        complete = work.complete

        def blocked_complete():
            result = complete()
            if result:
                accepted.set()
                assert release.wait(2), "Test did not release accepted legacy DONE"
            return result

        monkeypatch.setattr(work, "complete", blocked_complete)
        control.tail().release.set()
        assert accepted.wait(1)
        cancelling = in_thread(lambda: c.tasks.cancel(c.manager.playback_ports))
        fresh = None
        try:
            # If cancellation can return across the accepted notification, admit
            # a real successor while the old notification is still suspended.
            if cancelling.done.wait(0.05):
                assert cancelling.errors == []
                fresh = c.submit(("successor legacy",), "Neural")
                with c.tasks._state_cond:
                    assert c.tasks._state_cond.wait_for(lambda:
                        c.tasks._current_task is fresh.tasks[0]
                        and c.tasks._current_phase == "awaiting_completion", 1)
        finally:
            release.set()
            assert cancelling.done.wait(2)
            assert cancelling.errors == []
        if fresh is None:
            fresh = c.submit(("successor legacy",), "Neural")
        successor = control.wait_call(2)
        assert not successor.release.is_set(), "Successor synthesis must still be blocked"
        with pytest.raises(TimeoutError):
            fresh.tasks[0].future.result(timeout=0.05)
        assert c.output.dones == []
        control.tail(2, idle_number=2).release.set()
        c.wait_done()
        assert old.state is c.scheduler.RequestState.CANCELLED
        assert fresh.tasks[0].future.result(timeout=1) is True
        assert fresh.state is c.scheduler.RequestState.COMPLETED
    finally:
        release.set()
        c.close()


def test_neural_legacy_control_failure_delivery_cannot_complete_cancelled_request(monkeypatch, tmp_path):
    c = assemble(monkeypatch, tmp_path, supported=False)
    release = Event()
    try:
        control = c.controls["Neural"]
        request = c.submit(("legacy control failure",), "Neural")
        control.wait_call()
        work = next(iter(control.core._segmentWorks))
        complete, accepted = work.complete, Event()

        def blocked_complete():
            result = complete()
            if result:
                accepted.set()
                assert release.wait(2), "Test did not release accepted failure DONE"
            return result

        monkeypatch.setattr(work, "complete", blocked_complete)
        control.player.error = "pause"
        pausing = in_thread(lambda: c.tasks.pause_current(True))
        assert accepted.wait(1)
        cancelling = in_thread(lambda: c.tasks.cancel(c.manager.playback_ports))
        try:
            assert cancelling.done.wait(1), "Cancel blocked behind external legacy event delivery"
        finally:
            release.set()
            assert pausing.done.wait(2)
            assert cancelling.done.wait(2)
        assert len(pausing.errors) == 1 and isinstance(pausing.errors[0], OSError)
        assert cancelling.errors == []
        assert request.state is c.scheduler.RequestState.CANCELLED
        assert c.output.dones == []
    finally:
        release.set()
        c.close()


def test_contextual_neural_legacy_ignores_anonymous_and_revoked_completion(monkeypatch, tmp_path):
    c = assemble(monkeypatch, tmp_path, supported=False)
    try:
        control = c.controls["Neural"]
        request = c.submit(("legacy identity",), "Neural")
        control.wait_call()
        work = next(iter(control.core._segmentWorks))
        context = work.context
        old_sink = work.on_event
        done = c.rt.models.PlaybackEvent(c.rt.models.EventKind.DONE,
            context.source_id, segment_id=context.segment_id)
        c.bridge._done_event.notify(synth=control.core)
        with pytest.raises(TimeoutError):
            request.tasks[0].future.result(timeout=0.03)
        c.bridge.unbind(control.session.source_id)
        c.bridge.bind(control.core, control.session.source_id, completion=control.session.completion)
        old_sink(done)
        with pytest.raises(TimeoutError):
            request.tasks[0].future.result(timeout=0.03)
        assert c.output.dones == []
        monkeypatch.setattr(work, "on_event", c.bridge.legacy_segment_sink(control.core, context))
        control.tail().release.set()
        c.wait_done()
        assert request.tasks[0].future.result(timeout=1) is True
    finally:
        c.close()


def _exercise_neural_legacy_terminal_index_cancel(failure, tmp_path):
    # A broken lock order leaves daemon engine/scheduler threads deadlocked.
    # Run this case in its own interpreter so failed evidence cannot hang cleanup.
    monkeypatch = pytest.MonkeyPatch()
    c = assemble(monkeypatch, tmp_path, supported=False)
    control = c.controls["Neural"]
    c.submit(("legacy", c.commands.IndexCommand(818)), "Neural")
    control.wait_call()
    work = next(iter(control.core._segmentWorks))
    complete = work.complete
    accepted, release_done = Event(), Event()
    index_entered, cancel_index, cancelled = Event(), Event(), Event()

    def held_complete():
        result = complete()
        if result:
            accepted.set()
            assert release_done.wait(2), "Test did not release terminal acceptance"
        return result

    def index_handler(index):
        assert index == 818
        index_entered.set()
        assert cancel_index.wait(2), "Test did not release index cancellation"
        c.tasks.cancel(c.manager.playback_ports)
        cancelled.set()

    monkeypatch.setattr(work, "complete", held_complete)
    monkeypatch.setattr(c.bridge, "index_reached", index_handler)
    bookmark = in_thread(lambda: control.env.native.bookmark("818"))
    assert index_entered.wait(1)
    if failure:
        control.player.error = "pause"
        terminal = in_thread(lambda: c.tasks.pause_current(True))
    else:
        control.wait_call().release.set()
        control.wait_idle().release.set()
        terminal = None
    assert accepted.wait(1)
    cancel_index.set()
    release_done.set()
    assert cancelled.wait(1), "Index cancellation and legacy terminal delivery deadlocked"
    assert bookmark.done.wait(1) and bookmark.errors == []
    if terminal is not None:
        assert terminal.done.wait(1)
        assert len(terminal.errors) == 1 and isinstance(terminal.errors[0], OSError)
    assert c.output.dones == []
    c.close()
    monkeypatch.undo()


@pytest.mark.parametrize("failure", [False, True])
def test_neural_legacy_terminal_and_index_cancel_have_no_lock_inversion(tmp_path, failure):
    script = (
        "from pathlib import Path\n"
        "from test_runtime_drain_integration import _exercise_neural_legacy_terminal_index_cancel\n"
        f"_exercise_neural_legacy_terminal_index_cancel({failure!r}, Path({str(tmp_path)!r}))\n"
    )
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).parent,
                            text=True, capture_output=True, timeout=6)
    assert result.returncode == 0, result.stderr
