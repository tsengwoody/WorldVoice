from enum import Enum


class EngineType(Enum):
	VE = (
		"synthDrivers.WorldVoice.voice.VEVoice",
		"VEVoice",
		_("Activate VE")
	)
	SAPI5 = (
		"synthDrivers.WorldVoice.voice.Sapi5Voice",
		"Sapi5Voice",
		_("Activate SAPI5")
	)
	OneCore = (
		"synthDrivers.WorldVoice.voice.OneCoreVoice",
		"OneCoreVoice",
		_("Activate OneCore")
	)
	RH = (
		"synthDrivers.WorldVoice.voice.RHVoice",
		"RHVoice",
		_("Activate RH")
	)
	Espeak = (
		"synthDrivers.WorldVoice.voice.EspeakVoice",
		"EspeakVoice",
		_("Activate Espeak")
	)
	IBM = (
		"synthDrivers.WorldVoice.voice.IBMVoice",
		"IBMVoice",
		_("Activate IBM")
	)

	@property
	def module_path(self) -> str:
		# e.g. "voice.VEVoice"
		return self.value[0]

	@property
	def class_name(self) -> str:
		# e.g. "VEVoice"
		return self.value[1]

	@property
	def label(self) -> str:
		# e.g. "VE"
		return self.value[2]

	@property
	def default_enabled(self) -> bool:
		# default enabled
		return self in [EngineType.VE, EngineType.OneCore, EngineType.SAPI5]

	@property
	def name(self) -> str:
		# e.g. "VE"
		return self._name_
