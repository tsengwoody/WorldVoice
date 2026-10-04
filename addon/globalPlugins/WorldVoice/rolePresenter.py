"""State and transaction of the WorldVoice speech-role settings panel, without wx."""

from collections.abc import Callable, MutableMapping

PARAMETER_NAMES = ("rate", "pitch", "volume", "inflection", "rateBoost")


class RolePanelPresenter:
	"""Pending role choices and consistency flags over one shared voice edit.

	Voice parameters change live (preview) through the shared edit; apply()
	saves them, then roles, flags, the main voice and its speech section.
	"""

	def __init__(
		self,
		manager,
		*,
		speech_section: Callable[[], MutableMapping],
		set_main_voice: Callable[[str], None],
	):
		self._manager = manager
		self._speech_section = speech_section
		self._set_main_voice = set_main_voice
		self._edit = manager.beginVoiceSettingsEdit()
		self._pending: dict[str, str] = {}
		self._initial_engine = manager.engine_consistency.enabled
		self._before_parameter_preview: dict[str, dict] | None = None
		self._read_flags()

	def _read_flags(self):
		self.keep_engine = self._manager.engine_consistency.enabled
		self.keep_voice = self._manager.voice_consistency.enabled
		self.keep_parameters = self._manager.parameter_consistency.enabled

	# Queries

	def locales(self) -> list[tuple[str, str]]:
		names = self._manager.localesToNamesMap
		return [(locale, names[locale]) for locale in self._manager.languages]

	def voices(self, locale: str) -> list[tuple[str, str]]:
		descriptions = {voice.name: voice.description for voice in self._manager.table}
		names = []
		for name in self._manager.localeToVoicesMap.get(locale, []):
			if name not in names:
				names.append(name)
		return [(name, descriptions.get(name) or name) for name in names]

	def selected_voice(self, locale: str) -> str:
		if locale in self._pending:
			return self._pending[locale]
		return self._manager.roles.assignments().get(locale, "")

	def voice(self, name: str):
		return self._manager.getVoiceInstance(name)

	def capabilities(self, name: str) -> frozenset:
		return self._manager.getVoiceCapabilities(name).settings if name else frozenset()

	def variants(self, name: str) -> list[str]:
		return ["default"] + [item["id"] for item in self._manager.getVoiceVariants(name) if item != ""]

	# Edits

	def _main_parameters(self) -> dict:
		base = self._manager.defaultVoiceInstance.snapshot()
		return {parameter: getattr(base, parameter) for parameter in PARAMETER_NAMES}

	def select_voice(self, locale: str, name: str):
		self._pending[locale] = name
		if not name:
			return None
		voice = self.voice(name)
		if self.keep_parameters:
			voice.update_settings(**self._main_parameters())
		return voice

	def set_parameter(self, name: str, parameter: str, value) -> None:
		voice = self.voice(name)
		setattr(voice, parameter, value)
		if self.keep_parameters:
			self._manager.previewVoiceParameterConsistent(voice)

	def set_variant(self, name: str, value: str) -> None:
		self.voice(name).variant = value

	def set_engine_consistency(self, enabled: bool) -> None:
		self.keep_engine = enabled
		self._manager.engine_consistency.enabled = enabled

	def set_voice_consistency(self, enabled: bool) -> None:
		self.keep_voice = enabled

	def set_parameter_consistency(self, enabled: bool) -> None:
		if enabled and not self.keep_parameters:
			settings = self._manager.settings
			self._before_parameter_preview = {
				key: {parameter: settings.state(key).get(parameter) for parameter in PARAMETER_NAMES}
				for key in settings.keys()
			}
			self.keep_parameters = True
			self._manager.previewVoiceParameterConsistent(self._manager.defaultVoiceInstance)
		elif not enabled and self.keep_parameters:
			self.keep_parameters = False
			# Undo only this dialog's preview, keeping other edits made before it.
			# A voice first loaded during the preview goes back to its loaded values.
			record = self._before_parameter_preview
			if record is not None:
				settings = self._manager.settings
				for key in settings.keys():
					state = settings.state(key)
					values = record.get(key) or {p: state.baseline(p) for p in PARAMETER_NAMES}
					state.update(**values)
			self._before_parameter_preview = None

	# Transaction

	def apply(self) -> None:
		manager = self._manager
		if self.keep_parameters:
			manager.previewVoiceParameterConsistent(manager.defaultVoiceInstance)
		self._edit.apply()  # A failure leaves everything below unsaved.

		assignments = manager.roles.assignments()
		for locale, name in self._pending.items():
			if name:
				assignments[locale] = name
			else:
				assignments.pop(locale, None)
		manager.engine_consistency.enabled = self.keep_engine
		manager.engine_consistency.persist()
		manager.voice_consistency.enabled = self.keep_voice
		manager.parameter_consistency.enabled = self.keep_parameters
		available = manager.localeToVoicesMap
		manager.roles.save(
			{
				locale: name
				for locale, name in assignments.items()
				if locale in available and name in available[locale]
			},
		)

		if self.keep_voice:
			chosen = self._pending.get(manager.voice_consistency.main_locale(manager.defaultVoiceInstance))
			if chosen and chosen != manager.defaultVoiceName:
				self._set_main_voice(chosen)

		try:
			section = self._speech_section()
		except KeyError:
			section = None
		if section is not None:
			snapshot = manager.settings.snapshot(manager.defaultVoiceName)
			for parameter in PARAMETER_NAMES:
				section[parameter] = getattr(snapshot, parameter)

		self._pending.clear()
		self._before_parameter_preview = None
		self._initial_engine = manager.engine_consistency.enabled

	def discard(self) -> None:
		self._edit.discard()
		self._pending.clear()
		self._before_parameter_preview = None
		self._manager.engine_consistency.enabled = self._initial_engine
		self._read_flags()

	def close(self) -> None:
		self._edit.close()
