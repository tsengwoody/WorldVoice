import importlib.util
import sys
import threading
import types
from pathlib import Path

import pytest


WORLDVOICE = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"


class EventStub:
	def __init__(self, callback=None):
		self.handlers = []
		self.callback = callback

	def register(self, handler):
		self.handlers.append(handler)

	def unregister(self, handler):
		self.handlers.remove(handler)

	def notify(self, **kwargs):
		if self.callback:
			self.callback(**kwargs)
		for handler in tuple(self.handlers):
			handler(**kwargs)


@pytest.fixture
def modules(monkeypatch):
	package_name = "worldvoice_request_builder_under_test"
	package = types.ModuleType(package_name)
	package.__path__ = [str(WORLDVOICE)]
	monkeypatch.setitem(sys.modules, package_name, package)
	monkeypatch.setitem(sys.modules, "config", types.SimpleNamespace(conf={}))
	monkeypatch.setitem(sys.modules, "languageHandler", types.SimpleNamespace(getLanguageDescription=lambda language: language))
	log = types.SimpleNamespace(debug=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None)
	monkeypatch.setitem(sys.modules, "logHandler", types.SimpleNamespace(log=log))
	owner = object()
	done_seen = threading.Event()
	done_calls = []

	def record_done(synth):
		if synth is owner:
			done_calls.append(synth)
			done_seen.set()

	done = EventStub(record_done)
	index = EventStub()
	monkeypatch.setitem(sys.modules, "synthDriverHandler", types.SimpleNamespace(
		getSynth=lambda: owner,
		synthDoneSpeaking=done,
		synthIndexReached=index,
		VoiceInfo=object,
	))

	class BreakCommand:
		def __init__(self, time):
			self.time = time

	monkeypatch.setitem(sys.modules, "speech", types.ModuleType("speech"))
	monkeypatch.setitem(sys.modules, "speech.commands", types.SimpleNamespace(BreakCommand=BreakCommand))

	def load(name, path):
		spec = importlib.util.spec_from_file_location(f"{package_name}.{name}", path)
		module = importlib.util.module_from_spec(spec)
		monkeypatch.setitem(sys.modules, spec.name, module)
		spec.loader.exec_module(module)
		return module

	driver = load("driver", WORLDVOICE / "driver/__init__.py")
	manager_module = load("taskManager", WORLDVOICE / "taskManager.py")
	builder = load("requestBuilder", WORLDVOICE / "requestBuilder.py") if (WORLDVOICE / "requestBuilder.py").exists() else None
	return types.SimpleNamespace(
		driver=driver, manager_module=manager_module, builder=builder,
		BreakCommand=BreakCommand, done=done, done_seen=done_seen,
		done_calls=done_calls, owner=owner,
	)


@pytest.fixture
def manager(modules):
	instance = modules.manager_module.TaskManager(owner=modules.owner)
	yield instance
	instance.shutdown()


def fake_voice_class(modules):
	class FakeVoice(modules.driver.Voice):
		def __init__(self, name, engine, manager):
			self.name = name
			self.engine = engine
			self.taskManager = manager
			self.spoken = []
			self.core = types.SimpleNamespace(cancel=lambda: None)

		def speak(self, chunks, request):
			self.spoken.append(list(chunks))
			self.taskManager.append_speech(request, self, lambda: None)

		def breaks(self, seconds, request):
			self.taskManager.append_break(request, self, seconds)

	return FakeVoice


def test_builder_submits_complete_multivoice_request_once(modules, manager):
	FakeVoice = fake_voice_class(modules)
	zh = FakeVoice("zh", "VE", manager)
	en = FakeVoice("en", "Neural", manager)
	submitted = []
	original_submit = manager.submit_request

	def submit(request):
		submitted.append((request, [(task.kind, task.voiceInstance) for task in request.tasks]))
		return original_submit(request)

	manager.submit_request = submit
	assert modules.builder.queue_speech_sequence(
		manager, ["中", en, "English", modules.BreakCommand(200)], zh, {"VE", "Neural"},
	)
	assert len(submitted) == 1
	assert submitted[0][1] == [("speech", zh), ("speech", en), ("break", en)]
	assert zh.spoken == [["中"]]
	assert en.spoken == [["English"]]


@pytest.mark.parametrize("supports_token", [True, False, None])
def test_voice_passes_token_only_to_opted_in_core(modules, manager, supports_token):
	voice = object.__new__(modules.driver.Voice)
	voice.taskManager = manager
	calls = []
	core = types.SimpleNamespace(speak=lambda text, **kwargs: calls.append((text, kwargs)), cancel=lambda: None)
	if supports_token is not None:
		core.supportsCancellationToken = supports_token
	voice.core = core
	voice.active = lambda: None
	request = manager.new_request()
	voice.speak(["hello"], request)
	assert len(request.tasks) == 1
	request.tasks[-1].run()
	assert calls == [(["hello"], {"cancellationToken": request.token} if supports_token else {})]


def test_break_only_request_sends_no_external_done(modules, manager):
	FakeVoice = fake_voice_class(modules)
	voice = FakeVoice("zh", "VE", manager)
	assert modules.builder.queue_speech_sequence(manager, [modules.BreakCommand(0)], voice, {"VE"})
	manager._q.join()
	assert modules.done_calls == []


def test_cancel_during_build_rejects_complete_request(modules, manager):
	FakeVoice = fake_voice_class(modules)
	voice = FakeVoice("zh", "VE", manager)
	original_speak = voice.speak

	def cancel_on_first_chunk(chunks, request):
		original_speak(chunks, request)
		manager.cancel([voice])

	voice.speak = cancel_on_first_chunk
	assert modules.builder.queue_speech_sequence(
		manager, ["first", modules.BreakCommand(100), "second"], voice, {"VE"},
	) is False
	assert manager._q.empty()
	assert not modules.done_calls


def test_voice_cancelled_before_run_does_not_call_core(modules, manager):
	voice = object.__new__(modules.driver.Voice)
	voice.taskManager = manager
	calls = []
	voice.core = types.SimpleNamespace(speak=lambda text: calls.append(text), cancel=lambda: None)
	voice.active = lambda: calls.append("active")
	request = manager.new_request()
	voice.speak(["hello"], request)
	request.token.cancel()
	request.tasks[-1].run()
	assert calls == []


def test_voice_manager_cancel_passes_default_and_cache_without_stopping(modules, monkeypatch):
	engine = types.ModuleType(f"{modules.driver.__package__}.engine")
	engine.EngineType = object
	engine.READY_ENGINE_CLASS = {}
	engine.get_engine_enabled = lambda *args: False
	engine.refresh_ready_engine_classes = lambda *args: None
	monkeypatch.setitem(sys.modules, engine.__name__, engine)
	name = f"{modules.driver.__package__}.voiceManager"
	spec = importlib.util.spec_from_file_location(name, WORLDVOICE / "voiceManager.py")
	voice_manager_module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, name, voice_manager_module)
	spec.loader.exec_module(voice_manager_module)
	stopped = []
	default = types.SimpleNamespace(stop=lambda: stopped.append("default"))
	cached = types.SimpleNamespace(stop=lambda: stopped.append("cached"))
	passed = []
	manager = types.SimpleNamespace(cancel=lambda voices: passed.append(list(voices)))
	instance = object.__new__(voice_manager_module.VoiceManager)
	instance._defaultVoiceInstance = default
	instance._instanceCache = {"default": default, "cached": cached}
	instance.taskManager = manager
	instance.cancel()
	assert passed == [[default, cached]]
	assert stopped == []
