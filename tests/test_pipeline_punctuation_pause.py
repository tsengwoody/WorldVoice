from types import ModuleType, SimpleNamespace
import importlib.util
import sys


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
	]:
		sys.modules.pop(name, None)

	config = ModuleType("config")
	config.conf = {
		"general": {"loggingLevel": "INFO"},
		"WorldVoice": {"log": {"enable": False}},
	}
	monkeypatch.setitem(sys.modules, "config", config)

	globalVars = ModuleType("globalVars")
	globalVars.speechDictionaryProcessing = True
	monkeypatch.setitem(sys.modules, "globalVars", globalVars)

	logHandler = ModuleType("logHandler")
	logHandler.log = SimpleNamespace(debug=lambda *args, **kwargs: None)
	monkeypatch.setitem(sys.modules, "logHandler", logHandler)

	commands = ModuleType("speech.commands")

	class BreakCommand:
		def __init__(self, time):
			self.time = time

	class LangChangeCommand:
		def __init__(self, lang=None):
			self.lang = lang

	commands.BreakCommand = BreakCommand
	commands.LangChangeCommand = LangChangeCommand
	monkeypatch.setitem(sys.modules, "speech.commands", commands)

	speech = ModuleType("speech")
	speech.speech = SimpleNamespace(processText=lambda *args, **kwargs: args[1])
	monkeypatch.setitem(sys.modules, "speech", speech)

	extensions = ModuleType("speech.extensions")
	extensions.filter_speechSequence = FakeSpeechSequenceFilter()
	monkeypatch.setitem(sys.modules, "speech.extensions", extensions)

	speechDictHandler = ModuleType("speechDictHandler")
	speechDictHandler.processText = lambda text: text
	monkeypatch.setitem(sys.modules, "speechDictHandler", speechDictHandler)

	synthDriverHandler = ModuleType("synthDriverHandler")
	synthDriverHandler.getSynth = lambda: SimpleNamespace(name="notWorldVoice")
	monkeypatch.setitem(sys.modules, "synthDriverHandler", synthDriverHandler)

	synthDrivers = ModuleType("synthDrivers")
	synthDrivers.__path__ = []
	monkeypatch.setitem(sys.modules, "synthDrivers", synthDrivers)

	worldVoice = ModuleType("synthDrivers.WorldVoice")
	worldVoice.__path__ = ["addon/synthDrivers/WorldVoice"]
	monkeypatch.setitem(sys.modules, "synthDrivers.WorldVoice", worldVoice)

	speechcommand = ModuleType("synthDrivers.WorldVoice._speechcommand")

	class WVLangChangeCommand(LangChangeCommand):
		pass

	speechcommand.WVLangChangeCommand = WVLangChangeCommand
	monkeypatch.setitem(sys.modules, "synthDrivers.WorldVoice._speechcommand", speechcommand)

	worldVoiceLog = ModuleType("synthDrivers.WorldVoice.log")

	class PipelineLog:
		def __init__(self, *args, **kwargs):
			pass

	worldVoiceLog.PipelineLog = PipelineLog
	monkeypatch.setitem(sys.modules, "synthDrivers.WorldVoice.log", worldVoiceLog)

	settingsModule = ModuleType("synthDrivers.WorldVoice.pipeline.settings")
	settingsModule.get_effective_pipeline_settings = lambda: settings
	monkeypatch.setitem(sys.modules, "synthDrivers.WorldVoice.pipeline.settings", settingsModule)

	spec = importlib.util.spec_from_file_location(
		"synthDrivers.WorldVoice.pipeline",
		"addon/synthDrivers/WorldVoice/pipeline/__init__.py",
	)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module, BreakCommand


def punctuation_settings(wait_factor, remove_characters=False):
	return SimpleNamespace(
		ignore_comma_between_number=False,
		number_mode="value",
		punctuation_pause_characters=".,",
		punctuation_pause_enabled=True,
		remove_punctuation_characters=remove_characters,
		scaled_item_wait=lambda: 0,
		scaled_number_wait=lambda: 0,
		scaled_chinesespace_wait=lambda: 0,
		scaled_punctuation_wait=lambda: wait_factor,
		scaled_pair_wait=lambda: 0,
	)


def run_punctuation_filters(module, speech_sequence):
	return list(module.inject_punctuation_pause(speech_sequence))


def test_zero_punctuation_wait_factor_preserves_existing_text_and_breaks(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0))
	existing_break = BreakCommand(30)

	result = run_punctuation_filters(module, ["Hello.", existing_break, "World"])

	assert result == ["Hello.", existing_break, "World"]


def test_positive_punctuation_wait_factor_inserts_a_punctuation_break(monkeypatch):
	module, _BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(250))

	result = list(module.inject_punctuation_pause(["Hello. World"]))

	assert result[0] == "Hello"
	assert result[1] == "."
	assert type(result[2]).__name__ == "PunctuationBreakCommand"
	assert result[2].time == 250
	assert result[3] == " World"


def test_removing_configured_punctuation_preserves_existing_breaks(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(250, remove_characters=True))
	existing_break = BreakCommand(30)

	result = run_punctuation_filters(module, ["Hello.", existing_break, "World"])

	assert result == ["Hello", existing_break, "World"]


def test_removal_uses_pause_points_even_with_zero_wait_or_disabled_pause_control(monkeypatch):
	settings = punctuation_settings(0, remove_characters=True)
	module, _BreakCommand = load_pipeline_module(monkeypatch, settings)
	assert "".join(run_punctuation_filters(module, ["Hello, world."])) == "Hello world."

	settings.scaled_punctuation_wait = lambda: 250
	settings.punctuation_pause_enabled = False
	assert "".join(run_punctuation_filters(module, ["Hello, world."])) == "Hello world."


def test_removal_applies_at_pause_points_with_or_without_new_breaks(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(250, remove_characters=True))
	existing_break = BreakCommand(30)

	result = run_punctuation_filters(module, ["Hello. World.", existing_break, "."])

	assert result[0] == "Hello"
	assert type(result[1]).__name__ == "PunctuationBreakCommand"
	assert result[1].time == 250
	assert result[2] == " World"
	assert result[3] is existing_break
	assert result[4] == "."
	assert len(result) == 5


def test_removal_preserves_numeric_punctuation_without_a_pause(monkeypatch):
	module, _BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(250, remove_characters=True))

	result = run_punctuation_filters(module, ["Value 3.5 and 12,500. Next"])

	assert result[0] == "Value 3.5 and 12,500"
	assert type(result[1]).__name__ == "PunctuationBreakCommand"
	assert result[2] == " Next"


def test_removal_applies_to_pause_between_text_items(monkeypatch):
	module, _BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(250, remove_characters=True))

	result = run_punctuation_filters(module, ["Hello.", "World"])

	assert result[0] == "Hello"
	assert type(result[1]).__name__ == "PunctuationBreakCommand"
	assert result[2] == "World"


def test_zero_wait_removes_pause_point_before_an_existing_break(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0, remove_characters=True))
	existing_break = BreakCommand(30)

	result = run_punctuation_filters(module, ["Hello.", existing_break, "World"])

	assert result == ["Hello", existing_break, "World"]


def test_pause_filter_is_registered_when_wait_is_zero(monkeypatch):
	module, _BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0, remove_characters=True))
	monkeypatch.setattr(module.speech_dictionary, "install", lambda: None)
	module.static_register()

	assert module.inject_punctuation_pause in sys.modules["speech.extensions"].filter_speechSequence.registered
