from collections import OrderedDict

import addonHandler
import config
import core
import gui
import queueHandler
import tones
import wx
from gui import guiHelper
from gui.settingsDialogs import MultiCategorySettingsDialog, SettingsPanel
from logHandler import log
from synthDrivers.WorldVoice import languageDetection
from synthDrivers.WorldVoice.engine import ENGINE_SPECS, get_engine_enabled
from synthDrivers.WorldVoice.languageDetection.settings import detection_settings
from synthDrivers.WorldVoice.pipeline.context import worldvoice_synth
from synthDrivers.WorldVoice.pipeline.registry import LOG_SWITCHES
from synthDrivers.WorldVoice.pipeline.settings import PIPELINE_SETTINGS, pipeline_settings, read_stored
from synthDrivers.WorldVoice.ui.controls import (
	CHANGE_EVENTS,
	apply_dependencies,
	control_value,
	make_control,
	read_control,
)
from synthDrivers.WorldVoice.ui.panelLayout import (
	PIPELINE_PANEL,
	controller_keys,
	panel_specs,
	pipeline_attribute,
)

from .pipelineLog import ask_export, confirm_enable, pipeline_log
from .rolePresenter import RolePanelPresenter
from .utils import guard_errors

addonHandler.initTranslation()

# Labels of the log switches that have no pipeline setting of their own.
_STAGE_LOG_LABELS = {
	# Translators: Label for the pipeline log switch of a speech pipeline stage.
	"apply_speech_dictionaries": _("Apply speech dictionaries"),
	# Translators: Label for the pipeline log switch of a speech pipeline stage.
	"speech_viewer": _("Speech viewer"),
}
# One label per log switch, in LOG_SWITCHES order. A stage named after a pipeline setting uses that
# setting's name: its settings-ring name, else its label (tests keep "&" out of these).
_SETTING_NAMES = {spec.key: spec.display_name or spec.label for spec in PIPELINE_SETTINGS}
_LOG_LABELS = {key: _SETTING_NAMES.get(key) or _STAGE_LOG_LABELS.get(key, key) for key in LOG_SWITCHES}


def got_error_callback(panel):
	dialog = wx.GetTopLevelParent(panel)
	dialog.onCancel(None)
	wx.CallAfter(gui.mainFrame.popupSettingsDialog, type(dialog))


def _as_bool(value):
	if isinstance(value, str):
		return value.lower() not in {"false", "0", ""}
	return bool(value)


class BaseSettingsPanel(SettingsPanel):
	# Translators: Title of a setting dialog.
	title = _("WorldVoice")
	settings = OrderedDict({})  # noqa: RUF012
	field = "WorldVoice"

	def makeSettings(self, settingsSizer, settingsSizerHelper=None):
		if not settingsSizerHelper:
			settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		for k, v in self.settings.items():
			if "options" in v:
				attr = k + "Selection"
				options = v["options"]
				widget = settingsSizerHelper.addLabeledControl(
					v["label"],
					wx.Choice,
					choices=list(options.values()),
				)
				setattr(self, attr, widget)
				try:
					index = list(v["options"].keys()).index(str(config.conf["WorldVoice"][self.field][k]))
				except Exception:  # noqa: BLE001 - a missing or invalid stored value selects the first option
					log.debugWarning(f"Invalid stored WorldVoice {self.field} {k}", exc_info=True)
					index = 0
				widget.Selection = index
			else:
				setattr(
					self,
					k + "CheckBox",
					settingsSizerHelper.addItem(wx.CheckBox(self, label=v["label"])),
				)
				# A value NVDA refuses on read shows the default, so the panel still opens.
				value = read_stored(config.conf["WorldVoice"][self.field], k, v.get("default", False))
				getattr(self, k + "CheckBox").SetValue(_as_bool(value))
		return settingsSizerHelper

	def onSave(self) -> None:
		self._write_settings()

	def _write_settings(self) -> bool:
		"""Write the panel's widgets to config; return False if any value could not be written.

		Every widget is read before anything is written, so a failed read leaves config untouched.
		"""
		try:
			values = {}
			for k, v in self.settings.items():
				if "options" in v:
					widget = getattr(self, k + "Selection")
					values[k] = list(v["options"].keys())[widget.GetSelection()]
				else:
					values[k] = getattr(self, k + "CheckBox").IsChecked()
			for k, value in values.items():
				config.conf["WorldVoice"][self.field][k] = value
		except Exception:
			log.error("WorldVoice: failed to save %s settings", self.field, exc_info=True)
			tones.beep(100, 100)
			return False
		return True


class SpeechPipelinePanel(SettingsPanel):
	title = _("Speech Pipeline")

	def makeSettings(self, sizer):
		# Every control comes from the pipeline settings table, in its order, under one helper
		# so NVDA's spacing separates the rows.
		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)
		settings = pipeline_settings.get()
		specs = self._specs()
		for spec in specs:
			control = make_control(self, settingsSizerHelper, spec, getattr(settings, spec.key))
			setattr(self, pipeline_attribute(spec), control)
		controllers = controller_keys(specs)
		for spec in specs:
			if spec.key in controllers:
				self.Bind(CHANGE_EVENTS[spec.control], self._onControllerChange, self._control(spec))
		self._applyDependencies()

	@staticmethod
	def _specs():
		return panel_specs(PIPELINE_SETTINGS, PIPELINE_PANEL)

	def _control(self, spec):
		return getattr(self, pipeline_attribute(spec), None)

	def _readController(self, key):
		(spec,) = [spec for spec in self._specs() if spec.key == key]
		return read_control(spec, self._control(spec))

	def _applyDependencies(self):
		apply_dependencies(self._specs(), self._readController, self._control)

	def _onControllerChange(self, event):
		self._applyDependencies()

	def onSave(self):
		# The table guard keeps ordering-only entries (NVDA stores them) out of this panel; skip one anyway.
		values = {
			spec.key: control_value(spec, self._control(spec))
			for spec in self._specs()
			if spec.pipeline_config
		}
		# A choice with no selection names no value, so the stored one is kept.
		pipeline_settings.update(**{key: value for key, value in values.items() if value is not None})


class SpeechRoleSettingsPanel(SettingsPanel):
	title = _("Speech Role")
	NO_SELECT = "no-select"

	def makeSettings(self, sizer):
		self.disable = False
		synth = worldvoice_synth()
		if synth is None:
			infoCtrl = wx.TextCtrl(
				self,
				value=_("Your current speech synthesizer is not WorldVoice."),
				style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE,
			)
			infoCtrl.SetBackgroundColour(self.GetBackgroundColour())
			sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)
			self.disable = True
			return

		self._manager = synth.voice_manager

		def set_main_voice(name):
			current = worldvoice_synth()
			if current is not None:
				current.voice = name
			config.conf["speech"][synth.name]["voice"] = name

		self._presenter = RolePanelPresenter(
			self._manager,
			speech_section=lambda: config.conf["speech"][synth.name],
			set_main_voice=set_main_voice,
		)
		self.Bind(wx.EVT_WINDOW_DESTROY, self._onDestroy)
		locales = self._presenter.locales()
		self._locales = [locale for locale, _name in locales]
		self._voiceNamesByChoiceIndex = []

		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)
		helpLabel = wx.StaticText(
			self,
			label=_("Select a language, and then configure the voice to be used:"),
		)
		helpLabel.Wrap(self.GetSize()[0])
		settingsSizerHelper.addItem(helpLabel)
		self._localesChoice = settingsSizerHelper.addLabeledControl(
			_("Locale Name:"),
			wx.Choice,
			choices=[name for _locale, name in locales],
		)
		self.Bind(wx.EVT_CHOICE, self.onLocaleChanged, self._localesChoice)
		self._voicesChoice = settingsSizerHelper.addLabeledControl(_("Voice Name:"), wx.Choice, choices=[])
		self.Bind(wx.EVT_CHOICE, self.onVoiceChange, self._voicesChoice)
		self._variantsChoice = settingsSizerHelper.addLabeledControl(_("Variant:"), wx.Choice, choices=[])
		self.Bind(wx.EVT_CHOICE, self.onVariantChange, self._variantsChoice)

		self._rateSlider = settingsSizerHelper.addLabeledControl(
			_("&Rate:"),
			wx.Slider,
			value=50,
			minValue=0,
			maxValue=100,
			style=wx.SL_HORIZONTAL,
		)
		self.Bind(wx.EVT_SLIDER, self.onSpeechRateSliderScroll, self._rateSlider)

		self._rateBoostCheckBox = wx.CheckBox(
			self,
			label=_("Rate boost"),
		)
		settingsSizerHelper.addItem(self._rateBoostCheckBox)
		self.Bind(wx.EVT_CHECKBOX, self.onRateBoostChange, self._rateBoostCheckBox)

		self._pitchSlider = settingsSizerHelper.addLabeledControl(
			_("&Pitch:"),
			wx.Slider,
			value=50,
			minValue=0,
			maxValue=100,
			style=wx.SL_HORIZONTAL,
		)
		self.Bind(wx.EVT_SLIDER, self.onPitchSliderScroll, self._pitchSlider)

		self._inflectionSlider = settingsSizerHelper.addLabeledControl(
			_("I&nflection:"),
			wx.Slider,
			value=50,
			minValue=0,
			maxValue=100,
			style=wx.SL_HORIZONTAL,
		)
		self.Bind(wx.EVT_SLIDER, self.onInflectionSliderScroll, self._inflectionSlider)

		self._volumeSlider = settingsSizerHelper.addLabeledControl(
			_("V&olume:"),
			wx.Slider,
			value=50,
			minValue=0,
			maxValue=100,
			style=wx.SL_HORIZONTAL,
		)
		self.Bind(wx.EVT_SLIDER, self.onVolumeSliderScroll, self._volumeSlider)

		self.sliderDisable()

		self._keepEngineConsistentCheckBox = wx.CheckBox(
			self,
			label=_("Keep main engine and locale engine consistent"),
		)
		self._keepEngineConsistentCheckBox.SetValue(self._presenter.keep_engine)
		settingsSizerHelper.addItem(self._keepEngineConsistentCheckBox)
		self.Bind(wx.EVT_CHECKBOX, self.onKeepEngineConsistentChange, self._keepEngineConsistentCheckBox)

		self._keepConsistentCheckBox = wx.CheckBox(
			self,
			label=_("Keep main speech role and locale speech role consistent"),
		)
		self._keepConsistentCheckBox.SetValue(self._presenter.keep_voice)
		settingsSizerHelper.addItem(self._keepConsistentCheckBox)
		self.Bind(wx.EVT_CHECKBOX, self.onKeepVoiceConsistentChange, self._keepConsistentCheckBox)

		self._keepParameterConsistentCheckBox = wx.CheckBox(
			self,
			label=_("Keep parameter settings consistent between different speech roles"),
		)
		self._keepParameterConsistentCheckBox.SetValue(self._presenter.keep_parameters)
		settingsSizerHelper.addItem(self._keepParameterConsistentCheckBox)
		self.Bind(
			wx.EVT_CHECKBOX,
			self.onKeepParameterConsistentChange,
			self._keepParameterConsistentCheckBox,
		)

	def postInit(self):
		if self.disable:
			return

		self._updateVoicesSelection()
		self._localesChoice.SetFocus()

	def _getSelectedVoiceName(self):
		index = self._voicesChoice.GetCurrentSelection()
		if index == wx.NOT_FOUND:
			return ""
		if index < 0 or index >= len(self._voiceNamesByChoiceIndex):
			return ""
		return self._voiceNamesByChoiceIndex[index]

	def _currentLocale(self):
		index = self._localesChoice.GetCurrentSelection()
		return self._locales[index] if 0 <= index < len(self._locales) else None

	def _updateVoicesSelection(self):
		locale = self._currentLocale()
		if locale is None:
			self._voiceNamesByChoiceIndex = []
			self._voicesChoice.SetItems([])
			return
		voices = self._presenter.voices(locale)
		self._voiceNamesByChoiceIndex = [""] + [name for name, _label in voices]
		self._voicesChoice.SetItems([self.NO_SELECT] + [label for _name, label in voices])
		try:
			self._voicesChoice.Select(
				self._voiceNamesByChoiceIndex.index(self._presenter.selected_voice(locale)),
			)
		except ValueError:
			self._voicesChoice.Select(0)
		self._showVoice(self._getSelectedVoiceName())

	def _showVoice(self, voiceName):
		if voiceName:
			voiceInstance = self._presenter.voice(voiceName)
			self._rateSlider.SetValue(voiceInstance.rate)
			self._pitchSlider.SetValue(voiceInstance.pitch)
			self._volumeSlider.SetValue(voiceInstance.volume)
			self._inflectionSlider.SetValue(voiceInstance.inflection)
			self._rateBoostCheckBox.SetValue(voiceInstance.rateBoost)
		self._updateVariantsSelection()
		self.sliderDisable()
		self.sliderEnable()

	def _updateVariantsSelection(self):
		voiceName = self._getSelectedVoiceName()
		if not voiceName:
			self._variantsChoice.SetItems([])
			return
		variants = self._presenter.variants(voiceName)
		self._variantsChoice.SetItems(variants)
		try:
			self._variantsChoice.Select(variants.index(self._presenter.voice(voiceName).variant))
		except ValueError:
			self._variantsChoice.Select(0)

	@guard_errors(callback=got_error_callback)
	def onLocaleChanged(self, event):
		self._updateVoicesSelection()

	@guard_errors(callback=got_error_callback)
	def onVoiceChange(self, event):
		locale = self._currentLocale()
		if locale is None:
			return
		voiceName = self._getSelectedVoiceName()
		self._presenter.select_voice(locale, voiceName)
		self._showVoice(voiceName)

	@guard_errors(callback=got_error_callback)
	def onVariantChange(self, event):
		voiceName = self._getSelectedVoiceName()
		if voiceName:
			self._presenter.set_variant(voiceName, self._variantsChoice.GetStringSelection())

	@guard_errors(callback=got_error_callback)
	def onKeepEngineConsistentChange(self, event):
		self._presenter.set_engine_consistency(self._keepEngineConsistentCheckBox.GetValue())
		locales = self._presenter.locales()
		self._locales = [locale for locale, _name in locales]
		self._localesChoice.SetItems([name for _locale, name in locales])
		self._updateVoicesSelection()

	@guard_errors(callback=got_error_callback)
	def onKeepVoiceConsistentChange(self, event):
		self._presenter.set_voice_consistency(self._keepConsistentCheckBox.GetValue())

	@guard_errors(callback=got_error_callback)
	def onKeepParameterConsistentChange(self, event):
		self._presenter.set_parameter_consistency(self._keepParameterConsistentCheckBox.GetValue())
		self._showVoice(self._getSelectedVoiceName())

	def sliderEnable(self):
		voiceName = self._getSelectedVoiceName()
		if voiceName:
			supportedSettings = self._presenter.capabilities(voiceName)
			self._rateSlider.Enable()
			self._pitchSlider.Enable()
			self._volumeSlider.Enable()
			if "inflection" in supportedSettings:
				self._inflectionSlider.Enable()
			if "rateBoost" in supportedSettings:
				self._rateBoostCheckBox.Enable()

	def sliderDisable(self):
		self._rateSlider.Disable()
		self._pitchSlider.Disable()
		self._volumeSlider.Disable()
		self._inflectionSlider.Disable()
		self._rateBoostCheckBox.Disable()

	def _setParameter(self, parameter, value):
		voiceName = self._getSelectedVoiceName()
		if voiceName:
			self._presenter.set_parameter(voiceName, parameter, value)

	@guard_errors(callback=got_error_callback)
	def onSpeechRateSliderScroll(self, event):
		self._setParameter("rate", self._rateSlider.GetValue())

	@guard_errors(callback=got_error_callback)
	def onPitchSliderScroll(self, event):
		self._setParameter("pitch", self._pitchSlider.GetValue())

	@guard_errors(callback=got_error_callback)
	def onVolumeSliderScroll(self, event):
		self._setParameter("volume", self._volumeSlider.GetValue())

	@guard_errors(callback=got_error_callback)
	def onInflectionSliderScroll(self, event):
		self._setParameter("inflection", self._inflectionSlider.GetValue())

	@guard_errors(callback=got_error_callback)
	def onRateBoostChange(self, event):
		self._setParameter("rateBoost", self._rateBoostCheckBox.GetValue())

	@guard_errors(callback=lambda self: None)
	def onDiscard(self):
		if self.disable:
			return
		self._presenter.discard()

	def _onDestroy(self, event):
		# Child control destruction also bubbles through the panel.
		if event.GetEventObject() is self:
			self._presenter.close()
		event.Skip()

	def onSave(self):
		# The dialog is not modal: the synth may have changed since it opened.
		current = worldvoice_synth()
		if self.disable or current is None:
			return
		if current.voice_manager is not self._manager:
			# NVDA rebuilt WorldVoice (e.g. after an audio device change); the panel edits the old one.
			log.warning("WorldVoice restarted while the voice settings were open; role settings not saved")
			return
		try:
			self._presenter.apply()
		except Exception as error:
			log.error("Failed to save voice settings", exc_info=True)
			gui.messageBox(
				_(
					"An unexpected error occurred while processing your action.\n\n"
					"Details: {err}\n\n"
					"A full stack trace has been written to the NVDA log.",
				).format(err=str(error)),
				_("WorldVoice Setting Dialog - Error"),
				wx.OK | wx.ICON_ERROR,
			)
			# NVDA's settings dialog aborts the save and stays open only on ValueError.
			raise ValueError("WorldVoice voice settings were not saved") from error


class UnicodeDetectionSettingsPanel(SettingsPanel):
	title = _("Unicode Detection")

	def makeSettings(self, sizer):
		self.disable = False
		synth = worldvoice_synth()
		if synth is None:
			infoCtrl = wx.TextCtrl(
				self,
				value=_("Your current speech synthesizer is not WorldVoice."),
				style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE,
			)
			infoCtrl.SetBackgroundColour(self.GetBackgroundColour())
			sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)
			self.disable = True
			return

		self._manager = synth.voice_manager

		self.localesToNames = self._manager.localesToNamesMap
		self._locales = self._manager.languages
		self._detection = detection_settings.get()

		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)

		self._scriptChoices = {
			script: self._add_script_choice(settingsSizerHelper, script, label)
			for script, label in self._script_labels().items()
		}

		DetectLanguageTimingLabel = [
			_("Before NVDA processes speech commands"),
			_("After NVDA processes speech commands"),
		]
		self._DetectLanguageTimingValue = ["before", "after"]
		self._DLTChoice = settingsSizerHelper.addLabeledControl(
			_("Language detection timing:"),
			wx.Choice,
			choices=DetectLanguageTimingLabel,
		)
		self._DetectLanguageTiming = self._detection.timing
		try:
			self._DLTChoice.Select(self._DetectLanguageTimingValue.index(self._DetectLanguageTiming))
		except ValueError:
			self._DLTChoice.Select(0)

	def _script_labels(self):
		return {
			# Translators: Label of the choice of the language assumed for Latin letters.
			"Latin": _("Language assumed for latin characters:"),
			# Translators: Label of the choice of the language assumed for Han characters (CJK ideographs).
			"Han": _("Language assumed for CJK characters:"),
			# Translators: Label of the choice of the language assumed for Arabic letters.
			"Arabic": _("Language assumed for arabic characters:"),
			# Translators: Label of the choice of the language assumed for Cyrillic letters.
			"Cyrillic": _("Language assumed for cyrillic characters:"),
			# Translators: Label of the choice of the language assumed for Devanagari letters.
			"Devanagari": _("Language assumed for devanagari characters:"),
		}

	def _add_script_choice(self, helper, script, label):
		"""A choice of the available two-letter languages written in script."""
		candidates = set(languageDetection.SCRIPT_LANGUAGES[script])
		locales = sorted(candidates & {locale for locale in self._locales if len(locale) == 2})
		names = [self.localesToNames[locale] for locale in locales]
		choice = helper.addLabeledControl(label, wx.Choice, choices=names)
		stored = self._detection.script_language[script]
		try:
			choice.Select(locales.index(stored))
		except ValueError:
			choice.Select(0)
		if not names:
			choice.Disable()
		return choice, locales

	def onSave(self):
		if self.disable or worldvoice_synth() is None:
			return
		# The driver subscribes to these settings and re-registers detection when the timing changes.
		detection_settings.update(
			script_language={
				script: locales[choice.GetCurrentSelection()]
				for script, (choice, locales) in self._scriptChoices.items()
				if choice.IsEnabled()
			},
			timing=self._DetectLanguageTimingValue[self._DLTChoice.GetCurrentSelection()],
		)


class SpeechEngineSettingsPanel(BaseSettingsPanel):
	# Translators: Title of a setting dialog.
	title = _("Speech Engine")
	field = "engine"

	def makeSettings(self, sizer):
		infoCtrl = wx.TextCtrl(
			self,
			value=_("Please select one or more speech engines to enable."),
			style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE,
		)
		infoCtrl.SetBackgroundColour(self.GetBackgroundColour())
		sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)

		group_sizer = wx.StaticBoxSizer(
			wx.StaticBox(self, label=_("Select Speech Engines to Enable")),
			wx.VERTICAL,
		)
		sizer.Add(group_sizer, proportion=1, flag=wx.EXPAND)

		self.settings = OrderedDict(
			{eng.name: {"label": eng.label, "default": eng.default_enabled} for eng in ENGINE_SPECS},
		)

		super().makeSettings(group_sizer)

		self.previousActiveEngine = {
			eng.name
			for eng in ENGINE_SPECS
			if get_engine_enabled(eng.name, config.conf["WorldVoice"]["engine"])
		}

	def isValid(self) -> bool:
		self.activeEngine = set()
		for k in self.settings:
			if getattr(self, k + "CheckBox").IsChecked():
				self.activeEngine.add(k)

		if len(self.activeEngine) == 0:
			gui.messageBox(
				# Translators: The message displayed
				_("Changes to speech-engine settings can’t be saved because no speech engine is enabled."),
				# Translators: The title of the dialog
				_("No Speech Engine Enabled"),
				wx.OK | wx.ICON_WARNING,
				self,
			)
			return False
		if self.activeEngine != self.previousActiveEngine:
			self.confirm = gui.messageBox(
				# Translators: The message displayed
				_(
					"To enable or disable the speech engine, NVDA needs to save your configuration and restart. Would you like to restart now?",
				),
				# Translators: The title of the dialog
				_("Speech Engine Change"),
				wx.YES | wx.NO | wx.CANCEL | wx.ICON_WARNING,
				self,
			)
			if self.confirm == wx.CANCEL:
				return False
		return True

	def onSave(self):
		# Write the engine flags first so the saved configuration includes them.
		if (
			self.activeEngine != self.previousActiveEngine
			and self._write_settings()
			and self.confirm == wx.YES
		):
			gui.mainFrame.onSaveConfigurationCommand(None)
			queueHandler.queueFunction(queueHandler.eventQueue, core.restart)


class LogSettingsPanel(BaseSettingsPanel):
	# Translators: Title of a setting dialog.
	title = _("Log Record")
	field = "log"
	settings = OrderedDict(  # noqa: RUF012
		(key, {"label": _LOG_LABELS[key]}) for key in LOG_SWITCHES
	)

	def makeSettings(self, sizer):
		self._enable_checkbox = wx.CheckBox(
			self,
			label=_("Enable logging of WorldVoice’s speech pipeline"),
		)
		sizer.Add(self._enable_checkbox, proportion=1, flag=wx.EXPAND)
		group_sizer = wx.StaticBoxSizer(
			wx.StaticBox(self, label=_("Select Speech Pipelines to Enable")),
			wx.VERTICAL,
		)
		sizer.Add(group_sizer, proportion=1, flag=wx.EXPAND)

		self.Bind(wx.EVT_CHECKBOX, self.onEnableCheckboxChange, self._enable_checkbox)
		self._enable_checkbox.SetValue(pipeline_log.enabled)
		super().makeSettings(group_sizer)
		self.onEnableCheckboxChange(None)

	def onEnableCheckboxChange(self, event):
		if self._enable_checkbox.GetValue():
			self.sliderEnable()
		else:
			self.sliderDisable()

	def sliderEnable(self):
		for k in self.settings:
			getattr(self, k + "CheckBox").Enable()

	def sliderDisable(self):
		for k in self.settings:
			getattr(self, k + "CheckBox").Disable()

	def isValid(self) -> bool:
		if self._enable_checkbox.GetValue() and not pipeline_log.enabled:
			answer = confirm_enable(allow_cancel=True)
			if answer == wx.CANCEL:
				self._enable_checkbox.SetValue(False)
				self.onEnableCheckboxChange(None)
				return False
			if answer != wx.YES:
				# "No" keeps logging off; show that instead of a checked box.
				self._enable_checkbox.SetValue(False)
				self.onEnableCheckboxChange(None)
		return True

	def onSave(self):
		enabled_before = pipeline_log.enabled
		enabled_after = self._enable_checkbox.GetValue()
		# Written on every save, like the stage switches (decided by the user, 2026-10-22,
		# fix/uniform-settings-save): NVDA skips an unchanged value and replaces a refused one.
		# isValid already confirmed turning logging on, or unticked the box when it was declined.
		if enabled_after:
			pipeline_log.enable()
		else:
			pipeline_log.disable()
		if enabled_before and not enabled_after and ask_export():
			wx.CallAfter(pipeline_log.export)
		self._write_settings()


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
