"""PipelineScope registers the stages exactly while an owner wants them."""

import importlib.util
import sys
from types import ModuleType, SimpleNamespace


def load_scope_module(monkeypatch):
	package = ModuleType("scope_pkg")
	package.__path__ = []
	package.register_stages = lambda: None
	package.unregister_stages = lambda: None
	monkeypatch.setitem(sys.modules, "scope_pkg", package)
	settings = ModuleType("scope_pkg.settings")
	settings.pipeline_settings = SimpleNamespace(subscribe=lambda listener: None)
	settings.PipelineSettings = object
	settings.PipelineSettingsService = object
	monkeypatch.setitem(sys.modules, "scope_pkg.settings", settings)
	spec = importlib.util.spec_from_file_location(
		"scope_pkg.scope",
		"addon/synthDrivers/WorldVoice/pipeline/scope.py",
	)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module


class FakeSettings:
	def __init__(self, scope):
		self.scope = scope
		self.listeners = []

	def get(self):
		return SimpleNamespace(scope=self.scope)

	def subscribe(self, listener):
		self.listeners.append(listener)

	def change(self, scope):
		self.scope = scope
		for listener in self.listeners:
			listener(SimpleNamespace(scope=scope))


def make_scope(monkeypatch, scope):
	module = load_scope_module(monkeypatch)
	calls = []
	settings = FakeSettings(scope)
	pipeline = module.PipelineScope(
		settings,
		lambda: calls.append("register"),
		lambda: calls.append("unregister"),
	)
	return pipeline, settings, calls


def test_global_scope_all_registers_once_across_worldvoice_start_and_end(monkeypatch):
	pipeline, _settings, calls = make_scope(monkeypatch, "all")
	pipeline.attach_global()
	pipeline.worldvoice_started()
	pipeline.worldvoice_ended()
	assert calls == ["register"]
	assert pipeline.registered
	pipeline.detach_global()
	assert calls == ["register", "unregister"]


def test_worldvoice_scope_registers_only_while_worldvoice_runs(monkeypatch):
	pipeline, _settings, calls = make_scope(monkeypatch, "WorldVoice")
	pipeline.attach_global()
	assert calls == []
	pipeline.worldvoice_started()
	pipeline.worldvoice_ended()
	assert calls == ["register", "unregister"]


def test_scope_changes_apply_through_the_subscription(monkeypatch):
	pipeline, settings, calls = make_scope(monkeypatch, "WorldVoice")
	pipeline.attach_global()
	settings.change("all")
	settings.change("WorldVoice")
	assert calls == ["register", "unregister"]
	pipeline.worldvoice_started()
	settings.change("all")
	settings.change("WorldVoice")
	assert calls == ["register", "unregister", "register"]


def test_plugin_detach_keeps_running_worldvoice_registered(monkeypatch):
	pipeline, _settings, calls = make_scope(monkeypatch, "all")
	pipeline.attach_global()
	pipeline.worldvoice_started()
	pipeline.detach_global()
	assert calls == ["register"]
	pipeline.worldvoice_ended()
	assert calls == ["register", "unregister"]
