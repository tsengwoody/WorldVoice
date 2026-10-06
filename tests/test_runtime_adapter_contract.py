"""The same production runtime works with or without the legacy boundary."""

from concurrent.futures import CancelledError
from contextlib import nullcontext

import pytest
from runtime_harness import (
	assemble_adapter_contract,
	forbid_legacy_runtime_imports,
	submit_contract_request,
	tracked_requests,
)
from waiting import WAIT_TIMEOUT


@pytest.fixture(params=["native", "legacy"])
def contract(monkeypatch, request):
	"""Retain the LEGACY_DONE contract separately from marker completion."""
	guard = forbid_legacy_runtime_imports(monkeypatch) if request.param == "native" else nullcontext()
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
	assert [future.result(WAIT_TIMEOUT) for future in futures] == [True, True, True]
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
		assert futures[0].result(WAIT_TIMEOUT) is True
		assert c.output.wait_done() == 1
		edit.discard()
		assert state.get("rate") == 72
		_, futures = submit(c, "Contract:a")
		assert futures[0].result(WAIT_TIMEOUT) is True
		assert c.output.wait_done(count=2) == 2
		assert [entry[3] for entry in c.core.spoken] == [81, 72]
		assert c.repo.saves == saved
	finally:
		edit.close()


def test_synchronous_done_completes_once_and_filters_indexes(contract):
	c = contract
	request, futures = submit(c, "Contract:a")
	assert futures[0].result(WAIT_TIMEOUT) is True
	assert c.output.wait_done() == 1
	assert c.output.indexes == [7]
	assert request.state is c.scheduler.RequestState.COMPLETED
	assert request.remaining == 0
	assert c.tasks.submit_request(request) is False


def test_cancel_suppresses_completion_and_allows_following_request(contract):
	c = contract
	c.core.complete_synchronously = False
	request, futures = submit(c, "Contract:a")
	assert c.core.entered.wait(WAIT_TIMEOUT)
	c.tasks.cancel([c.session])
	with pytest.raises(CancelledError):
		futures[0].result(WAIT_TIMEOUT)
	assert request.state is c.scheduler.RequestState.CANCELLED
	assert c.output.done_count == 0
	assert c.core.cancel_count >= 1
	assert c.core.tokens[0].is_cancelled()
	c.core.complete_synchronously = True
	following, futures = submit(c, "Contract:b")
	assert futures[0].result(WAIT_TIMEOUT) is True
	assert c.output.wait_done() == 1
	assert following.state is c.scheduler.RequestState.COMPLETED
	assert [entry[1] for entry in c.core.spoken] == ["a", "b"]
	assert not c.core.tokens[1].is_cancelled()


def test_repeated_shutdown_closes_engine_once(contract):
	c = contract
	_, futures = submit(c, "Contract:a")
	assert futures[0].result(WAIT_TIMEOUT) is True
	assert c.output.wait_done() == 1
	c.tasks.shutdown()
	c.tasks.shutdown()
	c.session.close()
	c.session.close()
	assert (c.core.open_count, c.core.close_count) == (1, 1)
	assert c.repo.saves == []


@pytest.fixture(params=["native", "legacy"])
def marker_contract(monkeypatch, request):
	# NVDA command stubs belong solely to the legacy boundary.
	commands = request.getfixturevalue("nvda_commands") if request.param == "legacy" else None
	guard = forbid_legacy_runtime_imports(monkeypatch) if request.param == "native" else nullcontext()
	with guard:
		c = assemble_adapter_contract(
			monkeypatch,
			request.param,
			completion_mode="END_INDEX",
			commands=commands,
		)
		try:
			yield c
		finally:
			c.tasks.shutdown()
			if c.bridge is not None:
				c.bridge.close()
			c.session.close()
			c.ledger.close()


def completed(c, request):
	assert [task.future.result(WAIT_TIMEOUT) for task in request.tasks] == [
		None if task.playback is None else True for task in request.tasks
	]
	c.tasks._q.join()
	assert request.state is c.scheduler.RequestState.COMPLETED
	assert request.remaining == 0


def test_same_voice_two_segments_preserve_activation_cache(marker_contract):
	c = marker_contract
	request = submit_contract_request(
		c,
		["A", c.rt.models.SelectVoice("Contract:a"), "B"],
		default_key="Contract:a",
	)
	completed(c, request)
	assert c.core.apply_count == 1
	assert len(set(c.core.segment_ids)) == 2
	assert len(c.core.internal_wire_indexes) == 2
	assert c.output.done_count == 1


def test_original_indexes_round_trip_without_internal_marker_leak(marker_contract):
	c = marker_contract
	originals = [c.index_command(123), c.index_command(124)]
	request = submit_contract_request(c, ["A", *originals], default_key="Contract:a")
	completed(c, request)
	assert c.output.indexes == [123, 124]
	assert not any(i in c.core.internal_wire_indexes for i in c.output.indexes)
	assert not set(c.core.wire_indexes).intersection(c.output.indexes)
	assert [command.index for command in originals] == [123, 124]
	assert c.output.done_count == 1


def test_complete_select_pause_sequence_has_exactly_three_markers(marker_contract):
	c = marker_contract
	select, pause = c.rt.models.SelectVoice, c.rt.models.Pause
	request = submit_contract_request(
		c,
		["A", select("Contract:b"), "B", pause(0.2), "C"],
		default_key="Contract:a",
	)
	completed(c, request)
	assert [task.seconds for task in request.tasks] == [None, None, 0.2, None]
	assert [entry[0][0] for entry in c.core.spoken] == ["A", "B", "C"]
	assert [entry[1] for entry in c.core.spoken] == ["a", "b", "b"]
	assert len(c.core.internal_wire_indexes) == 3
	assert len(set(c.core.segment_ids)) == 3
	assert c.core.apply_count == 2
	assert c.output.done_count == 1


def test_repeated_selection_and_unavailable_segments_add_no_markers(marker_contract):
	c = marker_contract
	select, pause = c.rt.models.SelectVoice, c.rt.models.Pause
	request = submit_contract_request(
		c,
		[
			select("Contract:a"),
			select("Contract:a"),
			"A",
			select("missing:x"),
			"ignored",
			c.index_command(999),
			pause(20),
			select("Contract:b"),
			select("Contract:b"),
			"B",
		],
		default_key="Contract:a",
	)
	completed(c, request)
	assert len(request.tasks) == len(c.core.internal_wire_indexes) == 2
	assert c.output.indexes == []
	assert c.output.done_count == 1


def test_marker_a_b_a_restores_voice_and_settings(marker_contract):
	c = marker_contract
	c.store.state("Contract:a").update(rate=72, pitch=61, volume=83)
	c.store.state("Contract:b").update(rate=33, pitch=44, volume=55)
	select = c.rt.models.SelectVoice
	request = submit_contract_request(
		c,
		["A", select("Contract:b"), "B", select("Contract:a"), "A"],
		default_key="Contract:a",
	)
	completed(c, request)
	assert [entry[1:] for entry in c.core.spoken] == [
		("a", "en", 72, 61, 83),
		("b", "zh_TW", 33, 44, 55),
		("a", "en", 72, 61, 83),
	]
	assert c.core.apply_count == 3
	assert c.output.done_count == 1
	assert c.repo.saves == []


def test_cancel_a_b_a_rejects_same_source_late_callbacks(marker_contract):
	c = marker_contract
	c.core.complete_synchronously = False
	old = submit_contract_request(c, ["old", c.index_command(123)], default_key="Contract:a")
	assert c.core.entered.wait(WAIT_TIMEOUT)
	old_marker = c.core.internal_wire_indexes[-1]
	old_wires = c.core.wire_indexes[:]
	c.tasks.cancel([c.session])
	with pytest.raises(CancelledError):
		old.tasks[0].future.result(WAIT_TIMEOUT)
	assert old.token.is_cancelled()
	assert c.output.done_count == 0
	for key in ("Contract:b", "Contract:a"):
		c.core.entered.clear()
		current = submit_contract_request(c, ["new"], default_key=key)
		assert c.core.entered.wait(WAIT_TIMEOUT)
		for wire in [*old_wires, old_marker]:
			c.core.emit("INDEX", wire)
		c.core.emit("DONE")
		assert not current.tasks[0].future.done()
		assert c.output.indexes == []
		c.core.emit("INDEX", c.core.internal_wire_indexes[-1])
		completed(c, current)
	assert [entry[1] for entry in c.core.spoken] == ["a", "b", "a"]
	assert len(set(c.core.segment_ids)) == 3
	assert c.output.done_count == 2


def test_commands_without_text_still_get_one_marker(marker_contract):
	c = marker_contract
	command = object()
	completed(c, submit_contract_request(c, [command, c.index_command(123)], default_key="Contract:a"))
	assert c.core.spoken[0][0][0] is command
	assert c.output.indexes == [123]
	assert len(c.core.internal_wire_indexes) == 1
	assert c.output.done_count == 1


@pytest.mark.parametrize("failure", ["generator", "exhaustion", "invalid_index"])
def test_errors_before_core_entry_never_speak(marker_contract, failure):
	c = marker_contract
	if failure == "generator":

		def sequence():
			yield "A"
			yield c.rt.models.Pause(0)
			raise ValueError("source failed")

		with pytest.raises(ValueError, match="source failed"):
			submit_contract_request(c, sequence(), default_key="Contract:a")
		assert c.output.done_count == 0
	else:
		commands = (
			[c.index_command(i) for i in range(16)] if failure == "exhaustion" else [c.index_command(123)]
		)
		if failure == "invalid_index":
			commands[0].index = "invalid"
		request = submit_contract_request(c, commands, default_key="Contract:a")
		assert request.tasks[0].future.exception(WAIT_TIMEOUT) is not None
		c.tasks._q.join()
		assert request.state is c.scheduler.RequestState.FAILED
		assert c.output.done_count == 1
	assert c.core.spoken == []
	assert tracked_requests(c.tasks) == {}


def test_synchronous_terminal_marker_output_cancel_wins(marker_contract):
	c = marker_contract
	# Hardware reports only END; the production ledger flushes original indexes.
	c.core.end_only = True
	original = c.output.index_reached

	def cancel_on_index(index):
		original(index)
		c.tasks.cancel([c.session])

	c.output.index_reached = cancel_on_index
	request = submit_contract_request(
		c,
		[
			c.index_command(123),
			c.index_command(124),
			c.rt.models.SelectVoice("Contract:b"),
			"never",
		],
		default_key="Contract:a",
	)
	c.tasks._q.join()
	assert all(task.future.cancelled() for task in request.tasks)
	assert request.state is c.scheduler.RequestState.CANCELLED
	assert c.output.indexes == [123]
	assert c.output.done_count == 0
	assert len(c.core.spoken) == 1
	assert c.core.tokens[0].is_cancelled()


def test_cancelled_token_prevents_core_entry(marker_contract):
	c = marker_contract
	token = c.scheduler.CancellationToken()
	token.cancel()
	assert c.session.activate("Contract:a")
	c.session.speak(
		("cancelled",),
		token,
		context=c.rt.models.PlaybackContext(c.session.source_id, 9000),
	)
	assert c.core.spoken == []
	assert c.output.done_count == 0


def test_reentrant_end_preserves_all_indexes_in_accepted_batch(marker_contract):
	c = marker_contract
	c.core.complete_synchronously = False
	request = submit_contract_request(
		c,
		[c.index_command(123), c.index_command(124)],
		default_key="Contract:a",
	)
	assert c.core.entered.wait(WAIT_TIMEOUT)
	original = c.output.index_reached
	pending_at_output = []

	def reenter_on_first(index):
		original(index)
		pending_at_output.append((index, request.tasks[0].future.done(), c.output.done_count))
		if index == 123:
			c.core.emit("INDEX", c.core.internal_wire_indexes[-1])

	c.output.index_reached = reenter_on_first
	# Reporting the second wire flushes both original indexes in one batch.
	c.core.emit("INDEX", c.core.wire_indexes[1])
	completed(c, request)
	assert c.output.indexes == [123, 124]
	assert pending_at_output == [(123, False, 0), (124, False, 0)]
	assert c.output.done_count == 1


def test_marker_core_treats_text_as_text_not_an_index_command(marker_contract):
	c = marker_contract
	emitted = []
	original = c.core.emit

	def emit(kind, index=None):
		emitted.append((kind, index))
		original(kind, index)

	c.core.emit = emit
	request = submit_contract_request(
		c,
		["text with an index method", c.index_command(123)],
		default_key="Contract:a",
	)
	completed(c, request)
	assert c.core.wire_indexes == [501, 502]
	assert emitted == [("INDEX", 501), ("INDEX", 501), ("INDEX", 502), ("INDEX", 502), ("DONE", None)]
	assert c.output.indexes == [123]
