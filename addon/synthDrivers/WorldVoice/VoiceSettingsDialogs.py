import addonHandler
import gui
import wx
from autoSettingsUtils.driverSetting import BooleanDriverSetting, NumericDriverSetting
from gui import guiHelper
from gui.settingsDialogs import VoiceSettingsPanel
from logHandler import log

from .pipeline.settings import PIPELINE_CONFIG_KEYS, pipeline_settings

addonHandler.initTranslation()


class WorldVoiceVoiceSettingsPanel(VoiceSettingsPanel):
	def makeSettings(self, settingsSizer):
		self._pipelineSnapshot = pipeline_settings.get() if self._isWorldVoice() else None
		self.createDriverSettings()
		super().makeSettings(settingsSizer)
		self._addPunctuationPauseCharactersControl(settingsSizer)
		self._bindPunctuationPauseEnabledToggle()

	def _bindPunctuationPauseEnabledToggle(self):
		"""
		Hook the "Enable punctuation pause control" checkbox so the
		"Punctuation wait factor" slider is hidden while the feature is
		disabled, mirroring the initial state on dialog open.
		"""
		checkbox = getattr(self, "punctuationpauseenabledCheckbox", None)
		sliderSizer = self.sizerDict.get("punctuationwaitfactor")
		if checkbox is None or sliderSizer is None:
			return
		checkbox.Bind(wx.EVT_CHECKBOX, self._onPunctuationPauseEnabledToggle)
		self._applyPunctuationWaitFactorVisibility()

	def _onPunctuationPauseEnabledToggle(self, evt):
		evt.Skip()
		self._getSettingsStorage().punctuationpauseenabled = evt.IsChecked()
		self._applyPunctuationWaitFactorVisibility()

	def _applyPunctuationWaitFactorVisibility(self):
		checkbox = getattr(self, "punctuationpauseenabledCheckbox", None)
		sliderSizer = self.sizerDict.get("punctuationwaitfactor")
		if checkbox is None or sliderSizer is None:
			return
		if checkbox.GetValue():
			self.settingsSizer.Show(sliderSizer)
		else:
			self.settingsSizer.Hide(sliderSizer)
		self.settingsSizer.Layout()

	def _addPunctuationPauseCharactersControl(self, settingsSizer):
		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.punctuationPauseCharactersEdit = settingsSizerHelper.addLabeledControl(
			_("Punctuation pause characters:"),
			wx.TextCtrl,
		)
		charactersSizer = self.punctuationPauseCharactersEdit.GetContainingSizer()
		punctuationWaitSizer = self.sizerDict.get("punctuationwaitfactor")
		if charactersSizer is not None and punctuationWaitSizer is not None:
			punctuationWaitIndex = next(
				(
					index
					for index, item in enumerate(settingsSizer.GetChildren())
					if item.GetSizer() is punctuationWaitSizer
				),
				None,
			)
			if punctuationWaitIndex is not None:
				charactersItem = settingsSizer.GetItem(charactersSizer)
				settingsSizer.Detach(charactersSizer)
				settingsSizer.Insert(
					punctuationWaitIndex + 1,
					charactersSizer,
					charactersItem.GetProportion(),
					charactersItem.GetFlag(),
					charactersItem.GetBorder(),
				)
			self.punctuationPauseCharactersEdit.MoveAfterInTabOrder(
				self.punctuationwaitfactorSlider,
			)
		self.punctuationPauseCharactersEdit.SetValue(pipeline_settings.get().punctuation_pause_characters)

	def onSave(self):
		pipeline_settings.update(punctuation_pause_characters=self.punctuationPauseCharactersEdit.GetValue())
		super().onSave()
		if self._isWorldVoice():
			# After Apply, a later Cancel keeps what was applied, like NVDA's own settings.
			self._pipelineSnapshot = pipeline_settings.get()

	def _isWorldVoice(self):
		return getattr(self.driver, "name", None) == "WorldVoice"

	def onDiscard(self):
		super().onDiscard()
		# Pipeline settings are not NVDA driver config, so loadSettings cannot
		# restore values changed while this panel was open.
		snapshot = getattr(self, "_pipelineSnapshot", None)
		if snapshot is None or not self._isWorldVoice():
			return
		current = pipeline_settings.get()
		changes = {
			key: getattr(snapshot, key)
			for key in PIPELINE_CONFIG_KEYS
			if getattr(current, key) != getattr(snapshot, key)
		}
		if changes:
			pipeline_settings.update(**changes)

	def createDriverSettings(self, changedSetting=None):
		"""
		Creates, hides or updates existing GUI controls for all of supported settings.

		Every control is created up front in its standard order, so a voice switch that
		reveals RateBoost or Inflection shows them in place instead of at the end.
		"""
		# Copied from NVDA's AutoSettingsMixin.updateDriverSettings, listing allSupportedSettings
		# so every control exists in its standard order; compare with NVDA's version on every
		# NVDA upgrade (tests/test_nvda_settings_copy.py fails when they drift).
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

		supportedSettings = (
			settingsInst.allSupportedSettings
			if hasattr(settingsInst, "allSupportedSettings")
			else settingsInst.supportedSettings
		)
		for setting in supportedSettings:
			if setting.id == changedSetting:
				# Changing a setting shouldn't cause that setting's own values to change.
				continue
			if setting.id in self.sizerDict:  # update a value
				self._updateValueForControl(setting, settingsStorage)
			elif setting.id.startswith("_"):
				# Skip private settings.
				continue
			else:  # create a new control
				self._createNewControl(setting, settingsStorage)
		# Update graphical layout of the dialog
		self.settingsSizer.Layout()

	def _updateValueForControl(self, setting, settingsStorage):
		self.settingsSizer.Show(self.sizerDict[setting.id])
		if isinstance(setting, NumericDriverSetting):
			getattr(self, f"{setting.id}Slider").SetValue(
				getattr(settingsStorage, setting.id),
			)
		elif isinstance(setting, BooleanDriverSetting):
			getattr(self, f"{setting.id}Checkbox").SetValue(
				getattr(settingsStorage, setting.id),
			)
		else:
			stringSettingAttribName = f"_{setting.id}s"
			setattr(
				self,
				stringSettingAttribName,
				# Settings are stored as an ordered dict.
				# Therefore wrap this inside a list call.
				list(
					getattr(
						self.getSettings(),
						f"available{setting.id.capitalize()}s",
					).values(),
				),
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
