"""Bring-up helpers for the driver: fixed-order teardown, step timing, attribute patches."""

import time
from collections.abc import Callable, Sequence
from contextlib import contextmanager


class Teardown:
	"""Cleanups registered as resources come up, run once in one fixed order."""

	def __init__(self, order: Sequence[str], logger):
		self._order = tuple(order)
		self._logger = logger
		self._cleanups: dict[str, Callable[[], object]] = {}

	def add(self, name: str, cleanup: Callable[[], object]) -> None:
		if name not in self._order:
			raise ValueError(f"{name!r} has no place in the teardown order")
		if name in self._cleanups:
			raise ValueError(f"{name!r} is already registered")
		self._cleanups[name] = cleanup

	def run(self) -> None:
		cleanups, self._cleanups = self._cleanups, {}
		for name in self._order:
			cleanup = cleanups.get(name)
			if cleanup is None:
				continue
			try:
				cleanup()
			except Exception:
				self._logger.error("WorldVoice terminate: %s", name, exc_info=True)


@contextmanager
def timed(logger, label: str):
	start = time.perf_counter()
	try:
		yield
	finally:
		if logger is not None:
			logger.debug("WorldVoice init timing: %s %.3fs", label, time.perf_counter() - start)


def patch_attribute(owner, name: str, value) -> Callable[[], None]:
	"""Set owner.name to value; the returned function restores the original once."""
	original = getattr(owner, name)
	setattr(owner, name, value)
	restored = False

	def restore() -> None:
		nonlocal restored
		if restored:
			return
		restored = True
		setattr(owner, name, original)

	return restore
