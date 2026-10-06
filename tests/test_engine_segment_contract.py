"""Segment contract every outer engine wrapper must keep for the scheduler.

The adapters in engine_contract_harness drive each engine's own fakes. Known
gaps are strict xfails: fixing one turns it into XPASS, which fails the run
until the mark is removed.
"""

from contextlib import suppress
from threading import Condition, Thread, get_ident

import pytest
from engine_contract_harness import (
	CerenceAdapter,
	EspeakAdapter,
	OneCoreAdapter,
	RHVoiceAdapter,
	SAPI5Adapter,
	VEAdapter,
)
from waiting import eventually

ADAPTERS = {
	"VE": VEAdapter,
	"Cerence": CerenceAdapter,
	"OneCore": OneCoreAdapter,
	"RHVoice": RHVoiceAdapter,
	"SAPI5": SAPI5Adapter,
	"Espeak": EspeakAdapter,
}


class C3Blocking(AssertionError):
	"""speak_segment stayed blocked until delivery (refactor.md C3)."""


def _engines(**xfails):
	"""Every engine; ``xfails`` maps an engine to its known gap as (reason, raised type)."""
	params = []
	for name in ADAPTERS:
		marks = []
		if name in xfails:
			reason, raises = xfails[name]
			# Only the known gap may xfail; any other failure still fails the run.
			marks.append(pytest.mark.xfail(strict=True, raises=raises, reason=reason))
		params.append(pytest.param(name, marks=marks, id=name))
	return params


class Events(list):
	def __init__(self, adapter):
		super().__init__()
		self.condition = Condition()
		self.threads = []
		self.on_delivery_thread = []
		self._adapter = adapter

	def append(self, event):
		on_delivery_thread = self._adapter.on_delivery_thread()
		with self.condition:
			super().append(event)
			self.threads.append(get_ident())
			self.on_delivery_thread.append(on_delivery_thread)
			self.condition.notify_all()

	def wait_one(self, timeout=2):
		with self.condition:
			assert self.condition.wait_for(lambda: bool(self), timeout), "no terminal event delivered"
		# A duplicate delivered shortly after the first event must still be caught.
		with self.condition:
			self.condition.wait_for(lambda: len(self) > 1, 0.1)
			assert len(self) == 1, f"expected one terminal event, got {list(self)}"
			return self[0]


@pytest.fixture
def engine(request, monkeypatch, tmp_path):
	adapter = ADAPTERS[request.param]()
	adapter.open(monkeypatch, tmp_path)
	yield adapter
	adapter.close()


def _start_speak(adapter, token, context, events):
	errors = []

	def run():
		try:
			adapter.speak(("hello",), token, context, events.append)
		except Exception as error:  # noqa: BLE001 - the test reports any caller-thread failure
			errors.append(error)

	thread = Thread(target=run, name="contract caller", daemon=True)
	thread.start()
	return thread, errors


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_completed_segment_drains_once_on_the_delivery_thread(engine):
	context = engine.PlaybackContext(object(), 17)
	events = Events(engine)
	caller, errors = _start_speak(engine, engine.new_token(), context, events)

	engine.complete()
	event = events.wait_one()
	caller.join(2)

	assert not caller.is_alive() and errors == []
	assert event.kind is engine.EventKind.SEGMENT_DRAINED
	assert event.source_id is context.source_id
	assert event.segment_id == 17
	assert events.on_delivery_thread == [True]
	assert events.threads[0] != caller.ident


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_segment_after_terminate_fails_once_without_native_call(engine):
	engine.terminate()
	context = engine.PlaybackContext(object(), 19)
	events = Events(engine)
	caller, errors = _start_speak(engine, engine.new_token(), context, events)

	event = events.wait_one()
	caller.join(2)

	assert not caller.is_alive() and errors == []
	assert event.kind is engine.EventKind.SEGMENT_FAILED
	assert event.source_id is context.source_id
	assert event.segment_id == 19
	assert engine.native_call_count() == 0


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_cancelled_token_never_reaches_native_or_sink(engine):
	token = engine.new_token()
	token.cancel()
	events = Events(engine)
	caller, errors = _start_speak(engine, token, engine.PlaybackContext(object(), 21), events)

	caller.join(2)
	with events.condition:
		events.condition.wait_for(lambda: bool(events), 0.2)

	assert not caller.is_alive() and errors == []
	assert engine.native_call_count() == 0
	assert list(events) == []


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_speak_segment_returns_before_delivery(engine):
	context = engine.PlaybackContext(object(), 23)
	events = Events(engine)
	caller, errors = _start_speak(engine, engine.new_token(), context, events)

	caller.join(1)
	returned_early = not caller.is_alive()
	delivered_early = list(events)
	engine.complete()
	event = events.wait_one()
	caller.join(2)

	assert delivered_early == []
	assert errors == []
	assert event.kind is engine.EventKind.SEGMENT_DRAINED
	assert event.segment_id == 23
	# Checked last so every other assertion still applies to the C3 engines.
	if not returned_early:
		raise C3Blocking("speak_segment did not return before the segment completed")


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_ordinary_speak_after_terminate_raises(engine):
	engine.terminate()
	calls = engine.native_call_count()
	with pytest.raises(RuntimeError, match="driver has terminated"):
		engine.speak_ordinary(("hello",))
	assert engine.native_call_count() == calls


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_segment_after_player_stop_failure_fails(engine):
	engine.fail_next_stop()
	with suppress(Exception):
		engine.core.cancel()
	context = engine.PlaybackContext(object(), 25)
	events = Events(engine)
	caller, errors = _start_speak(engine, engine.new_token(), context, events)

	event = events.wait_one()
	caller.join(2)

	assert not caller.is_alive() and errors == []
	assert event.kind is engine.EventKind.SEGMENT_FAILED
	assert event.segment_id == 25
	# Failed because of the latched stop failure, not for another reason.
	assert str(event.error) == "player stop failed"


ORDINARY_THEN_SEGMENT = {
	"VE": "SEGMENT_FAILED",
	"Cerence": "SEGMENT_FAILED",
	"OneCore": "SEGMENT_DRAINED",
	"RHVoice": "SEGMENT_DRAINED",
	"SAPI5": "SEGMENT_DRAINED",
	"Espeak": "SEGMENT_DRAINED",
}


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_segment_after_ordinary_speech_follows_the_engine_mode_rule(engine):
	# VE/Cerence refuse correlated mode once legacy speech ran: its callback
	# lifetimes are unproven. Every other engine runs the segment after it.
	engine.speak_ordinary(("first",))
	engine.complete_ordinary()
	expected = getattr(engine.EventKind, ORDINARY_THEN_SEGMENT[engine.engine])
	ordinary_calls = engine.native_call_count()
	context = engine.PlaybackContext(object(), 27)
	events = Events(engine)
	caller, errors = _start_speak(engine, engine.new_token(), context, events)
	if expected is engine.EventKind.SEGMENT_DRAINED:
		eventually(
			lambda: engine.native_call_count() > ordinary_calls,
			message="the segment never reached native synthesis",
		)
		engine.complete()
	event = events.wait_one()
	caller.join(2)
	assert not caller.is_alive() and errors == []
	assert event.kind is expected
	assert event.segment_id == 27
	if event.kind is engine.EventKind.SEGMENT_FAILED:
		assert "Legacy" in str(event.error)
