import ctypes
import sys
from io import BytesIO
from threading import Event, Thread, current_thread
from types import SimpleNamespace

import pytest
from runtime_harness import live_operations, pending_records, segment_host, segment_lifecycle
from waiting import HOLD_TIMEOUT, WAIT_TIMEOUT, eventually, stays_unset
from worldvoice_cancel_wrapper_harness import (
	Token,
	background_idle,
	buffered_audio,
	callback_handler,
	emit,
	end_process,
	inner_stop_flag,
	leased_player,
	load_real_driver_with_native_stubs,
	native_call,
	native_callback,
	native_message,
	player_of,
	queued_begins,
	queued_done_speaking,
	real_player,
	sonic_state,
	stop_gate_clear,
	termination_done,
)


@pytest.fixture(params=["VE", "Cerence"])
def env(request, monkeypatch):
	# The harness reloads runtime models for every engine case. Reload the
	# coordinator too so its event enum belongs to that same runtime copy.
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime._segmentLifecycle", raising=False)
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)
	result = load_real_driver_with_native_stubs(monkeypatch, request.param)
	result.core = result.new_core()
	result.core._veCallbackHandler._ensureSonicStream = lambda: False
	result.events, result.indexes, result.dones = [], [], []
	monkeypatch.setattr(
		result.original_driver.synthIndexReached,
		"notify",
		lambda **kwargs: result.indexes.append(kwargs["index"]),
	)
	monkeypatch.setattr(
		result.original_driver.synthDoneSpeaking,
		"notify",
		lambda **kwargs: result.dones.append(kwargs),
	)
	return result


def prove_fake_quiescence(env, monkeypatch):
	# A test-only contract promises this native call will not start callbacks
	# after return. It never changes the production capability result.
	monkeypatch.setattr(env.core, "_confirmNativeQuiescence", lambda native: None)


def run_thread(action):
	errors, done = [], Event()

	def run():
		try:
			action()
		except Exception as error:  # noqa: BLE001 - collected and asserted in the test thread
			errors.append(error)
		finally:
			done.set()

	thread = Thread(target=run, daemon=True)
	thread.start()
	return thread, done, errors


def finish(call):
	assert call[1].wait(WAIT_TIMEOUT)
	assert call[2] == []


def wait_for(predicate):
	eventually(predicate)


def lifecycle_of(env):
	return segment_lifecycle(segment_host(env.core))


def settle_segment(env, context):
	# speak_segment returns before delivery; wait for this segment's
	# operation to be published or discarded.
	lifecycle = lifecycle_of(env)
	wait_for(lambda: all(operation.work.context is not context for operation in live_operations(lifecycle)))


def settle_worker(env):
	# Ordinary speech is queued to the inner BgThread; wait until it ran.
	wait_for(lambda: background_idle(env.core))


def queued_ordinary(env):
	return sum(task.record.operation is None for task in queued_begins(env.core))


def speak_ordinary(env, *args, **kwargs):
	result = env.core.speak(*args, **kwargs)
	settle_worker(env)
	return result


def speak(env, commands=("hello",), *, token=None, segment=17):
	token = token or Token()
	context = env.rt.models.PlaybackContext(object(), segment)

	def run():
		env.core.speak_segment(commands, token, context=context, on_event=env.events.append)
		settle_segment(env, context)

	return token, context, run_thread(run)


def test_shared_lifecycle_waits_for_chunk_callback_and_idle(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	feed_entered, feed_release, idle_entered, idle_release = Event(), Event(), Event(), Event()
	callbacks = []
	real_player(env.core).feed = lambda data: (feed_entered.set(), feed_release.wait(HOLD_TIMEOUT))
	real_player(env.core).idle = lambda: (idle_entered.set(), idle_release.wait(HOLD_TIMEOUT))

	def native(instance, text):
		# Artificial order: the real SDK sends ENDPROCESS last, on the calling thread.
		# Sending it first lets a chunk callback on another thread still be feeding when
		# the call returns, which is the only way to prove the BgThread waits for it
		# (wait_consumers) before retire and idle; ENDPROCESS sent after the return
		# would be refused.
		end_process(env, instance)
		callbacks.append(run_thread(lambda: emit(env, instance, index=31, end=False)))
		assert feed_entered.wait(WAIT_TIMEOUT)

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, context, call = speak(env)
	assert feed_entered.wait(WAIT_TIMEOUT)
	assert env.events == []
	assert not idle_entered.is_set()
	feed_release.set()
	wait_for(lambda: bool(callbacks))
	finish(callbacks[0])
	assert idle_entered.wait(WAIT_TIMEOUT)
	assert env.events == []
	idle_release.set()
	finish(call)
	wait_for(lambda: len(env.events) == 1)
	assert len(env.events) == 1
	assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert env.events[0].source_id is context.source_id
	assert env.events[0].segment_id == context.segment_id
	assert env.indexes == [31]


def test_shared_cancel_retires_guarded_feed_before_successor(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	feed_entered, feed_release, stop_entered, stop_release = Event(), Event(), Event(), Event()
	calls, callbacks = [], []
	real_player(env.core).feed = lambda data: (feed_entered.set(), feed_release.wait(HOLD_TIMEOUT))

	def stop():
		stop_entered.set()
		assert stop_release.wait(HOLD_TIMEOUT)

	real_player(env.core).stop = stop

	def native(instance, text):
		calls.append(text)
		if len(calls) == 1:
			callbacks.append(run_thread(lambda: emit(env, instance, index=41)))
			assert feed_entered.wait(WAIT_TIMEOUT)
		else:
			emit(env, instance, index=42)

	monkeypatch.setattr(env.native, "processText2Speech", native)
	token, _, first = speak(env)
	assert feed_entered.wait(WAIT_TIMEOUT)
	token.cancel()
	_, context, second = speak(env, segment=18)
	feed_release.set()
	assert stop_entered.wait(WAIT_TIMEOUT)
	assert calls == ["hello"]
	stop_release.set()
	# The callback thread can feed before native() records its handle.
	wait_for(lambda: bool(callbacks))
	finish(callbacks[0])
	finish(first)
	finish(second)
	wait_for(lambda: len(env.events) == 1)
	assert calls == ["hello", "hello"]
	assert env.indexes == [42]
	assert len(env.events) == 1
	assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert env.events[0].source_id is context.source_id
	assert env.events[0].segment_id == 18
	# Native callback admission stays closed after the successor retires.
	assert emit(env, env.opened[0][1], index=43) == [env.types.NUAN_E_TTS_USERSTOP]
	assert env.indexes == [42]


def test_terminal_listener_can_speak_successor(env, monkeypatch):
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
	token = Token()
	source = object()
	events = []
	first_context = env.rt.models.PlaybackContext(source, 17)
	second_context = env.rt.models.PlaybackContext(source, 18)

	def listener(event):
		events.append(event)
		if event.segment_id == 17:
			env.core.speak_segment(("second",), Token(), context=second_context, on_event=listener)

	first = run_thread(
		lambda: env.core.speak_segment(
			("first",),
			token,
			context=first_context,
			on_event=listener,
		),
	)
	finish(first)
	wait_for(lambda: len(events) == 2)
	assert [event.segment_id for event in events] == [17, 18]


def test_speak_returns_before_native_synthesis(env, monkeypatch):
	# Like the original add-on: speak() queues to the BgThread and returns.
	entered, release = Event(), Event()

	def native(instance, text):
		entered.set()
		assert release.wait(HOLD_TIMEOUT)
		end_process(env, instance)

	monkeypatch.setattr(env.native, "processText2Speech", native)
	call = run_thread(lambda: env.core.speak(("ordinary",)))
	try:
		assert entered.wait(WAIT_TIMEOUT)
		assert call[1].wait(WAIT_TIMEOUT), "speak() waited for native synthesis"
		assert env.dones == []
	finally:
		release.set()
	finish(call)
	settle_worker(env)
	assert len(env.dones) == 1


def test_settings_apply_in_call_order_with_speech(env, monkeypatch):
	# Like the original add-on: settings queue behind speech already requested.
	order = []
	entered, release = Event(), Event()

	def native(instance, text):
		if text == "first":
			entered.set()
			assert release.wait(HOLD_TIMEOUT)
		order.append(("spoken", text))
		end_process(env, instance)

	monkeypatch.setattr(env.native, "processText2Speech", native)
	monkeypatch.setattr(env.native, "setParamList", lambda instance, *values: order.append(("set", values)))
	first = run_thread(lambda: env.core.speak(("first",)))
	assert entered.wait(WAIT_TIMEOUT)
	env.core._set_volume(40)
	release.set()
	finish(first)
	env.core.speak(("second",))
	settle_worker(env)
	assert order == [("spoken", "first"), ("set", ((env.types.VE_PARAM_VOLUME, 40),)), ("spoken", "second")]


def test_cancel_drops_a_segment_queued_behind_the_worker(env, monkeypatch):
	# After a handoff the next segment can queue while the BgThread finishes
	# the previous retirement; cancel must retire it without a DONE.
	prove_fake_quiescence(env, monkeypatch)
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
	host = segment_host(env.core)
	retire = host.retire
	held, release = Event(), Event()

	def held_retire(record, **kwargs):
		result = retire(record, **kwargs)
		if not held.is_set():
			held.set()
			assert release.wait(HOLD_TIMEOUT)
		return result

	monkeypatch.setattr(host, "retire", held_retire)
	_, _, first = speak(env)
	try:
		assert held.wait(WAIT_TIMEOUT)
		context = env.rt.models.PlaybackContext(object(), 18)
		env.core.speak_segment(("second",), Token(), context=context, on_event=env.events.append)
		wait_for(lambda: queued_begins(env.core))
		env.core.cancel()
	finally:
		release.set()
	finish(first)
	settle_segment(env, context)
	settle_worker(env)
	assert all(event.segment_id != 18 for event in env.events)
	assert env.dones == []


def test_failed_ordinary_speech_still_publishes_done(env, monkeypatch):
	# speak() no longer raises, so a failed request must still release a
	# LEGACY_DONE waiter, as the original add-on's DoneSpeaking does.
	def fail(instance, text):
		raise OSError("native failed")

	monkeypatch.setattr(env.native, "processText2Speech", fail)
	speak_ordinary(env, ("ordinary",))
	assert len(env.dones) == 1
	assert real_player(env.core).idles == 0


def test_engine_settings_variant_waits_for_running_speech(env, monkeypatch):
	# The variant write joins the BgThread queue like every inner setting, so
	# it never runs on the same native instance as an in-flight synthesis.
	order = []
	entered, release = Event(), Event()

	def native(instance, text):
		entered.set()
		assert release.wait(HOLD_TIMEOUT)
		order.append(("spoken", text))
		end_process(env, instance)

	monkeypatch.setattr(env.native, "processText2Speech", native)
	monkeypatch.setattr(env.native, "setParamList", lambda instance, *values: order.append(("set", values)))
	monkeypatch.setattr(env.native, "getParamList", lambda instance, *ids: ["plain"] * len(ids))
	first = run_thread(lambda: env.core.speak(("first",)))
	assert entered.wait(WAIT_TIMEOUT)
	voice = object.__new__(env.module.Voice)
	voice.applyEngineSettings(
		env.core,
		SimpleNamespace(voice_id=env.core.voice, variant="default", waitfactor=2),
	)
	try:
		assert order == []
	finally:
		release.set()
	finish(first)
	settle_worker(env)
	assert order == [("spoken", "first"), ("set", ((env.types.VE_PARAM_VOICE_OPERATING_POINT, "plain"),))]


def test_parameter_read_never_reorders_queued_speech(env, monkeypatch):
	# A settings read on the main thread (synth.rate etc.) may overlap a
	# segment being queued on its lifecycle thread. Draining and re-putting
	# the queue there moved Begin behind Retire: a silent "drained" segment.
	prove_fake_quiescence(env, monkeypatch)
	spoken = []
	monkeypatch.setattr(
		env.native,
		"processText2Speech",
		lambda instance, text: (spoken.append(text), end_process(env, instance)),
	)
	monkeypatch.setattr(env.native, "getParamList", lambda instance, *ids: [50] * len(ids))
	core, bg = env.core, env.core._bgQueue
	hold = Event()
	bg.put(lambda: hold.wait(HOLD_TIMEOUT))
	reading, read_done, retired = Event(), Event(), Event()
	original_get, original_put, original_speak = bg.get_nowait, bg.put, core._speak

	def get_nowait():
		reading.set()
		return original_get()

	def put(task):
		if not retired.is_set() and getattr(current_thread(), "name", "") == "parameter read":
			assert retired.wait(WAIT_TIMEOUT)
		original_put(task)
		if isinstance(task, env.module._Retire):
			retired.set()

	def read():
		core.getParameter(core.voiceInstance, env.types.VE_PARAM_VOLUME)
		read_done.set()

	def racing_speak(instance, chunks):
		Thread(target=read, name="parameter read", daemon=True).start()
		wait_for(lambda: reading.is_set() or read_done.is_set())
		original_speak(instance, chunks)

	monkeypatch.setattr(bg, "get_nowait", get_nowait)
	monkeypatch.setattr(bg, "put", put)
	monkeypatch.setattr(core, "_speak", racing_speak)
	_, _, call = speak(env, ("hello",), segment=31)
	wait_for(lambda: retired.is_set())
	hold.set()
	finish(call)
	assert read_done.wait(WAIT_TIMEOUT)
	settle_worker(env)
	assert spoken == ["hello"]
	assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
	assert env.dones == []


def _ending_native(env, monkeypatch):
	def native(instance, text):
		end_process(env, instance)

	monkeypatch.setattr(env.native, "processText2Speech", native)


def _fails_once(errors, original=None):
	def call(*args):
		if errors:
			raise errors.pop()
		return original(*args) if original is not None else None

	return call


def test_drain_idle_failure_fails_only_its_segment(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	_ending_native(env, monkeypatch)
	player = real_player(env.core)
	error = OSError("idle failed")
	player.idle = _fails_once([error])
	_, first_context, first = speak(env)
	finish(first)
	assert [(event.kind, event.source_id, event.error) for event in env.events] == [
		(env.rt.models.EventKind.SEGMENT_FAILED, first_context.source_id, error),
	]
	# The drain or the lifecycle stopped the player for the successor instead of latching.
	assert player.stops >= 1
	assert segment_host(env.core).control_error is None
	_, second_context, second = speak(env, segment=18)
	finish(second)
	assert [(event.kind, event.source_id) for event in env.events[1:]] == [
		(env.rt.models.EventKind.SEGMENT_DRAINED, second_context.source_id),
	]


def test_drain_stop_failure_after_idle_failure_latches(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	calls = []

	def native(instance, text):
		calls.append(text)
		end_process(env, instance)

	monkeypatch.setattr(env.native, "processText2Speech", native)
	player = real_player(env.core)
	idle_error, stop_error = OSError("idle failed"), OSError("stop failed")
	player.idle = _fails_once([idle_error])
	player.stop = _fails_once([stop_error], player.stop)
	_, _, first = speak(env)
	finish(first)
	# The latch fails the accepted segment with the stop error before its idle error.
	assert [(event.kind, event.error) for event in env.events] == [
		(env.rt.models.EventKind.SEGMENT_FAILED, stop_error),
	]
	assert segment_host(env.core).control_error is stop_error
	spoken = len(calls)
	_, context, second = speak(env, segment=18)
	finish(second)
	assert [(event.kind, event.source_id, event.error) for event in env.events[1:]] == [
		(env.rt.models.EventKind.SEGMENT_FAILED, context.source_id, stop_error),
	]
	assert len(calls) == spoken


def test_terminate_waits_for_coordinator_stop(env, monkeypatch):
	idle_entered, idle_release, hook_entered, hook_release = Event(), Event(), Event(), Event()
	closed = Event()
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
	monkeypatch.setattr(env.native, "close", lambda instance: None)
	monkeypatch.setattr(env.native, "terminate", lambda: None)
	real_player(env.core).idle = lambda: (idle_entered.set(), idle_release.wait(HOLD_TIMEOUT))
	real_player(env.core).stop = idle_release.set
	real_player(env.core).close = closed.set
	request_stop = env.core._segmentHost.request_stop

	def delayed_stop(operation):
		hook_entered.set()
		assert hook_release.wait(HOLD_TIMEOUT)
		request_stop(operation)

	monkeypatch.setattr(env.core._segmentHost, "request_stop", delayed_stop)
	_, _, speech = speak(env)
	assert idle_entered.wait(WAIT_TIMEOUT)
	terminating = run_thread(env.core.terminate)
	assert hook_entered.wait(WAIT_TIMEOUT)
	stays_unset(closed)
	hook_release.set()
	finish(speech)
	finish(terminating)
	assert closed.is_set()


@pytest.mark.parametrize("cancel_kind", ["token", "direct"])
def test_speak_segment_returns_while_a_previous_sink_runs(env, monkeypatch, cancel_kind):
	# C3: speak_segment no longer waits for delivery, so a blocked sink of the
	# previous segment cannot hold the caller; cancellation keeps it silent.
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
	sink_entered, sink_release = Event(), Event()
	first_context = env.rt.models.PlaybackContext(object(), 17)

	def first_sink(event):
		sink_entered.set()
		assert sink_release.wait(HOLD_TIMEOUT)

	env.core.speak_segment(("first",), Token(), context=first_context, on_event=first_sink)
	assert sink_entered.wait(WAIT_TIMEOUT)
	token = Token()
	context = env.rt.models.PlaybackContext(object(), 18)
	second = run_thread(
		lambda: env.core.speak_segment(
			("second",),
			token,
			context=context,
			on_event=env.events.append,
		),
	)
	try:
		assert second[1].wait(WAIT_TIMEOUT), "speak_segment waited for an earlier delivery"
		if cancel_kind == "token":
			token.cancel()
		else:
			env.core.cancel()
	finally:
		sink_release.set()
	finish(second)
	settle_segment(env, context)
	assert env.events == []


@pytest.mark.parametrize("hook", ["stop", "idle"])
def test_player_hook_can_reenter_terminate(env, monkeypatch, hook):
	monkeypatch.setattr(env.native, "close", lambda instance: None)
	monkeypatch.setattr(env.native, "terminate", lambda: None)
	token = Token()
	if hook == "stop":
		monkeypatch.setattr(env.native, "processText2Speech", lambda *args: token.cancel())
	else:
		monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
	entered = Event()

	def reenter():
		if not entered.is_set():
			entered.set()
			env.core.terminate()

	setattr(real_player(env.core), hook, reenter)
	_, _, call = speak(env, token=token)
	assert entered.wait(WAIT_TIMEOUT)
	finish(call)
	assert termination_done(env.core).wait(WAIT_TIMEOUT)
	assert real_player(env.core).closes == 1


def test_native_constructor_owns_contextual_callback_before_first_open(env):
	instance = env.core.voiceInstance
	assert isinstance(
		callback_handler(env.core),
		getattr(env.module, "_Contextual" + env.engine + "Callback"),
	)
	assert env.opened[0][1] == instance
	assert env.opened[0][2] is native_callback(env.core)
	callback_handler(env.core)._feedBuf = BytesIO(b"keep")
	message = native_message(env.types, env.types.VE_MSG_ENDPROCESS, env.types.VE_OUTDATA())
	assert env.opened[0][2](instance, None, message) == env.types.NUAN_E_TTS_USERSTOP
	assert buffered_audio(callback_handler(env.core)) == b"keep"
	assert env.module.Voice.synthDriverClass is env.module.SynthDriver


@pytest.mark.parametrize("version,mode", [("2026.3", "wasapi"), ("2025.3", "legacy")])
def test_guarded_native_profiles_are_enabled_with_unverified_evidence(env, version, mode):
	support = env.core.get_segment_drain_support(nvda_version=version, audio_mode=mode)
	assert support.supported
	assert "unverified" in support.reason.lower()


def test_vocalizer_endprocess_is_not_segment_drain(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	entered, release = Event(), Event()

	def idle():
		entered.set()
		assert release.wait(HOLD_TIMEOUT)

	real_player(env.core).idle = idle
	monkeypatch.setattr(
		env.native,
		"processText2Speech",
		lambda instance, text: emit(env, instance, index=23),
	)
	_, context, call = speak(env)
	assert entered.wait(WAIT_TIMEOUT)
	assert env.events == []
	assert real_player(env.core).fed == [b"pcm"]
	assert env.indexes == [23]
	release.set()
	finish(call)
	assert len(env.events) == 1
	assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert env.events[0].source_id is context.source_id
	assert env.events[0].segment_id == 17
	assert env.dones == []


class WaitObservingCondition:
	"""Coordinator condition proxy that records which threads waited on it."""

	def __init__(self, condition):
		self._condition = condition
		self.waiters = set()

	def __enter__(self):
		return self._condition.__enter__()

	def __exit__(self, *exc):
		return self._condition.__exit__(*exc)

	def __getattr__(self, name):
		return getattr(self._condition, name)

	def wait(self, timeout=None):
		self.waiters.add(current_thread())
		return self._condition.wait(timeout)

	def wait_for(self, predicate, timeout=None):
		self.waiters.add(current_thread())
		return self._condition.wait_for(predicate, timeout)


def hold_contextual_final_idle(env, monkeypatch):
	"""Start a contextual segment and hold it inside its final player idle."""
	prove_fake_quiescence(env, monkeypatch)
	held = type("Held", (), {})()
	held.entered, held.release, held.finished = Event(), Event(), Event()
	held.native_calls = []

	def native(instance, text):
		held.native_calls.append((text, held.finished.is_set()))
		emit(env, instance)

	def idle():
		held.entered.set()
		assert held.release.wait(HOLD_TIMEOUT), "Test did not release the final idle"
		held.finished.set()

	monkeypatch.setattr(env.native, "processText2Speech", native)
	real_player(env.core).idle = idle
	# A stop releases a real blocked idle.
	real_player(env.core).stop = held.release.set
	held.token, held.context, held.contextual = speak(env)
	assert held.entered.wait(WAIT_TIMEOUT)
	assert env.events == []
	held.condition = WaitObservingCondition(lifecycle_of(env)._condition)
	lifecycle_of(env)._condition = held.condition
	return held


def start_ordinary_behind(held, env):
	# speak() returns once queued; the worker holds it behind the segment.
	ordinary = run_thread(lambda: env.core.speak(("ordinary",)))
	finish(ordinary)
	wait_for(lambda: queued_ordinary(env) == 1)
	return ordinary


def test_contextual_final_idle_keeps_ordinary_speech_out_of_native(env, monkeypatch):
	held = hold_contextual_final_idle(env, monkeypatch)
	try:
		ordinary = start_ordinary_behind(held, env)
		assert held.native_calls == [("hello", False)], (
			"Ordinary speech entered native during the contextual final idle"
		)
		assert queued_ordinary(env) == 1
	finally:
		held.release.set()
	finish(held.contextual)
	finish(ordinary)
	settle_worker(env)
	wait_for(lambda: len(env.events) == 1)
	assert held.native_calls == [("hello", False), ("ordinary", True)]
	assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert (env.events[0].source_id, env.events[0].segment_id) == (
		held.context.source_id,
		held.context.segment_id,
	)
	assert len(env.events) == 1


def test_cancel_during_contextual_final_idle_releases_waiting_ordinary(env, monkeypatch):
	held = hold_contextual_final_idle(env, monkeypatch)
	try:
		ordinary = start_ordinary_behind(held, env)
		assert held.native_calls == [("hello", False)]
		env.core.cancel()
	finally:
		held.release.set()
	finish(held.contextual)
	finish(ordinary)
	settle_worker(env)
	# Like the original add-on, cancel drops queued speech and keeps its DoneSpeaking; that
	# request was cancelled, so it publishes no DONE.
	assert held.native_calls == [("hello", False)]
	assert env.dones == []
	# The discarded segment's record is forgotten on the lifecycle's delivery thread.
	host = segment_host(env.core)
	eventually(
		lambda: not pending_records(host),
		message=lambda: f"the discarded segment's record stayed pending: {pending_records(host)}",
	)
	eventually(lambda: not live_operations(lifecycle_of(env)))
	assert env.events == []


@pytest.mark.parametrize("ordinary_seals_first", [False, True])
def test_terminate_during_contextual_final_idle_with_waiting_ordinary(
	env,
	monkeypatch,
	ordinary_seals_first,
):
	monkeypatch.setattr(env.native, "close", lambda instance: None)
	monkeypatch.setattr(env.native, "terminate", lambda: None)
	held = hold_contextual_final_idle(env, monkeypatch)
	closed = Event()
	real_player(env.core).close = closed.set
	calls = []
	if ordinary_seals_first:
		# Coordinator termination stops the contextual idle and frees the
		# waiting ordinary request. Let that request seal driver termination
		# before terminate() reaches its own driver cancel.
		original_cancel = env.core.cancel

		def late_cancel():
			# The inner terminate on the ordinary thread also cancels.
			if current_thread() is not calls[0][0]:
				assert calls[0][1].wait(WAIT_TIMEOUT), "Ordinary request did not finish first"
			original_cancel()

		monkeypatch.setattr(env.core, "cancel", late_cancel)
	try:
		ordinary = start_ordinary_behind(held, env)
		calls.append(ordinary)
		assert held.native_calls == [("hello", False)]
		terminating = run_thread(env.core.terminate)
		finish(terminating)
	finally:
		held.release.set()
	finish(held.contextual)
	assert ordinary[1].wait(WAIT_TIMEOUT)
	# The queued request returned at once; terminate's cancel dropped it.
	assert ordinary[2] == []
	assert held.native_calls == [("hello", False)]
	assert closed.is_set()
	assert env.events == []


def test_multichunk_langchange_has_one_work_and_final_drain(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	change = __import__("speech.commands", fromlist=["LangChangeCommand"]).LangChangeCommand()
	change.lang = "fr"
	monkeypatch.setattr(env.core, "getVoiceNameForLanguage", lambda language: "fr", raising=False)
	monkeypatch.setattr(env.module, "split_speech_text_pieces", lambda text: [text + "1", text + "2"])
	calls, works = [], []

	def native(instance, text):
		calls.append((instance.pHandleData, text))
		works.append(native_call(env.core).record)
		emit(env, instance, index=len(calls))

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, _, call = speak(env, ("hello", change, "bonjour"))
	finish(call)
	assert len(calls) == 4
	assert [item[0] for item in calls] == [1, 1, 2, 2]
	assert all(work is works[0] for work in works)
	assert env.indexes == [1, 2, 3, 4]
	assert len(env.opened) == 2
	assert all(opened[2] is native_callback(env.core) for opened in env.opened)
	assert len(env.events) == 1
	assert real_player(env.core).idles == 1


@pytest.mark.parametrize("cancel_kind", ["token", "direct", "inner-clear"])
def test_cancelled_idle_cannot_complete_segment(env, monkeypatch, cancel_kind):
	prove_fake_quiescence(env, monkeypatch)
	entered, release = Event(), Event()
	real_player(env.core).idle = lambda: (entered.set(), release.wait(HOLD_TIMEOUT))
	real_player(env.core).stop = release.set
	monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: emit(env, instance))
	token, _, call = speak(env)
	assert entered.wait(WAIT_TIMEOUT)
	if cancel_kind == "token":
		token.cancel()
	else:
		env.core.cancel()
		if cancel_kind == "inner-clear":
			# The inner driver's queued clear of its own stop flag revives nothing.
			inner_stop_flag(callback_handler(env.core)).clear()
	release.set()
	finish(call)
	assert env.events == []


@pytest.mark.parametrize("fault", ["feed", "idle", "write", "read", "flush", "marker", "native"])
def test_processing_errors_latch_failure_on_original_context(env, monkeypatch, fault):
	prove_fake_quiescence(env, monkeypatch)

	def fail(*args, **kwargs):
		raise OSError(f"{fault} failed")

	if fault in ("feed", "idle"):
		setattr(real_player(env.core), fault, fail)
	elif fault == "marker":
		monkeypatch.setattr(env.original_driver.synthIndexReached, "notify", fail)
	elif fault in ("write", "read", "flush"):

		class Sonic:
			def writeShort(self, *args):
				if fault == "write":
					fail()

			def readShort(self):
				if fault == "read":
					fail()
				return b"tail"

			def flush(self):
				if fault == "flush":
					fail()

		callback = callback_handler(env.core)

		def sonic():
			callback.sonicStream = Sonic()
			callback._sonicEnabled = True
			return True

		callback._ensureSonicStream = sonic
	results = []

	def native(instance, text):
		if fault == "native":
			fail()
		results.extend(emit(env, instance, index=9))

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, context, call = speak(env)
	finish(call)
	assert len(env.events) == 1
	assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert env.events[0].source_id is context.source_id
	assert str(env.events[0].error) == f"{fault} failed"
	assert env.dones == []
	if fault not in ("idle", "native"):
		assert env.types.NUAN_E_TTS_USERSTOP in results


def test_explicit_activation_override_allows_successor_after_idle(env, monkeypatch):
	calls = []
	monkeypatch.setattr(
		env.native,
		"processText2Speech",
		lambda instance, text: (calls.append(text), end_process(env, instance)),
	)
	_, _, first = speak(env)
	finish(first)
	assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
	_, _, second = speak(env, segment=18)
	finish(second)
	assert env.events[1].kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert calls == ["hello", "hello"]
	callback_handler(env.core)._feedBuf = BytesIO(b"new")
	assert emit(env, env.core.voiceInstance) == [env.types.NUAN_E_TTS_USERSTOP]
	assert buffered_audio(callback_handler(env.core)) == b"new"


def test_cancel_stop_in_progress_blocks_next_native_call(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	entered, release = Event(), Event()
	real_player(env.core).stop = lambda: (entered.set(), release.wait(HOLD_TIMEOUT))
	cancelling = run_thread(env.core.cancel)
	assert entered.wait(WAIT_TIMEOUT)
	native_entered = Event()
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: native_entered.set())
	_, _, call = speak(env)
	stays_unset(native_entered)
	release.set()
	finish(cancelling)
	finish(call)
	assert len(env.events) == 1


def test_foreign_instance_endprocess_does_not_touch_current_buffer(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	callback = callback_handler(env.core)

	def native(instance, text):
		callback._feedBuf = BytesIO(b"current")
		foreign = env.types.VE_HSAFE()
		foreign.pHandleData = 123
		result = callback(
			foreign,
			None,
			native_message(env.types, env.types.VE_MSG_ENDPROCESS, env.types.VE_OUTDATA()),
		)
		assert result == env.types.NUAN_E_TTS_USERSTOP
		assert buffered_audio(callback) == b"current"

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, _, call = speak(env)
	finish(call)
	assert real_player(env.core).fed == []


def test_anonymous_done_never_completes_context(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)

	def native(instance, text):
		env.core._onIndexReached(None)
		assert env.events == []

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, _, call = speak(env)
	finish(call)
	assert len(env.events) == 1
	assert env.dones == []


def test_native_userstop_without_cancel_is_failure(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: env.types.NUAN_E_TTS_USERSTOP)
	_, _, call = speak(env)
	finish(call)
	assert len(env.events) == 1
	assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert "USERSTOP" in str(env.events[0].error)


def test_direct_cancel_after_idle_return_still_invalidates_original_work(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
	returned, release = Event(), Event()
	retire = env.core._segmentHost.retire

	def after_native(record, **kwargs):
		returned.set()
		assert release.wait(HOLD_TIMEOUT)
		return retire(record, **kwargs)

	monkeypatch.setattr(env.core._segmentHost, "retire", after_native)
	_, _, call = speak(env)
	assert returned.wait(WAIT_TIMEOUT)
	env.core.cancel()
	release.set()
	finish(call)
	assert env.events == []


def test_cancel_discards_sonic_internal_tail_before_next_segment(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)

	class Sonic:
		def __init__(self, tail):
			self.tail = tail
			self.flushed = False

		def writeShort(self, *args):
			pass

		def readShort(self):
			return self.tail if self.flushed else b""

		def flush(self):
			self.flushed = True

	streams = [Sonic(b"OLDTAIL"), Sonic(b"NEWTAIL")]
	callback = callback_handler(env.core)

	def sonic():
		if callback.sonicStream is None:
			callback.sonicStream = streams.pop(0)
			callback._sonicEnabled = True
		return True

	callback._ensureSonicStream = sonic
	calls = []

	def native(instance, text):
		calls.append(text)
		emit(env, instance, end=len(calls) > 1)
		if len(calls) == 1:
			env.core.cancel()

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, _, old = speak(env)
	finish(old)
	_, _, new = speak(env, segment=18)
	finish(new)
	assert real_player(env.core).fed == [b"NEWTAIL"]
	assert [event.segment_id for event in env.events] == [18]


def test_real_sonic_initialization_failure_uses_native_pcm_fallback(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	callback = callback_handler(env.core)
	callback._ensureSonicStream = env.original_driver.VECallback._ensureSonicStream.__get__(callback)
	monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: emit(env, instance))
	_, _, call = speak(env)
	finish(call)
	assert sonic_state(callback).init_tried
	assert not sonic_state(callback).enabled
	assert real_player(env.core).fed == [b"pcm"]
	assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_late_endprocess_outside_call_preserves_next_buffer(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: emit(env, instance))
	_, _, call = speak(env)
	finish(call)
	callback = callback_handler(env.core)
	callback._feedBuf = BytesIO(b"next buffer")
	result = callback(
		env.core.voiceInstance,
		None,
		native_message(env.types, env.types.VE_MSG_ENDPROCESS, env.types.VE_OUTDATA()),
	)
	assert result == env.types.NUAN_E_TTS_USERSTOP
	assert buffered_audio(callback) == b"next buffer"


def test_cancelled_native_userstop_is_silent_and_publishes_no_done(env, monkeypatch):
	def native(instance, text):
		env.core.cancel()
		return env.types.NUAN_E_TTS_USERSTOP

	monkeypatch.setattr(env.native, "processText2Speech", native)
	speak_ordinary(env, ("legacy",))
	assert env.dones == []
	assert env.events == []


def test_callback_lease_holds_bookmark_handler_before_next_call(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	entered, release, callback_ready = Event(), Event(), Event()

	def index(**kwargs):
		entered.set()
		assert release.wait(HOLD_TIMEOUT)

	monkeypatch.setattr(env.original_driver.synthIndexReached, "notify", index)
	calls, callbacks = [], []

	def native(instance, text):
		calls.append(text)
		if len(calls) == 1:
			callbacks.append(run_thread(lambda: emit(env, instance, index=7)))
			callback_ready.set()
			assert entered.wait(WAIT_TIMEOUT)

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, _, first = speak(env)
	assert entered.wait(WAIT_TIMEOUT)
	assert callback_ready.wait(WAIT_TIMEOUT)
	env.core.cancel()
	_, _, second = speak(env, segment=18)
	assert calls == ["hello"]
	release.set()
	finish(callbacks[0])
	finish(first)
	finish(second)
	assert [event.segment_id for event in env.events] == [18]


@pytest.mark.parametrize("kind", ["empty", "index", "break"])
def test_zero_audio_segments_still_wait_for_real_idle(env, monkeypatch, kind):
	prove_fake_quiescence(env, monkeypatch)
	from speech import commands

	sequence = ()
	if kind == "index":
		index = commands.IndexCommand()
		index.index = 23
		sequence = (index,)
	elif kind == "break":
		pause = commands.BreakCommand()
		pause.time = 20
		sequence = (pause,)
	entered, release = Event(), Event()
	real_player(env.core).idle = lambda: (entered.set(), release.wait(HOLD_TIMEOUT))
	# A call that produces no audio still ends with ENDPROCESS.
	monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: end_process(env, instance))
	_, _, call = speak(env, sequence)
	assert entered.wait(WAIT_TIMEOUT)
	assert env.events == []
	release.set()
	finish(call)
	assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_pause_holds_completion_after_real_idle(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	env.core.pause(True)
	entered = Event()
	real_player(env.core).idle = entered.set
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
	_, _, call = speak(env)
	assert entered.wait(WAIT_TIMEOUT)
	stays_unset(call[1])
	env.core.pause(False)
	finish(call)
	assert len(env.events) == 1


@pytest.mark.parametrize("status", [0, 0x80000807, 0xFFFFFFFF])
def test_raw_status_survives_installed_ctypes_errcheck(env, monkeypatch, status):
	native_function = env.native.veDll.ve_ttsProcessText2Speech
	# The real installed checker returns None for OK and USERSTOP.
	native_function.errcheck = env.native.veCheckForError
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: status)
	if status == 0xFFFFFFFF:
		with pytest.raises(env.types.VeError):
			env.module.ProcessText2Speech(env.core.voiceInstance, "hello")()
	else:
		assert env.module.ProcessText2Speech(env.core.voiceInstance, "hello")() == status
	assert native_function.errcheck is env.native.veCheckForError


def test_raw_status_call_does_not_mutate_shared_errcheck_concurrently(env, monkeypatch):
	native_function = env.native.veDll.ve_ttsProcessText2Speech
	native_function.errcheck = env.native.veCheckForError
	entered, release = Event(), Event()

	def process(instance, text):
		if text == "outer":
			entered.set()
			assert release.wait(HOLD_TIMEOUT)
		return env.types.NUAN_OK

	monkeypatch.setattr(env.native, "processText2Speech", process)
	results = []
	outer = run_thread(
		lambda: results.append(env.module.ProcessText2Speech(env.core.voiceInstance, "outer")()),
	)
	try:
		assert entered.wait(WAIT_TIMEOUT)
		data = env.types.VE_INTEXT()
		text = b"original"
		data.eTextFormat = env.types.VE_NORM_TEXT
		data.cntTextLength = len(text)
		data.szInText = ctypes.cast(ctypes.c_char_p(text), ctypes.c_void_p)
		assert native_function(env.core.voiceInstance, ctypes.byref(data)) is None
		assert native_function.errcheck is env.native.veCheckForError
	finally:
		release.set()
	finish(outer)
	assert results == [0]


def test_cancel_resets_pause_before_next_legacy_speech(env, monkeypatch):
	# Empty speech reaches idle without the native ABI, isolating pause state.
	env.core.pause(True)
	env.core.cancel()
	call = run_thread(lambda: speak_ordinary(env, ()))
	try:
		finish(call)
		assert len(env.dones) == 1
	finally:
		env.core.pause(False)
		call[0].join(1)


def test_done_listener_can_terminate_without_deadlocking_speech(env, monkeypatch):
	monkeypatch.setattr(env.native, "close", lambda instance: None)
	monkeypatch.setattr(env.native, "terminate", lambda: None)
	monkeypatch.setattr(
		env.original_driver.synthDoneSpeaking,
		"notify",
		lambda **kwargs: env.core.terminate(),
	)
	call = run_thread(lambda: speak_ordinary(env, ()))
	try:
		finish(call)
		# Terminate from the BgThread is reentrant: a closer thread closes the player.
		# A reentrant terminate closes the player on its own closer thread.
		closes = eventually(
			lambda: real_player(env.core).closes,
			message="the closer thread never closed the player",
		)
		assert closes == 1
	finally:
		if not call[1].is_set():
			# Rescue the pre-fix non-reentrant lock so this RED cannot leave
			# a permanently blocked thread in the test process.
			env.core._speechRunLock.release()
			call[0].join(1)


def test_index_listener_can_terminate_and_retire_native_before_close(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	monkeypatch.setattr(env.native, "close", lambda instance: None)
	monkeypatch.setattr(env.native, "terminate", lambda: None)
	listener_returned, native_returned, closed = Event(), Event(), Event()
	close_player = real_player(env.core).close

	def close():
		assert native_returned.is_set()
		close_player()
		closed.set()

	real_player(env.core).close = close

	def index(**kwargs):
		env.core.terminate()
		assert not closed.is_set()
		listener_returned.set()

	monkeypatch.setattr(env.original_driver.synthIndexReached, "notify", index)

	def process(instance, text):
		emit(env, instance, index=7)
		native_returned.set()

	monkeypatch.setattr(env.native, "processText2Speech", process)
	_, _, call = speak(env)
	try:
		assert listener_returned.wait(WAIT_TIMEOUT)
		finish(call)
		assert closed.wait(WAIT_TIMEOUT)
		assert env.events == []
	finally:
		if not call[1].is_set():
			env.core._speechRunLock.release()
			call[0].join(1)


def test_native_error_status_fails_context_through_installed_errcheck(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	# Exercise the real ve2 checker, not a Python exception from the stub.
	env.native.veDll.ve_ttsProcessText2Speech.errcheck = env.native.veCheckForError
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: 0xFFFFFFFF)
	_, context, call = speak(env)
	finish(call)
	assert len(env.events) == 1
	assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert env.events[0].source_id is context.source_id
	assert isinstance(env.events[0].error, env.types.VeError)
	assert env.dones == []


@pytest.mark.parametrize("env", ["Cerence"], indirect=True)
@pytest.mark.parametrize("bookmark", [b"23", b"-17", b"0"])
def test_cerence_bookmark_decodes_szvalue(env, monkeypatch, bookmark):
	prove_fake_quiescence(env, monkeypatch)
	results = []

	def native(instance, text):
		results.extend(emit(env, instance, index=bookmark))

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, _, call = speak(env)
	finish(call)
	assert results == [env.types.NUAN_OK] * 3
	assert env.indexes == [{b"23": 23, b"-17": -17, b"0": 0}[bookmark]]
	assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


@pytest.mark.parametrize("env", ["Cerence"], indirect=True)
@pytest.mark.parametrize("bookmark", [b"bad", b"", None])
def test_cerence_bookmark_decode_fault_fails_work(env, monkeypatch, bookmark):
	prove_fake_quiescence(env, monkeypatch)
	results, idle_calls = [], []
	real_player(env.core).idle = lambda: idle_calls.append(True)

	def native(instance, text):
		results.extend(emit(env, instance, index=bookmark))
		# Even a later idle return cannot rehabilitate the failed work.
		real_player(env.core).idle()

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, context, call = speak(env)
	finish(call)
	assert env.types.NUAN_E_TTS_USERSTOP in results
	assert idle_calls == [True]
	assert env.indexes == []
	assert len(env.events) == 1
	assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert env.events[0].source_id is context.source_id
	assert env.events[0].segment_id == 17
	assert isinstance(env.events[0].error, (TypeError, ValueError))
	assert env.dones == []


@pytest.mark.parametrize("env", ["Cerence"], indirect=True)
def test_callback_rejects_missing_instance_without_touching_current_buffer(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	callback = callback_handler(env.core)

	def native(instance, text):
		callback._feedBuf = BytesIO(b"current")
		message = native_message(env.types, env.types.VE_MSG_ENDPROCESS, env.types.VE_OUTDATA())
		assert callback(None, None, message) == env.types.NUAN_E_TTS_USERSTOP
		assert buffered_audio(callback) == b"current"

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, _, call = speak(env)
	finish(call)
	assert real_player(env.core).fed == []


@pytest.mark.parametrize("apply_before_barrier", [True, False])
@pytest.mark.parametrize("fresh_during_pause", [True, False])
def test_cancel_retires_inflight_pause_before_fresh_speech(env, apply_before_barrier, fresh_during_pause):
	entered, release, idle_entered = Event(), Event(), Event()
	player = real_player(env.core)
	pause_player = player.pause

	def pause(switch):
		if switch and not apply_before_barrier:
			entered.set()
			assert release.wait(HOLD_TIMEOUT)
		pause_player(switch)
		if switch and apply_before_barrier:
			entered.set()
			assert release.wait(HOLD_TIMEOUT)

	player.pause = pause
	player.idle = idle_entered.set
	pausing, fresh = run_thread(lambda: env.core.pause(True)), None
	try:
		assert entered.wait(WAIT_TIMEOUT)
		# Cancellation must still stop the player while pause is in flight.
		cancelling = run_thread(env.core.cancel)
		finish(cancelling)
		assert not player.isPaused
		if fresh_during_pause:
			fresh = run_thread(lambda: speak_ordinary(env, ()))
			stays_unset(idle_entered)
		release.set()
		finish(pausing)
		if fresh is None:
			fresh = run_thread(lambda: speak_ordinary(env, ()))
		finish(fresh)
		assert idle_entered.is_set()
		assert not player.isPaused
		assert len(env.dones) == 1
	finally:
		release.set()
		pausing[0].join(1)
		env.core.pause(False)
		if fresh is not None:
			fresh[0].join(1)


def test_pause_requested_during_cancel_waits_for_player_stop(env):
	stop_entered, stop_release, pause_entered = Event(), Event(), Event()
	player = real_player(env.core)
	stop_player, pause_player = player.stop, player.pause

	def stop():
		stop_entered.set()
		assert stop_release.wait(HOLD_TIMEOUT)
		stop_player()

	def pause(switch):
		pause_entered.set()
		pause_player(switch)

	player.stop, player.pause = stop, pause
	cancelling, pausing = run_thread(env.core.cancel), None
	try:
		assert stop_entered.wait(WAIT_TIMEOUT)
		pausing = run_thread(lambda: env.core.pause(True))
		stays_unset(pause_entered)
		stop_release.set()
		finish(cancelling)
		finish(pausing)
		assert player.isPaused
		env.core.pause(False)
		fresh = run_thread(lambda: speak_ordinary(env, ()))
		finish(fresh)
		assert len(env.dones) == 1
	finally:
		stop_release.set()
		cancelling[0].join(1)
		if pausing is not None:
			pausing[0].join(1)
		env.core.pause(False)


def test_segment_drain_waits_for_real_resume_return(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	idle_entered, resume_entered, resume_release = Event(), Event(), Event()
	player = real_player(env.core)
	pause_player = player.pause
	env.core.pause(True)

	def pause(switch):
		if not switch:
			resume_entered.set()
			assert resume_release.wait(HOLD_TIMEOUT)
		pause_player(switch)

	player.pause = pause
	player.idle = idle_entered.set
	monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: end_process(env, instance))
	_, _, speech = speak(env)
	resuming = None
	try:
		assert idle_entered.wait(WAIT_TIMEOUT)
		resuming = run_thread(lambda: env.core.pause(False))
		assert resume_entered.wait(WAIT_TIMEOUT)
		stays_unset(speech[1])
		assert env.events == []
		resume_release.set()
		finish(resuming)
		finish(speech)
		assert not player.isPaused
		assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
	finally:
		resume_release.set()
		if resuming is not None:
			resuming[0].join(1)
		env.core.pause(False)
		speech[0].join(1)


def assert_operation_failed(call, error):
	assert call[1].wait(WAIT_TIMEOUT)
	assert call[2] == [error]


@pytest.mark.parametrize("speech_path", ["legacy", "segment"])
@pytest.mark.parametrize("fresh_during_pause", [True, False])
def test_failed_cancelled_pause_reconciliation_blocks_fresh_speech(
	env,
	monkeypatch,
	speech_path,
	fresh_during_pause,
):
	prove_fake_quiescence(env, monkeypatch)
	entered, release = Event(), Event()
	player = real_player(env.core)
	pause_player = player.pause
	error = OSError("resume failed")
	failed_resume_states = []

	def pause(switch):
		if switch:
			entered.set()
			assert release.wait(HOLD_TIMEOUT)
			pause_player(True)
		else:
			failed_resume_states.append(player.isPaused)
			raise error

	player.pause = pause
	native_calls = []
	monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: native_calls.append(text))

	def fresh_speech():
		if speech_path == "legacy":
			return run_thread(lambda: speak_ordinary(env, ("fresh",)))
		return speak(env, ("fresh",), segment=18)[2]

	pausing, fresh = run_thread(lambda: env.core.pause(True)), None
	try:
		assert entered.wait(WAIT_TIMEOUT)
		finish(run_thread(env.core.cancel))
		assert not player.isPaused
		if fresh_during_pause:
			fresh = fresh_speech()
			stays_unset(fresh[1])
		release.set()
		assert_operation_failed(pausing, error)
		# Corrective resume failed before changing the paused player.
		assert failed_resume_states == [True]
		if fresh is None:
			fresh = fresh_speech()
		if speech_path == "legacy":
			if fresh_during_pause:
				# Queued before the fault: the worker drops it, nothing is raised.
				finish(fresh)
			else:
				assert_operation_failed(fresh, error)
		else:
			finish(fresh)
			assert len(env.events) == 1
			assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
			assert env.events[0].segment_id == 18
			assert env.events[0].error is error
		assert native_calls == []
		# Async speak(): speech queued before the fault still releases its DONE.
		assert len(env.dones) == (1 if speech_path == "legacy" and fresh_during_pause else 0)
		assert player.idles == 0
		# Clearing cancellation cannot clear an unknown player state fault.
		env.core.cancel()
		again = fresh_speech()
		if speech_path == "legacy":
			assert_operation_failed(again, error)
		else:
			finish(again)
			assert len(env.events) == 2
			assert all(event.kind is env.rt.models.EventKind.SEGMENT_FAILED for event in env.events)
		assert native_calls == []
	finally:
		release.set()
		pausing[0].join(1)
		if fresh is not None:
			fresh[0].join(1)


@pytest.mark.parametrize("speech_path", ["legacy", "segment"])
def test_resume_failure_faults_active_work_and_suppresses_drain(env, monkeypatch, speech_path):
	prove_fake_quiescence(env, monkeypatch)
	idle_entered, idle_release = Event(), Event()
	player = real_player(env.core)
	env.core.pause(True)
	stop_player = player.stop

	def idle():
		idle_entered.set()
		assert idle_release.wait(HOLD_TIMEOUT)

	def stop():
		stop_player()
		idle_release.set()

	player.idle, player.stop = idle, stop
	error = OSError("active resume failed")
	failed_resume_states = []

	def pause(switch):
		failed_resume_states.append(player.isPaused)
		raise error

	player.pause = pause
	if speech_path == "legacy":
		speech = run_thread(lambda: speak_ordinary(env, ()))
		context = None
	else:
		_, context, speech = speak(env, ())
	try:
		assert idle_entered.wait(WAIT_TIMEOUT)
		with pytest.raises(OSError, match="active resume failed"):
			env.core.pause(False)
		assert failed_resume_states == [True]
		if speech_path == "legacy":
			# speak() returned once queued; the fault suppresses its DONE.
			finish(speech)
		else:
			finish(speech)
			assert len(env.events) == 1
			assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
			assert env.events[0].source_id is context.source_id
			assert env.events[0].segment_id == 17
			assert env.events[0].error is error
		# Async speak(): the failed ordinary request still releases its DONE.
		assert len(env.dones) == (1 if speech_path == "legacy" else 0)
	finally:
		# Release the pre-fix paused work so RED does not leak a thread.
		env.core.cancel()
		speech[0].join(1)


@pytest.mark.parametrize("terminators", [1, 2])
def test_terminate_waits_for_pause_fault_stop_without_active_speech(env, monkeypatch, terminators):
	player = real_player(env.core)
	stop_entered, stop_release, shutdown_stop, closed = Event(), Event(), Event(), Event()
	stops, stops_after_close, native_closes, native_terminations = [], [], [], []
	error = OSError("pause failed before shutdown")
	player.pause = lambda switch: (_ for _ in ()).throw(error)
	stop_player, close_player = player.stop, player.close

	def stop():
		if closed.is_set():
			stops_after_close.append(True)
		stops.append(True)
		if len(stops) == 1:
			stop_entered.set()
			assert stop_release.wait(HOLD_TIMEOUT)
		else:
			shutdown_stop.set()
		stop_player()

	def close():
		close_player()
		closed.set()

	player.stop, player.close = stop, close
	instance = env.core.voiceInstance
	monkeypatch.setattr(env.native, "close", lambda value: native_closes.append(value))
	monkeypatch.setattr(env.native, "terminate", lambda: native_terminations.append(True))
	pausing, shutting_down = run_thread(lambda: env.core.pause(True)), []
	try:
		assert stop_entered.wait(WAIT_TIMEOUT)
		shutting_down = [run_thread(env.core.terminate) for _ in range(terminators)]
		assert shutdown_stop.wait(WAIT_TIMEOUT)
		stays_unset(closed)
		assert native_closes == []
		assert native_terminations == []
		assert all(not call[1].is_set() for call in shutting_down)
		with pytest.raises(RuntimeError, match="terminated"):
			env.core.pause(True)
		stop_release.set()
		assert_operation_failed(pausing, error)
		for call in shutting_down:
			finish(call)
		assert closed.is_set()
		assert player.closes == 1
		assert native_closes == [instance]
		assert native_terminations == [True]
		env.core.terminate()
		env.core.cancel()
		with pytest.raises(RuntimeError, match="terminated"):
			env.core.pause(False)
		assert player.closes == 1
		assert stops_after_close == []
	finally:
		stop_release.set()
		pausing[0].join(1)
		for call in shutting_down:
			call[0].join(1)


@pytest.mark.parametrize("operation", ["pause", "cancel", "fault_stop"])
def test_reentrant_player_terminate_waits_for_own_operation(env, monkeypatch, operation):
	player = real_player(env.core)
	operation_returned, listener_returned = Event(), Event()
	stop_player, pause_player, close_player = player.stop, player.pause, player.close
	monkeypatch.setattr(env.native, "close", lambda value: None)
	monkeypatch.setattr(env.native, "terminate", lambda: None)
	calls = []

	def stop():
		calls.append(True)
		if len(calls) == 1 and operation in ("cancel", "fault_stop"):
			env.core.terminate()
			assert player.closes == 0
			listener_returned.set()
			stop_player()
			operation_returned.set()
		else:
			stop_player()

	error = OSError("reentrant pause failure")

	def pause(switch):
		if operation == "fault_stop":
			raise error
		env.core.terminate()
		assert player.closes == 0
		listener_returned.set()
		pause_player(switch)
		operation_returned.set()

	def close():
		assert operation_returned.is_set()
		close_player()

	player.stop, player.pause, player.close = stop, pause, close
	action = env.core.cancel if operation == "cancel" else lambda: env.core.pause(True)
	call = run_thread(action)
	try:
		if operation == "fault_stop":
			assert_operation_failed(call, error)
		else:
			finish(call)
		assert listener_returned.is_set()
		assert player.closes == 1
		env.core.terminate()
		assert player.closes == 1
	finally:
		if not call[1].is_set():
			# Release a pre-fix self-wait from RED, without leaving a thread.
			termination_done(env.core).set()
			call[0].join(1)


def test_reentrant_terminate_from_player_close_does_not_wait_for_itself(env, monkeypatch):
	player = real_player(env.core)
	close_player = player.close
	listener_returned = Event()
	monkeypatch.setattr(env.native, "close", lambda value: None)
	monkeypatch.setattr(env.native, "terminate", lambda: None)

	def close():
		env.core.terminate()
		listener_returned.set()
		close_player()

	player.close = close
	call = run_thread(env.core.terminate)
	try:
		finish(call)
		assert listener_returned.is_set()
		assert player.closes == 1
		env.core.terminate()
		assert player.closes == 1
	finally:
		if not call[1].is_set():
			termination_done(env.core).set()
			call[0].join(1)


class CountingToken(Token):
	"""The test Token, counting how often waiters poll it."""

	def __init__(self):
		super().__init__()
		self.checks = 0

	def is_cancelled(self):
		self.checks += 1
		return super().is_cancelled()


def assert_not_polled(read_count, window=0.2):
	# A 50 ms poll would re-check about four times in this window.
	before = read_count()
	Event().wait(window)
	assert read_count() - before <= 1, "waiter is polling instead of waiting for a notification"


def test_contextual_delivery_wait_does_not_poll(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: emit(env, instance))
	entered, release = Event(), Event()

	def blocking_sink(event):
		entered.set()
		assert release.wait(HOLD_TIMEOUT), "Test did not release the sink"

	token = CountingToken()
	context = env.rt.models.PlaybackContext(object(), 17)
	call = run_thread(
		lambda: env.core.speak_segment(("hello",), token, context=context, on_event=blocking_sink),
	)
	try:
		assert entered.wait(WAIT_TIMEOUT)
		assert_not_polled(lambda: token.checks)
		token.cancel()
		assert call[1].wait(WAIT_TIMEOUT), "speak_segment was not woken by token cancellation"
	finally:
		release.set()
	finish(call)


def test_cancel_player_stop_failure_rejects_successor(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	failures = [OSError("stop failed")]

	def stop():
		# Only the first stop fails; later stops succeed like a recovered player.
		if failures:
			raise failures.pop()

	real_player(env.core).stop = stop
	with pytest.raises(OSError):
		env.core.cancel()
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
	_, context, call = speak(env)
	finish(call)
	assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_FAILED]
	assert env.events[0].source_id is context.source_id


def test_stop_player_failure_rejects_successor(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	failures = [OSError("stop failed")]

	def stop():
		# Only the first stop fails; later stops succeed like a recovered player.
		if failures:
			raise failures.pop()

	real_player(env.core).stop = stop
	with pytest.raises(OSError):
		env.core._stopPlayer()
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
	_, _context, call = speak(env)
	finish(call)
	assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_FAILED]


def test_cancel_releases_the_stop_gate_when_abandon_fails(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
	host = segment_host(env.core)
	retire = host.retire
	held, release = Event(), Event()

	def held_retire(record, **kwargs):
		result = retire(record, **kwargs)
		if not held.is_set():
			held.set()
			assert release.wait(HOLD_TIMEOUT)
		return result

	monkeypatch.setattr(host, "retire", held_retire)
	_, _, first = speak(env)
	abandon = host.abandon
	try:
		assert held.wait(WAIT_TIMEOUT)
		context = env.rt.models.PlaybackContext(object(), 18)
		env.core.speak_segment(("second",), Token(), context=context, on_event=env.events.append)
		wait_for(lambda: queued_begins(env.core))
		dropped = []

		def failing_abandon(record):
			dropped.append(record)
			raise RuntimeError("abandon failed")

		monkeypatch.setattr(host, "abandon", failing_abandon)
		with pytest.raises(RuntimeError, match="abandon failed"):
			env.core.cancel()
		assert stop_gate_clear(env.core)
	finally:
		monkeypatch.setattr(host, "abandon", abandon)
		for record in locals().get("dropped", []):
			abandon(record)
		release.set()
	finish(first)
	settle_segment(env, context)
	settle_worker(env)


# ENGINE_DONE: the wrapper flushes Sonic and the pending feed buffer (the record's audio tail)
# only at VE_MSG_ENDPROCESS, so a segment record reaches ENGINE_DONE only when its last native
# call saw an admitted ENDPROCESS. A Windows SDK probe (VE 2.2.0, Cerence 21.6.0; branch SDKTest,
# ec53410) saw exactly one ENDPROCESS, always last, on every successful call.


def speak_pieces(env, monkeypatch, pieces, ends):
	"""Speak one segment of ``pieces``; native call i delivers ENDPROCESS when ends[i] says so."""
	prove_fake_quiescence(env, monkeypatch)
	monkeypatch.setattr(env.module, "split_speech_text_pieces", lambda text: list(pieces))
	calls = []

	def native(instance, text):
		calls.append(text)
		emit(env, instance, end=ends[len(calls) - 1])

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, _, call = speak(env)
	finish(call)
	wait_for(lambda: len(env.events) == 1)
	return calls


def test_segment_whose_every_call_ends_reaches_engine_done(env, monkeypatch):
	calls = speak_pieces(env, monkeypatch, ["a", "b", "c"], [True, True, True])
	assert calls == ["a", "b", "c"]
	assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


def test_last_call_without_endprocess_fails_the_segment(env, monkeypatch):
	calls = speak_pieces(env, monkeypatch, ["a", "b"], [True, False])
	assert calls == ["a", "b"]
	assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_FAILED]
	assert "engine_done" in str(env.events[0].error)


def test_only_the_last_call_needs_endprocess(env, monkeypatch):
	# A middle call's tail stays in Sonic and the feed buffer and goes out with the next call.
	calls = speak_pieces(env, monkeypatch, ["a", "b", "c"], [True, False, True])
	assert calls == ["a", "b", "c"]
	assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


def test_refused_endprocess_does_not_reach_engine_done(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	results = []

	def native(instance, text):
		emit(env, instance, end=False)
		# Admission refuses a callback for another instance: it proves nothing for this call.
		foreign = env.types.VE_HSAFE()
		foreign.pHandleData = 123
		results.append(end_process(env, foreign))

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, _, call = speak(env)
	finish(call)
	wait_for(lambda: len(env.events) == 1)
	assert results == [env.types.NUAN_E_TTS_USERSTOP]
	assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_FAILED]
	assert "engine_done" in str(env.events[0].error)


def test_segment_without_native_call_reaches_engine_done(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	monkeypatch.setattr(env.module, "split_speech_text_pieces", lambda text: [])
	calls = []
	monkeypatch.setattr(env.native, "processText2Speech", lambda *args: calls.append(args))
	_, _, call = speak(env)
	finish(call)
	wait_for(lambda: len(env.events) == 1)
	assert calls == []
	assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


# Ordinary speech declares AUDIO_FED, ENGINE_DONE and PLAYED_OUT like a segment record. Its idle
# and DONE stay with the inner DoneSpeaking, which runs before _Retire and proves PLAYED_OUT for
# the record it was bound to at submit, so a failed record still has published DONE; the host's
# failure handling only stops the player. A record cancelled through cancel() (the host) retires
# cancelled: its unreached barriers are no failure. It publishes no DONE when the cancel lands
# before its DoneSpeaking; a cancel after it leaves the DONE already published.


def record_retires(env, monkeypatch):
	host = segment_host(env.core)
	retire, outcomes = host.retire, []

	def recording_retire(record, **kwargs):
		outcome = retire(record, **kwargs)
		outcomes.append((record, outcome))
		return outcome

	monkeypatch.setattr(host, "retire", recording_retire)
	return outcomes


def speak_ordinary_pieces(env, monkeypatch, pieces, native):
	"""Speak one ordinary request of ``pieces`` through ``native``; return the recorded retires."""
	monkeypatch.setattr(env.module, "split_speech_text_pieces", lambda text: list(pieces))
	monkeypatch.setattr(env.native, "processText2Speech", native)
	outcomes = record_retires(env, monkeypatch)
	speak_ordinary(env, ("ordinary",))
	return outcomes


def missing_barrier_logs(caplog):
	return [record.getMessage() for record in caplog.records if "retired without its" in record.getMessage()]


def ending_calls(env, ends):
	calls = []

	def native(instance, text):
		calls.append(text)
		emit(env, instance, end=ends[len(calls) - 1])

	return calls, native


@pytest.mark.parametrize("ends", [[True], [True, False, True]], ids=["one-call", "middle-call-unended"])
def test_ordinary_speech_reaches_every_barrier(env, monkeypatch, caplog, ends):
	calls, native = ending_calls(env, ends)
	pieces = [str(i) for i in range(len(ends))]
	shared = player_of(env.core)
	outcomes = speak_ordinary_pieces(env, monkeypatch, pieces, native)
	# The player bound to the record is the inner speak()'s only: the shared one is back.
	assert player_of(env.core) is shared
	assert len(calls) == len(ends)
	[(record, outcome)] = outcomes
	assert record.barriers == {"audio_fed": True, "engine_done": True, "played_out": True}
	assert (outcome.cancelled, outcome.error) == (False, None)
	player = real_player(env.core)
	assert player.fed == [b"pcm"] * len(ends)
	assert (player.idles, player.stops) == (1, 0)
	assert len(env.dones) == 1
	assert missing_barrier_logs(caplog) == []


@pytest.mark.parametrize("ends", [[False], [True, False]], ids=["one-call", "last-of-two"])
def test_ordinary_last_call_without_endprocess_fails_the_record(env, monkeypatch, caplog, ends):
	ends = list(ends)  # changed below; the parametrized list is shared by both engines
	calls, native = ending_calls(env, ends)
	pieces = [str(i) for i in range(len(ends))]
	outcomes = speak_ordinary_pieces(env, monkeypatch, pieces, native)
	assert len(calls) == len(ends)
	[(record, outcome)] = outcomes
	assert record.barriers == {"audio_fed": True, "engine_done": False, "played_out": True}
	assert outcome.cancelled is False
	assert "engine_done" in str(outcome.error)
	# The wrapper drops the outcome; the host's log is what makes the failure visible.
	[logged] = missing_barrier_logs(caplog)
	assert env.engine in logged and "engine_done" in logged
	player = real_player(env.core)
	# DoneSpeaking idled and published DONE before _Retire; the host then discards queued audio.
	assert (player.idles, player.stops) == (1, 1)
	assert len(env.dones) == 1
	# The failure belongs to that record: later speech is accepted and completes.
	assert segment_host(env.core).control_error is None
	outcomes.clear()
	calls.clear()
	ends[:] = [True] * len(ends)
	speak_ordinary(env, ("again",))
	[(_, outcome)] = outcomes
	assert (outcome.cancelled, outcome.error) == (False, None)
	assert len(env.dones) == 2


def test_cancel_before_the_native_call_retires_cancelled(env, monkeypatch, caplog):
	begin = env.core._beginRecord

	def cancelling_begin(record):
		begin(record)
		env.core.cancel()

	monkeypatch.setattr(env.core, "_beginRecord", cancelling_begin)
	calls, native = ending_calls(env, [True])
	outcomes = speak_ordinary_pieces(env, monkeypatch, ["a"], native)
	assert calls == []
	[(record, outcome)] = outcomes
	assert record.cancelled
	assert record.barriers == {"audio_fed": False, "engine_done": False, "played_out": False}
	assert (outcome.cancelled, outcome.error) == (True, None)
	# Nothing was fed; cancel() stops the player and so does the host's cancelled retire.
	player = real_player(env.core)
	assert (player.fed, player.idles, player.stops) == ([], 0, 2)
	assert env.dones == []
	assert missing_barrier_logs(caplog) == []


def test_cancel_mid_feed_retires_cancelled(env, monkeypatch, caplog):
	player = real_player(env.core)
	feed, results = player.feed, []

	def cancelling_feed(data):
		feed(data)
		env.core.cancel()

	monkeypatch.setattr(player, "feed", cancelling_feed)

	def native(instance, text):
		results.append(emit(env, instance))

	outcomes = speak_ordinary_pieces(env, monkeypatch, ["a"], native)
	types = env.types
	# OUTBUFDONE sees the cancelled record after its feed; cancel() closed the call's admission,
	# so the ENDPROCESS that follows is refused and proves nothing for ENGINE_DONE.
	assert results == [[types.NUAN_OK, types.NUAN_E_TTS_USERSTOP, types.NUAN_E_TTS_USERSTOP]]
	[(record, outcome)] = outcomes
	assert record.cancelled
	assert record.native.lastCallEnded is False
	assert record.barriers == {"audio_fed": False, "engine_done": False, "played_out": False}
	assert (outcome.cancelled, outcome.error) == (True, None)
	assert (player.fed, player.idles) == ([b"pcm"], 0)
	assert env.dones == []
	assert missing_barrier_logs(caplog) == []


def test_legacy_endprocess_after_a_recorded_error_is_acknowledged_but_does_not_count(
	env,
	monkeypatch,
	caplog,
):
	# Synthetic: production never records an error on a record whose native call still admits
	# (the callback's except closes the admission at once); its only way into this branch is the
	# cancel window below. Injecting the error holds the branch's precondition without a cancel,
	# so the acknowledgement is pinned for a failed record too: NUAN_OK, like the original add-on,
	# yet not an admitted ENDPROCESS, so it proves nothing for ENGINE_DONE.
	error, results = OSError("feed failed"), []
	host = segment_host(env.core)

	def native(instance, text):
		emit(env, instance, end=False)
		host.record_error(host.current(), error)
		results.append(end_process(env, instance))

	outcomes = speak_ordinary_pieces(env, monkeypatch, ["a"], native)
	assert results == [env.types.NUAN_OK]
	[(record, outcome)] = outcomes
	assert record.native.lastCallEnded is False
	assert record.barriers == {"audio_fed": False, "engine_done": False, "played_out": False}
	assert (outcome.cancelled, outcome.error) == (False, error)
	player = real_player(env.core)
	# The host's failure path discards queued audio; the failed (not cancelled) request still
	# releases its DONE waiter.
	assert (player.fed, player.idles, player.stops) == ([b"pcm"], 0, 1)
	assert len(env.dones) == 1
	assert missing_barrier_logs(caplog) == []


def test_legacy_endprocess_in_the_cancel_window_is_acknowledged_but_does_not_count(
	env,
	monkeypatch,
	caplog,
):
	# The production way into the legacy acknowledgement: cancel() from another thread has run
	# host.cancel() (the record is cancelled) but has not yet closed the call's admission under
	# _speechStateLock, and the SDK's ENDPROCESS arrives in between. Replayed in order here: the
	# ENDPROCESS is sent right after host.cancel() returns, inside cancel().
	host, results, instances = segment_host(env.core), [], []
	cancel = host.cancel

	def cancel_then_endprocess():
		cancel()
		results.append(end_process(env, instances[0]))

	monkeypatch.setattr(host, "cancel", cancel_then_endprocess)

	def native(instance, text):
		instances.append(instance)
		emit(env, instance, end=False)
		env.core.cancel()

	outcomes = speak_ordinary_pieces(env, monkeypatch, ["a"], native)
	assert results == [env.types.NUAN_OK]
	[(record, outcome)] = outcomes
	assert record.cancelled
	assert record.native.lastCallEnded is False
	assert record.barriers == {"audio_fed": False, "engine_done": False, "played_out": False}
	assert (outcome.cancelled, outcome.error) == (True, None)
	player = real_player(env.core)
	# cancel()'s own stop plus the host's cancelled-path stop at retire; no DONE.
	assert (player.fed, player.idles, player.stops) == ([b"pcm"], 0, 2)
	assert env.dones == []
	assert missing_barrier_logs(caplog) == []


def test_cancel_before_begin_skips_the_record(env, monkeypatch, caplog):
	# A cancel that lands after the BgThread took the record's _Begin off the queue (so
	# _dropQueuedSpeech cannot drop it) and before it runs: the record is skipped and abandoned.
	begin, begun = env.core._beginRecord, []

	def cancelling_begin(record):
		env.core.cancel()
		begun.append(record)
		begin(record)

	monkeypatch.setattr(env.core, "_beginRecord", cancelling_begin)
	calls, native = ending_calls(env, [True])
	outcomes = speak_ordinary_pieces(env, monkeypatch, ["a"], native)
	[record] = begun
	assert record.native.skipped
	assert record.abandoned and record.cancelled
	assert calls == []
	# abandon() retires the record without retire().
	assert outcomes == []
	player = real_player(env.core)
	# Only cancel()'s own stop.
	assert (player.fed, player.idles, player.stops) == ([], 0, 1)
	assert env.dones == []
	assert missing_barrier_logs(caplog) == []


def test_cancel_after_the_last_call_retires_cancelled(env, monkeypatch, caplog):
	# The terminal idle runs after the last native call and before _Retire.
	player = real_player(env.core)
	idle = player.idle

	def cancelling_idle():
		idle()
		env.core.cancel()

	monkeypatch.setattr(player, "idle", cancelling_idle)
	calls, native = ending_calls(env, [True])
	outcomes = speak_ordinary_pieces(env, monkeypatch, ["a"], native)
	assert calls == ["a"]
	[(record, outcome)] = outcomes
	assert record.native.lastCallEnded is True
	assert record.barriers == {"audio_fed": False, "engine_done": False, "played_out": False}
	assert (outcome.cancelled, outcome.error) == (True, None)
	assert record.cancelled
	# cancel()'s own stop plus the host's cancelled-path stop at retire.
	assert (player.fed, player.idles, player.stops) == ([b"pcm"], 1, 2)
	assert env.dones == []
	assert missing_barrier_logs(caplog) == []


def test_cancel_between_the_retire_reaches_is_not_a_failure(env, monkeypatch, caplog):
	# A cancel that lands after _retireRecord reached AUDIO_FED skips ENGINE_DONE; retire reads
	# the host cancellation itself, so the record retires cancelled, not failed for engine_done.
	host = segment_host(env.core)
	reach = host.reach

	def cancelling_reach(record, barrier):
		reach(record, barrier)
		if barrier == "audio_fed":
			env.core.cancel()

	monkeypatch.setattr(host, "reach", cancelling_reach)
	calls, native = ending_calls(env, [True])
	outcomes = speak_ordinary_pieces(env, monkeypatch, ["a"], native)
	assert calls == ["a"]
	[(record, outcome)] = outcomes
	assert record.barriers == {"audio_fed": True, "engine_done": False, "played_out": True}
	assert record.cancelled
	assert (outcome.cancelled, outcome.error) == (True, None)
	player = real_player(env.core)
	assert (player.fed, player.idles, player.stops) == ([b"pcm"], 1, 2)
	# DoneSpeaking ran before _Retire, before the cancel, so DONE was published.
	assert len(env.dones) == 1
	assert missing_barrier_logs(caplog) == []


# The final idle that proves PLAYED_OUT runs in the inner DoneSpeaking, before _Retire. The
# player (fed/idles/stops) and DONE assertions below also pass on master's wrapper, before
# PLAYED_OUT (verified 2026-10-29), except where a test says otherwise.


def played_out_reaches(env, monkeypatch):
	"""An Event set when PLAYED_OUT is reached on any record, and the records it was reached on."""
	host = segment_host(env.core)
	reach, reached, records = host.reach, Event(), []

	def recording_reach(record, barrier):
		reach(record, barrier)
		if barrier == "played_out":
			records.append(record)
			reached.set()

	monkeypatch.setattr(host, "reach", recording_reach)
	return reached, records


def idle_entered(env, monkeypatch):
	player = real_player(env.core)
	idle, entered = player.idle, Event()

	def entering_idle():
		idle()
		entered.set()

	monkeypatch.setattr(player, "idle", entering_idle)
	return entered


def test_ordinary_played_out_waits_for_resume_after_the_final_idle(env, monkeypatch, caplog):
	calls, native = ending_calls(env, [True])
	monkeypatch.setattr(env.native, "processText2Speech", native)
	outcomes = record_retires(env, monkeypatch)
	reached, _ = played_out_reaches(env, monkeypatch)
	entered = idle_entered(env, monkeypatch)
	env.core.pause(True)
	try:
		env.core.speak(("ordinary",))
		assert entered.wait(WAIT_TIMEOUT)
		# The idle returned while paused: the pause wait holds PLAYED_OUT back.
		stays_unset(reached)
		assert outcomes == []
	finally:
		env.core.pause(False)
	settle_worker(env)
	assert calls == ["ordinary"]
	[(record, outcome)] = outcomes
	assert record.barriers == {"audio_fed": True, "engine_done": True, "played_out": True}
	assert (outcome.cancelled, outcome.error) == (False, None)
	player = real_player(env.core)
	assert (player.fed, player.idles, player.stops) == ([b"pcm"], 1, 0)
	assert len(env.dones) == 1
	assert missing_barrier_logs(caplog) == []


def test_ordinary_cancelled_during_the_final_pause_never_plays_out(env, monkeypatch, caplog):
	calls, native = ending_calls(env, [True])
	monkeypatch.setattr(env.native, "processText2Speech", native)
	outcomes = record_retires(env, monkeypatch)
	reached, _ = played_out_reaches(env, monkeypatch)
	entered = idle_entered(env, monkeypatch)
	env.core.pause(True)
	try:
		env.core.speak(("ordinary",))
		assert entered.wait(WAIT_TIMEOUT)
		# cancel() clears the pause and wakes the wait with the record invalid.
		env.core.cancel()
	finally:
		env.core.pause(False)
	settle_worker(env)
	assert calls == ["ordinary"]
	assert not reached.is_set()
	[(record, outcome)] = outcomes
	assert record.barriers == {"audio_fed": False, "engine_done": False, "played_out": False}
	assert (outcome.cancelled, outcome.error) == (True, None)
	assert record.cancelled
	player = real_player(env.core)
	# cancel(): its own stop plus the host's cancelled-path stop at retire.
	assert (player.fed, player.idles, player.stops) == ([b"pcm"], 1, 2)
	# The request was cancelled, so its DoneSpeaking publishes no DONE.
	assert env.dones == []
	assert missing_barrier_logs(caplog) == []


def test_kept_done_of_a_dropped_request_never_plays_out_another(env, monkeypatch, caplog):
	# Defensive: cancel() keeps a dropped request's DoneSpeaking, and in production it still runs
	# before the next request's _Begin (_dropQueuedSpeech keeps the order, and that _Begin is
	# queued only after cancel() releases admission), while no record is current. Run it by hand
	# while a later request is current to prove the binding alone keeps it from idling or
	# reaching PLAYED_OUT for that request. Master's _currentRecord lookup idles once here, so
	# unlike the section's other tests this one fails on master by that idle.
	held, release, inside = Event(), Event(), []
	host = segment_host(env.core)
	player = real_player(env.core)
	kept = []

	def native(instance, text):
		if text == "first":
			held.set()
			assert release.wait(HOLD_TIMEOUT)
			return
		if text == "third":
			current = host.current()
			idles = player.idles
			for done in kept:
				done()
			inside.append((current.barriers.get("played_out", False), player.idles - idles))
		emit(env, instance)

	monkeypatch.setattr(env.native, "processText2Speech", native)
	outcomes = record_retires(env, monkeypatch)
	_, records = played_out_reaches(env, monkeypatch)
	try:
		env.core.speak(("first",))
		assert held.wait(WAIT_TIMEOUT)
		env.core.speak(("second",))
		dropped = host.current(), queued_done_speaking(env.core)
		env.core.cancel()
		# The second request never began: its DoneSpeaking is the one cancel() kept behind
		# the first request's own.
		kept.extend(task for task in queued_done_speaking(env.core) if task in dropped[1][1:])
		assert len(kept) == 1
		env.core.speak(("third",))
	finally:
		release.set()
	settle_worker(env)
	assert inside == [(False, 0)]
	[(first, first_outcome), (third, third_outcome)] = outcomes
	assert first is dropped[0]
	assert (first_outcome.cancelled, first_outcome.error) == (True, None)
	assert first.barriers["played_out"] is False
	assert third.barriers == {"audio_fed": True, "engine_done": True, "played_out": True}
	assert (third_outcome.cancelled, third_outcome.error) == (False, None)
	assert records == [third]
	assert player.idles == 1
	assert missing_barrier_logs(caplog) == []


@pytest.mark.parametrize("native_queued", [True, False], ids=["after-native", "before-native"])
def test_inner_speak_failure_after_begin_keeps_todays_outcome(env, monkeypatch, caplog, native_queued):
	# The inner speak() queues its DoneSpeaking last: when it raises, the record has its
	# _Begin and _Retire but no final idle, so it cannot prove PLAYED_OUT. Today it retires
	# without an error, a stop or a log; that stays so.
	calls, native = ending_calls(env, [True])
	monkeypatch.setattr(env.native, "processText2Speech", native)
	outcomes = record_retires(env, monkeypatch)
	speak_chunks = env.core._speak

	def failing_speak(instance, chunks):
		if native_queued:
			speak_chunks(instance, chunks)
		raise RuntimeError("inner speak failed")

	monkeypatch.setattr(env.core, "_speak", failing_speak)
	shared = player_of(env.core)
	with pytest.raises(RuntimeError, match="inner speak failed"):
		env.core.speak(("ordinary",))
	assert player_of(env.core) is shared
	settle_worker(env)
	assert calls == (["ordinary"] if native_queued else [])
	[(record, outcome)] = outcomes
	assert record.barriers == {"audio_fed": True, "engine_done": True}
	assert record.error is None
	assert (outcome.cancelled, outcome.error) == (False, None)
	player = real_player(env.core)
	assert (player.fed, player.idles, player.stops) == ([b"pcm"] if native_queued else [], 0, 0)
	assert env.dones == []
	assert missing_barrier_logs(caplog) == []
	# Later speech is unaffected.
	monkeypatch.setattr(env.core, "_speak", speak_chunks)
	outcomes.clear()
	calls.clear()
	speak_ordinary(env, ("again",))
	[(_, outcome)] = outcomes
	assert (outcome.cancelled, outcome.error) == (False, None)


def test_inner_speak_failure_keeps_its_error_for_a_set_without_played_out(env, monkeypatch):
	# SegmentHost.enqueue takes any ordinary set; a caller's set without PLAYED_OUT has nothing
	# to undeclare, and the inner speak()'s own exception reaches the caller.
	outcomes = record_retires(env, monkeypatch)

	def failing_speak(instance, chunks):
		raise RuntimeError("inner speak failed")

	monkeypatch.setattr(env.core, "_speak", failing_speak)
	with pytest.raises(RuntimeError, match="inner speak failed"):
		segment_host(env.core).enqueue(("ordinary",), barriers=frozenset({"audio_fed"}))
	settle_worker(env)
	[(record, outcome)] = outcomes
	assert record.barriers == {"audio_fed": True}
	assert (outcome.cancelled, outcome.error) == (False, None)


def test_failed_final_idle_fails_the_record(env, monkeypatch, caplog):
	# Today a raising idle() is only logged by the BgThread. It is recorded on the record now,
	# so the record fails instead of silently missing PLAYED_OUT; the inner DoneSpeaking still
	# publishes no DONE, and only the host's failure path stops the player.
	error = OSError("idle failed")
	player = real_player(env.core)

	def failing_idle():
		player.idles += 1
		raise error

	monkeypatch.setattr(player, "idle", failing_idle)
	calls, native = ending_calls(env, [True])
	outcomes = speak_ordinary_pieces(env, monkeypatch, ["a"], native)
	[(record, outcome)] = outcomes
	assert record.barriers == {"audio_fed": False, "engine_done": False, "played_out": False}
	assert record.error is error
	assert (outcome.cancelled, outcome.error) == (False, error)
	assert (player.fed, player.idles, player.stops) == ([b"pcm"], 1, 1)
	assert env.dones == []
	# The recorded error is the failure; no missing-barrier failure is added.
	assert missing_barrier_logs(caplog) == []
	# Only that record fails: later speech is accepted and completes.
	assert segment_host(env.core).control_error is None
	monkeypatch.setattr(player, "idle", lambda: None)
	outcomes.clear()
	calls.clear()
	speak_ordinary(env, ("again",))
	[(_, outcome)] = outcomes
	assert (outcome.cancelled, outcome.error) == (False, None)
	assert len(env.dones) == 1


def test_feeds_go_through_the_lease(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	leased = sys.modules[type(segment_host(env.core)).__module__].LeasedPlayer
	assert isinstance(leased_player(env.core), leased)
	assert leased_player(env.core)._player is real_player(env.core)

	def native(instance, text):
		emit(env, instance)

	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, _, call = speak(env)
	finish(call)
	assert real_player(env.core).fed == [b"pcm"]
	assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


def test_late_feed_after_cancel_is_stopped_and_stop_failure_latches(env, monkeypatch):
	prove_fake_quiescence(env, monkeypatch)
	player = real_player(env.core)
	entered, release = Event(), Event()
	original_feed, original_stop = player.feed, player.stop
	feed_threads = []

	def held_feed(data):
		feed_threads.append(current_thread())
		entered.set()
		assert release.wait(HOLD_TIMEOUT)
		original_feed(data)

	def native(instance, text):
		emit(env, instance)

	player.feed = held_feed
	monkeypatch.setattr(env.native, "processText2Speech", native)
	_, _, first = speak(env)
	assert entered.wait(WAIT_TIMEOUT)
	env.core.cancel()
	error = OSError("late stop failed")
	failures = [error]

	def stop():
		# The lifecycle's stop_native also stops the cancelled segment, on its own thread. The
		# lease's stop runs on the callback thread that fed, before the callback returns: fail
		# that one, once.
		if failures and current_thread() in feed_threads:
			raise failures.pop()
		original_stop()

	player.stop = stop
	release.set()
	finish(first)
	assert failures == [], "the lease did not stop again after the late feed"
	assert segment_host(env.core).control_error is error
	player.feed, player.stop = original_feed, original_stop
	_, context, second = speak(env, segment=18)
	finish(second)
	assert [(event.kind, event.source_id) for event in env.events] == [
		(env.rt.models.EventKind.SEGMENT_FAILED, context.source_id),
	]
