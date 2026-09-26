"""Load the pure runtime without executing the WorldVoice/NVDA entry point."""

import importlib.util
from pathlib import Path
import sys
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
    return SimpleNamespace(package=package, models=models, settings=settings)


@pytest.fixture
def rt(monkeypatch):
    return load_runtime(monkeypatch)


def make_spec(key="Fake:a", language="en"):
    engine, voice_id = key.split(":", 1)
    return sys.modules[f"{PACKAGE}.models"].VoiceSpec(
        voice_id, key, f"Voice {voice_id}", language, engine, language,
    )
