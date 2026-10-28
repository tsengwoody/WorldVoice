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
	"""Every attribute the wrapper reads through the NVDA module object called alias."""
	return {
		n.attr
		for n in ast.walk(tree)
		if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == alias
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
	nvda = NVDA_SAPI5.read_text(encoding="utf-8")
	# Whole words: `_thread` must not pass on `_threadCond` alone.
	assert [name for name in privates if not re.search(rf"\b{re.escape(name)}\b", nvda)] == []
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
	parents = INNER_ONECORE.read_text(encoding="utf-8") + NVDA_ONECORE.read_text(encoding="utf-8")
	assert all(re.search(rf"\b{re.escape(name)}\b", parents) for name in privates)
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
	# "original driver" branch, and the bridge always passes the cancellation token.
	source = (ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8")
	assert "_guardInstalled" not in source
	tree = ast.parse(source)
	synth = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SynthDriver")
	assert any(
		isinstance(item, ast.Assign)
		and [ast.unparse(t) for t in item.targets] == ["supportsCancellationToken"]
		and isinstance(item.value, ast.Constant)
		and item.value.value is True
		for item in synth.body
	)


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
