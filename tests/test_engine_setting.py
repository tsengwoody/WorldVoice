"""The synth's speech engine: it follows the voice and filters availableVoices (spec §3.4)."""

from collections import OrderedDict
from types import SimpleNamespace

import pytest
from nvda_stubs import worldvoice_conf
from pipeline_harness import auto_properties, load_synth

# engine -> (voice name, voice text, language), in table order.
VOICES = {
	"A": [("A:a1", "One - English [A]", "en_US"), ("A:a2", "Two - German [A]", "de_DE")],
	"B": [("B:b1", "Bee - French [B]", "fr_FR")],
}


class Manager:
	"""The VoiceManager interface the synth reads, over VOICES."""

	def __init__(self):
		self._infos = {
			engine: OrderedDict(
				(name, SimpleNamespace(id=name, displayName=text, language=language))
				for name, text, language in voices
			)
			for engine, voices in VOICES.items()
		}
		self._default = "A:a1"
		self.roles = {}
		self.picks = []
		self.cancels = 0

	@property
	def engines(self):
		return tuple(self._infos)

	def engine_of(self, voice_name):
		(engine,) = [engine for engine, infos in self._infos.items() if voice_name in infos]
		return engine

	def voice_infos_for_engine(self, engine):
		return self._infos[engine]

	@property
	def voice_infos(self):
		return OrderedDict(item for infos in self._infos.values() for item in infos.items())

	def voice_name_for_engine(self, engine, language):
		self.picks.append((engine, language))
		return next(iter(self._infos[engine]))

	@property
	def default_voice_name(self):
		return self._default

	@default_voice_name.setter
	def default_voice_name(self, name):
		if name not in self.voice_infos:
			raise LookupError(name)
		self._default = name

	def get_voice_name_for_language(self, language):
		return self.roles.get(language, self._default)

	def cancel(self):
		self.cancels += 1


@pytest.fixture
def env(monkeypatch):
	synth_class, _settings = load_synth(monkeypatch, worldvoice_conf())
	namespace = synth_class._get_voice.__globals__
	language = ["en"]
	changes = []

	def changeVoice(synth, voice):
		# NVDA's synthDriverHandler.changeVoice sets the voice, then rebuilds the ring and dictionary.
		changes.append((synth, voice))
		synth.voice = voice

	monkeypatch.setitem(namespace, "OrderedDict", OrderedDict)
	monkeypatch.setitem(
		namespace,
		"StringParameterInfo",
		lambda id, name: SimpleNamespace(id=id, displayName=name),
	)
	monkeypatch.setitem(namespace, "languageHandler", SimpleNamespace(getLanguage=lambda: language[0]))
	monkeypatch.setitem(namespace, "changeVoice", changeVoice)
	auto_properties(
		monkeypatch,
		synth_class,
		"voice",
		"engine",
		"availableEngines",
		"availableVoices",
		"availableLanguages",
	)
	synth = object.__new__(synth_class)
	synth._voiceManager = manager = Manager()
	synth._voice = "A:a1"
	return SimpleNamespace(synth=synth, manager=manager, changes=changes, language=language)


def test_available_engines_lists_the_catalog_engines(env):
	assert [(key, info.id, info.displayName) for key, info in env.synth.availableEngines.items()] == [
		("A", "A", "A"),
		("B", "B", "B"),
	]


def test_engine_follows_the_voice(env):
	assert env.synth.engine == "A"
	env.synth.voice = "B:b1"
	assert env.synth.engine == "B"


def test_available_voices_is_the_current_engines_list_and_follows_a_voice_change(env):
	synth = env.synth
	assert list(synth.availableVoices) == ["A:a1", "A:a2"]
	synth.voice = "B:b1"
	# NVDA's own property would keep the first list forever (synthDriverHandler.py:274-277).
	assert list(synth.availableVoices) == ["B:b1"]
	assert synth.availableVoices["B:b1"].displayName == "Bee - French [B]"
	assert list(synth._getAvailableVoices()) == ["B:b1"]
	assert "_availableVoices" not in vars(synth)


def test_available_languages_lists_every_engines_languages(env):
	assert env.synth.availableLanguages == {"en_US", "de_DE", "fr_FR"}


def test_choosing_another_engine_changes_the_voice_through_change_voice(env):
	env.language[0] = "de"
	env.synth.engine = "B"
	assert env.changes == [(env.synth, "B:b1")]
	assert env.manager.picks == [("B", "de")]
	assert env.synth.voice == "B:b1"
	# NVDA's panel cancels speech; the setter never stops an engine.
	assert env.manager.cancels == 0


def test_choosing_the_current_engine_changes_nothing(env):
	env.synth.voice = "A:a2"
	env.synth.engine = "A"
	assert env.changes == []
	assert env.manager.picks == []
	assert env.synth.voice == "A:a2"


def test_choosing_an_unknown_engine_raises_and_keeps_the_voice(env):
	with pytest.raises(LookupError):
		env.synth.engine = "C"
	assert env.changes == []
	assert env.manager.picks == []
	assert env.synth.voice == "A:a1"


def test_before_load_settings_the_engine_follows_the_role_voice(env):
	# Before NVDA loads the saved voice, the voice is the role voice of the interface language, which
	# may belong to another engine than the default voice (keep-engine-consistent off).
	env.synth._voice = None
	env.manager.roles["fr"] = "B:b1"
	env.language[0] = "fr"
	assert env.synth.voice == "B:b1"
	assert env.synth.engine == "B"
	assert env.synth.availableVoices[env.synth.voice].language == "fr_FR"
