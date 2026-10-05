import ast
from pathlib import Path
from dataclasses import replace
import types

import pytest

from test_f4_engine_session import module, snap, rt
from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs

DRIVERS = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/driver"


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_wrapper_settings_are_pending_until_activation(monkeypatch, engine, snap):
	harness = load_real_driver_with_native_stubs(monkeypatch, engine)
	adapter = object.__new__(harness.module.Voice)
	writes = []
	# VE queues inner settings on its BgThread; this fake runs them at once.
	core = types.SimpleNamespace(waitfactor=0, _bgQueue=types.SimpleNamespace(put=lambda task: task()))
	core.getVoiceInstance = lambda voice_id: f"native:{voice_id}"
	core.getParameter = lambda instance, parameter, type_: "plain"
	core.availableVariants = {"plain": object(), "bright": object()}
	adapter.core = core  # the harness Voice base is a plain object
	monkeypatch.setattr(harness.module, "TtsSetParamList",
		lambda instance, pair: lambda: writes.append((instance, pair[1])))
	adapter.id = "a"
	adapter.variant = "bright"
	adapter.waitfactor = 4
	assert writes == []
	assert core.waitfactor == 0

	adapter.applyEngineSettings(core, replace(snap("a", 1), variant="bright", waitfactor=4))
	assert writes == [("native:a", "bright")]
	assert core.waitfactor == 4
	adapter.applyEngineSettings(core, replace(snap("a", 2), variant="default", waitfactor=2))
	assert writes[-1] == ("native:a", "plain")
	assert core.waitfactor == 2
	with pytest.raises(ValueError, match="Unavailable variant: missing"):
		adapter.applyEngineSettings(core, replace(snap("a", 3), variant="missing"))
	assert writes[-1] == ("native:a", "plain")


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_variant_default_is_recaptured_for_rebuilt_core(monkeypatch, engine, snap):
	harness = load_real_driver_with_native_stubs(monkeypatch, engine)
	adapter = object.__new__(harness.module.Voice)
	writes = []
	monkeypatch.setattr(harness.module, "TtsSetParamList",
		lambda instance, pair: lambda: writes.append((instance, pair[1])))
	for native_default in ("plain", "warm"):
		core = types.SimpleNamespace(
			waitfactor=0, availableVariants={"plain": object(), "warm": object()},
			_bgQueue=types.SimpleNamespace(put=lambda task: task()),
			getVoiceInstance=lambda voice_id: f"native:{voice_id}",
			getParameter=lambda instance, parameter, type_: native_default,
		)
		adapter.applyEngineSettings(core, snap("a", 0))
	assert writes == [("native:a", "plain"), ("native:a", "warm")]


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_variant_metadata_read_preserves_playback_state(monkeypatch, engine):
	harness = load_real_driver_with_native_stubs(monkeypatch, engine)
	adapter = object.__new__(harness.module.Voice)
	core = types.SimpleNamespace(voice="a", rate=71, pitch=63, waitfactor=2)
	core.getVoiceInstance = lambda voice_id: f"native:{voice_id}"
	core.getParameter = lambda instance, parameter, type_: "en"
	adapter.core = core  # the harness Voice base is a plain object
	monkeypatch.setattr(harness.module.ve2 if engine == "VE" else harness.module.ttsapi,
		"getSpeechDBList", lambda language, voice_id: ["plain", "bright"])
	adapter.id = "b"
	assert [variant["id"] for variant in adapter.variants] == ["plain", "bright"]
	assert (core.voice, core.rate, core.pitch, core.waitfactor) == ("a", 71, 63, 2)


def test_onecore_language_is_applied_only_on_activation():
	path = DRIVERS / "OneCore/__init__.py"
	tree = ast.parse(path.read_text(encoding="utf-8"))
	voice_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Voice")
	class BaseVoice:
		def __init__(self, id, name, taskManager, language=None):
			self.language = language
	core = types.SimpleNamespace(language="original")
	environment = {"Voice": BaseVoice, "SynthDriver": object, "DrainProfile": lambda **kwargs: None}
	exec(compile(ast.Module(body=[voice_class], type_ignores=[]), str(path), "exec"), environment)
	environment["Voice"].core = core
	adapter = environment["Voice"]("a", "OneCore:a", None, language="en")
	assert core.language == "original"
	adapter.applyEngineSettings(core, types.SimpleNamespace(language="fr"))
	assert core.language == "fr"


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_voice_metadata_names_the_declaring_engine(monkeypatch, engine):
	harness = load_real_driver_with_native_stubs(monkeypatch, engine)
	voice_class = harness.module.Voice
	monkeypatch.setattr(voice_class, "ready", classmethod(lambda cls: True), raising=False)
	monkeypatch.setattr(voice_class, "engine", "Renamed")
	monkeypatch.setattr(harness.module, "languageHandler",
		types.SimpleNamespace(getLanguageDescription=lambda locale: "English"))
	# The harness Voice base is a plain object; the base voices() just maps this hook.
	metadata = voice_class.voiceInfoToMetadata(types.SimpleNamespace(id="x", language="en", displayName="x"))
	assert metadata["engine"] == "Renamed"


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_voice_metadata_keeps_vocalizer_quirks(monkeypatch, engine):
	harness = load_real_driver_with_native_stubs(monkeypatch, engine)
	voice_class = harness.module.Voice
	monkeypatch.setattr(voice_class, "ready", classmethod(lambda cls: True), raising=False)
	language = types.SimpleNamespace(getLanguageDescription=lambda locale: "")
	monkeypatch.setattr(harness.module, "languageHandler", language, raising=False)
	metadata = voice_class.voiceInfoToMetadata(
		types.SimpleNamespace(id="x", language="en", displayName="Display - b'English'"),
	)
	assert metadata["langDescription"] == "English"
	assert metadata["description"] == f"x - English [{voice_class.engine}]"
	assert metadata["name"] == f"{voice_class.engine}:x"
