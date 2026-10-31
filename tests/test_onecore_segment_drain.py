import ctypes
import gc
import inspect
import io
import sys
import wave
import weakref
from threading import Event, current_thread, get_ident

import pytest
from onecore_drain_harness import (
	VERSION,
	has_player,
	in_thread,
	load_onecore,
	native_call,
	queued_segment_jobs,
	queued_speech,
	segment_paused,
	segment_terminated,
	segment_worker,
	stop_gate_clear,
)
from runtime_harness import (
	accepted_operations,
	delivery_thread,
	lifecycle_terminated,
	live_operations,
	segment_host,
	segment_lifecycle,
)
from waiting import (
	HOLD_TIMEOUT,
	WAIT_TIMEOUT,
	eventually,
	holds_within,
	quiet_period,
	stays_false,
	stays_unset,
)


@pytest.fixture
def env(monkeypatch):
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime._segmentLifecycle", raising=False)
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)
	result = load_onecore(monkeypatch)
	yield result
	result.player.feed_release.set()
	result.player.sync_release.set()
	if result.driver is not None:
		result.driver.terminate()


def speak(env, segment=17, commands=("hello",), events=None, token=None):
	events = [] if events is None else events
	token = token or env.scheduler.CancellationToken()
	context = env.rt.models.PlaybackContext(object(), segment)
	env.driver.speak_segment(commands, token, context=context, on_event=events.append)
	return token, context, events


def finish(call):
	assert call.done.wait(WAIT_TIMEOUT), "Callback did not exit"
	call.thread.join(1)
	assert call.errors == []


def wait_events(events, count=1):
	eventually(lambda: len(events) >= count, message="Segment event was not delivered")


def test_stubs_cover_names_that_onecore_annotations_use(env):
	# Python 3.13 and older evaluate annotations when the def runs, so a stubbed
	# module must also provide every name that NVDA's oneCore.py uses only in one.
	base = env.base
	annotated = []
	for owner in vars(base).values():
		if inspect.isclass(owner) and owner.__module__ == base.__name__:
			annotated.append(owner)
			for member in vars(owner).values():
				member = getattr(member, "__func__", member)
				if inspect.isfunction(member):
					annotated.append(member)
	assert annotated
	missing = []
	for item in annotated:
		try:
			inspect.get_annotations(item)  # evaluates them, like Python 3.13
		except (NameError, AttributeError) as error:
			missing.append(f"{item.__qualname__}: {error}")
	assert missing == []


def test_onecore_uses_shared_lifecycle_for_an_empty_segment(env):
	events = []
	_, context, _ = speak(env, commands=(), events=events)
	# The actual wrapper must own the same operation that the coordinator runs.
	env.native.wait_calls(1)
	operation = native_call(env.driver).operation
	assert operation.work.context is context
	assert operation in live_operations(segment_lifecycle(segment_host(env.driver)))
	response = in_thread(lambda: env.native.respond(frames=0, markers=""))
	finish(response)
	assert env.player.sync_entered.wait(WAIT_TIMEOUT)
	assert events == []
	env.player.sync_release.set()
	wait_events(events)
	assert len(events) == 1
	assert events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert events[0].source_id is context.source_id
	assert events[0].segment_id == context.segment_id


def test_onecore_shared_handoff_waits_for_callback_feed_and_stop(env):
	_, old_context, old_events = speak(env)
	env.native.wait_calls(1)
	old_operation = native_call(env.driver).operation
	env.player.feed_release.clear()
	stop_entered, release_stop = Event(), Event()
	original_stop = env.player.stop

	def blocked_stop():
		stop_entered.set()
		assert release_stop.wait(HOLD_TIMEOUT), "Test did not release the old stop"
		original_stop()

	env.player.stop = blocked_stop
	response = in_thread(env.native.respond)
	assert env.player.feed_entered.wait(WAIT_TIMEOUT)
	cancel = in_thread(env.driver.cancel)
	assert stop_entered.wait(WAIT_TIMEOUT)
	_, new_context, new_events = speak(env, segment=18)
	assert len(env.native.calls) == 1
	assert old_events == [] and new_events == []
	assert old_operation.work.context is old_context
	env.player.feed_release.set()
	stays_false(env.native.condition, lambda: len(env.native.calls) >= 2)
	release_stop.set()
	finish(response)
	finish(cancel)
	env.native.wait_calls(2)
	assert native_call(env.driver).operation is not old_operation
	env.player.sync_release.set()
	env.native.respond(markers="")
	wait_events(new_events)
	assert old_events == []
	assert len(new_events) == 1
	assert new_events[0].source_id is new_context.source_id
	assert new_events[0].segment_id == new_context.segment_id


def test_onecore_callback_return_precedes_drain_and_successor_native_call(env):
	_, first, first_events = speak(env)
	_, second, second_events = speak(env, segment=18)
	env.native.wait_calls(1)
	callback_body_returned, release_callback = Event(), Event()
	original_callback = env.driver._callback

	def held_callback(*args):
		original_callback(*args)
		callback_body_returned.set()
		assert release_callback.wait(HOLD_TIMEOUT)

	env.driver._callback = held_callback
	env.player.sync_release.set()
	response = in_thread(lambda: env.native.respond(markers=""))
	assert callback_body_returned.wait(WAIT_TIMEOUT)
	advanced = holds_within(env.native.condition, lambda: len(env.native.calls) >= 2)
	assert not advanced, "Successor native call began before callback returned"
	assert first_events == [] and second_events == []
	assert len(env.native.calls) == 1
	release_callback.set()
	finish(response)
	wait_events(first_events)
	env.native.wait_calls(2)
	env.native.respond(markers="")
	wait_events(second_events)
	assert first_events[0].source_id is first.source_id
	assert second_events[0].source_id is second.source_id


def test_onecore_retirement_return_precedes_drain_and_successor_native_call(env):
	_, first, first_events = speak(env)
	_, second, second_events = speak(env, segment=18)
	env.native.wait_calls(1)
	retired, release_retirement = Event(), Event()
	original_retire = env.driver._retireSegmentNative

	def held_retirement(native):
		original_retire(native)
		if native.operation is not None:
			retired.set()
			assert release_retirement.wait(HOLD_TIMEOUT)

	env.driver._retireSegmentNative = held_retirement
	env.player.sync_release.set()
	response = in_thread(lambda: env.native.respond(markers=""))
	assert retired.wait(WAIT_TIMEOUT)
	advanced = holds_within(env.native.condition, lambda: len(env.native.calls) >= 2)
	assert not advanced, "Successor native call began before retirement returned"
	assert first_events == [] and second_events == []
	release_retirement.set()
	finish(response)
	wait_events(first_events)
	env.native.wait_calls(2)
	env.native.respond(markers="")
	wait_events(second_events)
	assert first_events[0].source_id is first.source_id
	assert second_events[0].source_id is second.source_id


def test_onecore_successor_player_open_waits_for_old_feed_and_stop(env):
	speak(env)
	env.native.wait_calls(1)
	original_open = env.player.open
	opened = []

	def observed_open():
		opened.append(True)
		original_open()

	env.player.open = observed_open
	env.player.feed_release.clear()
	stop_entered, release_stop = Event(), Event()
	original_stop = env.player.stop

	def blocked_stop():
		stop_entered.set()
		assert release_stop.wait(HOLD_TIMEOUT)
		original_stop()

	env.player.stop = blocked_stop
	response = in_thread(env.native.respond)
	assert env.player.feed_entered.wait(WAIT_TIMEOUT)
	cancel = in_thread(env.driver.cancel)
	assert stop_entered.wait(WAIT_TIMEOUT)
	speak(env, segment=18)
	assert opened == []
	assert len(env.native.calls) == 1
	env.player.feed_release.set()
	stays_false(env.native.condition, lambda: bool(opened))
	release_stop.set()
	finish(response)
	finish(cancel)
	env.native.wait_calls(2)
	assert opened == [True]
	env.player.sync_release.set()
	env.native.respond(markers="")


def test_onecore_waits_for_tail_sync_before_drain(env, monkeypatch):
	# PLAYED_OUT is OneCore's sync() returning: it must be reached only after sync() returns.
	synced, reached = [], []
	sync, reach = env.player.sync, env.driver._segmentHost.reach

	def tracked_sync():
		sync()
		synced.append(True)

	def tracked_reach(record, barrier):
		reached.append((barrier, bool(synced)))
		reach(record, barrier)

	monkeypatch.setattr(env.player, "sync", tracked_sync)
	monkeypatch.setattr(env.driver._segmentHost, "reach", tracked_reach)
	_token, context, events = speak(env)
	env.native.wait_calls(1)
	call = in_thread(env.native.respond)
	assert env.player.sync_entered.wait(WAIT_TIMEOUT)
	assert env.indexes == [1]
	assert sum(map(len, env.player.fed)) == 16
	assert events == []
	assert env.outer.PLAYED_OUT not in {barrier for barrier, _ in reached}
	env.player.sync_release.set()
	finish(call)
	wait_events(events)
	assert reached == [(env.outer.AUDIO_FED, False), (env.outer.PLAYED_OUT, True)]
	assert len(events) == 1
	assert events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert events[0].source_id is context.source_id
	assert events[0].segment_id == 17
	assert env.outer.Voice.synthDriverClass is type(env.driver)


def test_settings_tuples_do_not_take_native_job_identity(env):
	env.driver._set_rate(60)
	_, first, events_a = speak(env)
	_, second, events_b = speak(env, segment=18)
	env.native.wait_calls(1)
	assert env.native.settings == [("Rate", 1.1)]
	assert len(env.native.calls) == 1
	env.player.sync_release.set()
	env.native.respond()
	env.native.wait_calls(2)
	env.native.respond()
	wait_events(events_a)
	wait_events(events_b)
	assert events_a[0].source_id is first.source_id
	assert events_b[0].source_id is second.source_id
	assert events_b[0].segment_id == 18


def test_setting_changed_while_a_segment_waits_applies_before_it(env):
	# A queued segment enters OneCore's queue only once its predecessor drains,
	# so a setting changed meanwhile is applied before that segment is spoken.
	speak(env)
	env.native.wait_calls(1)
	_, _, events = speak(env, segment=18)
	env.driver._set_rate(60)
	env.player.sync_release.set()
	env.native.respond(markers="")
	env.native.wait_calls(2)
	assert env.native.settings == [("Rate", 1.1)]
	env.native.respond(markers="")
	wait_events(events)
	assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


def test_ordinary_speech_and_settings_keep_call_order(env):
	entries = []
	original_speak = env.native.speak

	def recording_speak(token, text):
		entries.append(list(env.native.settings))
		original_speak(token, text)

	env.native.ocSpeech_speak = env.native.ocSpeech_speak.__class__(recording_speak)
	env.driver.speak(("first",))
	env.driver._set_rate(60)
	env.driver.speak(("second",))
	env.native.wait_calls(1)
	env.player.sync_release.set()
	env.native.respond(markers="")
	env.native.wait_calls(2)
	env.native.respond(markers="")
	assert entries == [[], [("Rate", 1.1)]]


def test_failed_setting_change_is_logged_and_later_speech_continues(env):
	# A native setting that fails is logged; it does not latch a control error
	# that would reject all later speech.
	def failing_set(token, value):
		raise OSError("set rate failed")

	env.native.ocSpeech_setRate = env.native.ocSpeech_setRate.__class__(failing_set)
	env.driver._set_rate(60)
	_, _, events = speak(env)
	env.native.wait_calls(1)
	env.player.sync_release.set()
	env.native.respond(markers="")
	wait_events(events)
	assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
	assert segment_host(env.driver).control_error is None


def test_cancel_removes_queued_text_but_keeps_settings_identity(env):
	speak(env)
	env.native.wait_calls(1)
	_, _, discarded = speak(env, segment=18)
	env.driver._set_volume(75)
	env.driver.cancel()
	_, expected, events = speak(env, segment=19)
	env.native.respond()
	env.native.wait_calls(2)
	env.native.respond()
	wait_events(events)
	assert discarded == []
	assert env.native.settings == [("Volume", 0.75)]
	assert events[0].source_id is expected.source_id
	assert events[0].segment_id == 19


def test_cancel_sees_accepted_work_while_xml_conversion_is_held(env, monkeypatch):
	converting, release = Event(), Event()
	converter = env.outer.oneCore._OcSsmlConverter
	original = converter.convertToXml

	def held_convert(self, commands):
		converting.set()
		assert release.wait(HOLD_TIMEOUT)
		return original(self, commands)

	monkeypatch.setattr(converter, "convertToXml", held_convert)
	token = env.scheduler.CancellationToken()
	events = []
	context = env.rt.models.PlaybackContext(object(), 17)
	speaking = in_thread(
		lambda: env.driver.speak_segment(
			("hello",),
			token,
			context=context,
			on_event=events.append,
		),
	)
	try:
		assert converting.wait(WAIT_TIMEOUT)
		cancelling = in_thread(env.driver.cancel)
		finish(cancelling)
		release.set()
		finish(speaking)
		assert env.native.calls == []
		assert events == []
	finally:
		release.set()


def test_cancel_after_control_fault_capture_suppresses_pending_failure(env, monkeypatch):
	converting, release_conversion = Event(), Event()
	captured, release_delivery = Event(), Event()
	converter = env.outer.oneCore._OcSsmlConverter
	original_convert = converter.convertToXml
	original_delivery = env.driver._controlFault.deliver

	def held_convert(self, commands):
		converting.set()
		assert release_conversion.wait(HOLD_TIMEOUT)
		return original_convert(self, commands)

	def held_delivery(failure):
		captured.set()
		assert release_delivery.wait(HOLD_TIMEOUT)
		return original_delivery(failure)

	monkeypatch.setattr(converter, "convertToXml", held_convert)
	monkeypatch.setattr(env.driver._controlFault, "deliver", held_delivery)
	token = env.scheduler.CancellationToken()
	context = env.rt.models.PlaybackContext(object(), 17)
	events = []
	speaking = in_thread(
		lambda: env.driver.speak_segment(
			("hello",),
			token,
			context=context,
			on_event=events.append,
		),
	)
	try:
		assert converting.wait(WAIT_TIMEOUT)
		operation = next(iter(live_operations(segment_lifecycle(segment_host(env.driver)))))
		faulting = in_thread(lambda: env.driver._failSegmentControl(OSError("player failed")))
		assert captured.wait(WAIT_TIMEOUT)
		cancelling = in_thread(env.driver.cancel)
		finish(cancelling)
		release_delivery.set()
		finish(faulting)
		release_conversion.set()
		finish(speaking)
		eventually(lambda: operation not in live_operations(segment_lifecycle(segment_host(env.driver))))
		assert events == []
		assert env.native.calls == []
	finally:
		release_delivery.set()
		release_conversion.set()


def test_suppressed_conversion_failure_retires_accepted_membership(env, monkeypatch):
	converting, release_conversion = Event(), Event()
	failing, release_failure = Event(), Event()
	converter = env.outer.oneCore._OcSsmlConverter

	def broken_conversion(self, commands):
		converting.set()
		assert release_conversion.wait(HOLD_TIMEOUT)
		raise ValueError("conversion failed")

	monkeypatch.setattr(converter, "convertToXml", broken_conversion)
	token = env.scheduler.CancellationToken()
	context = env.rt.models.PlaybackContext(object(), 17)
	events = []
	speaking = in_thread(
		lambda: env.driver.speak_segment(
			("hello",),
			token,
			context=context,
			on_event=events.append,
		),
	)
	try:
		assert converting.wait(WAIT_TIMEOUT)
		operation = next(iter(live_operations(segment_lifecycle(segment_host(env.driver)))))
		real_fail = operation.work.fail

		def held_fail(error):
			failing.set()
			assert release_failure.wait(HOLD_TIMEOUT)
			return real_fail(error)

		monkeypatch.setattr(operation.work, "fail", held_fail)
		release_conversion.set()
		finish(speaking)
		assert failing.wait(WAIT_TIMEOUT)
		assert operation in accepted_operations(segment_host(env.driver))
		token.cancel()
		release_failure.set()
		eventually(lambda: operation not in live_operations(segment_lifecycle(segment_host(env.driver))))
		eventually(lambda: operation not in accepted_operations(segment_host(env.driver)))
		assert events == []
		assert env.native.calls == []
	finally:
		release_conversion.set()
		release_failure.set()


def test_cancel_sees_work_between_queue_pop_and_lifecycle_run(env, monkeypatch):
	entered, release, finished = Event(), Event(), Event()
	lifecycle = env.driver._segmentHost._lifecycle
	real_run = lifecycle.run

	def held_run(operation, commands):
		entered.set()
		assert release.wait(HOLD_TIMEOUT)
		try:
			return real_run(operation, commands)
		finally:
			finished.set()

	monkeypatch.setattr(lifecycle, "run", held_run)
	_, _, events = speak(env)
	try:
		assert entered.wait(WAIT_TIMEOUT)
		env.driver.cancel()
		release.set()
		assert finished.wait(WAIT_TIMEOUT)
		assert env.native.calls == []
		assert events == []
	finally:
		release.set()


@pytest.mark.parametrize("failure", [False, True])
def test_late_cancelled_callback_is_consumed_before_next_submission(env, failure):
	_, _, old_events = speak(env)
	env.native.wait_calls(1)
	env.driver.cancel()
	_, new, new_events = speak(env, segment=18)
	assert len(env.native.calls) == 1
	env.native.respond(failure=failure)
	env.native.wait_calls(2)
	assert old_events == [] and new_events == []
	env.native.respond()
	wait_events(new_events)
	assert len(new_events) == 1
	assert new_events[0].source_id is new.source_id
	assert new_events[0].segment_id == 18


@pytest.mark.parametrize(
	"response",
	[
		{"failure": True},
		{"malformed": True},
		{"markers": "bad"},
		{"markers": "1:999999999"},
		{"markers": "2:40000|1:20000"},
	],
)
def test_native_and_parse_errors_fail_original_work_without_drain(env, response):
	_, context, events = speak(env)
	env.native.wait_calls(1)
	env.player.sync_release.set()
	env.native.respond(**response)
	wait_events(events)
	assert len(events) == 1
	assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert events[0].source_id is context.source_id
	assert isinstance(events[0].error, Exception)
	assert env.dones == []


def test_observable_player_errors_fail_without_drain(env):
	_, _, events = speak(env)
	env.native.wait_calls(1)
	env.player.error = "feed"
	env.player.sync_release.set()
	env.native.respond()
	wait_events(events)
	assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_FAILED]


def test_sync_failure_fails_only_its_segment(env):
	_, original, failed = speak(env)
	env.native.wait_calls(1)
	env.player.error = "sync"
	env.player.sync_release.set()
	env.native.respond()
	wait_events(failed)
	assert [(event.kind, event.source_id) for event in failed] == [
		(env.rt.models.EventKind.SEGMENT_FAILED, original.source_id),
	]
	assert str(failed[0].error) == "sync failed"
	# The drain (and the lifecycle after it) stopped the player before reporting; a successor
	# may use it. The drain's own stop is defensive: the lifecycle's stops alone pass this test.
	assert env.player.stops >= 1
	assert segment_host(env.driver).control_error is None
	env.player.error = None
	_, successor, drained = speak(env, segment=18)
	env.native.wait_calls(2)
	env.native.respond(markers="")
	wait_events(drained)
	assert [(event.kind, event.source_id) for event in drained] == [
		(env.rt.models.EventKind.SEGMENT_DRAINED, successor.source_id),
	]


def test_segment_drain_idles_the_real_player(env):
	# C4 (phase 54): the drain idles the real player, not the lease, whose idle
	# admits only the current record and would skip it after retirement.
	_, _, events = speak(env)
	env.native.wait_calls(1)
	env.player.sync_release.set()
	env.native.respond(markers="")
	wait_events(events)
	assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
	assert env.player.idles == 1


def test_idle_failure_fails_only_its_segment(env):
	_, original, failed = speak(env)
	env.native.wait_calls(1)
	env.player.error = "idle"
	env.player.sync_release.set()
	env.native.respond(markers="")
	wait_events(failed)
	assert [(event.kind, event.source_id) for event in failed] == [
		(env.rt.models.EventKind.SEGMENT_FAILED, original.source_id),
	]
	assert str(failed[0].error) == "idle failed"
	assert env.player.stops >= 1
	assert segment_host(env.driver).control_error is None
	env.player.error = None
	_, successor, drained = speak(env, segment=18)
	env.native.wait_calls(2)
	env.native.respond(markers="")
	wait_events(drained)
	assert [(event.kind, event.source_id) for event in drained] == [
		(env.rt.models.EventKind.SEGMENT_DRAINED, successor.source_id),
	]


def test_sync_failure_lets_a_queued_segment_drain(env):
	_, first, failed = speak(env)
	env.native.wait_calls(1)
	_, queued, queued_events = speak(env, segment=18)
	env.player.error = "sync"
	env.player.sync_release.set()
	env.native.respond(markers="")
	wait_events(failed)
	assert [(event.kind, event.source_id, event.segment_id) for event in failed] == [
		(env.rt.models.EventKind.SEGMENT_FAILED, first.source_id, 17),
	]
	env.player.error = None
	env.native.wait_calls(2)
	env.native.respond(markers="")
	wait_events(queued_events)
	assert [(event.kind, event.source_id, event.segment_id) for event in queued_events] == [
		(env.rt.models.EventKind.SEGMENT_DRAINED, queued.source_id, 18),
	]


def test_drain_stop_failure_after_sync_failure_latches(env):
	_, _, failed = speak(env)
	env.native.wait_calls(1)
	error = OSError("stop failed after sync")

	def failing_stop():
		raise error

	original_stop = env.player.stop
	env.player.error = "sync"
	env.player.sync_release.set()
	env.player.stop = failing_stop
	try:
		env.native.respond()
		wait_events(failed)
		assert segment_host(env.driver).control_error is error
	finally:
		env.player.stop = original_stop
	env.player.error = None
	_, _, rejected = speak(env, segment=18)
	wait_events(rejected)
	assert rejected[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert rejected[0].error is error
	assert len(env.native.calls) == 1


@pytest.mark.parametrize("terminated", [False, True])
def test_onecore_rejected_segment_uses_async_lifecycle_delivery(env, terminated):
	if terminated:
		env.driver.terminate()
	else:
		speak(env)
		env.native.wait_calls(1)
		original_stop = env.player.stop
		env.player.stop = lambda: (_ for _ in ()).throw(OSError("stop failed"))
		try:
			with pytest.raises(OSError):
				env.driver.cancel()
		finally:
			env.player.stop = original_stop
		eventually(lambda: segment_host(env.driver).control_error is not None)
	caller = get_ident()
	received, events, threads = Event(), [], []
	token = env.scheduler.CancellationToken()
	context = env.rt.models.PlaybackContext(object(), 19)

	def sink(event):
		events.append(event)
		threads.append(get_ident())
		received.set()

	env.driver.speak_segment(("rejected",), token, context=context, on_event=sink)
	assert received.wait(WAIT_TIMEOUT)
	# Give a duplicate failure time to arrive before counting.
	quiet_period()
	assert len(events) == 1
	assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert events[0].source_id is context.source_id
	assert events[0].segment_id == 19
	assert threads == [delivery_thread(segment_lifecycle(segment_host(env.driver))).ident]
	assert threads[0] != caller
	assert len(env.native.calls) == (0 if terminated else 1)


def test_onecore_acceptance_is_atomic_with_terminate(env):
	entered, release_accept = Event(), Event()
	original_accept = env.driver._segmentHost._lifecycle.accept

	def blocked_accept(*args, **kwargs):
		entered.set()
		assert release_accept.wait(HOLD_TIMEOUT)
		return original_accept(*args, **kwargs)

	env.driver._segmentHost._lifecycle.accept = blocked_accept
	events = []
	speaking = in_thread(lambda: speak(env, events=events))
	assert entered.wait(WAIT_TIMEOUT)
	terminating = in_thread(env.driver.terminate)
	stays_unset(terminating.done)
	release_accept.set()
	finish(speaking)
	finish(terminating)
	assert events == []  # Accepted before terminate, then cancelled.


def test_segment_accepted_before_terminate_stays_silent(env, monkeypatch):
	# terminate() must silence work it already accepted before that work can
	# observe the terminated flag (its conversion would then fail).
	host = env.driver._segmentHost
	original_submit = host.submit_native

	def submit_after_terminate_flag(operation, commands):
		eventually(lambda: segment_terminated(env.driver))
		return original_submit(operation, commands)

	monkeypatch.setattr(host, "submit_native", submit_after_terminate_flag)
	cancel_entered, release_cancel = Event(), Event()
	original_cancel = env.driver.cancel

	def blocked_cancel():
		cancel_entered.set()
		assert release_cancel.wait(HOLD_TIMEOUT)
		original_cancel()

	env.driver.cancel = blocked_cancel
	_, _, events = speak(env)
	terminating = in_thread(env.driver.terminate)
	try:
		assert cancel_entered.wait(WAIT_TIMEOUT)
		quiet_period()
		assert events == [], "terminate published a failure for work it had accepted"
	finally:
		release_cancel.set()
		finish(terminating)
	assert events == []
	assert env.native.calls == []


def test_onecore_terminate_overlap_preserves_rejected_failure_event(env):
	lifecycle = env.driver._segmentHost._lifecycle
	delivery_entered, release_delivery = Event(), Event()
	blocker_context = env.rt.models.PlaybackContext(object(), 20)
	lifecycle.reject_new(
		blocker_context,
		env.scheduler.CancellationToken(),
		lambda event: (delivery_entered.set(), release_delivery.wait(HOLD_TIMEOUT)),
		RuntimeError("block delivery"),
	)
	assert delivery_entered.wait(WAIT_TIMEOUT)
	cancel_entered, release_cancel = Event(), Event()
	original_cancel = env.driver.cancel

	def blocked_cancel():
		cancel_entered.set()
		assert release_cancel.wait(HOLD_TIMEOUT)
		original_cancel()

	env.driver.cancel = blocked_cancel
	terminating = in_thread(env.driver.terminate)
	try:
		assert cancel_entered.wait(WAIT_TIMEOUT)
		_, context, events = speak(env, segment=21)
		assert events == []
		release_cancel.set()
		eventually(lambda: lifecycle_terminated(lifecycle))
		assert events == []
	finally:
		release_cancel.set()
		release_delivery.set()
		finish(terminating)
	wait_events(events)
	assert len(events) == 1
	assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert events[0].source_id is context.source_id
	assert events[0].segment_id == 21
	assert len(env.native.calls) == 0


def test_onecore_accepted_then_terminated_suppresses_pending_failure(env, monkeypatch):
	lifecycle = env.driver._segmentHost._lifecycle
	delivery_entered, release_delivery = Event(), Event()
	blocker_context = env.rt.models.PlaybackContext(object(), 20)
	lifecycle.reject_new(
		blocker_context,
		env.scheduler.CancellationToken(),
		lambda event: (delivery_entered.set(), release_delivery.wait(HOLD_TIMEOUT)),
		RuntimeError("block delivery"),
	)
	assert delivery_entered.wait(WAIT_TIMEOUT)

	convert_entered, release_convert = Event(), Event()
	converter = env.base._OcSsmlConverter
	original_convert = converter.convertToXml

	def blocked_convert(self, commands):
		convert_entered.set()
		assert release_convert.wait(HOLD_TIMEOUT)
		return original_convert(self, commands)

	monkeypatch.setattr(converter, "convertToXml", blocked_convert)
	events = []
	token = env.scheduler.CancellationToken()
	context = env.rt.models.PlaybackContext(object(), 22)
	speaking = in_thread(
		lambda: env.driver.speak_segment(
			("accepted",),
			token,
			context=context,
			on_event=events.append,
		),
	)
	assert convert_entered.wait(WAIT_TIMEOUT)

	cancel_entered, release_cancel = Event(), Event()
	original_cancel = env.driver.cancel

	def blocked_cancel():
		cancel_entered.set()
		assert release_cancel.wait(HOLD_TIMEOUT)
		original_cancel()

	env.driver.cancel = blocked_cancel
	terminating = in_thread(env.driver.terminate)
	try:
		assert cancel_entered.wait(WAIT_TIMEOUT)
		release_convert.set()
		finish(speaking)
		assert events == []
		release_cancel.set()
		eventually(lambda: lifecycle_terminated(lifecycle))
	finally:
		release_convert.set()
		release_cancel.set()
		release_delivery.set()
		finish(terminating)
	eventually(lambda: all(operation.work.context is not context for operation in live_operations(lifecycle)))
	assert events == []
	assert env.native.calls == []


@pytest.mark.parametrize(
	"commands,frames,markers",
	[
		(("index-only",), 0, "1:0"),
		(("break-only",), 8, ""),
	],
	ids=["index-only", "break-only"],
)
def test_empty_index_and_break_segments_drain_at_known_end(env, commands, frames, markers):
	if commands == ("index-only",):
		index = env.commands.IndexCommand()
		index.index = 1
		commands = (index,)
	elif commands == ("break-only",):
		pause = env.commands.BreakCommand()
		pause.time = 8
		commands = (pause,)
	_, _, events = speak(env, commands=commands)
	env.native.wait_calls(1)
	env.player.sync_release.set()
	env.native.respond(frames=frames, markers=markers)
	wait_events(events)
	assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


def test_segment_drain_does_not_wait_for_resume(env):
	# A pause after the audio played out is the scheduler's to hold (phase 54).
	_, _, events = speak(env)
	env.native.wait_calls(1)
	env.driver.pause(True)
	env.player.sync_release.set()
	try:
		call = in_thread(lambda: env.native.respond(frames=8, markers=""))
		finish(call)
		wait_events(events)
		assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
		assert env.driver._segmentPaused
	finally:
		env.driver.pause(False)


def test_pause_before_first_wav_also_pauses_new_player(env):
	env.driver._player = None
	speak(env)
	env.native.wait_calls(1)
	env.driver.pause(True)
	call = in_thread(lambda: env.native.respond(markers=""))
	assert env.player.sync_entered.wait(WAIT_TIMEOUT)
	paused = env.player.pause_switch
	env.driver.pause(False)
	env.player.sync_release.set()
	finish(call)
	assert paused, "A player initialized after pause played without being paused"


def test_cancel_stop_returning_from_sync_never_reports_drain(env):
	_, _, events = speak(env)
	env.native.wait_calls(1)
	call = in_thread(env.native.respond)
	assert env.player.sync_entered.wait(WAIT_TIMEOUT)
	env.driver.cancel()
	finish(call)
	assert events == []
	assert env.player.stops >= 1


def test_cancel_stop_must_exit_before_a_retired_callback_allows_new_work(env):
	speak(env)
	env.native.wait_calls(1)
	stopped = Event()
	release_stop = Event()
	original_stop = env.player.stop

	def blocked_stop():
		stopped.set()
		assert release_stop.wait(HOLD_TIMEOUT)
		original_stop()

	env.player.stop = blocked_stop
	cancel = in_thread(env.driver.cancel)
	assert stopped.wait(WAIT_TIMEOUT)
	speak(env, segment=18)
	env.native.respond(failure=True)
	advanced = holds_within(env.native.condition, lambda: len(env.native.calls) >= 2)
	release_stop.set()
	finish(cancel)
	assert not advanced, "New native work started before the old cancel stop exited"
	env.native.wait_calls(2)


def test_terminate_unblocks_sync_and_retains_late_callback(env):
	_, _, events = speak(env)
	env.native.wait_calls(1)
	callback = env.native.callback
	call = in_thread(env.native.respond)
	assert env.player.sync_entered.wait(WAIT_TIMEOUT)
	env.driver.terminate()
	finish(call)
	# A timeout in the actual helper's terminate may leave the pointer callable.
	callback(None, 0, None)
	assert events == []
	assert env.native.terminated


def test_native_submission_exception_fails_and_allows_following_work(env):
	env.native.submit_error = OSError("submit failed")
	failed = Event()
	events = []
	token = env.scheduler.CancellationToken()
	context = env.rt.models.PlaybackContext(object(), 17)
	env.driver.speak_segment(
		("hello",),
		token,
		context=context,
		on_event=lambda event: (events.append(event), failed.set()),
	)
	assert failed.wait(WAIT_TIMEOUT)
	assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_FAILED]
	env.native.submit_error = None
	speak(env, segment=18)
	env.native.wait_calls(1)


def test_capability_allows_live_profile_without_provenance_certification(env, monkeypatch):
	support = env.driver.get_segment_drain_support(nvda_version=VERSION, audio_mode="wasapi")
	assert support.supported
	assert "unverified" in support.reason.lower()
	for version, audio in (("2026.3", "wasapi"), (VERSION, "waveout"), ("2024.1", "wasapi")):
		support = env.driver.get_segment_drain_support(nvda_version=version, audio_mode=audio)
		assert support.supported and support.reason
	monkeypatch.setattr(env.base, "__file__", "/unverified/oneCore.py")
	support = env.driver.get_segment_drain_support(nvda_version=VERSION, audio_mode="wasapi")
	assert support.supported and "unverified" in support.reason.lower()


@pytest.mark.parametrize("missing", ["token", "callback", "native speak"])
def test_capability_rejects_partial_initialization(env, missing):
	if missing == "token":
		env.driver._ocSpeechToken.value = None
	elif missing == "callback":
		env.driver._callbackInst = None
	else:
		env.native.ocSpeech_speak = None
	support = env.driver.get_segment_drain_support(nvda_version=VERSION, audio_mode="wasapi")
	assert not support.supported and support.reason


def test_drain_reports_while_a_resume_is_in_flight(env):
	_, _, events = speak(env)
	env.native.wait_calls(1)
	env.driver.pause(True)
	env.player.sync_release.set()
	call = in_thread(lambda: env.native.respond(frames=0, markers=""))
	assert env.player.sync_entered.wait(WAIT_TIMEOUT)
	resumed = Event()
	release = Event()
	original_pause = env.player.pause

	def blocking_resume(switch):
		if not switch:
			resumed.set()
			assert release.wait(HOLD_TIMEOUT)
		original_pause(switch)

	env.player.pause = blocking_resume
	resume = in_thread(lambda: env.driver.pause(False))
	try:
		assert resumed.wait(WAIT_TIMEOUT)
		finish(call)
		wait_events(events)
		assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
	finally:
		release.set()
	finish(resume)


def start_controlled_playback(env, mode):
	if mode == "legacy_after_segment":
		speak(env)
		env.native.wait_calls(1)
		env.player.sync_release.set()
		env.native.respond(markers="")
		# The shared coordinator completes playback on its worker after the
		# native callback returns. Wait for that handoff before resetting sync.
		eventually(lambda: native_call(env.driver) is None)
		env.player.sync_release.clear()
		env.player.sync_entered.clear()
	if mode == "segment":
		_, context, events = speak(env)
	else:
		context, events = None, []
		env.driver.speak(("legacy",))
	env.native.wait_calls(2 if mode == "legacy_after_segment" else 1)
	return context, events


@pytest.mark.parametrize("mode", ["segment", "legacy", "legacy_after_segment"])
@pytest.mark.parametrize("terminate", [False, True])
def test_late_pause_retires_before_cancel_handoff_or_native_close(env, mode, terminate):
	_, old_events = start_controlled_playback(env, mode)
	original_pause, original_stop = env.player.pause, env.player.stop
	pause_entered, release_pause, stopped = Event(), Event(), Event()

	def blocked_pause(switch):
		if switch:
			pause_entered.set()
			assert release_pause.wait(HOLD_TIMEOUT), "Test did not release pause"
		original_pause(switch)

	def observed_stop():
		original_stop()
		stopped.set()

	env.player.pause, env.player.stop = blocked_pause, observed_stop
	pause = in_thread(lambda: env.driver.pause(True))
	assert pause_entered.wait(WAIT_TIMEOUT)
	closing = in_thread(env.driver.terminate if terminate else env.driver.cancel)
	try:
		assert stopped.wait(WAIT_TIMEOUT), "Cancel must stop playback before waiting for pause"
		stays_unset(closing.done, message="Close/cancel retired while pause could still affect the player")
		if terminate:
			assert not env.native.terminated
		else:
			_, _, successor_events = speak(env, segment=18)
			if mode != "legacy":
				env.native.respond(failure=True)
			assert len(env.native.calls) == (2 if mode == "legacy_after_segment" else 1)
	finally:
		release_pause.set()
		finish(pause)
		finish(closing)
	assert old_events == []
	if not terminate:
		if mode == "legacy":
			env.native.respond(failure=True)
		env.native.wait_calls(3 if mode == "legacy_after_segment" else 2)
		assert not env.player.pause_switch, "A retired pause affected successor playback"
		env.native.respond(markers="")
		wait_events(successor_events)
		assert [event.kind for event in successor_events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
	else:
		assert env.native.terminated


@pytest.mark.parametrize("mode", ["segment", "legacy", "legacy_after_segment"])
@pytest.mark.parametrize("switch", [False, True])
def test_pause_or_resume_error_resolves_work_and_blocks_new_admission(env, mode, switch):
	context, events = start_controlled_playback(env, mode)
	if not switch:
		env.driver.pause(True)
	call = in_thread(lambda: env.native.respond(markers=""))
	assert env.player.sync_entered.wait(WAIT_TIMEOUT)
	error = OSError("player control failed")

	def failed_control(switch):
		raise error

	env.player.pause = failed_control
	with pytest.raises(OSError) as raised:
		env.driver.pause(switch)
	assert raised.value is error
	env.player.sync_release.set()
	finish(call)
	if mode == "segment":
		wait_events(events)
		assert len(events) == 1
		assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
		assert events[0].error is error
		assert events[0].source_id is context.source_id
		assert events[0].segment_id == context.segment_id
	else:
		assert env.dones == [env.driver], "Legacy failure did not release its wait exactly once"
	calls = len(env.native.calls)
	_, _, rejected = speak(env, segment=18)
	wait_events(rejected)
	assert len(rejected) == 1
	assert rejected[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert rejected[0].error is error
	with pytest.raises(OSError) as rejected_legacy:
		env.driver.speak(("uncertain player",))
	assert rejected_legacy.value is error
	assert len(env.native.calls) == calls


def test_pause_error_on_new_player_latches_before_following_segment(env):
	env.driver._player = None
	_, _, events = speak(env)
	env.native.wait_calls(1)
	env.driver.pause(True)
	error = OSError("new player pause failed")

	def failed_pause(switch):
		raise error

	env.player.pause = failed_pause
	env.native.respond(markers="")
	wait_events(events)
	assert len(events) == 1 and events[0].error is error
	_, _, rejected = speak(env, segment=18)
	wait_events(rejected)
	assert len(rejected) == 1 and rejected[0].error is error
	assert len(env.native.calls) == 1


def test_control_error_fails_queued_contexts_and_allows_reentrant_cancel(env):
	events, failed = [], Event()
	token = env.scheduler.CancellationToken()
	context = env.rt.models.PlaybackContext(object(), 17)

	def failure_sink(event):
		events.append(event)
		env.driver.cancel()
		failed.set()

	env.driver.speak_segment(("active",), token, context=context, on_event=failure_sink)
	env.native.wait_calls(1)
	_, queued_context, queued_events = speak(env, segment=18)
	error = OSError("pause failed with queued work")

	def failed_pause(switch):
		raise error

	env.player.pause = failed_pause
	pause = in_thread(lambda: env.driver.pause(True))
	assert pause.done.wait(WAIT_TIMEOUT), "Failure sink deadlocked while cancelling"
	pause.thread.join(1)
	assert pause.errors == [error]
	env.native.respond(failure=True)
	assert failed.wait(WAIT_TIMEOUT)
	assert len(events) == 1 and events[0].error is error
	wait_events(queued_events)
	assert len(queued_events) == 1 and queued_events[0].error is error
	assert queued_events[0].source_id is queued_context.source_id
	assert len(env.native.calls) == 1


def test_cancelled_legacy_feed_retires_only_after_its_final_stop(env):
	speak(env)
	env.native.wait_calls(1)
	env.player.sync_release.set()
	env.native.respond()
	env.driver.speak(("legacy",))
	env.native.wait_calls(2)
	env.player.feed_entered.clear()
	env.player.feed_release.clear()
	call = in_thread(lambda: env.native.respond(markers=""))
	assert env.player.feed_entered.wait(WAIT_TIMEOUT)
	env.driver.cancel()
	speak(env, segment=18)
	assert len(env.native.calls) == 2
	final_stop = Event()
	release_stop = Event()
	original_stop = env.player.stop
	stop_threads = []

	def blocked_final_stop():
		stop_threads.append(current_thread())
		final_stop.set()
		assert release_stop.wait(HOLD_TIMEOUT)
		original_stop()

	env.player.stop = blocked_final_stop
	env.player.feed_release.set()
	stopped = final_stop.wait(WAIT_TIMEOUT)
	advanced = holds_within(env.native.condition, lambda: len(env.native.calls) >= 3)
	release_stop.set()
	finish(call)
	assert stopped, "The legacy feed queued audio after cancel without a final stop"
	assert not advanced, "New native work started before the cancelled legacy feed's final stop"
	# The worker's retire also stops the cancelled sentence; the lease's stop is the one on the
	# callback thread that fed, before the callback returns.
	assert call.thread in stop_threads, "The lease did not stop again after the late legacy feed"
	env.native.wait_calls(3)
	assert env.dones == []


def test_cancelled_legacy_sync_does_not_emit_done(env):
	speak(env)
	env.native.wait_calls(1)
	env.player.sync_release.set()
	env.native.respond()
	env.driver.speak(("legacy",))
	env.native.wait_calls(2)
	env.player.sync_entered.clear()
	env.player.sync_release.clear()
	call = in_thread(lambda: env.native.respond(markers=""))
	assert env.player.sync_entered.wait(WAIT_TIMEOUT)
	env.driver.cancel()
	finish(call)
	assert env.dones == []


@pytest.mark.parametrize("correlated", [False, True])
def test_terminated_driver_is_collected_while_late_native_callback_stays_callable(env, correlated):
	if correlated:
		speak(env)
		env.native.wait_calls(1)
		env.player.sync_release.set()
		env.native.respond()
	callback = env.native.callback
	driver_ref = weakref.ref(env.driver)
	touched = []
	env.driver._callback = lambda *args: touched.append("late driver access")
	env.driver.terminate()
	worker = segment_worker(env.driver)
	if worker is not None:
		worker.join(WAIT_TIMEOUT)
		assert not worker.is_alive()
	callback(None, 0, None)
	assert touched == []
	env.dones.clear()
	env.driver = None
	gc.collect()
	assert driver_ref() is None, "Retained native callback kept the terminated driver graph alive"
	callback(None, 0, None)
	assert touched == []


def queue_segment_behind_ordinary_speech(env):
	env.driver.speak(("legacy",))
	env.native.wait_calls(1)
	_, _, queued = speak(env, segment=18)
	eventually(lambda: queued_segment_jobs(env.driver))
	return queued


def test_cancel_releases_a_segment_queued_behind_ordinary_speech(env):
	queued = queue_segment_behind_ordinary_speech(env)
	env.driver.cancel()
	env.native.respond(markers="")
	_, _, events = speak(env, segment=19)
	env.native.wait_calls(2)
	env.player.sync_release.set()
	env.native.respond(markers="")
	wait_events(events)
	assert queued == []
	assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


def test_control_error_fails_a_segment_queued_behind_ordinary_speech(env):
	queued = queue_segment_behind_ordinary_speech(env)
	error = OSError("pause failed behind ordinary speech")

	def failed_pause(switch):
		raise error

	env.player.pause = failed_pause
	with pytest.raises(OSError):
		env.driver.pause(True)
	wait_events(queued)
	assert len(queued) == 1
	assert queued[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert queued[0].error is error


def test_legacy_speak_still_uses_parent_interface(env):
	env.driver.speak(("legacy",))
	env.native.wait_calls(1)
	env.player.sync_release.set()
	env.native.respond()
	assert env.indexes == [1]
	assert env.dones == [env.driver]
	# The ordinary path still idles once, when its queue is empty.
	assert env.player.idles == 1


def test_ordinary_speech_waits_for_contextual_final_sync(env):
	# Parity probe for the VE/Cerence ordinary-speech ownership finding: the
	# contextual final playback barrier keeps ordinary text out of native.
	entries = []
	original_speak = env.native.speak

	def recording_speak(token, text):
		entries.append((text, env.player.sync_release.is_set()))
		original_speak(token, text)

	env.native.ocSpeech_speak = env.native.ocSpeech_speak.__class__(recording_speak)
	_, context, events = speak(env)
	env.native.wait_calls(1)
	response = in_thread(lambda: env.native.respond(markers=""))
	assert env.player.sync_entered.wait(WAIT_TIMEOUT)
	finish(response)
	env.driver.speak(("ordinary",))
	assert len(env.native.calls) == 1, "Ordinary text entered native during the final sync"
	assert len(queued_speech(env.driver)) == 1
	assert events == []
	env.player.sync_release.set()
	wait_events(events)
	env.native.wait_calls(2)
	assert [released for _, released in entries] == [False, True]
	env.native.respond(markers="")
	assert env.dones == [env.driver]
	assert len(events) == 1
	assert events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert (events[0].source_id, events[0].segment_id) == (context.source_id, context.segment_id)


def _hold_admission(env):
	held, release = Event(), Event()

	def hold():
		with env.driver._segmentHost.admission():
			held.set()
			assert release.wait(HOLD_TIMEOUT)

	holder = in_thread(hold)
	assert held.wait(WAIT_TIMEOUT)
	return holder, release


def _wait_gate_held(env):
	eventually(lambda: not stop_gate_clear(env.driver), message="cancel never raised the stop gate")


def test_pause_between_fault_capture_and_delivery_does_not_reach_the_player(env, monkeypatch):
	captured, release_delivery = Event(), Event()
	original_delivery = env.driver._controlFault.deliver

	def held_delivery(failure):
		captured.set()
		assert release_delivery.wait(HOLD_TIMEOUT)
		return original_delivery(failure)

	monkeypatch.setattr(env.driver._controlFault, "deliver", held_delivery)
	speak(env)
	env.native.wait_calls(1)
	pauses = []
	original_pause = env.player.pause
	env.player.pause = lambda switch: (pauses.append(switch), original_pause(switch))
	faulting = in_thread(lambda: env.driver._failSegmentControl(OSError("player failed")))
	assert captured.wait(WAIT_TIMEOUT)
	try:
		pausing = in_thread(lambda: env.driver.pause(True))
		assert pausing.done.wait(WAIT_TIMEOUT) and pausing.errors == []
		assert pauses == []
		assert segment_paused(env.driver) is False
	finally:
		release_delivery.set()
	assert faulting.done.wait(WAIT_TIMEOUT)
	assert stop_gate_clear(env.driver)


def test_cancel_whose_player_stop_fails_releases_the_stop_gate(env):
	speak(env)
	env.native.wait_calls(1)

	def failing_stop():
		raise OSError("stop failed")

	original_stop = env.player.stop
	env.player.stop = failing_stop
	try:
		with pytest.raises(OSError):
			env.driver.cancel()
		assert stop_gate_clear(env.driver)
	finally:
		env.player.stop = original_stop


def test_player_created_during_an_inflight_stop_is_not_paused(env):
	env.driver._player = None
	speak(env)
	env.native.wait_calls(1)
	env.driver.pause(True)
	pauses = []
	original_pause = env.player.pause
	env.player.pause = lambda switch: (pauses.append(switch), original_pause(switch))
	holder, release = _hold_admission(env)
	cancelling = in_thread(env.driver.cancel)
	try:
		_wait_gate_held(env)
		assert segment_paused(env.driver) is True
		call = in_thread(lambda: env.native.respond(markers=""))
		eventually(lambda: has_player(env.driver))
		assert True not in pauses
	finally:
		release.set()
		env.player.sync_release.set()
	assert (
		holder.done.wait(WAIT_TIMEOUT) and cancelling.done.wait(WAIT_TIMEOUT) and call.done.wait(WAIT_TIMEOUT)
	)
	assert stop_gate_clear(env.driver)


def test_ordinary_player_open_failure_fails_only_its_sentence(env):
	original_open = env.player.open
	opens = []

	def open_once():
		# NVDA's speak() opens first; the worker's open for the first sentence fails.
		opens.append(current_thread().name)
		if opens.count("WorldVoice OneCore") == 1 and opens[-1] == "WorldVoice OneCore":
			raise OSError("audio device busy")
		original_open()

	env.player.open = open_once
	dones = []
	first_done = Event()
	original_done = env.outer.synthDoneSpeaking.notify

	def completed(**kwargs):
		original_done(**kwargs)
		dones.append(kwargs.get("synth"))
		first_done.set()

	env.outer.synthDoneSpeaking.notify = completed
	env.driver.speak(("first",))
	# The skipped sentence still completes, or the scheduler waits for it until a cancel.
	assert first_done.wait(WAIT_TIMEOUT), "a sentence that could not open the player never completed"
	quiet_period()
	assert dones == [env.driver]
	assert segment_host(env.driver).control_error is None
	env.driver.speak(("second",))
	env.native.wait_calls(1)
	assert len(env.native.calls) == 1 and "second" in env.native.calls[0]


def test_segment_player_open_failure_fails_only_its_segment(env):
	error = OSError("audio device gone")
	original_open = env.player.open

	def fail_open():
		raise error

	env.player.open = fail_open
	_, _, events = speak(env)
	wait_events(events)
	assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert events[0].error is error
	assert segment_host(env.driver).control_error is None
	env.player.open = original_open
	_, _, drained = speak(env, segment=18)
	env.native.wait_calls(1)
	env.player.sync_release.set()
	env.native.respond(markers="")
	wait_events(drained)
	assert [event.kind for event in drained] == [env.rt.models.EventKind.SEGMENT_DRAINED]


def test_player_replacement_failure_fails_only_its_segment(env, monkeypatch):
	error = OSError("no device for this rate")

	def failing_player(**kwargs):
		raise error

	monkeypatch.setattr(env.base.nvwave, "WavePlayer", failing_player)
	_, _, events = speak(env)
	env.native.wait_calls(1)
	# The old player's idle before the replacement must not wait.
	env.player.sync_release.set()
	env.player.samplesPerSec = 2000
	env.native.respond(markers="")
	wait_events(events)
	assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert events[0].error is error
	assert segment_host(env.driver).control_error is None


@pytest.mark.parametrize("failure", ["feed", "sync"])
def test_ordinary_callback_failure_fails_only_its_sentence(env, failure):
	# A failed feed is recorded by the lease; a failed sync() reaches the raw player, so only
	# _legacyCallback records it. Unrecorded, the sentence would never publish its DONE.
	speak(env)
	env.native.wait_calls(1)
	env.player.sync_release.set()
	env.native.respond()
	stops = env.player.stops
	env.player.error = failure
	env.driver.speak(("first",))
	env.native.wait_calls(2)
	env.native.respond(markers="")
	eventually(lambda: env.dones == [env.driver], message="the failed sentence never completed")
	quiet_period()
	assert env.dones == [env.driver]
	assert segment_host(env.driver).control_error is None
	assert env.player.stops > stops
	env.player.error = None
	env.driver.speak(("second",))
	env.native.wait_calls(3)
	assert "second" in env.native.calls[-1]


def test_ordinary_native_speak_failure_fails_only_its_sentence(env):
	dones = []
	done = Event()
	original_done = env.outer.synthDoneSpeaking.notify

	def completed(**kwargs):
		original_done(**kwargs)
		dones.append(kwargs.get("synth"))
		done.set()

	env.outer.synthDoneSpeaking.notify = completed
	env.native.submit_error = OSError("speech engine busy")
	env.driver.speak(("first",))
	assert done.wait(WAIT_TIMEOUT), "a sentence the engine rejected never completed"
	quiet_period()
	assert dones == [env.driver]
	assert segment_host(env.driver).control_error is None
	env.native.submit_error = None
	env.driver.speak(("second",))
	env.native.wait_calls(1)
	assert "second" in env.native.calls[-1]


def _leased_player_class(env):
	return sys.modules[type(segment_host(env.driver)).__module__].LeasedPlayer


def test_stop_failure_latches_and_rejects_ordinary_speech(env):
	token, _, _ = speak(env)
	env.native.wait_calls(1)
	error = OSError("stop failed")

	def failing_stop():
		raise error

	original_stop = env.player.stop
	env.player.stop = failing_stop
	try:
		# A token cancelled before core.cancel(): the drain path discards its audio
		# through the strategy's stop_player.
		token.cancel()
		env.native.respond(markers="")
		eventually(lambda: segment_host(env.driver).control_error is not None)
	finally:
		env.player.stop = original_stop
	assert segment_host(env.driver).control_error is error
	with pytest.raises(OSError) as rejected:
		env.driver.speak(("next",))
	assert rejected.value is error
	assert len(env.native.calls) == 1


def test_player_is_leased_after_seed_construction_and_replacement(env):
	leased = _leased_player_class(env)
	assert isinstance(env.driver._player, leased)
	assert env.driver._player._player is env.player
	_, _, events = speak(env)
	env.native.wait_calls(1)
	env.player.sync_release.set()
	# A WAV at another rate makes NVDA build a replacement player.
	env.player.samplesPerSec = 2000
	env.native.respond(markers="")
	wait_events(events)
	assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
	assert isinstance(env.driver._player, leased)
	assert env.driver._player._player is env.player
	env.driver._player = None
	assert env.driver._player is None


def test_index_fires_after_the_record_retired(env):
	_, _, events = speak(env)
	env.native.wait_calls(1)
	record = native_call(env.driver)
	held = []
	original_feed = env.player.feed

	def deferred_index_feed(data, size=None, onDone=None):
		# Like the real player: the index callback fires when that audio plays, later.
		original_feed(data, size)
		if onDone:
			held.append(onDone)

	env.player.feed = deferred_index_feed
	env.native.respond(markers="1:2000")
	eventually(lambda: record.closed, message="The worker did not retire the record")
	assert held and env.indexes == []
	for onDone in held:
		onDone()
	assert env.indexes == [1]
	env.player.sync_release.set()
	wait_events(events)
	assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


def test_cancelled_segment_feed_is_stopped_by_the_lease_before_successor(env):
	speak(env)
	env.native.wait_calls(1)
	env.player.feed_entered.clear()
	env.player.feed_release.clear()
	call = in_thread(lambda: env.native.respond(markers=""))
	assert env.player.feed_entered.wait(WAIT_TIMEOUT)
	env.driver.cancel()
	speak(env, segment=18)
	assert len(env.native.calls) == 1
	final_stop, release_stop = Event(), Event()
	original_stop = env.player.stop
	stop_threads = []

	def blocked_final_stop():
		stop_threads.append(current_thread())
		final_stop.set()
		assert release_stop.wait(HOLD_TIMEOUT)
		original_stop()

	env.player.stop = blocked_final_stop
	env.player.feed_release.set()
	stopped = final_stop.wait(WAIT_TIMEOUT)
	advanced = holds_within(env.native.condition, lambda: len(env.native.calls) >= 2)
	release_stop.set()
	finish(call)
	assert stopped, "The segment feed queued audio after cancel without a final stop"
	assert not advanced, "New native work started before the cancelled feed's final stop"
	# The lifecycle also stops the cancelled segment; the lease's stop is the one on the
	# callback thread that fed, before the callback returns.
	assert call.thread in stop_threads, "The lease did not stop again after the late feed"
	env.native.wait_calls(2)


def test_cancel_pause_lock_stop_failure_delivers_after_lock_release(env, monkeypatch):
	speak(env)
	env.native.wait_calls(1)
	error = OSError("stop failed under the pause lock")
	stops = []
	original_stop = env.player.stop

	def second_stop_fails():
		# cancel's first stop succeeds; the one under the pause lock fails.
		stops.append(True)
		if len(stops) == 2:
			raise error
		original_stop()

	pause_lock_free = []
	original_delivery = env.driver._controlFault.deliver

	def observed_delivery(fault):
		if fault is not None:
			lock = env.driver._segmentPauseLock
			acquired = lock.acquire(blocking=False)
			pause_lock_free.append(acquired)
			if acquired:
				lock.release()
		return original_delivery(fault)

	monkeypatch.setattr(env.driver._controlFault, "deliver", observed_delivery)
	env.player.stop = second_stop_fails
	with pytest.raises(OSError) as raised:
		env.driver.cancel()
	assert raised.value is error
	assert pause_lock_free == [True]
	assert segment_host(env.driver).control_error is error
	assert stop_gate_clear(env.driver)


def test_segment_conversion_without_prosody_options_uses_the_pre_api5_converter(env, monkeypatch):
	used = []

	def spy(name):
		converter = getattr(env.base, name)

		class Spy(converter):
			def __init__(self, *args):
				used.append(name)
				super().__init__(*args)

		monkeypatch.setattr(env.base, name, Spy)

	spy("_OcSsmlConverter")
	spy("_OcPreAPI5SsmlConverter")
	# NVDA asks the native helper once; older Windows OneCore voices have no prosody options.
	env.driver.supportsProsodyOptions = False
	speak(env)
	env.native.wait_calls(1)
	assert used == ["_OcPreAPI5SsmlConverter"]


def test_cancel_before_any_audio_stops_nothing(env):
	env.driver._player = None
	_, _, cancelled = speak(env)
	env.native.wait_calls(1)
	env.driver.cancel()
	# The cancelled utterance's callback still arrives, and creates no player.
	env.native.respond(markers="")
	assert segment_host(env.driver).control_error is None
	assert segment_host(env.driver).faulted is False
	_, context, events = speak(env, segment=18)
	env.native.wait_calls(2)
	env.player.sync_release.set()
	env.native.respond(markers="")
	wait_events(events)
	assert cancelled == []
	assert [(event.kind, event.segment_id) for event in events] == [
		(env.rt.models.EventKind.SEGMENT_DRAINED, context.segment_id),
	]


def test_a_token_cancelled_queued_segment_is_abandoned_unopened(env):
	opens = []
	original_open = env.player.open
	env.player.open = lambda: (opens.append(current_thread().name), original_open())[1]
	env.driver.speak(("alpha",))
	env.native.wait_calls(1)
	token, _, cancelled = speak(env, segment=18, commands=("bravo",))
	eventually(lambda: queued_segment_jobs(env.driver))
	opened_before = len(opens)
	# An external token cancels without calling the driver's cancel.
	token.cancel()
	env.native.respond(markers="")
	_, context, events = speak(env, segment=19, commands=("charlie",))
	env.native.wait_calls(2)
	env.player.sync_release.set()
	env.native.respond(markers="")
	wait_events(events)
	assert [event.segment_id for event in events] == [context.segment_id]
	assert cancelled == []
	assert not any("bravo" in text for text in env.native.calls)
	# Only charlie's worker opened the player after bravo was queued.
	assert len(opens) == opened_before + 1


def test_a_segment_cancelled_while_the_player_opens_is_never_spoken(env):
	tokens = []
	original_open = env.player.open

	def open_and_cancel():
		original_open()
		if tokens:
			tokens.pop().cancel()

	env.player.open = open_and_cancel
	# The token is in place before the segment can reach the worker's open().
	tokens.append(env.scheduler.CancellationToken())
	_, _, cancelled = speak(env, commands=("bravo",), token=tokens[0])
	_, context, events = speak(env, segment=18, commands=("charlie",))
	env.native.wait_calls(1)
	env.player.sync_release.set()
	env.native.respond(markers="")
	wait_events(events)
	assert [event.segment_id for event in events] == [context.segment_id]
	assert cancelled == []
	assert len(env.native.calls) == 1 and "charlie" in env.native.calls[0]


def wav_response(frames=8):
	"""A OneCore WAV, as Native.respond builds it: the fixed header, then the PCM."""
	stream = io.BytesIO()
	with wave.open(stream, "wb") as wav:
		wav.setnchannels(1)
		wav.setsampwidth(2)
		wav.setframerate(1000)
		wav.writeframes(b"\x01\x02" * frames)
	raw = bytearray(stream.getvalue())
	raw[16:20] = (18).to_bytes(4, "little")
	raw[36:36] = b"\x00\x00"
	raw[4:8] = (len(raw) - 8).to_bytes(4, "little")
	return bytes(raw)


@pytest.mark.parametrize("truncation", ["header_before_player", "payload"])
def test_truncated_wav_fails_the_segment_without_feeding(env, monkeypatch, truncation):
	# An exception escaping a ctypes callback is only reported as unraisable; collect those.
	unraisable = []
	monkeypatch.setattr(sys, "unraisablehook", unraisable.append)
	header = env.base.WAVE_HEADER_LENGTH
	if truncation == "header_before_player":
		env.driver._player = None
		raw, length = bytes(64), 10
	else:
		raw = wav_response(frames=8)
		length = header + 4
	_, context, events = speak(env)
	env.native.wait_calls(1)
	buffer = ctypes.create_string_buffer(raw, len(raw) + 64)
	# The native callback must return normally whatever the audio holds.
	env.native.callback(ctypes.addressof(buffer), length, "")
	assert unraisable == []
	wait_events(events)
	assert [(event.kind, event.segment_id) for event in events] == [
		(env.rt.models.EventKind.SEGMENT_FAILED, context.segment_id),
	]
	assert isinstance(events[0].error, ValueError)
	assert "truncated" in str(events[0].error)
	assert env.player.fed == []
	_, context, following = speak(env, segment=18)
	env.native.wait_calls(2)
	env.player.sync_release.set()
	env.native.respond(markers="")
	wait_events(following)
	assert [(event.kind, event.segment_id) for event in following] == [
		(env.rt.models.EventKind.SEGMENT_DRAINED, context.segment_id),
	]


def test_cancel_during_a_paused_final_idle_publishes_no_done(env):
	idle_entered, idle_release = Event(), Event()
	idle = env.player.idle

	def held_idle():
		idle_entered.set()
		assert idle_release.wait(HOLD_TIMEOUT)
		idle()

	env.player.idle = held_idle
	env.player.sync_release.set()
	env.driver.speak(("last",))
	env.native.wait_calls(1)
	call = in_thread(lambda: env.native.respond(markers=""))
	assert idle_entered.wait(WAIT_TIMEOUT)
	# Paused during the final idle: DONE waits for the resume, and a cancel replaces it.
	env.driver.pause(True)
	idle_release.set()
	eventually(lambda: segment_paused(env.driver) and not call.done.is_set())
	env.driver.cancel()
	finish(call)
	assert env.dones == []
