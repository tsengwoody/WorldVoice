"""Load the speech pipeline, its settings and the synth settings that expose them, against NVDA stubs."""

import ast
import sys
import types
from types import SimpleNamespace

from addon_loader import WORLDVOICE, alias_package, load_source
from nvda_stubs import StubModules, worldvoice_conf


class FakeSpeechSequenceFilter:
	def __init__(self):
		self.registered = []

	def register(self, handler):
		self.registered.append(handler)

	def unregister(self, handler):
		pass

	def moveToEnd(self, handler, last=False):
		pass


def load_pipeline_module(monkeypatch, settings):
	stubs = StubModules(monkeypatch)
	for name in [
		"config",
		"globalVars",
		"logHandler",
		"speech",
		"speech.commands",
		"speech.extensions",
		"speechDictHandler",
		"synthDriverHandler",
		"synthDrivers",
		"synthDrivers.WorldVoice",
		"synthDrivers.WorldVoice._speechcommand",
		"synthDrivers.WorldVoice.log",
		"synthDrivers.WorldVoice.pipeline",
		"synthDrivers.WorldVoice.pipeline.speech_dictionary",
		"synthDrivers.WorldVoice.pipeline.settings",
		"synthDrivers.WorldVoice.pipeline.context",
		"synthDrivers.WorldVoice.pipeline.scope",
	]:
		sys.modules.pop(name, None)

	config = stubs.module("config")
	config.conf = {"general": {"loggingLevel": "INFO"}, **worldvoice_conf()}

	globalVars = stubs.module("globalVars")
	globalVars.speechDictionaryProcessing = True

	logHandler = stubs.module("logHandler")
	logHandler.log = SimpleNamespace(debug=lambda *args, **kwargs: None)

	commands = stubs.module("speech.commands")

	class SpeechCommand:
		"""NVDA's base of every speech command; NVDA's speechXml checks it."""

	class BreakCommand(SpeechCommand):
		def __init__(self, time):
			self.time = time

	class LangChangeCommand(SpeechCommand):
		def __init__(self, lang=None):
			self.lang = lang

	commands.SpeechCommand = SpeechCommand
	commands.BreakCommand = BreakCommand
	commands.LangChangeCommand = LangChangeCommand

	speech = stubs.module("speech")
	speech.speech = SimpleNamespace(processText=lambda *args, **kwargs: args[1])

	extensions = stubs.module("speech.extensions")
	extensions.filter_speechSequence = FakeSpeechSequenceFilter()

	speechDictHandler = stubs.module("speechDictHandler")
	speechDictHandler.processText = lambda text: text

	synthDriverHandler = stubs.module("synthDriverHandler")
	synthDriverHandler.getSynth = lambda: SimpleNamespace(name="notWorldVoice")

	alias_package(monkeypatch, "synthDrivers")
	alias_package(monkeypatch, "synthDrivers.WorldVoice", WORLDVOICE)

	speechcommand = stubs.module("synthDrivers.WorldVoice._speechcommand")

	class WVLangChangeCommand(LangChangeCommand):
		pass

	speechcommand.WVLangChangeCommand = WVLangChangeCommand

	worldVoiceLog = stubs.module("synthDrivers.WorldVoice.log")

	class PipelineLog:
		def __init__(self, *args, **kwargs):
			pass

	worldVoiceLog.PipelineLog = PipelineLog

	settingsModule = stubs.module("synthDrivers.WorldVoice.pipeline.settings")
	settingsModule.pipeline_settings = SimpleNamespace(effective=lambda supports_roles: settings)

	module = load_source(monkeypatch, "synthDrivers.WorldVoice.pipeline", WORLDVOICE / "pipeline/__init__.py")
	module._test_settings = settings
	return module, BreakCommand


def punctuation_settings(wait_factor, remove_characters=False):
	return SimpleNamespace(
		ignore_comma_between_number=False,
		number_mode="value",
		scope="WorldVoice",
		punctuation_pause_characters=".,",
		punctuation_pause_enabled=True,
		remove_punctuation_characters=remove_characters,
		scaled_item_wait=lambda: 0,
		scaled_number_wait=lambda: 0,
		scaled_chinesespace_wait=lambda: 0,
		scaled_punctuation_wait=lambda: wait_factor,
		scaled_group_wait=lambda: 0,
		group_size=3,
	)


ORDER = [
	"apply_speech_dictionaries",
	"ignore_comma_between_number",
	"number_language",
	"number_mode",
	"chinesespace_wait_factor",
	"item_wait_factor",
	"punctuation_wait_factor",
	"number_wait_factor",
	"speech_viewer",
]


def load_settings_module(monkeypatch, conf, errors=None):
	stubs = StubModules(monkeypatch)
	config = stubs.module("config")
	config.conf = conf
	addon_handler = stubs.module("addonHandler")
	addon_handler.initTranslation = lambda: None
	log_handler = stubs.module("logHandler")
	log_handler.log = SimpleNamespace(
		error=lambda *args, **kwargs: (errors if errors is not None else []).append(args),
	)
	synth_driver_handler = stubs.module("synthDriverHandler")
	synth_driver_handler.getSynth = lambda: None
	stubs.translation()
	return load_source(monkeypatch, "pipeline_settings_under_test", WORLDVOICE / "pipeline/settings.py")


SYNTH = WORLDVOICE / "__init__.py"


class Setting:
	def __init__(self, kind, id, label=None, **options):
		self.kind, self.id, self.label, self.options = kind, id, label, options


def setting_factory(kind):
	return lambda id, label=None, **options: Setting(kind, id, label, **options)


class Base:
	@classmethod
	def VoiceSetting(cls):
		return Setting("voice", "voice")

	@classmethod
	def VariantSetting(cls):
		return Setting("variant", "variant")

	@classmethod
	def RateSetting(cls):
		return Setting("rate", "rate")

	@classmethod
	def RateBoostSetting(cls):
		return Setting("rateBoost", "rateBoost")

	@classmethod
	def PitchSetting(cls):
		return Setting("pitch", "pitch")

	@classmethod
	def InflectionSetting(cls):
		return Setting("inflection", "inflection")

	@classmethod
	def VolumeSetting(cls):
		return Setting("volume", "volume")

	def loadSettings(self, *args, **kwargs):
		self.loaded = True


def load_synth(monkeypatch, conf):
	"""The real SynthDriver with its pipeline settings, over Base, and the settings module it reads."""
	settings_module = load_settings_module(monkeypatch, conf)
	tree = ast.parse(SYNTH.read_text(encoding="utf-8"))
	wanted = [
		node
		for node in tree.body
		if isinstance(node, ast.ClassDef)
		and node.name in {"_PipelineSetting", "SynthDriver"}
		or isinstance(node, ast.For)
		and ast.unparse(node.iter) == "PIPELINE_SETTINGS"
	]
	environment = {
		"SynthDriver": Base,
		"PIPELINE_SETTINGS": settings_module.PIPELINE_SETTINGS,
		"NUMBER_MODE_CHOICES": settings_module.NUMBER_MODE_CHOICES,
		"pipeline_settings": settings_module.pipeline_settings,
		"BooleanDriverSetting": setting_factory("bool"),
		"NumericDriverSetting": setting_factory("int"),
		"DriverSetting": setting_factory("str"),
		"_": lambda text: text,
		"config": types.SimpleNamespace(conf=conf),
		**{
			name: type(name, (), {})
			for name in (
				"IndexCommand",
				"CharacterModeCommand",
				"LangChangeCommand",
				"BreakCommand",
				"PitchCommand",
				"RateCommand",
				"VolumeCommand",
			)
		},
		"synthIndexReached": object(),
		"synthDoneSpeaking": object(),
	}
	# Not load_definitions: the module-level loop that adds the pipeline settings to SynthDriver
	# is a statement with no name, so the selection is by hand.
	exec(compile(ast.Module(body=wanted, type_ignores=[]), str(SYNTH), "exec"), environment)
	return environment["SynthDriver"], settings_module
