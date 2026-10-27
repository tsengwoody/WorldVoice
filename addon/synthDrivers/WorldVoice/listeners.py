"""A list of listeners that a failing listener cannot stop.

NVDA-free (portable core): the caller passes the logger, and the message it logs.
"""

import logging
from collections.abc import Callable
from typing import Generic, ParamSpec

P = ParamSpec("P")


class Listeners(Generic[P]):
	"""Listeners told in subscription order, each once; one that raises is logged and skipped."""

	def __init__(self, logger: logging.Logger, failure_message: str):
		self._logger = logger
		self._failure_message = failure_message
		self._listeners: list[Callable[P, None]] = []

	def subscribe(self, listener: Callable[P, None]) -> None:
		if listener not in self._listeners:
			self._listeners.append(listener)

	def unsubscribe(self, listener: Callable[P, None]) -> None:
		try:
			self._listeners.remove(listener)
		except ValueError:
			pass

	def notify(self, *args: P.args, **kwargs: P.kwargs) -> None:
		# Over a copy, so a listener may unsubscribe while told.
		for listener in tuple(self._listeners):
			try:
				listener(*args, **kwargs)
			except Exception:
				self._logger.error(self._failure_message, exc_info=True)
