"""A VE or Cerence constructor that raises releases what it built and re-raises the original error.

VoiceClassAdapter.open gets no core to terminate when SynthDriver() raises, so the constructor itself
stops the segment delivery thread and the BgThread, closes the player and terminates the native
library, newest first. A failing cleanup step is logged and the rest still run.
"""

import pytest
from worldvoice_cancel_wrapper_harness import FakePlayer, load_real_driver_with_native_stubs


class Boom(Exception):
	pass


@pytest.fixture(params=["VE", "Cerence"])
def built(request, monkeypatch):
	harness = load_real_driver_with_native_stubs(monkeypatch, request.param)
	record = type("Record", (), {})()
	record.hosts, record.threads, record.players, record.calls, record.logged = [], [], [], [], []

	class RecordingHost(harness.module.SegmentHost):
		def __init__(self, *args, **kwargs):
			super().__init__(*args, **kwargs)
			record.hosts.append(self)

		def terminate(self):
			record.calls.append("host")
			return super().terminate()

	class RecordingThread(harness.original_driver.BgThread):
		def __init__(self, queue):
			super().__init__(queue)
			record.threads.append(self)

		def join(self, *args, **kwargs):
			record.calls.append("thread")
			return super().join(*args, **kwargs)

	class RecordingPlayer(FakePlayer):
		def __init__(self, **kwargs):
			super().__init__(**kwargs)
			self.options = kwargs
			record.players.append(self)

		def close(self):
			record.calls.append("player")
			super().close()

	monkeypatch.setattr(harness.module, "SegmentHost", RecordingHost)
	monkeypatch.setattr(harness.original_driver, "BgThread", RecordingThread)
	monkeypatch.setattr(harness.original_driver.nvwave, "WavePlayer", RecordingPlayer)
	monkeypatch.setattr(harness.native, "terminate", lambda: record.calls.append("native"))
	monkeypatch.setattr(
		harness.module.log,
		"error",
		lambda *args, **kwargs: record.logged.append((args, kwargs)),
	)
	return harness, record


def _assert_released(record, *, native, player):
	(host,) = record.hosts
	assert host.terminated
	assert not host._lifecycle._delivery_thread.is_alive()
	if native:
		(thread,) = record.threads
		assert not thread.is_alive()
	else:
		assert record.threads == []
	assert [player.closes for player in record.players] == ([1] if player else [])
	expected = (["player"] if player else []) + (["thread", "native"] if native else []) + ["host"]
	assert record.calls == expected


def test_a_failing_player_releases_the_thread_native_and_host(built, monkeypatch):
	harness, record = built

	def fail(**kwargs):
		raise Boom("no audio device")

	monkeypatch.setattr(harness.original_driver.nvwave, "WavePlayer", fail)
	with pytest.raises(Boom, match="no audio device"):
		harness.new_core()
	_assert_released(record, native=True, player=False)


def test_failing_resources_release_the_player_thread_native_and_host(built, monkeypatch):
	harness, record = built

	def fail():
		raise Boom("language list failed")

	monkeypatch.setattr(harness.original_driver, "getAvailableResources", fail)
	with pytest.raises(Boom, match="language list failed"):
		harness.new_core()
	_assert_released(record, native=True, player=True)


def test_no_voices_is_a_clear_error_and_releases_everything(built, monkeypatch):
	harness, record = built
	monkeypatch.setattr(harness.native, "getVoiceList", lambda language: [])
	with pytest.raises(RuntimeError, match="no voices available"):
		harness.new_core()
	_assert_released(record, native=True, player=True)


def test_a_failing_native_initialize_releases_the_host(built, monkeypatch):
	harness, record = built

	def fail(resources):
		raise Boom("native library missing")

	monkeypatch.setattr(harness.native, "initialize", fail)
	with pytest.raises(Boom, match="native library missing"):
		harness.new_core()
	_assert_released(record, native=False, player=False)


def test_no_resources_releases_the_host(built, monkeypatch):
	harness, record = built
	monkeypatch.setattr(harness.original_driver, "getResourcePaths", list)
	with pytest.raises(RuntimeError, match="no resources available"):
		harness.new_core()
	_assert_released(record, native=False, player=False)


def test_a_failing_cleanup_step_is_logged_and_the_rest_still_run(built, monkeypatch):
	harness, record = built

	def fail_terminate():
		record.calls.append("native")
		raise RuntimeError("terminate failed")

	monkeypatch.setattr(harness.native, "terminate", fail_terminate)
	monkeypatch.setattr(harness.native, "getVoiceList", lambda language: [])
	with pytest.raises(RuntimeError, match="no voices available"):
		harness.new_core()
	_assert_released(record, native=True, player=True)
	((args, kwargs),) = record.logged
	assert (args, kwargs) == (
		(f"WorldVoice {harness.engine} initialization cleanup failed",),
		{"exc_info": True},
	)


def test_a_built_core_keeps_its_resources(built):
	harness, record = built
	core = harness.new_core()
	try:
		assert record.calls == []
		(thread,) = record.threads
		assert thread.is_alive()
		assert [player.closes for player in record.players] == [0]
	finally:
		core.terminate()


def test_nvda_2024_config_opens_the_player_on_the_speech_output_device(built, monkeypatch):
	# NVDA 2024.x keeps outputDevice in [speech]; config schema 14 (NVDA 2025.1) moved it to [audio].
	harness, record = built
	conf = {"audio": {}, "speech": {"outputDevice": "Speakers (2024)"}}
	monkeypatch.setattr(harness.original_driver.config, "conf", conf)
	core = harness.new_core()
	try:
		(player,) = record.players
		assert player.options["outputDevice"] == "Speakers (2024)"
	finally:
		core.terminate()
