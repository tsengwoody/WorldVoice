"""Read NVDA releases from ref/nvda and check host names on their source (phase 51 §4.2, §5).

The runtime check (runtime/hostNames.py) looks at the live NVDA module and class. Old releases
cannot be imported here, so static_missing builds the same view from a release's compiled source:
a module name exists when the module body stores it at top level (STORE_NAME, or STORE_GLOBAL
for a name some function declares `global`); a class name exists when the class body stores it
or the code nested in the body stores it as an attribute. It sees one class and one file, where
the live check sees the whole MRO, so the static view is the stricter one, with two exceptions:

- a module name bound only inside `if` or `try` (a platform check, `except ImportError`) counts
  here even when that branch does not run on the user's machine, where the live check misses it;
- the live check reads functions only one level below a class attribute (hostNames.py), so a
  method under a decorator that keeps no __wrapped__, under two wrapping decorators, or under
  staticmethod, classmethod or property over a wrapping decorator hides its stores from the live check, not
  from the compiled source.

The phase 51 review checked every release in RELEASES by hand: no name the wrappers list is bound
either way. A name added to a list later is not checked for this automatically.
"""

import ast
import dis
import functools
import subprocess
import warnings
from collections.abc import Iterable
from dataclasses import dataclass
from types import CodeType

import pytest
from addon_loader import REF, WORLDVOICE, load_source

NVDA = REF / "nvda"
# One tag per NVDA feature release in the supported range, then the newest tag. Point releases
# never change the synth driver files (phase 51 spec §5). Add each new release here when ref/nvda
# is updated; a test fails while the newest feature release in ref/nvda's tags is not here.
RELEASES = (
	"2024.1",
	"2024.2",
	"2024.3",
	"2024.4",
	"2025.1",
	"2025.2",
	"2025.3",
	"2026.1",
	"2026.2",
	"2026.3beta6",
)
WORKING_TREE = "working-tree"

host_names = load_source(None, "hostNames_for_releases", WORLDVOICE / "runtime/hostNames.py", register=False)


@functools.cache
def release_source(version: str, file: str) -> str:
	"""synthDrivers/<file> of NVDA release <version>, or of the ref/nvda working tree."""
	if version == WORKING_TREE:
		return (NVDA / "source/synthDrivers" / file).read_text(encoding="utf-8")
	tag = f"release-{version}"
	result = subprocess.run(
		["git", "-C", str(NVDA), "show", f"{tag}:source/synthDrivers/{file}"],
		capture_output=True,
		text=True,
		encoding="utf-8",
		check=False,
	)
	if result.returncode != 0:
		pytest.fail(
			f"ref/nvda has no {tag} (or no {file} in it): {result.stderr.strip()}. The NVDA-name "
			"check covers every supported NVDA release; fetch NVDA's release tags with "
			"`git -C ref/nvda fetch --tags` or use a full clone.",
		)
	return result.stdout


def _stored_names(code: CodeType, opnames=frozenset({"STORE_NAME"})) -> set[str]:
	return {instruction.argval for instruction in dis.get_instructions(code) if instruction.opname in opnames}


def static_missing(
	source: str,
	module_label: str,
	class_name: str,
	class_label: str,
	*,
	module_names: Iterable[str],
	class_names: Iterable[str],
) -> tuple[str, ...]:
	"""The listed names source lacks, in missing_host_names' format."""
	with warnings.catch_warnings():
		# Old sources may hold escapes a newer Python warns about.
		warnings.simplefilter("ignore", SyntaxWarning)
		module_code = compile(source, module_label, "exec")
	# A name a function declares `global` is stored with STORE_GLOBAL at module level too (NVDA's
	# _espeak.py: player, isSpeaking and others); a module-level `global` statement does the same.
	module_bound = _stored_names(module_code, frozenset({"STORE_NAME", "STORE_GLOBAL"}))
	class_bound = set()
	for const in module_code.co_consts:
		if isinstance(const, CodeType) and const.co_name == class_name:
			class_bound |= _stored_names(const) | host_names.stored_attribute_names(const)
	missing = [f"{module_label}.{name}" for name in module_names if name not in module_bound]
	missing += [f"{class_label}.{name}" for name in class_names if name not in class_bound]
	return tuple(sorted(missing))


@dataclass(frozen=True)
class EngineNames:
	"""Where one wrapper's NVDA names live: its port, NVDA's module and NVDA's synth class."""

	port: str
	module_file: str
	module_label: str
	class_file: str
	class_name: str
	class_label: str


ENGINES = {
	"Espeak": EngineNames(
		"_EspeakPort",
		"_espeak.py",
		"synthDrivers._espeak",
		"espeak.py",
		"SynthDriver",
		"synthDrivers.espeak.SynthDriver",
	),
	"SAPI5": EngineNames(
		"_Sapi5HostNames",
		"sapi5.py",
		"synthDrivers.sapi5",
		"sapi5.py",
		"SynthDriver",
		"synthDrivers.sapi5.SynthDriver",
	),
	"OneCore": EngineNames(
		"_OneCorePort",
		"oneCore.py",
		"synthDrivers.oneCore",
		"oneCore.py",
		"OneCoreSynthDriver",
		"synthDrivers.oneCore.OneCoreSynthDriver",
	),
}


@functools.cache
def port_names(engine: str) -> tuple[frozenset[str], frozenset[str]]:
	"""(module names, class names) the wrapper's port lists, read from its source."""
	tree = ast.parse((WORLDVOICE / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
	port = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == ENGINES[engine].port)
	constants = {}
	for node in port.body:
		if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
			args = node.value.args
			constants[node.targets[0].id] = frozenset(ast.literal_eval(args[0]) if args else ())
	return (
		constants["NVDA_MODULE_NAMES"],
		constants["NVDA_PRIVATES"] | constants["NVDA_OVERRIDES"],
	)


def release_missing(engine: str, version: str) -> tuple[str, ...]:
	"""The engine's listed names that NVDA <version> lacks (static view)."""
	names = ENGINES[engine]
	module_names, class_names = port_names(engine)
	missing = static_missing(
		release_source(version, names.module_file),
		names.module_label,
		"",
		"",
		module_names=module_names,
		class_names=(),
	)
	missing += static_missing(
		release_source(version, names.class_file),
		"",
		names.class_name,
		names.class_label,
		module_names=(),
		class_names=class_names,
	)
	return tuple(sorted(missing))
