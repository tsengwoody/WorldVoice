"""The Unicode detection panel's script choices and what it saves."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from detector_harness import load_language_detection

PANEL = Path(__file__).resolve().parents[1] / "addon/globalPlugins/WorldVoice/speechSettingsDialog.py"


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

	manager = SimpleNamespace(languages=languages, localesToNamesMap={locale: f"<{locale}>" for locale in languages})
	synth = Synth(manager)
	environment = {
		"SettingsPanel": object,
		"_": lambda text: text,
		"wx": SimpleNamespace(Choice=object, CheckBox=lambda parent, label: Control(label)),
		"guiHelper": SimpleNamespace(BoxSizerHelper=Helper),
		"config": SimpleNamespace(conf=conf),
		"getSynth": lambda: synth,
		"languageDetection": env.module,
	}
	tree = ast.parse(PANEL.read_text(encoding="utf-8"))
	node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "UnicodeDetectionSettingsPanel")
	exec(compile(ast.Module(body=[node], type_ignores=[]), str(PANEL), "exec"), environment)
	panel = object.__new__(environment["UnicodeDetectionSettingsPanel"])
	panel.makeSettings(SimpleNamespace())
	return SimpleNamespace(panel=panel, added=added, switching=switching, synth=synth)


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
	assert (built.switching["latinCharactersLanguage"], built.switching["CJKCharactersLanguage"],
		built.switching["arabicCharactersLanguage"], built.switching["ignoreNumbersInLanguageDetection"]) == (
		"en", "zh", "ar", False)


def test_stored_language_not_offered_selects_the_first(env):
	built = build(env, LANGUAGES, {"latinCharactersLanguage": "xx"})
	assert built.added[1].selection == 0


def test_script_without_candidates_is_disabled_and_not_saved(env):
	built = build(env, ["en", "zh"], {"arabicCharactersLanguage": "fa"})
	arabic = built.added[3]
	assert arabic.choices == [] and arabic.enabled is False
	built.panel.onSave()
	assert built.switching["arabicCharactersLanguage"] == "fa"


@pytest.mark.parametrize("timing,refreshed", [("before", True), ("after", False)])
def test_changing_detection_timing_refreshes_detection(env, timing, refreshed):
	built = build(env, LANGUAGES, {})
	built.added[4].Select(["before", "after"].index(timing))
	built.synth.events.clear()
	built.panel.onSave()
	assert built.switching["DetectLanguageTiming"] == timing
	assert built.synth.events == ([("refresh",)] if refreshed else [])


@pytest.fixture
def env(stub_modules, monkeypatch):
	return load_language_detection(stub_modules, monkeypatch)
