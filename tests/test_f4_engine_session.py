from types import SimpleNamespace

import pytest
from runtime_harness import MemoryRepository, make_spec


class FakeCore:
	def __init__(self, supported=("rate", "pitch", "volume")):
		object.__setattr__(self, "writes", [])
		object.__setattr__(self, "fail_on", None)
		object.__setattr__(
			self,
			"supportedSettings",
			[SimpleNamespace(id=name) for name in supported],
		)

	def __setattr__(self, name, value):
		if name in {"voice", "rateBoost", "rate", "pitch", "volume", "inflection"}:
			self.writes.append((name, value))
			if name == self.fail_on:
				raise RuntimeError(name)
		object.__setattr__(self, name, value)


@pytest.fixture
def engine(session_module, bridge_modules, rt):
	store = rt.voice_settings.VoiceSettingsStore(MemoryRepository())
	for key in ("Fake:a", "Fake:b"):
		store.ensure(make_spec(key))
	result = SimpleNamespace(core=FakeCore(), store=store, hook=lambda core, snapshot: None)

	def adapter(core):
		class Legacy:
			@classmethod
			def create_core(cls):
				return core

			@classmethod
			def destroy_core(cls, target):
				pass

			@classmethod
			def supportedSettings(cls):
				return [setting.id for setting in core.supportedSettings]

		return bridge_modules.adapter.LegacyEngineAdapter(
			Legacy,
			lambda key: SimpleNamespace(
				applyEngineSettings=lambda core, snapshot: result.hook(core, snapshot),
			),
		)

	result.adapter = adapter
	result.session = session_module.EngineSession(adapter(result.core), store)
	result.session.open()
	yield result
	result.session.close()


def test_first_activation_writes_supported_settings_in_order(engine):
	applied = []
	engine.hook = lambda core, snapshot: applied.append((core, snapshot))
	assert engine.session.activate("Fake:a") is True
	assert engine.core.writes == [
		("voice", "a"),
		("rate", 50),
		("pitch", 50),
		("volume", 50),
	]
	assert applied == [(engine.core, engine.store.snapshot("Fake:a"))]


def test_same_stamp_skips_setters_and_voice_switch_reapplies(engine):
	applied = []
	engine.hook = lambda core, snapshot: applied.append(snapshot.voice_id)
	assert engine.session.activate("Fake:a") is True
	before = len(engine.core.writes)
	assert engine.session.activate("Fake:a") is False
	assert len(engine.core.writes) == before
	assert applied == ["a"]
	assert engine.session.activate("Fake:b") is True
	assert engine.session.activate("Fake:a") is True
	assert applied == ["a", "b", "a"]


def test_revision_change_reapplies_same_voice(engine):
	assert engine.session.activate("Fake:a") is True
	before = len(engine.core.writes)
	engine.store.state("Fake:a").update(rate=72)
	assert engine.session.activate("Fake:a") is True
	assert len(engine.core.writes) > before
	assert engine.core.rate == 72


def test_reopen_reapplies_same_snapshot(engine):
	assert engine.session.activate("Fake:a") is True
	engine.session.close()
	engine.session.open()
	engine.core.writes.clear()
	assert engine.session.activate("Fake:a") is True
	assert engine.core.writes == [
		("voice", "a"),
		("rate", 50),
		("pitch", 50),
		("volume", 50),
	]


def test_partial_failure_invalidates_stamp(engine):
	engine.session.activate("Fake:a")
	engine.store.state("Fake:a").update(variant="bright")
	engine.hook = lambda core, value: (_ for _ in ()).throw(RuntimeError("variant"))
	with pytest.raises(RuntimeError, match="variant"):
		engine.session.activate("Fake:a")
	engine.hook = lambda core, value: None
	engine.store.rollback("Fake:a")
	assert engine.session.activate("Fake:a") is True


def test_setter_failure_invalidates_stamp(engine):
	engine.session.activate("Fake:a")
	engine.core.fail_on = "pitch"
	engine.store.state("Fake:a").update(rate=72)
	with pytest.raises(RuntimeError, match="pitch"):
		engine.session.activate("Fake:a")
	engine.core.fail_on = None
	engine.store.rollback("Fake:a")
	assert engine.session.activate("Fake:a") is True
