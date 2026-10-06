from types import SimpleNamespace

import pytest

from runtime_harness import FakeAdapter, MemoryRepository, make_spec


@pytest.fixture
def setup(compat, rt):
    repo = MemoryRepository()
    store = rt.settings.VoiceSettingsStore(repo)
    adapter = FakeAdapter()
    session = rt.session.EngineSession(adapter, store)
    binding = compat.facade.LegacyVoiceBinding(store, session, None)

    class Voice(compat.facade.VoiceFacade):
        pass

    voice = Voice(make_spec("Fake:a"), binding)
    return SimpleNamespace(repo=repo, store=store, adapter=adapter, session=session,
                           binding=binding, cls=Voice, voice=voice)


def test_facade_and_new_api_share_one_state(setup):
    facade, binding = setup.voice, setup.binding
    facade.rate = 72
    assert binding.settings.snapshot(facade.name).rate == 72
    binding.settings.state(facade.name).update(pitch=63)
    assert facade.pitch == 63
    binding.settings.rollback(facade.name)
    assert facade.rate == 50
    assert facade.pitch == 50
    assert setup.repo.saves == []
    other = setup.cls(make_spec("Fake:a"), setup.binding)
    other.volume = 23
    assert facade.volume == 23
    assert setup.repo.loads == ["Fake:a"]


def test_constructor_and_reload_do_not_activate_core(setup):
    assert setup.adapter.applied == []
    assert setup.adapter.open_count == 0
    setup.repo.values["Fake:a"] = {"rate": 81}
    setup.voice.loadParameter()
    assert setup.voice.rate == 81
    assert setup.store.state(setup.voice.name).baseline("rate") == 81
    assert setup.adapter.applied == []
    assert setup.adapter.open_count == 0


def test_all_settings_are_live_proxies(setup):
    voice = setup.voice
    voice.update_settings(rate=72, pitch=63, volume=84, variant="bright",
                          inflection=33, rateBoost=True, waitfactor=4)
    snapshot = voice.snapshot()
    assert (snapshot.rate, snapshot.pitch, snapshot.volume, snapshot.variant,
            snapshot.inflection, snapshot.rateBoost, snapshot.waitfactor) == (72, 63, 84, "bright", 33, True, 4)
    assert (voice.rate, voice.pitch, voice.volume, voice.variant,
            voice.inflection, voice.rateBoost, voice.waitfactor) == (72, 63, 84, "bright", 33, True, 4)
    assert snapshot.revision == 7
    voice.commit()
    voice.rate = 88
    setup.store.rollback(voice.name)
    assert voice.rate == 72
    assert len(setup.repo.saves) == 1
    # A snapshot is a value: later edits and rollbacks do not change it.
    assert snapshot.rate == 72


def test_failed_commit_does_not_advance_the_baseline(setup):
    setup.voice.rate = 72
    setup.repo.fail_next_save = True
    with pytest.raises(OSError):
        setup.voice.commit()
    assert setup.store.state(setup.voice.name).baseline("rate") == 50
    setup.store.rollback(setup.voice.name)
    assert setup.voice.rate == 50


def test_stop_cancels_the_shared_session_without_closing_it(setup):
    setup.voice.stop()
    assert setup.adapter.cancel_count == 1
    assert setup.adapter.close_count == 0
    assert setup.repo.saves == []


def test_facade_reads_its_engine_core_from_the_binding(setup, compat):
    core = object()
    binding = compat.facade.LegacyVoiceBinding(setup.store, setup.session, core)
    voice = setup.cls(make_spec("Fake:b", "fr"), binding)
    assert voice.core is core and setup.voice.core is None
    assert (voice.id, voice.name, voice.language) == ("b", "Fake:b", "fr")
    assert "core" not in vars(voice) and not hasattr(setup.cls, "_runtime_binding")
