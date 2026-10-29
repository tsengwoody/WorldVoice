"""Segment contract every outer engine wrapper must keep for the scheduler.

The adapters in engine_contract_harness drive each engine's own fakes. Known
gaps are strict xfails: fixing one turns it into XPASS, which fails the run
until the mark is removed.
"""

import sys
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
from waiting import WAIT_TIMEOUT, eventually, stays_false

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

	def wait_one(self, timeout=WAIT_TIMEOUT):
		eventually(lambda: bool(self), timeout, message="no terminal event delivered")
		# A duplicate delivered shortly after the first event must still be caught.
		stays_false(
			self.condition,
			lambda: len(self) > 1,
			message=lambda: f"expected one terminal event, got {list(self)}",
		)
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
	caller.join(WAIT_TIMEOUT)

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
	caller.join(WAIT_TIMEOUT)

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

	caller.join(WAIT_TIMEOUT)
	stays_false(events.condition, lambda: bool(events), message=lambda: f"unexpected events {list(events)}")
	assert not caller.is_alive() and errors == []
	assert engine.native_call_count() == 0


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_speak_segment_returns_before_delivery(engine):
	context = engine.PlaybackContext(object(), 23)
	events = Events(engine)
	caller, errors = _start_speak(engine, engine.new_token(), context, events)

	caller.join(WAIT_TIMEOUT)
	returned_early = not caller.is_alive()
	delivered_early = list(events)
	engine.complete()
	event = events.wait_one()
	caller.join(WAIT_TIMEOUT)

	assert delivered_early == []
	assert errors == []
	assert event.kind is engine.EventKind.SEGMENT_DRAINED
	assert event.segment_id == 23
	# Checked last so every other assertion still applies to the C3 engines.
	if not returned_early:
		raise C3Blocking("speak_segment did not return before the segment completed")


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_every_core_speaks_segments_through_the_shared_mixin(engine):
	# Nothing in a loaded wrapper's MRO shadows the shared entry (a parent driver gaining one would).
	core = type(engine.core)
	assert core.speak_segment is sys.modules[core.__module__].SegmentHostSpeaker.speak_segment


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_ordinary_speak_after_terminate_raises(engine):
	engine.terminate()
	calls = engine.native_call_count()
	with pytest.raises(RuntimeError, match="driver has terminated"):
		engine.speak_ordinary(("hello",))
	assert engine.native_call_count() == calls


# pause() after terminate differs by engine (cons.md B15). Unifying it would change a shutdown race,
# so phase 45' keeps it; the table makes a later change deliberate. eSpeak's comes from NVDA's
# _espeak.pause on the player that terminate set to None.
POST_TERMINATE_PAUSE = {
	"VE": RuntimeError,
	"Cerence": RuntimeError,
	"Espeak": AttributeError,
	"OneCore": None,
	"RHVoice": None,
	"SAPI5": None,
}


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_pause_after_terminate_keeps_each_engine_behaviour(engine):
	engine.terminate()
	expected = POST_TERMINATE_PAUSE[engine.engine]
	if expected is None:
		assert engine.core.pause(True) is None
	elif expected is RuntimeError:
		with pytest.raises(RuntimeError, match=f"^{engine.engine} driver has terminated$"):
			engine.core.pause(True)
	else:
		with pytest.raises(expected):
			engine.core.pause(True)


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_segment_after_player_stop_failure_fails(engine):
	engine.fail_next_stop()
	with suppress(Exception):
		engine.core.cancel()
	context = engine.PlaybackContext(object(), 25)
	events = Events(engine)
	caller, errors = _start_speak(engine, engine.new_token(), context, events)

	event = events.wait_one()
	caller.join(WAIT_TIMEOUT)

	assert not caller.is_alive() and errors == []
	assert event.kind is engine.EventKind.SEGMENT_FAILED
	assert event.segment_id == 25
	# Failed because of the latched stop failure, not for another reason.
	assert str(event.error) == "player stop failed"


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_segment_after_ordinary_speech_drains(engine):
	# A direct caller may speak ordinary speech and then a segment on one core; every engine runs
	# the segment after it. Production never mixes the two on one core: the engine adapter's
	# completion contract is fixed before it speaks (bridge/engineAdapter.py configureCompletion).
	engine.speak_ordinary(("first",))
	engine.complete_ordinary()
	ordinary_calls = engine.native_call_count()
	context = engine.PlaybackContext(object(), 27)
	events = Events(engine)
	caller, errors = _start_speak(engine, engine.new_token(), context, events)
	eventually(
		lambda: engine.native_call_count() > ordinary_calls,
		message="the segment never reached native synthesis",
	)
	engine.complete()
	event = events.wait_one()
	caller.join(WAIT_TIMEOUT)
	assert not caller.is_alive() and errors == []
	assert event.kind is engine.EventKind.SEGMENT_DRAINED
	assert event.segment_id == 27
