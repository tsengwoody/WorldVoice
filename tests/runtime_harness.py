"""Load the pure runtime without executing the WorldVoice/NVDA entry point."""

import importlib.util
import builtins
from contextlib import contextmanager
from pathlib import Path
import sys
from threading import Condition, Event
from types import ModuleType, SimpleNamespace

import pytest


RUNTIME = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/runtime"
PACKAGE = "worldvoice_runtime_test"


def load_runtime(monkeypatch, package_name=PACKAGE):
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module

    package = load(package_name, RUNTIME / "__init__.py")
    models = load(f"{package_name}.models", RUNTIME / "models.py")
    settings = load(f"{package_name}.settings", RUNTIME / "settings.py")
    session = load(f"{package_name}.session", RUNTIME / "session.py")
    return SimpleNamespace(package=package, models=models, settings=settings, session=session)


def load_scheduler(monkeypatch, rt):
    name = f"{rt.package.__name__}.scheduler"
    spec = importlib.util.spec_from_file_location(name, RUNTIME / "scheduler.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


class RecordingOutput:
    def __init__(self):
        self.indexes = []
        self.done_count = 0
        self.condition = Condition()

    def index_reached(self, index):
        with self.condition:
            self.indexes.append(index)
            self.condition.notify_all()

    def done_speaking(self):
        with self.condition:
            self.done_count += 1
            self.condition.notify_all()

    def wait_done(self, timeout=1, count=1):
        with self.condition:
            self.condition.wait_for(lambda: self.done_count >= count, timeout)
            return self.done_count


@pytest.fixture
def rt(monkeypatch):
    return load_runtime(monkeypatch)


def make_spec(key="Fake:a", language="en"):
    engine, voice_id = key.split(":", 1)
    return sys.modules[f"{PACKAGE}.models"].VoiceSpec(
        voice_id, key, f"Voice {voice_id}", language, engine, language,
    )


class MemoryRepository:
    def __init__(self):
        self.values = {}
        self.loads = []
        self.saves = []
        self.fail_next_save = False
        self.before_save = None

    def load(self, spec):
        self.loads.append(spec.name)
        return self.values.get(spec.name, {}).copy()

    def save(self, spec, values):
        self.saves.append((spec.name, dict(values)))
        if self.before_save is not None:
            self.before_save(spec, values)
        if self.fail_next_save:
            self.fail_next_save = False
            raise OSError("Save failed")
        self.values[spec.name] = dict(values)


class FakeAdapter:
    """An observable engine boundary with explicit blocking/failure hooks."""

    def __init__(self, capabilities=None, voices=(), voice_variants=None):
        self.notification_source = object()
        self.capabilities = capabilities
        self.voices = voices
        self.voice_variants = voice_variants or {}
        self.applied = []
        self.spoken = []
        self.contexts = []
        self.finished = []
        self.paused = []
        self.open_count = 0
        self.close_count = 0
        self.cancel_count = 0
        self.cancel_entered = Event()
        self.before_apply = None
        self.before_speak = None
        self.open_error = None
        self.close_error = None

    def open(self):
        self.open_count += 1
        if self.open_error is not None:
            raise self.open_error

    def close(self):
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error

    def list_voices(self):
        return self.voices

    def variants(self, key):
        return self.voice_variants.get(key, ())

    def apply(self, spec, snapshot):
        self.applied.append((spec, snapshot))
        if self.before_apply is not None:
            self.before_apply(spec, snapshot)

    def speak(self, commands, token, *, context=None):
        self.contexts.append(context)
        self.spoken.append((commands, token))
        if self.before_speak is not None:
            self.before_speak(commands, token)

    def finish_segment(self, context):
        self.finished.append(context)

    def cancel(self):
        self.cancel_count += 1
        self.cancel_entered.set()

    def pause(self, switch):
        self.paused.append(switch)


class FakePlayback(FakeAdapter):
    """Pure playback port; hooks run at the actual engine-call boundary."""

    def __init__(self):
        super().__init__()
        self.source_id = object()
        self.completion = sys.modules[f"{PACKAGE}.models"].CompletionContract()
        self.activated = []
        self.on_activate = None
        self.on_speak = None
        self.on_cancel = None
        self.entered = Event()

    def activate(self, key):
        self.activated.append(key)
        if self.on_activate:
            self.on_activate()
        return True

    def speak(self, commands, token, *, context=None):
        super().speak(commands, token, context=context)
        self.entered.set()
        if self.on_speak:
            self.on_speak()

    def cancel(self):
        super().cancel()
        if self.on_cancel:
            self.on_cancel()


def load_config_repository(monkeypatch, rt):
    # Supply only the package namespace: never execute the NVDA entry point.
    from types import ModuleType

    package_name = "worldvoice_repository_test"
    package = ModuleType(package_name)
    package.__path__ = [str(RUNTIME.parent)]
    monkeypatch.setitem(sys.modules, package_name, package)
    monkeypatch.setitem(sys.modules, f"{package_name}.runtime", rt.package)
    monkeypatch.setitem(sys.modules, f"{package_name}.runtime.models", rt.models)
    monkeypatch.setitem(sys.modules, f"{package_name}.runtime.settings", rt.settings)
    name = f"{package_name}.configRepository"
    spec = importlib.util.spec_from_file_location(name, RUNTIME.parent / "configRepository.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@contextmanager
def forbid_legacy_runtime_imports(monkeypatch):
    """Reject old boundaries even when another test already cached a module."""
    forbidden = {
        "compat", "driver", "synthDrivers", "config", "synthDriverHandler",
        "logHandler", "languageHandler", "speech", "globalVars", "addonHandler",
        "gui", "nvwave", "winKernel", "api", "NVDA", "nvda",
    }

    def check(name):
        if forbidden.intersection(name.split(".")):
            raise AssertionError(f"Forbidden runtime dependency: {name}")

    original_import = builtins.__import__
    original_import_module = importlib.import_module

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        check(name)
        for item in fromlist or ():
            check(item)
        return original_import(name, globals, locals, fromlist, level)

    def guarded_import_module(name, package=None):
        check(name)
        return original_import_module(name, package)

    with monkeypatch.context() as guard:
        guard.setattr(builtins, "__import__", guarded_import)
        guard.setattr(importlib, "import_module", guarded_import_module)
        yield


class ContractCore:
    """Only the hardware/event source is fake; runtime ownership stays real."""

    supportsCancellationToken = True

    def __init__(self):
        self.open_count = self.close_count = self.cancel_count = 0
        self.spoken = []
        self.tokens = []
        self.entered = Event()
        self.complete_synchronously = True
        self.emit = None

    def speak(self, commands, cancellationToken):
        self.spoken.append((commands, self.voice, self.language,
                            self.rate, self.pitch, self.volume))
        self.tokens.append(cancellationToken)
        self.entered.set()
        if self.complete_synchronously:
            self.emit("INDEX", 7)
            self.emit("INDEX", 7)
            self.emit("DONE")
            self.emit("DONE")
            self.emit("INDEX", 8)

    def cancel(self):
        self.cancel_count += 1

    def pause(self, switch):
        pass


def assemble_adapter_contract(monkeypatch, adapter_kind):
    """Use the identical production Store, Session and scheduler for both ports.

    The caller installs the native import guard before calling this function
    and keeps it installed through worker/session teardown.
    """
    rt = load_runtime(monkeypatch, "worldvoice_contract_runtime")
    scheduler = load_scheduler(monkeypatch, rt)
    voices = tuple(rt.models.VoiceSpec(key, "Contract:" + key, key, language,
                                      "Contract", language)
                   for key, language in (("a", "en"), ("b", "zh_TW")))
    core = ContractCore()
    supported = frozenset({"rate", "pitch", "volume"})
    if adapter_kind == "native":
        class NativeAdapter:
            notification_source = core
            capabilities = rt.models.EngineCapabilities(supported, supports_cancellation_token=True)

            def open(self):
                core.open_count += 1

            def close(self):
                core.close_count += 1

            def list_voices(self):
                return voices

            def variants(self, key):
                return ()

            def apply(self, spec, snapshot):
                core.voice, core.language = spec.id, snapshot.language
                core.rate, core.pitch, core.volume = snapshot.rate, snapshot.pitch, snapshot.volume

            def speak(self, commands, token, *, context=None):
                core.speak(commands, cancellationToken=token)

            def finish_segment(self, context):
                pass

            def cancel(self):
                core.cancel()

            def pause(self, switch):
                core.pause(switch)

        adapter = NativeAdapter()
    elif adapter_kind == "legacy":
        # Supply a namespace only; never execute the NVDA addon entry point.
        name = "worldvoice_contract_legacy"
        package = ModuleType(name)
        package.__path__ = [str(RUNTIME.parent)]
        monkeypatch.setitem(sys.modules, name, package)
        for suffix, module in (("", rt.package), (".models", rt.models),
                               (".settings", rt.settings), (".session", rt.session)):
            monkeypatch.setitem(sys.modules, name + ".runtime" + suffix, module)
        for suffix in ("compat", "compat.engineAdapter"):
            monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
        legacy = importlib.import_module(name + ".compat.engineAdapter")

        class LegacyVoice:
            @classmethod
            def engineOn(cls):
                cls.core = core
                core.open_count += 1

            @classmethod
            def engineOff(cls):
                core.close_count += 1
                cls.core = None

            @classmethod
            def supportedSettings(cls):
                return supported

            @classmethod
            def voices(cls):
                return [vars(spec) for spec in voices]

            def applyEngineSettings(self, target, snapshot):
                target.language = snapshot.language

            variants = ()

        cached = {spec.name: LegacyVoice() for spec in voices}
        adapter = legacy.LegacyEngineAdapter(LegacyVoice, cached.__getitem__)
    else:
        raise ValueError(adapter_kind)
    repo = MemoryRepository()
    store = rt.settings.VoiceSettingsStore(repo)
    session = rt.session.EngineSession(adapter, store)
    session.open()
    for spec in session.list_voices():
        store.ensure(spec)
    output = RecordingOutput()
    tasks = scheduler.TaskManager(output)
    core.emit = lambda kind, index=None: tasks.on_event(rt.models.PlaybackEvent(
        rt.models.EventKind[kind], session.source_id, index))
    return SimpleNamespace(rt=rt, scheduler=scheduler, core=core, repo=repo,
                           store=store, session=session, tasks=tasks, output=output)


def load_index_support(monkeypatch, rt, package_name):
    """Load real ledger/commands into an isolated addon namespace."""
    package = sys.modules.get(package_name)
    if package is None:
        package = ModuleType(package_name)
        package.__path__ = [str(RUNTIME.parent)]
        monkeypatch.setitem(sys.modules, package_name, package)
    monkeypatch.setitem(sys.modules, package_name + ".runtime", rt.package)
    monkeypatch.setitem(sys.modules, package_name + ".runtime.models", rt.models)
    for suffix in ("indexLedger", "_speechcommand", "compat.indexCodec"):
        monkeypatch.delitem(sys.modules, package_name + "." + suffix, raising=False)
    return SimpleNamespace(
        package=package_name,
        ledger=importlib.import_module(package_name + ".indexLedger"),
        commands=importlib.import_module(package_name + "._speechcommand"),
    )
