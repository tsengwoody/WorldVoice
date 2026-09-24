import ctypes
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


def test_ve_installs_gate_on_core_and_existing_callback(ve_harness):
	core = ve_harness.new_core()
	assert core.supportsCancellationToken is True
	assert core._isSilence is core._veCallbackHandler._isSilence
	assert core._player is core._veCallbackHandler._player
	assert isinstance(core._isSilence, ve_harness.module._SilenceGate)
	assert core._player._real is core._real_player
	assert ve_harness.module.Voice.synth_driver_class is ve_harness.original_driver.SynthDriver


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
