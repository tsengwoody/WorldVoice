"""Pipeline log switching is shared by the plugin scripts and the log panel."""

import ast
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "addon/globalPlugins/WorldVoice/pipelineLog.py"
PANEL = ROOT / "addon/globalPlugins/WorldVoice/speechSettingsDialog.py"


def load_service(monkeypatch, answers=None):
	answers = answers or []
	asked = []
	stubs = {
		"config": types.SimpleNamespace(conf={"WorldVoice": {"log": {"enable": False}}}),
		"gui": types.SimpleNamespace(mainFrame=None, messageBox=lambda *args: asked.append(args) or answers.pop(0)),
		"wx": types.SimpleNamespace(YES=2, NO=8, CANCEL=16),
		"logHandler": types.SimpleNamespace(log=types.SimpleNamespace(error=lambda *a, **k: asked.append("logged"))),
		"addonHandler": types.SimpleNamespace(initTranslation=lambda: None),
		"synthDrivers": types.SimpleNamespace(__path__=[]),
		"synthDrivers.WorldVoice": types.SimpleNamespace(__path__=[]),
		"synthDrivers.WorldVoice.pipeline": types.SimpleNamespace(pl=types.SimpleNamespace(export=lambda: asked.append("exported"))),
	}
	for name, module in stubs.items():
		monkeypatch.setitem(sys.modules, name, module)
	import builtins
	monkeypatch.setattr(builtins, "_", lambda text: text, raising=False)
	spec = importlib.util.spec_from_file_location("pipeline_log_under_test", SERVICE)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module, stubs["config"].conf, asked


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
	node.body = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name in {"isValid", "onEnableCheckboxChange"}]
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
	panel._enable_checkbox = types.SimpleNamespace(GetValue=lambda: state["value"], SetValue=lambda v: state.update(value=v))
	panel.sliderEnable = lambda: enabled.append(True)
	panel.sliderDisable = lambda: enabled.append(False)
	assert panel.isValid() is True
	assert state["value"] is False
	assert enabled == [False]
