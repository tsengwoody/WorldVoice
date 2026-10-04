"""The three KeepMainLocale* policies."""

import importlib.util
import sys
from types import ModuleType, SimpleNamespace


def load_policy(monkeypatch):
	package = ModuleType("policy_pkg")
	package.__path__ = ["addon/synthDrivers/WorldVoice"]
	monkeypatch.setitem(sys.modules, "policy_pkg", package)
	spec = importlib.util.spec_from_file_location(
		"policy_pkg.mainLocalePolicy", "addon/synthDrivers/WorldVoice/mainLocalePolicy.py",
	)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module


def flags(**values):
	return {"WorldVoice": {"autoLanguageSwitching": {
		"KeepMainLocaleEngineConsistent": values.get("engine", True),
		"KeepMainLocaleVoiceConsistent": values.get("voice", True),
		"KeepMainLocaleParameterConsistent": values.get("parameter", False),
	}}, "speech": {"WorldVoice": {"rate": 70}}}


def test_engine_consistency_is_a_pending_flag_until_persisted(monkeypatch):
	module = load_policy(monkeypatch)
	conf = flags(engine=True)
	policy = module.EngineConsistency(lambda: conf)
	table = [SimpleNamespace(engine="A", name="a"), SimpleNamespace(engine="B", name="b")]
	assert [v.name for v in policy.visible(table, "A")] == ["a"]
	policy.enabled = False
	assert [v.name for v in policy.visible(table, "A")] == ["a", "b"]
	assert conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"] is True
	policy.persist()
	assert conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"] is False


def test_voice_consistency_follows_the_main_voice_only_when_enabled(monkeypatch):
	module = load_policy(monkeypatch)
	conf = flags(voice=False)
	assigned = []
	roles = SimpleNamespace(assign=lambda locale, voice: assigned.append((locale, voice)))
	policy = module.VoiceConsistency(lambda: conf, roles, language=lambda: "zh_TW")
	voice = SimpleNamespace(name="A:a", language="en_US")
	policy.follow(voice)
	assert assigned == []
	policy.enabled = True
	assert conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"] is True
	policy.follow(voice)
	policy.follow(SimpleNamespace(name="B:b", language=None))
	assert assigned == [("en", "A:a"), ("zh", "B:b")]


def test_parameter_copy_updates_each_voice_once(monkeypatch):
	module = load_policy(monkeypatch)
	updates = {}
	class State:
		def __init__(self, key):
			self.key = key
		def update(self, **values):
			updates.setdefault(self.key, []).append(values)
	base = SimpleNamespace(rate=72, pitch=60, volume=70, inflection=55, rateBoost=True, variant="x")
	store = SimpleNamespace(
		snapshot=lambda key: base, keys=lambda: ("a", "b"), state=State,
	)
	module.ParameterConsistency(lambda: flags()).copy_from(store, "a")
	expected = [{"rate": 72, "pitch": 60, "volume": 70, "inflection": 55, "rateBoost": True}]
	assert updates == {"a": expected, "b": expected}


def test_shared_section_only_when_enabled_and_available(monkeypatch):
	module = load_policy(monkeypatch)
	conf = flags(parameter=False)
	policy = module.ParameterConsistency(lambda: conf)
	assert policy.shared_section(lambda: "WorldVoice") is None
	policy.enabled = True
	assert policy.shared_section(lambda: "WorldVoice") == {"rate": 70}
	def unavailable():
		raise RuntimeError("no synth")
	assert policy.shared_section(unavailable) is None
	assert policy.shared_section(lambda: "Other") is None
