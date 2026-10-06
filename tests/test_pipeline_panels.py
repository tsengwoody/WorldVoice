"""Pipeline UI panels save through the pipeline settings service."""

import ast
import types
from pathlib import Path

from test_pipeline_stages import ORDER

ROOT = Path(__file__).resolve().parents[1]
PANELS = ROOT / "addon/globalPlugins/WorldVoice/speechSettingsDialog.py"
VOICE_PANEL = ROOT / "addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py"
SYNTH = ROOT / "addon/synthDrivers/WorldVoice/__init__.py"


def load(path, names, environment):
	tree = ast.parse(path.read_text(encoding="utf-8"))
	nodes = [
		node
		for node in tree.body
		if isinstance(node, ast.ClassDef)
		and node.name in names
		or isinstance(node, ast.Assign)
		and any(getattr(t, "id", None) in names for t in node.targets)
	]
	exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), environment)
	return environment


class Widget:
	def __init__(self, value=None, selection=0):
		self.value, self.selection = value, selection

	def GetValue(self):
		return self.value

	def GetCurrentSelection(self):
		return self.selection


def test_log_labels_match_stages_and_confspec():
	environment = load(PANELS, {"_LOG_LABELS"}, {"_": lambda text: text})
	assert list(environment["_LOG_LABELS"]) == ORDER
	tree = ast.parse(SYNTH.read_text(encoding="utf-8"))
	source = ast.unparse(tree)
	assert "stage.log_key: 'boolean(default=false)' for stage in STAGES" in source


def test_pipeline_panel_saves_once_through_the_service():
	updates = []
	environment = load(
		PANELS,
		{"SpeechPipelinePanel"},
		{
			"SettingsPanel": object,
			"_": lambda text: text,
			"pipeline_settings": types.SimpleNamespace(update=lambda **changes: updates.append(changes)),
		},
	)
	panel = object.__new__(environment["SpeechPipelinePanel"])
	panel._scope_value = ["all", "WorldVoice"]
	panel._scope_choice = Widget(selection=0)
	panel.number_mode_value = ["value", "number", "pair"]
	panel._number_mode_choice = Widget(selection=2)
	panel._ignore_comma_between_number_checkbox = Widget(True)
	panel._global_wait_factor_slider = Widget(3)
	for name in ("number", "item", "sayall", "chinesespace", "punctuation", "pair"):
		setattr(panel, f"_{name}_wait_factor_slider", Widget(7))
	panel._punctuation_pause_enabled_checkbox = Widget(False)
	panel._remove_punctuation_characters_checkbox = Widget(True)
	panel._punctuation_pause_characters_edit = Widget(" .,")

	panel.onSave()

	assert updates == [
		{
			"scope": "all",
			"ignore_comma_between_number": True,
			"number_mode": "pair",
			"global_wait_factor": 30,
			"number_wait_factor": 7,
			"item_wait_factor": 7,
			"sayall_wait_factor": 7,
			"chinesespace_wait_factor": 7,
			"punctuation_wait_factor": 7,
			"punctuation_pause_enabled": False,
			"remove_punctuation_characters": True,
			"punctuation_pause_characters": " .,",
			"pair_wait_factor": 7,
		},
	]
	for name in ("onGlobalWaitFactorSliderScroll", "sliderEnable", "onScopeSelectionChange"):
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

	environment = load(
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


def test_voice_panel_discard_after_apply_keeps_applied_pipeline_values():
	state = {"item_wait_factor": 10, "punctuation_pause_characters": "."}

	def update(**changes):
		state.update(changes)

	class Base:
		def onSave(self):
			pass

		def onDiscard(self):
			pass

	environment = load(
		VOICE_PANEL,
		{"WorldVoiceVoiceSettingsPanel"},
		{
			"VoiceSettingsPanel": Base,
			"pipeline_settings": types.SimpleNamespace(
				get=lambda: types.SimpleNamespace(**state),
				update=update,
			),
			"PIPELINE_CONFIG_KEYS": ("item_wait_factor", "punctuation_pause_characters"),
		},
	)
	panel = object.__new__(environment["WorldVoiceVoiceSettingsPanel"])
	type(panel).driver = property(lambda self: types.SimpleNamespace(name="WorldVoice"))
	panel._pipelineSnapshot = types.SimpleNamespace(**state)
	panel.punctuationPauseCharactersEdit = Widget(".")
	state["item_wait_factor"] = 40

	panel.onSave()  # NVDA Apply
	state["item_wait_factor"] = 70
	panel.onDiscard()  # then Cancel

	assert state["item_wait_factor"] == 40
