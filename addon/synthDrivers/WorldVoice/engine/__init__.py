import os

import addonHandler
from logHandler import log

from .discovery import (
	discover_engine_specs,
	get_engine_enabled as _get_engine_enabled,
	load_enabled_engine_classes,
)

addonHandler.initTranslation()

PACKAGE_ROOT = os.path.dirname(os.path.dirname(__file__))
# PACKAGE_ROOT is .../addons/WorldVoice/synthDrivers/WorldVoice, so climb four levels
# to get back to NVDA's config path where WorldVoice-workspace lives.
user_folder = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(PACKAGE_ROOT))))
WVW_PATH = os.path.join(user_folder, "WorldVoice-workspace")

INTERNAL_DRIVER_ROOT = os.path.join(PACKAGE_ROOT, "driver")
INTERNAL_DRIVER_PACKAGE = f"{__package__.rsplit('.', 1)[0]}.driver"

ENGINE_SPECS = tuple(
	discover_engine_specs(
		internal_root=INTERNAL_DRIVER_ROOT,
		internal_package=INTERNAL_DRIVER_PACKAGE,
		external_root=WVW_PATH,
		logger=log,
	)
)
ENGINE_SPEC_INDEX = {spec.name: spec for spec in ENGINE_SPECS}

# Compatibility shim for existing iteration sites that expect `for eng in EngineType`.
EngineType = ENGINE_SPECS

READY_ENGINE_CLASS = {}


def refresh_ready_engine_classes(engine_config) -> dict[str, type]:
	ready = load_enabled_engine_classes(list(ENGINE_SPECS), engine_config, logger=log)
	READY_ENGINE_CLASS.clear()
	READY_ENGINE_CLASS.update(ready)
	return READY_ENGINE_CLASS


def get_engine_enabled(engine_name: str, engine_config) -> bool:
	spec = ENGINE_SPEC_INDEX.get(engine_name)
	if spec is None:
		if engine_name not in engine_config:
			return False
		value = engine_config[engine_name]
		if isinstance(value, str):
			return value.lower() not in {"false", "0", ""}
		return bool(value)
	return _get_engine_enabled(engine_config, spec)


def get_engine_label(engine_name: str) -> str:
	spec = ENGINE_SPEC_INDEX.get(engine_name)
	if spec is None:
		return engine_name
	return spec.label


def get_engine_default_enabled(engine_name: str) -> bool:
	spec = ENGINE_SPEC_INDEX.get(engine_name)
	if spec is None:
		return False
	return spec.default_enabled
