"""The driver settings, the settings ring and both settings panels follow the pipeline table's order."""

import types

import pytest
from pipeline_harness import Setting, load_synth
from ui_harness import (
	BooleanDriverSetting,
	DriverSetting,
	Label,
	NumericDriverSetting,
	Sizer,
	load_settings_dialog,
	load_voice_panel,
	make_panel,
)

STANDARD = ["engine", "voice", "variant", "rate", "rateBoost", "pitch", "inflection", "volume", "uwv"]
TABLE_DRIVER_IDS = [
	"globalWaitFactor",
	"numlan",
	"nummod",
	"numberWaitFactor",
	"itemWaitFactor",
	"sayAllWaitFactor",
	"unspacedScriptSpaceWaitFactor",
	"punctuationPauseEnabled",
	"removePunctuationCharacters",
	"punctuationWaitFactor",
]


def synth_and_table(monkeypatch):
	synth_class, settings_module = load_synth(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	synth = object.__new__(synth_class)
	synth._voiceManager = types.SimpleNamespace(
		default_voice_name="v",
		get_voice_capabilities=lambda name: types.SimpleNamespace(settings=frozenset()),
	)
	return synth, settings_module.PIPELINE_SETTINGS


def test_driver_settings_follow_the_table(monkeypatch):
	synth, table = synth_and_table(monkeypatch)
	ids = [setting.id for setting in synth.allSupportedSettings]
	assert ids[: len(STANDARD)] == STANDARD
	assert ids[len(STANDARD) :] == [
		spec.driver_id for spec in table if spec.driver_id and "voice" in spec.panels
	]
	assert ids[len(STANDARD) :] == TABLE_DRIVER_IDS


def test_ring_follows_the_table_after_the_standard_settings(monkeypatch):
	# NVDA's ring lists supportedSettings in order, skipping availableInSettingsRing=False.
	synth, _table = synth_and_table(monkeypatch)
	ring = [
		setting.id for setting in synth.supportedSettings if setting.options.get("availableInSettingsRing")
	]
	# The engine setting is not in the ring (spec D2); the voice's capabilities hide rate boost and inflection.
	assert ring == ["voice", "variant", "rate", "pitch", "volume", "uwv", *TABLE_DRIVER_IDS]


def test_engine_setting_is_first_unstored_and_off_the_ring(monkeypatch):
	synth, _table = synth_and_table(monkeypatch)
	engine = synth.supportedSettings[0]
	assert (engine.kind, engine.id, engine.label) == ("str", "engine", "Speec&h engine")
	assert engine.options["useConfig"] is False
	assert engine.options["availableInSettingsRing"] is False
	assert synth.allSupportedSettings[0].id == "engine"


def test_initial_ring_setting_is_rates_place_in_the_ring(monkeypatch):
	# NVDA's own answer, rate's index in supportedSettings, would be 3: it counts the engine setting.
	synth, _table = synth_and_table(monkeypatch)
	ring = [setting.id for setting in synth.supportedSettings if setting.availableInSettingsRing]
	assert synth._get_initialSettingsRingSetting() == 2
	assert ring[2] == "rate"


@pytest.mark.parametrize(
	("ids", "expected"),
	[(["engine", "voice"], 0), (["engine"], None)],
)
def test_initial_ring_setting_without_rate(monkeypatch, ids, expected):
	synth, _table = synth_and_table(monkeypatch)
	settings = [
		Setting("str", setting_id, availableInSettingsRing=setting_id != "engine") for setting_id in ids
	]
	monkeypatch.setattr(type(synth), "supportedSettings", property(lambda self: settings))
	assert synth._get_initialSettingsRingSetting() == expected


def test_ring_names_follow_the_label_rule(monkeypatch):
	# Without a displayName NVDA shows the label with its accelerator removed.
	synth, _table = synth_and_table(monkeypatch)
	names = {
		setting.id: setting.options.get("displayName", (setting.label or "").replace("&", ""))
		for setting in synth.supportedSettings
		if setting.id in TABLE_DRIVER_IDS and setting.options.get("availableInSettingsRing")
	}
	assert names == {
		"globalWaitFactor": "Global wait factor",
		"numlan": "Number language",
		"nummod": "Number mode",
		"numberWaitFactor": "Number wait factor",
		"itemWaitFactor": "Item wait factor",
		"sayAllWaitFactor": "Say all wait factor",
		"unspacedScriptSpaceWaitFactor": "Space wait factor between CJK and Southeast Asian characters",
		"punctuationPauseEnabled": "Punctuation pauses",
		"removePunctuationCharacters": "Remove punctuation at pause points",
		"punctuationWaitFactor": "Punctuation wait factor",
	}


# NVDA's driver setting class for each control a driver entry uses.
NVDA_SETTINGS = {"checkbox": BooleanDriverSetting, "slider": NumericDriverSetting, "choice": DriverSetting}


class TableDriver:
	"""WorldVoice as the Voice panel sees it: the voice plus every driver setting of the table."""

	name = "WorldVoice"

	def __init__(self, table):
		entries = [spec for spec in table if spec.driver_id is not None and "voice" in spec.panels]
		self.allSupportedSettings = [DriverSetting("voice")] + [
			NVDA_SETTINGS[spec.control](spec.driver_id) for spec in entries
		]
		self.supportedSettings = list(self.allSupportedSettings)
		self.availableVoices = {"eva": types.SimpleNamespace(id="eva", displayName="Eva")}
		self.voice = "eva"
		for spec in entries:
			if spec.control == "choice":
				options = spec.choices or (("default", "default"),)
				setattr(
					self,
					f"available{spec.driver_id.capitalize()}s",
					{value: types.SimpleNamespace(id=value, displayName=label) for value, label in options},
				)
			setattr(self, spec.driver_id, spec.default)

	def isSupported(self, name):
		return True


def voice_panel(monkeypatch):
	env = load_voice_panel(monkeypatch)
	panel = env.module.WorldVoiceVoiceSettingsPanel(TableDriver(env.module.PIPELINE_SETTINGS))
	panel.makeSettings(panel.settingsSizer)
	specs = env.module.panelSpecs(env.module.PIPELINE_SETTINGS, "voice")
	return env, panel, specs


def voice_controls(env, panel, specs):
	"""Each Voice panel table entry's control, by key."""
	module = env.module
	return {
		spec.key: getattr(
			panel,
			module.driverAttribute(spec) if spec.driver_id is not None else module.voiceAttribute(spec),
		)
		for spec in specs
	}


def voice_row_items(env, panel, specs):
	"""Each table entry's key with its settings-sizer item, in the panel's layout order."""
	controls = voice_controls(env, panel, specs)
	rows = {}
	for spec in specs:
		row = (
			panel.sizerDict[spec.driver_id]
			if spec.driver_id is not None
			else env.controls.controlRow(controls[spec.key], spec)
		)
		rows[id(row)] = spec.key
	return [(rows[id(entry.item)], entry) for entry in panel.settingsSizer.items if id(entry.item) in rows]


def voice_rows(env, panel, specs):
	"""The table entries in the panel's layout order."""
	return [key for key, _item in voice_row_items(env, panel, specs)]


def tab_keys(panel, controls):
	keys = {id(control): key for key, control in controls.items()}
	return [keys[id(control)] for control in panel.tab_order if id(control) in keys]


VOICE_KEYS = [
	"global_wait_factor",
	"number_language",
	"number_mode",
	"group_size",
	"number_wait_factor",
	"item_wait_factor",
	"sayall_wait_factor",
	"unspaced_script_space_wait_factor",
	"punctuation_pause_enabled",
	"remove_punctuation_characters",
	"punctuation_wait_factor",
	"punctuation_pause_characters",
]


def test_voice_panel_rows_follow_the_table(monkeypatch):
	env, panel, specs = voice_panel(monkeypatch)
	assert voice_rows(env, panel, specs) == [spec.key for spec in specs] == VOICE_KEYS


def test_voice_panel_tab_order_follows_the_table(monkeypatch):
	env, panel, specs = voice_panel(monkeypatch)
	assert tab_keys(panel, voice_controls(env, panel, specs)) == VOICE_KEYS


def test_voice_panel_rows_and_tab_order_survive_a_voice_change(monkeypatch):
	env, panel, specs = voice_panel(monkeypatch)

	panel.updateDriverSettings(changedSetting="voice")  # what NVDA runs after the voice changed

	assert voice_rows(env, panel, specs) == VOICE_KEYS
	assert tab_keys(panel, voice_controls(env, panel, specs)) == VOICE_KEYS


def window_keys(panel, controls):
	"""The table entries in the panel's window order: what NVDA's object navigation follows."""
	keys = {id(control): key for key, control in controls.items()}
	return [keys[id(window)] for window in panel.children if id(window) in keys]


def labels_out_of_place(panel, specs, controls):
	"""The entries whose label is not the window just before their control, in the same row."""
	misplaced = []
	for spec in specs:
		if spec.control == "checkbox":
			continue
		control = controls[spec.key]
		index = panel.children.index(control)
		label = panel.children[index - 1] if index else None
		if not isinstance(label, Label) or label.GetContainingSizer() is not control.GetContainingSizer():
			misplaced.append(spec.key)
	return misplaced


class OtherDriver:
	"""Another synthesizer: no allSupportedSettings and none of WorldVoice's settings."""

	name = "espeak"

	def __init__(self):
		self.supportedSettings = [DriverSetting("voice"), NumericDriverSetting("rate")]
		self.availableVoices = {"eva": types.SimpleNamespace(id="eva", displayName="Eva")}
		self.voice, self.rate = "eva", 50

	def isSupported(self, name):
		return name in {"voice", "rate"}


def build_then(monkeypatch, scenario):
	"""A WorldVoice Voice panel after the scenario; returns (env, panel, specs, windows before it)."""
	env = load_voice_panel(monkeypatch)
	table_driver = TableDriver(env.module.PIPELINE_SETTINGS)
	first = OtherDriver() if scenario == "other synth rebuild" else table_driver
	panel = env.module.WorldVoiceVoiceSettingsPanel(first)
	panel.makeSettings(panel.settingsSizer)
	before = list(panel.children)
	if scenario == "voice switch":
		panel.updateDriverSettings(changedSetting="voice")  # what NVDA runs after the voice changed
	elif scenario in ("worldvoice rebuild", "other synth rebuild"):
		# NVDA's refreshGui on a new synth instance: every window goes, makeSettings runs again.
		panel._driver = TableDriver(env.module.PIPELINE_SETTINGS)
		panel.refreshGui()
	specs = env.module.panelSpecs(env.module.PIPELINE_SETTINGS, "voice")
	return env, panel, specs, before


@pytest.mark.parametrize(
	"scenario",
	["first build", "voice switch", "worldvoice rebuild", "other synth rebuild"],
)
def test_voice_panel_orders_follow_the_table(monkeypatch, scenario):
	env, panel, specs, before = build_then(monkeypatch, scenario)
	controls = voice_controls(env, panel, specs)

	assert window_keys(panel, controls) == VOICE_KEYS
	assert tab_keys(panel, controls) == VOICE_KEYS
	assert voice_rows(env, panel, specs) == VOICE_KEYS
	assert labels_out_of_place(panel, specs, controls) == []
	if scenario == "voice switch":
		assert panel.children == before


@pytest.mark.parametrize(
	"scenario",
	["first build", "voice switch", "worldvoice rebuild", "other synth rebuild"],
)
def test_voice_panel_rows_are_spaced_like_nvdas_driver_rows(monkeypatch, scenario):
	# NVDA inserts each driver row with a 10px bottom border (settingsDialogs.py:1585-1590). A
	# WorldVoice row without it touches the next one: the last, Punctuation pause characters,
	# would touch NVDA's Automatic language switching checkbox.
	env, panel, specs, _before = build_then(monkeypatch, scenario)
	spacing = {key: (item.GetBorder(), item.GetFlag()) for key, item in voice_row_items(env, panel, specs)}
	assert spacing == dict.fromkeys(VOICE_KEYS, (10, env.wx.BOTTOM))


def test_pipeline_panel_controls_follow_the_table(monkeypatch):
	env = load_settings_dialog(monkeypatch)
	panel = make_panel(env.module.SpeechPipelinePanel)
	sizer = Sizer()
	panel.makeSettings(sizer)
	specs = env.panels.pipeline.panelSpecs(env.panels.pipeline.PIPELINE_SETTINGS, "pipeline")
	controls = {spec.key: getattr(panel, env.panels.pipeline.pipelineAttribute(spec)) for spec in specs}
	keys = [spec.key for spec in specs]
	assert keys == ["scope", *(key for key in VOICE_KEYS if key != "number_language")]
	assert tab_keys(types.SimpleNamespace(tab_order=sizer.controls()), controls) == keys
	assert tab_keys(panel, controls) == keys
