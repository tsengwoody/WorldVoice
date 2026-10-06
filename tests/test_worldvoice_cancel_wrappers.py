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
	guarded_real_player,
	has_segment_host,
	inside_native_call,
	load_real_driver_with_native_stubs,
	native_call,
	native_callback,
	native_message,
	player_of,
	real_player,
	silence_gate,
	sonic_state,
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


def test_installs_gate_on_core_and_existing_callback(engine_harness):
	core = engine_harness.new_core()
	assert core.supportsCancellationToken is True
	handler = callback_handler(core)
	assert silence_gate(core) is silence_gate(handler)
	assert player_of(core) is player_of(handler)
	assert isinstance(silence_gate(core), engine_harness.module._SilenceGate)
	assert guarded_real_player(player_of(core)) is real_player(core)
	assert engine_harness.module.Voice.synth_driver_class is engine_harness.module.SynthDriver


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
			assert not isinstance(
				getattr(owner, field),
				(engine_harness.module._SilenceGate, engine_harness.module._GuardedPlayer),
			)


def test_missing_callback_falls_back_without_partial_install(engine_harness):
	core = engine_harness.new_core(missing="_veCallbackHandler")
	assert core.supportsCancellationToken is False
	assert type(silence_gate(core)) is threading.Event
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


def test_assignment_failure_restores_all_four_references(engine_harness):
	original = {}

	class FailOnceProxy:
		def __init__(self, real):
			original["core_gate"] = real._isSilence
			original["core_player"] = real._player
			real._isSilence = threading.Event()
			real._player = type(real._player)()
			original["callback_gate"] = real._isSilence
			original["callback_player"] = real._player
			object.__setattr__(self, "real", real)
			object.__setattr__(self, "failed", False)

		def __getattr__(self, name):
			return getattr(self.real, name)

		def __setattr__(self, name, value):
			if name == "_player" and not self.failed:
				object.__setattr__(self, "failed", True)
				raise RuntimeError("injected install failure")
			setattr(self.real, name, value)

	core = engine_harness.new_core(callback_proxy=FailOnceProxy)
	assert core.supportsCancellationToken is False
	handler = callback_handler(core)
	assert silence_gate(core) is original["core_gate"]
	assert player_of(core) is original["core_player"]
	assert silence_gate(handler) is original["callback_gate"]
	assert player_of(handler) is original["callback_player"]


def test_restoration_failure_raises_instead_of_returning_partial_core(engine_harness):
	created = []

	class FailInstallAndRestoreProxy:
		def __init__(self, real):
			object.__setattr__(self, "real", real)
			created.append(self)

		def __getattr__(self, name):
			return getattr(self.real, name)

		def __setattr__(self, name, value):
			if name == "_player":
				raise RuntimeError("installation setter failed")
			if name == "_isSilence" and type(value) is threading.Event:
				raise RuntimeError("restoration setter failed")
			setattr(self.real, name, value)

	with pytest.raises(RuntimeError, match="restoration"):
		engine_harness.new_core(callback_proxy=FailInstallAndRestoreProxy)
	assert isinstance(silence_gate(created[0].real), engine_harness.module._SilenceGate)


def test_gate_checks_token_only_during_native_call(engine_harness):
	gate = engine_harness.module._SilenceGate()
	token = type("Token", (), {"is_cancelled": lambda self: False})()
	gate.begin(token)
	assert gate.cancelled() is False
	assert gate.is_set() is True
	gate._inside_native_call = True
	assert gate.isSet() is False
	gate.set()
	gate.clear()
	assert gate.cancelled() is True
	gate.begin(token)
	assert gate.cancelled() is False
	token.is_cancelled = lambda: True
	assert gate.cancelled() is True


def test_callback_rejects_audio_outside_native_call(engine_harness):
	core = engine_harness.new_core()
	types = engine_harness.types
	out_data = types.VE_OUTDATA()
	message = native_message(types, types.VE_MSG_OUTBUFREQ, out_data)
	assert callback_handler(core)(None, None, message) == types.NUAN_E_TTS_USERSTOP
	assert real_player(core).fed == []


def test_player_stops_after_feed_when_cancelled_mid_feed(engine_harness):
	core = engine_harness.new_core()
	gate = silence_gate(core)
	gate.begin(None)
	real_player(core).feed = lambda data: gate.set()
	player_of(core).feed(b"sound")
	assert real_player(core).stops == 1
	player_of(core).idle()
	assert real_player(core).idles == 0


def test_player_skips_feed_when_already_cancelled(engine_harness):
	core = engine_harness.new_core()
	silence_gate(core).set()
	player_of(core).feed(b"discard")
	assert real_player(core).fed == []


def test_cancel_between_token_check_and_clear_stays_stopped(engine_harness, monkeypatch):
	core, token = ready_core(engine_harness), Token()
	entry_paused, release_entry = threading.Event(), threading.Event()
	gate = silence_gate(core)
	begin = gate.begin

	def paused_begin(received):
		entry_paused.set()
		assert release_entry.wait(HOLD_TIMEOUT)
		return begin(received)

	monkeypatch.setattr(gate, "begin", paused_begin)
	called = []
	monkeypatch.setattr(
		engine_harness.native,
		"processText2Speech",
		lambda instance, text: called.append(text),
	)
	worker = threading.Thread(
		target=speak_now,
		args=(core, ["old"]),
		kwargs={"cancellationToken": token},
	)
	worker.start()
	assert entry_paused.wait(WAIT_TIMEOUT)
	token.cancel()
	stopper = threading.Thread(target=core.cancel)
	stopper.start()
	release_entry.set()
	worker.join(WAIT_TIMEOUT)
	stopper.join(WAIT_TIMEOUT)
	assert not worker.is_alive() and not stopper.is_alive()
	assert gate.cancelled()
	assert called == []
	assert real_player(core).fed == []


def test_native_call_marker_clears_after_exception(engine_harness, monkeypatch):
	core = ready_core(engine_harness)

	def fail(instance, text):
		raise RuntimeError("native failed")

	monkeypatch.setattr(engine_harness.native, "processText2Speech", fail)
	if has_segment_host(core):
		# Asynchronous speech: the native error stays with the worker's record.
		speak_now(core, ["old"], cancellationToken=Token())
	else:
		with pytest.raises(RuntimeError, match="native failed"):
			speak_now(core, ["old"], cancellationToken=Token())
	assert inside_native_call(core) is False


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
	silence_gate(core).begin(token)
	core._onIndexReached(6)
	core._onIndexReached(None)
	token.cancel()
	core._onIndexReached(7)
	core._onIndexReached(None)
	assert indexes == [{"synth": core, "index": 6}]
	assert dones == [{"synth": core}]


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
