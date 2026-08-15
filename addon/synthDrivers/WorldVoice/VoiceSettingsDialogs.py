import addonHandler
from autoSettingsUtils.driverSetting import BooleanDriverSetting, NumericDriverSetting
import config
import gui
from gui import guiHelper
from gui.settingsDialogs import VoiceSettingsPanel
from logHandler import log
import wx

from .pipeline.settings import DEFAULT_PIPELINE_SETTINGS


addonHandler.initTranslation()


class WorldVoiceVoiceSettingsPanel(VoiceSettingsPanel):
	def makeSettings(self, settingsSizer):
		self.createDriverSettings()
		super().makeSettings(settingsSizer)
		self._addPunctuationPauseCharactersControl(settingsSizer)

	def _addPunctuationPauseCharactersControl(self, settingsSizer):
		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.punctuationPauseCharactersEdit = settingsSizerHelper.addLabeledControl(
			_("Punctuation pause characters:"),
			wx.TextCtrl,
		)
		self.punctuationPauseCharactersEdit.SetValue(
			config.conf["WorldVoice"]["pipeline"].get(
				"punctuation_pause_characters",
				DEFAULT_PIPELINE_SETTINGS["punctuation_pause_characters"],
			)
		)

	def onSave(self):
		value = self.punctuationPauseCharactersEdit.GetValue().strip()
		config.conf["WorldVoice"]["pipeline"]["punctuation_pause_characters"] = value
		super().onSave()

	def createDriverSettings(self, changedSetting=None):
		"""
		Creates, hides or updates existing GUI controls for all of supported settings.
		"""
		settingsInst = self.getSettings()
		settingsStorage = self._getSettingsStorage()
		# firstly check already created options
		for name, sizer in self.sizerDict.items():
			if name == changedSetting:
				# Changing a setting shouldn't cause that setting itself to disappear.
				continue
			if not settingsInst.isSupported(name):
				self.settingsSizer.Hide(sizer)
		# Create new controls, update already existing
		if gui._isDebug():
			log.debug(f"Current sizerDict: {self.sizerDict!r}")
			log.debug(f"Current supportedSettings: {self.getSettings().supportedSettings!r}")

		supportedSettings = settingsInst.allSupportedSettings if hasattr(settingsInst, "allSupportedSettings") else settingsInst.supportedSettings
		for setting in supportedSettings:
			if setting.id == changedSetting:
				# Changing a setting shouldn't cause that setting's own values to change.
				continue
			if setting.id in self.sizerDict:  # update a value
				self._updateValueForControl(setting, settingsStorage)
			else:  # create a new control
				self._createNewControl(setting, settingsStorage)
		# Update graphical layout of the dialog
		self.settingsSizer.Layout()

	def _updateValueForControl(self, setting, settingsStorage):
		self.settingsSizer.Show(self.sizerDict[setting.id])
		if isinstance(setting, NumericDriverSetting):
			getattr(self, f"{setting.id}Slider").SetValue(
				getattr(settingsStorage, setting.id)
			)
		elif isinstance(setting, BooleanDriverSetting):
			getattr(self, f"{setting.id}Checkbox").SetValue(
				getattr(settingsStorage, setting.id)
			)
		else:
			stringSettingAttribName = f"_{setting.id}s"
			setattr(
				self,
				stringSettingAttribName,
				# Settings are stored as an ordered dict.
				# Therefore wrap this inside a list call.
				list(getattr(
					self.getSettings(),
					f"available{setting.id.capitalize()}s"
				).values())
			)
			options = getattr(self, stringSettingAttribName)

			lCombo = getattr(self, f"{setting.id}List")
			lCombo.SetItems([x.displayName for x in options])
			try:
				cur = getattr(settingsStorage, setting.id)
				indexOfItem = [x.id for x in options].index(cur)
				lCombo.SetSelection(indexOfItem)
			except ValueError:
				pass
