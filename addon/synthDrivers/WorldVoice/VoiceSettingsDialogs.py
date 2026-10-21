import addonHandler
import gui
from autoSettingsUtils.driverSetting import BooleanDriverSetting, NumericDriverSetting
from gui import guiHelper
from gui.settingsDialogs import VoiceSettingsPanel
from logHandler import log

from .pipeline.panelLayout import (
	ABSENT,
	VOICE_PANEL,
	choice_values,
	controller_keys,
	dependent_states,
	driver_attribute,
	panel_specs,
	selected_value,
	voice_attribute,
	voice_placements,
)
from .pipeline.settings import PIPELINE_CONFIG_KEYS, PIPELINE_SETTINGS, pipeline_settings
from .pipelineControls import CHANGE_EVENTS, control_row, control_value, make_control

addonHandler.initTranslation()


def _moveSizer(settingsSizer, sizer, index):
	"""Move sizer to index in settingsSizer, keeping its proportion, flag and border."""
	# Read the layout first: wx deletes the sizer item on Detach.
	item = settingsSizer.GetItem(sizer)
	proportion, flag, border = item.GetProportion(), item.GetFlag(), item.GetBorder()
	settingsSizer.Detach(sizer)
	settingsSizer.Insert(index, sizer, proportion, flag, border)


class WorldVoiceVoiceSettingsPanel(VoiceSettingsPanel):
	def makeSettings(self, settingsSizer):
		self._pipelineSnapshot = pipeline_settings.get() if self._isWorldVoice() else None
		self.createDriverSettings()
		super().makeSettings(settingsSizer)
		self._addPipelineControls(settingsSizer)
		self._bindControllers()
		self._applyDependencies()

	def _bindControllers(self):
		"""Hook every control other settings depend on (depends_on in the pipeline table)."""
		controllers = controller_keys(self._voiceSpecs())
		for spec in self._voiceSpecs():
			control = self._voiceControl(spec)
			if spec.key in controllers and control is not None:
				control.Bind(CHANGE_EVENTS[spec.control], self._onControllerChange)

	def _onControllerChange(self, evt):
		# NVDA's own handler writes a driver setting; this one only updates the dependent controls.
		evt.Skip()
		self._applyDependencies()

	def _controllerDriverIds(self):
		controllers = controller_keys(self._voiceSpecs())
		return {spec.driver_id for spec in self._voiceSpecs() if spec.key in controllers and spec.driver_id}

	def _readController(self, key):
		"""The controller's value as its control shows it, or ABSENT without the control (another synth).

		Read the control, not the driver: this runs before NVDA's handler writes the setting.
		"""
		(spec,) = [spec for spec in self._voiceSpecs() if spec.key == key]
		control = self._voiceControl(spec)
		if control is None:
			return ABSENT
		if spec.control != "choice":
			return control.GetValue()
		if spec.driver_id is not None:
			# No selection (-1) names no option, although the list's last option is at -1.
			options = [option.id for option in getattr(self, f"_{spec.driver_id}s", [])]
			return selected_value(options, control.GetSelection())
		return selected_value(choice_values(spec), control.GetCurrentSelection())

	def _applyDependencies(self):
		# Disable rather than hide: NVDA's updateDriverSettings shows every supported
		# control again after a voice change, but never enables or disables one.
		specs = self._voiceSpecs()
		states = dependent_states(specs, self._readController)
		for spec in specs:
			control = self._voiceControl(spec)
			if spec.key in states and control is not None:
				control.Enable(states[spec.key])

	@staticmethod
	def _voiceSpecs():
		# Read at call time, so the order follows the table the module holds.
		return panel_specs(PIPELINE_SETTINGS, VOICE_PANEL)

	def _voiceControl(self, spec):
		"""The control of a Voice panel entry: NVDA's for a driver setting, else WorldVoice's; or None."""
		name = driver_attribute(spec) if spec.driver_id is not None else voice_attribute(spec)
		return getattr(self, name, None)

	def _addPipelineControls(self, settingsSizer):
		"""
		Add the table's settings that are not driver settings, each right after the row of the entry
		before it in the table, in layout and tab order. They are written on Save.
		Another synth gets none of them; the Speech Pipeline panel is where they are changed then.
		"""
		specs = self._voiceSpecs()
		added = [spec for spec in specs if spec.driver_id is None]
		# NVDA rebuilds this panel on a synth change and destroys the old windows.
		for spec in added:
			setattr(self, voice_attribute(spec), None)
		if not self._isWorldVoice():
			return
		settings = pipeline_settings.get()
		for spec in added:
			# A helper per control: its first item gets no spacer, so moving the row leaves none.
			helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
			setattr(
				self,
				voice_attribute(spec),
				make_control(self, helper, spec, getattr(settings, spec.key)),
			)
		byKey = {spec.key: spec for spec in specs}

		def hasRow(key):
			spec = byKey[key]
			if spec.driver_id is not None:
				return spec.driver_id in self.sizerDict
			return self._voiceControl(spec) is not None

		for key, anchorKey in voice_placements(specs, hasRow):
			if anchorKey is None:
				continue
			spec, anchor = byKey[key], byKey[anchorKey]
			control, anchorControl = self._voiceControl(spec), self._voiceControl(anchor)
			anchorRow = (
				self.sizerDict[anchor.driver_id]
				if anchor.driver_id is not None
				else control_row(anchorControl, anchor)
			)
			index = self._rowIndex(settingsSizer, anchorRow)
			if index is not None:
				_moveSizer(settingsSizer, control_row(control, spec), index + 1)
			control.MoveAfterInTabOrder(anchorControl)

	@staticmethod
	def _rowIndex(settingsSizer, row):
		"""The index of row in settingsSizer: NVDA adds a checkbox as itself, other rows as sizers."""
		return next(
			(
				index
				for index, item in enumerate(settingsSizer.GetChildren())
				if item.GetSizer() is row or item.GetWindow() is row
			),
			None,
		)

	def onSave(self):
		# Read the synth at save time: the panel may be saved before NVDA rebuilds it for another synth.
		if self._isWorldVoice():
			values = {}
			for spec in self._voiceSpecs():
				control = self._voiceControl(spec)
				if spec.driver_id is None and spec.pipeline_config and control is not None:
					values[spec.key] = control_value(spec, control)
			# One update, so subscribers see every value together, before NVDA saves its own settings.
			pipeline_settings.update(**{key: value for key, value in values.items() if value is not None})
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
		if setting.id in self._controllerDriverIds():
			# SetValue and SetSelection fire no event, so apply the controller to its dependents here.
			self._applyDependencies()
