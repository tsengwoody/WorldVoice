from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event

import pytest

from runtime_harness import MemoryRepository, make_spec


@pytest.fixture
def repo():
    return MemoryRepository()


@pytest.fixture
def store(rt, repo):
    return rt.settings.VoiceSettingsStore(repo)


def test_ensure_returns_same_state(store, repo):
    state = store.ensure(make_spec())
    state.update(rate=72)
    assert store.ensure(make_spec()) is state
    assert store.state("Fake:a") is state
    assert store.snapshot("Fake:a").rate == 72
    assert store.names() == ("Fake:a",)
    # Not a mapping: a dict-like keys() would invite `for key in store`, which raises.
    assert not hasattr(store, "keys")
    assert repo.loads == ["Fake:a"]


def test_conflicting_metadata_is_rejected(store, repo):
    spec = make_spec()
    store.ensure(spec)
    with pytest.raises(ValueError):
        store.ensure(replace(spec, language="zh_TW"))
    assert repo.loads == ["Fake:a"]
    assert store.snapshot("Fake:a").language == "en"


def test_unknown_key_does_not_implicitly_load_voice(store, repo):
    with pytest.raises(KeyError):
        store.state("Fake:a")
    assert repo.loads == []


def test_late_voice_and_failed_save_keep_cancel_baseline(store, repo):
    edit = store.begin_edit()
    state = store.ensure(make_spec("Fake:b"))
    state.update(rate=72)
    repo.fail_next_save = True
    with pytest.raises(OSError):
        edit.apply()
    assert state.get("rate") == 72
    assert state.baseline("rate") == 50
    edit.discard()
    assert state.get("rate") == 50
    assert repo.values == {}


def test_successful_apply_rebases_discard(store, repo):
    state = store.ensure(make_spec())
    edit = store.begin_edit()
    state.update(rate=72)
    edit.apply()
    state.update(rate=81)
    edit.discard()
    assert state.get("rate") == 72
    assert repo.values["Fake:a"]["rate"] == 72
    assert len(repo.saves) == 1


def test_begin_edit_uses_existing_pending_values_as_cancel_baseline(store, repo):
    state = store.ensure(make_spec())
    state.update(rate=61)
    edit = store.begin_edit()
    state.update(rate=81)
    edit.discard()
    assert state.get("rate") == 61
    assert repo.saves == []


def test_edit_during_save_preserves_new_pending_value(store, repo):
    state = store.ensure(make_spec())
    edit = store.begin_edit()
    state.update(rate=72)
    saving = Event()
    finish_save = Event()

    def before_save(spec, values):
        saving.set()
        assert finish_save.wait(2)

    def edit_while_saving():
        state.update(rate=81)
        # Persistence must not hold either the state or store lock.
        assert store.snapshot("Fake:a").rate == 81
        store.ensure(make_spec("Fake:b"))

    repo.before_save = before_save
    with ThreadPoolExecutor(max_workers=2) as executor:
        apply = executor.submit(edit.apply)
        try:
            assert saving.wait(2)
            executor.submit(edit_while_saving).result(timeout=2)
        finally:
            finish_save.set()
        apply.result(timeout=2)
    assert state.get("rate") == 81
    assert state.baseline("rate") == 72
    assert repo.values["Fake:a"]["rate"] == 72
    late_state = store.state("Fake:b")
    late_state.update(rate=92)
    edit.discard()
    assert state.get("rate") == 72
    assert late_state.get("rate") == 50


def test_partial_apply_advances_only_successful_baselines_and_can_retry(store, repo):
    first = store.ensure(make_spec())
    second = store.ensure(make_spec("Fake:b"))
    edit = store.begin_edit()
    first.update(rate=72)
    second.update(rate=81)

    def fail_second(spec, values):
        if spec.name == "Fake:b":
            raise OSError("Second save failed")

    repo.before_save = fail_second
    with pytest.raises(OSError):
        edit.apply()
    assert (first.baseline("rate"), second.baseline("rate")) == (72, 50)
    assert (first.get("rate"), second.get("rate")) == (72, 81)
    assert [key for key, _ in repo.saves] == ["Fake:a", "Fake:b"]
    repo.before_save = None
    edit.apply()
    second.update(rate=90)
    edit.discard()
    assert second.get("rate") == 81


def test_close_only_releases_ownership_and_is_idempotent(store, repo):
    state = store.ensure(make_spec())
    edit = store.begin_edit()
    with pytest.raises(RuntimeError):
        store.begin_edit()
    state.update(rate=72)
    edit.close()
    assert state.get("rate") == 72
    assert repo.saves == []
    next_edit = store.begin_edit()
    edit.close()
    with pytest.raises(RuntimeError):
        store.begin_edit()
    with pytest.raises(RuntimeError):
        edit.apply()
    with pytest.raises(RuntimeError):
        edit.discard()
    next_edit.close()
    store.begin_edit().close()


def test_commit_and_rollback_preserve_saved_values_without_an_edit(store, repo):
    state = store.ensure(make_spec())
    state.update(rate=72, waitfactor=3)
    store.commit("Fake:a")
    state.update(rate=81, waitfactor=8)
    store.rollback("Fake:a")
    assert (state.get("rate"), state.get("waitfactor")) == (72, 3)
    assert len(repo.saves) == 1


def test_reload_updates_shared_state_and_baseline(store, repo):
    state = store.ensure(make_spec())
    state.update(rate=72)
    repo.values["Fake:a"] = {"rate": 63, "variant": "new"}
    store.reload("Fake:a")
    assert store.state("Fake:a") is state
    assert (state.get("rate"), state.get("variant")) == (63, "new")
    state.update(rate=81)
    store.rollback("Fake:a")
    assert state.get("rate") == 63
    assert repo.loads == ["Fake:a", "Fake:a"]


def test_concurrent_ensure_loads_only_once(store, repo):
    with ThreadPoolExecutor(max_workers=4) as executor:
        states = list(executor.map(lambda _: store.ensure(make_spec()), range(12)))
    assert all(state is states[0] for state in states)
    assert repo.loads == ["Fake:a"]


def test_inherited_values_seed_a_new_state_and_its_cancel_baseline(store, repo):
    repo.values["Fake:b"] = {"rate": 41, "variant": "own"}
    store.set_inheritance(lambda spec: {"rate": 83} if spec.name == "Fake:b" else {})
    edit = store.begin_edit()
    state = store.ensure(make_spec("Fake:b"))
    assert (state.get("rate"), state.get("variant")) == (83, "own")
    assert state.baseline("rate") == 83
    state.update(rate=72)
    edit.discard()
    assert state.get("rate") == 83
    # Inherited values are not saved until a commit.
    assert repo.values["Fake:b"] == {"rate": 41, "variant": "own"}


def test_reload_layers_inherited_values_over_the_saved_ones(store, repo):
    inherited = {}
    store.set_inheritance(lambda spec: dict(inherited))
    state = store.ensure(make_spec())
    repo.values["Fake:a"] = {"rate": 63, "variant": "new"}
    inherited["rate"] = 90
    store.reload("Fake:a")
    assert (state.get("rate"), state.get("variant")) == (90, "new")
    assert state.baseline("rate") == 90


def test_no_thread_sees_a_state_before_it_inherits(store, repo):
    entered, release = Event(), Event()

    def inherit(spec):
        entered.set()
        assert release.wait(1)
        return {"rate": 83}

    store.set_inheritance(inherit)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(store.ensure, make_spec())
        assert entered.wait(1)
        second = executor.submit(store.ensure, make_spec())
        assert not second.done()
        release.set()
        assert first.result(1) is second.result(1)
    assert second.result().get("rate") == 83
    assert repo.loads == ["Fake:a"]
