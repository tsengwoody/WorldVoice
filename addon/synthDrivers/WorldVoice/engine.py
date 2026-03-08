from enum import Enum
import importlib
from importlib.machinery import PathFinder
import os
import sys

import addonHandler

addonHandler.initTranslation()

user_folder = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
WVW_PATH = os.path.join(user_folder, "WorldVoice-workspace")

INTERNAL_DRIVER_PACKAGE = f"{__package__}.driver"
EXTERNAL_DRIVER_DIRS = [
	# r"C:\path\to\external\WorldVoice\driver",
]
# Map an engine to an external driver root directory.
# Leave an engine unset to keep using the built-in package driver.
ENGINE_EXTERNAL_DRIVER_DIRS = {
	"MSC": os.path.join(WVW_PATH, "MSC"),
	"YongDe": os.path.join(WVW_PATH, "YongDe"),
}


SUPPORT_ENGINE = [
	"OneCore",
	"SAPI5",
	"Espeak",
	"RH",
	"VE",
	"Cerence",
	"IBM",
	"MSC",
	"Aisound",
	"YongDe",
]
DEFAULT_ENABLED = {"OneCore", "SAPI5", "VE"}


ENGINE_SPECS = {
	key: (
		key,
		"Voice",
		key
	) for key in SUPPORT_ENGINE
}

EngineType = Enum("EngineType", ENGINE_SPECS)


def module_path(self) -> str:
	return self.value[0]


def class_name(self) -> str:
	return self.value[1]


def label(self) -> str:
	return self.value[2]


def default_enabled(self) -> bool:
	return self._name_ in DEFAULT_ENABLED


def name(self) -> str:
	return self._name_


EngineType.module_path = property(module_path)
EngineType.class_name = property(class_name)
EngineType.label = property(label)
EngineType.default_enabled = property(default_enabled)
EngineType.name = property(name)


def _normalize_external_driver_dir(path: str | None) -> str | None:
	if not path:
		return None
	normalized = os.path.abspath(path)
	if not os.path.isdir(normalized):
		return None
	return normalized


def _load_external_driver_module(module_name: str, driver_dir: str):
	normalized = _normalize_external_driver_dir(driver_dir)
	if not normalized:
		raise ModuleNotFoundError(
			f"External driver directory for {module_name} is not available: {driver_dir}"
		)
	if PathFinder.find_spec(module_name, [normalized]) is None:
		raise ModuleNotFoundError(
			f"Driver module {module_name} was not found in external directory: {normalized}"
		)
	if normalized not in sys.path:
		sys.path.insert(0, normalized)
	return importlib.import_module(module_name)


def _load_driver_module(module_name: str):
	external_dir = ENGINE_EXTERNAL_DRIVER_DIRS.get(module_name)
	if external_dir:
		return _load_external_driver_module(module_name, external_dir)
	return importlib.import_module(f".{module_name}", package=INTERNAL_DRIVER_PACKAGE)


def load_voice_classes(engines: list[EngineType]) -> dict[str, type]:
	"""
	Dynamically import voice classes based on EngineType definitions.
	Returns a dict mapping engine-name (e.g. "VE") to the class object.
	"""
	classes: dict[str, type] = {}
	for eng in engines:
		module_name = eng.module_path
		class_name = eng.class_name
		try:
			module = _load_driver_module(module_name)
			cls = getattr(module, class_name)
		except ModuleNotFoundError:
			continue
		classes[eng.name] = cls
	return classes

voice_classes = load_voice_classes(EngineType)
READY_ENGINE_CLASS = {key: value for key, value in voice_classes.items() if value.ready()}
