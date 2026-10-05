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
from synthDriverHandler import getSynth
from synthDrivers.WorldVoice import languageDetection
from synthDrivers.WorldVoice.engine import EngineType, get_engine_enabled
from synthDrivers.WorldVoice.pipeline import STAGES
from synthDrivers.WorldVoice.pipeline.settings import pipeline_settings

from .pipelineLog import ask_export, confirm_enable, pipeline_log
from .rolePresenter import RolePanelPresenter
from .utils import guard_errors

addonHandler.initTranslation()

# Labels for the per-stage log switches; the switches themselves come from STAGES.
_LOG_LABELS = {
	"apply_speech_dictionaries": _("apply_speech_dictionaries"),
	"ignore_comma_between_number": _("Ignore comma between number"),
	"number_language": _("Number language"),
	"number_mode": _("Number mode"),
	"chinesespace_wait_factor": _("chinese space wait factor"),
	"item_wait_factor": _("item wait factor"),
	"punctuation_wait_factor": _("punctuation wait factor"),
	"number_wait_factor": _("number wait factor"),
	"speech_viewer": _("speech viewer"),
}


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
	settings = OrderedDict({})
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
					index = 0
					tones.beep(100, 100)
				widget.Selection = index
			else:
				setattr(
					self,
					k + "CheckBox",
					settingsSizerHelper.addItem(wx.CheckBox(self, label=v["label"])),
				)
				value = config.conf["WorldVoice"][self.field].get(k, v.get("default", False))
				getattr(self, k + "CheckBox").SetValue(_as_bool(value))
		return settingsSizerHelper

	def onSave(self) -> bool:
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
		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)
		settings = pipeline_settings.get()

		scope_label = [
			_("All Synthesizers (Global)"),
			_("Only WorldVoice Synthesizer"),
		]
		self._scope_value = ["all", "WorldVoice"]
		self._scope_choice = settingsSizerHelper.addLabeledControl(
			_("Effect Scope:"),
			wx.Choice,
			choices=scope_label,
		)
		try:
			self._scope_choice.Select(self._scope_value.index(settings.scope))
		except ValueError:
			self._scope_choice.Select(0)

		self._ignore_comma_between_number_checkbox = wx.CheckBox(
			self,
			label=_("Ignore comma between number"),
		)
		settingsSizerHelper.addItem(self._ignore_comma_between_number_checkbox)
		self._ignore_comma_between_number_checkbox.SetValue(settings.ignore_comma_between_number)

		number_mode_label = [
			_("value"),
			_("number"),
			_("pair"),
		]
		self.number_mode_value = ["value", "number", "pair"]

		self._number_mode_choice = settingsSizerHelper.addLabeledControl(
			_("Number mode:"),
			wx.Choice,
			choices=number_mode_label,
		)

		try:
			self._number_mode_choice.Select(self.number_mode_value.index(settings.number_mode))
		except ValueError:
			self._number_mode_choice.Select(0)

		self._global_wait_factor_slider = settingsSizerHelper.addLabeledControl(
			_("global wait factor:"),
			wx.Slider,
			value=5,
			minValue=0,
			maxValue=10,
			style=wx.SL_HORIZONTAL,
		)
		self._global_wait_factor_slider.SetValue(settings.global_wait_factor // 10)

		self._number_wait_factor_slider = settingsSizerHelper.addLabeledControl(
			_("number wait factor:"),
			wx.Slider,
			value=50,
			minValue=0,
			maxValue=100,
			style=wx.SL_HORIZONTAL,
		)
		self._number_wait_factor_slider.SetValue(settings.number_wait_factor)

		self._pair_wait_factor_slider = settingsSizerHelper.addLabeledControl(
			_("pair wait factor:"),
			wx.Slider,
			value=50,
			minValue=0,
			maxValue=100,
			style=wx.SL_HORIZONTAL,
		)
		self._pair_wait_factor_slider.SetValue(settings.pair_wait_factor)

		self._item_wait_factor_slider = settingsSizerHelper.addLabeledControl(
			_("item wait factor:"),
			wx.Slider,
			value=50,
			minValue=0,
			maxValue=100,
			style=wx.SL_HORIZONTAL,
		)
		self._item_wait_factor_slider.SetValue(settings.item_wait_factor)

		self._sayall_wait_factor_slider = settingsSizerHelper.addLabeledControl(
			_("sayall wait factor:"),
			wx.Slider,
			value=50,
			minValue=0,
			maxValue=100,
			style=wx.SL_HORIZONTAL,
		)
		self._sayall_wait_factor_slider.SetValue(settings.sayall_wait_factor)

		self._chinesespace_wait_factor_slider = settingsSizerHelper.addLabeledControl(
			_("chinese space wait factor:"),
			wx.Slider,
			value=50,
			minValue=0,
			maxValue=100,
			style=wx.SL_HORIZONTAL,
		)
		self._chinesespace_wait_factor_slider.SetValue(settings.chinesespace_wait_factor)

		self._punctuation_pause_enabled_checkbox = wx.CheckBox(
			self,
			label=_("Enable punctuation pause control"),
		)
		settingsSizerHelper.addItem(self._punctuation_pause_enabled_checkbox)
		self.Bind(
			wx.EVT_CHECKBOX,
			self.onPunctuationPauseEnabledChange,
			self._punctuation_pause_enabled_checkbox,
		)
		self._punctuation_pause_enabled_checkbox.SetValue(settings.punctuation_pause_enabled)

		self._remove_punctuation_characters_checkbox = wx.CheckBox(
			self,
			label=_("Remove configured punctuation at pause points"),
		)
		settingsSizerHelper.addItem(self._remove_punctuation_characters_checkbox)
		self.Bind(
			wx.EVT_CHECKBOX,
			self.onRemovePunctuationCharactersChange,
			self._remove_punctuation_characters_checkbox,
		)
		self._remove_punctuation_characters_checkbox.SetValue(settings.remove_punctuation_characters)

		self._punctuation_wait_factor_slider = settingsSizerHelper.addLabeledControl(
			_("punctuation wait factor:"),
			wx.Slider,
			value=50,
			minValue=0,
			maxValue=100,
			style=wx.SL_HORIZONTAL,
		)
		self._punctuation_wait_factor_slider.SetValue(settings.punctuation_wait_factor)

		self._punctuation_pause_characters_edit = settingsSizerHelper.addLabeledControl(
			_("Punctuation pause characters:"),
			wx.TextCtrl,
		)
		self._punctuation_pause_characters_edit.SetValue(settings.punctuation_pause_characters)
		self.onPunctuationPauseEnabledChange(None)

	def onPunctuationPauseEnabledChange(self, event):
		enabled = self._punctuation_pause_enabled_checkbox.GetValue()
		self._punctuation_wait_factor_slider.Enable(enabled)
		self._punctuation_pause_characters_edit.Enable(
			enabled or self._remove_punctuation_characters_checkbox.GetValue(),
		)

	def onRemovePunctuationCharactersChange(self, event):
		self._punctuation_pause_characters_edit.Enable(
			self._punctuation_pause_enabled_checkbox.GetValue()
			or self._remove_punctuation_characters_checkbox.GetValue(),
		)

	def onSave(self):
		pipeline_settings.update(
			scope=self._scope_value[self._scope_choice.GetCurrentSelection()],
			ignore_comma_between_number=self._ignore_comma_between_number_checkbox.GetValue(),
			number_mode=self.number_mode_value[self._number_mode_choice.GetCurrentSelection()],
			global_wait_factor=self._global_wait_factor_slider.GetValue() * 10,
			number_wait_factor=self._number_wait_factor_slider.GetValue(),
			item_wait_factor=self._item_wait_factor_slider.GetValue(),
			sayall_wait_factor=self._sayall_wait_factor_slider.GetValue(),
			chinesespace_wait_factor=self._chinesespace_wait_factor_slider.GetValue(),
			punctuation_wait_factor=self._punctuation_wait_factor_slider.GetValue(),
			punctuation_pause_enabled=self._punctuation_pause_enabled_checkbox.GetValue(),
			remove_punctuation_characters=self._remove_punctuation_characters_checkbox.GetValue(),
			punctuation_pause_characters=self._punctuation_pause_characters_edit.GetValue(),
			pair_wait_factor=self._pair_wait_factor_slider.GetValue(),
		)


class SpeechRoleSettingsPanel(SettingsPanel):
	title = _("Speech Role")
	NO_SELECT = "no-select"

	def makeSettings(self, sizer):
		self.disable = False
		if not getSynth().name == "WorldVoice":
			infoCtrl = wx.TextCtrl(
				self,
				value=_("Your current speech synthesizer is not WorldVoice."),
				style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE,
			)
			infoCtrl.SetBackgroundColour(self.GetBackgroundColour())
			sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)
			self.disable = True
			return

		self._manager = getSynth()._voiceManager

		synth = getSynth()

		def set_main_voice(name):
			if getSynth().name == "WorldVoice":
				getSynth().voice = name
			config.conf["speech"]["WorldVoice"]["voice"] = name

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

	@property
	def voiceInstance(self):
		voiceName = self._getSelectedVoiceName()
		return self._presenter.voice(voiceName) if voiceName else None

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
				self._voiceNamesByChoiceIndex.index(self._presenter.selected_voice(locale))
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
		if self.disable or getSynth().name != "WorldVoice":
			return
		self._presenter.set_engine_consistency(self._keepEngineConsistentCheckBox.GetValue())
		self._presenter.set_voice_consistency(self._keepConsistentCheckBox.GetValue())
		self._presenter.set_parameter_consistency(self._keepParameterConsistentCheckBox.GetValue())
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
		if not getSynth().name == "WorldVoice":
			infoCtrl = wx.TextCtrl(
				self,
				value=_("Your current speech synthesizer is not WorldVoice."),
				style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE,
			)
			infoCtrl.SetBackgroundColour(self.GetBackgroundColour())
			sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)
			self.disable = True
			return

		self._manager = getSynth()._voiceManager

		self.localesToNames = self._manager.localesToNamesMap
		self._locales = self._manager.languages

		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)
		latinSet = set(languageDetection.ALL_LATIN) & set(l for l in self._locales if len(l) == 2)
		self._latinLocales = sorted(list(latinSet))
		CJKSet = set(languageDetection.CJK) & set(l for l in self._locales if len(l) == 2)
		self._CJKLocales = sorted(list(CJKSet))
		arabicSet = set(languageDetection.ARABIC) & set(l for l in self._locales if len(l) == 2)
		self._arabicLocales = sorted(list(arabicSet))

		self._ignoreNumbersCheckBox = wx.CheckBox(
			self,
			# Translators: Either to ignore or not numbers when language detection is active
			label=_("Ignore numbers when detecting text language"),
		)
		self._ignoreNumbersCheckBox.SetValue(
			config.conf["WorldVoice"]["autoLanguageSwitching"]["ignoreNumbersInLanguageDetection"],
		)
		settingsSizerHelper.addItem(self._ignoreNumbersCheckBox)

		latinChoiceLocaleNames = [self.localesToNames[l] for l in self._latinLocales]
		self._latinChoice = settingsSizerHelper.addLabeledControl(
			_("Language assumed for latin characters:"),
			wx.Choice,
			choices=latinChoiceLocaleNames,
		)
		latinLocale = config.conf["WorldVoice"]["autoLanguageSwitching"]["latinCharactersLanguage"]
		try:
			self._latinChoice.Select(self._latinLocales.index(latinLocale))
		except ValueError:
			self._latinChoice.Select(0)
		if not latinChoiceLocaleNames:
			self._latinChoice.Disable()

		CJKChoiceLocaleNames = [self.localesToNames[l] for l in self._CJKLocales]
		self._CJKChoice = settingsSizerHelper.addLabeledControl(
			_("Language assumed for CJK characters:"),
			wx.Choice,
			choices=CJKChoiceLocaleNames,
		)
		CJKLocale = config.conf["WorldVoice"]["autoLanguageSwitching"]["CJKCharactersLanguage"]
		try:
			self._CJKChoice.Select(self._CJKLocales.index(CJKLocale))
		except ValueError:
			self._CJKChoice.Select(0)
		if not CJKChoiceLocaleNames:
			self._CJKChoice.Disable()

		arabicChoiceLocaleNames = [self.localesToNames[l] for l in self._arabicLocales]
		self._arabicChoice = settingsSizerHelper.addLabeledControl(
			_("Language assumed for arabic characters:"),
			wx.Choice,
			choices=arabicChoiceLocaleNames,
		)
		arabicLocale = config.conf["WorldVoice"]["autoLanguageSwitching"]["arabicCharactersLanguage"]
		try:
			self._arabicChoice.Select(self._arabicLocales.index(arabicLocale))
		except ValueError:
			self._arabicChoice.Select(0)
		if not arabicChoiceLocaleNames:
			self._arabicChoice.Disable()

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
		self._DetectLanguageTiming = config.conf["WorldVoice"]["autoLanguageSwitching"][
			"DetectLanguageTiming"
		]
		try:
			self._DLTChoice.Select(self._DetectLanguageTimingValue.index(self._DetectLanguageTiming))
		except ValueError:
			self._DLTChoice.Select(0)

	def onSave(self):
		if self.disable or not getSynth().name == "WorldVoice":
			return
		config.conf["WorldVoice"]["autoLanguageSwitching"]["ignoreNumbersInLanguageDetection"] = (
			self._ignoreNumbersCheckBox.GetValue()
		)
		if self._latinChoice.IsEnabled():
			config.conf["WorldVoice"]["autoLanguageSwitching"]["latinCharactersLanguage"] = (
				self._latinLocales[self._latinChoice.GetCurrentSelection()]
			)
		if self._CJKChoice.IsEnabled():
			config.conf["WorldVoice"]["autoLanguageSwitching"]["CJKCharactersLanguage"] = self._CJKLocales[
				self._CJKChoice.GetCurrentSelection()
			]
		if self._arabicChoice.IsEnabled():
			config.conf["WorldVoice"]["autoLanguageSwitching"]["arabicCharactersLanguage"] = (
				self._arabicLocales[self._arabicChoice.GetCurrentSelection()]
			)

		previous_DLT = config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"]
		current_DLT = self._DetectLanguageTimingValue[self._DLTChoice.GetCurrentSelection()]
		if current_DLT != previous_DLT:
			config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"] = current_DLT

			# trigger register/unregister language detector
			getSynth().uwv = getSynth().uwv


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
			{eng.name: {"label": eng.label, "default": eng.default_enabled} for eng in EngineType},
		)

		super().makeSettings(group_sizer)

		self.previousActiveEngine = set(
			[
				eng.name
				for eng in EngineType
				if get_engine_enabled(eng.name, config.conf["WorldVoice"]["engine"])
			],
		)

	def isValid(self) -> bool:
		self.activeEngine = set()
		for k, v in self.settings.items():
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
		if self.activeEngine != self.previousActiveEngine:
			# Write the engine flags first so the saved configuration includes them.
			if super().onSave() and self.confirm == wx.YES:
				gui.mainFrame.onSaveConfigurationCommand(None)
				queueHandler.queueFunction(queueHandler.eventQueue, core.restart)


class LogSettingsPanel(BaseSettingsPanel):
	# Translators: Title of a setting dialog.
	title = _("Log Record")
	field = "log"
	settings = OrderedDict(
		(stage.log_key, {"label": _LOG_LABELS.get(stage.log_key, stage.log_key)}) for stage in STAGES
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
		for k, v in self.settings.items():
			getattr(self, k + "CheckBox").Enable()

	def sliderDisable(self):
		for k, v in self.settings.items():
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
		if enabled_after and not enabled_before:
			pipeline_log.enable()
		elif enabled_before and not enabled_after:
			pipeline_log.disable()
			if ask_export():
				wx.CallAfter(pipeline_log.export)
		super().onSave()


class WorldVoiceSettingsDialog(MultiCategorySettingsDialog):
	dialogTitle = _("Settings")
	INITIAL_SIZE = (1000, 480)
	MIN_SIZE = (470, 240)

	def __init__(self, parent):
		if getSynth().name == "WorldVoice":
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
