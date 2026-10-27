"""The three keepMainLocale* policies."""

from types import SimpleNamespace

from addon_loader import WORLDVOICE, alias_package, load_source
from nvda_stubs import worldvoice_conf


def load_policy(monkeypatch):
	alias_package(monkeypatch, "policy_pkg", WORLDVOICE)
	return load_source(
		monkeypatch,
		"policy_pkg.voices.mainLocalePolicy",
		WORLDVOICE / "voices/mainLocalePolicy.py",
	)


def flags(**values):
	given = {
		"keepMainLocaleEngineConsistent": values.get("engine"),
		"keepMainLocaleVoiceConsistent": values.get("voice"),
		"keepMainLocaleParameterConsistent": values.get("parameter"),
	}
	# A flag the test leaves out keeps the confspec default.
	switching = {key: value for key, value in given.items() if value is not None}
	return {**worldvoice_conf(autoLanguageSwitching=switching), "speech": {"WorldVoice": {"rate": 70}}}


def test_engine_consistency_reads_config_and_previews_without_saving(monkeypatch):
	module = load_policy(monkeypatch)
	conf = flags(engine=True)
	policy = module.EngineConsistency(lambda: conf)
	table = [SimpleNamespace(engine="A", name="a"), SimpleNamespace(engine="B", name="b")]
	assert [v.name for v in policy.visible(table, "A")] == ["a"]
	policy.preview = False
	assert [v.name for v in policy.visible(table, "A")] == ["a", "b"]
	assert conf["WorldVoice"]["autoLanguageSwitching"]["keepMainLocaleEngineConsistent"] is True
	policy.preview = None
	policy.enabled = False
	assert conf["WorldVoice"]["autoLanguageSwitching"]["keepMainLocaleEngineConsistent"] is False
	assert [v.name for v in policy.visible(table, "A")] == ["a", "b"]


def test_engine_consistency_follows_a_profile_switch(monkeypatch):
	module = load_policy(monkeypatch)
	profiles = {"normal": flags(engine=False), "app": flags(engine=True)}
	active = {"name": "normal"}
	policy = module.EngineConsistency(lambda: profiles[active["name"]])
	assert policy.enabled is False
	active["name"] = "app"
	assert policy.enabled is True


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
	assert conf["WorldVoice"]["autoLanguageSwitching"]["keepMainLocaleVoiceConsistent"] is True
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
		snapshot=lambda key: base,
		names=lambda: ("a", "b"),
		state=State,
	)
	module.ParameterConsistency(lambda: flags()).copy_from(store, "a")
	expected = [{"rate": 72, "pitch": 60, "volume": 70, "inflection": 55, "rateBoost": True}]
	assert updates == {"a": expected, "b": expected}


def test_inherited_parameters_follow_the_main_voice_only_when_enabled(monkeypatch):
	module = load_policy(monkeypatch)
	conf = flags(parameter=False)
	policy = module.ParameterConsistency(lambda: conf)
	base = SimpleNamespace(rate=72, pitch=60, volume=70, inflection=55, rateBoost=True, variant="x")
	store = SimpleNamespace(snapshot=lambda key: base if key == "a" else None)
	assert policy.inherited(store, "a") == {}
	policy.enabled = True
	assert policy.inherited(store, "a") == {
		"rate": 72,
		"pitch": 60,
		"volume": 70,
		"inflection": 55,
		"rateBoost": True,
	}
