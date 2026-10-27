"""Load the WorldVoice driver class and voice manager under alias packages, with the stubs they need.

The two voice manager loaders differ on purpose: each uses its own alias package and config stub,
and the tests built on each expect exactly that setup.
"""

import sys
import types

from addon_loader import WORLDVOICE, alias_package, load_definitions, load_source
from nvda_stubs import worldvoice_conf
from voice_binding_harness import install_binding


class EventStub:
	"""Stands in for an NVDA extensionPoints.Action: notify calls every registered handler."""

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


def load_synth_class(environment):
	"""Execute the real driver class with NVDA's unavailable services replaced."""
	return load_definitions(WORLDVOICE / "__init__.py", ["SynthDriver"], environment)["SynthDriver"]


def _manager_conf():
	"""Engine consistency off, so tests choose each voice's engine themselves."""
	return worldvoice_conf(
		autoLanguageSwitching={
			"keepMainLocaleEngineConsistent": False,
			"keepMainLocaleParameterConsistent": False,
		},
	)


def load_voice_manager(monkeypatch):
	"""voices.manager under lifecycle_test_worldvoice, with stub config, language, log and synth modules."""
	package_name = "lifecycle_test_worldvoice"
	for name in tuple(sys.modules):
		if name.startswith(package_name + "."):
			monkeypatch.delitem(sys.modules, name)
	alias_package(monkeypatch, package_name, WORLDVOICE)
	config = types.SimpleNamespace(conf=_manager_conf())
	monkeypatch.setitem(sys.modules, "config", config)
	monkeypatch.setitem(sys.modules, "languageHandler", types.SimpleNamespace(getLanguage=lambda: "en"))
	monkeypatch.setitem(
		sys.modules,
		"logHandler",
		types.SimpleNamespace(
			log=types.SimpleNamespace(
				debug=lambda *args: None,
				error=lambda *args, **kwargs: None,
			),
		),
	)
	monkeypatch.setitem(
		sys.modules,
		"synthDriverHandler",
		types.SimpleNamespace(
			VoiceInfo=lambda id, displayName, language: types.SimpleNamespace(
				id=id,
				displayName=displayName,
				language=language,
			),
		),
	)
	return load_source(monkeypatch, f"{package_name}.voices.manager", WORLDVOICE / "voices/manager.py")


def init_policies(manager):
	"""Give a bare manager the policies the composition root would inject."""
	config = sys.modules["config"]
	manager._init_policies(lambda: config.conf, lambda: "en")


def load_f4_voice_manager(monkeypatch):
	"""voices.manager under f4_test_worldvoice; its stubs also have getLanguageDescription and getSynth."""
	package_name = "f4_test_worldvoice"
	for name in tuple(sys.modules):
		if name.startswith(package_name + "."):
			monkeypatch.delitem(sys.modules, name)
	alias_package(monkeypatch, package_name, WORLDVOICE)
	config = types.SimpleNamespace(conf=_manager_conf())
	monkeypatch.setitem(sys.modules, "config", config)
	monkeypatch.setitem(
		sys.modules,
		"languageHandler",
		types.SimpleNamespace(
			getLanguage=lambda: "en",
			getLanguageDescription=lambda language: language,
		),
	)
	log = types.SimpleNamespace(
		debug=lambda *args: None,
		error=lambda *args, **kwargs: None,
	)
	monkeypatch.setitem(sys.modules, "logHandler", types.SimpleNamespace(log=log))
	monkeypatch.setitem(
		sys.modules,
		"synthDriverHandler",
		types.SimpleNamespace(
			VoiceInfo=lambda id, displayName, language: types.SimpleNamespace(
				id=id,
				displayName=displayName,
				language=language,
			),
			getSynth=lambda: types.SimpleNamespace(name="WorldVoice"),
		),
	)
	return load_source(monkeypatch, f"{package_name}.voices.manager", WORLDVOICE / "voices/manager.py")


def create_f4_voices(monkeypatch, config):
	"""Two driver voices, A:a (en) and B:b (fr), bound to one settings store under f4_test_worldvoice."""
	module = load_source(monkeypatch, "f4_test_worldvoice.driver", WORLDVOICE / "driver/__init__.py")
	voice = install_binding(module, config)
	return voice("a", "A:a", "en"), voice("b", "B:b", "fr")


class RecordingCore:
	"""An engine core that records each voice parameter written to it and each text spoken."""

	def __init__(self):
		self.writes = []
		self.spoken = []
		self.supportedSettings = [
			types.SimpleNamespace(id=name) for name in ("rate", "pitch", "volume", "inflection", "rateBoost")
		]

	def __setattr__(self, name, value):
		if name in ("voice", "rate", "pitch", "volume", "inflection", "rateBoost"):
			self.writes.append((name, value))
		object.__setattr__(self, name, value)

	def speak(self, text):
		self.spoken.append(text)

	def cancel(self):
		pass


# Named views of WorldVoice internals that tests check but no public API exposes (which
# engines the manager holds, what the event bridge still binds, shutdown order); each
# private name is read here only. They read without a lock, as the tests did.


def engine_resources(manager):
	"""The engine resources the voice manager opened, by engine name, in open order."""
	return dict(manager._resources)


def voice_binding(voice):
	"""The binding a voice instance plays through."""
	return voice._binding


def consistency_roles(voice_consistency):
	"""The role repository the voice consistency policy reads."""
	return voice_consistency._roles


def bridge_bindings(bridge):
	"""The sources the NVDA event bridge still binds, by id."""
	return dict(bridge._sources)


def bridge_binding(bridge, source):
	"""The event bridge's binding for ``source``, or None."""
	return bridge._sources.get(id(source))


def bridge_closed(bridge):
	"""Whether the NVDA event bridge has been closed."""
	return bridge._closed


def ledger_closed(ledger):
	"""Whether the index ledger has been closed."""
	return ledger._closed


def synth_terminated(synth):
	"""Whether the WorldVoice synth driver has started terminating."""
	return synth._terminated


def port_adapter(port):
	"""The engine adapter behind a playback port."""
	return port._adapter


def voice_manager(synth):
	"""The voice manager the WorldVoice synth driver speaks through."""
	return synth._voiceManager


def chosen_voice(synth):
	"""The voice the WorldVoice synth driver recorded as chosen, or None."""
	return synth._voice


def voice_instances(manager):
	"""The voice instances the voice manager has created, by voice name."""
	return dict(manager._instance_cache)


def settings_baseline(voice, setting):
	"""The saved (baseline) value of a voice setting, which rollback restores."""
	return voice._state.baseline(setting)
