import ctypes
import threading
from io import BytesIO

import pytest
from waiting import HOLD_TIMEOUT, WAIT_TIMEOUT, eventually
from worldvoice_cancel_wrapper_harness import (
	Token,
	background_idle,
	buffered_audio,
	cached_instances,
	callback_handler,
	has_segment_host,
	inner_stop_flag,
	load_real_driver_with_native_stubs,
	native_call,
	native_callback,
	native_message,
	player_of,
	real_player,
	sonic_state,
	stand_in_real_player,
)


@pytest.fixture(params=["VE", "Cerence"])
def engine_harness(request, monkeypatch):
	return load_real_driver_with_native_stubs(monkeypatch, request.param)


def speak_now(core, *args, **kwargs):
	# VE queues ordinary speech to the inner BgThread (phase 3d-1); wait until it ran.
	result = core.speak(*args, **kwargs)
	if has_segment_host(core):
		eventually(lambda: background_idle(core))
	return result


def ready_core(engine_harness):
	core = engine_harness.new_core()
	core.voiceInstance = core.getVoiceInstance("fake")
	core.language = "en"
	core._normalization = "OFF"
	return core


def emit_audio(core, types, payload=b"new", done_result=None):
	callback = callback_handler(core)
	if done_result is None:
		done_result = types.NUAN_OK
	native = native_call(core)
	instance = native.instance if native is not None else None
	out_data = types.VE_OUTDATA()
	assert callback(instance, None, native_message(types, types.VE_MSG_OUTBUFREQ, out_data)) == types.NUAN_OK
	ctypes.memmove(out_data.pOutPcmBuf, payload, len(payload))
	out_data.cntPcmBufLen = len(payload)
	out_data.cntMrkListLen = 0
	assert callback(instance, None, native_message(types, types.VE_MSG_OUTBUFDONE, out_data)) == done_result
	assert callback(instance, None, native_message(types, types.VE_MSG_ENDPROCESS, out_data)) == types.NUAN_OK


def test_installs_player_stand_in_and_keeps_inner_stop_flag(engine_harness):
	core = engine_harness.new_core()
	assert core.supportsCancellationToken is True
	handler = callback_handler(core)
	assert isinstance(player_of(core), engine_harness.module._IdleRoutingPlayer)
	assert stand_in_real_player(player_of(core)) is real_player(core)
	# The guard leaves the callback's player and the inner stop Event as created.
	assert player_of(handler) is real_player(core)
	assert inner_stop_flag(core) is inner_stop_flag(handler)
	assert type(inner_stop_flag(core)) is threading.Event
	assert not inner_stop_flag(core).is_set()
	assert engine_harness.module.Voice.synthDriverClass is engine_harness.module.SynthDriver


@pytest.mark.parametrize(
	"missing",
	[
		"_isSilence",
		"_player",
		"callback._isSilence",
		"callback._player",
		"_feedBuf",
	],
)
def test_missing_private_field_falls_back_without_partial_install(engine_harness, missing):
	core = engine_harness.new_core(missing=missing)
	assert core.supportsCancellationToken is False
	for owner, field in (
		(core, "_isSilence"),
		(core, "_player"),
		(core._veCallbackHandler, "_isSilence"),
		(core._veCallbackHandler, "_player"),
	):
		missing_here = (owner is core and field == missing) or (
			owner is core._veCallbackHandler and missing == f"callback.{field}"
		)
		if not missing_here:
			assert not isinstance(getattr(owner, field), engine_harness.module._IdleRoutingPlayer)
			if field == "_isSilence":
				assert type(getattr(owner, field)) is threading.Event


def test_missing_callback_falls_back_without_partial_install(engine_harness):
	core = engine_harness.new_core(missing="_veCallbackHandler")
	assert core.supportsCancellationToken is False
	assert type(inner_stop_flag(core)) is threading.Event
	assert player_of(core) is not None


@pytest.mark.parametrize(
	"method,args",
	[
		("speak", (["text"],)),
		("_speak", ("voice", ["text"])),
		("cancel", ()),
		("_onIndexReached", (7,)),
	],
)
def test_fallback_delegates_each_original_method(engine_harness, monkeypatch, method, args):
	calls = []
	monkeypatch.setattr(
		engine_harness.original_driver.SynthDriver,
		method,
		lambda self, *received: calls.append(received) or "parent result",
	)
	core = engine_harness.new_core(missing="_feedBuf")
	assert getattr(core, method)(*args) == "parent result"
	assert calls == [args]


def test_assignment_failure_falls_back_unchanged(engine_harness, monkeypatch):
	module = engine_harness.module
	setter = module.SynthDriver.__setattr__

	def fail_stand_in(self, name, value):
		if name == "_player" and isinstance(value, module._IdleRoutingPlayer):
			raise RuntimeError("injected install failure")
		setter(self, name, value)

	monkeypatch.setattr(module.SynthDriver, "__setattr__", fail_stand_in)
	core = engine_harness.new_core()
	assert core.supportsCancellationToken is False
	assert player_of(core) is player_of(callback_handler(core))
	assert type(inner_stop_flag(core)) is threading.Event


def test_callback_rejects_audio_outside_native_call(engine_harness):
	core = engine_harness.new_core()
	types = engine_harness.types
	out_data = types.VE_OUTDATA()
	message = native_message(types, types.VE_MSG_OUTBUFREQ, out_data)
	assert callback_handler(core)(None, None, message) == types.NUAN_E_TTS_USERSTOP
	assert real_player(core).fed == []


def test_token_cancellation_rejects_real_callback_before_core_cancel(engine_harness, monkeypatch):
	core, token = ready_core(engine_harness), Token()
	results = []
	native_entered, release_native = threading.Event(), threading.Event()

	def native(instance, text):
		native_entered.set()
		assert release_native.wait(HOLD_TIMEOUT)
		out_data = engine_harness.types.VE_OUTDATA()
		for message_type in (
			engine_harness.types.VE_MSG_OUTBUFREQ,
			engine_harness.types.VE_MSG_OUTBUFDONE,
		):
			results.append(
				callback_handler(core)(
					instance if engine_harness.engine == "VE" else None,
					None,
					native_message(engine_harness.types, message_type, out_data),
				),
			)

	monkeypatch.setattr(engine_harness.native, "processText2Speech", native)
	worker = threading.Thread(
		target=speak_now,
		args=(core, ["old"]),
		kwargs={"cancellationToken": token},
	)
	worker.start()
	assert native_entered.wait(WAIT_TIMEOUT)
	token.cancel()
	release_native.set()
	worker.join(WAIT_TIMEOUT)
	assert not worker.is_alive()
	assert results == [engine_harness.types.NUAN_E_TTS_USERSTOP] * 2
	assert real_player(core).fed == []
	assert real_player(core).idles == 0


def test_cancelled_native_piece_rejects_callback_and_never_starts_next_piece(engine_harness, monkeypatch):
	core, token = ready_core(engine_harness), Token()
	native_entered = threading.Event()
	release_native = threading.Event()
	spoken_after_cancel = []
	callback_results = []
	monkeypatch.setattr(
		engine_harness.module,
		"split_speech_text_pieces",
		lambda text: ["first", "second"],
		raising=False,
	)

	def native(instance, text):
		if token.is_cancelled():
			spoken_after_cancel.append(text)
		native_entered.set()
		assert release_native.wait(HOLD_TIMEOUT)
		out_data = engine_harness.types.VE_OUTDATA()
		callback_results.append(
			callback_handler(core)(
				instance if engine_harness.engine == "VE" else None,
				None,
				native_message(
					engine_harness.types,
					engine_harness.types.VE_MSG_OUTBUFREQ,
					out_data,
				),
			),
		)

	monkeypatch.setattr(engine_harness.native, "processText2Speech", native)
	worker = threading.Thread(
		target=speak_now,
		args=(core, ["old"]),
		kwargs={"cancellationToken": token},
	)
	worker.start()
	assert native_entered.wait(WAIT_TIMEOUT)
	token.cancel()
	release_native.set()
	worker.join(WAIT_TIMEOUT)
	assert not worker.is_alive()
	assert callback_results == [engine_harness.types.NUAN_E_TTS_USERSTOP]
	assert spoken_after_cancel == []
	assert real_player(core).fed == []
	assert real_player(core).idles == 0


def test_cancel_during_real_callback_feed_stops_after_feed(engine_harness, monkeypatch):
	core, token = ready_core(engine_harness), Token()
	feed_entered, release_feed = threading.Event(), threading.Event()

	def slow_feed(data):
		feed_entered.set()
		assert release_feed.wait(HOLD_TIMEOUT)
		real_player(core).fed.append(data)

	real_player(core).feed = slow_feed
	callback_handler(core)._ensureSonicStream = lambda: False
	monkeypatch.setattr(
		engine_harness.native,
		"processText2Speech",
		lambda instance, text: emit_audio(
			core,
			engine_harness.types,
			b"sound",
			engine_harness.types.NUAN_E_TTS_USERSTOP,
		),
	)
	worker = threading.Thread(
		target=speak_now,
		args=(core, ["old"]),
		kwargs={"cancellationToken": token},
	)
	worker.start()
	assert feed_entered.wait(WAIT_TIMEOUT)
	token.cancel()
	assert real_player(core).stops == 0
	release_feed.set()
	worker.join(WAIT_TIMEOUT)
	assert not worker.is_alive()
	assert real_player(core).fed == [b"sound"]
	assert real_player(core).stops == 1
	assert real_player(core).idles == 0


def test_cancellation_does_not_restart_at_next_piece(engine_harness, monkeypatch):
	core, token = ready_core(engine_harness), Token()
	called = []
	monkeypatch.setattr(
		engine_harness.module,
		"split_speech_text_pieces",
		lambda text: ["first", "second"],
		raising=False,
	)

	def native(instance, text):
		called.append(text)
		core.cancel()

	monkeypatch.setattr(engine_harness.native, "processText2Speech", native)
	speak_now(core, ["old"], cancellationToken=token)
	assert called == ["first"]
	assert real_player(core).idles == 0
	core._speak("voice", ["later chunk"])
	assert called == ["first"]


def test_cancelled_request_drops_index_and_done_notifications(engine_harness, monkeypatch):
	core = ready_core(engine_harness)
	indexes, dones = record_notifications(engine_harness, monkeypatch)
	live, cancelled = Token(), Token()

	def native(instance, text):
		if text == "live":
			core._onIndexReached(6)
		else:
			cancelled.cancel()
			core._onIndexReached(7)

	monkeypatch.setattr(engine_harness.native, "processText2Speech", native)
	speak_now(core, ["live"], cancellationToken=live)
	assert indexes == [6]
	assert dones == [core]
	speak_now(core, ["cancelled"], cancellationToken=cancelled)
	assert indexes == [6]
	assert dones == [core]


@pytest.mark.parametrize("use_token", [True, False])
def test_direct_core_cancel_still_reports_done(engine_harness, monkeypatch, use_token):
	core = ready_core(engine_harness)
	token = Token() if use_token else None
	indexes, dones = [], []
	monkeypatch.setattr(
		engine_harness.original_driver.synthIndexReached,
		"notify",
		lambda **kwargs: indexes.append(kwargs),
	)
	monkeypatch.setattr(
		engine_harness.original_driver.synthDoneSpeaking,
		"notify",
		lambda **kwargs: dones.append(kwargs),
	)

	def native(instance, text):
		core.cancel()
		core._onIndexReached(7)

	monkeypatch.setattr(engine_harness.native, "processText2Speech", native)
	speak_now(core, ["old"], cancellationToken=token)
	assert indexes == []
	assert dones == [{"synth": core}]
	assert real_player(core).idles == 0


def test_cancelled_token_before_core_cancel_reports_nothing(engine_harness, monkeypatch):
	core, token = ready_core(engine_harness), Token()
	indexes, dones = [], []
	monkeypatch.setattr(
		engine_harness.original_driver.synthIndexReached,
		"notify",
		lambda **kwargs: indexes.append(kwargs),
	)
	monkeypatch.setattr(
		engine_harness.original_driver.synthDoneSpeaking,
		"notify",
		lambda **kwargs: dones.append(kwargs),
	)

	def native(instance, text):
		token.cancel()
		core._onIndexReached(7)
		core.cancel()

	monkeypatch.setattr(engine_harness.native, "processText2Speech", native)
	speak_now(core, ["old"], cancellationToken=token)
	assert indexes == []
	assert dones == []
	assert real_player(core).idles == 0


def test_new_request_drops_old_callback_buffer_and_sonic_tail(engine_harness, monkeypatch):
	core = ready_core(engine_harness)
	callback = callback_handler(core)
	callback._feedBuf = BytesIO(b"old buffered")
	callback._sonicSpeed = 1.4
	callback._sonicEnabled = True
	callback._sonicInitTried = True

	class OldSonic:
		def flush(self):
			pytest.fail("old Sonic tail was flushed")

	callback.sonicStream = OldSonic()

	def native(instance, text):
		assert buffered_audio(callback) == b""
		assert callback.sonicStream is None
		assert sonic_state(callback).enabled is False
		assert sonic_state(callback).init_tried is False
		callback._ensureSonicStream = lambda: False
		emit_audio(core, engine_harness.types, b"new")

	monkeypatch.setattr(engine_harness.native, "processText2Speech", native)
	speak_now(core, ["fresh"], cancellationToken=Token())
	assert sonic_state(callback).speed == 1.4
	assert real_player(core).fed == [b"new"]


def test_failed_sonic_init_is_not_retried_on_next_speak(engine_harness, monkeypatch):
	core = ready_core(engine_harness)
	callback = callback_handler(core)
	callback._sonicInitTried = True
	callback._sonicEnabled = False
	callback.sonicStream = None
	callback._feedBuf = BytesIO(b"old buffered")
	seen = []

	def native(instance, text):
		state = sonic_state(callback)
		seen.append((state.init_tried, state.enabled, buffered_audio(callback)))

	monkeypatch.setattr(engine_harness.native, "processText2Speech", native)
	speak_now(core, ["first"], cancellationToken=Token())
	speak_now(core, ["second"], cancellationToken=Token())
	assert seen == [(True, False, b"")] * 2
	assert callback._ensureSonicStream() is False


def test_untokened_speech_and_cancel_remain_usable(engine_harness, monkeypatch):
	core = ready_core(engine_harness)
	callback_handler(core)._ensureSonicStream = lambda: False
	monkeypatch.setattr(
		engine_harness.native,
		"processText2Speech",
		lambda instance, text: emit_audio(core, engine_harness.types, text.encode()),
	)
	speak_now(core, ["first"])
	core.cancel()
	speak_now(core, ["second"])
	assert real_player(core).fed == [b"first", b"second"]
	assert real_player(core).stops == 1
	assert real_player(core).idles == 2


def test_guard_keeps_original_normalization_and_rate_settings(engine_harness, monkeypatch):
	core = ready_core(engine_harness)
	core.availableNormalizations = {"OFF": object(), "NFC": object()}
	core._set_normalization("NFC")
	assert core.normalization == "NFC"
	core._rateBoost = True
	parameters = []
	monkeypatch.setattr(
		engine_harness.native,
		"setParamList",
		lambda instance, *values: parameters.append((instance, values)),
	)
	core._set_rate(50)
	if has_segment_host(core):
		# VE applies settings in order on the inner BgThread queue.
		eventually(lambda: background_idle(core))
	assert parameters == [(core.voiceInstance, ((engine_harness.types.VE_PARAM_SPEECHRATE, 100),))]
	assert callback_handler(core).getSpeed() == 3.25


def test_guard_keeps_original_pause_and_terminate(engine_harness, monkeypatch):
	core = engine_harness.new_core()
	core.pause(True)
	core.pause(False)
	assert real_player(core).pauses == [True, False]
	closed, terminated = [], []
	core._instanceCache["voice"] = "instance"
	monkeypatch.setattr(engine_harness.native, "close", lambda instance: closed.append(instance))
	monkeypatch.setattr(engine_harness.native, "terminate", lambda: terminated.append(True))
	core.terminate()
	assert closed == ["instance"]
	assert terminated == [True]
	assert cached_instances(core) == {}
	assert real_player(core).closes == 1
	assert native_callback(core) is None


def record_notifications(engine_harness, monkeypatch):
	indexes, dones = [], []
	monkeypatch.setattr(
		engine_harness.original_driver.synthIndexReached,
		"notify",
		lambda **kwargs: indexes.append(kwargs["index"]),
	)
	monkeypatch.setattr(
		engine_harness.original_driver.synthDoneSpeaking,
		"notify",
		lambda **kwargs: dones.append(kwargs["synth"]),
	)
	return indexes, dones


def speak_live_request(engine_harness, monkeypatch, core):
	# A finished live request must leave no running request behind it.
	called = []
	monkeypatch.setattr(
		engine_harness.native,
		"processText2Speech",
		lambda instance, text: called.append(text),
	)
	speak_now(core, ["live"])
	assert len(called) == 1
	assert real_player(core).idles == 1
	return called


def test_done_of_never_spoken_request_skips_idle(engine_harness, monkeypatch):
	# A request whose token is cancelled before its turn never begins: its DONE
	# idle has nothing to wait for, and its DONE stays silent.
	core, token = ready_core(engine_harness), Token()
	indexes, dones = record_notifications(engine_harness, monkeypatch)
	called = speak_live_request(engine_harness, monkeypatch, core)
	assert dones == [core]
	token.cancel()
	speak_now(core, ["old"], cancellationToken=token)
	assert len(called) == 1
	assert real_player(core).idles == 1
	assert dones == [core]
	assert indexes == []


def test_index_without_running_request_is_dropped(engine_harness, monkeypatch):
	core = ready_core(engine_harness)
	indexes, dones = record_notifications(engine_harness, monkeypatch)
	speak_live_request(engine_harness, monkeypatch, core)
	assert dones == [core]
	core._onIndexReached(5)
	assert indexes == []
	assert dones == [core]


def send(core, types, instance, message_type, out_data):
	return callback_handler(core)(instance, None, native_message(types, message_type, out_data))


def test_core_cancel_during_real_callback_feed_stops_after_feed(engine_harness, monkeypatch):
	core, types = ready_core(engine_harness), engine_harness.types
	feed_entered, release_feed = threading.Event(), threading.Event()
	results, stops = [], []

	def slow_feed(data):
		feed_entered.set()
		assert release_feed.wait(HOLD_TIMEOUT)
		real_player(core).fed.append(data)

	real_player(core).feed = slow_feed
	callback_handler(core)._ensureSonicStream = lambda: False

	def native(instance, text):
		out_data = types.VE_OUTDATA()
		results.append(send(core, types, instance, types.VE_MSG_OUTBUFREQ, out_data))
		ctypes.memmove(out_data.pOutPcmBuf, b"sound", 5)
		out_data.cntPcmBufLen = 5
		out_data.cntMrkListLen = 0
		results.append(send(core, types, instance, types.VE_MSG_OUTBUFDONE, out_data))

	monkeypatch.setattr(engine_harness.native, "processText2Speech", native)
	worker = threading.Thread(target=speak_now, args=(core, ["old"]))
	worker.start()
	assert feed_entered.wait(WAIT_TIMEOUT)
	stopper = threading.Thread(target=core.cancel)
	stopper.start()
	stopper.join(WAIT_TIMEOUT)
	assert not stopper.is_alive()
	stops.append(real_player(core).stops)
	release_feed.set()
	worker.join(WAIT_TIMEOUT)
	assert not worker.is_alive()
	assert results == [types.NUAN_OK, types.NUAN_E_TTS_USERSTOP]
	assert real_player(core).fed == [b"sound"]
	# The feed that was admitted before cancel is stopped again once it returns.
	assert real_player(core).stops > stops[0]
	assert real_player(core).idles == 0


def test_callback_after_core_cancel_feeds_nothing(engine_harness, monkeypatch):
	core, types = ready_core(engine_harness), engine_harness.types
	callback_handler(core)._ensureSonicStream = lambda: False
	results = []

	def native(instance, text):
		out_data = types.VE_OUTDATA()
		results.append(send(core, types, instance, types.VE_MSG_OUTBUFREQ, out_data))
		core.cancel()
		results.append(send(core, types, instance, types.VE_MSG_OUTBUFREQ, out_data))
		ctypes.memmove(out_data.pOutPcmBuf, b"late", 4)
		out_data.cntPcmBufLen = 4
		out_data.cntMrkListLen = 0
		results.append(send(core, types, instance, types.VE_MSG_OUTBUFDONE, out_data))

	monkeypatch.setattr(engine_harness.native, "processText2Speech", native)
	speak_now(core, ["old"])
	assert results == [types.NUAN_OK] + [types.NUAN_E_TTS_USERSTOP] * 2
	assert real_player(core).fed == []
	assert real_player(core).idles == 0


def test_cancel_while_request_begins_stays_stopped(engine_harness, monkeypatch):
	core, token = ready_core(engine_harness), Token()
	host = core._segmentHost
	entry_paused, release_entry = threading.Event(), threading.Event()
	begin = host.begin

	def paused_begin(record):
		# host.begin runs in the worker's begin task, after its validity check.
		entry_paused.set()
		assert release_entry.wait(HOLD_TIMEOUT)
		return begin(record)

	monkeypatch.setattr(host, "begin", paused_begin)
	called = []
	monkeypatch.setattr(
		engine_harness.native,
		"processText2Speech",
		lambda instance, text: called.append(text),
	)
	worker = threading.Thread(target=speak_now, args=(core, ["old"]), kwargs={"cancellationToken": token})
	worker.start()
	assert entry_paused.wait(WAIT_TIMEOUT)
	token.cancel()
	stopper = threading.Thread(target=core.cancel)
	stopper.start()
	release_entry.set()
	worker.join(WAIT_TIMEOUT)
	stopper.join(WAIT_TIMEOUT)
	assert not worker.is_alive() and not stopper.is_alive()
	assert called == []
	assert real_player(core).fed == []
	assert real_player(core).idles == 0


def test_native_call_admission_closes_after_exception(engine_harness, monkeypatch):
	core, types = ready_core(engine_harness), engine_harness.types
	instances, results = [], []

	def fail(instance, text):
		instances.append(instance)
		results.append(send(core, types, instance, types.VE_MSG_OUTBUFREQ, types.VE_OUTDATA()))
		raise RuntimeError("native failed")

	monkeypatch.setattr(engine_harness.native, "processText2Speech", fail)
	speak_now(core, ["old"], cancellationToken=Token())
	assert results == [types.NUAN_OK]
	assert native_call(core) is None
	assert (
		send(core, types, instances[0], types.VE_MSG_OUTBUFREQ, types.VE_OUTDATA())
		== types.NUAN_E_TTS_USERSTOP
	)


def test_dropped_request_done_skips_idle_and_reports_done(engine_harness, monkeypatch):
	core = ready_core(engine_harness)
	indexes, dones = record_notifications(engine_harness, monkeypatch)
	entered, release = threading.Event(), threading.Event()
	called = []

	def native(instance, text):
		called.append(text)
		entered.set()
		assert release.wait(HOLD_TIMEOUT)
		core.cancel()

	monkeypatch.setattr(engine_harness.native, "processText2Speech", native)
	core.speak(["first"])
	assert entered.wait(WAIT_TIMEOUT)
	core.speak(["second"])
	release.set()
	eventually(lambda: background_idle(core))
	assert called == ["first"]
	# Like the add-on's cancel: queued speech is dropped, its DONE kept.
	assert dones == [core, core]
	assert indexes == []
	assert real_player(core).idles == 0
	assert real_player(core).fed == []


@pytest.mark.parametrize("cancel_kind", ["core", "token"])
def test_endprocess_after_cancel_feeds_no_sonic_tail(engine_harness, monkeypatch, cancel_kind):
	core, types, token = ready_core(engine_harness), engine_harness.types, Token()
	callback = callback_handler(core)
	flushed, results = [], []

	class Sonic:
		speed = 1.0

		def writeShort(self, *args):
			pass

		def readShort(self):
			return b"tail"

		def flush(self):
			flushed.append(True)

	def sonic():
		callback.sonicStream = Sonic()
		callback._sonicEnabled = True
		return True

	callback._ensureSonicStream = sonic

	def native(instance, text):
		out_data = types.VE_OUTDATA()
		results.append(send(core, types, instance, types.VE_MSG_OUTBUFREQ, out_data))
		ctypes.memmove(out_data.pOutPcmBuf, b"pcm!", 4)
		out_data.cntPcmBufLen = 4
		out_data.cntMrkListLen = 0
		results.append(send(core, types, instance, types.VE_MSG_OUTBUFDONE, out_data))
		if cancel_kind == "core":
			core.cancel()
		else:
			token.cancel()
		results.append(send(core, types, instance, types.VE_MSG_ENDPROCESS, out_data))

	monkeypatch.setattr(engine_harness.native, "processText2Speech", native)
	speak_now(core, ["old"], cancellationToken=token)
	# Core cancel closes the call's admission; a token cancel keeps the legacy
	# ENDPROCESS acknowledgement. Neither flushes or feeds the buffered tail.
	last = types.NUAN_E_TTS_USERSTOP if cancel_kind == "core" else types.NUAN_OK
	assert results == [types.NUAN_OK, types.NUAN_OK, last]
	assert flushed == []
	assert real_player(core).fed == []


class RecordingEvent(threading.Event):
	def __init__(self):
		super().__init__()
		self.calls = []

	def set(self):
		self.calls.append("set")
		super().set()

	def clear(self):
		self.calls.append("clear")
		super().clear()

	def is_set(self):
		self.calls.append("is_set")
		return super().is_set()

	isSet = is_set


def test_guarded_speech_never_touches_inner_stop_flag(engine_harness, monkeypatch):
	# Like RHVoice's wrapper, the guard leaves the inner stop Event to the inner driver.
	core = ready_core(engine_harness)
	flag = RecordingEvent()
	core._isSilence = callback_handler(core)._isSilence = flag
	callback_handler(core)._ensureSonicStream = lambda: False
	monkeypatch.setattr(
		engine_harness.native,
		"processText2Speech",
		lambda instance, text: emit_audio(core, engine_harness.types, text.encode()),
	)
	speak_now(core, ["first"], cancellationToken=Token())
	core.cancel()
	speak_now(core, ["second"])
	assert flag.calls == []
	assert real_player(core).fed == [b"first", b"second"]
	core.pause(True)
	core.pause(False)
	assert real_player(core).pauses == [True, False]
	# The inner terminate calls cancel; it must return before the inner cancel
	# would set the flag.
	monkeypatch.setattr(engine_harness.native, "close", lambda instance: None)
	monkeypatch.setattr(engine_harness.native, "terminate", lambda: None)
	core.terminate()
	assert real_player(core).closes == 1
	assert flag.calls == []


@pytest.mark.parametrize("cancel_kind", ["core", "token"])
def test_cancel_before_native_call_starts_skips_it(engine_harness, monkeypatch, cancel_kind):
	# A cancel after the piece's first validity check, before its native call is
	# installed, must still keep the SDK call from starting.
	core, token = ready_core(engine_harness), Token()
	module = engine_harness.module
	entered, release = threading.Event(), threading.Event()
	native_call_type = module._NativeCall

	def paused_call(record, instance):
		entered.set()
		assert release.wait(HOLD_TIMEOUT)
		return native_call_type(record, instance)

	monkeypatch.setattr(module, "_NativeCall", paused_call)
	called = []
	monkeypatch.setattr(
		engine_harness.native,
		"processText2Speech",
		lambda instance, text: called.append(text),
	)
	worker = threading.Thread(target=speak_now, args=(core, ["old"]), kwargs={"cancellationToken": token})
	worker.start()
	assert entered.wait(WAIT_TIMEOUT)
	if cancel_kind == "core":
		core.cancel()
	else:
		token.cancel()
	release.set()
	worker.join(WAIT_TIMEOUT)
	assert not worker.is_alive()
	assert called == []
	assert real_player(core).fed == []
	assert real_player(core).idles == 0
