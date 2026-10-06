"""Waiting in concurrency tests: poll for a condition, never sleep a fixed time and hope."""

from threading import Event
from time import monotonic

# Positive waits return as soon as their condition holds, so a generous limit costs nothing
# and keeps a slow machine (coverage, parallel runs) from failing them.
WAIT_TIMEOUT = 3.0
# A fake that holds a worker until the test releases it waits longer than any positive wait,
# so a test asserting that work finishes while the hold is in place cannot pass because the
# hold expired first.
HOLD_TIMEOUT = 2 * WAIT_TIMEOUT
# Negative checks watch this long for something that must not happen; they can only miss.
QUIET_PERIOD = 0.05

_POLL = 0.002


def _text(message):
	# A callable message is built on failure, so it can show the state then.
	return message() if callable(message) else message


def eventually(predicate, timeout=WAIT_TIMEOUT, message=None):
	"""Poll until ``predicate()`` is truthy and return its value; fail after ``timeout``.

	An exception from ``predicate`` propagates at once.
	"""
	deadline = monotonic() + timeout
	pause = Event()
	while True:
		value = predicate()
		if value:
			return value
		if monotonic() >= deadline:
			break
		pause.wait(_POLL)
	raise AssertionError(_text(message) or f"condition still false after {timeout} s (last value: {value!r})")


def stays_unset(event, period=QUIET_PERIOD, message=None):
	"""Negative check: ``event`` is not set within ``period``. It can miss, never fail spuriously."""
	assert not event.wait(period), _text(message) or f"event was set within {period} s"


def holds_within(condition, predicate, period=QUIET_PERIOD):
	"""Whether ``predicate()`` became true within ``period``, waiting on ``condition``.

	For negative checks that must release blocked threads before they assert.
	"""
	with condition:
		return condition.wait_for(predicate, period)


def stays_false(condition, predicate, period=QUIET_PERIOD, message=None):
	"""Negative check on a condition variable: ``predicate()`` stays false for ``period``."""
	became_true = holds_within(condition, predicate, period)
	assert not became_true, _text(message) or f"condition became true within {period} s"


def quiet_period(period=QUIET_PERIOD):
	"""Give work that must not happen time to happen, before counting what did."""
	Event().wait(period)
