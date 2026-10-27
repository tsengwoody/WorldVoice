"""The Unicode detection panel's script choices and what it saves."""

import ast
from types import SimpleNamespace

import pytest
from addon_loader import ADDON, load_definitions
from detector_harness import load_language_detection
from ui_harness import BoxSizerHelper, CheckBox, Choice, Sizer

PANEL = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"


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


def build(env, languages, stored, table=None):
	switching = {
		"latinCharactersLanguage": "en",
		"CJKCharactersLanguage": "zh",
		"arabicCharactersLanguage": "ar",
		"cyrillicCharactersLanguage": "ru",
		"devanagariCharactersLanguage": "hi",
		"DetectLanguageTiming": "after",
		**stored,
	}
	conf = {"WorldVoice": {"autoLanguageSwitching": switching}}
	service = env.settings_module.DetectionSettingsService(lambda: conf)
	notified = []
	service.subscribe(lambda settings, changed: notified.append(changed))
	manager = SimpleNamespace(
		languages=languages,
		localesToNamesMap={locale: f"<{locale}>" for locale in languages},
	)
	synth = Synth(manager)
	environment = {
		"SettingsPanel": object,
		"_": lambda text: text,
		"wx": SimpleNamespace(Choice=Choice, CheckBox=CheckBox),
		"guiHelper": SimpleNamespace(BoxSizerHelper=BoxSizerHelper),
		"config": SimpleNamespace(conf=NoConfig()),
		"worldvoice_synth": lambda: synth,
		"DETECTION_SCRIPTS": table if table is not None else env.script_languages.DETECTION_SCRIPTS,
		"SCRIPT_LANGUAGES": env.script_languages.SCRIPT_LANGUAGES,
		"detection_settings": service,
	}
	load_definitions(PANEL, ["UnicodeDetectionSettingsPanel"], environment)
	panel = object.__new__(environment["UnicodeDetectionSettingsPanel"])
	sizer = Sizer()
	panel.makeSettings(sizer)
	return SimpleNamespace(
		panel=panel,
		added=sizer.controls(),
		switching=switching,
		synth=synth,
		notified=notified,
	)


LANGUAGES = ["en", "fr", "zh", "ja", "ar", "en_US", "uk", "ru", "ru_RU", "mr", "hi"]
STORED = {
	"latinCharactersLanguage": "fr",
	"CJKCharactersLanguage": "ja",
	"cyrillicCharactersLanguage": "uk",
	"devanagariCharactersLanguage": "mr",
}
TIMING = 5


def test_controls_choices_and_selections(env):
	built = build(env, LANGUAGES, STORED)
	labels = [control.label for control in built.added]
	assert labels == [
		"Language assumed for latin characters:",
		"Language assumed for CJK characters:",
		"Language assumed for arabic characters:",
		"Language assumed for cyrillic characters:",
		"Language assumed for devanagari characters:",
		"Language detection timing:",
	]
	latin, cjk, arabic, cyrillic, devanagari = built.added[0:TIMING]
	assert latin.choices == ["<en>", "<fr>"] and latin.selection == 1
	assert cjk.choices == ["<ja>", "<zh>"] and cjk.selection == 0
	assert arabic.choices == ["<ar>"] and arabic.selection == 0
	assert cyrillic.choices == ["<ru>", "<uk>"] and cyrillic.selection == 1
	assert devanagari.choices == ["<hi>", "<mr>"] and devanagari.selection == 1


def test_save_writes_each_enabled_choice(env):
	built = build(env, LANGUAGES, STORED)
	built.added[0].Select(0)
	built.added[1].Select(1)
	built.added[3].Select(0)
	built.added[4].Select(0)
	built.panel.onSave()
	assert (
		built.switching["latinCharactersLanguage"],
		built.switching["CJKCharactersLanguage"],
		built.switching["arabicCharactersLanguage"],
		built.switching["cyrillicCharactersLanguage"],
		built.switching["devanagariCharactersLanguage"],
	) == ("en", "zh", "ar", "ru", "hi")


def test_stored_language_not_offered_selects_the_first(env):
	built = build(env, LANGUAGES, {"latinCharactersLanguage": "xx"})
	assert built.added[0].selection == 0


def test_script_without_candidates_is_disabled_and_not_saved(env):
	stored = {
		"arabicCharactersLanguage": "fa",
		"cyrillicCharactersLanguage": "bg",
		"devanagariCharactersLanguage": "ne",
	}
	built = build(env, ["en", "zh"], stored)
	for index in (2, 3, 4):
		assert built.added[index].choices == [] and built.added[index].enabled is False
	built.panel.onSave()
	assert {key: built.switching[key] for key in stored} == stored


@pytest.mark.parametrize("timing,timing_changed", [("before", True), ("after", False)])
def test_saving_reports_a_timing_change_to_subscribers_not_to_the_synth(env, timing, timing_changed):
	built = build(env, LANGUAGES, {})
	built.added[TIMING].Select(["before", "after"].index(timing))
	built.synth.events.clear()
	built.panel.onSave()
	assert built.switching["DetectLanguageTiming"] == timing
	assert [("timing" in changed) for changed in built.notified] == ([True] if timing_changed else [])
	assert built.synth.events == []


def test_saving_unchanged_choices_notifies_nobody(env):
	built = build(env, LANGUAGES, STORED)
	built.panel.onSave()
	assert built.notified == []


DEFAULT_LABELS = [
	"Language assumed for latin characters:",
	"Language assumed for CJK characters:",
	"Language assumed for arabic characters:",
	"Language assumed for cyrillic characters:",
	"Language assumed for devanagari characters:",
]


def test_detection_panel_lists_every_table_script(env):
	table = env.script_languages.DETECTION_SCRIPTS
	built = build(env, LANGUAGES, STORED)
	assert set(built.panel._script_labels()) == {row.script for row in table}
	assert len(built.panel._script_labels()) == len(table)
	# The controls follow the table, not the labels: reversed rows give reversed controls.
	reversed_built = build(env, LANGUAGES, STORED, table=tuple(reversed(table)))
	assert [control.label for control in reversed_built.added[0:TIMING]] == DEFAULT_LABELS[::-1]
	reversed_built.added[TIMING - 1].Select(0)
	reversed_built.panel.onSave()
	assert reversed_built.switching["latinCharactersLanguage"] == "en"


def test_the_dialog_reads_the_tables_without_the_detector():
	# The panel needs the script table and the settings service, not the detector module.
	allowed = {
		"synthDrivers.WorldVoice.languageDetection.settings",
		"synthDrivers.WorldVoice.languageDetection.scriptLanguages",
	}
	for node in ast.walk(ast.parse(PANEL.read_text(encoding="utf-8"))):
		if isinstance(node, ast.ImportFrom):
			names = [node.module or "", *(f"{node.module}.{alias.name}" for alias in node.names)]
		elif isinstance(node, ast.Import):
			names = [alias.name for alias in node.names]
		else:
			continue
		if any("languageDetection" in name for name in names):
			assert isinstance(node, ast.ImportFrom) and node.module in allowed, ast.unparse(node)


@pytest.fixture
def env(stub_modules, monkeypatch):
	return load_language_detection(stub_modules, monkeypatch)
