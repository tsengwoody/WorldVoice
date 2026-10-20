"""Correlated drains across the real manager, adapters, bridge and wrappers."""

from concurrent.futures import TimeoutError

import pytest
from runtime_drain_integration_harness import ENGINES, assemble
from waiting import WAIT_TIMEOUT, stays_unset


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
	assert request.tasks[0].future.result(timeout=WAIT_TIMEOUT) is True
	assert [kind for kind, _ in c.output.timeline] == ["index", "drain", "done"]


@pytest.mark.parametrize("engine", ENGINES)
def test_requests_keep_speaking_after_the_index_range_is_used(monkeypatch, tmp_path, engine):
	# Before the fix the fourth request failed: three wire indexes had been used and never came back.
	c = assemble(monkeypatch, tmp_path, index_range=(1, 3))
	try:
		control = c.controls[engine]
		requests = []
		for number in range(1, 9):
			requests.append(c.submit(("hello", c.commands.IndexCommand(700 + number)), engine))
			control.tail(number).release.set()
			c.wait_done(number)
		assert c.output.indexes == list(range(701, 709))
		assert all(request.state is c.scheduler.RequestState.COMPLETED for request in requests)
		wires = [
			command.index
			for commands in control.commands
			for command in commands
			if isinstance(command, c.commands.IndexCommand)
		]
		assert wires == [1, 2, 3, 1, 2, 3, 1, 2]
	finally:
		c.close()


@pytest.mark.parametrize("engines", [("VE", "Cerence", "VE")])
def test_next_engine_starts_only_after_segment_drain(composition, engines):
	c = composition
	a, b, _ = engines
	request = c.submit(
		(
			"first",
			c.rt.models.Pause(0.001),
			c.rt.models.SelectVoice(c.key(b)),
			"second",
			c.rt.models.SelectVoice(c.key(a)),
			"third",
		),
		a,
	)
	first, second = c.controls[a], c.controls[b]
	barrier = first.tail()
	stays_unset(second.started)
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


@pytest.mark.parametrize("first,successor", [("VE", "Cerence")])
def test_switch_waits_for_original_correlated_drain(composition, first, successor):
	c = composition
	request = c.submit(
		(
			"original",
			c.rt.models.SelectVoice(c.key(successor)),
			"successor",
		),
		first,
	)
	original = c.controls[first]
	following = c.controls[successor]
	barrier = original.tail()
	context = original.contexts[0]
	assert c.output.drains == []
	stays_unset(following.started)
	assert following.calls == []
	assert not request.tasks[0].future.done()
	barrier.release.set()
	following.wait_call()
	assert len(c.output.drains) == 1
	event = c.output.drains[0]
	assert event.source_id is context.source_id
	assert event.segment_id == context.segment_id
	assert event.kind is c.rt.models.EventKind.SEGMENT_DRAINED
	assert following.contexts[0].source_id is not context.source_id
	assert following.contexts[0].segment_id != context.segment_id
	following.tail().release.set()
	c.wait_done()
	assert request.state is c.scheduler.RequestState.COMPLETED
	assert len(c.output.drains) == 2
	assert len(c.output.dones) == 1


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
	assert barrier.returned.wait(WAIT_TIMEOUT)
	with pytest.raises(TimeoutError):
		request.tasks[0].future.result(timeout=0.03)
	assert c.output.dones == []
	assert c.output.drains == []
	c.tasks.pause_current(False)
	c.wait_done()
	assert request.tasks[0].future.result(timeout=WAIT_TIMEOUT) is True
	assert len(c.output.dones) == 1


@pytest.mark.parametrize("engine", ENGINES)
def test_cancel_and_stale_sink_cannot_release_new_same_source_segment(composition, engine):
	c = composition
	control = c.controls[engine]
	old = c.submit(("old", c.commands.IndexCommand(11)), engine)
	control.wait_call()
	control.feed_release.clear()
	control.complete_native()
	assert control.feed_entered.wait(WAIT_TIMEOUT)
	old_context, old_sink = control.contexts[0], control.sinks[0]
	c.tasks.cancel(c.manager.playback_ports)
	fresh = c.submit(("fresh", c.commands.IndexCommand(22)), engine)
	old_sink(
		c.rt.models.PlaybackEvent(
			c.rt.models.EventKind.SEGMENT_DRAINED,
			old_context.source_id,
			segment_id=old_context.segment_id,
		),
	)
	assert len(control.calls) == 1
	assert not fresh.tasks[0].future.done()
	assert c.output.dones == []
	control.feed_release.set()
	control.wait_call(2)
	assert len(control.calls) == 2
	barrier = control.tail(2, idle_number=1)
	# Old context completion and anonymous NVDA DONE cannot satisfy fresh DRAIN.
	old_sink(
		c.rt.models.PlaybackEvent(
			c.rt.models.EventKind.SEGMENT_DRAINED,
			old_context.source_id,
			segment_id=old_context.segment_id,
		),
	)
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
	old_sink(
		c.rt.models.PlaybackEvent(
			c.rt.models.EventKind.SEGMENT_DRAINED,
			context.source_id,
			segment_id=context.segment_id,
		),
	)
	revoked(
		c.rt.models.PlaybackEvent(
			c.rt.models.EventKind.SEGMENT_DRAINED,
			current.source_id,
			segment_id=current.segment_id,
		),
	)
	with pytest.raises(TimeoutError):
		fresh.tasks[0].future.result(timeout=0.03)
	assert c.output.dones == []
	# The wrapper retains the revoked sink too; install a freshly bound sink at
	# the same actual work boundary to let this deliberately rebound job retire.
	live = c.bridge.segment_sink(control.core, current)
	barrier = control.tail(2, idle_number=2)
	assert not fresh.tasks[0].future.done()
	barrier.release.set()
	assert barrier.returned.wait(WAIT_TIMEOUT)
	live(
		c.rt.models.PlaybackEvent(
			c.rt.models.EventKind.SEGMENT_DRAINED,
			current.source_id,
			segment_id=current.segment_id,
		),
	)
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
	a, b = "VE:fake", "VE:fake2"
	c.manager.resolve_playback(b)
	c.store.state(b).update(rate=31)
	request = c.submit(
		(
			"english",
			c.rt.models.SelectVoice(b),
			"french",
			c.rt.models.SelectVoice(a),
			"english again",
		),
		"VE",
	)
	control = c.controls["VE"]
	for number in (1, 2, 3):
		barrier = control.tail(number)
		assert len(control.calls) == number
		barrier.release.set()
	c.wait_done()
	assert [snapshot.voice_id for snapshot in control.applied] == ["fake", "fake2", "fake"]
	assert [snapshot.rate for snapshot in control.applied] == [50, 31, 50]
	instances = [call.instance.pHandleData for call in control.calls]
	assert instances[0] != instances[1]
	assert instances[0] == instances[2]
	assert len({context.segment_id for context in control.contexts}) == 3
	assert len(c.output.drains) == 3
	assert request.state is c.scheduler.RequestState.COMPLETED


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_language_change_active_native_call_cannot_escape_cancel(composition, monkeypatch, engine):
	c = composition
	control = c.controls[engine]
	monkeypatch.setattr(control.core, "getVoiceNameForLanguage", lambda language: "fr", raising=False)
	old = c.submit(("hello", c.commands.LangChangeCommand("fr"), "bonjour"), engine)
	first = control.wait_call()
	control.complete_native()
	second = control.wait_call(2)
	first_id = first.instance.pHandleData
	second_id = second.instance.pHandleData
	assert first_id != second_id
	assert len(control.contexts) == 1
	assert c.output.drains == []
	c.tasks.cancel(c.manager.playback_ports)
	second.release.set()
	fresh = c.submit(("new default voice",), engine)
	control.wait_call(3)
	assert len(control.calls) == 3
	assert control.calls[2].instance.pHandleData == first_id
	fed_before = list(control.player.fed)
	from worldvoice_cancel_wrapper_harness import emit

	assert emit(control.env, second.instance, payload=b"stale", index=9999) == [
		control.env.types.NUAN_E_TTS_USERSTOP,
	]
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
	sequence = {
		"blank": ("   ",),
		"index": (c.commands.IndexCommand(809),),
		"break": (c.commands.BreakCommand(8),),
	}[content]
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
	assert request.tasks[0].future.result(timeout=WAIT_TIMEOUT) is True


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
