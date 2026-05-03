from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class EngineSpec:
	name: str
	label: str
	source: str
	module_name: str
	import_root: str
	default_enabled: bool


def _log(logger: Any, method: str, message: str, *args):
	if logger is None:
		return
	log_method = getattr(logger, method, None)
	if log_method is None:
		return
	log_method(message, *args)


def _coerce_bool(value: Any) -> bool:
	if isinstance(value, str):
		return value.lower() not in {"false", "0", ""}
	return bool(value)


def _iter_internal_candidates(internal_root: Path):
	if not internal_root.is_dir():
		return
	for child in sorted(internal_root.iterdir(), key=lambda item: item.name):
		package_init = child / "__init__.py"
		manifest = child / MANIFEST_FILENAME
		if not child.is_dir() or not package_init.is_file():
			continue
		yield child.name, manifest, "internal"


def _iter_external_candidates(external_root: Path):
	if not external_root.is_dir():
		return
	for child in sorted(external_root.iterdir(), key=lambda item: item.name):
		package_dir = child / child.name
		package_init = package_dir / "__init__.py"
		manifest = package_dir / MANIFEST_FILENAME
		if not child.is_dir() or not package_init.is_file():
			continue
		yield child.name, manifest, "external"


def _load_manifest(path: Path, logger: Any = None) -> dict[str, Any] | None:
	if not path.is_file():
		return None
	try:
		data = json.loads(path.read_text(encoding="utf-8"))
	except Exception as error:  # noqa: BLE001
		_log(logger, "warning", "Skipping %s engine candidate: invalid manifest (%s)", path.parent.name, error)
		return None
	if not isinstance(data, dict):
		_log(logger, "warning", "Skipping %s engine candidate: manifest must be a JSON object", path.parent.name)
		return None
	return data


def _build_engine_spec(name: str, source: str, module_name: str, import_root: str, manifest: dict[str, Any]):
	label = manifest.get("label", name)
	default_enabled = manifest.get("defaultEnabled")
	if default_enabled is None:
		default_enabled = source == "internal"
	return EngineSpec(
		name=name,
		label=str(label) if label else name,
		source=source,
		module_name=module_name,
		import_root=import_root,
		default_enabled=_coerce_bool(default_enabled),
	)


def _get_internal_import_root(internal_root: Path, internal_package: str) -> str:
	return str(internal_root.parents[len(internal_package.split(".")) - 1])


def _load_module(module_name: str, import_root: str):
	if import_root not in sys.path:
		sys.path.insert(0, import_root)
	return importlib.import_module(module_name)


def discover_engine_specs(
	internal_root: str | os.PathLike[str],
	internal_package: str,
	external_root: str | os.PathLike[str],
	logger: Any = None,
) -> list[EngineSpec]:
	specs: list[EngineSpec] = []
	internal_root_path = Path(internal_root)
	external_root_path = Path(external_root)
	internal_import_root = _get_internal_import_root(internal_root_path, internal_package)

	for name, manifest_path, source in _iter_internal_candidates(internal_root_path):
		if not manifest_path.is_file():
			_log(logger, "debug", "Skipping %s engine candidate: manifest missing", name)
			continue
		manifest = _load_manifest(manifest_path, logger=logger)
		if manifest is None:
			continue
		specs.append(_build_engine_spec(name, source, f"{internal_package}.{name}", internal_import_root, manifest))

	for name, manifest_path, source in _iter_external_candidates(external_root_path):
		if not manifest_path.is_file():
			_log(logger, "debug", "Skipping %s engine candidate: manifest missing", name)
			continue
		manifest = _load_manifest(manifest_path, logger=logger)
		if manifest is None:
			continue
		specs.append(_build_engine_spec(name, source, name, str(manifest_path.parent.parent), manifest))

	return specs


def load_enabled_engine_classes(
	engine_specs: list[EngineSpec],
	engine_config: dict[str, Any],
	logger: Any = None,
) -> dict[str, type]:
	ready: dict[str, type] = {}
	for spec in engine_specs:
		if not get_engine_enabled(engine_config, spec):
			continue
		engine_start = time.perf_counter()
		try:
			step_start = time.perf_counter()
			try:
				module = _load_module(spec.module_name, spec.import_root)
			finally:
				_log(
					logger,
					"debug",
					"WorldVoice init timing: ready check %s module import %.3fs",
					spec.name,
					time.perf_counter() - step_start,
				)
			step_start = time.perf_counter()
			voice = getattr(module, "Voice", None)
			_log(
				logger,
				"debug",
				"WorldVoice init timing: ready check %s Voice lookup %.3fs",
				spec.name,
				time.perf_counter() - step_start,
			)
			if voice is None:
				_log(logger, "warning", "Skipping %s engine candidate: Voice export missing", spec.name)
				continue
			voice_engine = getattr(voice, "engine", None)
			if voice_engine is not None and voice_engine != spec.name:
				_log(logger, "warning", "Skipping %s engine candidate: Voice.engine mismatch (%s)", spec.name, voice_engine)
				continue
			step_start = time.perf_counter()
			try:
				is_ready = voice.ready()
			finally:
				_log(
					logger,
					"debug",
					"WorldVoice init timing: ready check %s voice.ready %.3fs",
					spec.name,
					time.perf_counter() - step_start,
				)
			if not is_ready:
				continue
			ready[spec.name] = voice
		except Exception as error:  # noqa: BLE001
			_log(logger, "error", "Failed to load ready state for %s: %s", spec.name, error)
		finally:
			_log(
				logger,
				"debug",
				"WorldVoice init timing: ready check %s total %.3fs",
				spec.name,
				time.perf_counter() - engine_start,
			)
	return ready


def get_engine_enabled(engine_config: dict[str, Any], engine_spec: EngineSpec) -> bool:
	if engine_spec.name not in engine_config:
		return engine_spec.default_enabled
	value = engine_config[engine_spec.name]
	return _coerce_bool(value)
