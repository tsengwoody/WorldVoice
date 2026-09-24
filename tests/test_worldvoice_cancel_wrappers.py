import ctypes
from io import BytesIO
import threading

import pytest

from worldvoice_cancel_wrapper_harness import load_ve_harness


@pytest.fixture
def ve_harness(monkeypatch):
	return load_ve_harness(monkeypatch)


def native_message(types, message_type, out_data):
	message = types.VE_CALLBACKMSG()
	message.eMessage = message_type
	message.pParam = ctypes.cast(ctypes.pointer(out_data), ctypes.c_void_p)
	return ctypes.pointer(message)


def ready_core(ve_harness):
	core = ve_harness.new_core()
	core.voiceInstance = "voice"
	core.language = "en"
	core._normalization = "OFF"
	return core


class Token:
	def __init__(self):
		self._cancelled = False

	def cancel(self):
		self._cancelled = True

	def is_cancelled(self):
		return self._cancelled


def emit_audio(core, types, payload=b"new", done_result=None):
	callback = core._veCallbackHandler
	if done_result is None:
		done_result = types.NUAN_OK
	out_data = types.VE_OUTDATA()
	assert callback(None, None, native_message(types, types.VE_MSG_OUTBUFREQ, out_data)) == types.NUAN_OK
	ctypes.memmove(out_data.pOutPcmBuf, payload, len(payload))
	out_data.cntPcmBufLen = len(payload)
	out_data.cntMrkListLen = 0
	assert callback(None, None, native_message(types, types.VE_MSG_OUTBUFDONE, out_data)) == done_result
	assert callback(None, None, native_message(types, types.VE_MSG_ENDPROCESS, out_data)) == types.NUAN_OK


def test_ve_installs_gate_on_core_and_existing_callback(ve_harness):
	core = ve_harness.new_core()
	assert core.supportsCancellationToken is True
	assert core._isSilence is core._veCallbackHandler._isSilence
	assert core._player is core._veCallbackHandler._player
	assert isinstance(core._isSilence, ve_harness.module._SilenceGate)
	assert core._player._real is core._real_player
	assert ve_harness.module.Voice.synth_driver_class is ve_harness.module.CancellableSynthDriver


@pytest.mark.parametrize("missing", ["_isSilence", "_player", "callback._isSilence",
	"callback._player", "_feedBuf"])
def test_ve_missing_private_field_falls_back_without_partial_install(ve_harness, missing):
	core = ve_harness.new_core(missing=missing)
	assert core.supportsCancellationToken is False
	for owner, field in ((core, "_isSilence"), (core, "_player"),
		(core._veCallbackHandler, "_isSilence"), (core._veCallbackHandler, "_player")):
		missing_here = (owner is core and field == missing) or (
			owner is core._veCallbackHandler and missing == f"callback.{field}"
		)
		if not missing_here:
			assert not isinstance(
				getattr(owner, field),
				(ve_harness.module._SilenceGate, ve_harness.module._GuardedPlayer),
			)


def test_ve_missing_callback_falls_back_without_partial_install(ve_harness):
	core = ve_harness.new_core(missing="_veCallbackHandler")
	assert core.supportsCancellationToken is False
	assert type(core._isSilence) is threading.Event
	assert core._player is not None


@pytest.mark.parametrize("method,args", [
	("speak", (["text"],)), ("_speak", ("voice", ["text"])),
	("cancel", ()), ("_onIndexReached", (7,)),
])
def test_ve_fallback_delegates_each_original_method(ve_harness, monkeypatch, method, args):
	calls = []
	monkeypatch.setattr(ve_harness.original_driver.SynthDriver, method,
		lambda self, *received: calls.append(received) or "parent result")
	core = ve_harness.new_core(missing="_feedBuf")
	assert getattr(core, method)(*args) == "parent result"
	assert calls == [args]


def test_ve_assignment_failure_restores_all_four_references(ve_harness):
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

	core = ve_harness.new_core(callback_proxy=FailOnceProxy)
	assert core.supportsCancellationToken is False
	assert core._isSilence is original["core_gate"]
	assert core._player is original["core_player"]
	assert core._veCallbackHandler._isSilence is original["callback_gate"]
	assert core._veCallbackHandler._player is original["callback_player"]


def test_ve_restoration_failure_raises_instead_of_returning_partial_core(ve_harness):
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
		ve_harness.new_core(callback_proxy=FailInstallAndRestoreProxy)
	assert isinstance(created[0].real._isSilence, ve_harness.module._SilenceGate)


def test_ve_gate_checks_token_only_during_native_call(ve_harness):
	gate = ve_harness.module._SilenceGate()
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


def test_ve_callback_rejects_audio_outside_native_call(ve_harness):
	core = ve_harness.new_core()
	types = ve_harness.types
	out_data = types.VE_OUTDATA()
	message = native_message(types, types.VE_MSG_OUTBUFREQ, out_data)
	assert core._veCallbackHandler(None, None, message) == types.NUAN_E_TTS_USERSTOP
	assert core._real_player.fed == []


def test_ve_player_stops_after_feed_when_cancelled_mid_feed(ve_harness):
	core = ve_harness.new_core()
	gate = core._isSilence
	gate.begin(None)
	core._real_player.feed = lambda data: gate.set()
	core._player.feed(b"sound")
	assert core._real_player.stops == 1
	core._player.idle()
	assert core._real_player.idles == 0


def test_ve_player_skips_feed_when_already_cancelled(ve_harness):
	core = ve_harness.new_core()
	core._isSilence.set()
	core._player.feed(b"discard")
	assert core._real_player.fed == []


def test_ve_cancel_between_token_check_and_clear_stays_stopped(ve_harness, monkeypatch):
	core, token = ready_core(ve_harness), Token()
	entry_paused, release_entry = threading.Event(), threading.Event()
	begin = core._isSilence.begin

	def paused_begin(received):
		entry_paused.set()
		assert release_entry.wait(1)
		return begin(received)

	monkeypatch.setattr(core._isSilence, "begin", paused_begin)
	called = []
	monkeypatch.setattr(ve_harness.original_driver.ve2, "processText2Speech",
		lambda instance, text: called.append(text))
	worker = threading.Thread(target=core.speak, args=(["old"],),
		kwargs={"cancellationToken": token})
	worker.start()
	assert entry_paused.wait(1)
	token.cancel()
	stopper = threading.Thread(target=core.cancel)
	stopper.start()
	release_entry.set()
	worker.join(1)
	stopper.join(1)
	assert not worker.is_alive() and not stopper.is_alive()
	assert core._isSilence.cancelled()
	assert called == []
	assert core._real_player.fed == []


def test_ve_native_call_marker_clears_after_exception(ve_harness, monkeypatch):
	core = ready_core(ve_harness)
	def fail(instance, text):
		raise RuntimeError("native failed")
	monkeypatch.setattr(ve_harness.original_driver.ve2, "processText2Speech", fail)
	with pytest.raises(RuntimeError, match="native failed"):
		core.speak(["old"], cancellationToken=Token())
	assert core._isSilence._inside_native_call is False


def test_ve_token_cancellation_rejects_real_callback_before_core_cancel(ve_harness, monkeypatch):
	core, token = ready_core(ve_harness), Token()
	results = []
	native_entered, release_native = threading.Event(), threading.Event()
	def native(instance, text):
		native_entered.set()
		assert release_native.wait(1)
		out_data = ve_harness.types.VE_OUTDATA()
		for message_type in (ve_harness.types.VE_MSG_OUTBUFREQ,
			ve_harness.types.VE_MSG_OUTBUFDONE):
			results.append(core._veCallbackHandler(None, None,
				native_message(ve_harness.types, message_type, out_data)))
	monkeypatch.setattr(ve_harness.original_driver.ve2, "processText2Speech", native)
	worker = threading.Thread(target=core.speak, args=(["old"],),
		kwargs={"cancellationToken": token})
	worker.start()
	assert native_entered.wait(1)
	token.cancel()
	release_native.set()
	worker.join(1)
	assert not worker.is_alive()
	assert results == [ve_harness.types.NUAN_E_TTS_USERSTOP] * 2
	assert core._real_player.fed == []
	assert core._real_player.idles == 0


def test_ve_cancel_during_real_callback_feed_stops_after_feed(ve_harness, monkeypatch):
	core, token = ready_core(ve_harness), Token()
	feed_entered, release_feed = threading.Event(), threading.Event()
	def slow_feed(data):
		feed_entered.set()
		assert release_feed.wait(1)
		core._real_player.fed.append(data)
	core._real_player.feed = slow_feed
	core._veCallbackHandler._ensureSonicStream = lambda: False
	monkeypatch.setattr(ve_harness.original_driver.ve2, "processText2Speech",
		lambda instance, text: emit_audio(core, ve_harness.types, b"sound",
			ve_harness.types.NUAN_E_TTS_USERSTOP))
	worker = threading.Thread(target=core.speak, args=(["old"],),
		kwargs={"cancellationToken": token})
	worker.start()
	assert feed_entered.wait(1)
	token.cancel()
	assert core._real_player.stops == 0
	release_feed.set()
	worker.join(1)
	assert not worker.is_alive()
	assert core._real_player.fed == [b"sound"]
	assert core._real_player.stops == 1
	assert core._real_player.idles == 0


def test_ve_cancellation_does_not_restart_at_next_piece(ve_harness, monkeypatch):
	core, token = ready_core(ve_harness), Token()
	called = []
	monkeypatch.setattr(ve_harness.module, "split_speech_text_pieces",
		lambda text: ["first", "second"], raising=False)
	def native(instance, text):
		called.append(text)
		core.cancel()
	monkeypatch.setattr(ve_harness.original_driver.ve2, "processText2Speech", native)
	core.speak(["old"], cancellationToken=token)
	assert called == ["first"]
	assert core._real_player.idles == 0
	core._speak("voice", ["later chunk"])
	assert called == ["first"]


def test_ve_cancelled_request_drops_index_and_done_notifications(ve_harness, monkeypatch):
	core, token = ready_core(ve_harness), Token()
	indexes, dones = [], []
	monkeypatch.setattr(ve_harness.original_driver.synthIndexReached, "notify",
		lambda **kwargs: indexes.append(kwargs))
	monkeypatch.setattr(ve_harness.original_driver.synthDoneSpeaking, "notify",
		lambda **kwargs: dones.append(kwargs))
	core._isSilence.begin(token)
	core._onIndexReached(6)
	core._onIndexReached(None)
	token.cancel()
	core._onIndexReached(7)
	core._onIndexReached(None)
	assert indexes == [{"synth": core, "index": 6}]
	assert dones == [{"synth": core}]


def test_ve_new_request_drops_old_callback_buffer_and_sonic_tail(ve_harness, monkeypatch):
	core = ready_core(ve_harness)
	callback = core._veCallbackHandler
	callback._feedBuf = BytesIO(b"old buffered")
	callback._sonicSpeed = 1.4
	callback._sonicEnabled = True
	callback._sonicInitTried = True
	class OldSonic:
		def flush(self):
			pytest.fail("old Sonic tail was flushed")
	callback.sonicStream = OldSonic()
	def native(instance, text):
		assert callback._feedBuf.getvalue() == b""
		assert callback.sonicStream is None
		assert callback._sonicEnabled is False
		assert callback._sonicInitTried is False
		callback._ensureSonicStream = lambda: False
		emit_audio(core, ve_harness.types, b"new")
	monkeypatch.setattr(ve_harness.original_driver.ve2, "processText2Speech", native)
	core.speak(["fresh"], cancellationToken=Token())
	assert callback._sonicSpeed == 1.4
	assert core._real_player.fed == [b"new"]


def test_ve_untokened_speech_and_cancel_remain_usable(ve_harness, monkeypatch):
	core = ready_core(ve_harness)
	core._veCallbackHandler._ensureSonicStream = lambda: False
	monkeypatch.setattr(ve_harness.original_driver.ve2, "processText2Speech",
		lambda instance, text: emit_audio(core, ve_harness.types, text.encode()))
	core.speak(["first"])
	core.cancel()
	core.speak(["second"])
	assert core._real_player.fed == [b"first", b"second"]
	assert core._real_player.stops == 1
	assert core._real_player.idles == 2
