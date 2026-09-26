"""Production manager, facade, adapter, session and bridge composition."""

import ast
import importlib
import sys
import threading
from types import SimpleNamespace

import pytest

from runtime_harness import MemoryRepository
from test_worldvoice_lifecycle import _load_voice_manager, _load_synth_class, WORLDVOICE
from test_worldvoice_request_builder import EventStub


@pytest.fixture
def composition(monkeypatch):
    manager_module = _load_voice_manager(monkeypatch, {})
    package = manager_module.__package__
    monkeypatch.setattr(manager_module, "VoiceInfo", lambda key, description, language:
                        SimpleNamespace(id=key, description=description, language=language))
    monkeypatch.setattr(sys.modules["languageHandler"], "getLanguageDescription", lambda value: value, raising=False)
    monkeypatch.setattr(sys.modules["synthDriverHandler"], "getSynth", lambda: None, raising=False)
    driver = importlib.import_module(package + ".driver")
    settings = importlib.import_module(package + ".runtime.settings")
    scheduler = importlib.import_module(package + ".runtime.scheduler")
    bridge_module = importlib.import_module(package + ".nvdaEventBridge")
    repo = MemoryRepository()
    store = settings.VoiceSettingsStore(repo)
    done, index = EventStub(), EventStub()
    owner = object()
    bridge = bridge_module.NvdaEventBridge(owner, done_event=done, index_event=index, get_synth=lambda: owner)
    tasks = scheduler.TaskManager(bridge)
    bridge.start(tasks.on_event)
    cores = []

    class Core:
        def __init__(self):
            self.closes = 0
            self.cancels = 0
            self.availableVoices = {key: SimpleNamespace(id=key, language=language, displayName=key)
                                    for key, language in (("a", "en"), ("b", "zh"))}
            cores.append(self)

        def terminate(self):
            self.closes += 1

        def cancel(self):
            self.cancels += 1

    def engine(name, *, shared=None, fail=False, empty=False):
        class Voice(driver.Voice):
            core = None
            session = None
            synth_driver_class = Core

            @classmethod
            def engineOn(cls):
                cls.core = shared or Core()
                if fail:
                    raise RuntimeError("partial open")

            @classmethod
            def supportedSettings(cls):
                return ["rate", "pitch", "volume"]

            @classmethod
            def voices(cls):
                return [] if empty else super().voices()

            def applyEngineSettings(self, core, snapshot):
                core.language = snapshot.language

        Voice.engine = name
        manager_module.EngineType.append(SimpleNamespace(name=name))
        manager_module.READY_ENGINE_CLASS[name] = Voice
        return Voice

    managers = []

    def create():
        manager = manager_module.VoiceManager(tasks, store, bridge)
        managers.append(manager)
        return manager

    yield SimpleNamespace(engine=engine, create=create, store=store, repo=repo,
                          bridge=bridge, tasks=tasks, cores=cores, Core=Core,
                          module=manager_module, driver=driver)
    tasks.shutdown()
    bridge.close()
    for manager in managers:
        manager.terminate(commit=False)


def test_only_started_sessions_are_resolvable(composition):
    c = composition
    c.engine("failed", fail=True)
    c.engine("ok")
    manager = c.create()
    assert manager.resolve_playback("failed:a") is None
    assert manager.resolve_playback("ok:a") is not None
    assert c.cores[0].closes == 1
    assert c.repo.saves == []


def test_shared_source_alias_uses_one_session_and_close(composition):
    c = composition
    shared = c.Core()
    first, alias = c.engine("first", shared=shared), c.engine("alias", shared=shared)
    manager = c.create()
    assert manager.resolve_playback("first:a") is manager.resolve_playback("alias:a")
    assert first.session is alias.session
    manager.getVoiceInstance("alias:a").active()
    manager.terminate(commit=False)
    manager.terminate(commit=False)
    assert shared.closes == 1
    assert first.core is alias.core is None
    assert first._runtime_binding is alias._runtime_binding is None
    assert manager.resolve_playback("first:a") is None


def test_failed_alias_open_preserves_existing_owner_and_closes_once(composition):
    c = composition
    shared = c.Core()
    first = c.engine("first", shared=shared)
    failed = c.engine("failed", shared=shared, fail=True)
    manager = c.create()
    session = manager.resolve_playback("first:a")
    assert session is first.session
    assert manager.resolve_playback("failed:a") is None
    assert shared.closes == 0
    assert failed.core is failed._runtime_binding is None
    spoken = []
    def speak(commands):
        assert shared.closes == 0
        spoken.append(commands)
    shared.speak = speak
    assert session.activate("first:a")
    session.speak(("owner remains usable",), SimpleNamespace(is_cancelled=lambda: False))
    assert spoken == [("owner remains usable",)]
    manager.terminate(commit=False)
    assert shared.closes == 1
    assert c.repo.saves == []


@pytest.mark.parametrize("failure", ["empty", "bind"])
def test_initialization_failure_closes_without_commit(composition, failure):
    c = composition
    cls = c.engine("bad", empty=failure == "empty")
    if failure == "bind":
        original = c.bridge.bind
        def bind(source, source_id):
            original(source, source_id)
            raise RuntimeError("bind failed")
        c.bridge.bind = bind
    with pytest.raises(RuntimeError, match="No WorldVoice voices|bind failed"):
        c.create()
    assert c.cores[0].closes == 1
    assert c.bridge._sources == {}
    assert c.repo.saves == []
    assert cls._runtime_binding is None


def test_source_is_bound_before_engine_is_published(composition):
    c = composition
    c.engine("ok")
    original = c.bridge.bind
    def bind(source, source_id):
        # The manager is still being constructed; its enumeration hook observes
        # only a resource whose notifications can already reach the scheduler.
        original(source, source_id)
    c.bridge.bind = bind
    original_voices = c.module.READY_ENGINE_CLASS["ok"].voices
    def voices(cls):
        assert id(cls.core) in c.bridge._sources
        return original_voices()
    c.module.READY_ENGINE_CLASS["ok"].voices = classmethod(voices)
    assert c.create().resolve_playback("ok:a") is not None


def test_cached_onecore_voice_round_trip_through_manager(composition):
    c = composition
    c.engine("OneCore")
    path = WORLDVOICE / "driver/OneCore/__init__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    voice_class = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    environment = {"Voice": c.driver.Voice, "SynthDriver": c.Core}
    exec(compile(ast.Module(body=[voice_class], type_ignores=[]), str(path), "exec"), environment)
    c.module.READY_ENGINE_CLASS["OneCore"] = environment["Voice"]
    manager = c.create()
    a, b = (manager.getVoiceInstance("OneCore:" + key) for key in ("a", "b"))
    a.update_settings(rate=72, pitch=61, volume=83)
    b.update_settings(rate=33, pitch=44, volume=55)
    for voice in (a, b, manager.getVoiceInstance(a.name)):
        voice.active()
    core = c.cores[0]
    assert (core.voice, core.language, core.rate, core.pitch, core.volume) == ("a", "en", 72, 61, 83)
    assert c.repo.loads == ["OneCore:a", "OneCore:b"]


def test_facade_creation_preserves_existing_pending_state_and_edit_baseline(composition):
    c = composition
    c.engine("ok")
    manager = c.create()
    state = c.store.ensure(manager.getVoiceSpec("ok:b"))
    edit = c.store.begin_edit()
    state.update(rate=72)
    voice = manager.getVoiceInstance("ok:b")
    assert voice.rate == 72
    edit.discard()
    assert voice.rate == 50


def test_manager_cancel_passes_sessions_without_core_access(composition):
    c = composition
    c.engine("ok")
    manager = c.create()
    received = []
    c.tasks.cancel = lambda playbacks=(): received.extend(playbacks)
    manager.cancel()
    assert received == [manager.resolve_playback("ok:a")]
    assert c.cores[0].cancels == 0


def test_normal_shutdown_saves_settings_without_a_facade(composition):
    c = composition
    c.engine("ok")
    manager = c.create()
    assert manager.resolve_playback("ok:b") is not None
    c.store.state("ok:b").update(rate=72)
    manager.terminate()
    assert c.repo.values["ok:b"]["rate"] == 72
    saves = list(c.repo.saves)
    manager.terminate()
    assert c.repo.saves == saves


def make_synth(c, manager):
    commands = {name: type(name, (), {}) for name in (
        "IndexCommand", "CharacterModeCommand", "LangChangeCommand", "BreakCommand",
        "PitchCommand", "RateCommand", "VolumeCommand",
    )}
    errors = []
    root = _load_synth_class({
        "SynthDriver": object, "synthIndexReached": object(), "synthDoneSpeaking": object(),
        "nvdaLog": SimpleNamespace(error=lambda *args, **kwargs: errors.append(args)), **commands,
    })
    synth = object.__new__(root)
    synth._terminated = synth._pipelineRegistered = synth._voicePanelPatched = False
    synth._spellingPatched = synth._startNotified = False
    synth.taskManager, synth._eventBridge, synth._voiceManager = c.tasks, c.bridge, manager
    return synth, errors


@pytest.mark.parametrize("bridge_error", [False, True])
def test_worker_stops_before_bridge_and_sessions_close(composition, bridge_error):
    c = composition
    c.engine("ok")
    manager = c.create()
    entered, release, stopping = (threading.Event() for _ in range(3))
    core = c.cores[0]
    def speak(commands):
        entered.set()
        assert release.wait(2)
    core.speak = speak
    request = c.tasks.new_request()
    c.tasks.append_speech(request, manager.resolve_playback("ok:a"), "ok:a", ("hello",))
    assert c.tasks.submit_request(request)
    assert entered.wait(1)
    closed = []
    original_shutdown, original_close, original_terminate = c.tasks.shutdown, c.bridge.close, core.terminate
    def shutdown(playbacks=()):
        stopping.set()
        original_shutdown(playbacks)
        closed.append("worker")
    def close_bridge():
        assert not c.tasks._thread.is_alive()
        was_closed = c.bridge._closed
        original_close()
        closed.append("bridge")
        if bridge_error and not was_closed:
            raise RuntimeError("bridge cleanup failure")
    def close_core():
        assert not c.tasks._thread.is_alive()
        assert c.bridge._closed
        original_terminate()
        closed.append("session")
    c.tasks.shutdown, c.bridge.close, core.terminate = shutdown, close_bridge, close_core
    synth, errors = make_synth(c, manager)
    thread = threading.Thread(target=synth.terminate)
    try:
        thread.start()
        assert stopping.wait(1)
        assert c.tasks._thread.is_alive()
        assert not c.bridge._closed
        assert core.closes == 0
    finally:
        release.set()
        thread.join(1)
    assert not thread.is_alive()
    assert len(errors) == int(bridge_error)
    assert closed == ["worker", "bridge", "session"]
    assert c.repo.saves


def test_save_or_engine_close_failure_does_not_abandon_other_resources(composition):
    c = composition
    c.engine("one")
    c.engine("two")
    manager = c.create()
    manager.getVoiceInstance("two:a")
    c.repo.fail_next_save = True
    def close_failure():
        c.cores[1].closes += 1
        raise RuntimeError("close failure")
    c.cores[1].terminate = close_failure
    manager.terminate()
    assert [core.closes for core in c.cores] == [1, 1]
    assert {name for name, values in c.repo.saves} == {"one:a", "two:a"}
    assert c.bridge._sources == {}


def test_waitfactor_updates_declared_capability_without_activating(composition):
    c = composition
    c.engine("plain")
    capable = c.engine("extension")
    capable.extra_capabilities = frozenset({"waitfactor", "variant"})
    manager = c.create()
    manager.waitfactor = 4
    assert manager.getVoiceInstance("extension:b").waitfactor == 4
    assert manager.getVoiceInstance("plain:a").waitfactor == 0
    assert manager.getVoiceCapabilities("extension:b").supports_variants
    assert not any(hasattr(core, "voice") for core in c.cores)


def test_pipeline_emits_voice_keys_without_constructing_selected_facades(composition):
    c = composition
    c.engine("ok")
    manager = c.create()
    c.module.config.conf["WorldVoice"]["role"] = {"zh": {"voice": "ok:b"}}
    models = importlib.import_module(c.module.__package__ + ".runtime.models")
    class Language:
        def __init__(self, lang):
            self.lang = lang
    class WVLanguage(Language):
        pass
    path = WORLDVOICE / "pipeline/__init__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "lang_cmd_to_voice")
    environment = {"Iterable": list, "Iterator": list, "SpeechCmd": object,
                   "LangChangeCommand": Language, "WVLangChangeCommand": WVLanguage,
                   "SelectVoice": models.SelectVoice}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), environment)
    result = list(environment["lang_cmd_to_voice"](
        [Language("zh"), "中文", WVLanguage(None), "English", Language("missing")],
        manager, manager.defaultVoiceInstance))
    assert result == [models.SelectVoice("ok:b"), "中文", models.SelectVoice("ok:a"),
                      "English", models.SelectVoice("ok:a")]
    assert tuple(manager._instanceCache) == ("ok:a",)


@pytest.mark.parametrize("submission", ["new", "building", "speak"])
def test_termination_closes_admission_before_blocking_cancel(composition, submission):
    c = composition
    c.engine("one")
    c.engine("two")
    manager = c.create()
    synth, errors = make_synth(c, manager)
    building = c.tasks.new_request()
    c.tasks.append_speech(building, manager.resolve_playback("one:a"), "one:a", ("pending",))
    entered, release = threading.Event(), threading.Event()
    def cancel():
        c.cores[0].cancels += 1
        entered.set()
        assert release.wait(2)
    c.cores[0].cancel = cancel
    thread = threading.Thread(target=synth.terminate)
    try:
        thread.start()
        assert entered.wait(1)
        assert synth._terminated
        if submission == "new":
            scheduler = importlib.import_module(c.module.__package__ + ".runtime.scheduler")
            with pytest.raises(scheduler.InvalidRequestState):
                c.tasks.new_request()
        elif submission == "building":
            assert c.tasks.submit_request(building) is False
            assert building.token.is_cancelled()
        else:
            # Terminated entry points must return before touching pipeline or
            # facade dependencies, which may already be unavailable.
            assert synth.speak(["ignored"]) is None
        assert c.tasks._thread.is_alive()
        assert not c.bridge._closed
        assert [core.closes for core in c.cores] == [0, 0]
    finally:
        release.set()
        thread.join(1)
    assert not thread.is_alive()
    assert errors == []
    assert [core.cancels for core in c.cores] == [1, 1]
    assert [core.closes for core in c.cores] == [1, 1]
    assert not c.tasks._thread.is_alive()
