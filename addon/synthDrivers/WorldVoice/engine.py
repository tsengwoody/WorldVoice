from enum import Enum

import addonHandler

addonHandler.initTranslation()

ENGINE_SPECS = {
	key: (
		f"synthDrivers.WorldVoice.driver.{key}.voice",
		f"{key}Voice",
		key
	) for key in ["OneCore", "SAPI5", "Espeak", "RH", "Aisound", "IBM", "VE"]
}


DEFAULT_ENABLED = {"VE", "OneCore", "SAPI5"}


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
