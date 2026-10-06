import importlib
import sys
import threading
import types
from pathlib import Path

import pytest
from addon_loader import alias_package
from runtime_harness import MemoryRepository, worker_queue_empty
from waiting import HOLD_TIMEOUT, WAIT_TIMEOUT
from worldvoice_harness import EventStub

WORLDVOICE = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"


@pytest.fixture
def modules(monkeypatch, nvda_commands):
	package_name = "worldvoice_request_builder_under_test"
	for name in tuple(sys.modules):
		if name.startswith(package_name + "."):
			monkeypatch.delitem(sys.modules, name)
	alias_package(monkeypatch, package_name, WORLDVOICE)
	monkeypatch.setitem(
		sys.modules,
		"languageHandler",
		types.SimpleNamespace(getLanguageDescription=lambda language: language),
	)

	def load(name):
		return importlib.import_module(package_name + "." + name)

	return types.SimpleNamespace(
		driver=load("driver"),
		manager_module=load("runtime.scheduler"),
		builder=load("runtime.requestBuilder"),
		models=load("runtime.models"),
		settings=load("runtime.settings"),
		session=load("runtime.session"),
		adapter=load("compat.engineAdapter"),
		facade=load("compat.voiceFacade"),
		commands=load("compat.commands"),
		bridge=load("nvdaEventBridge"),
		BreakCommand=nvda_commands.BreakCommand,
	)


@pytest.fixture
def assembly(modules):
	owner = object()
	done_seen = threading.Event()
	done_calls, indexes = [], []

	def record_done(synth):
		if synth is owner:
			done_calls.append(synth)
			done_seen.set()

	done = EventStub(record_done)
	index = EventStub(lambda synth, index: indexes.append(index) if synth is owner else None)
	bridge = modules.bridge.NvdaEventBridge(
		owner,
		done_event=done,
		index_event=index,
		get_synth=lambda: owner,
	)
	manager = modules.manager_module.TaskManager(bridge)
	bridge.start(manager.on_event)
	store = modules.settings.VoiceSettingsStore(MemoryRepository())
	ports, voices = {}, {}

	def voice(key, *, supports_token=None, on_speak=None):
		engine, voice_id = key.split(":")

		class Core:
			supportedSettings = ()

			def __init__(self):
				self.spoken = []
				self.cancelled = 0
				if supports_token is not None:
					self.supportsCancellationToken = supports_token

			def speak(self, commands, **kwargs):
				self.spoken.append((commands, kwargs))
				if on_speak:
					on_speak(self, commands, kwargs)
				else:
					done.notify(synth=self)

			def cancel(self):
				self.cancelled += 1

			def terminate(self):
				pass

		class Voice(modules.driver.Voice):
			synth_driver_class = Core

		Voice.engine = engine
		spec = modules.models.VoiceSpec(voice_id, key, key, "en", engine, "en")
		adapter = modules.adapter.LegacyEngineAdapter(Voice, voices.__getitem__)
		session = modules.session.EngineSession(adapter, store)
		session.open()
		instance = Voice(spec, modules.facade.LegacyVoiceBinding(store, session, adapter.core))
		voices[key] = instance
		ports[key] = session
		bridge.bind(adapter.notification_source, session.source_id)
		return instance

	def queue(sequence, default):
		return modules.builder.queue_speech_sequence(
			manager,
			modules.commands.normalize_legacy_commands(sequence),
			default.name,
			ports.get,
		)

	yield types.SimpleNamespace(
		manager=manager,
		store=store,
		voice=voice,
		queue=queue,
		ports=ports,
		done=done,
		index=index,
		done_calls=done_calls,
		indexes=indexes,
		done_seen=done_seen,
		owner=owner,
	)
	manager.shutdown()
	bridge.close()
	for session in ports.values():
		session.close()


def test_builder_submits_complete_multivoice_request_once(modules, assembly):
	a = assembly
	zh, en = a.voice("VE:zh"), a.voice("Neural:en")
	submitted = []
	original = a.manager.submit_request

	def submit(request):
		submitted.append(request)
		return original(request)

	a.manager.submit_request = submit
	assert a.queue(["中", modules.models.SelectVoice(en.name), "English", modules.BreakCommand(0)], zh)
	assert a.done_seen.wait(WAIT_TIMEOUT)
	assert len(submitted) == 1
	assert [(task.voice_key, task.commands, task.seconds) for task in submitted[0].tasks] == [
		("VE:zh", ("中",), None),
		("Neural:en", ("English",), None),
		(None, (), 0),
	]
	assert zh.core.spoken[0][0] == ("中",)
	assert en.core.spoken[0][0] == ("English",)


@pytest.mark.parametrize(
	"engines,texts,indexes",
	[
		(("VE", "Neural", "VE"), ("中", "English", "再見"), (11, 22, 33)),
	],
)
def test_ordered_engines_forward_only_live_events_and_finish_after_trailing_break(
	modules,
	assembly,
	engines,
	texts,
	indexes,
):
	a = assembly
	calls, raw_events, requests = [], [], []
	entered, release = threading.Event(), threading.Event()
	original = a.manager.submit_request

	def submit(request):
		requests.append(request)
		request.token.wait = lambda seconds: (entered.set(), release.wait(HOLD_TIMEOUT))
		return original(request)

	a.manager.submit_request = submit
	voices = []
	for number, (engine, index) in enumerate(zip(engines, indexes)):

		def speak(core, chunks, kwargs, index=index):
			calls.append((core, chunks, kwargs))
			raw_events.append(("index", index))
			a.index.notify(synth=core, index=index)
			raw_events.append(("done",))
			a.done.notify(synth=core)

		voices.append(
			a.voice(
				f"{engine}:{number}",
				supports_token=engine in ("VE", "Cerence"),
				on_speak=speak,
			),
		)
	sequence = []
	for voice, text in zip(voices, texts):
		sequence.extend((modules.models.SelectVoice(voice.name), text))
	sequence.append(modules.BreakCommand(200))
	try:
		assert a.queue(sequence, voices[0])
		assert entered.wait(WAIT_TIMEOUT)
		assert [call[1] for call in calls] == [(text,) for text in texts]
		assert [event[0] for event in raw_events] == ["index", "done"] * len(voices)
		assert a.indexes == list(indexes)
		assert a.done_calls == []
		assert len(requests) == 1
		assert [task.seconds for task in requests[0].tasks] == [None] * len(voices) + [0.2]
		for core, _, kwargs in calls:
			assert kwargs == (
				{"cancellationToken": requests[0].token} if core.supportsCancellationToken else {}
			)
	finally:
		release.set()
	assert a.done_seen.wait(WAIT_TIMEOUT)
	assert a.done_calls == [a.owner]


def test_break_only_request_sends_no_external_done(modules, assembly):
	voice = assembly.voice("VE:zh")
	assert assembly.queue([modules.BreakCommand(0)], voice)
	assembly.manager._q.join()
	assert assembly.done_calls == []


def test_cancel_during_build_rejects_complete_request(modules, assembly):
	a = assembly
	voice = a.voice("VE:zh")
	original = a.manager.append_speech

	def append(*args):
		result = original(*args)
		a.manager.cancel(a.ports.values())
		return result

	a.manager.append_speech = append
	assert a.queue(["first", modules.BreakCommand(100), "second"], voice) is False
	assert worker_queue_empty(a.manager)
	assert not a.done_calls
	assert voice.core.spoken == []
