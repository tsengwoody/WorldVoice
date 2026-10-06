"""The Unicode detection panel's script choices and what it saves."""

from types import SimpleNamespace

import pytest
from addon_loader import ADDON, load_definitions
from detector_harness import load_language_detection

PANEL = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"


class Control:
	def __init__(self, label=None, choices=None):
		self.label, self.choices = label, list(choices or [])
		self.selection, self.enabled, self.value = None, True, None

	def Select(self, index):
		self.selection = index

	def GetCurrentSelection(self):
		return self.selection

	def IsEnabled(self):
		return self.enabled

	def Disable(self):
		self.enabled = False

	def SetValue(self, value):
		self.value = value

	def GetValue(self):
		return self.value


class Synth:
	def __init__(self, manager):
		object.__setattr__(self, "events", [])
		object.__setattr__(self, "name", "WorldVoice")
		object.__setattr__(self, "voice_manager", manager)
		object.__setattr__(self, "uwv", True)

	def __setattr__(self, name, value):
		self.events.append(("set", name))
		object.__setattr__(self, name, value)

	def refresh_language_detection(self):
		self.events.append(("refresh",))


class NoConfig:
	"""The panel reaches the detection keys only through the settings service."""

	def __getitem__(self, key):
		raise AssertionError(f"the panel read config[{key!r}] directly")


def build(env, languages, stored):
	switching = {
		"ignoreNumbersInLanguageDetection": True,
		"latinCharactersLanguage": "en",
		"CJKCharactersLanguage": "zh",
		"arabicCharactersLanguage": "ar",
		"DetectLanguageTiming": "after",
		**stored,
	}
	conf = {"WorldVoice": {"autoLanguageSwitching": switching}}
	service = env.settings_module.DetectionSettingsService(lambda: conf)
	notified = []
	service.subscribe(lambda settings, changed: notified.append(changed))
	added = []

	class Helper:
		def __init__(self, *args, **kwargs):
			pass

		def addLabeledControl(self, label, cls, choices=None):
			control = Control(label, choices)
			added.append(control)
			return control

		def addItem(self, item):
			added.append(item)
			return item

	manager = SimpleNamespace(
		languages=languages,
		localesToNamesMap={locale: f"<{locale}>" for locale in languages},
	)
	synth = Synth(manager)
	environment = {
		"SettingsPanel": object,
		"_": lambda text: text,
		"wx": SimpleNamespace(Choice=object, CheckBox=lambda parent, label: Control(label)),
		"guiHelper": SimpleNamespace(BoxSizerHelper=Helper),
		"config": SimpleNamespace(conf=NoConfig()),
		"getSynth": lambda: synth,
		"worldvoice_synth": lambda: synth,
		"languageDetection": env.module,
		"detection_settings": service,
	}
	load_definitions(PANEL, ["UnicodeDetectionSettingsPanel"], environment)
	panel = object.__new__(environment["UnicodeDetectionSettingsPanel"])
	panel.makeSettings(SimpleNamespace())
	return SimpleNamespace(panel=panel, added=added, switching=switching, synth=synth, notified=notified)


LANGUAGES = ["en", "fr", "zh", "ja", "ar", "en_US"]


def test_controls_choices_and_selections(env):
	built = build(env, LANGUAGES, {"latinCharactersLanguage": "fr", "CJKCharactersLanguage": "ja"})
	labels = [control.label for control in built.added]
	assert labels == [
		"Ignore numbers when detecting text language",
		"Language assumed for latin characters:",
		"Language assumed for CJK characters:",
		"Language assumed for arabic characters:",
		"Language detection timing:",
	]
	latin, cjk, arabic = built.added[1:4]
	assert latin.choices == ["<en>", "<fr>"] and latin.selection == 1
	assert cjk.choices == ["<ja>", "<zh>"] and cjk.selection == 0
	assert arabic.choices == ["<ar>"] and arabic.selection == 0
	assert built.added[0].value is True


def test_save_writes_each_enabled_choice(env):
	built = build(env, LANGUAGES, {"latinCharactersLanguage": "fr", "CJKCharactersLanguage": "ja"})
	built.added[1].Select(0)
	built.added[2].Select(1)
	built.added[0].SetValue(False)
	built.panel.onSave()
	assert (
		built.switching["latinCharactersLanguage"],
		built.switching["CJKCharactersLanguage"],
		built.switching["arabicCharactersLanguage"],
		built.switching["ignoreNumbersInLanguageDetection"],
	) == (
		"en",
		"zh",
		"ar",
		False,
	)


def test_stored_language_not_offered_selects_the_first(env):
	built = build(env, LANGUAGES, {"latinCharactersLanguage": "xx"})
	assert built.added[1].selection == 0


def test_script_without_candidates_is_disabled_and_not_saved(env):
	built = build(env, ["en", "zh"], {"arabicCharactersLanguage": "fa"})
	arabic = built.added[3]
	assert arabic.choices == [] and arabic.enabled is False
	built.panel.onSave()
	assert built.switching["arabicCharactersLanguage"] == "fa"


@pytest.mark.parametrize("timing,timing_changed", [("before", True), ("after", False)])
def test_saving_reports_a_timing_change_to_subscribers_not_to_the_synth(env, timing, timing_changed):
	built = build(env, LANGUAGES, {})
	built.added[4].Select(["before", "after"].index(timing))
	built.synth.events.clear()
	built.panel.onSave()
	assert built.switching["DetectLanguageTiming"] == timing
	assert [("timing" in changed) for changed in built.notified] == ([True] if timing_changed else [])
	assert built.synth.events == []


def test_saving_unchanged_choices_notifies_nobody(env):
	built = build(env, LANGUAGES, {"latinCharactersLanguage": "fr", "CJKCharactersLanguage": "ja"})
	built.panel.onSave()
	assert built.notified == []


@pytest.fixture
def env(stub_modules, monkeypatch):
	return load_language_detection(stub_modules, monkeypatch)
