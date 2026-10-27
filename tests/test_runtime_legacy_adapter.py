from types import SimpleNamespace

import pytest
from addon_loader import load_definitions
from legacy_adapter_harness import Core, legacy_class
from runtime_harness import RUNTIME, MemoryRepository, load_index_support, make_spec
from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs


def test_lifecycle_metadata_and_apply_order(bridge_modules, rt):
	core = Core()
	cls = legacy_class(core)
	adapter = bridge_modules.adapter.VoiceClassAdapter(cls, lambda key: cls())
	adapter.open()
	adapter.open()
	assert cls.opens == 1
	assert adapter.notificationSource is core
	spec = adapter.listVoices()[0]
	assert spec == rt.models.VoiceSpec("a", "Fake:a", "A", "en", "Fake", "en")
	assert adapter.variants(spec.name) == ({"id": "bright", "name": "Bright"},)
	assert core.writes == []
	snapshot = rt.voice_settings.VoiceState(spec, {"rate": 72, "rateBoost": True}).snapshot()
	adapter.apply(spec, snapshot)
	assert core.writes == [
		("voice", "a"),
		("rateBoost", True),
		("rate", 72),
		("pitch", 50),
		("volume", 50),
		("inflection", 50),
		("hook", "default"),
	]
	adapter.cancel()
	adapter.pause(True)
	adapter.pause(False)
	assert core.cancelled == 1
	assert core.paused == [True, False]
	adapter.close()
	adapter.close()
	assert cls.closes == 1
	assert adapter.core is None and adapter.notificationSource is None
	adapter.open()
	assert adapter.core is core
	adapter.close()
	assert (cls.opens, cls.closes) == (2, 2)


@pytest.mark.parametrize("extra", [{}, {"name": "noncanonical", "description": "", "locale": "en_US"}])
def test_voice_metadata_defaults_and_canonical_key(bridge_modules, rt, extra):
	cls = legacy_class(Core())
	cls.voices = classmethod(lambda cls, core: [dict(engine="Fake", id="a", language="en_US", **extra)])
	adapter = bridge_modules.adapter.VoiceClassAdapter(cls, lambda key: cls())
	assert adapter.listVoices() == (rt.models.VoiceSpec("a", "Fake:a", "", "en_US", "Fake", "en_US"),)


def test_malformed_voice_metadata_does_not_hide_valid_voices(bridge_modules, rt):
	cls = legacy_class(Core())
	valid = {
		"engine": "Fake",
		"id": "a",
		"language": "en",
		"name": "Fake:a",
		"description": "A",
		"locale": "en",
	}
	malformed = dict(valid, id="broken")
	del malformed["language"]
	cls.voices = classmethod(lambda cls, core: [malformed, valid])
	adapter = bridge_modules.adapter.VoiceClassAdapter(cls, lambda key: cls())
	assert adapter.listVoices() == (rt.models.VoiceSpec("a", "Fake:a", "A", "en", "Fake", "en"),)


@pytest.mark.parametrize("support", [True, False, None])
def test_token_support_comes_from_actual_core(bridge_modules, support):
	core = Core()
	if support is not None:
		core.supportsCancellationToken = support
	cls = legacy_class(core)
	cls.supportsCancellationToken = True  # Class claims are not authoritative.
	adapter = bridge_modules.adapter.VoiceClassAdapter(cls, lambda key: cls())
	adapter.open()
	token = SimpleNamespace(is_cancelled=lambda: False)
	adapter.speak(("hello",), token)
	assert core.spoken == [(("hello",), {"cancellationToken": token} if support else {})]
	assert adapter.capabilities.supports_cancellation_token is bool(support)
	assert adapter.capabilities.supports_variants is False
	assert adapter.capabilities.supports_waitfactor is False


def test_unsupported_generic_settings_are_not_written(bridge_modules, rt):
	core = Core()
	cls = legacy_class(core)
	cls.supportedSettings = classmethod(lambda cls: ["rate"])
	adapter = bridge_modules.adapter.VoiceClassAdapter(cls, lambda key: cls())
	adapter.open()
	state = rt.voice_settings.VoiceState(make_spec(), {})
	adapter.apply(state.spec, state.snapshot())
	assert core.writes == [("voice", "a"), ("rate", 50), ("hook", "default")]
	assert adapter.capabilities.settings == frozenset({"rate"})


def test_failed_core_creation_leaves_nothing_to_clean(bridge_modules, rt):
	core = Core()
	cls = legacy_class(core)

	def fail_open(cls):
		cls.opens += 1
		raise ValueError("open failed")

	cls.create_core = classmethod(fail_open)
	adapter = bridge_modules.adapter.VoiceClassAdapter(cls, lambda key: cls())
	session = rt.session.EngineSession(adapter, rt.voice_settings.VoiceSettingsStore(MemoryRepository()))
	with pytest.raises(ValueError, match="open failed"):
		session.open()
	assert adapter.core is None and adapter.notificationSource is None
	session.close()
	adapter.close()
	assert (cls.opens, cls.closes) == (1, 0)


def test_close_releases_adapter_state_even_when_destroy_core_fails(bridge_modules):
	core = Core()
	cls = legacy_class(core)

	def fail_destroy(cls, target):
		cls.closes += 1
		raise OSError("cleanup failed")

	cls.destroy_core = classmethod(fail_destroy)
	adapter = bridge_modules.adapter.VoiceClassAdapter(cls, lambda key: cls())
	adapter.open()
	with pytest.raises(OSError, match="cleanup failed"):
		adapter.close()
	assert adapter.core is None and adapter.notificationSource is None
	adapter.close()
	assert cls.closes == 1


def test_each_adapter_owns_its_own_core(bridge_modules):
	first_core, second_core = Core(), Core()
	first_cls, second_cls = legacy_class(first_core), legacy_class(second_core)
	first = bridge_modules.adapter.VoiceClassAdapter(first_cls, lambda key: first_cls())
	second = bridge_modules.adapter.VoiceClassAdapter(second_cls, lambda key: second_cls())
	first.open()
	second.open()
	assert (first.core, second.core) == (first_core, second_core)
	second.close()
	assert first.core is first_core
	assert (first_cls.closes, second_cls.closes) == (0, 1)
	first.close()
	assert (first_cls.closes, second_cls.closes) == (1, 1)


def test_onecore_cached_a_b_a_restores_language(bridge_modules, rt):
	path = RUNTIME.parent / "driver/OneCore/__init__.py"
	core = Core()
	env = {
		"BaseVoice": legacy_class(core),
		"SynthDriver": object,
		"DrainProfile": rt.playback_work.DrainProfile,
	}
	load_definitions(path, ["Voice"], env)
	cls = env["Voice"]
	store = rt.voice_settings.VoiceSettingsStore(MemoryRepository())
	store.ensure(make_spec("OneCore:a", "en")).update(rate=72)
	store.ensure(make_spec("OneCore:b", "zh_TW")).update(rate=31)
	adapter = bridge_modules.adapter.VoiceClassAdapter(cls, lambda key: cls())
	session = rt.session.EngineSession(adapter, store)
	session.open()
	for key in ("OneCore:a", "OneCore:b", "OneCore:a"):
		assert session.activate(key) is True
	assert (core.voice, core.language, core.rate) == ("a", "en", 72)
	assert session.activate("OneCore:a") is False


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_real_variant_and_waitfactor_hooks(bridge_modules, rt, monkeypatch, engine):
	harness = load_real_driver_with_native_stubs(monkeypatch, engine)

	class LegacyVoice(harness.module.Voice):
		extra_capabilities = frozenset({"variant", "waitfactor"})

	cls = LegacyVoice
	core = Core()
	# VE queues inner settings on its BgThread; this fake runs them at once.
	core._bgQueue = SimpleNamespace(put=lambda task: task())
	core.getVoiceInstance = lambda key: "native:" + key
	core.getParameter = lambda *args, **kwargs: "plain"
	core.availableVariants = {"plain": object(), "bright": object()}
	writes = []
	monkeypatch.setattr(
		harness.module,
		"TtsSetParamList",
		lambda instance, pair: lambda: writes.append((instance, pair[1])),
	)
	monkeypatch.setattr(
		harness.module.ve2 if engine == "VE" else harness.module.ttsapi,
		"getSpeechDBList",
		lambda language, key: ["plain", "bright"],
	)
	monkeypatch.setattr(cls, "create_core", classmethod(lambda cls: core), raising=False)
	monkeypatch.setattr(cls, "supportedSettings", classmethod(lambda cls: ["rate"]), raising=False)
	voice = object.__new__(cls)
	voice.id = "a"
	# The harness's Voice base is a plain object; a bound facade exposes core.
	voice.core = core
	adapter = bridge_modules.adapter.VoiceClassAdapter(cls, lambda key: voice)
	adapter.open()
	core.writes.clear()
	assert adapter.capabilities.supports_variants is True
	assert adapter.capabilities.supports_waitfactor is True
	assert adapter.variants(engine + ":a") == (
		{"id": "plain", "name": "plain"},
		{"id": "bright", "name": "bright"},
	)
	assert core.writes == []
	state = rt.voice_settings.VoiceState(make_spec(engine + ":a"), {"variant": "bright", "waitfactor": 4})
	adapter.apply(state.spec, state.snapshot())
	assert (core.voice, core.rate, core.waitfactor) == ("a", 50, 4)
	assert writes == [("native:a", "bright")]


@pytest.fixture
def marker_env(monkeypatch, bridge_modules, rt, nvda_commands):
	support = load_index_support(monkeypatch, rt, "worldvoice_bridge_test")
	ledger = support.ledger.IndexLedger()
	contract = rt.models.CompletionContract(
		rt.models.CompletionMode.END_INDEX,
		rt.models.IndexRange(501, 510),
	)
	core = Core()
	cls = legacy_class(core)
	adapter = bridge_modules.adapter.VoiceClassAdapter(
		cls,
		lambda key: cls(),
		indexLedger=ledger,
		completion=contract,
	)
	adapter.open()
	source_id = object()
	ledger.bind(core, source_id, contract)
	yield SimpleNamespace(
		adapter=adapter,
		core=core,
		ledger=ledger,
		contract=contract,
		source_id=source_id,
		context=rt.models.PlaybackContext(source_id, 1),
		commands=nvda_commands,
		support=support,
		models=rt.models,
		token=SimpleNamespace(is_cancelled=lambda: False),
	)
	adapter.close()
	ledger.close()


def test_synchronous_marker_callback_has_mapping(marker_env):
	env = marker_env
	events = []
	env.core.speak = lambda commands: events.extend(
		env.ledger.receiveIndex(env.source_id, commands[-1].index),
	)
	env.adapter.speak(("hello", env.commands.IndexCommand(123)), env.token, context=env.context)
	assert [event.kind for event in events] == [env.models.EventKind.INDEX, env.models.EventKind.SEGMENT_END]
	assert [event.index for event in events] == [123, None]
	assert all(event.segment_id == 1 for event in events)
	assert env.adapter.capabilities.completion == env.contract


def test_success_keeps_mapping_for_async_marker(marker_env):
	env = marker_env
	env.adapter.speak(("hello",), env.token, context=env.context)
	assert [event.segment_id for event in env.ledger.receiveIndex(env.source_id, 501)] == [1]


@pytest.mark.parametrize("cancel_after_prepare", [False, True])
def test_cancel_before_and_after_prepare_does_not_publish_live_segment(
	marker_env,
	monkeypatch,
	cancel_after_prepare,
):
	env = marker_env
	cancelled = not cancel_after_prepare
	env.token.is_cancelled = lambda: cancelled
	prepare = env.ledger.prepare

	def cancel_during_prepare(context, originals):
		nonlocal cancelled
		allocation = prepare(context, originals)
		cancelled = True
		return allocation

	monkeypatch.setattr(env.ledger, "prepare", cancel_during_prepare)
	env.adapter.speak(("hello",), env.token, context=env.context)
	assert env.core.spoken == []
	assert env.ledger.receiveIndex(env.source_id, 501) == ()
	assert prepare(env.context, ()).endIndex == (502 if cancel_after_prepare else 501)


def test_speak_failure_retires_mapping(marker_env):
	env = marker_env

	def fail(commands):
		raise OSError("core failed")

	env.core.speak = fail
	with pytest.raises(OSError, match="core failed"):
		env.adapter.speak(("hello",), env.token, context=env.context)
	assert env.ledger.receiveIndex(env.source_id, 501) == ()
	assert env.ledger.prepare(env.context, ()).endIndex == 502


def test_finish_is_idempotent(marker_env):
	env = marker_env
	env.adapter.speak(("hello",), env.token, context=env.context)
	env.adapter.finish_segment(env.context)
	env.adapter.finish_segment(env.context)
	assert env.ledger.receiveIndex(env.source_id, 501) == ()
	assert env.ledger.prepare(env.context, ()).endIndex == 502


def test_cancel_retires_source_before_core_callback(marker_env):
	env = marker_env
	env.adapter.speak(("one",), env.token, context=env.context)
	env.adapter.speak(("two",), env.token, context=env.models.PlaybackContext(env.source_id, 2))
	events = []
	env.core.cancel = lambda: events.extend(
		env.ledger.receiveIndex(env.source_id, 501) + env.ledger.receiveIndex(env.source_id, 502),
	)
	env.adapter.cancel()
	assert events == []
	assert env.ledger.prepare(env.context, ()).endIndex == 503


def test_legacy_without_context_preserves_commands(bridge_modules, monkeypatch):
	import builtins

	core = Core()
	cls = legacy_class(core)
	adapter = bridge_modules.adapter.VoiceClassAdapter(cls, lambda key: cls())
	adapter.open()
	commands = ("hello", object())
	original_import = builtins.__import__

	def guard(name, *args, **kwargs):
		if name.startswith("speech") or "indexCodec" in name:
			raise AssertionError("Legacy calls must not import marker dependencies")
		return original_import(name, *args, **kwargs)

	monkeypatch.setattr(builtins, "__import__", guard)
	adapter.speak(commands, SimpleNamespace(is_cancelled=lambda: False))
	assert core.spoken[0][0] is commands


def test_marker_mode_requires_context(marker_env):
	env = marker_env
	with pytest.raises(ValueError, match="context"):
		env.adapter.speak(("hello",), env.token)
	assert env.core.spoken == []
	assert env.ledger.prepare(env.context, ()).endIndex == 501


@pytest.fixture
def drain_env(monkeypatch, bridge_modules, rt, nvda_commands, request):
	support = load_index_support(monkeypatch, rt, "worldvoice_bridge_test")
	ledger = support.ledger.IndexLedger()
	core = Core()
	cls = legacy_class(core)
	adapter = bridge_modules.adapter.VoiceClassAdapter(cls, lambda key: cls(), indexLedger=ledger)
	adapter.open()
	contract = rt.models.CompletionContract(
		getattr(rt.models.CompletionMode, getattr(request, "param", "DRAIN")),
		rt.models.IndexRange(1, 9999),
	)
	adapter.configureCompletion(contract)
	source_id = object()
	binding_token = ledger.bind(core, source_id, contract)
	events, calls = [], []

	def speak_segment(commands, token, *, context, on_event):
		calls.append((commands, token, context, on_event))

	core.speak_segment = speak_segment

	def factory(context):
		return lambda event: events.extend(ledger.receiveSegmentEvent(event, bindingToken=binding_token))

	yield SimpleNamespace(
		adapter=adapter,
		core=core,
		ledger=ledger,
		contract=contract,
		source_id=source_id,
		context=rt.models.PlaybackContext(source_id, 1),
		commands=nvda_commands,
		support=support,
		models=rt.models,
		token=SimpleNamespace(is_cancelled=lambda: False),
		events=events,
		calls=calls,
		factory=factory,
	)
	adapter.close()
	ledger.close()


def test_adapter_passes_original_context_to_segment_entry(drain_env):
	env = drain_env
	env.adapter.configureSegmentEvents(env.factory)
	original = env.commands.IndexCommand(123)
	env.adapter.speak(("hello", original), env.token, context=env.context)
	commands, token, context, sink = env.calls[0]
	assert token is env.token and context is env.context
	assert callable(sink)
	assert [c.index for c in commands if isinstance(c, env.commands.IndexCommand)] == [1]
	assert not any(isinstance(c, env.support.commands.WorldVoiceIndexCommand) for c in commands)
	assert original.index == 123 and env.core.spoken == []


def test_synchronous_segment_drain_has_prepared_mapping(drain_env):
	env = drain_env
	env.adapter.configureSegmentEvents(env.factory)

	def speak(commands, token, *, context, on_event):
		on_event(
			env.models.PlaybackEvent(
				env.models.EventKind.SEGMENT_DRAINED,
				context.source_id,
				segment_id=context.segment_id,
			),
		)

	env.core.speak_segment = speak
	env.adapter.speak(("hello", env.commands.IndexCommand(123)), env.token, context=env.context)
	assert [(e.kind.name, e.index) for e in env.events] == [("INDEX", 123), ("SEGMENT_DRAINED", None)]


@pytest.mark.parametrize("failure", ["entry", "factory"])
def test_segment_entry_or_factory_failure_retires_mapping(drain_env, failure):
	env = drain_env

	def fail(*args, **kwargs):
		raise OSError("segment setup failed")

	env.adapter.configureSegmentEvents(fail if failure == "factory" else env.factory)
	if failure == "entry":
		env.core.speak_segment = fail
	with pytest.raises(OSError, match="segment setup failed"):
		env.adapter.speak(("hello", env.commands.IndexCommand(123)), env.token, context=env.context)
	assert env.ledger.receiveIndex(env.source_id, 1) == ()
	assert env.ledger.prepare(env.context, (456,)).wireIndexes == (2,)


def test_segment_failure_sink_preserves_error_without_index_backfill(drain_env):
	env = drain_env
	error = OSError("playback failed")
	env.adapter.configureSegmentEvents(env.factory)

	def speak(commands, token, *, context, on_event):
		on_event(
			env.models.PlaybackEvent(
				env.models.EventKind.SEGMENT_FAILED,
				context.source_id,
				segment_id=context.segment_id,
				error=error,
			),
		)

	env.core.speak_segment = speak
	env.adapter.speak(("hello", env.commands.IndexCommand(123)), env.token, context=env.context)
	assert len(env.events) == 1 and env.events[0].error is error


@pytest.mark.parametrize("cancel_after_prepare", [False, True])
def test_drain_cancel_before_dispatch_retires_segment(drain_env, monkeypatch, cancel_after_prepare):
	env = drain_env
	env.adapter.configureSegmentEvents(env.factory)
	cancelled = not cancel_after_prepare
	env.token.is_cancelled = lambda: cancelled
	prepare = env.ledger.prepare

	def cancel_during_prepare(context, originals):
		nonlocal cancelled
		allocation = prepare(context, originals)
		cancelled = True
		return allocation

	monkeypatch.setattr(env.ledger, "prepare", cancel_during_prepare)
	env.adapter.speak(("hello", env.commands.IndexCommand(123)), env.token, context=env.context)
	assert env.calls == []
	assert env.ledger.receiveIndex(env.source_id, 1) == ()
	assert prepare(env.context, (456,)).wireIndexes == ((2,) if cancel_after_prepare else (1,))


def test_drain_cancel_retires_before_core_emits_old_drain(drain_env):
	env = drain_env
	env.adapter.configureSegmentEvents(env.factory)
	env.adapter.speak(("hello", env.commands.IndexCommand(123)), env.token, context=env.context)
	sink = env.calls[0][3]
	env.core.cancel = lambda: sink(
		env.models.PlaybackEvent(
			env.models.EventKind.SEGMENT_DRAINED,
			env.source_id,
			segment_id=1,
		),
	)
	env.adapter.cancel()
	assert env.events == []


def test_drain_requires_event_factory_before_speech(drain_env):
	env = drain_env
	with pytest.raises(RuntimeError, match="segment event"):
		env.adapter.speak(("hello",), env.token, context=env.context)
	assert env.calls == env.core.spoken == []


@pytest.mark.parametrize("phase", ["before_open", "before_completion", "after_speech", "after_close"])
def test_segment_event_configuration_rejects_wrong_lifecycle_phase(bridge_modules, rt, phase):
	core = Core()
	core.speak_segment = lambda *args, **kwargs: None
	cls = legacy_class(core)
	adapter = bridge_modules.adapter.VoiceClassAdapter(cls, lambda key: cls())
	if phase != "before_open":
		adapter.open()
	if phase in ("after_speech", "after_close"):
		adapter.configureCompletion(rt.models.CompletionContract())
		if phase == "after_speech":
			adapter.speak(("hello",), SimpleNamespace(is_cancelled=lambda: False))
		else:
			adapter.close()
	with pytest.raises(RuntimeError):
		adapter.configureSegmentEvents(lambda context: lambda event: None)
	adapter.close()


def test_segment_configuration_requires_callable_core_entry(drain_env):
	env = drain_env
	env.core.speak_segment = None
	with pytest.raises(ValueError, match="speak_segment"):
		env.adapter.configureSegmentEvents(env.factory)


@pytest.mark.parametrize("drain_env", ["END_INDEX_AND_DRAIN"], indirect=True)
def test_and_mode_uses_segment_entry_and_keeps_terminal_marker(drain_env):
	env = drain_env
	env.adapter.configureSegmentEvents(env.factory)
	env.adapter.speak(("hello", env.commands.IndexCommand(123)), env.token, context=env.context)
	commands, token, context, _ = env.calls[0]
	assert token is env.token and context is env.context
	assert [c.index for c in commands if isinstance(c, env.commands.IndexCommand)] == [1, 2]
	assert isinstance(commands[-1], env.support.commands.WorldVoiceIndexCommand)
	assert env.core.spoken == []
