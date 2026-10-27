"""The WorldVoice settings dialog and the panels it offers."""

import addonHandler
from gui.settingsDialogs import MultiCategorySettingsDialog
from synthDrivers.WorldVoice.pipeline.context import worldvoice_synth

from .panels.detection import UnicodeDetectionSettingsPanel
from .panels.engine import SpeechEngineSettingsPanel
from .panels.log import LogSettingsPanel
from .panels.pipeline import SpeechPipelinePanel
from .panels.role import SpeechRoleSettingsPanel

addonHandler.initTranslation()


class WorldVoiceSettingsDialog(MultiCategorySettingsDialog):
	dialogTitle = _("Settings")
	INITIAL_SIZE = (1000, 480)
	MIN_SIZE = (470, 240)

	def __init__(self, parent):
		if worldvoice_synth() is not None:
			self.categoryClasses = [
				SpeechPipelinePanel,
				SpeechRoleSettingsPanel,
				SpeechEngineSettingsPanel,
				UnicodeDetectionSettingsPanel,
				LogSettingsPanel,
			]
		else:
			self.categoryClasses = [
				SpeechPipelinePanel,
				SpeechEngineSettingsPanel,
				LogSettingsPanel,
			]
		super().__init__(parent)  # 這時父類別會讀取 self.categoryClasses
		self.SetTitle(_("WorldVoice - %s") % self.dialogTitle)
