"""Evidence-gated completion selection and resource-bound adapter configuration."""

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from runtime_harness import lifecycle_hooks, segment_host, segment_lifecycle
from sapi5_drain_harness import load_sapi5
from worldvoice_harness import load_voice_manager


@pytest.fixture
def env(monkeypatch):
	module = load_voice_manager(monkeypatch)
	package = module.__package__.removesuffix(".voices")
	models = importlib.import_module(package + ".runtime.models")
	adapter = importlib.import_module(package + ".bridge.engineAdapter")
	return SimpleNamespace(module=module, package=package, models=models, adapter=adapter)


def policies_of(env):
	return importlib.import_module(env.package + ".bridge.completionPolicies")


def drain_types(env):
	return importlib.import_module(env.package + ".runtime.playbackWork")


def fake_voice(
	env,
	*,
	profile=True,
	wasapi=False,
	supported=True,
	reason="Native lifetime is unproven",
	engine="test-engine",
):
	"""A Voice/SynthDriver pair whose core answers the drain check as told."""
	work = drain_types(env)
	checked = []

	class SynthDriver:
		def speak_segment(self, commands, token, *, context, on_event):
			pass

		def get_segment_drain_support(self, *, nvda_version, audio_mode):
			checked.append((nvda_version, audio_mode))
			return work.DrainSupport(supported, "test-profile", reason)

	class Voice:
		synthDriverClass = SynthDriver
		drainProfile = work.DrainProfile(wasapi_dependent=wasapi) if profile else None

	Voice.engine = engine
	return SimpleNamespace(voice=Voice, driver=SynthDriver, core=SynthDriver(), checked=checked)


@pytest.mark.parametrize("supported", [False, True])
def test_profiled_voice_uses_drain_only_with_explicit_support(env, supported):
	pair = fake_voice(env, supported=supported)
	contract, support = (
		policies_of(env)
		.CompletionPolicy()
		.contractFor(
			pair.voice,
			pair.core,
			nvdaVersion="unknown",
			audioMode="default",
		)
	)
	assert pair.checked == [("unknown", "default")]
	assert support.supported is supported
	assert contract.mode is (
		env.models.CompletionMode.DRAIN if supported else env.models.CompletionMode.LEGACY_DONE
	)
	assert contract.index_range == (env.models.IndexRange(1, 9999) if supported else None)


def test_voice_without_profile_still_uses_legacy_done(env):
	# The core's own answer is never consulted without a declared profile.
	pair = fake_voice(env, profile=False, supported=False, engine="external-test-engine")
	contract, support = (
		policies_of(env)
		.CompletionPolicy()
		.contractFor(
			pair.voice,
			pair.core,
			nvdaVersion="unknown",
			audioMode="default",
		)
	)
	assert support is None and pair.checked == []
	assert contract.mode is env.models.CompletionMode.LEGACY_DONE
	assert contract.index_range is None


@pytest.mark.parametrize(
	"failure,reason",
	[
		("wrong_core", "The opened core is not the Voice's custom outer SynthDriver"),
		("missing_entry", "The custom core has no callable speak_segment entry"),
		("missing_support", "The custom core has no callable get_segment_drain_support check"),
		("support_error", "Drain support inspection failed: RuntimeError: inspection failed"),
		("invalid_support", "The wrapper did not return an explicit DrainSupport boolean decision"),
		("truthy_support", "The wrapper did not return an explicit DrainSupport boolean decision"),
		("unsupported_without_reason", "The wrapper has no supported adapter/native drain profile"),
	],
)
def test_unconfirmed_profile_falls_back_with_concrete_reason(env, failure, reason):
	work = drain_types(env)
	pair = fake_voice(
		env,
		supported=failure != "unsupported_without_reason",
		reason="" if failure == "unsupported_without_reason" else "unused",
	)
	core = pair.core
	if failure == "wrong_core":
		core = SimpleNamespace(
			speak_segment=pair.core.speak_segment,
			get_segment_drain_support=pair.core.get_segment_drain_support,
		)
	elif failure == "missing_entry":
		pair.driver.speak_segment = None
	elif failure == "missing_support":
		pair.driver.get_segment_drain_support = None
	elif failure == "support_error":

		def fail(self, **kwargs):
			raise RuntimeError("inspection failed")

		pair.driver.get_segment_drain_support = fail
	elif failure == "invalid_support":
		pair.driver.get_segment_drain_support = lambda self, **kwargs: SimpleNamespace(supported=True)
	elif failure == "truthy_support":
		pair.driver.get_segment_drain_support = lambda self, **kwargs: work.DrainSupport("yes", "p", "r")
	contract, support = (
		policies_of(env)
		.CompletionPolicy()
		.contractFor(
			pair.voice,
			core,
			nvdaVersion="2026.1",
			audioMode="default",
		)
	)
	assert support.supported is False and support.reason == reason
	assert contract.mode is env.models.CompletionMode.LEGACY_DONE


def test_drain_support_refuses_a_voice_without_profile(env):
	pair = fake_voice(env, profile=False)
	support = (
		policies_of(env)
		.CompletionPolicy()
		.drainSupport(
			pair.voice,
			pair.core,
			nvdaVersion="2026.1",
			audioMode="default",
		)
	)
	assert support.supported is False and support.reason == "The Voice declares no drain profile"
	assert pair.checked == []


def test_disabled_force_switch_reports_the_wrapper_reason(env):
	pair = fake_voice(env, reason="DRAIN explicitly enabled; playback is unverified")
	policy = policies_of(env).CompletionPolicy(forceUnverifiedDrain=False)
	contract, support = policy.contractFor(
		pair.voice,
		pair.core,
		nvdaVersion="2026.1",
		audioMode="default",
	)
	assert support.supported is False and support.profile == "test-profile"
	assert support.reason == (
		"Unverified DRAIN is disabled by force_unverified_drain: "
		"DRAIN explicitly enabled; playback is unverified"
	)
	assert contract.mode is env.models.CompletionMode.LEGACY_DONE
	assert policies_of(env).CompletionPolicy().forceUnverifiedDrain is True


def make_adapter(env):
	class Voice:
		@classmethod
		def createCore(cls):
			return SimpleNamespace(speak=lambda commands: None)

		@classmethod
		def supportedSettings(cls):
			return ()

	return env.adapter.VoiceClassAdapter(Voice, lambda key: None)


def test_configure_requires_open_and_cannot_downgrade(env):
	adapter = make_adapter(env)
	contract = env.models.CompletionContract(
		env.models.CompletionMode.END_INDEX,
		env.models.IndexRange(1, 10),
	)
	assert hasattr(adapter, "configureCompletion"), "Resource-bound completion configuration is missing"
	with pytest.raises(RuntimeError):
		adapter.configureCompletion(contract)
	adapter.open()
	adapter.configureCompletion(contract)
	adapter.configureCompletion(contract)
	with pytest.raises(RuntimeError):
		adapter.configureCompletion(env.models.CompletionContract())
	assert adapter.capabilities.completion == contract


def test_configure_after_speech_is_rejected(env):
	adapter = make_adapter(env)
	adapter.open()
	adapter.speak(("hello",), SimpleNamespace(is_cancelled=lambda: False))
	assert hasattr(adapter, "configureCompletion"), "Resource-bound completion configuration is missing"
	with pytest.raises(RuntimeError):
		adapter.configureCompletion(env.models.CompletionContract())


def ledger_adapter(env, core):
	"""A legacy adapter built as the voice manager builds every adapter: with an index ledger."""

	class Voice:
		@classmethod
		def createCore(cls):
			return core

		@classmethod
		def supportedSettings(cls):
			return ()

	ledger = importlib.import_module(env.package + ".bridge.indexLedger").IndexLedger()
	adapter = env.adapter.VoiceClassAdapter(Voice, lambda key: None, indexLedger=ledger)
	adapter.open()
	return adapter


class RecordingCore:
	def __init__(self, error=None):
		self.spoken = []
		self.error = error

	def speak(self, commands):
		self.spoken.append(commands)
		if self.error is not None:
			raise self.error

	def speak_segment(self, commands, token, *, context, on_event):
		pass


def test_legacy_speak_with_a_cancelled_token_never_enters_the_core(env):
	core = RecordingCore()
	adapter = ledger_adapter(env, core)
	assert adapter.speak(("hello",), SimpleNamespace(is_cancelled=lambda: True)) is None
	assert core.spoken == []


def test_legacy_speak_cancelled_during_entry_never_enters_the_core(env):
	core = RecordingCore()
	adapter = ledger_adapter(env, core)
	reads = []

	def is_cancelled():
		# Not cancelled when speak starts, cancelled by the time the core would be entered.
		reads.append(True)
		return len(reads) > 1

	assert adapter.speak(("hello",), SimpleNamespace(is_cancelled=is_cancelled)) is None
	assert core.spoken == []


def test_legacy_core_error_propagates_unchanged(env):
	error = OSError("engine failed")
	adapter = ledger_adapter(env, RecordingCore(error))
	with pytest.raises(OSError) as raised:
		adapter.speak(("hello",), SimpleNamespace(is_cancelled=lambda: False))
	assert raised.value is error


def test_segment_event_factory_must_be_callable(env):
	adapter = ledger_adapter(env, RecordingCore())
	models = env.models
	adapter.configureCompletion(
		models.CompletionContract(models.CompletionMode.DRAIN, models.IndexRange(1, 1000)),
	)
	with pytest.raises(TypeError, match="Segment event factory must be callable"):
		adapter.configureSegmentEvents(object())
	with pytest.raises(RuntimeError, match="Drain completion requires a segment event factory"):
		adapter.speak(
			("hello",),
			SimpleNamespace(is_cancelled=lambda: False),
			context=models.PlaybackContext(object(), 1),
		)


COMMANDS = (
	"IndexCommand",
	"CharacterModeCommand",
	"LangChangeCommand",
	"BreakCommand",
	"PitchCommand",
	"RateCommand",
	"VolumeCommand",
)


def real_completion_selector(policies, warnings, *, policy=None, version="2026.1"):
	"""The driver's selector: CompletionPolicy.select with NVDA's version and logger."""
	if policy is None:
		policy = policies.CompletionPolicy()
	policy.nvdaVersion = version
	policy._logger = SimpleNamespace(warning=lambda *args: warnings.append(args))
	return policy.select


@pytest.mark.parametrize(
	"profile,use_wasapi,expected",
	[
		("wasapi", True, "wasapi"),
		("wasapi", False, "legacy"),
		("wasapi", None, "unknown"),
		("wasapi", "true", "unknown"),
		("plain", True, "default"),
		("none", True, "default"),
	],
)
def test_synth_policy_uses_actual_opened_core(env, profile, use_wasapi, expected):
	pair = fake_voice(env, profile=profile != "none", wasapi=profile == "wasapi", supported=False)
	core = pair.core
	if use_wasapi is not None:
		core.useWasapi = use_wasapi
	warnings = []
	select = real_completion_selector(policies_of(env), warnings)
	assert select(pair.voice, core).mode is env.models.CompletionMode.LEGACY_DONE
	if profile == "none":
		assert pair.checked == [] and warnings == []
	else:
		assert pair.checked == [("2026.1", expected)]
		assert len(warnings) == 1 and warnings[0][1:4] == ("test-engine", "2026.1", expected)


@pytest.mark.parametrize(
	"engine,audio_modes",
	[
		("SAPI5", (("wasapi", True), ("legacy", False), ("unknown", False))),
		("Espeak", (("default", True), ("legacy", True), ("unknown", True))),
		("RHVoice", (("default", True), ("wasapi", True), ("unknown", True))),
	],
)
def test_actual_outer_voice_and_core_select_enabled_drain_profiles(
	monkeypatch,
	tmp_path,
	engine,
	audio_modes,
):
	if engine == "SAPI5":
		installed = load_sapi5(monkeypatch)
	elif engine == "Espeak":
		from espeak_drain_harness import load_espeak

		installed = load_espeak(monkeypatch, tmp_path)
	else:
		from rhvoice_drain_harness import load_rhvoice

		installed = load_rhvoice(monkeypatch, tmp_path)
	try:
		policies = fresh_policies(monkeypatch)
		policy = policies.CompletionPolicy()
		assert installed.outer.Voice.synthDriverClass is type(installed.driver)
		for audio_mode, expected in audio_modes:
			contract, support = policy.contractFor(
				installed.outer.Voice,
				installed.driver,
				nvdaVersion="2026.1",
				audioMode=audio_mode,
			)
			assert support.supported is expected and support.reason
			expected_mode = (
				installed.rt.models.CompletionMode.DRAIN
				if expected
				else installed.rt.models.CompletionMode.LEGACY_DONE
			)
			assert contract.mode is expected_mode
		warnings = []
		selected = real_completion_selector(policies, warnings)(installed.outer.Voice, installed.driver)
		assert selected.mode is installed.rt.models.CompletionMode.DRAIN
		assert selected.index_range is not None
		if engine == "RHVoice":
			assert warnings == []
	finally:
		if engine == "SAPI5":
			installed.driver.terminate()
		else:
			if engine == "Espeak":
				from espeak_drain_harness import finish
			else:
				from rhvoice_drain_harness import finish
			finish(installed)


def test_sapi5_legacy_first_segment_remains_legacy_done(monkeypatch):
	installed = load_sapi5(monkeypatch)
	try:
		installed.driver.useWasapi = False
		policies = fresh_policies(monkeypatch)
		support = policies.CompletionPolicy().drainSupport(
			installed.outer.Voice,
			installed.driver,
			nvdaVersion="2026.1",
			audioMode="legacy",
		)
		assert support.supported is False
		contract = real_completion_selector(policies, [])(installed.outer.Voice, installed.driver)
		assert contract.mode is installed.rt.models.CompletionMode.LEGACY_DONE
		assert contract.index_range is None
		assert installed.native.calls == []
		assert segment_host(installed.driver).current() is None
	finally:
		installed.driver.terminate()


SIX_ENGINES = ["OneCore", "VE", "Cerence", "SAPI5", "Espeak", "RHVoice"]


def load_installed_engine(monkeypatch, tmp_path, engine):
	"""Open the installed outer wrapper for *engine* on its fake native boundary."""
	control = None
	if engine in ("OneCore", "VE", "Cerence"):
		from runtime_drain_integration_harness import assemble

		composition = assemble(monkeypatch, tmp_path)
		control = composition.controls[engine]
		outer = control.env.outer if engine == "OneCore" else control.env.module
		core, close = control.core, composition.close
		mode, rt = ("wasapi" if engine == "OneCore" else "default"), composition.rt
	elif engine == "SAPI5":
		installed = load_sapi5(monkeypatch)
		outer, core, close, mode = installed.outer, installed.driver, installed.driver.terminate, "wasapi"
		rt = installed.rt
	elif engine == "Espeak":
		from espeak_drain_harness import finish, load_espeak

		installed = load_espeak(monkeypatch, tmp_path)
		outer, core, close, mode = installed.outer, installed.driver, lambda: finish(installed), "default"
		rt = installed.rt
	else:
		from rhvoice_drain_harness import finish, load_rhvoice

		installed = load_rhvoice(monkeypatch, tmp_path)
		outer, core, close, mode = installed.outer, installed.driver, lambda: finish(installed), "default"
		rt = installed.rt
	return SimpleNamespace(outer=outer, core=core, close=close, mode=mode, control=control, rt=rt)


def fresh_policies(monkeypatch):
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.bridge.completionPolicies", raising=False)
	return importlib.import_module("synthDrivers.WorldVoice.bridge.completionPolicies")


@pytest.mark.parametrize("engine", SIX_ENGINES)
def test_six_enabled_profiles_use_shared_lifecycle(monkeypatch, tmp_path, engine):
	"""The actual opened outer core must select DRAIN before any segment starts."""
	installed = load_installed_engine(monkeypatch, tmp_path, engine)
	outer, core, control = installed.outer, installed.core, installed.control
	try:
		policies = fresh_policies(monkeypatch)
		assert outer.Voice.synthDriverClass is type(core)
		assert outer.Voice.drainProfile is not None
		# The host owns the lifecycle and implements its hooks.
		host = segment_host(core)
		assert isinstance(host, outer.SegmentHost)
		assert lifecycle_hooks(segment_lifecycle(host)) is host
		policy = policies.CompletionPolicy()
		contract, support = policy.contractFor(
			outer.Voice,
			core,
			nvdaVersion="2026.1",
			audioMode=installed.mode,
		)
		assert support.supported is True
		assert contract.mode is policies.CompletionMode.DRAIN
		assert contract.index_range == policies.IndexRange(1, 9999)
		if control is not None:
			assert control.session.completion.mode is installed.rt.models.CompletionMode.DRAIN
			assert control.calls == []
	finally:
		installed.close()


def fresh_discovery(monkeypatch):
	"""engineRegistry/discovery.py without the package __init__, which scans the disk through NVDA."""
	registry = "synthDrivers.WorldVoice.engineRegistry"
	package = ModuleType(registry)
	package.__path__ = [str(Path(sys.modules["synthDrivers.WorldVoice"].__path__[0]) / "engineRegistry")]
	monkeypatch.setitem(sys.modules, registry, package)
	monkeypatch.delitem(sys.modules, registry + ".discovery", raising=False)
	return importlib.import_module(registry + ".discovery")


@pytest.mark.parametrize("engine", SIX_ENGINES)
def test_six_loaded_voices_pass_the_pre_rename_check(monkeypatch, tmp_path, engine):
	# Discovery skips a Voice that has a pre-rename contract name, inherited ones included (hasattr),
	# so the loaded class is checked the same way, not only the names its class body defines.
	installed = load_installed_engine(monkeypatch, tmp_path, engine)
	try:
		discovery = fresh_discovery(monkeypatch)
		assert discovery._pre_rename_contract_names(installed.outer.Voice) == []
	finally:
		sys.modules.pop("synthDrivers.WorldVoice.engineRegistry.discovery", None)
		installed.close()


@pytest.mark.parametrize("engine", SIX_ENGINES)
def test_disabled_force_switch_restores_legacy_done(monkeypatch, tmp_path, engine):
	installed = load_installed_engine(monkeypatch, tmp_path, engine)
	outer, core = installed.outer, installed.core
	try:
		policies = fresh_policies(monkeypatch)
		disabled = policies.CompletionPolicy(forceUnverifiedDrain=False)
		support = disabled.drainSupport(
			outer.Voice,
			core,
			nvdaVersion="2026.1",
			audioMode=installed.mode,
		)
		assert support.supported is False
		assert "force_unverified_drain" in support.reason and "unverified" in support.reason
		warnings = []
		select = real_completion_selector(policies, warnings, policy=disabled)
		contract = select(outer.Voice, core)
		assert contract.mode is installed.rt.models.CompletionMode.LEGACY_DONE
		assert contract.index_range is None
		assert select(outer.Voice, core) == contract
		assert len(warnings) == 1 and "force_unverified_drain" in warnings[0][-1]
		enabled = real_completion_selector(policies, warnings)
		assert enabled(outer.Voice, core).mode is installed.rt.models.CompletionMode.DRAIN
	finally:
		installed.close()


def test_disabled_force_switch_keeps_structural_fallback_reason(monkeypatch):
	installed = load_sapi5(monkeypatch)
	try:
		installed.driver.useWasapi = False
		policies = fresh_policies(monkeypatch)
		disabled = policies.CompletionPolicy(forceUnverifiedDrain=False)
		support = disabled.drainSupport(
			installed.outer.Voice,
			installed.driver,
			nvdaVersion="2026.1",
			audioMode="legacy",
		)
		assert support.supported is False
		assert support.reason == "SAPI5 legacy audio has no owned player idle barrier"
	finally:
		installed.driver.terminate()


def test_select_warns_once_per_distinct_fallback_profile(env):
	policies = policies_of(env)
	warnings = []
	policy = policies.CompletionPolicy(
		nvdaVersion="2026.1",
		logger=SimpleNamespace(warning=lambda *args: warnings.append(args)),
	)
	first = fake_voice(env, supported=False, reason="reason a", engine="Fake")
	second = fake_voice(env, supported=False, reason="reason b", engine="Fake")
	for pair in (first, first, second):
		assert policy.select(pair.voice, pair.core) == env.models.CompletionContract()
	assert [args[1:] for args in warnings] == [
		("Fake", "2026.1", "default", "test-profile", "reason a"),
		("Fake", "2026.1", "default", "test-profile", "reason b"),
	]
	assert warnings[0][0] == "WorldVoice %s uses LEGACY_DONE (NVDA %s, audio %s, profile %s): %s"


def test_fallback_dedupe_belongs_to_one_policy(env):
	policies = policies_of(env)
	warnings = []
	logger = SimpleNamespace(warning=lambda *args: warnings.append(args))
	pair = fake_voice(env, supported=False)
	for _ in range(2):
		policies.CompletionPolicy(nvdaVersion="2026.1", logger=logger).select(pair.voice, pair.core)
	assert len(warnings) == 2


@pytest.mark.parametrize("profile,supported", [(True, True), (True, False), (False, True)])
def test_select_matches_contract_for(env, profile, supported):
	policies = policies_of(env)
	policy = policies.CompletionPolicy(
		nvdaVersion="2026.1",
		logger=SimpleNamespace(warning=lambda *args: None),
	)
	pair = fake_voice(env, profile=profile, supported=supported)
	expected, _ = policy.contractFor(
		pair.voice,
		pair.core,
		nvdaVersion="2026.1",
		audioMode=policy.audioMode(pair.voice, pair.core),
	)
	assert policy.select(pair.voice, pair.core) == expected
