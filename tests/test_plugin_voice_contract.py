"""External engine plugins subclass driver.Voice the way ref/Neural does; that must keep working."""

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from addon_loader import REF

ROOT = Path(__file__).resolve().parents[1]
# The class attributes the base Voice offers plugins.
PLUGIN_VOICE_ATTRIBUTES = {"core", "engine", "synthDriverClass", "extraCapabilities", "drainProfile"}


class FakeCore:
	supportedSettings = tuple(SimpleNamespace(id=name) for name in ("rate", "pitch", "volume"))

	def __init__(self):
		self.availableVoices = {
			"v1": SimpleNamespace(id="v1", displayName="Neural One - English", language="en"),
		}
		self.terminated = False

	def speak(self, commands):
		pass

	def cancel(self):
		pass

	def pause(self, switch):
		pass

	def terminate(self):
		self.terminated = True


def neural_voice(base):
	class Voice(base):
		core = None
		engine = "Neural"
		synthDriverClass = FakeCore

	return Voice


def test_neural_style_plugin_runs_through_the_manager(composition):
	Voice = neural_voice(composition.driver.Voice)
	manager = composition.create(engine_classes={"Neural": Voice})
	assert [spec.name for spec in manager.table] == ["Neural:v1"]
	voice = manager.get_voice_instance("Neural:v1")
	assert voice.core is None  # the plugin's class attribute shadows the facade property
	voice.updateSettings(rate=61, pitch=42, volume=73)
	session = manager.resolve_playback("Neural:v1")
	assert session.activate("Neural:v1") is True
	core = manager._resources["Neural"].adapter.core
	assert (core.voice, core.rate, core.pitch, core.volume) == ("v1", 61, 42, 73)
	assert manager.get_voice_variants("Neural:v1") == ()
	manager.terminate(commit=False)
	assert core.terminated


def test_plugin_attributes_exist_on_the_base_voice(composition):
	base = composition.driver.Voice
	for name in PLUGIN_VOICE_ATTRIBUTES - {"core"}:
		assert hasattr(base, name), name
	assert isinstance(inspect.getattr_static(base, "core"), property)


def test_reference_neural_plugin_uses_only_plugin_attributes():
	path = REF / "Neural/Neural/__init__.py"
	if not path.is_file():
		pytest.skip("ref/Neural is not checked out")
	tree = ast.parse(path.read_text(encoding="utf-8"))
	aliases = {
		alias.asname or alias.name
		for node in tree.body
		if isinstance(node, ast.ImportFrom) and node.module == "synthDrivers.WorldVoice.driver"
		for alias in node.names
		if alias.name == "Voice"
	}
	(voice,) = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Voice"]
	bases = {base.id for base in voice.bases}
	assert bases and bases <= aliases
	assigned = set()
	for statement in voice.body:
		assert isinstance(statement, ast.Assign), ast.dump(statement)
		assigned |= {target.id for target in statement.targets}
	assert assigned <= PLUGIN_VOICE_ATTRIBUTES


def test_base_voice_lists_the_core_voices(composition):
	Voice = neural_voice(composition.driver.Voice)
	assert Voice.voices(None) == []
	assert Voice.voices(SimpleNamespace()) == []
	assert [(meta["name"], meta["language"]) for meta in Voice.voices(FakeCore())] == [("Neural:v1", "en")]


def test_listing_voices_trusts_the_ready_check_discovery_made(composition):
	class Voice(neural_voice(composition.driver.Voice)):
		@classmethod
		def ready(cls):
			raise AssertionError("discovery already asked")

	assert [meta["name"] for meta in Voice.voices(FakeCore())] == ["Neural:v1"]
