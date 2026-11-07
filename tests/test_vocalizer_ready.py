"""VE and Cerence are ready only when the DLLs their inner initialize loads are on disk.

Spec 2026-11-07-hide-unavailable-engines §4.2 (D1–D4): ready() checks the files only, at the paths
the inner driver derives, so the Speech Engine panel can hide an engine that cannot load.
"""

import ctypes
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from addon_loader import WORLDVOICE, load_source
from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs

FILES = {"VE": ["msvcr110.dll", "ve.dll", "vplatform.dll"], "Cerence": ["ve.dll", "vplatform.dll"]}
NATIVE = {"VE": "ve2", "Cerence": "ttsapi"}
# What this test machine gives the inner initialize: PROCESSOR_ARCHITECTURE for VE, 64-bit Python.
LIB = {"VE": "AMD64", "Cerence": "x64"}


def _inner_file(name):
	return WORLDVOICE / "driver" / name / "driver" / NATIVE[name] / "__init__.py"


def _load(monkeypatch, name):
	monkeypatch.setenv("PROCESSOR_ARCHITECTURE", "AMD64")
	monkeypatch.setattr(sys, "maxsize", 2**63 - 1)
	harness = load_real_driver_with_native_stubs(monkeypatch, name)
	logged = []
	monkeypatch.setattr(
		harness.module,
		"log",
		SimpleNamespace(
			**{
				level: lambda message, *args, level=level: logged.append((level, message % args))
				for level in ("debug", "info", "warning", "error", "debugWarning")
			},
		),
	)
	# Nine folders above the inner module, as its initialize derives NVDA's config directory.
	workspace = Path(_inner_file(name)).parents[8] / "WorldVoice-workspace" / name
	paths = [str(workspace / "lib" / LIB[name] / file) for file in FILES[name]]
	return SimpleNamespace(name=name, harness=harness, module=harness.module, logged=logged, paths=paths)


@pytest.fixture(params=["VE", "Cerence"])
def engine(request, monkeypatch):
	return _load(monkeypatch, request.param)


def _present(monkeypatch, paths):
	present = set(paths)
	monkeypatch.setattr(os.path, "isfile", lambda path: path in present)


def test_ready_with_every_file(engine, monkeypatch):
	assert engine.module._nativeFiles() == engine.paths
	_present(monkeypatch, engine.paths)
	assert engine.module.Voice.ready() is True
	assert engine.logged == []


@pytest.mark.parametrize(
	("name", "missing"),
	[
		("VE", "msvcr110.dll"),
		("VE", "ve.dll"),
		("VE", "vplatform.dll"),
		("Cerence", "ve.dll"),
		("Cerence", "vplatform.dll"),
	],
)
def test_ready_names_each_missing_file(monkeypatch, name, missing):
	engine = _load(monkeypatch, name)
	(path,) = [path for path in engine.paths if path.endswith(os.sep + missing)]
	_present(monkeypatch, [other for other in engine.paths if other != path])
	assert engine.module.Voice.ready() is False
	assert engine.logged == [("info", f"WorldVoice {name} engine is unavailable: missing {path}")]


def test_ready_without_the_workspace_names_every_file(engine, monkeypatch):
	_present(monkeypatch, [])
	assert engine.module.Voice.ready() is False
	assert engine.logged == [
		("info", f"WorldVoice {engine.name} engine is unavailable: missing " + ", ".join(engine.paths)),
	]


def test_ready_never_loads_a_library(engine, monkeypatch):
	def load_library(*args, **kwargs):
		raise AssertionError(f"ready() loaded {args}")

	# Every way ctypes opens a library: the loaders, the classes, and the primitive they share.
	for loader in ("cdll", "pydll", "windll", "oledll"):
		if hasattr(ctypes, loader):
			monkeypatch.setattr(getattr(ctypes, loader), "LoadLibrary", load_library)
	for name in ("CDLL", "PyDLL", "WinDLL", "OleDLL", "_dlopen"):
		monkeypatch.setattr(ctypes, name, load_library, raising=False)
	for present in (engine.paths, []):
		_present(monkeypatch, present)
		engine.module.Voice.ready()


def test_ve_ready_without_processor_architecture_raises_like_initialize(monkeypatch):
	engine = _load(monkeypatch, "VE")
	monkeypatch.delenv("PROCESSOR_ARCHITECTURE")
	# The registry's ready check logs the error and hides the engine (spec D3).
	with pytest.raises(KeyError):
		engine.module.Voice.ready()


@pytest.mark.parametrize(
	("name", "maxsize", "lib"),
	[("VE", 2**63 - 1, "AMD64"), ("Cerence", 2**63 - 1, "x64"), ("Cerence", 2**31 - 1, "x32")],
)
def test_ready_checks_exactly_what_initialize_loads(monkeypatch, name, maxsize, lib):
	engine = _load(monkeypatch, name)
	# The harness replaced initialize; load the real inner module again over it.
	inner = load_source(monkeypatch, engine.harness.native.__name__, _inner_file(name))
	loaded = []
	monkeypatch.setattr(
		inner,
		"cdll",
		SimpleNamespace(LoadLibrary=lambda path: loaded.append(path) or MagicMock()),
	)
	monkeypatch.setattr(sys, "maxsize", maxsize)

	inner.initialize([])

	assert loaded == engine.module._nativeFiles()
	assert all(os.path.basename(os.path.dirname(path)) == lib for path in loaded)
