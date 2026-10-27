import addonHandler
import wx
from autoSettingsUtils.driverSetting import BooleanDriverSetting, NumericDriverSetting
from gui import guiHelper
from gui.settingsDialogs import VoiceSettingsPanel

from ..pipeline.settings import PIPELINE_CONFIG_KEYS, PIPELINE_SETTINGS, pipeline_settings
from .controls import (
	CHANGE_EVENTS,
	applyDependencies,
	controlRow,
	controlValue,
	makeControl,
	readControl,
)
from .panelLayout import (
	VOICE_PANEL,
	controllerKeys,
	creationFollowers,
	driverAttribute,
	panelSpecs,
	voiceAttribute,
)

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
		# NVDA's makeSettings calls updateDriverSettings first, which makes every control below.
		super().makeSettings(settingsSizer)
		self._bindControllers()
		self._applyDependencies()

	def _bindControllers(self):
		"""Hook every control other settings depend on (depends_on in the pipeline table)."""
		controllers = controllerKeys(self._voiceSpecs())
		for spec in self._voiceSpecs():
			control = self._voiceControl(spec)
			if spec.key in controllers and control is not None:
				control.Bind(CHANGE_EVENTS[spec.control], self._onControllerChange)

	def _onControllerChange(self, evt):
		# NVDA's own handler writes a driver setting; this one only updates the dependent controls.
		evt.Skip()
		self._applyDependencies()

	def _controllerDriverIds(self):
		controllers = controllerKeys(self._voiceSpecs())
		return {spec.driver_id for spec in self._voiceSpecs() if spec.key in controllers and spec.driver_id}

	def _readController(self, key):
		"""The controller's value as its control shows it, or ABSENT without the control (another synth).

		Read the control, not the driver: this runs before NVDA's handler writes the setting.
		"""
		(spec,) = [spec for spec in self._voiceSpecs() if spec.key == key]
		# NVDA's list for a driver setting: the option ids it shows, in order.
		options = None
		if spec.driver_id is not None:
			options = [option.id for option in getattr(self, f"_{spec.driver_id}s", [])]
		return readControl(spec, self._voiceControl(spec), options)

	def _applyDependencies(self):
		# Disable rather than hide: NVDA's updateDriverSettings shows every supported
		# control again after a voice change, but never enables or disables one.
		applyDependencies(self._voiceSpecs(), self._readController, self._voiceControl)

	@staticmethod
	def _voiceSpecs():
		# Read at call time, so the order follows the table the module holds.
		return panelSpecs(PIPELINE_SETTINGS, VOICE_PANEL)

	def _voiceControl(self, spec):
		"""The control of a Voice panel entry: NVDA's for a driver setting, else WorldVoice's; or None.

		Every use of a table control goes through here. NVDA's refreshGui destroys the windows of
		the earlier build but keeps the attributes, and any call on a destroyed window raises; a
		destroyed wx window is falsy (NVDA's "if self.lastControl:" relies on it), so it counts as none.
		"""
		name = driverAttribute(spec) if spec.driver_id is not None else voiceAttribute(spec)
		control = getattr(self, name, None)
		return control if control else None

	def updateDriverSettings(self, changedSetting=None):
		"""Make every missing control in table order, then let NVDA hide, show and update them.

		Every driver setting the synth may ever support gets its control up front, in its standard
		order, so a voice switch that reveals RateBoost or Inflection shows them in place. Each
		WorldVoice control that is not a driver setting is made right after the row of the table
		entry before it, so window order (what object navigation follows), Tab order and layout
		follow the table, and its label stays just before it. Another synth gets none of them; the
		Speech Pipeline panel is where they are changed then.
		"""
		settingsInst = self.getSettings()
		settingsStorage = self._getSettingsStorage()
		allSettings = (
			settingsInst.allSupportedSettings
			if hasattr(settingsInst, "allSupportedSettings")
			else settingsInst.supportedSettings
		)
		specs = self._voiceSpecs()
		byKey = {spec.key: spec for spec in specs}
		absent = False
		for spec in specs:
			# Drop the windows of an earlier build, which NVDA's refreshGui destroyed; _voiceControl
			# already counts them as none, this keeps the attributes from naming them.
			if spec.driver_id is None and self._voiceControl(spec) is None:
				setattr(self, voiceAttribute(spec), None)
				absent = True
		values = pipeline_settings.get() if absent and self._isWorldVoice() else None
		listed = {setting.id for setting in allSettings if not setting.id.startswith("_")}
		followers = {
			driverId: [byKey[key] for key in keys]
			for driverId, keys in creationFollowers(specs, listed.__contains__).items()
		}
		# Each row made here, with the row made just before it, which it is placed after.
		placements = []
		previousRow = None
		for setting in allSettings:
			if setting.id != changedSetting and setting.id not in self.sizerDict and setting.id in listed:
				self._createNewControl(setting, settingsStorage)
			previousRow = self.sizerDict.get(setting.id, previousRow)
			previousRow = self._makePipelineControls(
				followers.get(setting.id, ()),
				values,
				previousRow,
				placements,
			)
		self._makePipelineControls(followers.get(None, ()), values, previousRow, placements)
		self._placePipelineRows(placements)
		super().updateDriverSettings(changedSetting)

	def _makePipelineControls(self, specs, values, previousRow, placements):
		"""Make the absent controls of specs, showing values (None: make none); return the last row.

		Each made row is recorded in placements with the row before it.
		"""
		for spec in specs:
			control = self._voiceControl(spec)
			if control is None and values is not None:
				# A helper per control: its first item gets no spacer, so moving the row leaves none.
				helper = guiHelper.BoxSizerHelper(self, sizer=self.settingsSizer)
				control = makeControl(self, helper, spec, getattr(values, spec.key))
				setattr(self, voiceAttribute(spec), control)
				# NVDA's next driver control moves after lastControl in Tab order (settingsDialogs.py
				# :1457-1459), so it stays after this one, as it was made.
				self.lastControl = control
				row = controlRow(control, spec)
				# The 10px bottom border NVDA gives each driver row (settingsDialogs.py:1585-1590), so
				# the last row does not touch NVDA's own controls; _moveSizer keeps it.
				item = self.settingsSizer.GetItem(row)
				item.SetBorder(10)
				item.SetFlag(wx.BOTTOM)
				placements.append((row, previousRow))
			if control is not None:
				previousRow = controlRow(control, spec)
		return previousRow

	def _placePipelineRows(self, placements):
		"""Move each made row after the row made just before it: layout only, windows stay put.

		NVDA inserts each driver row at len(self.sizerDict) - 1 (settingsDialogs.py:1585-1590),
		counting driver rows only, so a row made among them ends up after them; this puts it back.
		"""
		for row, previousRow in placements:
			index = None if previousRow is None else self._rowIndex(self.settingsSizer, previousRow)
			if index is not None:
				_moveSizer(self.settingsSizer, row, index + 1)

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
					values[spec.key] = controlValue(spec, control)
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
