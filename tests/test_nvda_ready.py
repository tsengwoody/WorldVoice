"""Voice.ready() of eSpeak, SAPI5 and OneCore checks their NVDA names on the live NVDA (phase 51)."""

import sys
from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, load_source
from engine_contract_harness import EspeakAdapter, OneCoreAdapter, SAPI5Adapter
from nvda_releases import WORKING_TREE, host_names, port_names, release_missing

# Per engine: the harness adapter, NVDA's module and synth class in the harness environment, and
# one listed module name and one listed class name to take away.
CASES = {
	"Espeak": (
		EspeakAdapter,
		lambda env: env.inner,
		lambda env: env.base.SynthDriver,
		"isSpeaking",
		"_onIndexReached",
	),
	"SAPI5": (
		SAPI5Adapter,
		lambda env: env.base,
		lambda env: env.base.SynthDriver,
		"_SapiEvent",
		"_speakThread",
	),
	"OneCore": (
		OneCoreAdapter,
		lambda env: env.base,
		lambda env: env.base.SynthDriver,
		"_OcSsmlConverter",
		"_processQueue",
	),
}


class RecordingLogger:
	def __init__(self):
		self.records = []

	def __getattr__(self, level):
		return lambda message, *args: self.records.append((level, message % args))


class UnreadVersion:
	@property
	def version(self):
		raise AssertionError("the NVDA version is read only to log a skip")


@pytest.fixture(params=sorted(CASES))
def engine(request, monkeypatch, tmp_path):
	adapter_class, module, host_class, module_name, class_name = CASES[request.param]
	adapter = adapter_class()
	adapter.open(monkeypatch, tmp_path)
	try:
		yield SimpleNamespace(
			name=request.param,
			env=adapter.env,
			module=module(adapter.env),
			host_class=host_class(adapter.env),
			module_name=module_name,
			class_name=class_name,
		)
	finally:
		adapter.close()


def ready(engine, monkeypatch, version):
	logger = RecordingLogger()
	with monkeypatch.context() as patch:
		patch.setattr(engine.env.outer, "log", logger)
		patch.setitem(sys.modules, "versionInfo", version)
		result = engine.env.outer.Voice.ready()
	return result, logger.records


def test_ready_on_ref_nvda_is_true_and_silent(engine, monkeypatch):
	assert ready(engine, monkeypatch, UnreadVersion()) == (True, [])


def test_ready_skips_with_one_warning_when_a_module_name_is_missing(engine, monkeypatch):
	with monkeypatch.context() as patch:
		patch.delattr(engine.module, engine.module_name)
		result, records = ready(engine, monkeypatch, SimpleNamespace(version="2025.1.0"))
	assert result is False
	message = (
		f"Skipping {engine.name} engine candidate: NVDA 2025.1.0 lacks names this engine needs: "
		f"{engine.module.__name__}.{engine.module_name}"
	)
	assert records == [("warning", message)]


def test_ready_skips_when_a_class_name_is_missing(engine, monkeypatch):
	owner = f"{engine.host_class.__module__}.{engine.host_class.__qualname__}"
	with monkeypatch.context() as patch:
		patch.delattr(engine.host_class, engine.class_name)
		result, records = ready(engine, monkeypatch, SimpleNamespace(version="2026.3.0"))
	assert result is False
	assert [level for level, _message in records] == ["warning"]
	assert records[0][1].endswith(f"NVDA 2026.3.0 lacks names this engine needs: {owner}.{engine.class_name}")


def test_live_and_static_views_agree_on_ref_nvda(engine):
	module_names, class_names = port_names(engine.name)
	live = host_names.missing_host_names(
		engine.module,
		engine.host_class,
		module_names=module_names,
		class_names=class_names,
	)
	assert live == release_missing(engine.name, WORKING_TREE) == ()


def test_sapi5_imports_and_skips_without_audio_stream_class(monkeypatch, tmp_path):
	adapter = SAPI5Adapter()
	adapter.open(monkeypatch, tmp_path)
	try:
		with monkeypatch.context() as patch:
			# NVDA 2024.x has no SynthDriverAudioStream; the wrapper reads it in a class statement.
			patch.delattr(adapter.env.base, "SynthDriverAudioStream")
			outer = load_source(
				patch,
				"synthDrivers.WorldVoice.driver.SAPI5",
				WORLDVOICE / "driver/SAPI5/__init__.py",
			)
			logger = RecordingLogger()
			patch.setattr(outer, "log", logger)
			patch.setitem(sys.modules, "versionInfo", SimpleNamespace(version="2024.1.0"))
			assert outer.Voice.ready() is False
		message = (
			"Skipping SAPI5 engine candidate: NVDA 2024.1.0 lacks names this engine needs: "
			"synthDrivers.sapi5.SynthDriverAudioStream"
		)
		assert logger.records == [("warning", message)]
	finally:
		adapter.close()
