"""Production manager, facade, adapter, session and bridge composition."""

import importlib
import sys
import threading
from concurrent.futures import CancelledError
from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, load_source
from nvda_stubs import StubModules
from runtime_harness import worker_alive
from waiting import HOLD_TIMEOUT, WAIT_TIMEOUT
from worldvoice_harness import (
	EventStub,
	bridge_binding,
	bridge_bindings,
	bridge_closed,
	consistency_roles,
	engine_resources,
	ledger_closed,
	load_synth_class,
	port_adapter,
	synth_terminated,
	voice_binding,
)


def _idle_token():
	"""A never-cancelled token that honours the CancellationView contract."""
	return SimpleNamespace(is_cancelled=lambda: False, add_callback=lambda callback: lambda: None)


def test_only_started_sessions_are_resolvable(composition):
	c = composition
	c.engine("failed", fail=True)
	c.engine("ok")
	manager = c.create()
	assert manager.resolve_playback("failed:a") is None
	assert manager.resolve_playback("ok:a") is not None
	# A failed create_core leaves no core behind; only the started engine opened one.
	assert [core.closes for core in c.cores] == [0]
	assert c.repo.saves == []


def test_default_voice_follows_the_injected_language(composition):
	composition.engine("x")
	assert composition.create(get_language=lambda: "zh").default_voice_name == "x:b"
	assert composition.create(get_language=lambda: "en").default_voice_name == "x:a"


def test_manager_keeps_the_injected_policy_and_roles(composition):
	c = composition
	c.engine("ok")
	policies = importlib.import_module(c.package + ".voices.mainLocalePolicy")
	roles_module = importlib.import_module(c.package + ".voices.roles")
	parameters = policies.ParameterConsistency(lambda: c.config.conf)
	roles = roles_module.ConfigRoleRepository(lambda: c.config.conf)
	manager = c.create(parameter_consistency=parameters, roles=roles)
	assert manager.parameter_consistency is parameters
	assert manager.roles is roles
	assert consistency_roles(manager.voice_consistency) is roles


def test_each_opened_engine_is_one_engine_resource(composition):
	c = composition
	classes = c.engine("first"), c.engine("second")
	c.engine("failed", fail=True)
	manager = c.create()
	assert [resource.engine for resource in engine_resources(manager).values()] == ["first", "second"]
	for resource, cls in zip(engine_resources(manager).values(), classes):
		assert resource.voice_class is cls
		assert resource.adapter.core is cls.opened is resource.binding.core
		assert resource.session is resource.binding.session is manager.resolve_playback(cls.engine + ":a")
		assert voice_binding(manager.get_voice_instance(cls.engine + ":a")) is resource.binding
	assert not hasattr(manager, "installEngine")
	manager.terminate(commit=False)
	assert engine_resources(manager) == {} and [cls.opened for cls in classes] == [None, None]


@pytest.mark.parametrize("failure", ["empty", "bind"])
def test_initialization_failure_closes_without_commit(composition, failure):
	c = composition
	c.engine("bad", empty=failure == "empty")
	if failure == "bind":
		original = c.bridge.bind

		def bind(source, source_id, **kwargs):
			original(source, source_id, **kwargs)
			raise RuntimeError("bind failed")

		c.bridge.bind = bind
	with pytest.raises(RuntimeError, match="No WorldVoice voices|bind failed"):
		c.create()
	assert c.cores[0].closes == 1
	assert bridge_bindings(c.bridge) == {}
	assert c.repo.saves == []


def test_an_unpublished_engine_is_never_visible(composition):
	c = composition
	c.engine("first"), c.engine("second")
	manager = c.create()
	first, second = engine_resources(manager)["first"], engine_resources(manager)["second"]
	second.published = False
	manager._set_voice_data()
	assert "second:a" not in manager.voice_infos and "first:a" in manager.voice_infos
	assert manager.playback_ports == (first.session,)
	assert manager.resolve_playback("second:a") is None
	with pytest.raises(KeyError):
		manager.get_voice_capabilities("second:a")
	with pytest.raises(KeyError):
		manager.get_voice_variants("second:a")


def test_after_terminate_nothing_resolves(composition):
	c = composition
	c.engine("ok")
	manager = c.create()
	manager.terminate(commit=False)
	assert manager.resolve_playback("ok:a") is None
	assert manager.playback_ports == ()
	with pytest.raises(KeyError):
		manager.get_voice_capabilities("ok:a")


def test_engines_open_in_engine_classes_order(composition):
	c = composition
	first, second = c.engine("first"), c.engine("second")
	manager = c.create(engine_classes={"second": second, "first": first})
	assert list(engine_resources(manager)) == ["second", "first"]
	assert [port.source_id for port in manager.playback_ports] == [
		engine_resources(manager)[name].session.source_id for name in ("second", "first")
	]


def test_engine_voices_are_listed_once_when_published(composition):
	c = composition
	cls = c.engine("ok")
	calls = []
	original = cls.voices
	cls.voices = classmethod(lambda cls_, core: calls.append(core) or original(core))
	manager = c.create()
	assert len(calls) == 1
	assert [spec.name for spec in engine_resources(manager)["ok"].voices] == ["ok:a", "ok:b"]
	assert [spec.name for spec in manager.table] == ["ok:a", "ok:b"]


def test_source_is_bound_before_engine_is_published(composition):
	c = composition
	c.engine("ok")
	original = c.bridge.bind

	def bind(source, source_id, **kwargs):
		# The manager is still being constructed; its enumeration hook observes
		# only a resource whose notifications can already reach the scheduler.
		original(source, source_id, **kwargs)

	c.bridge.bind = bind
	original_voices = c.engines["ok"].voices

	def voices(cls, core):
		assert bridge_binding(c.bridge, core) is not None
		return original_voices(core)

	c.engines["ok"].voices = classmethod(voices)
	assert c.create().resolve_playback("ok:a") is not None


def _config_repository(c):
	repository_module = importlib.import_module(c.package + ".voices.settingsRepository")
	c.store._repository = repository_module.ConfigVoiceSettingsRepository(c.config.conf)


@pytest.mark.parametrize("during_edit", [False, True])
def test_first_voice_resolution_inherits_main_values_and_keeps_cancel_baseline(composition, during_edit):
	c = composition
	c.engine("ok")
	conf = c.config.conf
	conf["WorldVoice"]["voices"] = {"ok:a": {"rate": "83"}}
	conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
	_config_repository(c)
	manager = c.create()
	edit = c.store.begin_edit() if during_edit else None
	try:
		assert manager.default_voice_instance.rate == 83
		assert manager.resolve_playback("ok:b") is not None
		state = c.store.state("ok:b")
		assert state.get("rate") == 83
		if edit is None:
			edit = c.store.begin_edit()
		state.update(rate=72)
		voice = manager.get_voice_instance("ok:b")
		assert voice.rate == 72
		assert c.store.state("ok:b") is state
		edit.discard()
		assert voice.rate == 83
		assert conf["WorldVoice"]["voices"]["ok:b"]["rate"] == 50
	finally:
		if edit is not None:
			edit.close()


def test_voices_inherit_the_main_voice_once_it_exists_but_keep_their_variant(composition):
	c = composition
	c.engine("ok")
	conf = c.config.conf
	conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
	conf["WorldVoice"]["voices"] = {
		"ok:a": {"rate": "40", "variant": "own", "inflection": "35", "rateBoost": "False"},
		"ok:b": {"rate": "41", "variant": "own-b"},
	}
	_config_repository(c)
	manager = c.create()
	main = c.store.state("ok:a")
	# The main voice loads first, from its own values.
	assert (main.get("rate"), main.get("variant"), main.get("inflection")) == (40, "own", 35)
	assert manager.resolve_playback("ok:b") is not None
	lazy = c.store.state("ok:b")
	assert (lazy.get("rate"), lazy.get("variant"), lazy.get("inflection")) == (40, "own-b", 35)


def test_reload_takes_the_main_voice_parameters_while_they_are_kept_consistent(composition):
	# NVDA's loadSettings sets the main voice from the profile before WorldVoice reloads every voice.
	c = composition
	c.engine("ok")
	conf = c.config.conf
	flags = conf["WorldVoice"]["autoLanguageSwitching"]
	flags["KeepMainLocaleParameterConsistent"] = True
	conf["WorldVoice"]["voices"] = {"ok:a": {"rate": "40"}, "ok:b": {"rate": "41", "variant": "own-b"}}
	_config_repository(c)
	manager = c.create()
	other = manager.get_voice_instance("ok:b")
	c.store.state("ok:a").update(rate=83)
	manager.reload()
	assert (manager.default_voice_instance.rate, other.rate, other.variant) == (83, 83, "own-b")
	assert c.store.state("ok:b").baseline("rate") == 83
	flags["KeepMainLocaleParameterConsistent"] = False
	manager.reload()
	assert (manager.default_voice_instance.rate, other.rate) == (40, 41)


def test_manager_cancel_passes_sessions_without_core_access(composition):
	c = composition
	c.engine("ok")
	manager = c.create()
	received = []
	c.tasks.cancel = lambda playbacks=(): received.extend(playbacks)
	manager.cancel()
	assert received == [manager.resolve_playback("ok:a")]
	assert c.cores[0].cancels == 0


def test_normal_shutdown_saves_settings_without_a_facade(composition):
	c = composition
	c.engine("ok")
	manager = c.create()
	assert manager.resolve_playback("ok:b") is not None
	c.store.state("ok:b").update(rate=72)
	manager.terminate()
	assert c.repo.values["ok:b"]["rate"] == 72
	saves = list(c.repo.saves)
	manager.terminate()
	assert c.repo.saves == saves


def make_synth(c, manager):
	bringup = importlib.import_module(c.package + ".bringup")
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
	errors = []
	log = SimpleNamespace(error=lambda *args, **kwargs: errors.append(args))
	root = load_synth_class(
		{
			"SynthDriver": object,
			"synthIndexReached": object(),
			"synthDoneSpeaking": object(),
			"nvdaLog": log,
			**commands,
			**{name: getattr(bringup, name) for name in ("Teardown", "timed", "patch_attribute")},
		},
	)
	synth = object.__new__(root)
	synth._terminated = False
	synth._terminateCommit = True
	synth.taskManager, synth._eventBridge, synth._voiceManager = c.tasks, c.bridge, manager
	synth._indexLedger = c.ledger
	# Register the runtime cleanups as _initialize does once each object exists.
	synth._teardown = bringup.Teardown(root._TEARDOWN_ORDER, log)
	synth._teardown.add("index ledger close", c.ledger.close)
	synth._teardown.add("event bridge close", c.bridge.close)
	synth._teardown.add("task manager shutdown", lambda: c.tasks.shutdown(manager.playback_ports))
	synth._teardown.add("voice manager terminate", lambda: manager.terminate(commit=synth._terminateCommit))
	return synth, errors


@pytest.mark.parametrize("bridge_error", [False, True])
def test_worker_stops_before_bridge_and_sessions_close(composition, bridge_error):
	c = composition
	c.engine("ok")
	manager = c.create()
	entered, release, stopping = (threading.Event() for _ in range(3))
	core = c.cores[0]

	def speak(commands):
		entered.set()
		assert release.wait(HOLD_TIMEOUT)

	core.speak = speak
	request = c.tasks.new_request()
	c.tasks.append_speech(request, manager.resolve_playback("ok:a"), "ok:a", ("hello",))
	assert c.tasks.submit_request(request)
	assert entered.wait(WAIT_TIMEOUT)
	closed = []
	original_shutdown, original_close, original_terminate = c.tasks.shutdown, c.bridge.close, core.terminate

	def shutdown(playbacks=()):
		stopping.set()
		original_shutdown(playbacks)
		closed.append("worker")

	def close_bridge():
		assert not worker_alive(c.tasks)
		was_closed = bridge_closed(c.bridge)
		original_close()
		closed.append("bridge")
		if bridge_error and not was_closed:
			raise RuntimeError("bridge cleanup failure")

	def close_core():
		assert not worker_alive(c.tasks)
		assert bridge_closed(c.bridge)
		original_terminate()
		closed.append("session")

	c.tasks.shutdown, c.bridge.close, core.terminate = shutdown, close_bridge, close_core
	synth, errors = make_synth(c, manager)
	thread = threading.Thread(target=synth.terminate)
	try:
		thread.start()
		assert stopping.wait(WAIT_TIMEOUT)
		assert worker_alive(c.tasks)
		assert not bridge_closed(c.bridge)
		assert core.closes == 0
	finally:
		release.set()
		thread.join(WAIT_TIMEOUT)
	assert not thread.is_alive()
	assert len(errors) == int(bridge_error)
	assert closed == ["worker", "bridge", "session"]
	assert c.repo.saves


def test_save_or_engine_close_failure_does_not_abandon_other_resources(composition):
	c = composition
	c.engine("one")
	c.engine("two")
	manager = c.create()
	manager.get_voice_instance("two:a")
	c.repo.fail_next_save = True

	def close_failure():
		c.cores[1].closes += 1
		raise RuntimeError("close failure")

	c.cores[1].terminate = close_failure
	manager.terminate()
	assert [core.closes for core in c.cores] == [1, 1]
	assert {name for name, values in c.repo.saves} == {"one:a", "two:a"}
	assert bridge_bindings(c.bridge) == {}


def test_waitfactor_updates_declared_capability_without_activating(composition):
	c = composition
	c.engine("plain")
	capable = c.engine("extension")
	capable.extra_capabilities = frozenset({"waitfactor", "variant"})
	manager = c.create()
	manager.waitfactor = 4
	assert manager.get_voice_instance("extension:b").waitfactor == 4
	assert manager.get_voice_instance("plain:a").waitfactor == 0
	assert manager.get_voice_capabilities("extension:b").supports_variants
	assert not any(hasattr(core, "voice") for core in c.cores)


@pytest.mark.parametrize("submission", ["new", "building", "speak"])
def test_termination_closes_admission_before_blocking_cancel(composition, submission):
	c = composition
	c.engine("one")
	c.engine("two")
	manager = c.create()
	synth, errors = make_synth(c, manager)
	building = c.tasks.new_request()
	c.tasks.append_speech(building, manager.resolve_playback("one:a"), "one:a", ("pending",))
	entered, release = threading.Event(), threading.Event()

	def cancel():
		c.cores[0].cancels += 1
		entered.set()
		assert release.wait(HOLD_TIMEOUT)

	c.cores[0].cancel = cancel
	thread = threading.Thread(target=synth.terminate)
	try:
		thread.start()
		assert entered.wait(WAIT_TIMEOUT)
		assert synth_terminated(synth)
		if submission == "new":
			scheduler = importlib.import_module(c.package + ".runtime.scheduler")
			with pytest.raises(scheduler.InvalidRequestState):
				c.tasks.new_request()
		elif submission == "building":
			assert c.tasks.submit_request(building) is False
			assert building.token.is_cancelled()
		else:
			# Terminated entry points must return before touching pipeline or
			# facade dependencies, which may already be unavailable.
			assert synth.speak(["ignored"]) is None
		assert worker_alive(c.tasks)
		assert not bridge_closed(c.bridge)
		assert [core.closes for core in c.cores] == [0, 0]
	finally:
		release.set()
		thread.join(WAIT_TIMEOUT)
	assert not thread.is_alive()
	assert errors == []
	assert [core.cancels for core in c.cores] == [1, 1]
	assert [core.closes for core in c.cores] == [1, 1]
	assert not worker_alive(c.tasks)


def marker_contract(c):
	return c.models.CompletionContract(c.models.CompletionMode.END_INDEX, c.models.IndexRange(501, 510))


def test_resource_bound_before_first_encoded_speech(composition, nvda_commands):
	c = composition
	cls = c.engine("marker")
	selected = []
	contract = marker_contract(c)

	def completion_for(voice_class, core):
		assert voice_class is cls and core is cls.opened
		selected.append(core)
		return contract

	manager = c.create(completion_for)
	port = manager.resolve_playback("marker:a")
	spoken = []
	finished = threading.Event()

	def speak(commands):
		spoken.extend(commands)
		c.index.notify(synth=cls.opened, index=commands[-1].index)

	cls.opened.speak = speak
	c.done.register(lambda synth: finished.set() if synth is c.owner else None)
	request = c.tasks.new_request()
	original = nvda_commands.IndexCommand(42)
	c.tasks.append_speech(request, port, "marker:a", ("hello", original))
	assert c.tasks.submit_request(request)
	assert finished.wait(WAIT_TIMEOUT)
	assert [item.index for item in spoken if isinstance(item, nvda_commands.IndexCommand)] == [501, 502]
	assert original.index == 42
	assert selected == [cls.opened]
	assert port.completion == contract


def test_partial_bind_failure_releases_resources_without_commit(composition):
	c = composition
	c.engine("marker")
	original = c.bridge.bind
	source_ids = []

	def bind(source, source_id, **kwargs):
		original(source, source_id, **kwargs)
		source_ids.append(source_id)
		raise RuntimeError("partial marker bind")

	c.bridge.bind = bind
	with pytest.raises(RuntimeError, match="partial marker bind"):
		c.create(lambda cls, core: marker_contract(c))
	assert c.cores[0].closes == 1
	assert bridge_bindings(c.bridge) == {}
	with pytest.raises(
		importlib.import_module(c.package + ".bridge.indexLedger").InvalidIndexContext,
	):
		c.ledger.prepare(c.models.PlaybackContext(source_ids[0], 1), ())
	assert c.repo.saves == []


def test_shutdown_disables_late_index_before_engine_close(composition):
	c = composition
	cls = c.engine("marker")
	manager = c.create(lambda cls, core: marker_contract(c))
	port = manager.resolve_playback("marker:a")
	marker = c.ledger.prepare(c.models.PlaybackContext(port.source_id, 1), (42,)).endIndex
	received = []
	c.index.register(lambda synth, index: received.append(index) if synth is c.owner else None)
	original_close = cls.opened.terminate

	def close():
		assert bridge_closed(c.bridge)
		assert not ledger_closed(c.ledger)
		c.index.notify(synth=cls.opened, index=marker)
		original_close()

	cls.opened.terminate = close
	synth, errors = make_synth(c, manager)
	synth.terminate()
	assert received == []
	assert errors == []
	assert ledger_closed(c.ledger)


def test_completion_selection_failure_closes_opened_core(composition):
	c = composition
	c.engine("marker")

	def fail(cls, core):
		raise RuntimeError("policy failure")

	with pytest.raises(RuntimeError, match="policy failure"):
		c.create(fail)
	assert c.cores[0].closes == 1
	assert c.repo.saves == []


def test_live_core_rebind_preserves_allocator_high_water(composition, nvda_commands):
	c = composition
	cls = c.engine("marker")
	manager = c.create(lambda cls, core: marker_contract(c))
	port = manager.resolve_playback("marker:a")
	spoken = []
	cls.opened.speak = lambda commands: spoken.append(commands[-1].index)
	token = _idle_token()
	port.speak(("first",), token, context=c.models.PlaybackContext(port.source_id, 1))
	c.bridge.unbind(port.source_id)
	c.bridge.bind(cls.opened, port.source_id, completion=port.completion)
	port.speak(("second",), token, context=c.models.PlaybackContext(port.source_id, 2))
	assert spoken == [501, 502]
	assert cls.opened.closes == 0
	assert c.ledger.receiveIndex(port.source_id, 501) == ()


def test_entry_point_imports_real_ledger_and_completion_policy(monkeypatch, nvda_commands):
	"""Execute the entire addon module, including its real relative imports."""
	package = "worldvoice_entrypoint_import_test"
	stub = StubModules(monkeypatch).module

	stub("addonHandler", initTranslation=lambda: None)
	stub("autoSettingsUtils", __path__=[])
	stub(
		"autoSettingsUtils.driverSetting",
		BooleanDriverSetting=object,
		DriverSetting=object,
		NumericDriverSetting=object,
	)
	stub("autoSettingsUtils.utils", StringParameterInfo=object)
	stub("config", conf=SimpleNamespace(spec={}))
	stub("extensionPoints", Action=EventStub)
	stub("gui")
	stub("languageHandler")
	stub("logHandler", log=SimpleNamespace())
	stub("versionInfo", version="test")
	for name in (
		"CharacterModeCommand",
		"LangChangeCommand",
		"PitchCommand",
		"RateCommand",
		"VolumeCommand",
		"SpeechCommand",
	):
		monkeypatch.setattr(nvda_commands, name, type(name, (), {}), raising=False)
	stub("speech.extensions", filter_speechSequence=SimpleNamespace())
	stub(
		"synthDriverHandler",
		VoiceInfo=object,
		SynthDriver=type("SynthDriver", (), {}),
		synthIndexReached=EventStub(),
		synthDoneSpeaking=EventStub(),
		getSynth=lambda: None,
	)
	# Unrelated UI and pipeline modules need NVDA, but all changed composition
	# boundaries below are imported from their actual files by __init__.py.
	stub(package + ".languageDetection", __path__=[])
	stub(package + ".languageDetection.detector", LanguageDetector=object)
	stub(package + ".languageDetection.settings", DETECTION_CONFSPEC={}, detection_settings=SimpleNamespace())
	stub(package + ".pipeline", __path__=[])
	stub(
		package + ".pipeline.languageCommands",
		**{
			name: lambda *args: None
			for name in ("inject_langchange_reorder", "deduplicate_language_command", "lang_cmd_to_voice")
		},
	)
	stub(package + ".pipeline.numberStages", detect_with_number_language=lambda *args: None)
	stub(
		package + ".pipeline.registry",
		LOG_SWITCHES=(),
		**{name: lambda *args: None for name in ("order_move_to_start_register", "listable")},
	)
	stub(
		package + ".pipeline.settings",
		NUMBER_LANGUAGE_CHOICES=(),
		NUMBER_MODE_CHOICES=(),
		PIPELINE_CONFSPEC={},
		PIPELINE_SETTINGS=(),
		pipeline_settings=SimpleNamespace(),
	)
	stub(package + ".pipeline.context", GENERIC_CONTEXT=object(), SpeechContext=object)
	stub(package + ".pipeline.scope", pipeline_scope=SimpleNamespace())
	stub(package + ".engineRegistry", ready_engine_classes=lambda engine_config: {})
	stub(package + ".ui.voicePanel", WorldVoiceVoiceSettingsPanel=object)
	monkeypatch.setattr(sys, "path", list(sys.path))
	try:
		# __init__.py loads as a package, so its relative imports resolve inside the alias.
		module = load_source(monkeypatch, package, WORLDVOICE / "__init__.py")
		# The global plugin imports generics.coreArchive from the add-on root right after
		# importing this package, which must put that root on sys.path although it no longer
		# imports anything from it itself.
		assert sys.path[0] == str(WORLDVOICE.parents[1])
		ledger = importlib.import_module(package + ".bridge.indexLedger")
		policies = importlib.import_module(package + ".bridge.completionPolicies")
		models = importlib.import_module(package + ".runtime.models")
		assert module.IndexLedger is ledger.IndexLedger
		assert module.CompletionPolicy is policies.CompletionPolicy
		voice = SimpleNamespace(engine="unverified", drain_profile=None)
		contract, support = module.CompletionPolicy().contractFor(
			voice,
			object(),
			nvdaVersion="test",
			audioMode="test",
		)
		assert contract.mode is models.CompletionMode.LEGACY_DONE and support is None
		assert module.SynthDriver.__module__ == package
		assert ledger.__file__ == str(WORLDVOICE / "bridge/indexLedger.py")
		assert policies.__file__ == str(WORLDVOICE / "bridge/completionPolicies.py")
	finally:
		for name in tuple(sys.modules):
			if name.startswith(package + "."):
				monkeypatch.delitem(sys.modules, name, raising=False)


def drain_contract(c, mode="DRAIN"):
	return c.models.CompletionContract(getattr(c.models.CompletionMode, mode), c.models.IndexRange(1, 9999))


def runtime_completion_selector(c, version="synthetic"):
	policies = importlib.import_module(c.package + ".bridge.completionPolicies")
	logs = []
	policy = policies.CompletionPolicy(
		nvdaVersion=version,
		logger=SimpleNamespace(warning=lambda *args: logs.append(args)),
	)
	return policy.select, logs


def installed_drain_voice(c, monkeypatch, name="OneCore", *, supported=True):
	"""Replace unavailable native resources at the installed-driver boundary."""
	work = importlib.import_module(c.package + ".runtime.playbackWork")
	support_type = work.DrainSupport
	cls = c.engine(name)
	cls.drain_profile = work.DrainProfile(wasapi_dependent=name in ("OneCore", "SAPI5"))
	checked, spoken = [], []

	class SynthDriver(c.Core):
		def get_segment_drain_support(self, *, nvda_version, audio_mode):
			checked.append((nvda_version, audio_mode))
			return support_type(supported, "native-test-profile", "Native callback lifetime is unproven")

		def speak_segment(self, commands, token, *, context, on_event):
			spoken.append((commands, context))
			on_event(
				c.models.PlaybackEvent(
					c.models.EventKind.SEGMENT_DRAINED,
					context.source_id,
					segment_id=context.segment_id,
				),
			)

	cls.synth_driver_class = SynthDriver
	return SimpleNamespace(
		voice=cls,
		driver=SynthDriver,
		checked=checked,
		spoken=spoken,
		support_type=support_type,
	)


@pytest.mark.parametrize("engine", ["OneCore", "VE", "SAPI5"])
def test_supported_installed_wrapper_is_bound_before_first_drain_speech(
	composition,
	monkeypatch,
	nvda_commands,
	engine,
):
	c = composition
	installed = installed_drain_voice(c, monkeypatch, engine)
	if engine in ("OneCore", "SAPI5"):
		installed.driver.useWasapi = True
	configured = []
	configure = c.module.LegacyEngineAdapter.configureSegmentEvents

	def configure_after_bind(adapter, factory):
		assert bridge_binding(c.bridge, installed.voice.opened).source is installed.voice.opened
		configure(adapter, factory)
		configured.append(adapter)

	monkeypatch.setattr(c.module.LegacyEngineAdapter, "configureSegmentEvents", configure_after_bind)
	select, logs = runtime_completion_selector(c)
	manager = c.create(select)
	port = manager.resolve_playback(engine + ":a")
	assert port.completion.mode is c.models.CompletionMode.DRAIN
	assert configured == [port_adapter(port)]
	assert installed.checked == [("synthetic", "wasapi" if engine in ("OneCore", "SAPI5") else "default")]
	assert logs == []
	done, indexes = threading.Event(), []
	c.done.register(lambda synth: done.set() if synth is c.owner else None)
	c.index.register(lambda synth, index: indexes.append(index) if synth is c.owner else None)
	request = c.tasks.new_request()
	c.tasks.append_speech(request, port, engine + ":a", ("hello", nvda_commands.IndexCommand(42)))
	assert c.tasks.submit_request(request) and done.wait(WAIT_TIMEOUT)
	commands, context = installed.spoken[0]
	assert context.source_id is port.source_id
	assert [command.index for command in commands if isinstance(command, nvda_commands.IndexCommand)] == [1]
	assert indexes == [42]
	with pytest.raises(RuntimeError, match="before speech"):
		port._adapter.configureCompletion(c.models.CompletionContract())
	policies = importlib.import_module(c.package + ".bridge.completionPolicies")
	assert policies._VERIFIED_CONTRACTS == {}


@pytest.mark.parametrize("outcome", ["failure", "cancel"])
def test_new_installed_wrapper_retains_request_identity_on_failure_or_cancel(
	composition,
	monkeypatch,
	nvda_commands,
	outcome,
):
	c = composition
	installed = installed_drain_voice(c, monkeypatch, "SAPI5")
	installed.driver.useWasapi = True
	selected, _ = runtime_completion_selector(c)
	manager = c.create(selected)
	port = manager.resolve_playback("SAPI5:a")
	assert port.completion.mode is c.models.CompletionMode.DRAIN
	entered = threading.Event()
	calls = []

	def hold(self, commands, token, *, context, on_event):
		calls.append((context, on_event))
		entered.set()

	installed.driver.speak_segment = hold
	request = c.tasks.new_request()
	future = c.tasks.append_speech(request, port, "SAPI5:a", ("first",))
	assert c.tasks.submit_request(request) and entered.wait(WAIT_TIMEOUT)
	context, sink = calls[0]
	if outcome == "failure":
		error = RuntimeError("native playback failed")
		sink(
			c.models.PlaybackEvent(
				c.models.EventKind.SEGMENT_FAILED,
				context.source_id,
				segment_id=context.segment_id,
				error=error,
			),
		)
		with pytest.raises(RuntimeError, match="native playback failed"):
			future.result(WAIT_TIMEOUT)
		assert request.state.name == "FAILED"
	else:
		c.tasks.cancel((port,))
		sink(
			c.models.PlaybackEvent(
				c.models.EventKind.SEGMENT_DRAINED,
				context.source_id,
				segment_id=context.segment_id,
			),
		)
		with pytest.raises(CancelledError):
			future.result(WAIT_TIMEOUT)
		assert future.cancelled()
		assert request.state.name == "CANCELLED"


@pytest.mark.parametrize(
	"use_wasapi,audio_mode,completion_mode",
	[
		(True, "wasapi", "DRAIN"),
		(False, "legacy", "LEGACY_DONE"),
		("absent", "unknown", "LEGACY_DONE"),
		(None, "unknown", "LEGACY_DONE"),
	],
)
def test_wasapi_mode_sensitive_support_uses_actual_opened_core(
	composition,
	monkeypatch,
	use_wasapi,
	audio_mode,
	completion_mode,
):
	c = composition
	installed = installed_drain_voice(c, monkeypatch, "OneCore")
	if use_wasapi != "absent":
		installed.driver.useWasapi = use_wasapi
	checked = []

	def support(self, *, nvda_version, audio_mode):
		checked.append((nvda_version, audio_mode))
		return installed.support_type(
			audio_mode == "wasapi",
			"mode-sensitive-test-profile",
			"Only the reviewed WASAPI audio profile is supported",
		)

	installed.driver.get_segment_drain_support = support
	select, logs = runtime_completion_selector(c)
	manager = c.create(select)
	port = manager.resolve_playback("OneCore:a")
	assert checked == [("synthetic", audio_mode)]
	assert port.completion.mode is getattr(c.models.CompletionMode, completion_mode)
	assert len(logs) == (0 if completion_mode == "DRAIN" else 1)
	policies = importlib.import_module(c.package + ".bridge.completionPolicies")
	assert policies._VERIFIED_CONTRACTS == {}


@pytest.mark.parametrize("engine", ["OneCore", "Espeak"])
@pytest.mark.parametrize(
	"failure",
	[
		"wrong_core",
		"missing_entry",
		"missing_support",
		"invalid_support",
		"truthy_support",
		"unsupported",
		"support_error",
	],
)
def test_unconfirmed_wrapper_uses_legacy_and_logs_concrete_fallback_once(
	composition,
	monkeypatch,
	engine,
	failure,
):
	c = composition
	installed = installed_drain_voice(c, monkeypatch, engine)
	cls = installed.voice
	if failure == "wrong_core":

		def foreign_core(voice):
			voice.opened = c.Core()
			return voice.opened

		cls.create_core = classmethod(foreign_core)
	elif failure == "missing_entry":
		installed.driver.speak_segment = None
	elif failure == "missing_support":
		installed.driver.get_segment_drain_support = None
	elif failure == "invalid_support":
		installed.driver.get_segment_drain_support = lambda *args, **kwargs: SimpleNamespace(supported=True)
	elif failure == "truthy_support":
		installed.driver.get_segment_drain_support = lambda *args, **kwargs: installed.support_type(
			"yes",
			"native-test-profile",
			"Not an explicit boolean support decision",
		)
	elif failure == "unsupported":
		installed.driver.get_segment_drain_support = lambda *args, **kwargs: installed.support_type(
			False,
			"native-test-profile",
			"Native callback lifetime is unproven",
		)
	elif failure == "support_error":

		def fail(*args, **kwargs):
			raise RuntimeError("Native profile inspection failed")

		installed.driver.get_segment_drain_support = fail
	select, logs = runtime_completion_selector(c)
	manager = c.create(select)
	port = manager.resolve_playback(engine + ":a")
	assert port.completion.mode is c.models.CompletionMode.LEGACY_DONE
	assert port.completion.index_range is None
	assert select(cls, cls.opened) == port.completion
	assert len(logs) == 1
	assert "LEGACY_DONE" in logs[0][0] and logs[0][-1]
	if failure == "unsupported":
		assert logs[0][-1] == "Native callback lifetime is unproven"
	if failure == "support_error":
		assert "Native profile inspection failed" in logs[0][-1]


def test_drain_factory_configured_after_bind_before_publication(composition, monkeypatch, nvda_commands):
	c = composition
	cls = c.engine("drain")
	calls, setup = [], []
	cls.synth_driver_class.speak_segment = lambda core, commands, token, **kwargs: calls.append(kwargs)
	configure = c.module.LegacyEngineAdapter.configureSegmentEvents

	def configure_after_bind(adapter, factory):
		assert bridge_binding(c.bridge, cls.opened).source is cls.opened
		configure(adapter, factory)
		setup.append(adapter)

	monkeypatch.setattr(c.module.LegacyEngineAdapter, "configureSegmentEvents", configure_after_bind)
	manager = c.create(lambda cls, core: drain_contract(c))
	port = manager.resolve_playback("drain:a")
	context = c.models.PlaybackContext(port.source_id, 1)
	port.speak(("hello",), _idle_token(), context=context)
	assert len(setup) == 1
	assert calls[0]["context"] is context and callable(calls[0]["on_event"])


@pytest.mark.parametrize(
	"order,mode",
	[
		("drain_first", "DRAIN"),
		("drain_first", "END_INDEX_AND_DRAIN"),
		("end_first", "END_INDEX_AND_DRAIN"),
	],
)
def test_drain_request_integrates_encoded_indexes_and_native_events(composition, nvda_commands, mode, order):
	c = composition
	cls = c.engine("drain")
	cls.synth_driver_class.speak_segment = lambda *args, **kwargs: None
	manager = c.create(lambda cls, core: drain_contract(c, mode))
	port = manager.resolve_playback("drain:a")
	indexes, sinks, completed = [], [], threading.Event()
	c.index.register(lambda synth, index: indexes.append(index) if synth is c.owner else None)
	c.done.register(lambda synth: completed.set() if synth is c.owner else None)

	def speak(commands, token, *, context, on_event):
		sinks.append(on_event)
		drain = c.models.PlaybackEvent(
			c.models.EventKind.SEGMENT_DRAINED,
			context.source_id,
			segment_id=context.segment_id,
		)
		if mode == "END_INDEX_AND_DRAIN" and order == "end_first":
			c.index.notify(synth=cls.opened, index=commands[-1].index)
		on_event(drain)
		if mode == "END_INDEX_AND_DRAIN" and order == "drain_first":
			c.index.notify(synth=cls.opened, index=commands[-1].index)

	cls.opened.speak_segment = speak
	request = c.tasks.new_request()
	c.tasks.append_speech(
		request,
		port,
		"drain:a",
		(
			"hello",
			nvda_commands.IndexCommand(42),
			nvda_commands.IndexCommand(7),
		),
	)
	assert c.tasks.submit_request(request)
	assert completed.wait(WAIT_TIMEOUT)
	assert indexes == [42, 7] and len(sinks) == 1


@pytest.mark.parametrize("action", ["cancel", "unbind"])
def test_index_handler_revokes_remainder_of_drain_batch(composition, nvda_commands, action):
	c = composition
	cls = c.engine("drain")
	cls.synth_driver_class.speak_segment = lambda *args, **kwargs: None
	manager = c.create(lambda cls, core: drain_contract(c))
	port = manager.resolve_playback("drain:a")
	entered, returned = threading.Event(), threading.Event()
	indexes, completed = [], []
	c.done.register(lambda synth: completed.append(synth))

	def output(synth, index):
		if synth is c.owner:
			indexes.append(index)
			if action == "cancel":
				c.tasks.cancel((port,))
			else:
				c.bridge.unbind(port.source_id)

	c.index.register(output)

	def speak(commands, token, *, context, on_event):
		entered.set()
		on_event(
			c.models.PlaybackEvent(
				c.models.EventKind.SEGMENT_DRAINED,
				context.source_id,
				segment_id=context.segment_id,
			),
		)
		returned.set()

	cls.opened.speak_segment = speak
	request = c.tasks.new_request()
	future = c.tasks.append_speech(
		request,
		port,
		"drain:a",
		(nvda_commands.IndexCommand(42), nvda_commands.IndexCommand(7)),
	)
	assert c.tasks.submit_request(request)
	assert entered.wait(WAIT_TIMEOUT) and returned.wait(WAIT_TIMEOUT)
	assert indexes == [42] and completed == []
	if action == "cancel":
		assert future.cancelled()
	else:
		assert not future.done()


def test_partial_event_configuration_rolls_back_binding_and_owner(composition, monkeypatch):
	c = composition
	cls = c.engine("drain")
	cls.synth_driver_class.speak_segment = lambda *args, **kwargs: None
	configure = c.module.LegacyEngineAdapter.configureSegmentEvents

	def fail_after_configure(adapter, factory):
		configure(adapter, factory)
		raise RuntimeError("partial event setup")

	monkeypatch.setattr(c.module.LegacyEngineAdapter, "configureSegmentEvents", fail_after_configure)
	with pytest.raises(RuntimeError, match="partial event setup"):
		c.create(lambda cls, core: drain_contract(c))
	assert bridge_bindings(c.bridge) == {}
	assert cls.opened is None and c.cores[0].closes == 1
	assert c.repo.saves == []


def test_each_drain_factory_captures_its_own_resource(composition, nvda_commands):
	c = composition
	first, second = c.engine("first"), c.engine("second")
	first.synth_driver_class.speak_segment = lambda *args, **kwargs: None
	manager = c.create(lambda cls, core: drain_contract(c))
	calls, completed = [], threading.Event()
	for cls in (first, second):

		def speak(commands, token, *, context, on_event, source=cls.opened):
			assert bridge_binding(c.bridge, source).sourceId is context.source_id
			calls.append(source)
			on_event(
				c.models.PlaybackEvent(
					c.models.EventKind.SEGMENT_DRAINED,
					context.source_id,
					segment_id=context.segment_id,
				),
			)

		cls.opened.speak_segment = speak
	c.done.register(lambda synth: completed.set() if synth is c.owner else None)
	request = c.tasks.new_request()
	for key in ("first:a", "second:a"):
		c.tasks.append_speech(request, manager.resolve_playback(key), key, ("hello",))
	assert c.tasks.submit_request(request) and completed.wait(WAIT_TIMEOUT)
	assert calls == [first.opened, second.opened]


def test_reentrant_drain_supplier_waits_until_current_index_batch_finishes(composition, nvda_commands):
	c = composition
	cls = c.engine("drain")
	cls.synth_driver_class.speak_segment = lambda *args, **kwargs: None
	manager = c.create(lambda cls, core: drain_contract(c))
	port = manager.resolve_playback("drain:a")
	delivery, current = [], {}
	completed = threading.Event()
	receive = c.ledger.receiveSegmentEvent

	def record_decode(event, **kwargs):
		delivery.append("decode")
		return receive(event, **kwargs)

	c.ledger.receiveSegmentEvent = record_decode

	def output(synth, index):
		if synth is c.owner:
			delivery.append(index)
			if index == 42:
				current["sink"](current["event"])

	c.index.register(output)
	c.done.register(lambda synth: completed.set() if synth is c.owner else None)

	def speak(commands, token, *, context, on_event):
		current["sink"] = on_event
		current["event"] = c.models.PlaybackEvent(
			c.models.EventKind.SEGMENT_DRAINED,
			context.source_id,
			segment_id=context.segment_id,
		)
		on_event(current["event"])

	cls.opened.speak_segment = speak
	request = c.tasks.new_request()
	c.tasks.append_speech(
		request,
		port,
		"drain:a",
		(
			nvda_commands.IndexCommand(42),
			nvda_commands.IndexCommand(7),
		),
	)
	assert c.tasks.submit_request(request) and completed.wait(WAIT_TIMEOUT)
	assert delivery == ["decode", 42, 7, "decode"]


def test_old_drain_sink_cannot_complete_request_after_core_rebind(composition, nvda_commands):
	c = composition
	cls = c.engine("drain")
	cls.synth_driver_class.speak_segment = lambda *args, **kwargs: None
	manager = c.create(lambda cls, core: drain_contract(c))
	port = manager.resolve_playback("drain:a")
	entered = threading.Event()
	calls, indexes = [], []
	c.index.register(lambda synth, index: indexes.append(index) if synth is c.owner else None)

	def speak(commands, token, *, context, on_event):
		calls.append((context, on_event))
		entered.set()

	cls.opened.speak_segment = speak
	first = c.tasks.new_request()
	c.tasks.append_speech(first, port, "drain:a", ("old",))
	assert c.tasks.submit_request(first) and entered.wait(WAIT_TIMEOUT)
	c.tasks.cancel((port,))
	c.bridge.unbind(port.source_id)
	c.bridge.bind(cls.opened, port.source_id, completion=port.completion)
	entered.clear()
	second = c.tasks.new_request()
	future = c.tasks.append_speech(second, port, "drain:a", ("new", nvda_commands.IndexCommand(42)))
	assert c.tasks.submit_request(second) and entered.wait(WAIT_TIMEOUT)
	old_context, old_sink = calls[0]
	old_sink(
		c.models.PlaybackEvent(
			c.models.EventKind.SEGMENT_DRAINED,
			old_context.source_id,
			segment_id=old_context.segment_id,
		),
	)
	assert indexes == [] and not future.done()
	new_context, new_sink = calls[1]
	new_sink(
		c.models.PlaybackEvent(
			c.models.EventKind.SEGMENT_DRAINED,
			new_context.source_id,
			segment_id=new_context.segment_id,
		),
	)
	assert future.result(WAIT_TIMEOUT) is True and indexes == [42]


def test_an_unavailable_main_voice_raises_and_keeps_the_current_one(composition):
	# NVDA's SynthDriver.loadSettings repairs the saved voice only when the setter raises.
	composition.engine("x")
	manager = composition.create(get_language=lambda: "en")
	with pytest.raises(LookupError):
		manager.default_voice_name = "x:missing"
	assert manager.default_voice_name == "x:a"
