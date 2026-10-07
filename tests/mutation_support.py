"""Let mutmut match the add-on modules these tests load under alias packages.

mutmut keys each mutant by the module path of its file (addon.synthDrivers.WorldVoice...), and
records which tests reach which function by the function's __module__. Tests load the add-on
under alias packages, so without this the names disagree, mutmut selects no test for a mutant
and reports it as surviving. Each trampolined function is named by its file instead.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def running_under_mutmut():
	# mutmut runs the tests from its copy of the project in mutants/.
	return ROOT.name == "mutants"


def _module_name(path):
	path = Path(path).resolve()
	if not path.is_relative_to(ROOT):
		return None
	parts = path.relative_to(ROOT).with_suffix("").parts
	return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def name_trampolines_by_file():
	"""Name what mutmut compares and records by the file, not by the alias it was loaded under."""
	from mutmut.mutation import trampoline

	wrap_in_trampoline = trampoline.wrap_in_trampoline
	record_trampoline_hit = trampoline.record_trampoline_hit
	# Alias module name -> the name mutmut derives from the file. Harnesses drop their aliases
	# from sys.modules, so remember them when the functions are decorated.
	canonical = {}

	def wrap(mutants_dict, is_classmethod=False):
		decorate = wrap_in_trampoline(mutants_dict, is_classmethod)

		def named(decorated):
			# The trampoline runs a mutant only when its module matches this name.
			name = _module_name(decorated.__code__.co_filename)
			if name is not None:
				canonical[decorated.__module__] = name
				decorated.__module__ = name
			return decorate(decorated)

		return named

	def record(name, caller=None):
		# The stats run records the original function's module, still the alias.
		alias, _, function = name.rpartition(".")
		return record_trampoline_hit(f"{canonical.get(alias, alias)}.{function}", caller=caller)

	trampoline.wrap_in_trampoline = wrap
	trampoline.record_trampoline_hit = record
