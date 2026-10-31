"""Pipeline log switching is shared by the plugin scripts and the log panel."""

import sys
import types
from pathlib import Path

import pytest
from addon_loader import ADDON, WORLDVOICE, load_definitions, load_source
from nvda_stubs import RefusingSection, StubModules, worldvoice_conf
from pipeline_harness import load_pipeline_module, load_settings_module, punctuation_settings

RECORDER = WORLDVOICE / "pipeline/recorder.py"
SERVICE = ADDON / "globalPlugins/WorldVoice/pipelineLog.py"
PANEL = ADDON / "globalPlugins/WorldVoice/panels/log.py"


def load_service(monkeypatch, answers=None, read_stored=None):
	"""The real pipelineLog.py; read_stored replaces the pipeline settings' reader of a stored value."""
	answers = answers or []
	asked = []
	stubs = {
		"config": types.SimpleNamespace(conf=worldvoice_conf()),
		"gui": types.SimpleNamespace(
			mainFrame=None,
			messageBox=lambda *args: asked.append(args) or answers.pop(0),
		),
		"wx": types.SimpleNamespace(YES=2, NO=8, CANCEL=16),
		"logHandler": types.SimpleNamespace(
			log=types.SimpleNamespace(error=lambda *a, **k: asked.append("logged")),
		),
		"addonHandler": types.SimpleNamespace(initTranslation=lambda: None),
		"synthDrivers": types.SimpleNamespace(__path__=[]),
		"synthDrivers.WorldVoice": types.SimpleNamespace(__path__=[]),
		"synthDrivers.WorldVoice.pipeline": types.SimpleNamespace(__path__=[]),
		"synthDrivers.WorldVoice.pipeline.registry": types.SimpleNamespace(
			pl=types.SimpleNamespace(move_to=lambda dst: asked.append(("moved", dst))),
		),
		"synthDrivers.WorldVoice.pipeline.settings": types.SimpleNamespace(
			read_stored=read_stored or (lambda section, key, default: section.get(key, default)),
		),
	}
	modules = StubModules(monkeypatch)
	for name, namespace in stubs.items():
		modules.module(name, **vars(namespace))
	modules.translation()
	module = load_source(monkeypatch, "pipeline_log_under_test", SERVICE)
	return module, sys.modules["config"].conf, asked


def test_service_switches_config_and_swallows_export_errors(monkeypatch):
	module, conf, asked = load_service(monkeypatch)

	def broken():
		raise OSError("disk")

	service = module.PipelineLogService(lambda: conf, broken)
	service.enable()
	assert service.enabled and conf["WorldVoice"]["log"]["enable"] is True
	service.disable()
	assert conf["WorldVoice"]["log"]["enable"] is False
	service.export()
	assert asked == ["logged"]


def test_service_reads_an_invalid_enable_flag_as_off(monkeypatch):
	settings = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	refused = RefusingSection(
		{"enable": "maybe"},
		{"enable": sys.modules["configobj.validate"].VdtTypeError("maybe")},
	)
	module, _conf, _asked = load_service(monkeypatch, read_stored=settings.read_stored)
	assert module.PipelineLogService(lambda: {"WorldVoice": {"log": refused}}).enabled is False


def test_prompts_map_answers(monkeypatch):
	module, _, asked = load_service(monkeypatch, answers=[2, 8, 2])
	assert module.confirmEnable(allowCancel=True) == 2
	assert module.askExport() is False
	assert module.askDisableOnStart() is True
	assert asked[0][2] == 2 | 8 | 16


def test_log_panel_no_unticks_enable(monkeypatch):
	enabled = []
	environment = {
		"wx": types.SimpleNamespace(YES=2, NO=8, CANCEL=16),
		"pipelineLogService": types.SimpleNamespace(enabled=False),
		"confirmEnable": lambda *, allowCancel: 8,
	}
	load_definitions(PANEL, ["LogSettingsPanel"], environment, members={"isValid", "onEnableCheckboxChange"})
	panel = environment["LogSettingsPanel"]()
	state = {"value": True}
	panel._enableCheckbox = types.SimpleNamespace(
		GetValue=lambda: state["value"],
		SetValue=lambda v: state.update(value=v),
	)
	panel.sliderEnable = lambda: enabled.append(True)
	panel.sliderDisable = lambda: enabled.append(False)
	assert panel.isValid() is True
	assert state["value"] is False
	assert enabled == [False]


@pytest.fixture
def log_module(monkeypatch):
	return load_source(monkeypatch, "worldvoice_log_under_test", RECORDER)


def test_the_pipeline_log_is_written_to_the_add_on_log_folder(monkeypatch):
	# The recorder moved into pipeline/ (phase 38); the file it writes stays addon/log/pipeline.csv.
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	recorder = load_source(monkeypatch, "worldvoice_recorder_path_under_test", RECORDER)
	assert recorder.PipelineLog(*module.pl.args).log_file == ADDON / "log" / "pipeline.csv"


def test_pipeline_log_touches_the_disk_only_when_written(log_module, tmp_path):
	pipeline = log_module.PipelineLog(tmp_path / "missing" / "log" / "pipeline.csv")
	assert not (tmp_path / "missing").exists()
	pipeline.write("id", "label", "before", ["text"])
	lines = pipeline.log_file.read_text(encoding="utf-8").splitlines()
	assert lines[0] == ",".join(log_module.PipelineLog.FIELDNAMES)
	assert lines[1].startswith("id,label,before,")


def test_move_to_hands_over_the_log_and_starts_a_new_one(log_module, tmp_path):
	pipeline = log_module.PipelineLog(tmp_path / "missing" / "log" / "pipeline.csv")
	pipeline.write("id", "label", "before", ["text"])
	dst = tmp_path / "exported" / "out.csv"
	pipeline.move_to(dst)
	assert len(dst.read_text(encoding="utf-8").splitlines()) == 2
	assert pipeline.log_file.read_text(encoding="utf-8").splitlines() == [
		",".join(log_module.PipelineLog.FIELDNAMES),
	]


class Dialog:
	def __init__(self, answer, path):
		self.answer, self.path = answer, path

	def __call__(self, *args, **kwargs):
		return self

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		return False

	def ShowModal(self):
		return self.answer

	def GetPath(self):
		return self.path


@pytest.mark.parametrize("outcome", ["cancel", "ok", "fail"])
def test_export_with_dialog(monkeypatch, tmp_path, outcome):
	module, _, _ = load_service(monkeypatch)
	shown = []
	path = str(tmp_path / "out.csv")
	monkeypatch.setattr(
		module,
		"wx",
		types.SimpleNamespace(
			FileDialog=Dialog(5100 if outcome != "cancel" else 5101, path),
			ID_OK=5100,
			FD_SAVE=1,
			FD_OVERWRITE_PROMPT=2,
			OK=4,
			ICON_INFORMATION=8,
			MessageBox=lambda *args, **kwargs: shown.append("message"),
			LogError=lambda message: shown.append("error"),
		),
	)
	moved = []

	def move_to(dst):
		if outcome == "fail":
			raise OSError("disk")
		moved.append(dst)

	module.exportWithDialog(types.SimpleNamespace(move_to=move_to))
	assert moved == ([Path(path)] if outcome == "ok" else [])
	assert shown == {"cancel": [], "ok": ["message"], "fail": ["error"]}[outcome]


def test_move_to_exports_a_log_that_was_never_written(log_module, tmp_path):
	pipeline = log_module.PipelineLog(tmp_path / "missing" / "log" / "pipeline.csv")
	dst = tmp_path / "exported" / "out.csv"
	pipeline.move_to(dst)
	assert dst.read_text(encoding="utf-8").splitlines() == [",".join(log_module.PipelineLog.FIELDNAMES)]
	assert pipeline.log_file.read_text(encoding="utf-8").splitlines() == [
		",".join(log_module.PipelineLog.FIELDNAMES),
	]
