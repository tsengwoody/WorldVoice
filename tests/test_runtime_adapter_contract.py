"""The same production runtime works with or without the legacy boundary."""

from concurrent.futures import CancelledError
from contextlib import nullcontext

import pytest

from runtime_harness import assemble_adapter_contract, forbid_legacy_runtime_imports


@pytest.fixture(params=["native", "legacy"])
def contract(monkeypatch, request):
    guard = (forbid_legacy_runtime_imports(monkeypatch)
             if request.param == "native" else nullcontext())
    with guard:
        runtime = assemble_adapter_contract(monkeypatch, request.param)
        try:
            yield runtime
        finally:
            runtime.tasks.shutdown()
            runtime.session.close()


def submit(c, *keys):
    request = c.tasks.new_request()
    futures = [c.tasks.append_speech(request, c.session, key, (key,)) for key in keys]
    assert c.tasks.submit_request(request)
    return request, futures


def test_cached_a_b_a_restores_voice_language_and_parameters(contract):
    c = contract
    c.store.state("Contract:a").update(rate=72, pitch=61, volume=83)
    c.store.state("Contract:b").update(rate=33, pitch=44, volume=55)
    # Equal revisions catch a cache incorrectly keyed by revision alone.
    _, futures = submit(c, "Contract:a", "Contract:b", "Contract:a")
    assert [future.result(1) for future in futures] == [True, True, True]
    assert c.output.wait_done() == 1
    assert c.core.spoken == [
        (("Contract:a",), "a", "en", 72, 61, 83),
        (("Contract:b",), "b", "zh_TW", 33, 44, 55),
        (("Contract:a",), "a", "en", 72, 61, 83),
    ]
    assert c.repo.loads == ["Contract:a", "Contract:b"]
    assert c.repo.saves == []


def test_apply_rebases_discard_and_next_segment_uses_restored_settings(contract):
    c = contract
    edit = c.store.begin_edit()
    try:
        state = c.store.state("Contract:a")
        state.update(rate=72)
        assert c.repo.saves == []
        edit.apply()
        assert c.repo.values["Contract:a"]["rate"] == 72
        saved = list(c.repo.saves)
        state.update(rate=81)
        _, futures = submit(c, "Contract:a")
        assert futures[0].result(1) is True
        assert c.output.wait_done() == 1
        edit.discard()
        assert state.get("rate") == 72
        _, futures = submit(c, "Contract:a")
        assert futures[0].result(1) is True
        assert c.output.wait_done(count=2) == 2
        assert [entry[3] for entry in c.core.spoken] == [81, 72]
        assert c.repo.saves == saved
    finally:
        edit.close()


def test_synchronous_done_completes_once_and_filters_indexes(contract):
    c = contract
    request, futures = submit(c, "Contract:a")
    assert futures[0].result(1) is True
    assert c.output.wait_done() == 1
    assert c.output.indexes == [7]
    assert request.state is c.scheduler.RequestState.COMPLETED
    assert request.remaining == 0
    assert c.tasks.submit_request(request) is False


def test_cancel_suppresses_completion_and_allows_following_request(contract):
    c = contract
    c.core.complete_synchronously = False
    request, futures = submit(c, "Contract:a")
    assert c.core.entered.wait(1)
    c.tasks.cancel([c.session])
    with pytest.raises(CancelledError):
        futures[0].result(1)
    assert request.state is c.scheduler.RequestState.CANCELLED
    assert c.output.done_count == 0
    assert c.core.cancel_count >= 1
    assert c.core.tokens[0].is_cancelled()
    c.core.complete_synchronously = True
    following, futures = submit(c, "Contract:b")
    assert futures[0].result(1) is True
    assert c.output.wait_done() == 1
    assert following.state is c.scheduler.RequestState.COMPLETED
    assert [entry[1] for entry in c.core.spoken] == ["a", "b"]
    assert not c.core.tokens[1].is_cancelled()


def test_repeated_shutdown_closes_engine_once(contract):
    c = contract
    _, futures = submit(c, "Contract:a")
    assert futures[0].result(1) is True
    assert c.output.wait_done() == 1
    c.tasks.shutdown()
    c.tasks.shutdown()
    c.session.close()
    c.session.close()
    assert (c.core.open_count, c.core.close_count) == (1, 1)
    assert c.repo.saves == []
