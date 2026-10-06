import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

WORLDVOICE = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"


def _load_synth_class(environment):
	"""Execute the real driver class with NVDA's unavailable services replaced."""
	tree = ast.parse((WORLDVOICE / "__init__.py").read_text(encoding="utf-8"))
	driver = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SynthDriver")
	exec(
		compile(ast.Module(body=[driver], type_ignores=[]), str(WORLDVOICE / "__init__.py"), "exec"),
		environment,
	)
	return environment["SynthDriver"]


def _assembly():
	spec = importlib.util.spec_from_file_location("lifecycle_assembly", WORLDVOICE / "assembly.py")
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return {name: getattr(module, name) for name in ("Teardown", "timed", "patch_attribute")}


def _construction_environment(failure, changes, close_error=None):
	panel = object()
	spelling = object()
	settings_dialogs = types.SimpleNamespace(VoiceSettingsPanel=panel)
	speech_api = types.SimpleNamespace(speakSpelling=spelling)
	gui = types.SimpleNamespace(settingsDialogs=settings_dialogs)
	speech = types.SimpleNamespace(speech=speech_api)

	class TaskManager:
		def __init__(self, output=None, logger=None):
			changes.append("task started")

		def on_event(self, event):
			pass

		def on_events(self, supplier):
			pass

		def shutdown(self, playbacks=()):
			changes.append("task stopped")

	class VoiceManager:
		playback_ports = ()
		allLanguages = ("en",)
		waitfactor = 0

		def __init__(
			self,
			taskManager,
			settings=None,
			bridge=None,
			*,
			index_ledger,
			completion_for,
			engine_classes,
			conf_provider,
			get_language,
		):
			assert index_ledger is bridge.ledger
			assert callable(completion_for)
			assert engine_classes == {"A": object}
			assert conf_provider() is environment["config"].conf
			assert get_language() == "en"
			if failure == "manager":
				raise RuntimeError("no voices")
			changes.append("engine started")

		def terminate(self, *, commit=True):
			# Only a failed construction discards unsaved voice settings.
			assert commit is (failure is None)
			changes.append("engine stopped")

	class Bridge:
		def __init__(self, *args, index_ledger, **kwargs):
			self.ledger = index_ledger

		def start(self, handler, *, batch_handler):
			assert handler.__self__ is batch_handler.__self__
			changes.append("bridge started")
			if failure == "bridge":
				raise RuntimeError("bridge failure")

		def close(self):
			changes.append("bridge stopped")
			if close_error is not None:
				raise close_error

	class Ledger:
		def close(self):
			changes.append("ledger stopped")

	class SpeechSymbols:
		def load(self, path):
			if failure == "symbols":
				raise RuntimeError("dictionary failure")
			changes.append("symbols loaded")

	class LanguageDetector:
		def __init__(self, languages, symbols, **providers):
			assert set(providers) == {"settings", "language"}
			changes.append("detector built")

		def add_detected_language_commands(self, sequence):
			return sequence

	class Action:
		def __init__(self, label):
			self.label = label

		def notify(self):
			changes.append(self.label)

	commands = {
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
	}

	def apply_pipeline():
		if failure == "pipeline":
			raise RuntimeError("pipeline failure")
		changes.append("pipeline started")

	def clear_pipeline():
		changes.append("pipeline stopped")

	repositories = []

	class NVDASynthDriver:
		pass

	logged = []

	def unavailable_synth():
		# NVDA's setSynth clears its current synth before constructing the next one.
		raise AssertionError("getSynth() is None while the synth is constructed")

	environment = {
		"SynthDriver": NVDASynthDriver,
		"synthIndexReached": object(),
		"synthDoneSpeaking": object(),
		"WVStart": Action("start"),
		"WVEnd": Action("end"),
		"time": types.SimpleNamespace(perf_counter=lambda: 0),
		"nvdaLog": types.SimpleNamespace(
			debug=lambda *args: None,
			error=lambda *args, **kwargs: logged.append(args),
		),
		"pipeline_scope": types.SimpleNamespace(
			worldvoice_started=apply_pipeline,
			worldvoice_ended=clear_pipeline,
		),
		"pipeline_settings": types.SimpleNamespace(
			get=lambda: types.SimpleNamespace(global_wait_factor=10),
			subscribe=lambda listener: changes.append("settings subscribed"),
			unsubscribe=lambda listener: changes.append("settings unsubscribed"),
		),
		"gui": gui,
		"WorldVoiceVoiceSettingsPanel": object(),
		"TaskManager": TaskManager,
		"VoiceManager": VoiceManager,
		"CompletionPolicy": lambda **options: types.SimpleNamespace(select=lambda voice_class, core: None),
		"versionInfo": types.SimpleNamespace(version="test"),
		"ready_engine_classes": lambda engine_config: {"A": object},
		"IndexLedger": Ledger,
		"NvdaEventBridge": Bridge,
		"ConfigVoiceSettingsRepository": lambda *args, **kwargs: (
			repositories.append((args, kwargs)) or object()
		),
		"VoiceSettingsStore": lambda repository: object(),
		"config": types.SimpleNamespace(conf={"WorldVoice": {"engine": {}}}),
		"getSynth": unavailable_synth,
		"languageHandler": types.SimpleNamespace(getLanguage=lambda: "en"),
		"speech": speech,
		"SpeechSymbols": SpeechSymbols,
		"filter_speechSequence": types.SimpleNamespace(
			unregister=lambda handler: changes.append("filter unregistered"),
		),
		"languageDetection": types.SimpleNamespace(LanguageDetector=LanguageDetector),
		"detection_settings": types.SimpleNamespace(
			subscribe=lambda listener: changes.append("detection subscribed"),
			unsubscribe=lambda listener: changes.append("detection unsubscribed"),
		),
		"listable": lambda function: function,
		**_assembly(),
		**commands,
	}
	return types.SimpleNamespace(
		environment=environment,
		settings_dialogs=settings_dialogs,
		panel=panel,
		speech_api=speech_api,
		spelling=spelling,
		repositories=repositories,
		logged=logged,
	)


@pytest.mark.parametrize("failure", ["manager", "symbols", "bridge"])
def test_failed_synth_construction_releases_acquired_resources(failure):
	changes = []
	built = _construction_environment(failure, changes)
	environment, settings_dialogs, panel = built.environment, built.settings_dialogs, built.panel
	speech_api, spelling = built.speech_api, built.spelling
	with pytest.raises(RuntimeError, match="no voices|dictionary failure|bridge failure"):
		_load_synth_class(environment)()

	assert settings_dialogs.VoiceSettingsPanel is panel
	assert speech_api.speakSpelling is spelling
	assert "task stopped" in changes
	assert "bridge stopped" in changes
	assert changes.index("task stopped") < changes.index("bridge stopped")
	assert changes.index("bridge stopped") < changes.index("ledger stopped")
	if "engine stopped" in changes:
		assert changes.index("engine stopped") < changes.index("ledger stopped")
	# Stages register last, so a construction that failed earlier never started them.
	assert "pipeline started" not in changes and "pipeline stopped" not in changes
	assert changes.count("end") == 1
	assert changes.count("settings subscribed") == changes.count("settings unsubscribed")
	if failure == "symbols":
		assert "engine stopped" in changes
		assert changes.index("bridge stopped") < changes.index("engine stopped")


def test_detection_settings_unsubscribe_before_the_filter_unregisters():
	changes = []
	_load_synth_class(_construction_environment(None, changes).environment)().terminate()
	assert changes.count("detection subscribed") == changes.count("detection unsubscribed") == 1
	assert changes.index("detection unsubscribed") < changes.index("filter unregistered")


def test_construction_failing_after_detection_subscribed_unsubscribes():
	changes = []
	with pytest.raises(RuntimeError, match="pipeline failure"):
		_load_synth_class(_construction_environment("pipeline", changes).environment)()
	assert changes.count("detection subscribed") == changes.count("detection unsubscribed") == 1
	assert changes.index("detection unsubscribed") < changes.index("filter unregistered")


def test_entry_points_are_silent_after_terminate():
	# NVDA may cancel speech from any thread while it is switching synths.
	changes = []
	driver = _load_synth_class(_construction_environment(None, changes).environment)()
	driver.terminate()
	driver.speak([])
	driver.cancel()
	driver.pause(True)


def test_stages_register_after_symbols_and_detector():
	changes = []
	_load_synth_class(_construction_environment(None, changes).environment)()
	assert changes.index("symbols loaded") < changes.index("pipeline started")
	assert changes.index("detector built") < changes.index("pipeline started")


def _load_voice_manager(monkeypatch):
	package_name = "lifecycle_test_worldvoice"
	for name in tuple(sys.modules):
		if name.startswith(package_name + "."):
			monkeypatch.delitem(sys.modules, name)
	package = types.ModuleType(package_name)
	package.__path__ = [str(WORLDVOICE)]
	monkeypatch.setitem(sys.modules, package_name, package)
	config = types.SimpleNamespace(
		conf={
			"WorldVoice": {
				"autoLanguageSwitching": {
					"KeepMainLocaleEngineConsistent": False,
					"KeepMainLocaleParameterConsistent": False,
				},
				"engine": {},
			},
		},
	)
	monkeypatch.setitem(sys.modules, "config", config)
	monkeypatch.setitem(sys.modules, "languageHandler", types.SimpleNamespace(getLanguage=lambda: "en"))
	monkeypatch.setitem(
		sys.modules,
		"logHandler",
		types.SimpleNamespace(
			log=types.SimpleNamespace(
				debug=lambda *args: None,
				error=lambda *args, **kwargs: None,
			),
		),
	)
	monkeypatch.setitem(
		sys.modules,
		"synthDriverHandler",
		types.SimpleNamespace(
			VoiceInfo=lambda id, displayName, language: types.SimpleNamespace(
				id=id,
				displayName=displayName,
				language=language,
			),
		),
	)
	name = f"{package_name}.voiceManager"
	spec = importlib.util.spec_from_file_location(name, WORLDVOICE / "voiceManager.py")
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, name, module)
	spec.loader.exec_module(module)
	return module


def init_policies(manager):
	"""Give a bare manager the policies the composition root would inject."""
	config = sys.modules["config"]
	manager._init_policies(lambda: config.conf, lambda: "en")


def manager_providers():
	config = sys.modules["config"]
	return {"conf_provider": lambda: config.conf, "get_language": lambda: "en"}


def test_voice_manager_logs_close_failures_under_the_published_engine_name(monkeypatch):
	class Engine:
		engine = "class-name"

	def fail(*args):
		raise RuntimeError("close failed")

	module = _load_voice_manager(monkeypatch)
	errors = []
	monkeypatch.setattr(
		module,
		"log",
		types.SimpleNamespace(
			error=lambda message, *args, **kwargs: errors.append(message % args),
		),
	)
	manager = object.__new__(module.VoiceManager)
	init_policies(manager)
	manager.taskManager = object()
	manager._terminated = False
	manager._instanceCache = {}
	manager.settings = types.SimpleNamespace(names=lambda: ())
	manager._bridge = types.SimpleNamespace(unbind=fail)
	manager._resources = {
		"published": module.EngineResource(
			"published",
			Engine,
			None,
			types.SimpleNamespace(close=fail, source_id=object()),
			None,
		),
	}
	manager.terminate()
	assert errors == ["Failed to unbind engine published", "Failed to close engine published"]


def test_drain_configuration_failure_rolls_back_previously_opened_engines(monkeypatch):
	closed, bound = [], {}

	class Engine:
		@classmethod
		def create_core(cls):
			core = types.SimpleNamespace()
			if cls.engine == "first":
				core.speak_segment = lambda *args, **kwargs: None
			return core

		@classmethod
		def destroy_core(cls, core):
			closed.append(cls.engine)

		@classmethod
		def supportedSettings(cls):
			return []

		@classmethod
		def voices(cls, core):
			return []

	class First(Engine):
		engine = "first"

	class Broken(Engine):
		engine = "broken"

	module = _load_voice_manager(monkeypatch)
	models = importlib.import_module(module.__package__ + ".runtime.models")
	from runtime_harness import MemoryRepository

	store = module.VoiceSettingsStore(MemoryRepository())

	def bind(source, source_id, **kwargs):
		bound[source_id] = source

	bridge = types.SimpleNamespace(
		bind=bind,
		unbind=lambda source_id: bound.pop(source_id, None),
		segment_sink=lambda source, context: lambda event: None,
	)
	with pytest.raises(ValueError, match="speak_segment"):
		module.VoiceManager(
			object(),
			store,
			bridge,
			index_ledger=importlib.import_module(module.__package__ + ".indexLedger").IndexLedger(),
			completion_for=lambda cls, core: models.CompletionContract(
				models.CompletionMode.DRAIN,
				models.IndexRange(1, 9999),
			),
			engine_classes={"first": First, "broken": Broken},
			**manager_providers(),
		)
	assert closed == ["broken", "first"] and bound == {}


@pytest.mark.parametrize("error", [RuntimeError("bridge failure"), KeyboardInterrupt()])
def test_terminate_cleanup_logs_errors_but_lets_interrupts_through(error):
	changes = []
	built = _construction_environment(None, changes, close_error=error)
	driver = _load_synth_class(built.environment)()

	if isinstance(error, KeyboardInterrupt):
		with pytest.raises(KeyboardInterrupt):
			driver.terminate()
		assert built.logged == []
		assert "ledger stopped" not in changes
	else:
		driver.terminate()
		assert built.logged == [("WorldVoice terminate: %s", "event bridge close")]
		assert "ledger stopped" in changes
