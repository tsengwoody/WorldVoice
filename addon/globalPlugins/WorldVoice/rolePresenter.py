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
		speech_section: Callable[[], MutableMapping],
		set_main_voice: Callable[[str], None],
	):
		self._manager = manager
		self._speech_section = speech_section
		self._set_main_voice = set_main_voice
		self._edit = manager.begin_voice_settings_edit()
		self._pending: dict[str, str] = {}
		self._before_parameter_preview: dict[str, dict] | None = None
		self._read_flags()

	def _read_flags(self):
		self.keep_engine = self._manager.engine_consistency.enabled
		self.keep_voice = self._manager.voice_consistency.enabled
		self.keep_parameters = self._manager.parameter_consistency.enabled

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

	def selected_voice(self, locale: str) -> str:
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

	def _main_parameters(self) -> dict:
		base = self._manager.default_voice_instance.snapshot()
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
			self._manager.preview_voice_parameter_consistent(voice)

	def set_variant(self, name: str, value: str) -> None:
		self.voice(name).variant = value

	def set_engine_consistency(self, enabled: bool) -> None:
		self.keep_engine = enabled
		# Only this flag changes which voices are listed, so it is previewed.
		self._manager.engine_consistency.preview = enabled

	def set_voice_consistency(self, enabled: bool) -> None:
		self.keep_voice = enabled

	def set_parameter_consistency(self, enabled: bool) -> None:
		if enabled and not self.keep_parameters:
			settings = self._manager.settings
			self._before_parameter_preview = {
				key: {parameter: settings.state(key).get(parameter) for parameter in PARAMETER_NAMES}
				for key in settings.names()
			}
			self.keep_parameters = True
			self._manager.preview_voice_parameter_consistent(self._manager.default_voice_instance)
		elif not enabled and self.keep_parameters:
			self.keep_parameters = False
			# Undo only this dialog's preview, keeping other edits made before it.
			# A voice first loaded during the preview goes back to its loaded values.
			record = self._before_parameter_preview
			if record is not None:
				settings = self._manager.settings
				for key in settings.names():
					state = settings.state(key)
					values = record.get(key) or {p: state.baseline(p) for p in PARAMETER_NAMES}
					state.update(**values)
			self._before_parameter_preview = None

	# Transaction

	def apply(self) -> None:
		manager = self._manager
		if self.keep_parameters:
			manager.preview_voice_parameter_consistent(manager.default_voice_instance)
		self._edit.apply()  # A failure leaves everything below unsaved.

		assignments = manager.roles.assignments()
		for locale, name in self._pending.items():
			if name:
				assignments[locale] = name
			else:
				assignments.pop(locale, None)
		manager.engine_consistency.enabled = self.keep_engine
		manager.engine_consistency.preview = None
		manager.voice_consistency.enabled = self.keep_voice
		manager.parameter_consistency.enabled = self.keep_parameters
		manager.roles.save(prune_assignments(assignments, manager.locale_to_voices_map))

		if self.keep_voice:
			chosen = self._pending.get(manager.voice_consistency.main_locale(manager.default_voice_instance))
			if chosen and chosen != manager.default_voice_name:
				self._set_main_voice(chosen)

		try:
			section = self._speech_section()
		except KeyError:
			section = None
		if section is not None:
			snapshot = manager.settings.snapshot(manager.default_voice_name)
			for parameter in PARAMETER_NAMES:
				section[parameter] = getattr(snapshot, parameter)

		self._pending.clear()
		self._before_parameter_preview = None

	def discard(self) -> None:
		self._edit.discard()
		self._pending.clear()
		self._before_parameter_preview = None
		self._manager.engine_consistency.preview = None
		self._read_flags()

	def close(self) -> None:
		# A panel destroyed without OK or Cancel must not leave its preview filtering voices.
		self._manager.engine_consistency.preview = None
		self._edit.close()
