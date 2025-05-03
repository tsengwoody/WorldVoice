from autoSettingsUtils.driverSetting import BooleanDriverSetting, NumericDriverSetting
import config
import gui
from gui.settingsDialogs import VoiceSettingsPanel
from logHandler import log


class WorldVoiceVoiceSettingsPanel(VoiceSettingsPanel):
	def makeSettings(self, settingsSizer):
		self.createDriverSettings()
		super().makeSettings(settingsSizer)

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
		for setting in settingsInst.allSupportedSettings:
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

	"""def onDiscard(self):
		super().onDiscard()
		synth = self.getSettings()
		if synth.name == 'WorldVoice':
			config.conf["WorldVoice"]["synthesizer"]["ignore_comma_between_number"] = synth.cni
			config.conf["WorldVoice"]["synthesizer"]["global_wait_factor"] = synth.globalwaitfactor
			config.conf["WorldVoice"]["synthesizer"]["number_wait_factor"] = synth.numberwaitfactor
			config.conf["WorldVoice"]["synthesizer"]["item_wait_factor"] = synth.itemwaitfactor
			config.conf["WorldVoice"]["synthesizer"]["sayall_wait_factor"] = synth.sayallwaitfactor
			config.conf["WorldVoice"]["synthesizer"]["chinesespace_wait_factor"] = synth.chinesespacewaitfactor

	def onSave(self):
		super().onSave()
		synth = self.getSettings()
		if synth.name == 'WorldVoice':
			config.conf["WorldVoice"]["synthesizer"]["ignore_comma_between_number"] = synth.cni
			config.conf["WorldVoice"]["synthesizer"]["global_wait_factor"] = synth.globalwaitfactor
			config.conf["WorldVoice"]["synthesizer"]["number_wait_factor"] = synth.numberwaitfactor
			config.conf["WorldVoice"]["synthesizer"]["item_wait_factor"] = synth.itemwaitfactor
			config.conf["WorldVoice"]["synthesizer"]["sayall_wait_factor"] = synth.sayallwaitfactor
			config.conf["WorldVoice"]["synthesizer"]["chinesespace_wait_factor"] = synth.chinesespacewaitfactor
	"""
