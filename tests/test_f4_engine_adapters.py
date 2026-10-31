import types
from dataclasses import replace

import pytest
from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs


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
	monkeypatch.setattr(
		harness.module,
		"TtsSetParamList",
		lambda instance, pair: lambda: writes.append((instance, pair[1])),
	)
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
	monkeypatch.setattr(
		harness.module,
		"TtsSetParamList",
		lambda instance, pair: lambda: writes.append((instance, pair[1])),
	)
	for native_default in ("plain", "warm"):
		core = types.SimpleNamespace(
			waitfactor=0,
			availableVariants={"plain": object(), "warm": object()},
			_bgQueue=types.SimpleNamespace(put=lambda task: task()),
			getVoiceInstance=lambda voice_id: f"native:{voice_id}",
			getParameter=lambda instance, parameter, type_, default=native_default: default,
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
	monkeypatch.setattr(
		harness.module.ve2 if engine == "VE" else harness.module.ttsapi,
		"getSpeechDBList",
		lambda language, voice_id: ["plain", "bright"],
	)
	adapter.id = "b"
	assert [variant["id"] for variant in adapter.variants] == ["plain", "bright"]
	assert (core.voice, core.rate, core.pitch, core.waitfactor) == ("a", 71, 63, 2)


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_voice_metadata_names_the_declaring_engine(monkeypatch, engine):
	harness = load_real_driver_with_native_stubs(monkeypatch, engine)
	voice_class = harness.module.Voice
	monkeypatch.setattr(voice_class, "ready", classmethod(lambda cls: True), raising=False)
	monkeypatch.setattr(voice_class, "engine", "Renamed")
	monkeypatch.setattr(
		harness.module,
		"languageHandler",
		types.SimpleNamespace(getLanguageDescription=lambda locale: "English"),
	)
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


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_metadata_without_a_language_description_uses_the_locale(monkeypatch, engine):
	harness = load_real_driver_with_native_stubs(monkeypatch, engine)
	voice_class = harness.module.Voice
	language = types.SimpleNamespace(getLanguageDescription=lambda locale: "")
	monkeypatch.setattr(harness.module, "languageHandler", language, raising=False)
	metadata = voice_class.voiceInfoToMetadata(
		types.SimpleNamespace(id="x", language="xx_YY", displayName="Plain"),
	)
	assert metadata["langDescription"] == "xx_YY"
	assert metadata["description"] == f"x - xx_YY [{voice_class.engine}]"


def test_cerence_variants_are_empty_without_speech_databases(monkeypatch):
	harness = load_real_driver_with_native_stubs(monkeypatch, "Cerence")
	voice = object.__new__(harness.module.Voice)
	voice.id = "x"
	voice.core = types.SimpleNamespace(
		getVoiceInstance=lambda voice_id: f"native:{voice_id}",
		getParameter=lambda instance, parameter, type_: "enu",
	)

	def no_databases(language, voice_id):
		raise OSError("no speech databases")

	monkeypatch.setattr(harness.module.ttsapi, "getSpeechDBList", no_databases)
	# The voice settings panel lists no variant instead of failing to open.
	assert voice.variants == []


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
@pytest.mark.parametrize(
	"raw,expected",
	[
		("b'bengali'", "bengali"),
		("b'b'", "b"),
		("plain", "plain"),
		("b'", "b'"),
	],
)
def test_bytes_repr_loses_only_its_wrapper(monkeypatch, engine, raw, expected):
	harness = load_real_driver_with_native_stubs(monkeypatch, engine)
	assert harness.module._stripBytesRepr(raw) == expected
