"""Read NVDA releases from ref/nvda and check host names on their source (phase 51 §4.2, §5).

The runtime check (runtime/hostNames.py) looks at the live NVDA module and class. Old releases
cannot be imported here, so static_missing builds the same view from a release's compiled source:
a module name exists when the module body stores it at top level; a class name exists when the
class body stores it or the code nested in the body stores it as an attribute. It sees one class
and one file, where the live check sees the whole MRO, so the runtime is never the stricter one.
"""

import dis
import functools
import subprocess
import warnings
from collections.abc import Iterable
from types import CodeType

import pytest
from addon_loader import REF, WORLDVOICE, load_source

NVDA = REF / "nvda"
# One tag per NVDA feature release in the supported range, then the newest tag. Point releases
# never change the synth driver files (phase 51 spec §5). Add each new release here when ref/nvda
# is updated.
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


def _stored_names(code: CodeType) -> set[str]:
	return {
		instruction.argval for instruction in dis.get_instructions(code) if instruction.opname == "STORE_NAME"
	}


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
	module_bound = _stored_names(module_code)
	class_bound = set()
	for const in module_code.co_consts:
		if isinstance(const, CodeType) and const.co_name == class_name:
			class_bound |= _stored_names(const) | host_names.stored_attribute_names(const)
	missing = [f"{module_label}.{name}" for name in module_names if name not in module_bound]
	missing += [f"{class_label}.{name}" for name in class_names if name not in class_bound]
	return tuple(sorted(missing))
