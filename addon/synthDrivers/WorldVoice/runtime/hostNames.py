"""Check that a host module and class still have the names an engine wrapper relies on.

A wrapper built on the host's own engine module (NVDA's synthDrivers.sapi5, say) lists the names
it reads, writes or overrides there. Before the engine is offered, the wrapper checks them here
against the running host, so a host version that lacks one does not fail at construction or speak
time: host_names_ready skips the engine with one log line, or a wrapper with another whole core to
use instead (SAPI5: NVDA's own driver) chooses it from missing_host_names.

What "exists" means, for the live check here and the tests' check of a release's source alike:

- a module name exists when the module has it as an attribute;
- a class name exists when the class has it (its own or inherited, a method, a class attribute or
  a property), or when code of a function defined on a class in its MRO stores it as an attribute
  (STORE_ATTR, on any object), which is how instance attributes made in __init__ show up without
  constructing the class. A name-mangled name is listed in its mangled form.

The functions read are one level below each attribute in the dict of a class in the MRO: the
attribute itself when it is a function, the function under staticmethod, classmethod or property
(fget, fset, fdel), and the attribute's own __wrapped__ (one functools.wraps decorator). Nothing
deeper is followed, so stores are not seen in a function under a decorator that keeps no
__wrapped__, under two wrapping decorators, or under staticmethod or property over a wrapping
decorator (there the wrapper's own code is read).
"""

import dis
from collections.abc import Callable, Iterable, Iterator
from types import CodeType


def _nested_code(code: CodeType) -> Iterator[CodeType]:
	yield code
	for const in code.co_consts:
		if isinstance(const, CodeType):
			yield from _nested_code(const)


def stored_attribute_names(code: CodeType) -> frozenset[str]:
	"""Every attribute name code, or code nested in it, stores (STORE_ATTR)."""
	return frozenset(
		instruction.argval
		for nested in _nested_code(code)
		for instruction in dis.get_instructions(nested)
		if instruction.opname == "STORE_ATTR"
	)


def _function_code(value) -> Iterator[CodeType]:
	# One level only: the value as a function, the function under staticmethod, classmethod and
	# property, and the value's own __wrapped__. A __wrapped__ chain is not followed.
	for candidate in (
		value,
		getattr(value, "__wrapped__", None),
		getattr(value, "__func__", None),
		getattr(value, "fget", None),
		getattr(value, "fset", None),
		getattr(value, "fdel", None),
	):
		code = getattr(candidate, "__code__", None)
		if isinstance(code, CodeType):
			yield code


def _class_stored_names(host_class: type) -> frozenset[str]:
	names = set()
	# object's own members are builtins without code, so walking it adds nothing.
	for klass in host_class.__mro__:
		for value in vars(klass).values():
			for code in _function_code(value):
				names |= stored_attribute_names(code)
	return frozenset(names)


def missing_host_names(
	module,
	host_class: type,
	*,
	module_names: Iterable[str],
	class_names: Iterable[str],
) -> tuple[str, ...]:
	"""The listed names the module or class lacks, qualified with their owner and sorted."""
	missing = [f"{module.__name__}.{name}" for name in module_names if not hasattr(module, name)]
	absent = [name for name in class_names if not hasattr(host_class, name)]
	if absent:
		stored = _class_stored_names(host_class)
		owner = f"{host_class.__module__}.{host_class.__qualname__}"
		missing += [f"{owner}.{name}" for name in absent if name not in stored]
	return tuple(sorted(missing))


def host_names_ready(
	engine: str,
	module,
	host_class: type,
	*,
	module_names: Iterable[str],
	class_names: Iterable[str],
	host_label: Callable[[], str],
	logger,
) -> bool:
	"""True when nothing listed is missing; otherwise log one warning naming them and return False.

	host_label names the host and its version; it is called only to write the warning.
	"""
	missing = missing_host_names(module, host_class, module_names=module_names, class_names=class_names)
	if not missing:
		return True
	logger.warning(
		"Skipping %s engine candidate: %s lacks names this engine needs: %s",
		engine,
		host_label(),
		", ".join(missing),
	)
	return False
