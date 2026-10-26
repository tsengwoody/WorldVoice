"""Load the speech pipeline, its settings and the synth settings that expose them, against NVDA stubs."""

import ast
import builtins
import importlib
import sys
import types
import unicodedata
from types import SimpleNamespace

import pytest
from addon_loader import REF, WORLDVOICE, alias_package, load_definitions, load_source
from nvda_stubs import StubModules, configobj_stub, worldvoice_conf

CHARACTER_PROCESSING = REF / "nvda/source/characterProcessing.py"


def symbol_name(locale, symbol):
	"""The stub of NVDA's characterProcessing.processSpeechSymbol: a letters-only name, unique per locale.

	symbol_name("en", ".") == "full stop en"; symbol_name("zh_TW", "×") == "multiplication sign zh tw".
	"""
	return " ".join([*unicodedata.name(symbol).lower().replace("-", " ").split(), *locale.lower().split("_")])


class FakeSpeechSequenceFilter:
	def __init__(self):
		self.registered = []

	def register(self, handler):
		self.registered.append(handler)

	def unregister(self, handler):
		pass

	def moveToEnd(self, handler, last=False):
		pass


def nvda_normalize_language():
	"""NVDA's own languageHandler.normalizeLanguage, run from ref/nvda without the rest of the module."""
	namespace = load_definitions(REF / "nvda/source/languageHandler.py", ["normalizeLanguage"], {})
	return namespace["normalizeLanguage"]


# The pipeline's modules, in the order PipelineModules looks a name up in.
PIPELINE_MODULES = (
	"registry",
	"sequence",
	"breaks",
	"items",
	"numberStages",
	"punctuation",
	"unspaced",
	"languageCommands",
	"context",
	"settings",
	"numbers",
	"symbols",
	"speechDictionary",
)


class PipelineModules:
	"""The pipeline's modules read as one namespace by the tests; pipeline/__init__.py is empty.

	module.<name of a module in PIPELINE_MODULES> is that module; any other name comes from the
	first module there that defines or imports it. A patch goes to the module that looks the name
	up, as module.registry for the stage handler's current_context, pipeline_settings, pl, log and
	filter_speechSequence: setting an attribute here raises, so a patch can never silently miss.
	"""

	def __init__(self, test_settings):
		modules = {name: sys.modules[f"synthDrivers.WorldVoice.pipeline.{name}"] for name in PIPELINE_MODULES}
		object.__setattr__(self, "_modules", modules)
		object.__setattr__(self, "_test_settings", test_settings)

	def __getattr__(self, name):
		if name in self._modules:
			return self._modules[name]
		for module in self._modules.values():
			if name in vars(module):
				return vars(module)[name]
		raise AttributeError(name)

	def __setattr__(self, name, value):
		raise AttributeError(f"patch {name} on the pipeline module that looks it up, as module.registry")


def load_pipeline_module(monkeypatch, settings):
	stubs = StubModules(monkeypatch)
	for name in [
		"config",
		"globalVars",
		"languageHandler",
		"logHandler",
		"speech",
		"speech.commands",
		"speech.extensions",
		"characterProcessing",
		"speechDictHandler",
		"synthDriverHandler",
		"synthDrivers",
		"synthDrivers.WorldVoice",
		"synthDrivers.WorldVoice.speechCommands",
		"synthDrivers.WorldVoice.numberLanguage",
		"synthDrivers.WorldVoice.languageDetection",
		"synthDrivers.WorldVoice.unicodeScripts.lookup",
		"synthDrivers.WorldVoice.pipeline",
		"synthDrivers.WorldVoice.pipeline.registry",
		"synthDrivers.WorldVoice.pipeline.sequence",
		"synthDrivers.WorldVoice.pipeline.breaks",
		"synthDrivers.WorldVoice.pipeline.items",
		"synthDrivers.WorldVoice.pipeline.numberStages",
		"synthDrivers.WorldVoice.pipeline.punctuation",
		"synthDrivers.WorldVoice.pipeline.unspaced",
		"synthDrivers.WorldVoice.pipeline.languageCommands",
		"synthDrivers.WorldVoice.pipeline.recorder",
		"synthDrivers.WorldVoice.pipeline.speechDictionary",
		"synthDrivers.WorldVoice.pipeline.settings",
		"synthDrivers.WorldVoice.pipeline.context",
		"synthDrivers.WorldVoice.pipeline.scope",
		"synthDrivers.WorldVoice.pipeline.numbers",
		"synthDrivers.WorldVoice.pipeline.symbols",
		"synthDrivers.WorldVoice.unicodeScripts.unspaced_common_data",
	]:
		sys.modules.pop(name, None)

	config = stubs.module("config")
	config.conf = {"general": {"loggingLevel": "INFO"}, **worldvoice_conf()}

	globalVars = stubs.module("globalVars")
	globalVars.speechDictionaryProcessing = True
	# NVDA's own locale directory, so the pipeline sees which symbol tables NVDA really has.
	globalVars.appDir = str(REF / "nvda/source")

	stubs.module("languageHandler", normalizeLanguage=nvda_normalize_language())

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

	class EndUtteranceCommand(SpeechCommand):
		"""NVDA's speech manager ends an utterance here (speech/manager.py)."""

	class ConfigProfileTriggerCommand(SpeechCommand):
		"""NVDA's speech manager ends an utterance before a profile trigger with a profile."""

		def __init__(self, trigger=None, enter=True):
			self.trigger = trigger
			self.enter = enter

	commands.SpeechCommand = SpeechCommand
	commands.BreakCommand = BreakCommand
	commands.LangChangeCommand = LangChangeCommand
	commands.EndUtteranceCommand = EndUtteranceCommand
	commands.ConfigProfileTriggerCommand = ConfigProfileTriggerCommand

	speech = stubs.module("speech")
	speech.speech = SimpleNamespace(processText=lambda *args, **kwargs: args[1])
	speech.getCurrentLanguage = lambda: "en"

	characterProcessing = stubs.module("characterProcessing")
	characterProcessing.processSpeechSymbol = symbol_name

	extensions = stubs.module("speech.extensions")
	extensions.filter_speechSequence = FakeSpeechSequenceFilter()

	speechDictHandler = stubs.module("speechDictHandler")
	speechDictHandler.processText = lambda text: text

	synthDriverHandler = stubs.module("synthDriverHandler")
	synthDriverHandler.getSynth = lambda: SimpleNamespace(name="notWorldVoice")

	alias_package(monkeypatch, "synthDrivers")
	alias_package(monkeypatch, "synthDrivers.WorldVoice", WORLDVOICE)

	speech_commands = stubs.module("synthDrivers.WorldVoice.speechCommands")

	class WVLangChangeCommand(LangChangeCommand):
		pass

	speech_commands.WVLangChangeCommand = WVLangChangeCommand

	recorder = stubs.module("synthDrivers.WorldVoice.pipeline.recorder")

	class PipelineLog:
		"""Keeps what the pipeline passes; it has no write, so a test that logs must replace pl."""

		def __init__(self, *args):
			self.args = args

	recorder.PipelineLog = PipelineLog

	settingsModule = stubs.module("synthDrivers.WorldVoice.pipeline.settings")
	settingsModule.pipeline_settings = SimpleNamespace(effective=lambda supports_roles: settings)
	settingsModule.read_stored = lambda section, key, default: section.get(key, default)

	load_source(monkeypatch, "synthDrivers.WorldVoice.pipeline", WORLDVOICE / "pipeline/__init__.py")
	# The stage table imports every stage module.
	importlib.import_module("synthDrivers.WorldVoice.pipeline.registry")
	return PipelineModules(settings), BreakCommand


def punctuation_settings(wait_factor, remove_characters=False):
	return SimpleNamespace(
		number_mode="value",
		scope="WorldVoice",
		punctuation_pause_characters=".,",
		punctuation_pause_enabled=True,
		remove_punctuation_characters=remove_characters,
		scaled_item_wait=lambda: 0,
		scaled_number_wait=lambda: 0,
		scaled_unspaced_script_space_wait=lambda: 0,
		scaled_punctuation_wait=lambda: wait_factor,
		group_size=3,
	)


# The log key of each stage in STAGES, in order: the thousands step logs as "number_mode", and so does
# the number stage, which the "number_language" switch also logs.
ORDER = [
	"apply_speech_dictionaries",
	"number_mode",
	"number_mode",
	"unspaced_script_space_wait_factor",
	"item_wait_factor",
	"punctuation_wait_factor",
	"number_wait_factor",
	"speech_viewer",
]
# One log switch per label, in the order of the stage that owns it.
LOG_SWITCH_ORDER = [
	"apply_speech_dictionaries",
	"number_language",
	"number_mode",
	"unspaced_script_space_wait_factor",
	"item_wait_factor",
	"punctuation_wait_factor",
	"number_wait_factor",
	"speech_viewer",
]


def load_settings_module(monkeypatch, conf, errors=None, warnings=None, validate="configobj.validate"):
	"""pipeline/settings.py over stub NVDA modules.

	errors and warnings collect the arguments of log.error and log.debugWarning. validate names
	the module that provides ValidateError: configobj's, the old top-level shim, or None for none.
	"""
	stubs = StubModules(monkeypatch)
	config = stubs.module("config")
	config.conf = conf
	addon_handler = stubs.module("addonHandler")
	addon_handler.initTranslation = lambda: None
	log_handler = stubs.module("logHandler")
	log_handler.log = SimpleNamespace(
		error=lambda *args, **kwargs: (errors if errors is not None else []).append(args),
		debugWarning=lambda *args, **kwargs: (warnings if warnings is not None else []).append(args),
	)
	# None in sys.modules makes an import of that name fail.
	for name in ("configobj", "configobj.validate", "validate"):
		monkeypatch.setitem(sys.modules, name, None)
	if validate == "configobj.validate":
		configobj_stub(stubs)
	elif validate == "validate":
		stubs.module("validate", ValidateError=type("ShimValidateError", (Exception,), {}))
	synth_driver_handler = stubs.module("synthDriverHandler")
	synth_driver_handler.getSynth = lambda: None
	stubs.translation()
	# Inside an alias package, so the settings' relative import of the number-language values resolves.
	alias_package(monkeypatch, "pipeline_settings_under_test")
	alias_package(monkeypatch, "pipeline_settings_under_test.pipeline")
	load_source(monkeypatch, "pipeline_settings_under_test.numberLanguage", WORLDVOICE / "numberLanguage.py")
	return load_source(
		monkeypatch,
		"pipeline_settings_under_test.pipeline.settings",
		WORLDVOICE / "pipeline/settings.py",
	)


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
		"NUMBER_LANGUAGE_CHOICES": settings_module.NUMBER_LANGUAGE_CHOICES,
		"FOLLOW": settings_module.FOLLOW,
		"MAIN": settings_module.MAIN,
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


def load_nvda_character_processing(monkeypatch, tmp_path):
	"""NVDA's real characterProcessing over ref/nvda's symbol tables, with its built-in dictionaries."""
	if not CHARACTER_PROCESSING.is_file():
		pytest.skip("ref/nvda is not checked out")
	stubs = StubModules(monkeypatch)
	stubs.translation()
	monkeypatch.setattr(builtins, "pgettext", lambda context, text: text, raising=False)
	stubs.module(
		"NVDAState",
		shouldWriteToDisk=lambda: False,
		WritePaths=SimpleNamespace(
			getSymbolsConfigFile=lambda locale: str(tmp_path / f"symbols-{locale}.dic"),
		),
	)
	ignore = lambda *args, **kwargs: None
	stubs.module(
		"logHandler",
		log=SimpleNamespace(debug=ignore, debugWarning=ignore, error=ignore, exception=ignore),
	)
	stubs.module("globalVars", appDir=str(REF / "nvda/source"))
	stubs.module("config", conf={"speech": {"symbolDictionaries": ["cldr"]}})
	stubs.module("addonHandler", getRunningAddons=list)
	character_processing = load_source(monkeypatch, "characterProcessing", CHARACTER_PROCESSING)
	character_processing._addSymbolDefinitions()
	return character_processing
