"""Load the pure runtime without executing the WorldVoice/NVDA entry point."""

import importlib.util
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace

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

    def speak(self, commands, token):
        self.spoken.append((commands, token))
        if self.before_speak is not None:
            self.before_speak(commands, token)

    def cancel(self):
        self.cancel_count += 1
        self.cancel_entered.set()

    def pause(self, switch):
        self.paused.append(switch)


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
