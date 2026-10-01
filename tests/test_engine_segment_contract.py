"""Segment contract every outer engine wrapper must keep for the scheduler.

The adapters in engine_contract_harness drive each engine's own fakes. Known
gaps are strict xfails: fixing one turns it into XPASS, which fails the run
until the mark is removed.
"""

from threading import Condition, Thread, get_ident

import pytest
from engine_contract_harness import (
	CerenceAdapter,
	EspeakAdapter,
	NeuralAdapter,
	OneCoreAdapter,
	RHVoiceAdapter,
	SAPI5Adapter,
	VEAdapter,
)
from neural_drain_harness import requires_neural

ADAPTERS = {
	"VE": VEAdapter,
	"Cerence": CerenceAdapter,
	"OneCore": OneCoreAdapter,
	"RHVoice": RHVoiceAdapter,
	"SAPI5": SAPI5Adapter,
	"Espeak": EspeakAdapter,
	"Neural": NeuralAdapter,
}


def _engines(**xfails):
	params = []
	for name in ADAPTERS:
		marks = [requires_neural] if name == "Neural" else []
		if name in xfails:
			marks.append(pytest.mark.xfail(strict=True, reason=xfails[name]))
		params.append(pytest.param(name, marks=marks, id=name))
	return params


def _c3(engine):
	return f"C3: {engine} speak_segment blocks until delivery; fixed by SegmentHost in phase 3"


class Events(list):
	def __init__(self):
		super().__init__()
		self.condition = Condition()
		self.threads = []

	def append(self, event):
		with self.condition:
			super().append(event)
			self.threads.append(get_ident())
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
	events = Events()
	caller, errors = _start_speak(engine, engine.new_token(), context, events)

	engine.complete()
	event = events.wait_one()
	caller.join(2)

	assert not caller.is_alive() and errors == []
	assert event.kind is engine.EventKind.SEGMENT_DRAINED
	assert event.source_id is context.source_id
	assert event.segment_id == 17
	assert events.threads == [engine.delivery_thread_ident()]
	assert events.threads[0] != caller.ident


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_segment_after_terminate_fails_once_without_native_call(engine):
	engine.terminate()
	context = engine.PlaybackContext(object(), 19)
	events = Events()
	caller, errors = _start_speak(engine, engine.new_token(), context, events)

	event = events.wait_one()
	caller.join(2)

	assert not caller.is_alive() and errors == []
	assert event.kind is engine.EventKind.SEGMENT_FAILED
	assert event.source_id is context.source_id
	assert event.segment_id == 19
	assert engine.native_call_count() == 0
