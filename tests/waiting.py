"""Waiting in concurrency tests: poll for a condition, never sleep a fixed time and hope."""

from threading import Event
from time import monotonic

# Positive waits return as soon as their condition holds, so a generous limit costs nothing
# and keeps a slow machine (coverage, parallel runs) from failing them.
WAIT_TIMEOUT = 3.0
# Negative checks watch this long for something that must not happen; they can only miss.
QUIET_PERIOD = 0.05

_POLL = 0.002


def eventually(predicate, timeout=WAIT_TIMEOUT, message=None):
	"""Poll until ``predicate()`` is truthy and return its value; fail after ``timeout``."""
	deadline = monotonic() + timeout
	pause = Event()
	while True:
		value = predicate()
		if value:
			return value
		if monotonic() >= deadline:
			break
		pause.wait(_POLL)
	raise AssertionError(message or f"condition still false after {timeout} s (last value: {value!r})")


def stays_unset(event, period=QUIET_PERIOD, message=None):
	"""Negative check: ``event`` is not set within ``period``. It can miss, never fail spuriously."""
	assert not event.wait(period), message or f"event was set within {period} s"


def quiet_period(period=QUIET_PERIOD):
	"""Give work that must not happen time to happen, before counting what did."""
	Event().wait(period)
