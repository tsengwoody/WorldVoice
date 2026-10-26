"""The known engines: found at import, with whether each is enabled, its label and its default.

The engine wrappers themselves live in driver/<Engine>/ (bundled) and in the WorldVoice-workspace
(plugins); discovery.py finds and loads them. Not part of driver/: a plugin's import of
synthDrivers.WorldVoice.driver must not scan the disk or initialize translations.
"""

import os

import addonHandler
from logHandler import log

from ..workspace import workspace_path
from .discovery import (
	coerce_bool,
	discover_engine_specs,
	get_engine_enabled as _get_engine_enabled,
	load_enabled_engine_classes,
)

addonHandler.initTranslation()

PACKAGE_ROOT = os.path.dirname(os.path.dirname(__file__))
WVW_PATH = workspace_path()

INTERNAL_DRIVER_ROOT = os.path.join(PACKAGE_ROOT, "driver")
INTERNAL_DRIVER_PACKAGE = f"{__package__.rsplit('.', 1)[0]}.driver"

ENGINE_SPECS = tuple(
	discover_engine_specs(
		internal_root=INTERNAL_DRIVER_ROOT,
		internal_package=INTERNAL_DRIVER_PACKAGE,
		external_root=WVW_PATH,
		logger=log,
	),
)
ENGINE_SPEC_INDEX = {spec.name: spec for spec in ENGINE_SPECS}


def ready_engine_classes(engine_config) -> dict[str, type]:
	"""Load the enabled, ready Voice classes in discovery order."""
	return load_enabled_engine_classes(list(ENGINE_SPECS), engine_config, logger=log)


def get_engine_enabled(engine_name: str, engine_config) -> bool:
	spec = ENGINE_SPEC_INDEX.get(engine_name)
	if spec is None:
		return engine_name in engine_config and coerce_bool(engine_config[engine_name])
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
