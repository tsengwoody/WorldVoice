"""Engine adapters for the shared segment contract tests.

Each adapter loads one real outer engine wrapper with that engine's existing
fakes. After ``open`` the fakes hold every segment before its final playback
barrier; only ``complete`` lets the current segment finish. Runtime access
stays here so later phases only need to update the adapters.
"""

import sys
from threading import Event

from espeak_drain_harness import finish as finish_espeak, load_espeak
from onecore_drain_harness import in_thread, load_onecore
from rhvoice_drain_harness import finish as finish_rhvoice, load_rhvoice
from sapi5_drain_harness import load_sapi5
from waiting import HOLD_TIMEOUT, WAIT_TIMEOUT
from worldvoice_cancel_wrapper_harness import Token, emit, load_real_driver_with_native_stubs


def _fresh_lifecycle_module(monkeypatch):
	# Each loader reloads runtime models; reload the coordinator too so its
	# event enum belongs to that same runtime copy.
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime._segmentLifecycle", raising=False)
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)


class _Adapter:
	engine = ""

	def bind(self, env, core):
		self.env = env
		self.core = core
		self.EventKind = env.rt.models.EventKind
		self.PlaybackContext = env.rt.models.PlaybackContext

	def new_token(self):
		return self.env.scheduler.CancellationToken()

	def speak(self, commands, token, context, sink):
		self.core.speak_segment(commands, token, context=context, on_event=sink)

	def terminate(self):
		self.core.terminate()

	def on_delivery_thread(self):
		return self.core._segmentHost.on_delivery_thread()

	def speak_ordinary(self, commands):
		self.core.speak(commands)

	def complete_ordinary(self):
		"""Let ordinary speech queued by speak_ordinary finish."""
		self.complete()

	def _player(self):
		return self.env.player

	def fail_next_stop(self):
		"""Make the engine's real player fail its next stop() once."""
		player = self._player()
		original = player.stop
		failures = [OSError("player stop failed")]

		def stop(*args, **kwargs):
			if failures:
				raise failures.pop()
			return original(*args, **kwargs)

		player.stop = stop


class EspeakAdapter(_Adapter):
	engine = "Espeak"

	def open(self, monkeypatch, tmp_path):
		_fresh_lifecycle_module(monkeypatch)
		env = load_espeak(monkeypatch, tmp_path)
		self.bind(env, env.driver)

	def complete(self):
		self.env.native.wait_calls(1)
		self.env.player.idle_release.set()
		self.env.native.release()

	def native_call_count(self):
		return len(self.env.native.calls)

	def close(self):
		finish_espeak(self.env)


class RHVoiceAdapter(_Adapter):
	engine = "RHVoice"

	def open(self, monkeypatch, tmp_path):
		_fresh_lifecycle_module(monkeypatch)
		env = load_rhvoice(monkeypatch, tmp_path)
		self.bind(env, env.driver)

	def complete(self):
		self.env.native.wait_call()
		self.env.native.release()

	def native_call_count(self):
		return len(self.env.native.calls)

	def _player(self):
		return self.core._SynthDriver__player

	def close(self):
		finish_rhvoice(self.env)


class SAPI5Adapter(_Adapter):
	engine = "SAPI5"

	def open(self, monkeypatch, tmp_path):
		_fresh_lifecycle_module(monkeypatch)
		env = load_sapi5(monkeypatch)
		self.bind(env, env.driver)

	def complete(self):
		self.env.native.wait_calls(1)
		self.env.native.end(self.env.native.calls[-1][0])
		self.env.player.idle_release.set()

	def native_call_count(self):
		return len(self.env.native.calls)

	def close(self):
		for player in self.env.players:
			player.feed_release.set()
			player.idle_release.set()
			player.stop_error = None
		for native in self.env.natives:
			native.purge_error = None
		self.core.terminate()


class OneCoreAdapter(_Adapter):
	engine = "OneCore"

	def open(self, monkeypatch, tmp_path):
		_fresh_lifecycle_module(monkeypatch)
		env = load_onecore(monkeypatch)
		self.bind(env, env.driver)

	def complete(self):
		self.env.native.wait_calls(1)
		response = in_thread(lambda: self.env.native.respond(frames=8, markers=""))
		assert response.done.wait(WAIT_TIMEOUT), "OneCore callback did not return"
		assert response.errors == []
		self.env.player.sync_release.set()

	def native_call_count(self):
		return len(self.env.native.calls)

	def complete_ordinary(self):
		# Legacy OneCore speech syncs and idles the player inside its callback.
		self.env.player.sync_release.set()
		self.complete()

	def close(self):
		self.env.player.feed_release.set()
		self.env.player.sync_release.set()
		self.core.terminate()


class _NuanceAdapter(_Adapter):
	def open(self, monkeypatch, tmp_path):
		_fresh_lifecycle_module(monkeypatch)
		env = load_real_driver_with_native_stubs(monkeypatch, self.engine)
		core = env.new_core()
		env.core = core
		core._veCallbackHandler._ensureSonicStream = lambda: False
		monkeypatch.setattr(env.original_driver.synthIndexReached, "notify", lambda **kwargs: None)
		monkeypatch.setattr(env.original_driver.synthDoneSpeaking, "notify", lambda **kwargs: None)
		# The fake SDK has no native resources to release on terminate.
		monkeypatch.setattr(env.native, "close", lambda instance: None)
		monkeypatch.setattr(env.native, "terminate", lambda: None)
		self.idle_release = Event()
		core._real_player.idle = lambda: self.idle_release.wait(HOLD_TIMEOUT)
		core._real_player.stop = self.idle_release.set
		self.calls = []

		def native(instance, text):
			self.calls.append(text)
			emit(env, instance)

		monkeypatch.setattr(env.native, "processText2Speech", native)
		self.bind(env, core)

	def new_token(self):
		return Token()

	def complete(self):
		self.idle_release.set()

	def native_call_count(self):
		return len(self.calls)

	def _player(self):
		return self.core._real_player

	def close(self):
		self.idle_release.set()
		self.core.terminate()


class VEAdapter(_NuanceAdapter):
	engine = "VE"


class CerenceAdapter(_NuanceAdapter):
	engine = "Cerence"
