"""Stand-ins for NVDA modules, registered in sys.modules for one test."""

import ast
import builtins
import copy
import functools
import re
import sys
from types import ModuleType

from addon_loader import WORLDVOICE, load_definitions

# The file whose installConfspec(conf) assigns conf.spec["WorldVoice"].
CONFSPEC_SOURCE = WORLDVOICE / "__init__.py"


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
	those defaults; a key the section's confspec lacks raises KeyError, except in a section with
	no keys of its own (engines, roles, voices), whose keys are data. The defaults are read from
	the add-on sources, so a new key reaches every test that uses this stub.
	"""
	conf = copy.deepcopy(_worldvoice_defaults())
	for name, values in sections.items():
		if name not in conf:
			raise KeyError(f"The WorldVoice confspec has no {name!r} section")
		unknown = sorted(set(values) - set(conf[name]))
		if conf[name] and unknown:
			raise KeyError(f"The WorldVoice confspec's {name!r} section has no {unknown}")
		conf[name].update(values)
	return {"WorldVoice": conf}


@functools.cache
def _worldvoice_defaults():
	# conf.spec["WorldVoice"] = {...} in installConfspec(conf) of CONFSPEC_SOURCE.
	for function in ast.parse(CONFSPEC_SOURCE.read_text(encoding="utf-8")).body:
		if not (isinstance(function, ast.FunctionDef) and function.name == "installConfspec"):
			continue
		for node in function.body:
			if (
				isinstance(node, ast.Assign)
				and isinstance(node.targets[0], ast.Subscript)
				and ast.unparse(node.targets[0]) == "conf.spec['WorldVoice']"
			):
				return _section_defaults(node.value)
	raise LookupError(f"installConfspec in {CONFSPEC_SOURCE.name} does not assign the WorldVoice confspec")


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


@functools.cache
def _stored_key_for():
	"""pipeline/settings.py's stored_key_for, run from the source with the STORED_WORDS it reads."""
	path = WORLDVOICE / "pipeline/settings.py"
	return load_definitions(path, ["STORED_WORDS", "stored_key_for"], {})["stored_key_for"]


def _spread_defaults(node):
	source = ast.unparse(node)
	if source == "DETECTION_CONFSPEC":
		spec = _top_level_value(WORLDVOICE / "languageDetection/settings.py", source)
		return {key: _confspec_default(validator) for key, validator in _detection_confspec(spec).items()}
	if source == "PIPELINE_CONFSPEC":
		# Built from the PipelineSettingSpec(key, kind, default, ...) table, under each key's stored
		# key, without the ordering-only entries (pipeline_config=False) NVDA stores as driver settings.
		table = _top_level_value(WORLDVOICE / "pipeline/settings.py", "PIPELINE_SETTINGS")
		stored_key_for = _stored_key_for()
		return {
			stored_key_for(ast.literal_eval(spec.args[0])): ast.literal_eval(spec.args[2])
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
		# One log switch per Stage(log_key, fn) in pipeline STAGES, except log_switch=False ones,
		# and one per key of a stage's also_logged_by, each under its stored key.
		stages = _top_level_value(WORLDVOICE / "pipeline/registry.py", "STAGES")
		value = _value_default(node.value)
		stored_key_for = _stored_key_for()
		keys = {}
		for stage in stages.elts:
			options = {keyword.arg: ast.literal_eval(keyword.value) for keyword in stage.keywords}
			if options.get("log_switch", True) is False:
				continue
			for key in (*options.get("also_logged_by", ()), ast.literal_eval(stage.args[0])):
				keys[stored_key_for(key)] = value
		return keys
	raise ValueError(f"Unexpected confspec entries: {source}")


def _detection_confspec(node):
	"""DETECTION_CONFSPEC: its literal entries, and one entry per row of the script table for a
	{row.<field>: f"...{row.<field>}..." for row in DETECTION_SCRIPTS} spread into it (no if)."""
	spec = {}
	for key, value in zip(node.keys, node.values, strict=True):
		if key is not None:
			spec[ast.literal_eval(key)] = ast.literal_eval(value)
		elif (
			isinstance(value, ast.DictComp)
			and len(value.generators) == 1
			and ast.unparse(value.generators[0].iter) == "DETECTION_SCRIPTS"
			# A filter would drop rows the stub keeps; an async loop is no plain table walk.
			and not value.generators[0].ifs
			and not value.generators[0].is_async
		):
			name = value.generators[0].target.id
			for row in _detection_scripts():
				spec[_row_value(value.key, name, row)] = _row_value(value.value, name, row)
		else:
			raise ValueError(f"Unexpected detection confspec entries: {ast.unparse(value)}")
	return spec


def _row_value(node, name, row):
	"""A field of row (name.field), a constant, or an f-string of them."""
	if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == name:
		return row[node.attr]
	if isinstance(node, ast.Constant):
		return node.value
	if isinstance(node, ast.JoinedStr):
		return "".join(
			str(_row_value(part.value if isinstance(part, ast.FormattedValue) else part, name, row))
			for part in node.values
		)
	raise ValueError(f"Unexpected detection confspec expression: {ast.unparse(node)}")


def _detection_scripts():
	"""The DetectionScript(...) rows of scriptLanguages.py, each as a dict of its fields."""
	path = WORLDVOICE / "languageDetection/scriptLanguages.py"
	(fields,) = [
		[item.target.id for item in node.body if isinstance(item, ast.AnnAssign)]
		for node in ast.parse(path.read_text(encoding="utf-8")).body
		if isinstance(node, ast.ClassDef) and node.name == "DetectionScript"
	]
	rows = []
	for call in _top_level_value(path, "DETECTION_SCRIPTS").elts:
		row = dict(zip(fields, (ast.literal_eval(argument) for argument in call.args), strict=False))
		row.update({keyword.arg: ast.literal_eval(keyword.value) for keyword in call.keywords})
		rows.append(row)
	return rows


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


_MISSING = object()


class RefusingSection(dict):
	"""A config section that refuses some stored values on read and skips unchanged writes, as NVDA does.

	refused maps a key to the error reading it raises. NVDA validates a stored value on every
	read (config/__init__.py:1269-1273) and its get only catches KeyError, so both get and []
	raise it. NVDA's __setitem__ (:1354-1372) compares the new value's str with the current one,
	read unvalidated (checkValidity=False): the stored value, else the confspec default (here
	defaults). An equal one is not written; any other replaces the stored value, a refused one
	too, and its key is recorded in written.
	"""

	def __init__(self, values=(), refused=None, defaults=None):
		super().__init__(values)
		self.refused = dict(refused or {})
		self.defaults = dict(defaults or {})
		self.written = []

	def __getitem__(self, key):
		if key in self.refused:
			raise self.refused[key]
		return super().__getitem__(key)

	def get(self, key, default=None):
		if key in self.refused:
			raise self.refused[key]
		return super().get(key, default)

	def __setitem__(self, key, value):
		# dict.get reads the raw value, refused or not, as checkValidity=False does.
		current = dict.get(self, key, self.defaults.get(key, _MISSING))
		if current is not _MISSING and str(current) == str(value):
			return
		self.refused.pop(key, None)
		self.written.append(key)
		super().__setitem__(key, value)
