"""The NVDA names the eSpeak, SAPI5 and OneCore wrappers list, checked on each NVDA release (phase 51)."""

import textwrap
from types import ModuleType

from nvda_releases import host_names, static_missing

AGREEMENT_SOURCE = textwrap.dedent(
	"""
	import os.path
	from types import SimpleNamespace as Namespace

	top = 1

	global declared
	declared = 4

	def helper():
		pass

	class Other:
		pass

	if True:
		conditional = 2

	try:
		guarded = 3
	except Exception:
		pass

	class Cls:
		_flag = False

		def __init__(self):
			self._made = 1
			self.__hidden = 2

		def _method(self):
			self._later = 2

			def inner():
				self._nested = 3

			return inner

		def _get_rate(self):
			return 1

		rate = property(_get_rate)
	""",
)
MODULE_NAMES = {
	"declared",
	"os",
	"Namespace",
	"top",
	"helper",
	"Other",
	"conditional",
	"guarded",
	"absent",
	"path",
}
CLASS_NAMES = {
	"_flag",
	"_made",
	"_Cls__hidden",
	"__hidden",
	"_method",
	"_later",
	"_nested",
	"_get_rate",
	"rate",
	"_absent",
}


def live_module(name, source, namespace=None):
	module = ModuleType(name)
	module.__dict__.update(namespace or {})
	exec(compile(source, name, "exec"), module.__dict__)  # noqa: S102 - a fixed test source
	return module


def test_static_and_live_views_agree_on_synthetic_source():
	module = live_module("m", AGREEMENT_SOURCE)
	live = host_names.missing_host_names(
		module,
		module.Cls,
		module_names=MODULE_NAMES,
		class_names=CLASS_NAMES,
	)
	static = static_missing(
		AGREEMENT_SOURCE,
		"m",
		"Cls",
		"m.Cls",
		module_names=MODULE_NAMES,
		class_names=CLASS_NAMES,
	)
	assert static == live == ("m.Cls.__hidden", "m.Cls._absent", "m.absent", "m.path")


def test_static_view_does_not_see_out_of_file_bases():
	class Base:
		def __init__(self):
			self._base = 1

	source = "class Child(Base):\n\tpass\n"
	module = live_module("m", source, {"Base": Base})
	assert host_names.missing_host_names(module, module.Child, module_names=(), class_names={"_base"}) == ()
	assert static_missing(source, "m", "Child", "m.Child", module_names=(), class_names={"_base"}) == (
		"m.Child._base",
	)


def test_static_view_ignores_globals_bound_only_inside_functions():
	source = "def f():\n\tglobal late\n\tlate = 1\n\nclass Cls:\n\tpass\n"
	module = live_module("m", source)
	live = host_names.missing_host_names(module, module.Cls, module_names={"late"}, class_names=())
	static = static_missing(source, "m", "Cls", "m.Cls", module_names={"late"}, class_names=())
	assert static == live == ("m.late",)
