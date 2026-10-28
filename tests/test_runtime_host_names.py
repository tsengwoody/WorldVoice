"""The core host-name check: what "exists" means for a module name and a class name (phase 51 §4.2)."""

import textwrap
from types import ModuleType

import pytest
from addon_loader import WORLDVOICE, load_source

host_names = load_source(None, "hostNames_under_test", WORLDVOICE / "runtime/hostNames.py", register=False)


def make_module(name, source):
	module = ModuleType(name)
	exec(compile(textwrap.dedent(source), name, "exec"), module.__dict__)  # noqa: S102 - a fixed test source
	return module


def class_code(source, class_name):
	module_code = compile(textwrap.dedent(source), "probe", "exec")
	return next(c for c in module_code.co_consts if getattr(c, "co_name", None) == class_name)


class RecordingLogger:
	def __init__(self):
		self.records = []

	def __getattr__(self, level):
		return lambda message, *args: self.records.append((level, message % args))


def test_stored_attribute_names_finds_stores_in_methods_nested_functions_and_lambdas():
	code = class_code(
		"""
		class Probe:
			def __init__(self):
				self.a = 1
				self.loaded

			def other(self):
				self.b = 2

				def inner():
					self.c = 3

				return inner, lambda s, v=1: [s.__dict__]
		""",
		"Probe",
	)
	result = host_names.stored_attribute_names(code)
	assert {"a", "b", "c"} <= result
	assert "loaded" not in result
	assert "__dict__" not in result


def test_stored_attribute_names_reports_mangled_form():
	code = class_code(
		"""
		class K:
			def __init__(self):
				self.__x = 1
		""",
		"K",
	)
	assert "_K__x" in host_names.stored_attribute_names(code)


PROBE = """
b = 1

class Base:
	def __init__(self):
		self._base = 1

class Cls(Base):
	_flag = False

	def __init__(self):
		super().__init__()
		self._made = 1

	def _m(self):
		self._later = 2

	def _get_rate(self):
		return 1

	rate = property(_get_rate)

	@property
	def held(self):
		self._fromProperty = 1

	@staticmethod
	def build(obj):
		obj._fromStatic = 1

	@classmethod
	def make(cls, obj):
		obj._fromClassMethod = 1
"""


@pytest.fixture
def probe():
	return make_module("fake.mod", PROBE)


def missing(probe, *, module_names=(), class_names=()):
	return host_names.missing_host_names(probe, probe.Cls, module_names=module_names, class_names=class_names)


def test_missing_module_names_are_qualified_and_sorted(probe):
	assert missing(probe, module_names={"b", "z", "a"}) == ("fake.mod.a", "fake.mod.z")


def test_instance_attributes_from_init_and_other_methods_are_present(probe):
	assert missing(probe, class_names={"_made", "_later"}) == ()


def test_class_level_and_property_names_are_present(probe):
	names = {"_flag", "_m", "_get_rate", "rate", "_fromProperty", "_fromStatic", "_fromClassMethod"}
	assert missing(probe, class_names=names) == ()


def test_inherited_instance_attribute_is_present_live(probe):
	assert missing(probe, class_names={"_base"}) == ()


def test_missing_class_names_are_qualified_with_module_and_qualname(probe):
	assert missing(probe, class_names={"_gone", "_made"}) == ("fake.mod.Cls._gone",)


def test_module_and_class_names_are_sorted_together(probe):
	assert missing(probe, module_names={"zz"}, class_names={"_gone"}) == ("fake.mod.Cls._gone", "fake.mod.zz")


def ready(probe, logger, label, **names):
	return host_names.host_names_ready(
		"SAPI5",
		probe,
		probe.Cls,
		module_names=names.get("module_names", ()),
		class_names=names.get("class_names", ()),
		host_label=label,
		logger=logger,
	)


def test_ready_does_not_call_label_or_log_when_complete(probe):
	def label():
		raise AssertionError("the label is read only to log a skip")

	logger = RecordingLogger()
	assert ready(probe, logger, label, module_names={"b"}, class_names={"_made"}) is True
	assert logger.records == []


def test_ready_logs_one_warning_and_returns_false_when_missing(probe):
	logger = RecordingLogger()
	assert (
		ready(probe, logger, lambda: "NVDA 2025.1.0", module_names={"a", "b"}, class_names={"_gone"}) is False
	)
	message = (
		"Skipping SAPI5 engine candidate: NVDA 2025.1.0 lacks names this engine needs: "
		"fake.mod.Cls._gone, fake.mod.a"
	)
	assert logger.records == [("warning", message)]
