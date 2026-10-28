"""Every engine strategy is a NativeStrategy, and the host never probes for hooks."""

import ast
import re
from pathlib import Path

import pytest
from addon_loader import REF

ROOT = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"
ENGINES = ("Espeak", "SAPI5", "RHVoice", "OneCore", "VE", "Cerence")


def test_every_strategy_subclasses_native_strategy():
	for engine in ENGINES:
		tree = ast.parse((ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
		strategies = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name.endswith("Strategy")]
		assert strategies, engine
		for node in strategies:
			assert [ast.unparse(base) for base in node.bases] == ["NativeStrategy"], (engine, node.name)


def test_espeak_touches_nvda_privates_only_through_its_port():
	tree = ast.parse((ROOT / "driver/Espeak/__init__.py").read_text(encoding="utf-8"))
	port = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_EspeakPort")
	inside = {id(node) for node in ast.walk(port)}
	outside = [
		node.lineno
		for node in ast.walk(tree)
		if isinstance(node, ast.Attribute)
		and isinstance(node.value, ast.Name)
		and node.value.id == "_espeak"
		and id(node) not in inside
	]
	assert outside == []


NVDA_ESPEAK = REF / "nvda/source/synthDrivers/espeak.py"


def test_espeak_nvda_names_are_listed_and_exist_in_nvda():
	tree = ast.parse((ROOT / "driver/Espeak/__init__.py").read_text(encoding="utf-8"))
	module_names = _class_constant(tree, "_EspeakPort", "NVDA_MODULE_NAMES")
	assert module_names == _module_reads(tree, "_espeak")
	assert module_names == {"EE_OK", "_execWhenDone", "espeakDLL", "isSpeaking", "onIndexReached", "player"}
	assert _class_constant(tree, "_EspeakPort", "NVDA_PRIVATES") == set()
	nvda = NVDA_ESPEAK.read_text(encoding="utf-8")
	synth = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SynthDriver")
	overridden = {
		n.name
		for n in synth.body
		if isinstance(n, ast.FunctionDef)
		and n.name.startswith("_")
		and not n.name.startswith("__")
		and f"def {n.name}(" in nvda
	}
	assert overridden == _class_constant(tree, "_EspeakPort", "NVDA_OVERRIDES") == {"_onIndexReached"}


@pytest.mark.parametrize("engine", ["Espeak", "RHVoice"])
def test_drain_support_requires_keywords(engine):
	tree = ast.parse((ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
	method = next(
		n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "get_segment_drain_support"
	)
	assert [a.arg for a in method.args.kwonlyargs] == ["nvda_version", "audio_mode"]
	assert method.args.kw_defaults == [None, None]


NVDA_SAPI5 = REF / "nvda/source/synthDrivers/sapi5.py"


def _sapi5_tree():
	return ast.parse((ROOT / "driver/SAPI5/__init__.py").read_text(encoding="utf-8"))


def _class_constant(tree, class_name, constant):
	node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
	assign = next(
		n
		for n in node.body
		if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == constant for t in n.targets)
	)
	return set(ast.literal_eval(assign.value.args[0])) if assign.value.args else set()


def _module_reads(tree, alias):
	"""Every attribute the wrapper reads through the NVDA module object called alias.

	SAPI5's _nvdaBase("X") reads sapi5.X by name.
	"""
	return {
		n.attr
		for n in ast.walk(tree)
		if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == alias
	} | {
		n.args[0].value
		for n in ast.walk(tree)
		if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_nvdaBase"
	}


def test_sapi5_nvda_privates_are_listed_and_exist_in_nvda():
	tree = _sapi5_tree()
	privates = _class_constant(tree, "_Sapi5Port", "NVDA_PRIVATES")
	overrides = _class_constant(tree, "_Sapi5Port", "NVDA_OVERRIDES")
	assert _class_constant(tree, "_Sapi5Port", "NVDA_MODULE_NAMES") == _module_reads(tree, "sapi5")
	own = set()
	for node in tree.body:
		if isinstance(node, ast.ClassDef):
			for item in node.body:
				if isinstance(item, ast.FunctionDef):
					own.add(item.name)
					if item.name == "__init__":
						own |= {
							n.attr
							for n in ast.walk(item)
							if isinstance(n, ast.Attribute)
							and isinstance(n.ctx, ast.Store)
							and isinstance(n.value, ast.Name)
							and n.value.id == "self"
						}
	# Attributes set up by our own runtime base classes are not NVDA's.
	host_tree = ast.parse((ROOT / "runtime/segmentHost.py").read_text(encoding="utf-8"))
	leased = next(n for n in host_tree.body if isinstance(n, ast.ClassDef) and n.name == "LeasedPlayer")
	own |= {item.name for item in leased.body if isinstance(item, ast.FunctionDef)}
	own |= {
		n.attr
		for n in ast.walk(leased)
		if isinstance(n, ast.Attribute)
		and isinstance(n.ctx, ast.Store)
		and isinstance(n.value, ast.Name)
		and n.value.id == "self"
	}
	accessed = {
		n.attr
		for n in ast.walk(tree)
		if isinstance(n, ast.Attribute)
		and n.attr.startswith("_")
		and not n.attr.startswith("__")
		and isinstance(n.value, ast.Name)
		and n.value.id in {"self", "driver", "synth"}
	}
	assert accessed - own <= privates
	# Existence on every supported NVDA: tests/test_nvda_release_names.py.
	nvda = NVDA_SAPI5.read_text(encoding="utf-8")
	synth = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SynthDriver")
	overridden = {
		n.name
		for n in synth.body
		if isinstance(n, ast.FunctionDef)
		and n.name.startswith("_")
		and not n.name.startswith("__")
		and f"def {n.name}(" in nvda
	}
	assert overridden == overrides


def test_sapi5_uses_the_shared_engine_controls():
	tree = _sapi5_tree()
	player = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_SegmentPlayer")
	assert [ast.unparse(base) for base in player.bases] == ["LeasedPlayer"]


INNER_RHVOICE = ROOT / "driver/RHVoice/driver/__init__.py"


def test_rhvoice_reaches_inner_privates_only_through_its_port():
	source = (ROOT / "driver/RHVoice/__init__.py").read_text(encoding="utf-8")
	tree = ast.parse(source)
	port = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_RHVoiceInner")
	port_source = ast.get_source_segment(source, port)
	assert "_SynthDriver__" not in source.replace(port_source, "")
	inner_source = INNER_RHVOICE.read_text(encoding="utf-8")
	# Only the inner SynthDriver mangles to _SynthDriver__; other classes reuse the same names.
	inner_class = next(
		n for n in ast.parse(inner_source).body if isinstance(n, ast.ClassDef) and n.name == "SynthDriver"
	)
	inner = ast.get_source_segment(inner_source, inner_class)
	for name in set(re.findall(r"_SynthDriver__(\w+)", port_source)):
		assert re.search(rf"self\.__{name}\b", inner), name


def test_rhvoice_uses_shared_player_and_stop_gate():
	source = (ROOT / "driver/RHVoice/__init__.py").read_text(encoding="utf-8")
	tree = ast.parse(source)
	player = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_WavePlayer")
	assert [ast.unparse(base) for base in player.bases] == ["LeasedPlayer"]


NVDA_ONECORE = REF / "nvda/source/synthDrivers/oneCore.py"
INNER_ONECORE = ROOT / "driver/OneCore/driver/__init__.py"


def _own_names(tree):
	own = set()
	for node in tree.body:
		if isinstance(node, ast.ClassDef):
			for item in node.body:
				if isinstance(item, ast.FunctionDef):
					own.add(item.name)
					if item.name == "__init__":
						own |= {
							n.attr
							for n in ast.walk(item)
							if isinstance(n, ast.Attribute)
							and isinstance(n.ctx, ast.Store)
							and isinstance(n.value, ast.Name)
							and n.value.id == "self"
						}
	return own


def test_onecore_parent_privates_are_listed_and_exist():
	tree = ast.parse((ROOT / "driver/OneCore/__init__.py").read_text(encoding="utf-8"))
	privates = _class_constant(tree, "_OneCorePort", "NVDA_PRIVATES")
	overrides = _class_constant(tree, "_OneCorePort", "NVDA_OVERRIDES")
	assert _class_constant(tree, "_OneCorePort", "NVDA_MODULE_NAMES") == _module_reads(tree, "oneCore")
	accessed = {
		n.attr
		for n in ast.walk(tree)
		if isinstance(n, ast.Attribute)
		and n.attr.startswith("_")
		and not n.attr.startswith("__")
		and isinstance(n.value, ast.Name)
		and n.value.id in {"self", "driver"}
	}
	assert accessed - _own_names(tree) <= privates
	# Existence on every supported NVDA: tests/test_nvda_release_names.py.
	parents = INNER_ONECORE.read_text(encoding="utf-8") + NVDA_ONECORE.read_text(encoding="utf-8")
	synth = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SynthDriver")
	overridden = {
		n.name
		for n in synth.body
		if isinstance(n, ast.FunctionDef)
		and n.name.startswith("_")
		and not n.name.startswith("__")
		and re.search(rf"def {n.name}\(", parents)
	}
	assert overridden == overrides


def test_onecore_uses_the_stop_gate_and_declares_voice_last():
	source = (ROOT / "driver/OneCore/__init__.py").read_text(encoding="utf-8")
	tree = ast.parse(source)
	names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
	assert names.count("Voice") == 1 and names.index("Voice") > names.index("SynthDriver")
	assert not any(
		isinstance(n, ast.Assign)
		and any(ast.unparse(t) in {"SynthDriver", "Voice.synthDriverClass"} for t in n.targets)
		for n in tree.body
	)


def _vocalizer_own_names(tree):
	own = _own_names(tree)
	for node in tree.body:
		if isinstance(node, ast.ClassDef):
			for item in node.body:
				if isinstance(item, ast.Assign):
					own |= {t.id for t in item.targets if isinstance(t, ast.Name)}
				if isinstance(item, ast.FunctionDef) and item.name == "_installGuard":
					own |= {
						n.attr
						for n in ast.walk(item)
						if isinstance(n, ast.Attribute)
						and isinstance(n.ctx, ast.Store)
						and isinstance(n.value, ast.Name)
						and n.value.id == "self"
					}
	return own


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_vocalizer_inner_privates_are_listed_and_exist(engine):
	tree = ast.parse((ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
	port = f"_{engine}Port"
	privates = _class_constant(tree, port, "INNER_PRIVATES")
	overrides = _class_constant(tree, port, "INNER_OVERRIDES")
	accessed = {
		n.attr
		for n in ast.walk(tree)
		if isinstance(n, ast.Attribute)
		and n.attr.startswith("_")
		and not n.attr.startswith("__")
		and isinstance(n.value, ast.Name)
	}
	assert accessed - _vocalizer_own_names(tree) <= privates
	inner = "".join(
		p.read_text(encoding="utf-8") for p in (ROOT / "driver" / engine / "driver").rglob("*.py")
	)
	assert all(re.search(rf"\b{re.escape(name)}\b", inner) for name in privates)
	synth = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SynthDriver")
	overridden = {
		n.name
		for n in synth.body
		if isinstance(n, ast.FunctionDef)
		and n.name.startswith("_")
		and not n.name.startswith("__")
		and re.search(rf"def {n.name}\(", inner)
	}
	assert overridden == overrides


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_vocalizer_wrapper_has_no_guard_fallback(engine):
	# The vendored inner is pinned above, so the guard always installs: no flag, no
	# "original driver" branch, and token support is a fixed trait declared on the Voice
	# (phase 52), not a claim of the core.
	source = (ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8")
	assert "_guardInstalled" not in source
	assert "supportsCancellationToken" not in source
	tree = ast.parse(source)
	voice = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Voice")
	assert _class_constant(tree, "Voice", "extraCapabilities") == {
		"waitfactor",
		"variant",
		"cancellationToken",
	}, voice.name


def test_every_wrapper_core_declares_the_segment_drain_entries():
	# The bridge looks both entries up by name; the base makes them one interface, and it comes
	# last so it never shadows an implementation from another base.
	for engine in ENGINES:
		tree = ast.parse((ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
		synth = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SynthDriver")
		assert ast.unparse(synth.bases[-1]) == "SegmentDrainCore", engine
		own = {n.name for n in synth.body if isinstance(n, ast.FunctionDef)}
		assert {"speak_segment", "get_segment_drain_support"} <= own, engine


def test_wrappers_do_not_shadow_their_bases():
	# class Voice(Voice) or class SynthDriver(SynthDriver) hides which class is the base; the
	# modules import their bases under their own names (BaseVoice, BaseSynthDriver).
	paths = [ROOT / "driver" / engine / "__init__.py" for engine in ENGINES] + [ROOT / "__init__.py"]
	shadowing = [
		f"{path.relative_to(ROOT)}:{node.lineno} {node.name}"
		for path in paths
		for node in ast.parse(path.read_text(encoding="utf-8")).body
		if isinstance(node, ast.ClassDef)
		and any(isinstance(base, ast.Name) and base.id == node.name for base in node.bases)
	]
	assert shadowing == []


NVDA_MODULE_ALIASES = {"Espeak": "_espeak", "SAPI5": "sapi5", "OneCore": "oneCore"}


def _import_time_nodes(node):
	"""The nodes Python evaluates when the module loads: not function or lambda bodies."""
	yield node
	if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
		children = [*node.decorator_list, node.args, *([node.returns] if node.returns else [])]
	elif isinstance(node, ast.Lambda):
		children = [node.args]
	else:
		children = list(ast.iter_child_nodes(node))
	for child in children:
		yield from _import_time_nodes(child)


def test_wrappers_read_no_nvda_module_attribute_at_import():
	# Voice.ready() can only report a missing NVDA name if the wrapper module imports first.
	found = []
	for engine, alias in NVDA_MODULE_ALIASES.items():
		tree = ast.parse((ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
		found += [
			f"{engine}:{n.lineno} {alias}.{n.attr}"
			for n in _import_time_nodes(tree)
			if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == alias
		]
		# from synthDrivers.sapi5 import X reads sapi5.X at import too; only the synth class itself,
		# which every NVDA release has, may be imported that way.
		found += [
			f"{engine}:{n.lineno} from {n.module} import {name.name}"
			for n in _import_time_nodes(tree)
			if isinstance(n, ast.ImportFrom)
			and n.level == 0
			and (n.module or "").startswith("synthDrivers.")
			and not n.module.startswith("synthDrivers.WorldVoice")
			for name in n.names
			if name.name != "SynthDriver"
		]
	assert found == []
	tree = _sapi5_tree()
	bases = {
		n.name: [ast.unparse(base) for base in n.bases]
		for n in tree.body
		if isinstance(n, ast.ClassDef) and n.name in {"_SegmentAudioStream", "_SegmentSapiSink"}
	}
	assert bases == {
		"_SegmentAudioStream": ["_nvdaBase('SynthDriverAudioStream')"],
		"_SegmentSapiSink": ["_nvdaBase('SapiSink')"],
	}


# Barrier names (phase 52). A barrier of a shared kind is named by its runtime/barriers.py
# constant; these are the only engine-specific names, each because its evidence proves
# something no shared kind describes (docs/superpowers/specs/2026-10-28-phase52-shared-barriers-design.md §3.2).
ENGINE_SPECIFIC_BARRIERS = {
	"Espeak": set(),
	"SAPI5": {"processed"},  # post-EndStream worker processing; SAPI5 speaks asynchronously
	"RHVoice": {"message"},  # RHVoice_new_message succeeded: a precondition, not completion
	"OneCore": {"callback", "synced"},  # async delivery callback fed all audio; sync() is not idle()
	"VE": set(),
	"Cerence": set(),
}
# Each strategy's declared set and its ordinary set (None: ordinary records take the strategy's).
DECLARED_BARRIERS = {
	"Espeak": ({"SYNTHESIZED", "ENGINE_DONE", "PLAYED_OUT"}, None),
	"RHVoice": ({"message", "ENGINE_DONE", "SYNTHESIZED", "PLAYED_OUT"}, None),
	"SAPI5": ({"ENGINE_DONE", "processed", "PLAYED_OUT"}, {"ENGINE_DONE", "processed"}),
	"OneCore": ({"callback", "synced"}, {"callback"}),
	"VE": ({"SYNTHESIZED", "PLAYED_OUT"}, set()),
	"Cerence": ({"SYNTHESIZED", "PLAYED_OUT"}, set()),
}


def _shared_barriers():
	tree = ast.parse((ROOT / "runtime/barriers.py").read_text(encoding="utf-8"))
	return {
		node.targets[0].id: node.value.value
		for node in tree.body
		if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
	}


def _frozenset_elements(call):
	assert isinstance(call, ast.Call) and ast.unparse(call.func) == "frozenset", ast.unparse(call)
	if not call.args:
		return []
	assert isinstance(call.args[0], ast.Set), ast.unparse(call)
	return list(call.args[0].elts)


def _barrier_label(node):
	return node.id if isinstance(node, ast.Name) else node.value


def _declared_barriers(tree):
	strategy = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name.endswith("Strategy"))
	declared = next(
		n.value
		for n in strategy.body
		if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["barriers"]
	)
	ordinary = next(
		(
			n.value
			for n in tree.body
			if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["_ORDINARY_BARRIERS"]
		),
		None,
	)
	return _frozenset_elements(declared), None if ordinary is None else _frozenset_elements(ordinary)


def _barrier_expressions(tree):
	"""Every expression the wrapper uses as a barrier name, wherever it declares, reaches or reads one."""
	declared, ordinary = _declared_barriers(tree)
	found = declared + (ordinary or [])
	for node in ast.walk(tree):
		if isinstance(node, ast.Call):
			if isinstance(node.func, ast.Attribute) and node.func.attr == "reach":
				found.append(node.args[1])
			if (
				isinstance(node.func, ast.Attribute)
				and node.func.attr == "get"
				and isinstance(node.func.value, ast.Attribute)
				and node.func.value.attr == "barriers"
			):
				found.append(node.args[0])
			for keyword in node.keywords:
				if keyword.arg == "idle_barrier" and not (
					isinstance(keyword.value, ast.Constant) and keyword.value.value is None
				):
					found.append(keyword.value)
				if keyword.arg == "barriers":
					# Ordinary speech passes its set by name; a literal set would bypass the table.
					assert ast.unparse(keyword.value) == "_ORDINARY_BARRIERS", ast.unparse(node)
		elif isinstance(node, ast.Subscript):
			if isinstance(node.value, ast.Attribute) and node.value.attr == "barriers":
				found.append(node.slice)
		elif isinstance(node, ast.Compare):
			for op, right in zip(node.ops, node.comparators, strict=True):
				if (
					isinstance(op, ast.In | ast.NotIn)
					and isinstance(right, ast.Attribute)
					and right.attr == "barriers"
				):
					found.append(node.left)
	return found


def _barrier_imports(tree):
	return {
		alias.name
		for node in tree.body
		if isinstance(node, ast.ImportFrom) and node.module == "runtime.barriers" and node.level == 3
		for alias in node.names
	}


@pytest.mark.parametrize("engine", ENGINES)
def test_strategy_barriers_use_shared_or_listed_names(engine):
	tree = ast.parse((ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
	shared, imported = _shared_barriers(), _barrier_imports(tree)
	assert imported <= set(shared), (engine, imported)
	for node in _barrier_expressions(tree):
		if isinstance(node, ast.Name):
			assert node.id in imported, (engine, node.id, node.lineno)
		else:
			assert isinstance(node, ast.Constant), (engine, ast.unparse(node), node.lineno)
			assert node.value in ENGINE_SPECIFIC_BARRIERS[engine], (engine, node.value, node.lineno)
	declared, ordinary = _declared_barriers(tree)
	expected_declared, expected_ordinary = DECLARED_BARRIERS[engine]
	assert {_barrier_label(node) for node in declared} == expected_declared
	assert len(declared) == len(expected_declared)
	assert (None if ordinary is None else {_barrier_label(node) for node in ordinary}) == expected_ordinary


def test_engine_specific_barrier_names_are_used_and_not_shared():
	shared_values = set(_shared_barriers().values())
	for engine, names in ENGINE_SPECIFIC_BARRIERS.items():
		assert not names & shared_values, engine
		tree = ast.parse((ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
		used = {node.value for node in _barrier_expressions(tree) if isinstance(node, ast.Constant)}
		assert used == names, engine


def test_leased_player_reaches_played_out_by_default():
	host_tree = ast.parse((ROOT / "runtime/segmentHost.py").read_text(encoding="utf-8"))
	leased = next(n for n in host_tree.body if isinstance(n, ast.ClassDef) and n.name == "LeasedPlayer")
	init = next(n for n in leased.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
	defaults = dict(zip((a.arg for a in init.args.kwonlyargs), init.args.kw_defaults, strict=True))
	assert ast.unparse(defaults["idle_barrier"]) == "PLAYED_OUT"
	assert "from .barriers import PLAYED_OUT" in ast.unparse(host_tree)


def _voice_extra_capabilities(tree):
	voice = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Voice")
	assigned = [
		n.value
		for n in voice.body
		if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["extraCapabilities"]
	]
	return {_barrier_label(node) for node in _frozenset_elements(assigned[0])} if assigned else set()


def _voice_reassigns_core_class(tree):
	voice = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Voice")
	targets = [
		target
		for node in ast.walk(voice)
		if isinstance(node, ast.Assign)
		for assigned in node.targets
		for target in (assigned.elts if isinstance(assigned, ast.Tuple) else [assigned])
	]
	return any(isinstance(t, ast.Attribute) and t.attr == "synthDriverClass" for t in targets)


@pytest.mark.parametrize("engine", ENGINES)
def test_a_token_capability_needs_a_fixed_core_that_takes_the_token(engine):
	# The bridge passes speak(commands, cancellationToken=token) on the Voice's word alone, so
	# the core class must be fixed and take the keyword. SAPI5 swaps in NVDA's own driver before
	# NVDA 2025.3, whose speak(speechSequence) would raise TypeError on a token.
	tree = ast.parse((ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
	declared = "cancellationToken" in _voice_extra_capabilities(tree)
	assert declared is (engine in {"VE", "Cerence"})
	if _voice_reassigns_core_class(tree):
		assert not declared
	if declared:
		assert not _voice_reassigns_core_class(tree)
		synth = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SynthDriver")
		speak = next(n for n in synth.body if isinstance(n, ast.FunctionDef) and n.name == "speak")
		assert "cancellationToken" in {a.arg for a in speak.args.args + speak.args.kwonlyargs}
