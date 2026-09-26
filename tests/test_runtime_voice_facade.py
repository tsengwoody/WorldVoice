from types import SimpleNamespace

import pytest

from runtime_harness import FakeAdapter, MemoryRepository, make_spec, rt
from test_runtime_legacy_adapter import compat


class RecordingTasks:
    def __init__(self):
        self.speeches = []
        self.breaks = []

    def append_speech(self, request, session, name, commands):
        self.speeches.append((request, session, name, commands))

    def append_break(self, request, seconds):
        self.breaks.append((request, seconds))


@pytest.fixture
def setup(compat, rt):
    repo = MemoryRepository()
    store = rt.settings.VoiceSettingsStore(repo)
    adapter = FakeAdapter()
    session = rt.session.EngineSession(adapter, store)
    binding = compat.facade.LegacyVoiceBinding(store, session, make_spec)

    class Voice(compat.facade.VoiceFacade):
        _runtime_binding = binding

    tasks = RecordingTasks()
    voice = Voice("a", "Fake:a", tasks, "en")
    return SimpleNamespace(repo=repo, store=store, adapter=adapter, session=session,
                           binding=binding, cls=Voice, tasks=tasks, voice=voice)


def test_facade_and_new_api_share_one_state(setup):
    facade, binding = setup.voice, setup.binding
    facade.rate = 72
    assert binding.settings.snapshot(facade.name).rate == 72
    binding.settings.state(facade.name).update(pitch=63)
    assert facade.pitch == 63
    facade.rollback()
    assert facade.rate == 50
    assert facade.pitch == 50
    assert setup.repo.saves == []
    other = setup.cls("a", "Fake:a", setup.tasks)
    other.volume = 23
    assert facade.volume == 23
    assert setup.repo.loads == ["Fake:a"]


def test_constructor_and_reload_do_not_activate_core(setup):
    assert setup.adapter.applied == []
    assert setup.adapter.open_count == 0
    setup.repo.values["Fake:a"] = {"rate": 81}
    setup.voice.loadParameter()
    assert setup.voice.rate == 81
    assert setup.voice.commit_rate == 81
    assert setup.adapter.applied == []
    assert setup.adapter.open_count == 0


def test_all_settings_and_baselines_are_live_proxies(setup):
    voice = setup.voice
    voice.update_settings(rate=72, pitch=63, volume=84, variant="bright",
                          inflection=33, rateBoost=True, waitfactor=4)
    snapshot = voice.snapshot()
    assert (snapshot.rate, snapshot.pitch, snapshot.volume, snapshot.variant,
            snapshot.inflection, snapshot.rateBoost, snapshot.waitfactor) == (72, 63, 84, "bright", 33, True, 4)
    assert voice.revision == 7
    assert voice.commit_rate == 50
    voice.commit_rate = 61
    assert setup.store.state(voice.name).baseline("rate") == 61
    setup.store.state(voice.name).checkpoint({"pitch": 42})
    assert voice.commit_pitch == 42
    voice.commit()
    assert (voice.commit_rate, voice.commit_pitch, voice.commit_volume, voice.commit_variant,
            voice.commit_inflection, voice.commit_rateBoost) == (72, 63, 84, "bright", 33, True)
    voice.rate = 88
    voice.rollback()
    assert voice.rate == 72
    assert len(setup.repo.saves) == 1
    assert snapshot.rate == 72


def test_failed_commit_does_not_advance_facade_baseline(setup):
    setup.voice.rate = 72
    setup.repo.fail_next_save = True
    with pytest.raises(OSError):
        setup.voice.commit()
    assert setup.voice.commit_rate == 50
    setup.voice.rollback()
    assert setup.voice.rate == 50


def test_playback_queues_key_and_commands_without_capturing_facade(setup):
    voice = setup.voice
    request = object()
    text = ["hello", object()]
    voice.speak(text, request)
    voice.breaks(0.25, request)
    assert setup.tasks.speeches == [(request, setup.session, "Fake:a", tuple(text))]
    assert setup.tasks.breaks == [(request, 0.25)]
    text.clear()
    assert len(setup.tasks.speeches[0][3]) == 2
    voice.rate = 77
    assert voice.active() is True
    assert setup.adapter.applied[-1][1].rate == 77
    assert voice.active() is False
    voice.stop()
    voice.pause()
    voice.resume()
    assert setup.adapter.cancel_count == 1
    assert setup.adapter.paused == [True, False]
    voice.close()
    assert setup.adapter.close_count == 0
    assert setup.repo.saves == []


def test_unbound_facade_refuses_construction(compat):
    with pytest.raises(RuntimeError, match="binding"):
        compat.facade.VoiceFacade("a", "Fake:a", RecordingTasks())
