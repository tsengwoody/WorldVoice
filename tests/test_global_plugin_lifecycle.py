"""GlobalPlugin terminate always runs its later cleanup steps."""

import ast
from pathlib import Path
import types

import pytest


PLUGIN_PATH = Path(__file__).resolve().parents[1] / "addon/globalPlugins/WorldVoice/__init__.py"


def load_plugin_class(environment):
	tree = ast.parse(PLUGIN_PATH.read_text(encoding="utf-8"))
	node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GlobalPlugin")
	exec(compile(ast.Module(body=[node], type_ignores=[]), str(PLUGIN_PATH), "exec"), environment)
	return environment["GlobalPlugin"]


def plugin_environment(calls, *, secure, menu_error=None):
	class Base:
		def __init__(self):
			pass

	class Menu:
		def Remove(self, item):
			if menu_error is not None:
				raise menu_error

	def record(name):
		return lambda *args, **kwargs: calls.append(name)

	tray = types.SimpleNamespace(menu=Menu(), Bind=lambda *args: None)
	return {
		"globalPluginHandler": types.SimpleNamespace(GlobalPlugin=Base),
		"script": lambda **kwargs: lambda function: function,
		"_": lambda text: text,
		"ADDON_SUMMARY": "WorldVoice",
		"globalVars": types.SimpleNamespace(appArgs=types.SimpleNamespace(secure=secure)),
		"gui": types.SimpleNamespace(mainFrame=types.SimpleNamespace(sysTrayIcon=tray)),
		"wx": types.SimpleNamespace(CallAfter=lambda *args: None, ID_ANY=-1),
		"patch": record("patch"),
		"unpatch": record("unpatch"),
		"pipeline_scope": types.SimpleNamespace(
			attach_global=record("attach"),
			detach_global=record("detach"),
		),
	}


def test_secure_mode_terminate_runs_every_cleanup_step():
	calls = []
	plugin = load_plugin_class(plugin_environment(calls, secure=True))()
	assert plugin.submenu_item is None

	plugin.terminate()

	assert "unpatch" in calls
	assert calls[-1] == "detach"


def test_dead_menu_runtime_error_does_not_stop_cleanup():
	calls = []
	environment = plugin_environment(
		calls,
		secure=True,
		menu_error=RuntimeError("wrapped C/C++ object deleted"),
	)
	plugin = load_plugin_class(environment)()
	plugin.submenu_item = types.SimpleNamespace(Destroy=lambda: calls.append("destroy"))

	plugin.terminate()

	assert "unpatch" in calls
	assert calls[-1] == "detach"
