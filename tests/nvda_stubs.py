"""Stand-ins for NVDA modules, registered in sys.modules for one test."""

import ast
import builtins
import copy
import functools
import re
import sys
from types import ModuleType

from addon_loader import WORLDVOICE


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


def worldvoice_conf(**sections):
	"""A WorldVoice config stub holding the defaults the add-on's confspec declares.

	NVDA's config returns a spec default for every key nobody stored, so a stub with every
	default behaves like a fresh profile. Each keyword names a section and its values replace
	those defaults. The defaults are read from the add-on sources, so a new key reaches every
	test that uses this stub.
	"""
	conf = copy.deepcopy(_worldvoice_defaults())
	for name, values in sections.items():
		if name not in conf:
			raise KeyError(f"The WorldVoice confspec has no {name!r} section")
		conf[name].update(values)
	return {"WorldVoice": conf}


@functools.cache
def _worldvoice_defaults():
	# config.conf.spec["WorldVoice"] = {...} in the synth package's __init__.py.
	for node in ast.parse((WORLDVOICE / "__init__.py").read_text(encoding="utf-8")).body:
		if (
			isinstance(node, ast.Assign)
			and isinstance(node.targets[0], ast.Subscript)
			and ast.unparse(node.targets[0]) == "config.conf.spec['WorldVoice']"
		):
			return _section_defaults(node.value)
	raise LookupError("The WorldVoice confspec is not assigned in __init__.py")


def _section_defaults(node):
	defaults = {}
	for key, value in zip(node.keys, node.values, strict=True):
		if key is None:
			defaults.update(_spread_defaults(value))
		elif key.value != "__many__":
			# __many__ only describes sections a profile may add; a fresh profile has none.
			defaults[key.value] = (
				_section_defaults(value) if isinstance(value, ast.Dict) else _value_default(value)
			)
	return defaults


def _value_default(node):
	if isinstance(node, ast.Constant):
		return _confspec_default(node.value)
	if isinstance(node, ast.Call) and ast.unparse(node.func) == "dict" and len(node.args) == 1:
		return _spread_defaults(node.args[0])
	raise ValueError(f"Unexpected confspec value: {ast.unparse(node)}")


def _spread_defaults(node):
	source = ast.unparse(node)
	if source == "DETECTION_CONFSPEC":
		spec = ast.literal_eval(_top_level_value(WORLDVOICE / "languageDetection/settings.py", source))
		return {key: _confspec_default(validator) for key, validator in spec.items()}
	if source == "PIPELINE_CONFSPEC":
		# Built from the PipelineSettingSpec(key, kind, default, ...) table, without the
		# ordering-only entries (pipeline_config=False) that NVDA stores as driver settings.
		table = _top_level_value(WORLDVOICE / "pipeline/settings.py", "PIPELINE_SETTINGS")
		return {
			ast.literal_eval(spec.args[0]): ast.literal_eval(spec.args[2])
			for spec in table.elts
			if not any(
				keyword.arg == "pipeline_config" and ast.literal_eval(keyword.value) is False
				for keyword in spec.keywords
			)
		}
	if (
		isinstance(node, ast.DictComp)
		and ast.unparse(node.key) == "key"
		and ast.unparse(node.generators[0].iter) == "LOG_SWITCHES"
	):
		# One log switch per Stage(log_key, fn) in pipeline STAGES, except log_switch=False ones.
		stages = _top_level_value(WORLDVOICE / "pipeline/__init__.py", "STAGES")
		value = _value_default(node.value)
		return {
			ast.literal_eval(stage.args[0]): value
			for stage in stages.elts
			if not any(
				keyword.arg == "log_switch" and ast.literal_eval(keyword.value) is False
				for keyword in stage.keywords
			)
		}
	raise ValueError(f"Unexpected confspec entries: {source}")


def _top_level_value(path, name):
	for node in ast.parse(path.read_text(encoding="utf-8")).body:
		targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
		if any(getattr(target, "id", None) == name for target in targets):
			return node.value
	raise LookupError(f"{path.name} assigns no {name}")


def _confspec_default(validator):
	"""The value a configobj check such as integer(default=50,min=0,max=100) gives when unset."""
	kind, arguments = re.fullmatch(r"(\w+)\((.*)\)", validator).groups()
	value = re.search(r'default=("[^"]*"|[^,]*)', arguments).group(1).strip('"')
	if kind == "boolean":
		return value.lower() in {"true", "yes", "on", "1"}
	if kind == "integer":
		return int(value)
	if kind == "string":
		return value
	raise ValueError(f"Unexpected confspec check: {validator}")


def configobj_stub(stubs):
	"""Register configobj.validate with the errors NVDA's config raises on read; return that module.

	The messages are configobj's own, which quote the stored value.
	"""

	class ValidateError(Exception):
		pass

	class VdtTypeError(ValidateError):
		def __init__(self, value):
			super().__init__(f'the value "{value}" is of the wrong type.')

	class VdtValueError(ValidateError):
		def __init__(self, value):
			super().__init__(f'the value "{value}" is unacceptable.')

	class VdtValueTooSmallError(VdtValueError):
		def __init__(self, value):
			ValidateError.__init__(self, f'the value "{value}" is too small.')

	class VdtValueTooBigError(VdtValueError):
		def __init__(self, value):
			ValidateError.__init__(self, f'the value "{value}" is too big.')

	package = stubs.module("configobj")
	package.__path__ = []
	validate = stubs.module(
		"configobj.validate",
		ValidateError=ValidateError,
		VdtTypeError=VdtTypeError,
		VdtValueError=VdtValueError,
		VdtValueTooSmallError=VdtValueTooSmallError,
		VdtValueTooBigError=VdtValueTooBigError,
	)
	package.validate = validate
	return validate


class RefusingSection(dict):
	"""A config section that refuses some stored values on read, as NVDA's validation does.

	refused maps a key to the error reading it raises. NVDA validates a stored value on every
	read (config/__init__.py:1269-1274) and its get only catches KeyError, so both get and []
	raise it.
	"""

	def __init__(self, values=(), refused=None):
		super().__init__(values)
		self.refused = dict(refused or {})

	def __getitem__(self, key):
		if key in self.refused:
			raise self.refused[key]
		return super().__getitem__(key)

	def get(self, key, default=None):
		if key in self.refused:
			raise self.refused[key]
		return super().get(key, default)
