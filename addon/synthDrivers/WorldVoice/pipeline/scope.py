from collections.abc import Callable

from .registry import register_stages, unregister_stages
from .settings import PipelineSettings, PipelineSettingsService, pipeline_settings


class PipelineScope:
	"""Keep the speech pipeline registered exactly while an owner wants it.

	WorldVoice always runs its pipeline. With scope "all", the global plugin
	also runs it for every other synthesizer.
	"""

	def __init__(
		self,
		settings: PipelineSettingsService,
		register: Callable[[], None],
		unregister: Callable[[], None],
	):
		self._settings = settings
		self._register = register
		self._unregister = unregister
		self._worldvoice = False
		self._global = False
		self._registered = False
		settings.subscribe(self._sync)

	@property
	def registered(self) -> bool:
		return self._registered

	def worldvoice_started(self) -> None:
		self._worldvoice = True
		self._sync()

	def worldvoice_ended(self) -> None:
		self._worldvoice = False
		self._sync()

	def attach_global(self) -> None:
		self._global = True
		self._sync()

	def detach_global(self) -> None:
		self._global = False
		self._sync()

	def _sync(self, settings: PipelineSettings | None = None) -> None:
		if self._worldvoice:
			wanted = True
		elif self._global:
			wanted = (settings or self._settings.get()).scope == "all"
		else:
			wanted = False
		if wanted == self._registered:
			return
		if wanted:
			self._register()
		else:
			self._unregister()
		self._registered = wanted


pipeline_scope = PipelineScope(pipeline_settings, register_stages, unregister_stages)
