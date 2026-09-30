"""Production manager, facade, adapter, session and bridge composition."""

import ast
from concurrent.futures import CancelledError
import importlib
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest

from runtime_harness import MemoryRepository
from test_worldvoice_lifecycle import _load_voice_manager, _load_synth_class, WORLDVOICE
from test_worldvoice_request_builder import EventStub
from test_worldvoice_index_command import nvda_commands


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
    models = importlib.import_module(package + ".runtime.models")
    ledger = importlib.import_module(package + ".indexLedger").IndexLedger()
    repo = MemoryRepository()
    store = settings.VoiceSettingsStore(repo)
    done, index = EventStub(), EventStub()
    owner = object()
    bridge = bridge_module.NvdaEventBridge(owner, done_event=done, index_event=index, get_synth=lambda: owner, index_ledger=ledger)
    tasks = scheduler.TaskManager(bridge)
    bridge.start(tasks.on_event, batch_handler=tasks.on_events)
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

    def create(completion_for=lambda cls, core: models.CompletionContract()):
        manager = manager_module.VoiceManager(tasks, store, bridge,
            index_ledger=ledger, completion_for=completion_for)
        managers.append(manager)
        return manager

    yield SimpleNamespace(engine=engine, create=create, store=store, repo=repo,
                          bridge=bridge, tasks=tasks, cores=cores, Core=Core,
                          module=manager_module, driver=driver, ledger=ledger, models=models,
                          done=done, index=index, owner=owner)
    tasks.shutdown()
    bridge.close()
    for manager in managers:
        manager.terminate(commit=False)
    ledger.close()


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
        def bind(source, source_id, **kwargs):
            original(source, source_id, **kwargs)
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
    def bind(source, source_id, **kwargs):
        # The manager is still being constructed; its enumeration hook observes
        # only a resource whose notifications can already reach the scheduler.
        original(source, source_id, **kwargs)
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


@pytest.mark.parametrize("during_edit", [False, True])
def test_first_voice_resolution_inherits_main_values_and_keeps_cancel_baseline(composition, during_edit):
    c = composition
    c.engine("ok")
    conf = c.module.config.conf
    conf["WorldVoice"]["voices"] = {}
    conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
    conf["speech"] = {"WorldVoice": {"rate": 83}}
    repository_module = importlib.import_module(c.module.__package__ + ".configRepository")
    c.store._repository = repository_module.ConfigVoiceSettingsRepository(conf, lambda: "WorldVoice")
    manager = c.create()
    edit = c.store.begin_edit() if during_edit else None
    try:
        assert manager.resolve_playback("ok:b") is not None
        state = c.store.state("ok:b")
        assert state.get("rate") == 83
        assert manager.defaultVoiceInstance.rate == 83
        if edit is None:
            edit = c.store.begin_edit()
        state.update(rate=72)
        voice = manager.getVoiceInstance("ok:b")
        assert voice.rate == 72
        assert c.store.state("ok:b") is state
        edit.discard()
        assert voice.rate == 83
        assert conf["WorldVoice"]["voices"]["ok:b"]["rate"] == 50
    finally:
        if edit is not None:
            edit.close()


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
    synth._indexLedger = c.ledger
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


def marker_contract(c):
    return c.models.CompletionContract(c.models.CompletionMode.END_INDEX, c.models.IndexRange(501, 510))


def test_resource_bound_before_first_encoded_speech(composition, nvda_commands):
    c = composition
    cls = c.engine("marker")
    selected = []
    contract = marker_contract(c)
    def completion_for(voice_class, core):
        assert voice_class is cls and core is cls.core
        assert cls.session is None
        selected.append(core)
        return contract
    manager = c.create(completion_for)
    port = manager.resolve_playback("marker:a")
    spoken = []
    finished = threading.Event()
    def speak(commands):
        spoken.extend(commands)
        c.index.notify(synth=cls.core, index=commands[-1].index)
    cls.core.speak = speak
    c.done.register(lambda synth: finished.set() if synth is c.owner else None)
    request = c.tasks.new_request()
    original = nvda_commands.IndexCommand(42)
    c.tasks.append_speech(request, port, "marker:a", ("hello", original))
    assert c.tasks.submit_request(request)
    assert finished.wait(1)
    assert [item.index for item in spoken if isinstance(item, nvda_commands.IndexCommand)] == [501, 502]
    assert original.index == 42
    assert selected == [cls.core]
    assert port.completion == contract


def test_alias_uses_one_allocator_and_one_close(composition, nvda_commands):
    c = composition
    shared = c.Core()
    c.engine("first", shared=shared)
    c.engine("alias", shared=shared)
    manager = c.create(lambda cls, core: marker_contract(c))
    spoken = []
    shared.speak = lambda commands: spoken.append(commands[-1].index)
    for segment, key in enumerate(("first:a", "alias:a"), 1):
        port = manager.resolve_playback(key)
        port.speak(("hello",), SimpleNamespace(is_cancelled=lambda: False),
                   context=c.models.PlaybackContext(port.source_id, segment))
    assert spoken == [501, 502]
    manager.terminate(commit=False)
    assert shared.closes == 1


def test_alias_conflicting_completion_contract_is_rejected(composition):
    c = composition
    shared = c.Core()
    first = c.engine("first", shared=shared)
    alias = c.engine("alias", shared=shared)
    with pytest.raises(ValueError, match="completion contract"):
        c.create(lambda cls, core: marker_contract(c) if cls is first else c.models.CompletionContract())
    assert first.session is alias.session is None
    assert first.core is alias.core is None
    assert shared.closes == 1
    assert c.bridge._sources == {}
    assert c.repo.saves == []


def test_partial_bind_failure_releases_resources_without_commit(composition):
    c = composition
    cls = c.engine("marker")
    original = c.bridge.bind
    source_ids = []
    def bind(source, source_id, **kwargs):
        original(source, source_id, **kwargs)
        source_ids.append(source_id)
        assert cls.session is None
        raise RuntimeError("partial marker bind")
    c.bridge.bind = bind
    with pytest.raises(RuntimeError, match="partial marker bind"):
        c.create(lambda cls, core: marker_contract(c))
    assert c.cores[0].closes == 1
    assert c.bridge._sources == {}
    with pytest.raises(importlib.import_module(c.module.__package__ + ".indexLedger").InvalidIndexContext):
        c.ledger.prepare(c.models.PlaybackContext(source_ids[0], 1), ())
    assert c.repo.saves == []


def test_shutdown_disables_late_index_before_engine_close(composition):
    c = composition
    cls = c.engine("marker")
    manager = c.create(lambda cls, core: marker_contract(c))
    port = manager.resolve_playback("marker:a")
    marker = c.ledger.prepare(c.models.PlaybackContext(port.source_id, 1), (42,)).end_index
    received = []
    c.index.register(lambda synth, index: received.append(index) if synth is c.owner else None)
    original_close = cls.core.terminate
    def close():
        assert c.bridge._closed
        assert not c.ledger._closed
        c.index.notify(synth=cls.core, index=marker)
        original_close()
    cls.core.terminate = close
    synth, errors = make_synth(c, manager)
    synth.terminate()
    assert received == []
    assert errors == []
    assert c.ledger._closed


def test_completion_selection_failure_closes_opened_core(composition):
    c = composition
    cls = c.engine("marker")
    def fail(cls, core):
        raise RuntimeError("policy failure")
    with pytest.raises(RuntimeError, match="policy failure"):
        c.create(fail)
    assert c.cores[0].closes == 1
    assert cls.session is None
    assert c.repo.saves == []


def test_live_core_rebind_preserves_allocator_high_water(composition, nvda_commands):
    c = composition
    cls = c.engine("marker")
    manager = c.create(lambda cls, core: marker_contract(c))
    port = manager.resolve_playback("marker:a")
    spoken = []
    cls.core.speak = lambda commands: spoken.append(commands[-1].index)
    token = SimpleNamespace(is_cancelled=lambda: False)
    port.speak(("first",), token, context=c.models.PlaybackContext(port.source_id, 1))
    c.bridge.unbind(port.source_id)
    c.bridge.bind(cls.core, port.source_id, completion=port.completion)
    port.speak(("second",), token, context=c.models.PlaybackContext(port.source_id, 2))
    assert spoken == [501, 502]
    assert cls.core.closes == 0
    assert c.ledger.receive_index(port.source_id, 501) == ()


def test_entry_point_imports_real_ledger_and_completion_policy(monkeypatch, nvda_commands):
    """Execute the entire addon module, including its real relative imports."""
    from types import ModuleType

    package = "worldvoice_entrypoint_import_test"
    def stub(name, **values):
        module = ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
        return module

    stub("addonHandler", initTranslation=lambda: None)
    stub("autoSettingsUtils", __path__=[])
    stub("autoSettingsUtils.driverSetting", BooleanDriverSetting=object,
         DriverSetting=object, NumericDriverSetting=object)
    stub("autoSettingsUtils.utils", StringParameterInfo=object)
    stub("config", conf=SimpleNamespace(spec={}))
    stub("extensionPoints", Action=EventStub)
    stub("gui")
    stub("languageHandler")
    stub("logHandler", log=SimpleNamespace())
    stub("versionInfo", version="test")
    for name in ("CharacterModeCommand", "LangChangeCommand", "PitchCommand",
                 "RateCommand", "VolumeCommand", "SpeechCommand"):
        monkeypatch.setattr(nvda_commands, name, type(name, (), {}), raising=False)
    stub("speech.extensions", filter_speechSequence=SimpleNamespace())
    stub("synthDriverHandler", VoiceInfo=object, SynthDriver=type("SynthDriver", (), {}),
         synthIndexReached=EventStub(), synthDoneSpeaking=EventStub(), getSynth=lambda: None)
    stub("generics", __path__=[])
    stub("generics.speechSymbols", __path__=[])
    stub("generics.speechSymbols.models", SpeechSymbols=object)
    # Unrelated UI and pipeline modules need NVDA, but all changed composition
    # boundaries below are imported from their actual files by __init__.py.
    stub(package + ".languageDetection")
    stub(package + ".pipeline", **{name: lambda *args: None for name in (
        "ignore_comma_between_number", "item_wait_factor", "inject_langchange_reorder",
        "deduplicate_language_command", "lang_cmd_to_voice", "order_move_to_start_register", "listable")})
    stub(package + ".pipeline.settings", **{name: lambda *args: None for name in (
        "apply_worldvoice_pipeline", "clear_pipeline", "get_effective_pipeline_settings", "save_pipeline_settings")})
    stub(package + ".engine", EngineType=[], READY_ENGINE_CLASS={},
         get_engine_enabled=lambda *args: True, refresh_ready_engine_classes=lambda *args: None)
    stub(package + ".VoiceSettingsDialogs", WorldVoiceVoiceSettingsPanel=object)
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec = importlib.util.spec_from_file_location(package, WORLDVOICE / "__init__.py",
                                                submodule_search_locations=[str(WORLDVOICE)])
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, package, module)
    try:
        spec.loader.exec_module(module)
        ledger = importlib.import_module(package + ".indexLedger")
        policies = importlib.import_module(package + ".compat.completionPolicies")
        models = importlib.import_module(package + ".runtime.models")
        assert module.IndexLedger is ledger.IndexLedger
        assert module.get_completion_contract is policies.get_completion_contract
        assert module.get_completion_contract("unverified", nvda_version="test", audio_mode="test").mode is models.CompletionMode.LEGACY_DONE
        assert module.SynthDriver.__module__ == package
        assert ledger.__file__ == str(WORLDVOICE / "indexLedger.py")
        assert policies.__file__ == str(WORLDVOICE / "compat/completionPolicies.py")
    finally:
        for name in tuple(sys.modules):
            if name.startswith(package + "."):
                monkeypatch.delitem(sys.modules, name, raising=False)


def drain_contract(c, mode="DRAIN"):
    return c.models.CompletionContract(getattr(c.models.CompletionMode, mode), c.models.IndexRange(1, 9999))


def runtime_completion_selector(c, version="synthetic"):
    policies = importlib.import_module(c.module.__package__ + ".compat.completionPolicies")
    commands = {name: type(name, (), {}) for name in (
        "IndexCommand", "CharacterModeCommand", "LangChangeCommand", "BreakCommand",
        "PitchCommand", "RateCommand", "VolumeCommand")}
    logs = []
    root = _load_synth_class({
        "SynthDriver": object, "synthIndexReached": object(), "synthDoneSpeaking": object(),
        "versionInfo": SimpleNamespace(version=version),
        "get_completion_contract": policies.get_completion_contract,
        "get_segment_drain_support": getattr(policies, "get_segment_drain_support", None),
        "nvdaLog": SimpleNamespace(warning=lambda *args: logs.append(args)), **commands,
    })
    return object.__new__(root)._completion_for, logs


def installed_drain_voice(c, monkeypatch, name="OneCore", *, supported=True):
    """Replace unavailable native resources at the installed-driver boundary."""
    support_type = importlib.import_module(c.module.__package__ + ".runtime.playbackWork").DrainSupport
    cls = c.engine(name)
    module_name = c.module.__package__ + ".driver." + name
    checked, spoken = [], []

    class SynthDriver(c.Core):
        def get_segment_drain_support(self, *, nvda_version, audio_mode):
            checked.append((nvda_version, audio_mode))
            return support_type(supported, "native-test-profile", "Native callback lifetime is unproven")

        def speak_segment(self, commands, token, *, context, on_event):
            spoken.append((commands, context))
            on_event(c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                           context.source_id, segment_id=context.segment_id))

    SynthDriver.__module__ = cls.__module__ = module_name
    cls.synth_driver_class = SynthDriver
    cls.engineOn = classmethod(lambda voice: setattr(voice, "core", SynthDriver()))
    module = ModuleType(module_name)
    module.Voice, module.SynthDriver = cls, SynthDriver
    monkeypatch.setitem(sys.modules, module_name, module)
    return SimpleNamespace(voice=cls, driver=SynthDriver, module=module,
                           checked=checked, spoken=spoken, support_type=support_type)


@pytest.mark.parametrize("engine", ["OneCore", "Neural", "VE", "Cerence", "SAPI5", "Espeak"])
def test_supported_installed_wrapper_is_bound_before_first_drain_speech(composition, monkeypatch, nvda_commands, engine):
    c = composition
    installed = installed_drain_voice(c, monkeypatch, engine)
    if engine in ("OneCore", "SAPI5"):
        installed.driver.useWasapi = True
    configured = []
    configure = c.module.LegacyEngineAdapter.configure_segment_events
    def configure_after_bind(adapter, factory):
        assert installed.voice.session is None
        assert c.bridge._sources[id(installed.voice.core)].source is installed.voice.core
        configure(adapter, factory)
        configured.append(adapter)
    monkeypatch.setattr(c.module.LegacyEngineAdapter, "configure_segment_events", configure_after_bind)
    select, logs = runtime_completion_selector(c)
    manager = c.create(select)
    port = manager.resolve_playback(engine + ":a")
    assert port.completion.mode is c.models.CompletionMode.DRAIN
    assert configured == [port._adapter]
    assert installed.checked == [("synthetic", "wasapi" if engine in ("OneCore", "SAPI5") else "default")]
    assert logs == []
    done, indexes = threading.Event(), []
    c.done.register(lambda synth: done.set() if synth is c.owner else None)
    c.index.register(lambda synth, index: indexes.append(index) if synth is c.owner else None)
    request = c.tasks.new_request()
    c.tasks.append_speech(request, port, engine + ":a", ("hello", nvda_commands.IndexCommand(42)))
    assert c.tasks.submit_request(request) and done.wait(1)
    commands, context = installed.spoken[0]
    assert context.source_id is port.source_id
    assert [command.index for command in commands if isinstance(command, nvda_commands.IndexCommand)] == [1]
    assert indexes == [42]
    with pytest.raises(RuntimeError, match="before speech"):
        port._adapter.configure_completion(c.models.CompletionContract())
    policies = importlib.import_module(c.module.__package__ + ".compat.completionPolicies")
    assert policies._VERIFIED_CONTRACTS == {}


@pytest.mark.parametrize("engine", ["SAPI5", "Espeak"])
@pytest.mark.parametrize("outcome", ["failure", "cancel"])
def test_new_installed_wrapper_retains_request_identity_on_failure_or_cancel(
        composition, monkeypatch, nvda_commands, engine, outcome):
    c = composition
    installed = installed_drain_voice(c, monkeypatch, engine)
    if engine == "SAPI5":
        installed.driver.useWasapi = True
    selected, _ = runtime_completion_selector(c)
    manager = c.create(selected)
    port = manager.resolve_playback(engine + ":a")
    assert port.completion.mode is c.models.CompletionMode.DRAIN
    entered = threading.Event()
    calls = []
    def hold(self, commands, token, *, context, on_event):
        calls.append((context, on_event))
        entered.set()
    installed.driver.speak_segment = hold
    request = c.tasks.new_request()
    future = c.tasks.append_speech(request, port, engine + ":a", ("first",))
    assert c.tasks.submit_request(request) and entered.wait(1)
    context, sink = calls[0]
    if outcome == "failure":
        error = RuntimeError("native playback failed")
        sink(c.models.PlaybackEvent(c.models.EventKind.SEGMENT_FAILED,
                                    context.source_id, segment_id=context.segment_id, error=error))
        with pytest.raises(RuntimeError, match="native playback failed"):
            future.result(1)
        assert request.state.name == "FAILED"
    else:
        c.tasks.cancel((port,))
        sink(c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                    context.source_id, segment_id=context.segment_id))
        with pytest.raises(CancelledError):
            future.result(1)
        assert future.cancelled()
        assert request.state.name == "CANCELLED"


@pytest.mark.parametrize("engine", ["OneCore", "SAPI5"])
@pytest.mark.parametrize("use_wasapi,audio_mode,completion_mode", [
    (True, "wasapi", "DRAIN"), (False, "legacy", "LEGACY_DONE"),
    ("absent", "unknown", "LEGACY_DONE"), (None, "unknown", "LEGACY_DONE"),
    ("true", "unknown", "LEGACY_DONE"), (1, "unknown", "LEGACY_DONE"),
    (0, "unknown", "LEGACY_DONE"),
])
def test_wasapi_mode_sensitive_support_uses_actual_opened_core(
        composition, monkeypatch, engine, use_wasapi, audio_mode, completion_mode):
    c = composition
    installed = installed_drain_voice(c, monkeypatch, engine)
    if use_wasapi != "absent":
        installed.driver.useWasapi = use_wasapi
    checked = []
    def support(self, *, nvda_version, audio_mode):
        checked.append((nvda_version, audio_mode))
        return installed.support_type(audio_mode == "wasapi", "mode-sensitive-test-profile",
                                      "Only the reviewed WASAPI audio profile is supported")
    installed.driver.get_segment_drain_support = support
    select, logs = runtime_completion_selector(c)
    manager = c.create(select)
    port = manager.resolve_playback(engine + ":a")
    assert checked == [("synthetic", audio_mode)]
    assert port.completion.mode is getattr(c.models.CompletionMode, completion_mode)
    assert len(logs) == (0 if completion_mode == "DRAIN" else 1)
    policies = importlib.import_module(c.module.__package__ + ".compat.completionPolicies")
    assert policies._VERIFIED_CONTRACTS == {}


@pytest.mark.parametrize("engine", ["OneCore", "SAPI5", "Espeak"])
@pytest.mark.parametrize("failure", ["foreign_voice", "foreign_driver", "wrong_core", "missing_entry",
                                    "wrong_signature", "missing_support", "invalid_support",
                                    "truthy_support", "unsupported", "support_error"])
def test_unconfirmed_wrapper_uses_legacy_and_logs_concrete_fallback_once(composition, monkeypatch, engine, failure):
    c = composition
    installed = installed_drain_voice(c, monkeypatch, engine)
    cls = installed.voice
    if failure == "foreign_voice":
        installed.module.Voice = type("ForeignVoice", (), {})
    elif failure == "foreign_driver":
        installed.driver.__module__ = "foreign_driver"
    elif failure == "wrong_core":
        cls.engineOn = classmethod(lambda voice: setattr(voice, "core", c.Core()))
    elif failure == "missing_entry":
        installed.driver.speak_segment = None
    elif failure == "wrong_signature":
        installed.driver.speak_segment = lambda self, commands: None
    elif failure == "missing_support":
        installed.driver.get_segment_drain_support = None
    elif failure == "invalid_support":
        installed.driver.get_segment_drain_support = lambda *args, **kwargs: SimpleNamespace(supported=True)
    elif failure == "truthy_support":
        installed.driver.get_segment_drain_support = lambda *args, **kwargs: installed.support_type(
            "yes", "native-test-profile", "Not an explicit boolean support decision")
    elif failure == "unsupported":
        installed.driver.get_segment_drain_support = lambda *args, **kwargs: installed.support_type(
            False, "native-test-profile", "Native callback lifetime is unproven")
    elif failure == "support_error":
        def fail(*args, **kwargs):
            raise RuntimeError("Native profile inspection failed")
        installed.driver.get_segment_drain_support = fail
    select, logs = runtime_completion_selector(c)
    manager = c.create(select)
    port = manager.resolve_playback(engine + ":a")
    assert port.completion.mode is c.models.CompletionMode.LEGACY_DONE
    assert port.completion.index_range is None
    assert select(cls, cls.core) == port.completion
    assert len(logs) == 1
    assert "LEGACY_DONE" in logs[0][0] and logs[0][-1]
    if failure == "unsupported":
        assert logs[0][-1] == "Native callback lifetime is unproven"
    if failure == "support_error":
        assert "Native profile inspection failed" in logs[0][-1]


def test_unsupported_targets_sharing_core_keep_one_legacy_owner(composition):
    c = composition
    shared = c.Core()
    first, alias = c.engine("OneCore", shared=shared), c.engine("Neural", shared=shared)
    select, logs = runtime_completion_selector(c)
    manager = c.create(select)
    port = manager.resolve_playback("OneCore:a")
    assert manager.resolve_playback("Neural:a") is port
    assert port.completion.mode is c.models.CompletionMode.LEGACY_DONE
    manager.terminate(commit=False)
    assert shared.closes == 1 and first.core is alias.core is None


def test_drain_factory_configured_after_bind_before_publication(composition, monkeypatch, nvda_commands):
    c = composition
    cls = c.engine("drain")
    calls, setup = [], []
    cls.synth_driver_class.speak_segment = lambda core, commands, token, **kwargs: calls.append(kwargs)
    configure = c.module.LegacyEngineAdapter.configure_segment_events
    def configure_after_bind(adapter, factory):
        assert cls.session is None
        assert c.bridge._sources[id(cls.core)].source is cls.core
        configure(adapter, factory)
        setup.append(adapter)
    monkeypatch.setattr(c.module.LegacyEngineAdapter, "configure_segment_events", configure_after_bind)
    manager = c.create(lambda cls, core: drain_contract(c))
    port = manager.resolve_playback("drain:a")
    context = c.models.PlaybackContext(port.source_id, 1)
    port.speak(("hello",), SimpleNamespace(is_cancelled=lambda: False), context=context)
    assert len(setup) == 1
    assert calls[0]["context"] is context and callable(calls[0]["on_event"])


@pytest.mark.parametrize("mode", ["DRAIN", "END_INDEX_AND_DRAIN"])
@pytest.mark.parametrize("order", ["drain_first", "end_first"])
def test_drain_request_integrates_encoded_indexes_and_native_events(composition, nvda_commands, mode, order):
    c = composition
    cls = c.engine("drain")
    cls.synth_driver_class.speak_segment = lambda *args, **kwargs: None
    manager = c.create(lambda cls, core: drain_contract(c, mode))
    port = manager.resolve_playback("drain:a")
    indexes, sinks, completed = [], [], threading.Event()
    c.index.register(lambda synth, index: indexes.append(index) if synth is c.owner else None)
    c.done.register(lambda synth: completed.set() if synth is c.owner else None)
    def speak(commands, token, *, context, on_event):
        sinks.append(on_event)
        drain = c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                      context.source_id, segment_id=context.segment_id)
        if mode == "END_INDEX_AND_DRAIN" and order == "end_first":
            c.index.notify(synth=cls.core, index=commands[-1].index)
        on_event(drain)
        if mode == "END_INDEX_AND_DRAIN" and order == "drain_first":
            c.index.notify(synth=cls.core, index=commands[-1].index)
    cls.core.speak_segment = speak
    request = c.tasks.new_request()
    c.tasks.append_speech(request, port, "drain:a", ("hello", nvda_commands.IndexCommand(42),
                                                   nvda_commands.IndexCommand(7)))
    assert c.tasks.submit_request(request)
    assert completed.wait(1)
    assert indexes == [42, 7] and len(sinks) == 1


@pytest.mark.parametrize("action", ["cancel", "unbind"])
def test_index_handler_revokes_remainder_of_drain_batch(composition, nvda_commands, action):
    c = composition
    cls = c.engine("drain")
    cls.synth_driver_class.speak_segment = lambda *args, **kwargs: None
    manager = c.create(lambda cls, core: drain_contract(c))
    port = manager.resolve_playback("drain:a")
    entered, returned = threading.Event(), threading.Event()
    indexes, completed = [], []
    c.done.register(lambda synth: completed.append(synth))
    def output(synth, index):
        if synth is c.owner:
            indexes.append(index)
            if action == "cancel":
                c.tasks.cancel((port,))
            else:
                c.bridge.unbind(port.source_id)
    c.index.register(output)
    def speak(commands, token, *, context, on_event):
        entered.set()
        on_event(c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                      context.source_id, segment_id=context.segment_id))
        returned.set()
    cls.core.speak_segment = speak
    request = c.tasks.new_request()
    future = c.tasks.append_speech(request, port, "drain:a",
                                 (nvda_commands.IndexCommand(42), nvda_commands.IndexCommand(7)))
    assert c.tasks.submit_request(request)
    assert entered.wait(1) and returned.wait(1)
    assert indexes == [42] and completed == []
    if action == "cancel":
        assert future.cancelled()
    else:
        assert not future.done()


def test_drain_alias_uses_only_owner_event_factory(composition, monkeypatch, nvda_commands):
    c = composition
    shared = c.Core()
    shared.speak_segment = lambda *args, **kwargs: None
    first, alias = c.engine("first", shared=shared), c.engine("alias", shared=shared)
    configured = []
    configure = c.module.LegacyEngineAdapter.configure_segment_events
    def record(adapter, factory):
        configured.append(adapter)
        configure(adapter, factory)
    monkeypatch.setattr(c.module.LegacyEngineAdapter, "configure_segment_events", record)
    manager = c.create(lambda cls, core: drain_contract(c))
    owner = manager.resolve_playback("first:a")
    assert manager.resolve_playback("alias:a") is owner
    assert configured == [owner._adapter] and len(c.bridge._sources) == 1
    manager.terminate(commit=False)
    assert first.session is alias.session is None and shared.closes == 1


def test_partial_event_configuration_rolls_back_binding_and_owner(composition, monkeypatch):
    c = composition
    cls = c.engine("drain")
    cls.synth_driver_class.speak_segment = lambda *args, **kwargs: None
    configure = c.module.LegacyEngineAdapter.configure_segment_events
    def fail_after_configure(adapter, factory):
        configure(adapter, factory)
        assert cls.session is None
        raise RuntimeError("partial event setup")
    monkeypatch.setattr(c.module.LegacyEngineAdapter, "configure_segment_events", fail_after_configure)
    with pytest.raises(RuntimeError, match="partial event setup"):
        c.create(lambda cls, core: drain_contract(c))
    assert c.bridge._sources == {}
    assert cls.core is cls.session is None and c.cores[0].closes == 1
    assert c.repo.saves == []


def test_each_drain_factory_captures_its_own_resource(composition, nvda_commands):
    c = composition
    first, second = c.engine("first"), c.engine("second")
    first.synth_driver_class.speak_segment = lambda *args, **kwargs: None
    manager = c.create(lambda cls, core: drain_contract(c))
    calls, completed = [], threading.Event()
    for cls in (first, second):
        def speak(commands, token, *, context, on_event, source=cls.core):
            assert c.bridge._sources[id(source)].source_id is context.source_id
            calls.append(source)
            on_event(c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                          context.source_id, segment_id=context.segment_id))
        cls.core.speak_segment = speak
    c.done.register(lambda synth: completed.set() if synth is c.owner else None)
    request = c.tasks.new_request()
    for key in ("first:a", "second:a"):
        c.tasks.append_speech(request, manager.resolve_playback(key), key, ("hello",))
    assert c.tasks.submit_request(request) and completed.wait(1)
    assert calls == [first.core, second.core]


def test_reentrant_drain_supplier_waits_until_current_index_batch_finishes(composition, nvda_commands):
    c = composition
    cls = c.engine("drain")
    cls.synth_driver_class.speak_segment = lambda *args, **kwargs: None
    manager = c.create(lambda cls, core: drain_contract(c))
    port = manager.resolve_playback("drain:a")
    delivery, current = [], {}
    completed = threading.Event()
    receive = c.ledger.receive_segment_event
    def record_decode(event, **kwargs):
        delivery.append("decode")
        return receive(event, **kwargs)
    c.ledger.receive_segment_event = record_decode
    def output(synth, index):
        if synth is c.owner:
            delivery.append(index)
            if index == 42:
                current["sink"](current["event"])
    c.index.register(output)
    c.done.register(lambda synth: completed.set() if synth is c.owner else None)
    def speak(commands, token, *, context, on_event):
        current["sink"] = on_event
        current["event"] = c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                               context.source_id, segment_id=context.segment_id)
        on_event(current["event"])
    cls.core.speak_segment = speak
    request = c.tasks.new_request()
    c.tasks.append_speech(request, port, "drain:a", (nvda_commands.IndexCommand(42),
                                                  nvda_commands.IndexCommand(7)))
    assert c.tasks.submit_request(request) and completed.wait(1)
    assert delivery == ["decode", 42, 7, "decode"]


def test_old_drain_sink_cannot_complete_request_after_core_rebind(composition, nvda_commands):
    c = composition
    cls = c.engine("drain")
    cls.synth_driver_class.speak_segment = lambda *args, **kwargs: None
    manager = c.create(lambda cls, core: drain_contract(c))
    port = manager.resolve_playback("drain:a")
    entered = threading.Event()
    calls, indexes = [], []
    c.index.register(lambda synth, index: indexes.append(index) if synth is c.owner else None)
    def speak(commands, token, *, context, on_event):
        calls.append((context, on_event))
        entered.set()
    cls.core.speak_segment = speak
    first = c.tasks.new_request()
    c.tasks.append_speech(first, port, "drain:a", ("old",))
    assert c.tasks.submit_request(first) and entered.wait(1)
    c.tasks.cancel((port,))
    c.bridge.unbind(port.source_id)
    c.bridge.bind(cls.core, port.source_id, completion=port.completion)
    entered.clear()
    second = c.tasks.new_request()
    future = c.tasks.append_speech(second, port, "drain:a", ("new", nvda_commands.IndexCommand(42)))
    assert c.tasks.submit_request(second) and entered.wait(1)
    old_context, old_sink = calls[0]
    old_sink(c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                   old_context.source_id, segment_id=old_context.segment_id))
    assert indexes == [] and not future.done()
    new_context, new_sink = calls[1]
    new_sink(c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                   new_context.source_id, segment_id=new_context.segment_id))
    assert future.result(1) is True and indexes == [42]
