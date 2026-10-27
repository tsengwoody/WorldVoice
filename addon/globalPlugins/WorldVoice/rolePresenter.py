"""State and transaction of the WorldVoice speech-role settings panel, without wx."""

from collections.abc import Callable, MutableMapping

from synthDrivers.WorldVoice.runtime.voiceSettings import PARAMETER_NAMES
from synthDrivers.WorldVoice.voices.roles import prune_assignments


class RolePanelPresenter:
	"""Pending role choices and consistency flags over one shared voice edit.

	Voice parameters change live (preview) through the shared edit; apply()
	saves them, then roles, flags, the main voice and its speech section.
	"""

	def __init__(
		self,
		manager,
		*,
		speechSection: Callable[[], MutableMapping],
		setMainVoice: Callable[[str], None],
	):
		self._manager = manager
		self._speechSection = speechSection
		self._setMainVoice = setMainVoice
		self._edit = manager.begin_voice_settings_edit()
		self._pending: dict[str, str] = {}
		self._beforeParameterPreview: dict[str, dict] | None = None
		self._readFlags()

	def _readFlags(self):
		self.keepEngine = self._manager.engine_consistency.enabled
		self.keepVoice = self._manager.voice_consistency.enabled
		self.keepParameters = self._manager.parameter_consistency.enabled

	# Queries

	def locales(self) -> list[tuple[str, str]]:
		names = self._manager.locales_to_names_map
		return [(locale, names[locale]) for locale in self._manager.languages]

	def voices(self, locale: str) -> list[tuple[str, str]]:
		descriptions = {voice.name: voice.description for voice in self._manager.table}
		names = []
		for name in self._manager.locale_to_voices_map.get(locale, []):
			if name not in names:
				names.append(name)
		return [(name, descriptions.get(name) or name) for name in names]

	def selectedVoice(self, locale: str) -> str:
		if locale in self._pending:
			return self._pending[locale]
		return self._manager.roles.assignments().get(locale, "")

	def voice(self, name: str):
		return self._manager.get_voice_instance(name)

	def capabilities(self, name: str) -> frozenset:
		return self._manager.get_voice_capabilities(name).settings if name else frozenset()

	def variants(self, name: str) -> list[str]:
		return ["default"] + [item["id"] for item in self._manager.get_voice_variants(name) if item != ""]

	# Edits

	def _mainParameters(self) -> dict:
		base = self._manager.default_voice_instance.snapshot()
		return {parameter: getattr(base, parameter) for parameter in PARAMETER_NAMES}

	def selectVoice(self, locale: str, name: str):
		self._pending[locale] = name
		if not name:
			return None
		voice = self.voice(name)
		if self.keepParameters:
			voice.update_settings(**self._mainParameters())
		return voice

	def setParameter(self, name: str, parameter: str, value) -> None:
		voice = self.voice(name)
		setattr(voice, parameter, value)
		if self.keepParameters:
			self._manager.preview_voice_parameter_consistent(voice)

	def setVariant(self, name: str, value: str) -> None:
		self.voice(name).variant = value

	def setEngineConsistency(self, enabled: bool) -> None:
		self.keepEngine = enabled
		# Only this flag changes which voices are listed, so it is previewed.
		self._manager.engine_consistency.preview = enabled

	def setVoiceConsistency(self, enabled: bool) -> None:
		self.keepVoice = enabled

	def setParameterConsistency(self, enabled: bool) -> None:
		if enabled and not self.keepParameters:
			settings = self._manager.settings
			self._beforeParameterPreview = {
				key: {parameter: settings.state(key).get(parameter) for parameter in PARAMETER_NAMES}
				for key in settings.names()
			}
			self.keepParameters = True
			self._manager.preview_voice_parameter_consistent(self._manager.default_voice_instance)
		elif not enabled and self.keepParameters:
			self.keepParameters = False
			# Undo only this dialog's preview, keeping other edits made before it.
			# A voice first loaded during the preview goes back to its loaded values.
			record = self._beforeParameterPreview
			if record is not None:
				settings = self._manager.settings
				for key in settings.names():
					state = settings.state(key)
					values = record.get(key) or {p: state.baseline(p) for p in PARAMETER_NAMES}
					state.update(**values)
			self._beforeParameterPreview = None

	# Transaction

	def apply(self) -> None:
		manager = self._manager
		if self.keepParameters:
			manager.preview_voice_parameter_consistent(manager.default_voice_instance)
		self._edit.apply()  # A failure leaves everything below unsaved.

		assignments = manager.roles.assignments()
		for locale, name in self._pending.items():
			if name:
				assignments[locale] = name
			else:
				assignments.pop(locale, None)
		manager.engine_consistency.enabled = self.keepEngine
		manager.engine_consistency.preview = None
		manager.voice_consistency.enabled = self.keepVoice
		manager.parameter_consistency.enabled = self.keepParameters
		manager.roles.save(prune_assignments(assignments, manager.locale_to_voices_map))

		if self.keepVoice:
			chosen = self._pending.get(manager.voice_consistency.main_locale(manager.default_voice_instance))
			if chosen and chosen != manager.default_voice_name:
				self._setMainVoice(chosen)

		try:
			section = self._speechSection()
		except KeyError:
			section = None
		if section is not None:
			snapshot = manager.settings.snapshot(manager.default_voice_name)
			for parameter in PARAMETER_NAMES:
				section[parameter] = getattr(snapshot, parameter)

		self._pending.clear()
		self._beforeParameterPreview = None

	def discard(self) -> None:
		self._edit.discard()
		self._pending.clear()
		self._beforeParameterPreview = None
		self._manager.engine_consistency.preview = None
		self._readFlags()

	def close(self) -> None:
		# A panel destroyed without OK or Cancel must not leave its preview filtering voices.
		self._manager.engine_consistency.preview = None
		self._edit.close()
