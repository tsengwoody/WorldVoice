"""An RHVoice, eSpeak, OneCore or SAPI5 constructor that raises releases what it built and re-raises.

VoiceClassAdapter.open gets no core to terminate when SynthDriver() raises, so the constructor itself
releases, newest first, what the wrapper built: the parent driver once its constructor has returned
(RHVoice, eSpeak), SAPI5's sink, worker and player, OneCore's native callback and token once NVDA's
constructor created them, and always the segment delivery thread. A failing release step is logged and
the rest still run. Anything else a parent constructor left half-built stays out of reach: it cannot be
released safely.
"""

import sys
from types import SimpleNamespace

import pytest
from espeak_drain_harness import Player as EspeakPlayer, finish as finish_espeak, load_espeak
from onecore_drain_harness import load_onecore, native_release_state
from rhvoice_drain_harness import NativeFunction as RHVoiceFunction, finish as finish_rhvoice, load_rhvoice
from runtime_harness import delivery_thread, segment_lifecycle
from sapi5_drain_harness import Native as SapiNative, Player as SapiPlayer, load_sapi5


class Boom(Exception):
	pass


def _fresh_runtime(monkeypatch):
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime._segmentLifecycle", raising=False)
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)


def _record(monkeypatch, outer):
	"""Record the wrapper's segment hosts, release order and error logs."""
	record = SimpleNamespace(hosts=[], calls=[], logged=[])

	class RecordingHost(outer.SegmentHost):
		def __init__(self, *args, **kwargs):
			super().__init__(*args, **kwargs)
			record.hosts.append(self)

		def terminate(self):
			record.calls.append("host")
			return super().terminate()

	class Log:
		def __getattr__(self, level):
			return lambda *args, **kwargs: record.logged.append((level, args, kwargs))

	monkeypatch.setattr(outer, "SegmentHost", RecordingHost)
	monkeypatch.setattr(outer, "log", Log(), raising=False)
	return record


def _assert_host_released(record):
	(host,) = record.hosts
	assert host.terminated
	assert not delivery_thread(segment_lifecycle(host)).is_alive()


def _assert_one_cleanup_error_logged(record, engine):
	((level, args, kwargs),) = record.logged
	assert (level, args, kwargs) == (
		"error",
		(f"WorldVoice {engine} initialization cleanup failed",),
		{"exc_info": True},
	)


# RHVoice --------------------------------------------------------------------


@pytest.fixture
def rhvoice(monkeypatch, tmp_path):
	_fresh_runtime(monkeypatch)
	env = load_rhvoice(monkeypatch, tmp_path)
	finish_rhvoice(env)
	record = _record(monkeypatch, env.outer)
	record.threads, record.players = [], []

	class RecordingThread(env.inner.TTSThread):
		def __init__(self, queue):
			super().__init__(queue)
			record.threads.append(self)

		def join(self, *args, **kwargs):
			record.calls.append("thread")
			return super().join(*args, **kwargs)

	class RecordingPlayer(env.inner.AudioPlayer):
		def __init__(self, *args):
			super().__init__(*args)
			record.players.append(self)

		def close(self):
			record.calls.append("player")
			super().close()

	def deleteEngine(engine):
		record.calls.append("engine")

	monkeypatch.setattr(env.inner, "TTSThread", RecordingThread)
	monkeypatch.setattr(env.inner, "AudioPlayer", RecordingPlayer)
	env.native.RHVoice_delete_tts_engine = RHVoiceFunction(deleteEngine)
	return env, record


def _fail_rhvoice_player_lookup_once(monkeypatch, env):
	# The wrapper's first step after the inner constructor; later lookups (cancel) still work.
	original = env.outer._RHVoiceInner.player
	failed = []

	def player(inner):
		if not failed:
			failed.append(True)
			raise Boom("player lookup failed")
		return original.fget(inner)

	monkeypatch.setattr(env.outer._RHVoiceInner, "player", property(player))


def test_rhvoice_a_failing_inner_constructor_releases_the_host(rhvoice):
	env, record = rhvoice
	env.native.RHVoice_new_tts_engine = RHVoiceFunction(lambda params: 0)
	with pytest.raises(RuntimeError, match="RHVoice: initialization error"):
		env.outer.SynthDriver()
	_assert_host_released(record)
	assert record.threads == []
	assert record.calls == ["host"]


def test_rhvoice_a_failing_step_after_the_inner_constructor_terminates_the_inner_and_host(
	rhvoice,
	monkeypatch,
):
	env, record = rhvoice
	_fail_rhvoice_player_lookup_once(monkeypatch, env)
	with pytest.raises(Boom, match="player lookup failed"):
		env.outer.SynthDriver()
	_assert_host_released(record)
	(thread,) = record.threads
	assert not thread.is_alive()
	assert record.calls == ["thread", "player", "engine", "host"]
	assert record.logged == []


def test_rhvoice_a_failing_cleanup_step_is_logged_and_the_host_still_released(rhvoice, monkeypatch):
	env, record = rhvoice

	def deleteEngine(engine):
		record.calls.append("engine")
		raise RuntimeError("delete failed")

	env.native.RHVoice_delete_tts_engine = RHVoiceFunction(deleteEngine)
	_fail_rhvoice_player_lookup_once(monkeypatch, env)
	with pytest.raises(Boom, match="player lookup failed"):
		env.outer.SynthDriver()
	_assert_host_released(record)
	assert record.calls == ["thread", "player", "engine", "host"]
	_assert_one_cleanup_error_logged(record, "RHVoice")


def test_rhvoice_a_built_core_keeps_its_resources(rhvoice):
	env, record = rhvoice
	driver = env.outer.SynthDriver()
	try:
		assert record.calls == []
		(thread,) = record.threads
		assert thread.is_alive()
		assert not record.hosts[0].terminated
	finally:
		driver.terminate()


# eSpeak ---------------------------------------------------------------------


@pytest.fixture
def espeak(monkeypatch, tmp_path):
	_fresh_runtime(monkeypatch)
	env = load_espeak(monkeypatch, tmp_path)
	# NVDA's eSpeak state is module-global: release the harness driver before building another.
	finish_espeak(env)
	record = _record(monkeypatch, env.outer)
	record.threads, record.players = [], []

	class RecordingThread(env.inner.BgThread):
		def __init__(self):
			super().__init__()
			record.threads.append(self)

		def join(self, *args, **kwargs):
			record.calls.append("thread")
			return super().join(*args, **kwargs)

	class RecordingPlayer(EspeakPlayer):
		def __init__(self, **kwargs):
			super().__init__(**kwargs)
			record.players.append(self)

		def close(self):
			record.calls.append("player")
			super().close()

	def terminate():
		record.calls.append("native")
		return 0

	monkeypatch.setattr(env.inner, "BgThread", RecordingThread)
	monkeypatch.setattr(env.inner.nvwave, "WavePlayer", RecordingPlayer)
	env.native.espeak_Terminate = env.native.espeak_Terminate.__class__(terminate)
	return env, record


def _fail_espeak_install(monkeypatch, env):
	def install(port, host, driver):
		raise Boom("install failed")

	monkeypatch.setattr(env.outer._EspeakPort, "install", install)


def test_espeak_a_failing_nvda_constructor_releases_the_host(espeak):
	env, record = espeak
	env.native.espeak_Initialize = env.native.espeak_Initialize.__class__(lambda *args: -1)
	with pytest.raises(OSError, match="espeak_Initialize failed"):
		env.outer.SynthDriver()
	_assert_host_released(record)
	assert record.threads == []
	assert record.calls == ["host"]


def test_espeak_a_failing_install_terminates_nvda_espeak_and_the_host(espeak, monkeypatch):
	env, record = espeak
	_fail_espeak_install(monkeypatch, env)
	with pytest.raises(Boom, match="install failed"):
		env.outer.SynthDriver()
	_assert_host_released(record)
	(thread,) = record.threads
	assert not thread.is_alive()
	assert [player.closed for player in record.players] == [True]
	assert record.calls == ["thread", "native", "player", "host"]
	assert env.inner.espeakDLL is None
	assert record.logged == []


def test_espeak_a_failing_cleanup_step_is_logged_and_the_host_still_released(espeak, monkeypatch):
	env, record = espeak

	def terminate():
		record.calls.append("native")
		raise RuntimeError("terminate failed")

	env.native.espeak_Terminate = env.native.espeak_Terminate.__class__(terminate)
	_fail_espeak_install(monkeypatch, env)
	with pytest.raises(Boom, match="install failed"):
		env.outer.SynthDriver()
	_assert_host_released(record)
	assert record.calls == ["thread", "native", "host"]
	_assert_one_cleanup_error_logged(record, "eSpeak")


def test_espeak_a_built_core_keeps_its_resources(espeak):
	env, record = espeak
	driver = env.outer.SynthDriver()
	try:
		assert record.calls == []
		(thread,) = record.threads
		assert thread.is_alive()
		assert not record.hosts[0].terminated
	finally:
		driver.terminate()


# OneCore --------------------------------------------------------------------


@pytest.fixture
def onecore(monkeypatch):
	_fresh_runtime(monkeypatch)
	env = load_onecore(monkeypatch)
	env.driver.terminate()
	return env, _record(monkeypatch, env.outer)


def _fail_onecore_initialize(env):
	def initialize(callback):
		raise Boom("ocSpeech_initialize failed")

	env.native.ocSpeech_initialize = env.native.ocSpeech_initialize.__class__(initialize)


def _fail_onecore_set_voice(env):
	# NVDA's constructor sets its default voice after it created the native token.
	def setVoice(token, index):
		raise Boom("ocSpeech_setVoice failed")

	env.native.ocSpeech_setVoice = env.native.ocSpeech_setVoice.__class__(setVoice)


def _record_token_release(env, record, built, error=None):
	"""Record each ocSpeech_terminate: the token value and the driver's callback state then."""
	released = []

	def terminate(token):
		record.calls.append("token")
		state = native_release_state(built[0])
		released.append((token.value, state.early_exit, state.detached))
		if error is not None:
			raise error

	env.native.ocSpeech_terminate = env.native.ocSpeech_terminate.__class__(terminate)
	return released


def _onecore_probe(env):
	"""A SynthDriver subclass that keeps the half-built driver its constructor raised from."""
	built = []

	class Probe(env.outer.SynthDriver):
		def __init__(self):
			built.append(self)
			super().__init__()

	return Probe, built


def test_onecore_a_failing_nvda_constructor_releases_the_host(onecore):
	env, record = onecore
	probe, built = _onecore_probe(env)
	_record_token_release(env, record, built)
	_fail_onecore_initialize(env)
	with pytest.raises(Boom, match="ocSpeech_initialize failed"):
		probe()
	_assert_host_released(record)
	assert record.calls == ["host"]


def test_onecore_a_failing_step_after_the_token_terminates_it_and_releases_the_host(onecore):
	env, record = onecore
	probe, built = _onecore_probe(env)
	released = _record_token_release(env, record, built)
	_fail_onecore_set_voice(env)
	with pytest.raises(Boom, match="ocSpeech_setVoice failed"):
		probe()
	# Callbacks are blocked before the token ends; then the token, then the host.
	assert released == [(123, True, True)]
	assert record.calls == ["token", "host"]
	_assert_host_released(record)
	assert env.outer._TERMINATED_CALLBACKS[-1] is env.native.callback
	state = native_release_state(built[0])
	assert state.token is None
	assert state.callback is None


def test_onecore_a_null_token_is_not_terminated(onecore):
	env, record = onecore
	probe, built = _onecore_probe(env)
	_record_token_release(env, record, built)
	env.native.ocSpeech_initialize = env.native.ocSpeech_initialize.__class__(lambda callback: 0)
	_fail_onecore_set_voice(env)
	with pytest.raises(Boom, match="ocSpeech_setVoice failed"):
		probe()
	assert record.calls == ["host"]
	_assert_host_released(record)


def test_onecore_a_failing_token_release_is_logged_and_the_original_error_raised(onecore):
	env, record = onecore
	probe, built = _onecore_probe(env)
	_record_token_release(env, record, built, error=RuntimeError("terminate failed"))
	_fail_onecore_set_voice(env)
	with pytest.raises(Boom, match="ocSpeech_setVoice failed"):
		probe()
	assert record.calls == ["token", "host"]
	_assert_host_released(record)
	_assert_one_cleanup_error_logged(record, "OneCore")


def test_onecore_a_failing_wrapper_step_before_the_parent_releases_the_host(onecore, monkeypatch):
	env, record = onecore

	def stopGate(condition):
		raise Boom("stop gate failed")

	monkeypatch.setattr(env.outer, "StopGate", stopGate)
	with pytest.raises(Boom, match="stop gate failed"):
		env.outer.SynthDriver()
	_assert_host_released(record)
	assert record.calls == ["host"]


def test_onecore_a_failing_host_release_is_logged_and_the_original_error_raised(onecore, monkeypatch):
	env, record = onecore
	host_class = env.outer.SegmentHost

	class FailingHost(host_class):
		def terminate(self):
			super().terminate()
			raise RuntimeError("host terminate failed")

	monkeypatch.setattr(env.outer, "SegmentHost", FailingHost)
	_fail_onecore_initialize(env)
	with pytest.raises(Boom, match="ocSpeech_initialize failed"):
		env.outer.SynthDriver()
	_assert_host_released(record)
	_assert_one_cleanup_error_logged(record, "OneCore")


def test_onecore_a_built_core_keeps_its_host(onecore):
	env, record = onecore
	driver = env.outer.SynthDriver()
	try:
		assert record.calls == []
		assert not record.hosts[0].terminated
	finally:
		driver.terminate()


# SAPI5 ----------------------------------------------------------------------


@pytest.fixture
def sapi5(monkeypatch):
	env = load_sapi5(monkeypatch)
	env.driver.terminate()
	record = _record(monkeypatch, env.outer)
	record.threads, record.players, record.sinks = [], [], []

	class RecordingThread(env.outer.Thread):
		def __init__(self, *args, **kwargs):
			super().__init__(*args, **kwargs)
			record.threads.append(self)

		def join(self, *args, **kwargs):
			record.calls.append("thread")
			return super().join(*args, **kwargs)

	class RecordingPlayer(SapiPlayer):
		def __init__(self, **kwargs):
			super().__init__(**kwargs)
			record.players.append(self)

		def close(self):
			record.calls.append("player")
			super().close()

	class RecordingSink(env.outer._SegmentSapiSink):
		def __init__(self, *args):
			super().__init__(*args)
			record.sinks.append(self)

		def detach(self):
			record.calls.append("sink")
			super().detach()

	monkeypatch.setattr(env.outer, "Thread", RecordingThread)
	monkeypatch.setattr(env.base.nvwave, "WavePlayer", RecordingPlayer)
	monkeypatch.setattr(env.outer, "_SegmentSapiSink", RecordingSink)
	return env, record


def _fail_sapi5_sink_install(monkeypatch, env):
	# NVDA's own SapiSink is accepted; the wrapper's sink, installed last, is refused.
	segmentSink = env.outer._SegmentSapiSink

	class Native(SapiNative):
		def SetNotifySink(self, sink):
			if isinstance(sink, segmentSink):
				raise Boom("notify sink refused")
			super().SetNotifySink(sink)

	monkeypatch.setattr(sys.modules["comtypes.client"], "CreateObject", lambda *args: Native())


def test_sapi5_a_failing_nvda_constructor_releases_the_host(sapi5, monkeypatch):
	env, record = sapi5

	def create(*args):
		raise Boom("no SAPI5 voice object")

	monkeypatch.setattr(sys.modules["comtypes.client"], "CreateObject", create)
	with pytest.raises(Boom, match="no SAPI5 voice object"):
		env.outer.SynthDriver()
	_assert_host_released(record)
	assert record.players == []
	assert record.calls == ["host"]


def test_sapi5_a_failing_audio_setup_closes_the_player_and_releases_the_host(sapi5, monkeypatch):
	env, record = sapi5

	def sonicInitialize():
		raise Boom("sonic failed")

	monkeypatch.setattr(env.base, "sonicInitialize", sonicInitialize)
	with pytest.raises(Boom, match="sonic failed"):
		env.outer.SynthDriver()
	_assert_host_released(record)
	assert record.threads == []
	assert [player.closed for player in record.players] == [True]
	assert record.calls == ["player", "host"]


def test_sapi5_a_failing_sink_install_releases_the_sink_worker_player_and_host(sapi5, monkeypatch):
	env, record = sapi5
	_fail_sapi5_sink_install(monkeypatch, env)
	with pytest.raises(Boom, match="notify sink refused"):
		env.outer.SynthDriver()
	_assert_host_released(record)
	(sink,) = record.sinks
	assert sink._eventSource is None
	(thread,) = record.threads
	assert not thread.is_alive()
	assert [player.closed for player in record.players] == [True]
	assert record.calls == ["sink", "thread", "player", "host"]
	assert record.logged == []


def test_sapi5_a_failing_cleanup_step_is_logged_and_the_host_still_released(sapi5, monkeypatch):
	env, record = sapi5

	class FailingPlayer(env.base.nvwave.WavePlayer):
		def close(self):
			super().close()
			raise RuntimeError("close failed")

	monkeypatch.setattr(env.base.nvwave, "WavePlayer", FailingPlayer)
	_fail_sapi5_sink_install(monkeypatch, env)
	with pytest.raises(Boom, match="notify sink refused"):
		env.outer.SynthDriver()
	_assert_host_released(record)
	(thread,) = record.threads
	assert not thread.is_alive()
	assert record.calls == ["sink", "thread", "player", "host"]
	_assert_one_cleanup_error_logged(record, "SAPI5")


def test_sapi5_a_built_core_keeps_its_resources(sapi5):
	env, record = sapi5
	driver = env.outer.SynthDriver()
	try:
		assert record.calls == []
		(thread,) = record.threads
		assert thread.is_alive()
		assert [player.closed for player in record.players] == [False]
		assert not record.hosts[0].terminated
	finally:
		driver.terminate()
