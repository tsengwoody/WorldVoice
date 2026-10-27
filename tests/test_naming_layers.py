"""Names follow the layer of the module that defines them (refactor9 §6.1, decided 2026-10-27).

1. The layer of a module decides the style of the names it defines itself:
   - portable core (CORE): PEP 8 snake_case;
   - NVDA host layer (HOST): NVDA's mixedCase (ref/nvda/projectDocs/dev/codingStandards.md), a
     lowercase first letter and no underscore apart from the prefixes script_, event_, _get_, _set_ of
     a function or method;
   - both: classes in CapWords; module and class names may also be UPPER_CASE constants or
     CapWords type aliases; leading underscores and dunder names are free.
   PENDING modules wait for the command model (refactor9 §6.2) and are not checked. EXCLUDED code
   (vendored engine drivers, NVDA's sonic, generated Unicode data) and tests/ are not renamed.
2. A name that implements or overrides someone else's interface keeps that name:
   - a method or field whose name a base class defines, when the guard can read that base: a class
     of the add-on named in the class statement (a Protocol or ABC of the core, a vendored driver
     class, driver.Voice, also under an alias such as BaseVoice), and a parameter of such a method
     that the base method also takes. A structural implementation of a core interface names it as a
     base, so the guard can read it: the bridge's adapters derive from runtime.session.EngineAdapter
     and runtime.scheduler.NotificationOutput, the engine wrappers' SynthDriver from
     runtime.segmentHost.SegmentDrainCore. An NVDA driver's metaclass (baseObject.AutoPropertyType,
     an ABCMeta) conflicts with a Protocol's, so such a base for a driver is an ABC;
   - a name from an interface the guard cannot read (NVDA, its setting ids included, the standard
     library, a native library's exports) is listed in INTERFACE_NAMES with the interface it mirrors.
   typing.override cannot be the marker yet: see test_no_module_imports_typing_override.
3. Stored identifiers use NVDA camelCase (refactor9 §6.1 rule 3, decided by the user 2026-10-27):
   what WorldVoice stores in a user's NVDA files belongs to the host layer, so the keys of nvda.ini's
   [WorldVoice] section, the driver setting ids and the script names gestures.ini binds have a
   lowercase first letter and no underscore (phase 47d renamed them without a migration). The core
   keeps its snake_case fields and maps each to its stored key (pipeline/settings.stored_key_for).
   Listed, with reasons: the product name (PROPER_NOUN_SECTIONS), the data sections whose keys are
   names, not identifiers (DATA_SECTIONS), and NVDA's own setting ids (NVDA_SETTING_IDS).

Every name a module binds is checked except imports: functions, methods, classes, parameters
(lambdas included), class and dataclass fields, attributes set on self or cls, module variables and
local variables (match captures included). Not checked: a name given as a string, as in
setattr(obj, "name", value), and an attribute set on another object than self or cls.
No list waits for a later phase: phases 47b to 47d emptied them.
"""

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from addon_loader import REF
from nvda_stubs import worldvoice_conf
from pipeline_harness import load_synth

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"
SYNTH = "synthDrivers/WorldVoice/"

CORE = tuple(
	SYNTH + path
	for path in (
		"runtime/",
		"unicodeScripts/",
		"text/",
		"languageDetection/",
		"pipeline/",
		"voices/",
		"listeners.py",
		"locales.py",
		"numberLanguage.py",
		"bringup.py",
		"speechCommands.py",
	)
)
HOST = (
	SYNTH + "bridge/",
	SYNTH + "driver/",
	SYNTH + "ui/",
	SYNTH + "__init__.py",
	SYNTH + "confspec.py",
	"globalPlugins/WorldVoice/",
	"installTasks.py",
	"generics/",
)
PENDING = (SYNTH + "engineRegistry/", SYNTH + "workspace.py")
EXCLUDED = re.compile(
	r"synthDrivers/WorldVoice/(driver/[^/]+/driver/|driver/sonic/|unicodeScripts/\w+_data\.py$)",
)

SNAKE_CASE = re.compile(r"_*[a-z][a-z0-9_]*")
MIXED_CASE = re.compile(r"_*[a-z][a-zA-Z0-9]*")
# NVDA's method prefixes: scripts, events and auto-property getters and setters are functions.
MIXED_CASE_FUNCTION = re.compile(r"_*(script_|event_|_get_|_set_)?[a-z][a-zA-Z0-9]*")
CAP_WORDS = re.compile(r"_*[A-Z][a-zA-Z0-9]*")
UPPER_CASE = re.compile(r"_*[A-Z][A-Z0-9_]*")

# Names from interfaces outside the add-on: {module path: {qualified name: the interface}}.
INTERFACE_NAMES = {
	SYNTH + "driver/Cerence/__init__.py": {
		"_SilenceGate.is_set": "threading.Event.is_set, to which the vendored callback's _isSilence.isSet() forwards",
	},
	SYNTH + "driver/Espeak/__init__.py": {
		"_SegmentNative.espeak_Synth": "the eSpeak NG DLL export, proxied for NVDA's _espeak.espeakDLL",
		"_SegmentNative.espeak_ng_Cancel": "the eSpeak NG DLL export, proxied for NVDA's _espeak.espeakDLL",
	},
	SYNTH + "driver/RHVoice/__init__.py": {
		"_NativeLibrary.RHVoice_delete_message": "the RHVoice export the vendored driver's __lib calls by name",
		"_NativeLibrary.RHVoice_new_message": "the RHVoice export the vendored driver's __lib calls by name",
		"_NativeLibrary.RHVoice_speak": "the RHVoice export the vendored driver's __lib calls by name",
	},
	SYNTH + "driver/SAPI5/__init__.py": {
		"_SegmentAudioStream.ISequentialStream_RemoteWrite": "NVDA synthDrivers.sapi5.SynthDriverAudioStream."
		"ISequentialStream_RemoteWrite, the COM method comtypes calls by name",
		"_SegmentSapiSink.Bookmark": "NVDA sapi5.SapiSink.Bookmark, the SAPI event comtypes calls by name",
		"_SegmentSapiSink.EndStream": "NVDA sapi5.SapiSink.EndStream, the SAPI event comtypes calls by name",
		"_SegmentSapiSink.ISpNotifySink_Notify": "NVDA synthDrivers.sapi5.SapiSink.ISpNotifySink_Notify, the COM "
		"method comtypes calls by name",
		"_SegmentSapiSink.StartStream": "NVDA sapi5.SapiSink.StartStream, the SAPI event comtypes calls by name",
	},
	SYNTH + "driver/VE/__init__.py": {
		"_SilenceGate.is_set": "threading.Event.is_set, to which the vendored callback's _isSilence.isSet() forwards",
	},
	SYNTH + "runtime/models.py": {
		"VoiceSnapshot.rateBoost": "the voice setting id rateBoost (runtime/voiceSettings.VOICE_PARAMETERS), "
		"stored in nvda.ini and NVDA's SynthDriver setting of that name",
	},
	SYNTH + "runtime/segmentHost.py": {
		"LeasedPlayer.feed.<locals>.onDone": "NVDA nvwave.WavePlayer.feed(data, size=None, onDone=None), "
		"which engine wrappers call by keyword",
	},
	SYNTH + "speechCommands.py": {
		"WVLangChangeCommand.isDefault": "NVDA speech.commands.SynthParamCommand.isDefault, which "
		"ParamChangeTracker.update reads (speech/manager.py)",
	},
}


@dataclass(frozen=True)
class Definition:
	path: str
	qualname: str
	name: str
	kind: str  # class, function, parameter, field, variable or local
	line: int


def layer(path: str) -> str | None:
	"""core, host, pending or excluded for a module path relative to addon/; None when unknown."""
	if EXCLUDED.match(path):
		return "excluded"
	for name, prefixes in (("pending", PENDING), ("core", CORE), ("host", HOST)):
		if path.startswith(prefixes):
			return name
	return None


def follows_layer(definition: Definition, module_layer: str) -> bool:
	name = definition.name
	if name.startswith("__") and name.endswith("__") or not name.strip("_"):
		return True
	if definition.kind == "class":
		return bool(CAP_WORDS.fullmatch(name))
	if definition.kind in ("field", "variable") and (UPPER_CASE.fullmatch(name) or CAP_WORDS.fullmatch(name)):
		return True
	if module_layer == "core":
		return bool(SNAKE_CASE.fullmatch(name))
	return bool((MIXED_CASE_FUNCTION if definition.kind == "function" else MIXED_CASE).fullmatch(name))


def _module_name(path: str) -> str:
	parts = path.removesuffix(".py").split("/")
	return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _arguments(arguments: ast.arguments) -> list[ast.arg]:
	extra = [arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None]
	return [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs, *extra]


def _self_fields(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[ast.Attribute]:
	"""The attributes a method sets on its first parameter (self, or cls in a class method)."""
	arguments = node.args.posonlyargs + node.args.args
	if not arguments or any(getattr(item, "id", None) == "staticmethod" for item in node.decorator_list):
		return
	for target in ast.walk(node):
		if (
			isinstance(target, ast.Attribute)
			and isinstance(target.ctx, ast.Store)
			and isinstance(target.value, ast.Name)
			and target.value.id == arguments[0].arg
		):
			yield target


def _class_members(node: ast.ClassDef) -> dict[str, set[str]]:
	"""The method and field names a class defines itself, each with its parameter names (none for a field)."""
	members: dict[str, set[str]] = {}
	pending = list(node.body)
	while pending:
		item = pending.pop()
		if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
			members.setdefault(item.name, set()).update(argument.arg for argument in _arguments(item.args))
			for target in _self_fields(item):
				members.setdefault(target.attr, set())
		elif isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store):
			members.setdefault(item.id, set())
		elif not isinstance(item, ast.ClassDef):
			pending += ast.iter_child_nodes(item)
	return members


class _Module:
	"""One parsed module: what its imported names refer to, and its top-level classes."""

	def __init__(self, path: str, source: str):
		self.path = path
		self.tree = ast.parse(source)
		package = _module_name(path).split(".")
		if not path.endswith("/__init__.py"):
			package = package[:-1]
		# name -> (module, attribute), attribute None for an imported module.
		self.imports: dict[str, tuple[str, str | None]] = {}
		for node in ast.walk(self.tree):
			if isinstance(node, ast.ImportFrom):
				source_module = node.module or ""
				if node.level:
					parent = package[: len(package) - node.level + 1]
					source_module = ".".join([*parent, *filter(None, [node.module])])
				for alias in node.names:
					self.imports[alias.asname or alias.name] = (source_module, alias.name)
			elif isinstance(node, ast.Import):
				for alias in node.names:
					bound = alias.asname or alias.name.partition(".")[0]
					self.imports[bound] = (alias.name if alias.asname else bound, None)
		self.classes = {node.name: node for node in self.tree.body if isinstance(node, ast.ClassDef)}


class _Index:
	"""Modules by dotted name, to read the base classes that a checked class names."""

	def __init__(self, sources: dict[str, str]):
		self.modules = {_module_name(path): _Module(path, source) for path, source in sources.items()}
		self._owners = {
			id(node): module for module in self.modules.values() for node in module.classes.values()
		}

	@classmethod
	def of_addon(cls) -> "_Index":
		files = sorted(ADDON.rglob("*.py"))
		return cls({file.relative_to(ADDON).as_posix(): file.read_text(encoding="utf-8") for file in files})

	def _lookup(self, module_name: str, name: str, depth: int = 0) -> ast.ClassDef | None:
		"""The class module_name defines or imports as name, following re-exports."""
		module = self.modules.get(module_name)
		if module is None or depth > 5:
			return None
		if name in module.classes:
			return module.classes[name]
		source, attribute = module.imports.get(name, ("", None))
		return None if attribute is None else self._lookup(source, attribute, depth + 1)

	def _resolve(self, module: _Module, base: ast.expr, line: int) -> ast.ClassDef | None:
		"""The class base names in a class statement at line of module (class X(X) names the import)."""
		if isinstance(base, ast.Subscript):
			base = base.value
		if isinstance(base, ast.Name):
			if base.id in module.classes and module.classes[base.id].lineno < line:
				return module.classes[base.id]
			source, attribute = module.imports.get(base.id, ("", None))
			return None if attribute is None else self._lookup(source, attribute)
		if (
			isinstance(base, ast.Attribute)
			and isinstance(base.value, ast.Name)
			and base.value.id in module.imports
		):
			source, attribute = module.imports[base.value.id]
			return self._lookup(source if attribute is None else f"{source}.{attribute}", base.attr)
		return None

	def inherited(self, module: _Module, node: ast.ClassDef) -> dict[str, set[str]]:
		"""The members of every base class of node that the index can read, transitively, each with
		the parameter names its methods take."""
		names: dict[str, set[str]] = {}
		pending = [(module, base, node.lineno) for base in node.bases]
		seen = set()
		while pending:
			owner, base, line = pending.pop()
			found = self._resolve(owner, base, line)
			if found is None or id(found) in seen:
				continue
			seen.add(id(found))
			for name, parameters in _class_members(found).items():
				names.setdefault(name, set()).update(parameters)
			pending += [(self._owners[id(found)], parent, found.lineno) for parent in found.bases]
		return names


class _Walker:
	"""Each name one module binds, with whether a base class of its class defines it (rule 2)."""

	def __init__(self, index: _Index, module: _Module):
		self.index = index
		self.module = module
		self.found: list[tuple[Definition, bool]] = []
		self.body(module.tree.body, "", "variable", frozenset(), frozenset())

	def add(self, scope: str, name: str, kind: str, line: int, overrides: bool = False) -> None:
		self.found.append((Definition(self.module.path, scope + name, name, kind, line), overrides))

	def body(self, nodes, scope, kind, inherited, declared_global):
		for node in nodes:
			self.visit(node, scope, kind, inherited, declared_global)

	def visit(self, node, scope, kind, inherited, declared_global):
		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
			self.function(node, scope, kind == "field", inherited)
			return
		if isinstance(node, ast.ClassDef):
			self.add(scope, node.name, "class", node.lineno)
			self.body(
				node.body,
				f"{scope}{node.name}.",
				"field",
				self.index.inherited(self.module, node),
				frozenset(),
			)
			return
		if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
			if node.id in declared_global:
				self.add("", node.id, "variable", node.lineno)
			else:
				self.add(scope, node.id, kind, node.lineno, node.id in inherited)
		elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name:
			self.add(scope, node.name, kind, node.lineno)
		elif isinstance(node, ast.MatchMapping) and node.rest:
			self.add(scope, node.rest, kind, node.lineno)
		elif isinstance(node, ast.Lambda):
			for argument in _arguments(node.args):
				self.add(scope, argument.arg, "parameter", argument.lineno)
		for child in ast.iter_child_nodes(node):
			self.visit(child, scope, kind, inherited, declared_global)

	def function(self, node, scope, is_method, inherited):
		overrides = is_method and node.name in inherited
		self.add(scope, node.name, "function", node.lineno, overrides)
		inner = f"{scope}{node.name}.<locals>."
		for argument in _arguments(node.args):
			mirrored = overrides and argument.arg in inherited[node.name]
			self.add(inner, argument.arg, "parameter", argument.lineno, mirrored)
		declared = frozenset(
			name for child in ast.walk(node) if isinstance(child, ast.Global) for name in child.names
		)
		self.body(node.body, inner, "local", frozenset(), declared)
		if is_method:
			for target in _self_fields(node):
				self.add(scope, target.attr, "field", target.lineno, target.attr in inherited)


def violations(index: _Index) -> dict[tuple[str, str], Definition]:
	"""The definitions in checked modules that break their layer's style and override nothing."""
	found = {}
	for module in index.modules.values():
		module_layer = layer(module.path)
		if module_layer not in ("core", "host"):
			continue
		for definition, overrides in _Walker(index, module).found:
			if not overrides and not follows_layer(definition, module_layer):
				found.setdefault((definition.path, definition.qualname), definition)
	return found


def _listed(*tables: dict) -> set[tuple[str, str]]:
	return {(path, name) for table in tables for path, names in table.items() for name in names}


@pytest.fixture(scope="module")
def addon_violations():
	return violations(_Index.of_addon())


def test_every_add_on_module_has_a_layer():
	paths = sorted(file.relative_to(ADDON).as_posix() for file in ADDON.rglob("*.py"))
	assert [path for path in paths if layer(path) is None] == []


def test_naming_follows_layer(addon_violations):
	listed = _listed(INTERFACE_NAMES)
	assert [
		f"{definition.path}:{definition.line} {definition.qualname}"
		for key, definition in sorted(addon_violations.items())
		if key not in listed
	] == []


def test_lists_hold_only_names_that_break_the_rule(addon_violations):
	# A renamed or removed name must leave the lists, so they only shrink.
	listed = _listed(INTERFACE_NAMES)
	assert sorted(listed - set(addon_violations)) == []


def test_no_module_imports_typing_override():
	# typing.override is new in Python 3.12, and NVDA runs Python 3.11 before 2026.1
	# (ref/nvda/user_docs/en/changes.md, 2026.1: "NVDA is now built with Python 3.13"). While the
	# add-on supports an older NVDA, the import would stop the synth from loading there.
	build_vars = (ROOT / "buildVars.py").read_text(encoding="utf-8")
	minimum = re.search(r'addon_minimumNVDAVersion="(\d+)\.(\d+)', build_vars)
	assert minimum
	if (int(minimum.group(1)), int(minimum.group(2))) >= (2026, 1):
		# Not a skip: the suite keeps 0 skipped, so the test must go when its reason does.
		pytest.fail(
			"The minimum NVDA version now runs Python 3.13, so typing.override imports there: delete this test.",
		)
	importers = []
	for file in sorted(ADDON.rglob("*.py")):
		path = file.relative_to(ADDON).as_posix()
		if layer(path) == "excluded":
			continue
		for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
			if (
				isinstance(node, ast.ImportFrom)
				and node.module in ("typing", "typing_extensions")
				and any(alias.name == "override" for alias in node.names)
			):
				importers.append(f"{path}:{node.lineno}")
	assert importers == []


# Rule 3: the identifiers WorldVoice stores in a user's NVDA files.
STORED_CASE = re.compile(r"[a-z][a-zA-Z0-9]*")
# Not walked: the product name, which NVDA also stores as the selected synthesizer ([speech] synth).
PROPER_NOUN_SECTIONS = {
	"WorldVoice": "the product name: nvda.ini's [WorldVoice] and [speech][WorldVoice] sections and the "
	"synth name NVDA stores as the selected synthesizer",
}
# Sections whose keys are data, not identifiers; the confspec defines none of their keys (only __many__).
DATA_SECTIONS = {
	"engine": "engine names, each enabled or not",
	"role": "locales, each a section naming the voice assigned to it",
	"voices": "voice names, each a section of NVDA's voice setting ids",
}
# NVDA's own setting ids (synthDriverHandler.SynthDriver), which the synth and each voice store; they are
# camelCase already, and listed to pin that they are NVDA's, not WorldVoice's, names.
NVDA_SETTING_IDS = frozenset({"voice", "variant", "rate", "rateBoost", "pitch", "inflection", "volume"})


def stored_identifier_violations(names):
	"""Each (where, name) whose name is not NVDA camelCase, as "where: name"."""
	return [f"{where}: {name}" for where, name in names if not STORED_CASE.fullmatch(name)]


def _driver_setting_ids(monkeypatch):
	synth_class, _settings = load_synth(monkeypatch, worldvoice_conf())
	return [setting.id for setting in object.__new__(synth_class).allSupportedSettings]


def _stored_identifiers(monkeypatch):
	"""Every identifier WorldVoice defines and stores: (where, name)."""
	names = []
	for section, values in worldvoice_conf()["WorldVoice"].items():
		names.append(("nvda.ini [WorldVoice]", section))
		if section not in DATA_SECTIONS:
			names += [(f"nvda.ini [WorldVoice][{section}]", key) for key in values]
	names += [("nvda.ini [WorldVoice][voices][<voice>]", name) for name in _voice_parameter_names()]
	names += [("driver setting id", setting_id) for setting_id in _driver_setting_ids(monkeypatch)]
	for file in sorted(ADDON.rglob("*.py")):
		path = file.relative_to(ADDON).as_posix()
		if layer(path) != "host":
			continue
		for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
			if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("script_"):
				names.append((f"gestures.ini script in {path}", node.name.removeprefix("script_")))
	return names


def _voice_parameter_names():
	"""The keys of each voice's section: the names of runtime/voiceSettings.VOICE_PARAMETERS."""
	source = (ADDON / SYNTH / "runtime/voiceSettings.py").read_text(encoding="utf-8")
	for node in ast.parse(source).body:
		if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "VOICE_PARAMETERS":
			return [ast.literal_eval(row.elts[0]) for row in node.value.elts]
	raise LookupError("runtime/voiceSettings.py assigns no VOICE_PARAMETERS")


def test_stored_identifiers_use_nvda_camel_case(monkeypatch):
	assert stored_identifier_violations(_stored_identifiers(monkeypatch)) == []


def test_the_stored_identifier_check_reports_other_spellings():
	names = [("x", "DetectLanguageTiming"), ("x", "number_mode"), ("x", "numberMode")]
	assert stored_identifier_violations(names) == ["x: DetectLanguageTiming", "x: number_mode"]


def test_data_sections_hold_no_defined_keys():
	# The confspec gives these sections only __many__ (or nothing): every key in them is a name.
	conf = worldvoice_conf()["WorldVoice"]
	assert [section for section in DATA_SECTIONS if conf[section] != {}] == []


def test_nvda_setting_ids_are_nvdas(monkeypatch):
	# The synth's settings are NVDA's ids, its own uwv, and the pipeline table's driver ids; each voice
	# stores NVDA's ids too. Every one of NVDA's is a setting id in NVDA's own SynthDriver.
	_synth_class, settings = load_synth(monkeypatch, worldvoice_conf())
	table_ids = {spec.driver_id for spec in settings.PIPELINE_SETTINGS if spec.driver_id}
	assert set(_driver_setting_ids(monkeypatch)) - table_ids - {"uwv"} == NVDA_SETTING_IDS
	assert set(_voice_parameter_names()) <= NVDA_SETTING_IDS
	nvda = (REF / "nvda/source/synthDriverHandler.py").read_text(encoding="utf-8")
	assert [name for name in sorted(NVDA_SETTING_IDS) if f'"{name}"' not in nvda] == []


CORE_MODULE = SYNTH + "voices/example.py"
HOST_MODULE = SYNTH + "bridge/example.py"


@pytest.mark.parametrize(
	("path", "source", "expected"),
	[
		(CORE_MODULE, "def getVoice():\n\tpass\n", ["getVoice"]),
		(CORE_MODULE, "def get_voice(voiceName):\n\tpass\n", ["get_voice.<locals>.voiceName"]),
		(CORE_MODULE, "class Spec:\n\tvoiceName: str\n", ["Spec.voiceName"]),
		(CORE_MODULE, "class Spec:\n\tdef __init__(self):\n\t\tself.voiceName = 1\n", ["Spec.voiceName"]),
		(CORE_MODULE, "def run():\n\tfor voiceName in ():\n\t\tpass\n", ["run.<locals>.voiceName"]),
		(CORE_MODULE, "speak = lambda speechSequence: None\n", ["speechSequence"]),
		(CORE_MODULE, "def run():\n\tdef innerStep():\n\t\tpass\n", ["run.<locals>.innerStep"]),
		(
			CORE_MODULE,
			"def run(items):\n\tif itemCount := len(items):\n\t\tpass\n",
			["run.<locals>.itemCount"],
		),
		(CORE_MODULE, "def run():\n\tglobal lastValue\n\tlastValue = 1\n", ["lastValue"]),
		(
			CORE_MODULE,
			(
				"def run(value):\n\tmatch value:\n\t\tcase [firstItem, *otherItems]:\n\t\t\tpass\n"
				"\t\tcase {**allItems}:\n\t\t\tpass\n"
			),
			["run.<locals>.firstItem", "run.<locals>.otherItems", "run.<locals>.allItems"],
		),
		(
			CORE_MODULE,
			"class Spec:\n\t@classmethod\n\tdef build(cls):\n\t\tcls.lastSpec = None\n",
			["Spec.lastSpec"],
		),
		(
			CORE_MODULE,
			"MAX_RATE = 1\nVoiceKey = str\n\n\nclass VoiceSpec:\n\tdef __repr__(self):\n\t\tpass\n",
			[],
		),
		(HOST_MODULE, "def get_voice():\n\tpass\n", ["get_voice"]),
		(HOST_MODULE, "class Panel:\n\tdef _get_rateBoost(self):\n\t\tpass\n", []),
		(HOST_MODULE, "class Plugin:\n\tdef script_toggle(self, gesture):\n\t\tpass\n", []),
		(
			HOST_MODULE,
			"class Bridge:\n\tdef __init__(self, getSynth):\n\t\tself._get_synth = getSynth\n",
			["Bridge._get_synth"],
		),
		(HOST_MODULE, "def run():\n\tscript_name = 1\n", ["run.<locals>.script_name"]),
		(
			HOST_MODULE,
			"import wx\n\n\nclass Panel(wx.Panel):\n\tdef Destroy(self):\n\t\tpass\n",
			["Panel.Destroy"],
		),
	],
)
def test_the_guard_reads_each_kind_of_name(path, source, expected):
	assert [qualname for _path, qualname in violations(_Index({path: source}))] == expected


def test_the_guard_lets_an_override_keep_the_base_name():
	sources = {
		SYNTH
		+ "runtime/port.py": "class Port:\n\tdef speak_segment(self, segment_id):\n\t\tself.last_id = 0\n",
		HOST_MODULE: (
			"from ..runtime.port import Port\n\n\n"
			"class Adapter(Port):\n"
			"\tdef speak_segment(self, segment_id):\n\t\tself.last_id = segment_id\n\n"
			"\tdef own_name(self):\n\t\tpass\n"
		),
	}
	assert [qualname for _path, qualname in violations(_Index(sources))] == ["Adapter.own_name"]


def test_the_guard_flags_an_override_parameter_the_base_lacks():
	# An override mirrors the parameters of the base method; one the base lacks is the class's own.
	sources = {
		SYNTH + "runtime/port.py": "class Port:\n\tdef speak_segment(self, segment_id):\n\t\tpass\n",
		HOST_MODULE: (
			"from ..runtime.port import Port\n\n\n"
			"class Adapter(Port):\n"
			"\tdef speak_segment(self, segment_id, extra_flag=None):\n\t\tpass\n"
		),
	}
	found = violations(_Index(sources))
	assert [qualname for _path, qualname in found] == ["Adapter.speak_segment.<locals>.extra_flag"]


def test_the_guard_follows_a_base_imported_under_an_alias():
	# The wrappers import driver.Voice as BaseVoice; their contract overrides stay exempt only if the
	# guard resolves the alias to the class it names.
	sources = {
		SYNTH + "runtime/port.py": "class Port:\n\tdef speak_segment(self, segment_id):\n\t\tpass\n",
		HOST_MODULE: (
			"from ..runtime.port import Port as BasePort\n\n\n"
			"class Port(BasePort):\n"
			"\tdef speak_segment(self, segment_id):\n\t\tpass\n\n"
			"\tdef own_name(self):\n\t\tpass\n"
		),
	}
	assert [qualname for _path, qualname in violations(_Index(sources))] == ["Port.own_name"]


def test_the_guard_reads_the_imported_base_of_a_class_with_its_name():
	# class SynthDriver(SynthDriver) derives from the imported class, not from itself.
	source = (
		"from synthDriverHandler import SynthDriver\n\n\n"
		"class SynthDriver(SynthDriver):\n"
		"\tdef own_name(self):\n\t\tpass\n"
	)
	found = violations(_Index({HOST_MODULE: source}))
	assert [qualname for _path, qualname in found] == ["SynthDriver.own_name"]
