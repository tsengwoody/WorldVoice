"""Pipeline UI panels save through the pipeline settings service."""

import ast
import types

from addon_loader import ADDON, WORLDVOICE, load_definitions
from pipeline_harness import LOG_SWITCH_ORDER
from ui_harness import load_settings_dialog, load_voice_settings_dialogs

PANELS = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"
VOICE_PANEL = WORLDVOICE / "ui/voicePanel.py"
SYNTH = WORLDVOICE / "__init__.py"


class Widget:
	def __init__(self, value=None, selection=0):
		self.value, self.selection = value, selection

	def GetValue(self):
		return self.value

	def GetCurrentSelection(self):
		return self.selection


def test_log_labels_match_stages_and_confspec(monkeypatch):
	assert list(load_settings_dialog(monkeypatch).module._LOG_LABELS) == LOG_SWITCH_ORDER
	tree = ast.parse(SYNTH.read_text(encoding="utf-8"))
	source = ast.unparse(tree)
	assert "key: 'boolean(default=false)' for key in LOG_SWITCHES" in source


def test_log_switch_labels_are_unchanged(monkeypatch):
	# The test _ is the identity, so these are the msgids the Log Record panel shows.
	labels = load_settings_dialog(monkeypatch).module._LOG_LABELS
	assert list(labels.items()) == [
		("apply_speech_dictionaries", "Apply speech dictionaries"),
		("number_language", "Number language"),
		("number_mode", "Number mode"),
		("unspaced_script_space_wait_factor", "Space wait factor between CJK and Southeast Asian characters"),
		("item_wait_factor", "Item wait factor"),
		("punctuation_wait_factor", "Punctuation wait factor"),
		("number_wait_factor", "Number wait factor"),
		("speech_viewer", "Speech viewer"),
	]


def test_log_labels_follow_the_table_labels(monkeypatch):
	# Decided by the user (2026-10-21): the log switches use the settings' sentence-case labels.
	env = load_settings_dialog(monkeypatch)
	labels = env.module._LOG_LABELS
	table = {spec.key: spec for spec in env.module.PIPELINE_SETTINGS}
	for key, label in labels.items():
		first, *rest = label.split()
		assert first[0].isupper() and not any(
			word[0].isupper() for word in rest if word not in {"CJK", "Southeast", "Asian"}
		), label
		if key in table:
			spec = table[key]
			assert label in {spec.display_name, spec.label.replace("&", "")}, (key, label)
	assert labels["apply_speech_dictionaries"] == "Apply speech dictionaries"
	assert labels["speech_viewer"] == "Speech viewer"


def test_pipeline_panel_saves_once_through_the_service(monkeypatch):
	updates = []
	module = load_settings_dialog(monkeypatch).module
	module.pipeline_settings = types.SimpleNamespace(update=lambda **changes: updates.append(changes))
	panel = object.__new__(module.SpeechPipelinePanel)
	panel._scope_choice = Widget(selection=0)
	panel._number_mode_choice = Widget(selection=3)
	panel._global_wait_factor_slider = Widget(3)
	for name in ("number", "item", "sayall", "unspaced_script_space", "punctuation"):
		setattr(panel, f"_{name}_wait_factor_slider", Widget(7))
	panel._punctuation_pause_enabled_checkbox = Widget(False)
	panel._remove_punctuation_characters_checkbox = Widget(True)
	panel._punctuation_pause_characters_edit = Widget(" .,")
	panel._group_size_spin = Widget(5)

	panel.onSave()

	assert updates == [
		{
			"scope": "all",
			"number_mode": "group",
			"global_wait_factor": 30,
			"number_wait_factor": 7,
			"item_wait_factor": 7,
			"sayall_wait_factor": 7,
			"unspaced_script_space_wait_factor": 7,
			"punctuation_wait_factor": 7,
			"punctuation_pause_enabled": False,
			"remove_punctuation_characters": True,
			"punctuation_pause_characters": " .,",
			"group_size": 5,
		},
	]
	for name in (
		"onGlobalWaitFactorSliderScroll",
		"sliderEnable",
		"onScopeSelectionChange",
		"_scope_value",
		"number_mode_value",
		"_selected_number_mode",
		"onNumberModeChange",
		"onPunctuationPauseEnabledChange",
	):
		assert not hasattr(panel, name)


def test_voice_panel_discard_restores_live_pipeline_changes():
	state = {"item_wait_factor": 10, "number_mode": "value"}
	updates = []

	def update(**changes):
		updates.append(changes)
		state.update(changes)

	class Base:
		def onDiscard(self):
			updates.append("nvda discard")

	environment = load_definitions(
		VOICE_PANEL,
		{"WorldVoiceVoiceSettingsPanel"},
		{
			"VoiceSettingsPanel": Base,
			"pipeline_settings": types.SimpleNamespace(
				get=lambda: types.SimpleNamespace(**state),
				update=update,
			),
			"PIPELINE_CONFIG_KEYS": ("item_wait_factor", "number_mode"),
		},
	)
	panel = object.__new__(environment["WorldVoiceVoiceSettingsPanel"])
	panel._pipelineSnapshot = types.SimpleNamespace(**state)
	type(panel).driver = property(lambda self: types.SimpleNamespace(name="WorldVoice"))
	state["item_wait_factor"] = 40

	panel.onDiscard()

	assert updates == ["nvda discard", {"item_wait_factor": 10}]
	assert state["item_wait_factor"] == 10


def voice_panel(monkeypatch, pipeline_settings, driver_name="WorldVoice"):
	"""The real Voice panel over ui_harness's NVDA panel, without makeSettings."""
	module = load_voice_settings_dialogs(monkeypatch).module
	module.pipeline_settings = pipeline_settings
	panel = object.__new__(module.WorldVoiceVoiceSettingsPanel)
	panel._driver = types.SimpleNamespace(name=driver_name)
	panel.base_calls = []
	return module, panel


def test_voice_panel_discard_after_apply_keeps_applied_pipeline_values(monkeypatch):
	state = {"item_wait_factor": 10, "punctuation_pause_characters": ".", "group_size": 3}

	def update(**changes):
		state.update(changes)

	module, panel = voice_panel(
		monkeypatch,
		types.SimpleNamespace(get=lambda: types.SimpleNamespace(**state), update=update),
	)
	module.PIPELINE_CONFIG_KEYS = ("item_wait_factor", "punctuation_pause_characters", "group_size")
	panel._pipelineSnapshot = types.SimpleNamespace(**state)
	panel.punctuationPauseCharactersEdit = Widget(".")
	panel.groupSizeSpin = Widget(3)
	state["item_wait_factor"] = 40

	panel.onSave()  # NVDA Apply
	state["item_wait_factor"] = 70
	panel.onDiscard()  # then Cancel

	assert state["item_wait_factor"] == 40


def test_voice_panel_saves_the_characters_and_group_size_in_one_update(monkeypatch):
	calls = []
	_module, panel = voice_panel(
		monkeypatch,
		types.SimpleNamespace(update=lambda **changes: calls.append(changes), get=lambda: None),
	)
	panel.base_calls = calls
	panel.punctuationPauseCharactersEdit = Widget(" .,")
	panel.groupSizeSpin = Widget(5)

	panel.onSave()

	# One update, so subscribers see both values together, before NVDA saves its own settings.
	assert calls == [{"punctuation_pause_characters": " .,", "group_size": 5}, "onSave"]


def dialog_msgids():
	# The string constant of every _() call in the dialog.
	tree = ast.parse(PANELS.read_text(encoding="utf-8"))
	return {
		node.args[0].value
		for node in ast.walk(tree)
		if isinstance(node, ast.Call)
		and isinstance(node.func, ast.Name)
		and node.func.id == "_"
		and node.args
		and isinstance(node.args[0], ast.Constant)
		and isinstance(node.args[0].value, str)
	}


def test_log_labels_come_from_the_table(monkeypatch):
	# A log switch named after a pipeline setting shows that setting's name, translated once in the
	# table; only stages without a setting have a label of their own in the dialog.
	module = load_settings_dialog(monkeypatch).module
	table = {spec.key: spec for spec in module.PIPELINE_SETTINGS}
	assert set(module._STAGE_LOG_LABELS) == {key for key in LOG_SWITCH_ORDER if key not in table}
	for key in LOG_SWITCH_ORDER:
		if key in table:
			label = module._LOG_LABELS[key]
			assert label == (table[key].display_name or table[key].label), key
			assert "&" not in label, key
	strings = {spec.label for spec in table.values()} | (
		{spec.display_name for spec in table.values()} - {None}
	)
	assert dialog_msgids() & strings == set()


def test_table_labels_tell_translators_they_name_log_switches(monkeypatch):
	# The Log Record panel shows these table strings as its switch labels; the dialog no longer has a
	# _() call of its own for them, so only the table's comment can tell translators.
	module = load_settings_dialog(monkeypatch).module
	table = {spec.key for spec in module.PIPELINE_SETTINGS}
	lines = (WORLDVOICE / "pipeline/settings.py").read_text(encoding="utf-8").splitlines()
	silent = []
	for key in LOG_SWITCH_ORDER:
		if key not in table:
			continue
		call = f"_({module._LOG_LABELS[key]!r})".replace("'", '"')
		(number,) = [n for n, line in enumerate(lines) if call in line]
		comments = []
		above = number - 1
		while lines[above].lstrip().startswith("#"):
			comments.insert(0, lines[above].strip().lstrip("# "))
			above -= 1
		if "log switch" not in " ".join(comments):
			silent.append(key)
	assert silent == []
