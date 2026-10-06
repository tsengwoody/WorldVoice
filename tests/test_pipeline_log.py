"""Pipeline log switching is shared by the plugin scripts and the log panel."""

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest
from nvda_stubs import StubModules

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "addon/synthDrivers/WorldVoice/log.py"
SERVICE = ROOT / "addon/globalPlugins/WorldVoice/pipelineLog.py"
PANEL = ROOT / "addon/globalPlugins/WorldVoice/speechSettingsDialog.py"


def load_service(monkeypatch, answers=None):
	answers = answers or []
	asked = []
	stubs = {
		"config": types.SimpleNamespace(conf={"WorldVoice": {"log": {"enable": False}}}),
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
		"synthDrivers.WorldVoice.pipeline": types.SimpleNamespace(
			pl=types.SimpleNamespace(move_to=lambda dst: asked.append(("moved", dst))),
		),
	}
	modules = StubModules(monkeypatch)
	for name, namespace in stubs.items():
		modules.module(name, **vars(namespace))
	modules.translation()
	spec = importlib.util.spec_from_file_location("pipeline_log_under_test", SERVICE)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
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


def test_prompts_map_answers(monkeypatch):
	module, _, asked = load_service(monkeypatch, answers=[2, 8, 2])
	assert module.confirm_enable(allow_cancel=True) == 2
	assert module.ask_export() is False
	assert module.ask_disable_on_start() is True
	assert asked[0][2] == 2 | 8 | 16


def test_log_panel_no_unticks_enable(monkeypatch):
	tree = ast.parse(PANEL.read_text(encoding="utf-8"))
	node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LogSettingsPanel")
	node.body = [
		n
		for n in node.body
		if isinstance(n, ast.FunctionDef) and n.name in {"isValid", "onEnableCheckboxChange"}
	]
	node.bases = []
	enabled = []
	environment = {
		"wx": types.SimpleNamespace(YES=2, NO=8, CANCEL=16),
		"pipeline_log": types.SimpleNamespace(enabled=False),
		"confirm_enable": lambda *, allow_cancel: 8,
	}
	exec(compile(ast.Module(body=[node], type_ignores=[]), str(PANEL), "exec"), environment)
	panel = environment["LogSettingsPanel"]()
	state = {"value": True}
	panel._enable_checkbox = types.SimpleNamespace(
		GetValue=lambda: state["value"],
		SetValue=lambda v: state.update(value=v),
	)
	panel.sliderEnable = lambda: enabled.append(True)
	panel.sliderDisable = lambda: enabled.append(False)
	assert panel.isValid() is True
	assert state["value"] is False
	assert enabled == [False]


@pytest.fixture
def log_module(monkeypatch, tmp_path):
	spec = importlib.util.spec_from_file_location("worldvoice_log_under_test", LOG)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	monkeypatch.setattr(module, "log_dir", tmp_path / "missing" / "log")
	return module


def test_pipeline_log_touches_the_disk_only_when_written(log_module, tmp_path):
	pipeline = log_module.PipelineLog("pipeline.csv")
	assert not (tmp_path / "missing").exists()
	pipeline.write("id", "label", "before", ["text"])
	lines = pipeline.log_file.read_text(encoding="utf-8").splitlines()
	assert lines[0] == ",".join(log_module.PipelineLog.FIELDNAMES)
	assert lines[1].startswith("id,label,before,")


def test_move_to_hands_over_the_log_and_starts_a_new_one(log_module, tmp_path):
	pipeline = log_module.PipelineLog("pipeline.csv")
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

	module.export_with_dialog(types.SimpleNamespace(move_to=move_to))
	assert moved == ([Path(path)] if outcome == "ok" else [])
	assert shown == {"cancel": [], "ok": ["message"], "fail": ["error"]}[outcome]


def test_move_to_exports_a_log_that_was_never_written(log_module, tmp_path):
	pipeline = log_module.PipelineLog("pipeline.csv")
	dst = tmp_path / "exported" / "out.csv"
	pipeline.move_to(dst)
	assert dst.read_text(encoding="utf-8").splitlines() == [",".join(log_module.PipelineLog.FIELDNAMES)]
	assert pipeline.log_file.read_text(encoding="utf-8").splitlines() == [
		",".join(log_module.PipelineLog.FIELDNAMES),
	]
