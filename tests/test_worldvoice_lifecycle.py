import importlib
import sys
import types

import pytest
from addon_loader import WORLDVOICE, load_source
from nvda_stubs import worldvoice_conf
from worldvoice_harness import (
	init_policies,
	load_synth_class,
	load_voice_manager,
	number_language_choice_class,
)


def _bringup():
	module = load_source(None, "lifecycle_bringup", WORLDVOICE / "bringup.py", register=False)
	return {name: getattr(module, name) for name in ("Teardown", "timed", "patch_attribute")}


def _construction_environment(failure, changes, close_error=None):
	panel = object()
	spelling = object()
	settings_dialogs = types.SimpleNamespace(VoiceSettingsPanel=panel)
	speech_api = types.SimpleNamespace(speakSpelling=spelling)
	gui = types.SimpleNamespace(settingsDialogs=settings_dialogs)
	speech = types.SimpleNamespace(speech=speech_api)
	detectors = []

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
		all_languages = ("en",)
		waitfactor = 0

		def __init__(
			self,
			task_manager,
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
		def __init__(self, *args, indexLedger, **kwargs):
			self.ledger = indexLedger

		def start(self, handler, *, batchHandler):
			assert handler.__self__ is batchHandler.__self__
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

	class LanguageDetector:
		def __init__(self, languages, **providers):
			assert set(providers) == {"settings", "language", "number_language"}
			detectors.append(providers)
			if failure == "detector":
				raise RuntimeError("detector failure")
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
		"BaseSynthDriver": NVDASynthDriver,
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
		"config": types.SimpleNamespace(conf=worldvoice_conf()),
		"getSynth": unavailable_synth,
		"languageHandler": types.SimpleNamespace(getLanguage=lambda: "en"),
		"FOLLOW": "default",
		"MAIN": "main",
		"NumberLanguageChoice": number_language_choice_class(),
		"speech": speech,
		"filter_speechSequence": types.SimpleNamespace(
			unregister=lambda handler: changes.append("filter unregistered"),
		),
		"LanguageDetector": LanguageDetector,
		"detection_settings": types.SimpleNamespace(
			subscribe=lambda listener: changes.append("detection subscribed"),
			unsubscribe=lambda listener: changes.append("detection unsubscribed"),
		),
		"listable": lambda function: function,
		**_bringup(),
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
		detectors=detectors,
	)


@pytest.mark.parametrize("failure", ["manager", "detector", "bridge"])
def test_failed_synth_construction_releases_acquired_resources(failure):
	changes = []
	built = _construction_environment(failure, changes)
	environment, settings_dialogs, panel = built.environment, built.settings_dialogs, built.panel
	speech_api, spelling = built.speech_api, built.spelling
	with pytest.raises(RuntimeError, match="no voices|detector failure|bridge failure"):
		load_synth_class(environment)()

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
	if failure == "detector":
		assert "engine stopped" in changes
		assert changes.index("bridge stopped") < changes.index("engine stopped")


def test_detection_settings_unsubscribe_before_the_filter_unregisters():
	changes = []
	load_synth_class(_construction_environment(None, changes).environment)().terminate()
	assert changes.count("detection subscribed") == changes.count("detection unsubscribed") == 1
	assert changes.index("detection unsubscribed") < changes.index("filter unregistered")


def test_construction_failing_after_detection_subscribed_unsubscribes():
	changes = []
	with pytest.raises(RuntimeError, match="pipeline failure"):
		load_synth_class(_construction_environment("pipeline", changes).environment)()
	assert changes.count("detection subscribed") == changes.count("detection unsubscribed") == 1
	assert changes.index("detection unsubscribed") < changes.index("filter unregistered")


def test_entry_points_are_silent_after_terminate():
	# NVDA may cancel speech from any thread while it is switching synths.
	changes = []
	driver = load_synth_class(_construction_environment(None, changes).environment)()
	driver.terminate()
	driver.speak([])
	driver.cancel()
	driver.pause(True)


def test_terminate_drops_the_number_language_choice():
	# Phase 40 review M1: the choice holds the voice manager, which terminate drops with the rest.
	driver = load_synth_class(_construction_environment(None, []).environment)()
	assert driver._numberLanguageChoice is not None
	driver.terminate()
	assert driver._voiceManager is None
	assert driver._numberLanguageChoice is None


def test_the_detector_reads_the_drivers_number_language():
	# Spelling follows the number language (phase 35 spec §5): the detector asks the driver each time.
	built = _construction_environment(None, [])
	driver = load_synth_class(built.environment)()
	(providers,) = built.detectors
	assert providers["number_language"]() == "default"
	driver._set_numlan("main")
	assert providers["number_language"]() == "main"


def test_the_driver_gives_the_voice_settings_repository_a_conf_provider():
	built = _construction_environment(None, [])
	load_synth_class(built.environment)()
	((args, kwargs),) = built.repositories
	(provider,) = args
	assert kwargs == {}
	config = built.environment["config"]
	assert provider() is config.conf
	config.conf = worldvoice_conf()
	assert provider() is config.conf


def test_stages_register_after_the_detector():
	changes = []
	load_synth_class(_construction_environment(None, changes).environment)()
	assert changes.index("detector built") < changes.index("pipeline started")


def manager_providers():
	config = sys.modules["config"]
	return {"conf_provider": lambda: config.conf, "get_language": lambda: "en"}


def test_voice_manager_logs_close_failures_under_the_published_engine_name(monkeypatch):
	class Engine:
		engine = "class-name"

	def fail(*args):
		raise RuntimeError("close failed")

	module = load_voice_manager(monkeypatch)
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
	manager.task_manager = object()
	manager._terminated = False
	manager._instance_cache = {}
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
		def createCore(cls):
			core = types.SimpleNamespace()
			if cls.engine == "first":
				core.speak_segment = lambda *args, **kwargs: None
			return core

		@classmethod
		def destroyCore(cls, core):
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

	module = load_voice_manager(monkeypatch)
	package = module.__package__.removesuffix(".voices")
	models = importlib.import_module(package + ".runtime.models")
	from runtime_harness import MemoryRepository

	store = module.VoiceSettingsStore(MemoryRepository())

	def bind(source, source_id, **kwargs):
		bound[source_id] = source

	bridge = types.SimpleNamespace(
		bind=bind,
		unbind=lambda source_id: bound.pop(source_id, None),
		segmentSink=lambda source, context: lambda event: None,
	)
	with pytest.raises(ValueError, match="speak_segment"):
		module.VoiceManager(
			object(),
			store,
			bridge,
			index_ledger=importlib.import_module(package + ".bridge.indexLedger").IndexLedger(),
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
	driver = load_synth_class(built.environment)()

	if isinstance(error, KeyboardInterrupt):
		with pytest.raises(KeyboardInterrupt):
			driver.terminate()
		assert built.logged == []
		assert "ledger stopped" not in changes
	else:
		driver.terminate()
		assert built.logged == [("WorldVoice terminate: %s", "event bridge close")]
		assert "ledger stopped" in changes
