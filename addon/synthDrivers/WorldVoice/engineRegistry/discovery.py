from __future__ import annotations

import importlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..bringup import timed

MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class EngineSpec:
	name: str
	label: str
	source: str
	module_name: str
	import_root: str
	default_enabled: bool


# Callers that pass no logger report through stdlib logging, which NVDA routes to its log.
_LOG = logging.getLogger(__name__)

# driver.Voice contract names before phase 47c renamed them to NVDA mixedCase (refactor9 6.1), with
# their new names. A plugin that still has one was built for an older WorldVoice: its core cannot be
# created, or its drain profile or capabilities would be silently ignored, so it is skipped.
# Decided by the user (2026-10-28): the one exception is synth_driver_class alone, the only name the
# Neural, IBM and AISound plugins use; it is mapped onto synthDriverClass with a warning.
MAPPED_CONTRACT_NAME = "synth_driver_class"
PRE_RENAME_CONTRACT_NAMES = {
	"synth_driver_class": "synthDriverClass",
	"extra_capabilities": "extraCapabilities",
	"drain_profile": "drainProfile",
	"create_core": "createCore",
	"destroy_core": "destroyCore",
	"update_settings": "updateSettings",
}


def coerce_bool(value: Any) -> bool:
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
	logger = logger or _LOG
	try:
		data = json.loads(path.read_text(encoding="utf-8"))
	except Exception as error:  # noqa: BLE001 - a broken manifest skips that engine with a warning
		logger.warning(
			"Skipping %s engine candidate: invalid manifest (%s)",
			path.parent.name,
			error,
		)
		return None
	if not isinstance(data, dict):
		logger.warning(
			"Skipping %s engine candidate: manifest must be a JSON object",
			path.parent.name,
		)
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
		default_enabled=coerce_bool(default_enabled),
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
	logger = logger or _LOG
	specs: list[EngineSpec] = []
	internal_root_path = Path(internal_root)
	external_root_path = Path(external_root)
	internal_import_root = _get_internal_import_root(internal_root_path, internal_package)

	for name, manifest_path, source in _iter_internal_candidates(internal_root_path):
		if not manifest_path.is_file():
			logger.debug("Skipping %s engine candidate: manifest missing", name)
			continue
		manifest = _load_manifest(manifest_path, logger=logger)
		if manifest is None:
			continue
		specs.append(
			_build_engine_spec(name, source, f"{internal_package}.{name}", internal_import_root, manifest),
		)

	for name, manifest_path, source in _iter_external_candidates(external_root_path):
		if not manifest_path.is_file():
			logger.debug("Skipping %s engine candidate: manifest missing", name)
			continue
		manifest = _load_manifest(manifest_path, logger=logger)
		if manifest is None:
			continue
		specs.append(_build_engine_spec(name, source, name, str(manifest_path.parent.parent), manifest))

	return specs


def _pre_rename_contract_names(voice: Any) -> list[str]:
	"""The pre-rename contract names voice defines or inherits, in the table's order."""
	return [name for name in PRE_RENAME_CONTRACT_NAMES if hasattr(voice, name)]


def load_enabled_engine_classes(
	engine_specs: list[EngineSpec],
	engine_config: dict[str, Any],
	logger: Any = None,
) -> dict[str, type]:
	logger = logger or _LOG
	ready: dict[str, type] = {}
	for spec in engine_specs:
		if not get_engine_enabled(engine_config, spec):
			continue
		with timed(logger, f"ready check {spec.name} total"):
			try:
				with timed(logger, f"ready check {spec.name} module import"):
					module = _load_module(spec.module_name, spec.import_root)
				with timed(logger, f"ready check {spec.name} Voice lookup"):
					voice = getattr(module, "Voice", None)
				if voice is None:
					logger.warning("Skipping %s engine candidate: Voice export missing", spec.name)
					continue
				voice_engine = getattr(voice, "engine", None)
				if voice_engine is not None and voice_engine != spec.name:
					logger.warning(
						"Skipping %s engine candidate: Voice.engine mismatch (%s)",
						spec.name,
						voice_engine,
					)
					continue
				stale = _pre_rename_contract_names(voice)
				# A workspace engine is a plugin its author updates; a bundled one is WorldVoice's own.
				owner, remedy = (
					("plugin", "update the plugin")
					if spec.source == "external"
					else ("bundled engine", "update WorldVoice")
				)
				if stale == [MAPPED_CONTRACT_NAME]:
					new_name = PRE_RENAME_CONTRACT_NAMES[MAPPED_CONTRACT_NAME]
					# A plugin that also sets the new name supports both contracts; the new one wins.
					if not getattr(voice, new_name, None):
						setattr(voice, new_name, getattr(voice, MAPPED_CONTRACT_NAME))
						logger.warning(
							"Mapping %s engine candidate's pre-rename contract name %s onto %s for now; %s",
							spec.name,
							MAPPED_CONTRACT_NAME,
							new_name,
							remedy,
						)
					stale = []
				if stale:
					logger.error(
						"Skipping %s engine candidate: %s uses the pre-rename contract name(s) %s; %s",
						spec.name,
						owner,
						", ".join(f"{name} (now {PRE_RENAME_CONTRACT_NAMES[name]})" for name in stale),
						remedy,
					)
					continue
				with timed(logger, f"ready check {spec.name} voice.ready"):
					is_ready = voice.ready()
				if not is_ready:
					continue
				ready[spec.name] = voice
			except Exception as error:  # noqa: BLE001 - one engine failing to load is logged and skipped
				logger.error("Failed to load ready state for %s: %s", spec.name, error)
	return ready


def get_engine_enabled(engine_config: dict[str, Any], engine_spec: EngineSpec) -> bool:
	if engine_spec.name not in engine_config:
		return engine_spec.default_enabled
	value = engine_config[engine_spec.name]
	return coerce_bool(value)
