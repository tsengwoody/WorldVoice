"""Choosing another voice while a segment is in flight must not silence the request.

In segment (drain) mode a direct engine cancel that bypasses the scheduler silences the
in-flight segment without failing it, so the request used to wait for a drain that never
came until NVDA's next cancel. SynthDriver._set_voice runs without a preceding NVDA cancel
when a configuration profile switch changes the voice, so it must leave the current
request alone: the segments already queued keep their voice and finish.
"""

import sys
from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, load_definitions, load_source
from espeak_drain_harness import finish, load_espeak
from runtime_drain_integration_harness import ENGINES, assemble
from runtime_harness import MemoryRepository
from waiting import WAIT_TIMEOUT, eventually


def _words(text):
	"""The test words a native call received, whatever markup the wrapper added."""
	return [word for word in ("first", "second") if word in str(text)]


def _synth_driver(manager):
	"""The real SynthDriver._set_voice over manager, without NVDA's base class."""
	namespace = load_definitions(WORLDVOICE / "__init__.py", ["SynthDriver"], {}, members={"_set_voice"})
	synth = namespace["SynthDriver"]()
	synth._voiceManager = manager
	synth._voice = None
	return synth


# keepMainLocaleVoiceConsistent is on by default: the voice setter then also reassigns the
# main locale's role, which must not touch the engine either.
@pytest.mark.parametrize("follow_main_locale", [True, False])
@pytest.mark.parametrize("when", ["during_native", "during_playback"])
@pytest.mark.parametrize("engine", ENGINES)
def test_choosing_another_voice_mid_segment_lets_the_request_finish(
	monkeypatch,
	tmp_path,
	engine,
	when,
	follow_main_locale,
):
	c = assemble(monkeypatch, tmp_path)
	try:
		control = c.controls[engine]
		switching = sys.modules["config"].conf["WorldVoice"]["autoLanguageSwitching"]
		switching["keepMainLocaleVoiceConsistent"] = follow_main_locale
		c.manager.default_voice_name = c.key(engine)
		other = next(spec for spec in c.manager.table if spec.engine != engine)
		synth = _synth_driver(c.manager)
		IndexCommand = c.commands.IndexCommand
		request = c.submit(
			("first", IndexCommand(701), c.rt.models.Pause(0.001), "second", IndexCommand(702)),
			engine,
		)
		if when == "during_native":
			control.wait_call(1)
			synth._set_voice(other.name)
			barrier = control.tail(1)
		else:
			# Native synthesis is done and the audio fed; the player is still playing it.
			barrier = control.tail(1)
			synth._set_voice(other.name)
		assert c.manager.default_voice_name == other.name
		main_locale = c.manager.voice_consistency.main_locale(c.manager.default_voice_instance)
		assert (c.manager.roles.voice_for(main_locale) == other.name) is follow_main_locale
		assert c.output.dones == []
		barrier.release.set()
		# The second segment keeps the voice it was queued with.
		control.tail(2).release.set()
		c.wait_done()
		assert [task.future.result(timeout=WAIT_TIMEOUT) for task in request.tasks] == [True, None, True]
		assert request.state is c.scheduler.RequestState.COMPLETED
		assert [_words(call.text) for call in control.calls] == [["first"], ["second"]]
		assert c.controls[other.engine].calls == []
		assert c.output.indexes == [701, 702]
		assert len(c.output.dones) == 1
		assert [kind for kind, _ in c.output.timeline] == ["index", "drain", "index", "drain", "done"]
	finally:
		c.close()


class _Output:
	def __init__(self):
		self.indexes, self.dones = [], 0

	def index_reached(self, index):
		self.indexes.append(index)

	def done_speaking(self):
		self.dones += 1


class _EspeakAdapter:
	"""Forward segment speech and cancel to the real eSpeak wrapper, as VoiceClassAdapter does."""

	def __init__(self, env, tasks, completion):
		self.env, self.tasks = env, tasks
		self.capabilities = SimpleNamespace(completion=completion)
		self.cancels = 0

	def open(self):
		pass

	def close(self):
		pass

	def variants(self, key):
		return ()

	def apply(self, spec, snapshot):
		pass

	def speak(self, commands, token, *, context=None):
		def sink(event):
			self.tasks.on_events(lambda: (event,))

		self.env.driver.speak_segment(commands, token, context=context, on_event=sink)

	def finish_segment(self, context):
		pass

	def cancel(self):
		self.cancels += 1
		self.env.driver.cancel()

	def pause(self, switch):
		pass


class _Voices:
	"""VoiceManager's default voice semantics: an unknown name raises before anything changes."""

	def __init__(self, voices, default):
		self._voices = voices
		self.default_voice_instance = voices[default]

	@property
	def default_voice_name(self):
		return self.default_voice_instance.name

	@default_voice_name.setter
	def default_voice_name(self, name):
		if name not in self._voices:
			raise LookupError(name)
		self.default_voice_instance = self._voices[name]


@pytest.fixture
def espeak(monkeypatch, tmp_path):
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime._segmentLifecycle", raising=False)
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)
	env = load_espeak(monkeypatch, tmp_path)
	yield env
	finish(env)


@pytest.mark.parametrize("when", ["during_native", "during_playback"])
def test_choosing_another_voice_mid_espeak_segment_lets_the_request_finish(monkeypatch, espeak, when):
	env = espeak
	rt = env.rt
	M = rt.models
	facade = load_source(
		monkeypatch,
		"synthDrivers.WorldVoice.bridge.voiceFacade",
		WORLDVOICE / "bridge/voiceFacade.py",
	)
	output = _Output()
	tasks = env.scheduler.TaskManager(output)
	adapter = _EspeakAdapter(env, tasks, M.CompletionContract(M.CompletionMode.DRAIN, M.IndexRange(1, 9999)))
	store = rt.voice_settings.VoiceSettingsStore(MemoryRepository())
	session = rt.session.EngineSession(adapter, store)
	session.open()
	binding = facade.VoiceBinding(store, session, env.driver)
	voices = {
		name: facade.VoiceFacade(M.VoiceSpec(voice_id, name, name, "en", "eSpeak", "en"), binding)
		for voice_id, name in (("en", "eSpeak:en"), ("max", "eSpeak:max"))
	}
	synth = _synth_driver(_Voices(voices, "eSpeak:en"))
	env.native.next_scripts = [{}, {"auto_return": True}]
	request = tasks.new_request()
	tasks.append_speech(request, session, "eSpeak:en", ("first",))
	tasks.append_break(request, 0.001)
	tasks.append_speech(request, session, "eSpeak:en", ("second",))
	try:
		assert tasks.submit_request(request)
		first = env.native.wait_calls(1)
		if when == "during_native":
			synth._set_voice("eSpeak:max")
			env.player.idle_release.set()
			first.return_release.set()
		else:
			# All audio is fed; the player is still playing it.
			assert env.player.idle_entered.wait(WAIT_TIMEOUT)
			synth._set_voice("eSpeak:max")
			first.return_release.set()
			env.player.idle_release.set()
		assert synth._voiceManager.default_voice_name == "eSpeak:max"
		assert [task.future.result(timeout=WAIT_TIMEOUT) for task in request.tasks] == [True, None, True]
		eventually(lambda: output.dones == 1)
		assert request.state is env.scheduler.RequestState.COMPLETED
		assert [_words(call.text) for call in env.native.calls] == [["first"], ["second"]]
		assert adapter.cancels == 0
	finally:
		tasks.shutdown([session])
