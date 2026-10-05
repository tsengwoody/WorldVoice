"""Stand-ins for NVDA modules, registered in sys.modules for one test."""

import builtins
import sys
from types import ModuleType


class StubModules:
	"""Create stub modules through monkeypatch, so each test restores sys.modules."""

	def __init__(self, monkeypatch):
		self._monkeypatch = monkeypatch

	def module(self, name, **attrs):
		result = ModuleType(name)
		result.__dict__.update(attrs)
		self._monkeypatch.setitem(sys.modules, name, result)
		return result

	def package(self, name, path, **attrs):
		result = self.module(name, **attrs)
		result.__path__ = [str(path)]
		return result

	def translation(self):
		"""Install the identity ``_`` that NVDA add-ons get from initTranslation."""
		self._monkeypatch.setattr(builtins, "_", lambda text: text, raising=False)
