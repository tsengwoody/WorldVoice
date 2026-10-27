"""The Speech Pipeline panel, built from the pipeline settings table."""

import addonHandler
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel
from synthDrivers.WorldVoice.pipeline.settings import PIPELINE_SETTINGS, pipeline_settings
from synthDrivers.WorldVoice.ui.controls import (
	CHANGE_EVENTS,
	applyDependencies,
	controlValue,
	makeControl,
	readControl,
)
from synthDrivers.WorldVoice.ui.panelLayout import (
	PIPELINE_PANEL,
	controllerKeys,
	panelSpecs,
	pipelineAttribute,
)

addonHandler.initTranslation()


class SpeechPipelinePanel(SettingsPanel):
	title = _("Speech Pipeline")

	def makeSettings(self, sizer):
		# Every control comes from the pipeline settings table, in its order, under one helper
		# so NVDA's spacing separates the rows.
		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)
		settings = pipeline_settings.get()
		specs = self._specs()
		for spec in specs:
			control = makeControl(self, settingsSizerHelper, spec, getattr(settings, spec.key))
			setattr(self, pipelineAttribute(spec), control)
		controllers = controllerKeys(specs)
		for spec in specs:
			if spec.key in controllers:
				self.Bind(CHANGE_EVENTS[spec.control], self._onControllerChange, self._control(spec))
		self._applyDependencies()

	@staticmethod
	def _specs():
		return panelSpecs(PIPELINE_SETTINGS, PIPELINE_PANEL)

	def _control(self, spec):
		return getattr(self, pipelineAttribute(spec), None)

	def _readController(self, key):
		(spec,) = [spec for spec in self._specs() if spec.key == key]
		return readControl(spec, self._control(spec))

	def _applyDependencies(self):
		applyDependencies(self._specs(), self._readController, self._control)

	def _onControllerChange(self, event):
		self._applyDependencies()

	def onSave(self):
		# The table guard keeps ordering-only entries (NVDA stores them) out of this panel; skip one anyway.
		values = {
			spec.key: controlValue(spec, self._control(spec))
			for spec in self._specs()
			if spec.pipeline_config
		}
		# A choice with no selection names no value, so the stored one is kept.
		pipeline_settings.update(**{key: value for key, value in values.items() if value is not None})
