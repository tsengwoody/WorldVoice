"""Voice.ready() of eSpeak, SAPI5 and OneCore checks their NVDA names on the live NVDA (phase 51).

eSpeak and OneCore are skipped when a name is missing. SAPI5 then uses NVDA's own SAPI5 driver as
the whole core, without WorldVoice's segment drain (user decision 2026-10-28, spec §9 Q1).
"""

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
		raise AssertionError("the NVDA version is read only to write a log line")


def _opened(name, monkeypatch, tmp_path):
	adapter_class, module, host_class, module_name, class_name = CASES[name]
	adapter = adapter_class()
	adapter.open(monkeypatch, tmp_path)
	try:
		yield SimpleNamespace(
			name=name,
			env=adapter.env,
			module=module(adapter.env),
			host_class=host_class(adapter.env),
			module_name=module_name,
			class_name=class_name,
		)
	finally:
		adapter.close()


@pytest.fixture(params=sorted(CASES))
def engine(request, monkeypatch, tmp_path):
	yield from _opened(request.param, monkeypatch, tmp_path)


# Engines that discovery skips when the running NVDA lacks a listed name.
@pytest.fixture(params=["Espeak", "OneCore"])
def skipped_engine(request, monkeypatch, tmp_path):
	yield from _opened(request.param, monkeypatch, tmp_path)


@pytest.fixture
def sapi5(monkeypatch, tmp_path):
	yield from _opened("SAPI5", monkeypatch, tmp_path)


def ready(engine, monkeypatch, version):
	logger = RecordingLogger()
	with monkeypatch.context() as patch:
		patch.setattr(engine.env.outer, "log", logger)
		patch.setitem(sys.modules, "versionInfo", version)
		result = engine.env.outer.Voice.ready()
	return result, logger.records


def test_ready_on_ref_nvda_is_true_and_silent(engine, monkeypatch):
	assert ready(engine, monkeypatch, UnreadVersion()) == (True, [])


def test_ready_skips_with_one_warning_when_a_module_name_is_missing(skipped_engine, monkeypatch):
	engine = skipped_engine
	with monkeypatch.context() as patch:
		patch.delattr(engine.module, engine.module_name)
		result, records = ready(engine, monkeypatch, SimpleNamespace(version="2025.1.0"))
	assert result is False
	message = (
		f"Skipping {engine.name} engine candidate: NVDA 2025.1.0 lacks names this engine needs: "
		f"{engine.module.__name__}.{engine.module_name}"
	)
	assert records == [("warning", message)]


def test_ready_skips_when_a_class_name_is_missing(skipped_engine, monkeypatch):
	engine = skipped_engine
	owner = f"{engine.host_class.__module__}.{engine.host_class.__qualname__}"
	with monkeypatch.context() as patch:
		patch.delattr(engine.host_class, engine.class_name)
		result, records = ready(engine, monkeypatch, SimpleNamespace(version="2026.3.0"))
	assert result is False
	assert [level for level, _message in records] == ["warning"]
	assert records[0][1].endswith(f"NVDA 2026.3.0 lacks names this engine needs: {owner}.{engine.class_name}")


def sapi5_fallback_message(version, *missing):
	return (
		f"SAPI5 engine uses NVDA's own SAPI5 driver, without WorldVoice's segment drain: NVDA {version} "
		f"lacks {len(missing)} of the names WorldVoice's SAPI5 driver needs: {', '.join(missing)}"
	)


def assert_sapi5_uses_the_wrapper(sapi5):
	voice = sapi5.env.outer.Voice
	assert voice.synthDriverClass is sapi5.env.outer.SynthDriver
	assert voice.drainProfile == sapi5.env.outer.DrainProfile(wasapi_dependent=True)


def assert_sapi5_uses_nvdas_driver(sapi5):
	voice = sapi5.env.outer.Voice
	assert voice.synthDriverClass is sapi5.host_class
	assert voice.drainProfile is None


def test_sapi5_on_ref_nvda_uses_the_wrapper(sapi5, monkeypatch):
	assert ready(sapi5, monkeypatch, UnreadVersion()) == (True, [])
	assert_sapi5_uses_the_wrapper(sapi5)


def test_sapi5_uses_nvdas_driver_with_one_info_line_when_a_module_name_is_missing(sapi5, monkeypatch):
	with monkeypatch.context() as patch:
		patch.delattr(sapi5.module, sapi5.module_name)
		result, records = ready(sapi5, monkeypatch, SimpleNamespace(version="2025.1.0"))
	assert result is True
	assert_sapi5_uses_nvdas_driver(sapi5)
	assert records == [
		("info", sapi5_fallback_message("2025.1.0", f"synthDrivers.sapi5.{sapi5.module_name}")),
	]


def test_sapi5_uses_nvdas_driver_when_a_class_name_is_missing(sapi5, monkeypatch):
	with monkeypatch.context() as patch:
		patch.delattr(sapi5.host_class, sapi5.class_name)
		result, records = ready(sapi5, monkeypatch, SimpleNamespace(version="2025.2.0"))
	assert result is True
	assert_sapi5_uses_nvdas_driver(sapi5)
	missing = f"synthDrivers.sapi5.SynthDriver.{sapi5.class_name}"
	assert records == [("info", sapi5_fallback_message("2025.2.0", missing))]


def test_sapi5_choice_follows_each_ready_call(sapi5, monkeypatch):
	# ready() decides both ways each time: a later check on a complete NVDA restores the wrapper.
	with monkeypatch.context() as patch:
		patch.delattr(sapi5.module, sapi5.module_name)
		ready(sapi5, monkeypatch, SimpleNamespace(version="2025.1.0"))
	assert_sapi5_uses_nvdas_driver(sapi5)
	assert ready(sapi5, monkeypatch, UnreadVersion()) == (True, [])
	assert_sapi5_uses_the_wrapper(sapi5)


def test_live_and_static_views_agree_on_ref_nvda(engine):
	module_names, class_names = port_names(engine.name)
	live = host_names.missing_host_names(
		engine.module,
		engine.host_class,
		module_names=module_names,
		class_names=class_names,
	)
	assert live == release_missing(engine.name, WORKING_TREE) == ()


def test_sapi5_imports_and_uses_nvdas_driver_without_audio_stream_class(monkeypatch, tmp_path):
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
			assert outer.Voice.ready() is True
			assert outer.Voice.synthDriverClass is adapter.env.base.SynthDriver
			assert outer.Voice.drainProfile is None
		message = sapi5_fallback_message("2024.1.0", "synthDrivers.sapi5.SynthDriverAudioStream")
		assert logger.records == [("info", message)]
	finally:
		adapter.close()


def _label_definitions():
	"""(file, line) of every NVDA label function and versionInfo import in the wrappers and bridge."""
	import ast

	found = []
	paths = sorted((WORLDVOICE / "driver").glob("*/__init__.py")) + sorted(
		(WORLDVOICE / "bridge").glob("*.py"),
	)
	for path in paths:
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
			if isinstance(node, ast.FunctionDef) and node.name in {"nvdaLabel", "_nvdaLabel"}:
				found.append((path.relative_to(WORLDVOICE).as_posix(), "def"))
			elif isinstance(node, ast.Import) and any(alias.name == "versionInfo" for alias in node.names):
				found.append((path.relative_to(WORLDVOICE).as_posix(), "import"))
	return found


def test_one_nvda_label_names_the_running_nvda(monkeypatch):
	# One function names NVDA in the ready() log lines; it reads versionInfo only when called.
	assert _label_definitions() == [("bridge/nvdaVersion.py", "def"), ("bridge/nvdaVersion.py", "import")]
	module = load_source(monkeypatch, "worldvoice_nvda_version", WORLDVOICE / "bridge/nvdaVersion.py")
	monkeypatch.setitem(sys.modules, "versionInfo", SimpleNamespace(version="2026.1.0"))
	assert module.nvdaLabel() == "NVDA 2026.1.0"
