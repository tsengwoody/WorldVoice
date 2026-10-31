"""SAPI5 on each NVDA release: NVDA's own driver before 2025.3, WorldVoice's wrapper from 2025.3.

User decision 2026-10-28 (phase 51 spec §9 Q1): where NVDA lacks a name the SAPI5 wrapper uses,
NVDA's own synthDrivers.sapi5.SynthDriver is the whole core, as in WorldVoice 6.2, with no
segment drain. Each test loads one release's synthDrivers/sapi5.py from ref/nvda (git show, never
a checkout) behind the SAPI5 drain harness's NVDA stubs, then the real driver.Voice base and
WorldVoice's SAPI5 wrapper, and drives the chosen core through the bridge as the add-on does.
"""

import ctypes
import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, load_source
from engine_contract_harness import _fresh_lifecycle_module
from nvda_releases import RELEASES, release_missing, release_source
from sapi5_drain_harness import load_sapi5

FIRST_WRAPPER_RELEASE = RELEASES.index("2025.3")
OLD_RELEASES = RELEASES[:FIRST_WRAPPER_RELEASE]
WRAPPER_RELEASES = RELEASES[FIRST_WRAPPER_RELEASE:]
PACKAGE = "synthDrivers.WorldVoice"


class RecordingLogger:
	def __init__(self):
		self.records = []

	def __getattr__(self, level):
		return lambda message, *args: self.records.append((level, message % args))


class VoiceToken:
	Id = "v1"

	def GetDescription(self):
		return "Voice One"

	def getattribute(self, name):
		return "409"

	GetAttribute = getattribute


class FakeSpVoice:
	"""The SAPI.SpVoice COM object, with both spellings the releases use."""

	def __init__(self):
		self.calls = []
		self.voice = VoiceToken()
		self.rate = self.Rate = 0
		self.volume = self.Volume = 100
		self.AudioOutput = None
		self.audioOutputStream = self.AudioOutputStream = self
		self.status = SimpleNamespace(LastBookmark="")
		self.Format = SimpleNamespace(
			GetWaveFormatEx=lambda: SimpleNamespace(
				FormatTag=1,
				BitsPerSample=16,
				Channels=1,
				SamplesPerSec=22050,
			),
			SetWaveFormatEx=lambda format: None,
		)

	def getVoices(self):
		return [VoiceToken()]

	GetVoices = getVoices

	def getAudioOutputs(self):
		return []

	GetAudioOutputs = getAudioOutputs

	def Speak(self, text, flags):
		self.calls.append(text)
		return len(self.calls)

	def QueryInterface(self, interface):
		return self

	def SetNotifySink(self, sink):
		self.sink = sink

	def setState(self, *args):
		pass


class Conf(dict):
	def getConfigValidation(self, key):
		return SimpleNamespace(default="default")


def load_release(monkeypatch, tmp_path, version):
	"""NVDA <version>'s sapi5 module, WorldVoice's SAPI5 wrapper on it, and the bridge modules."""
	_fresh_lifecycle_module(monkeypatch)
	harness = load_sapi5(monkeypatch)
	harness.driver.terminate()
	spVoices = []

	def createObject(progId):
		if progId == "SAPI.SPVoice":
			spVoices.append(FakeSpVoice())
			return spVoices[-1]
		return SimpleNamespace()

	# What the release sources need beyond the stubs the harness gives the ref/nvda source.
	monkeypatch.setattr(sys.modules["comtypes.client"], "CreateObject", createObject)
	monkeypatch.setattr(sys.modules["comtypes.client"], "GetEvents", lambda *args: object(), raising=False)
	monkeypatch.setattr(sys.modules["comtypes"], "IUnknown", object, raising=False)
	monkeypatch.setattr(sys.modules["nvwave"], "outputDeviceNameToID", lambda *args: -1, raising=False)
	monkeypatch.setattr(
		sys.modules["config"],
		"conf",
		Conf(speech={"outputDevice": "default"}, audio={"outputDevice": "default"}),
	)
	ole32 = SimpleNamespace(CoTaskMemAlloc=SimpleNamespace(), CoTaskMemFree=SimpleNamespace())
	monkeypatch.setattr(ctypes, "windll", SimpleNamespace(ole32=ole32), raising=False)
	objidl = ModuleType("objidl")
	objidl.__dict__.update(
		_LARGE_INTEGER=ctypes.c_longlong,
		_ULARGE_INTEGER=ctypes.c_ulonglong,
		IStream=object,
	)
	monkeypatch.setitem(sys.modules, "objidl", objidl)
	handler = sys.modules["synthDriverHandler"]
	monkeypatch.setattr(
		handler,
		"VoiceInfo",
		lambda id, name, language=None: SimpleNamespace(id=id, displayName=name, language=language),
	)
	# NVDA's SynthDriver base gives availableVoices; the harness base does not.
	monkeypatch.setattr(
		handler.SynthDriver,
		"availableVoices",
		property(lambda self: self._getAvailableVoices()),
		raising=False,
	)
	monkeypatch.setattr(
		sys.modules["languageHandler"],
		"getLanguageDescription",
		lambda locale: "English",
		raising=False,
	)
	monkeypatch.setitem(sys.modules, "versionInfo", SimpleNamespace(version=version))

	source = tmp_path / "sapi5.py"
	source.write_text(release_source(version, "sapi5.py"), encoding="utf-8")
	base = load_source(monkeypatch, "synthDrivers.sapi5", source)
	# The real plugin base, so createCore, voices and supportedSettings are the add-on's own.
	load_source(monkeypatch, f"{PACKAGE}.driver", WORLDVOICE / "driver/__init__.py")
	outer = load_source(monkeypatch, f"{PACKAGE}.driver.SAPI5", WORLDVOICE / "driver/SAPI5/__init__.py")
	assert outer.sapi5 is base
	logger = RecordingLogger()
	monkeypatch.setattr(outer, "log", logger)
	for name in ("bridge.completionPolicies", "bridge.engineAdapter"):
		monkeypatch.delitem(sys.modules, f"{PACKAGE}.{name}", raising=False)
	return SimpleNamespace(
		base=base,
		outer=outer,
		records=logger.records,
		spVoices=spVoices,
		commands=harness.commands,
		models=importlib.import_module(f"{PACKAGE}.runtime.models"),
		policies=importlib.import_module(f"{PACKAGE}.bridge.completionPolicies"),
		engineAdapter=importlib.import_module(f"{PACKAGE}.bridge.engineAdapter"),
	)


@pytest.mark.parametrize("version", OLD_RELEASES)
def test_old_nvda_chooses_its_own_sapi5_driver_with_one_info_line(monkeypatch, tmp_path, version):
	env = load_release(monkeypatch, tmp_path, version)
	voice = env.outer.Voice
	assert voice.ready() is True
	assert voice.synthDriverClass is env.base.SynthDriver
	assert voice.drainProfile is None
	# The live check on the release's own module agrees with the static view of its source.
	missing = release_missing("SAPI5", version)
	assert missing
	message = (
		f"SAPI5 engine uses NVDA's own SAPI5 driver, without WorldVoice's segment drain: NVDA {version} "
		f"lacks {len(missing)} of the names WorldVoice's SAPI5 driver needs: {', '.join(missing)}"
	)
	assert env.records == [("info", message)]


@pytest.mark.parametrize("version", OLD_RELEASES)
def test_old_nvda_sapi5_driver_runs_through_the_bridge_as_a_legacy_done_core(monkeypatch, tmp_path, version):
	env = load_release(monkeypatch, tmp_path, version)
	voice = env.outer.Voice
	assert voice.ready() is True
	warnings = []
	policy = env.policies.CompletionPolicy(
		nvdaVersion=version,
		logger=SimpleNamespace(warning=lambda *args: warnings.append(args)),
	)
	# resolveVoice gives a bound voice; the base methods it serves read no instance state.
	adapter = env.engineAdapter.VoiceClassAdapter(voice, lambda key: object.__new__(voice))
	adapter.open()
	try:
		core = adapter.core
		assert type(core) is env.base.SynthDriver
		assert adapter.notificationSource is core
		contract, support = policy.contractFor(voice, core, nvdaVersion=version, audioMode="default")
		assert support is None
		contract = policy.select(voice, core)
		assert contract == env.models.CompletionContract()
		assert contract.mode is env.models.CompletionMode.LEGACY_DONE
		assert warnings == []
		adapter.configureCompletion(contract)
		capabilities = adapter.capabilities
		assert capabilities.settings == frozenset(
			setting.id for setting in env.base.SynthDriver.supportedSettings
		)
		[spec] = adapter.listVoices()
		assert (spec.id, spec.name, spec.engine) == ("v1", "SAPI5:v1", "SAPI5")
		snapshot = env.models.VoiceSnapshot(
			voice_id="v1",
			revision=1,
			language="en",
			rate=70,
			pitch=50,
			volume=40,
			variant="default",
			inflection=50,
			rateBoost=False,
			waitfactor=0,
		)
		adapter.apply(spec, snapshot)
		spVoice = env.spVoices[-1]
		assert (spVoice.Rate, spVoice.Volume) == (core._percentToRate(70), 40)
		token = SimpleNamespace(is_cancelled=lambda: False, add_callback=lambda callback: lambda: None)
		# NVDA's speak(speechSequence) takes the sequence only, as the bridge passes it.
		adapter.speak(["hello", env.commands.IndexCommand(3)], token)
		[text] = spVoice.calls
		assert "hello" in text and '<Bookmark Mark="3" />' in text
		adapter.cancel()
		assert spVoice.calls[-1] is None
	finally:
		adapter.close()
	assert core.tts is None


@pytest.mark.parametrize("version", OLD_RELEASES)
def test_old_nvda_sapi5_same_voice_reapply_keeps_the_com_voice(monkeypatch, tmp_path, version):
	env = load_release(monkeypatch, tmp_path, version)
	voice = env.outer.Voice
	assert voice.ready() is True
	adapter = env.engineAdapter.VoiceClassAdapter(voice, lambda key: object.__new__(voice))
	adapter.open()
	try:
		core = adapter.core
		[spec] = adapter.listVoices()
		for revision, rate in ((1, 70), (2, 30)):
			snapshot = env.models.VoiceSnapshot(
				voice_id="v1",
				revision=revision,
				language="en",
				rate=rate,
				pitch=50,
				volume=40,
				variant="default",
				inflection=50,
				rateBoost=False,
				waitfactor=0,
			)
			adapter.apply(spec, snapshot)
			if revision == 1:
				created = len(env.spVoices)
		# NVDA's own driver rebuilds its COM voice on every voice set; the second apply skips it.
		assert len(env.spVoices) == created
		assert env.spVoices[-1].Rate == core._percentToRate(30)
	finally:
		adapter.close()


@pytest.mark.parametrize("version", WRAPPER_RELEASES)
def test_nvda_2025_3_and_later_choose_the_wrapper_silently(monkeypatch, tmp_path, version):
	env = load_release(monkeypatch, tmp_path, version)
	voice = env.outer.Voice
	assert release_missing("SAPI5", version) == ()
	assert voice.ready() is True
	assert voice.synthDriverClass is env.outer.SynthDriver
	assert issubclass(voice.synthDriverClass, env.base.SynthDriver)
	assert voice.drainProfile == env.outer.DrainProfile(wasapi_dependent=True)
	assert env.records == []
