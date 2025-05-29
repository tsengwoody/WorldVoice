from collections import defaultdict, OrderedDict
import importlib

import wx
import addonHandler
import config
import core
import gui
from gui import guiHelper
from gui.settingsDialogs import MultiCategorySettingsDialog, SettingsPanel
import languageHandler
from logHandler import log
import queueHandler
from synthDriverHandler import getSynth
from synthDrivers.WorldVoice import languageDetection
from synthDrivers.WorldVoice.pipeline import order_move_to_start_register, static_register, dynamic_register, unregister, pl
from synthDrivers.WorldVoice.voice.engine import EngineType
import tones

from .utils import guard_errors


addonHandler.initTranslation()


def got_error_callback(self):
	dialog_class = self.Parent.Parent.__class__
	dialog_class.wvd.onCancel(None)
	wx.CallAfter(gui.mainFrame.popupSettingsDialog, dialog_class)


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
				widget = settingsSizerHelper.addLabeledControl(v["label"], wx.Choice, choices=list(options.values()))
				setattr(self, attr, widget)
				try:
					index = list(v["options"].keys()).index(str(config.conf["WorldVoice"][self.field][k]))
				except BaseException:
					index = 0
					tones.beep(100, 100)
				widget.Selection = index
			else:
				setattr(self, k + "CheckBox", settingsSizerHelper.addItem(wx.CheckBox(self, label=v["label"])))
				value = config.conf["WorldVoice"][self.field][k]
				getattr(self, k + "CheckBox").SetValue(value)
		return settingsSizerHelper

	def onSave(self):
		try:
			for k, v in self.settings.items():
				if "options" in v:
					attr = k + "Selection"
					widget = getattr(self, attr)
					config.conf["WorldVoice"][self.field][k] = list(v["options"].keys())[widget.GetSelection()]
				else:
					config.conf["WorldVoice"][self.field][k] = getattr(self, k + "CheckBox").IsChecked()
		except BaseException:
			for k, v in self.settings.items():
				if "options" in v:
					config.conf["WorldVoice"][self.field][k] = list(v["options"].keys())[0]
				else:
					config.conf["WorldVoice"][self.field][k] = True
			tones.beep(100, 100)


class SpeechPipelinePanel(SettingsPanel):
	title = _("Speech Pipeline")

	def makeSettings(self, sizer):
		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)

		scope_label = [
			_("All Synthesizers (Global)"),
			_("Only WorldVoice Synthesizer"),
		]
		self._scope_value = ["all", "WorldVoice"]
		self._scope_choice = settingsSizerHelper.addLabeledControl(
			_("Effect Scope:"),
			wx.Choice,
			choices=scope_label
		)
		self._scope = config.conf["WorldVoice"]["pipeline"]["scope"]
		try:
			self._scope_choice.Select(self._scope_value.index(self._scope))
		except ValueError:
			self._scope_choice.Select(0)

		self._ignore_comma_between_number_checkbox = wx.CheckBox(
			self,
			label=_("Ignore comma between number")
		)
		settingsSizerHelper.addItem(self._ignore_comma_between_number_checkbox)
		self.Bind(wx.EVT_CHECKBOX, self.onIgnoreCommaBetweenNumberCheckboxChange, self._ignore_comma_between_number_checkbox)
		self._ignore_comma_between_number_checkbox.SetValue(config.conf["WorldVoice"]["pipeline"]["ignore_comma_between_number"])

		number_mode_label = [
			_("value"),
			_("number"),
		]
		self.number_mode_value = ["value", "number"]

		self._number_mode_choice = settingsSizerHelper.addLabeledControl(
			_("Number mode:"),
			wx.Choice,
			choices=number_mode_label
		)

		try:
			self._number_mode_choice.Select(self.number_mode_value.index(config.conf["WorldVoice"]["pipeline"]["number_mode"]))
		except ValueError:
			self._number_mode_choice.Select(0)

		self._global_wait_factor_slider = settingsSizerHelper.addLabeledControl(_("global wait factor:"), wx.Slider, value=5, minValue=0, maxValue=10, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onGlobalWaitFactorSliderScroll, self._global_wait_factor_slider)
		self._global_wait_factor_slider.SetValue(config.conf["WorldVoice"]["pipeline"]["global_wait_factor"] // 10)

		self._number_wait_factor_slider = settingsSizerHelper.addLabeledControl(_("number wait factor:"), wx.Slider, value=50, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onNumberWaitFactorSliderScroll, self._number_wait_factor_slider)
		self._number_wait_factor_slider.SetValue(config.conf["WorldVoice"]["pipeline"]["number_wait_factor"])

		self._item_wait_factor_slider = settingsSizerHelper.addLabeledControl(_("item wait factor:"), wx.Slider, value=50, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onItemWaitFactorSliderScroll, self._item_wait_factor_slider)
		self._item_wait_factor_slider.SetValue(config.conf["WorldVoice"]["pipeline"]["item_wait_factor"])

		self._sayall_wait_factor_slider = settingsSizerHelper.addLabeledControl(_("sayall wait factor:"), wx.Slider, value=50, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onSayallWaitFactorSliderScroll, self._sayall_wait_factor_slider)
		self._sayall_wait_factor_slider.SetValue(config.conf["WorldVoice"]["pipeline"]["sayall_wait_factor"])

		self._chinesespace_wait_factor_slider = settingsSizerHelper.addLabeledControl(_("chinese space wait factor:"), wx.Slider, value=50, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onChinesespaceWaitFactorSliderScroll, self._chinesespace_wait_factor_slider)
		self._chinesespace_wait_factor_slider.SetValue(config.conf["WorldVoice"]["pipeline"]["chinesespace_wait_factor"])

	def onScopeSelectionChange(self, event):
		value = self._scope_value[self._scope_choice.GetCurrentSelection()]
		if value == "all":
			if getSynth().name != "WorldVoice":
				static_register()
				dynamic_register()
				order_move_to_start_register()
		elif value == "WorldVoice":
			if getSynth().name != "WorldVoice":
				unregister()

	def onIgnoreCommaBetweenNumberCheckboxChange(self, event):
		pass

	def onGlobalWaitFactorSliderScroll(self, event):
		pass

	def onNumberWaitFactorSliderScroll(self, event):
		pass

	def onItemWaitFactorSliderScroll(self, event):
		pass

	def onSayallWaitFactorSliderScroll(self, event):
		pass

	def onChinesespaceWaitFactorSliderScroll(self, event):
		pass

	def sliderEnable(self):
		self._ignore_comma_between_number_checkbox.Enable()
		self._number_mode_choice.Enable()
		self._global_wait_factor_slider.Enable()
		self._number_wait_factor_slider.Enable()
		self._item_wait_factor_slider.Enable()
		self._sayall_wait_factor_slider.Enable()
		self._chinesespace_wait_factor_slider.Enable()

	def sliderDisable(self):
		self._ignore_comma_between_number_checkbox.Disable()
		self._number_mode_choice.Disable()
		self._global_wait_factor_slider.Disable()
		self._number_wait_factor_slider.Disable()
		self._item_wait_factor_slider.Disable()
		self._sayall_wait_factor_slider.Disable()
		self._chinesespace_wait_factor_slider.Disable()

	def onSave(self):
		config.conf["WorldVoice"]["pipeline"]["scope"] = self._scope_value[self._scope_choice.GetCurrentSelection()]

		config.conf["WorldVoice"]["pipeline"]["ignore_comma_between_number"] = self._ignore_comma_between_number_checkbox.GetValue()
		config.conf["WorldVoice"]["pipeline"]["number_mode"] = self.number_mode_value[self._number_mode_choice.GetCurrentSelection()]
		config.conf["WorldVoice"]["pipeline"]["global_wait_factor"] = self._global_wait_factor_slider.GetValue() * 10
		config.conf["WorldVoice"]["pipeline"]["number_wait_factor"] = self._number_wait_factor_slider.GetValue()
		config.conf["WorldVoice"]["pipeline"]["item_wait_factor"] = self._item_wait_factor_slider.GetValue()
		config.conf["WorldVoice"]["pipeline"]["sayall_wait_factor"] = self._sayall_wait_factor_slider.GetValue()
		config.conf["WorldVoice"]["pipeline"]["chinesespace_wait_factor"] = self._chinesespace_wait_factor_slider.GetValue()

		self.onScopeSelectionChange(None)

		if getSynth().name == 'WorldVoice':
			getSynth().cni = config.conf["WorldVoice"]["pipeline"]["ignore_comma_between_number"]
			getSynth().nummod = self.number_mode_value[self._number_mode_choice.GetCurrentSelection()]
			getSynth().globalwaitfactor = config.conf["WorldVoice"]["pipeline"]["global_wait_factor"]
			getSynth().numberwaitfactor = config.conf["WorldVoice"]["pipeline"]["number_wait_factor"]
			getSynth().itemwaitfactor = config.conf["WorldVoice"]["pipeline"]["item_wait_factor"]
			getSynth().sayallwaitfactor = config.conf["WorldVoice"]["pipeline"]["sayall_wait_factor"]
			getSynth().chinesespacewaitfactor = config.conf["WorldVoice"]["pipeline"]["chinesespace_wait_factor"]
			getSynth().saveSettings()
		else:
			config.conf["speech"]["WorldVoice"]["cni"] = config.conf["WorldVoice"]["pipeline"]["ignore_comma_between_number"]
			config.conf["speech"]["WorldVoice"]["cni"] = config.conf["WorldVoice"]["pipeline"]["ignore_comma_between_number"]
			config.conf["speech"]["WorldVoice"]["nummod"] = self.number_mode_value[self._number_mode_choice.GetCurrentSelection()]
			config.conf["speech"]["WorldVoice"]["globalwaitfactor"] = config.conf["WorldVoice"]["pipeline"]["global_wait_factor"]
			config.conf["speech"]["WorldVoice"]["numberwaitfactor"] = config.conf["WorldVoice"]["pipeline"]["number_wait_factor"]
			config.conf["speech"]["WorldVoice"]["itemwaitfactor"] = config.conf["WorldVoice"]["pipeline"]["item_wait_factor"]
			config.conf["speech"]["WorldVoice"]["sayallwaitfactor"] = config.conf["WorldVoice"]["pipeline"]["sayall_wait_factor"]
			config.conf["speech"]["WorldVoice"]["chinesespacewaitfactor"] = config.conf["WorldVoice"]["pipeline"]["chinesespace_wait_factor"]


class SpeechRoleSettingsPanel(SettingsPanel):
	title = _("Speech Role")

	def makeSettings(self, sizer):
		self.disable = False
		if not getSynth().name == 'WorldVoice':
			infoCtrl = wx.TextCtrl(
				self,
				value=_('Your current speech synthesizer is not WorldVoice.'),
				style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE
			)
			infoCtrl.SetBackgroundColour(self.GetBackgroundColour())
			sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)
			self.disable = True
			return

		self._manager = getSynth()._voiceManager
		self.ready = self._manager.ready()
		if not self.ready:
			infoCtrl = wx.TextCtrl(
				self,
				value=_('Your current speech synthesizer is not ready.'),
				style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE
			)
			infoCtrl.SetBackgroundColour(self.GetBackgroundColour())
			sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)
			self.disable = True
			return

		self._localeToVoices = self._manager.localeToVoicesMap
		self.localesToNames = self._manager.localesToNamesMap
		self._locales = self._manager.languages

		self._dataToPercist = defaultdict(lambda: {})

		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)
		helpLabel = wx.StaticText(self, label=_("Select a language, and then configure the voice to be used:"))
		helpLabel.Wrap(self.GetSize()[0])
		settingsSizerHelper.addItem(helpLabel)
		localeNames = [self.localesToNames[l] for l in self._locales]
		self._localesChoice = settingsSizerHelper.addLabeledControl(_("Locale Name:"), wx.Choice, choices=localeNames)
		self.Bind(wx.EVT_CHOICE, self.onLocaleChanged, self._localesChoice)
		self._voicesChoice = settingsSizerHelper.addLabeledControl(_("Voice Name:"), wx.Choice, choices=[])
		self.Bind(wx.EVT_CHOICE, self.onVoiceChange, self._voicesChoice)
		self._variantsChoice = settingsSizerHelper.addLabeledControl(_("Variant:"), wx.Choice, choices=[])
		self.Bind(wx.EVT_CHOICE, self.onVariantChange, self._variantsChoice)

		self._rateSlider = settingsSizerHelper.addLabeledControl(_("&Rate:"), wx.Slider, value=50, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onSpeechRateSliderScroll, self._rateSlider)

		self._rateBoostCheckBox = wx.CheckBox(
			self,
			label=_("Rate boost")
		)
		settingsSizerHelper.addItem(self._rateBoostCheckBox)
		self.Bind(wx.EVT_CHECKBOX, self.onRateBoostChange, self._rateBoostCheckBox)

		self._pitchSlider = settingsSizerHelper.addLabeledControl(_("&Pitch:"), wx.Slider, value=50, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onPitchSliderScroll, self._pitchSlider)

		self._inflectionSlider = settingsSizerHelper.addLabeledControl(_("I&nflection:"), wx.Slider, value=50, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onInflectionSliderScroll, self._inflectionSlider)

		self._volumeSlider = settingsSizerHelper.addLabeledControl(_("V&olume:"), wx.Slider, value=50, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onVolumeSliderScroll, self._volumeSlider)

		self.sliderDisable()

		self._keepEngineConsistentCheckBox = wx.CheckBox(
			self,
			label=_("Keep main engine and locale engine consistent")
		)
		self._keepEngineConsistentCheckBox.SetValue(config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"])
		settingsSizerHelper.addItem(self._keepEngineConsistentCheckBox)
		self.Bind(wx.EVT_CHECKBOX, self.onKeepEngineConsistentChange, self._keepEngineConsistentCheckBox)

		self._keepConsistentCheckBox = wx.CheckBox(
			self,
			label=_("Keep main voice and locale voice consistent")
		)
		self._keepConsistentCheckBox.SetValue(config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"])
		settingsSizerHelper.addItem(self._keepConsistentCheckBox)

		self._keepParameterConsistentCheckBox = wx.CheckBox(
			self,
			label=_("Keep main parameter and locale parameter consistent")
		)
		self._keepParameterConsistentCheckBox.SetValue(config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"])
		settingsSizerHelper.addItem(self._keepParameterConsistentCheckBox)
		self.Bind(wx.EVT_CHECKBOX, self.onKeepParameterConsistentChange, self._keepParameterConsistentCheckBox)

	def postInit(self):
		if self.disable:
			return

		self._updateVoicesSelection()
		self._localesChoice.SetFocus()

	@property
	def voiceInstance(self):
		voiceName = self._voicesChoice.GetStringSelection()
		if voiceName == '' or voiceName == 'no-select':
			return
		voiceInstance = self._manager.getVoiceInstance(voiceName)
		return voiceInstance

	def _updateVoicesSelection(self):
		localeIndex = self._localesChoice.GetCurrentSelection()
		if localeIndex < 0:
			self._voicesChoice.SetItems([])
		else:
			locale = self._locales[localeIndex]
			voices = ["no-select"] + self._localeToVoices[locale]
			self._voicesChoice.SetItems(voices)
			if locale in config.conf["WorldVoice"]["role"]:
				try:
					voice = config.conf["WorldVoice"]["role"][locale]["voice"]
				except BaseException:
					self._voicesChoice.Select(0)
					self.onVoiceChange(None)
					return
				if voice:
					try:
						self._voicesChoice.Select(voices.index(voice))
					except ValueError:
						self._voicesChoice.Select(0)
					self.onVoiceChange(None)
			else:
				self._voicesChoice.Select(0)
				self.onVoiceChange(None)

	def _updateVariantsSelection(self):
		voiceName = self._voicesChoice.GetStringSelection()
		if voiceName != "no-select":
			voiceInstance = self._manager.getVoiceInstance(voiceName)
			variants = [i["id"] for i in voiceInstance.variants if i != '']
			variants = ['default'] + variants
			variant = voiceInstance.variant
			self._variantsChoice.SetItems(variants)
			try:
				self._variantsChoice.Select(variants.index(variant))
			except ValueError:
				self._variantsChoice.Select(0)
		else:
			self._variantsChoice.SetItems([])

	@guard_errors(callback=got_error_callback)
	def onLocaleChanged(self, event):
		self._updateVoicesSelection()

	@guard_errors(callback=got_error_callback)
	def onVoiceChange(self, event):
		localeIndex = self._localesChoice.GetCurrentSelection()
		locale = self._locales[localeIndex]
		voiceName = self._voicesChoice.GetStringSelection()
		if voiceName != "no-select":
			self._dataToPercist[locale]["voice"] = self._voicesChoice.GetStringSelection()
			voiceInstance = self._manager.getVoiceInstance(voiceName)
			if self._keepParameterConsistentCheckBox.GetValue():
				mainVoiceInstance = self._manager._defaultVoiceInstance
				voiceInstance.rate = mainVoiceInstance.rate
				voiceInstance.pitch = mainVoiceInstance.pitch
				voiceInstance.volume = mainVoiceInstance.volume
				voiceInstance.inflection = mainVoiceInstance.inflection
				voiceInstance.rateBoost = mainVoiceInstance.rateBoost
			self._rateSlider.SetValue(voiceInstance.rate)
			self._pitchSlider.SetValue(voiceInstance.pitch)
			self._volumeSlider.SetValue(voiceInstance.volume)
			self._inflectionSlider.SetValue(voiceInstance.inflection)
			self._rateBoostCheckBox.SetValue(voiceInstance.rateBoost)
		else:
			self._dataToPercist[locale]["voice"] = "no-select"
		self._updateVariantsSelection()
		self.sliderDisable()
		self.sliderEnable()

	@guard_errors(callback=got_error_callback)
	def onVariantChange(self, event):
		voiceName = self._voicesChoice.GetStringSelection()
		if voiceName != "no-select":
			voiceInstance = self._manager.getVoiceInstance(voiceName)
			voiceInstance.variant = self._variantsChoice.GetStringSelection()

	@guard_errors(callback=got_error_callback)
	def onKeepEngineConsistentChange(self, event):
		self._manager.keepMainLocaleEngineConsistent = self._keepEngineConsistentCheckBox.GetValue()
		self._manager.onKeepEngineConsistent()

		self._localeToVoices = self._manager.localeToVoicesMap
		self.localesToNames = self._manager.localesToNamesMap
		self._locales = self._manager.languages

		self._localesChoice.SetItems([self.localesToNames[l] for l in self._locales])
		self._updateVoicesSelection()

	@guard_errors(callback=got_error_callback)
	def onKeepParameterConsistentChange(self, event):
		voiceName = self._voicesChoice.GetStringSelection()
		if voiceName == "":
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(self._manager._defaultVoiceInstance)
			return
		if voiceName != "no-select":
			self.sliderEnable()
			voiceInstance = self._manager.getVoiceInstance(voiceName)
			if self._keepParameterConsistentCheckBox.GetValue():
				mainVoiceInstance = self._manager._defaultVoiceInstance
				voiceInstance.rate = mainVoiceInstance.rate
				voiceInstance.pitch = mainVoiceInstance.pitch
				voiceInstance.volume = mainVoiceInstance.volume
				voiceInstance.inflection = mainVoiceInstance.inflection
				voiceInstance.rateBoost = mainVoiceInstance.rateBoost
			self._rateSlider.SetValue(voiceInstance.rate)
			self._pitchSlider.SetValue(voiceInstance.pitch)
			self._volumeSlider.SetValue(voiceInstance.volume)
			self._inflectionSlider.SetValue(voiceInstance.inflection)
			self._rateBoostCheckBox.SetValue(voiceInstance.rateBoost)
		else:
			self.sliderDisable()
		if self._keepParameterConsistentCheckBox.GetValue():
			self._manager.onVoiceParameterConsistent(self._manager._defaultVoiceInstance)

	def sliderEnable(self):
		if self.voiceInstance:
			self._rateSlider.Enable()
			self._pitchSlider.Enable()
			self._volumeSlider.Enable()
			if self.voiceInstance.engine in ["aisound", "IBM", "Espeak"]:
				self._inflectionSlider.Enable()
			if self.voiceInstance.engine in ["OneCore", "RH", "Espeak", "SAPI5", "VE"]:
				self._rateBoostCheckBox.Enable()

	def sliderDisable(self):
		self._rateSlider.Disable()
		self._pitchSlider.Disable()
		self._volumeSlider.Disable()
		self._inflectionSlider.Disable()
		self._rateBoostCheckBox.Disable()

	@guard_errors(callback=got_error_callback)
	def onSpeechRateSliderScroll(self, event):
		if self.voiceInstance:
			self.voiceInstance.rate = self._rateSlider.GetValue()
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(self.voiceInstance)

	@guard_errors(callback=got_error_callback)
	def onPitchSliderScroll(self, event):
		if self.voiceInstance:
			self.voiceInstance.pitch = self._pitchSlider.GetValue()
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(self.voiceInstance)

	@guard_errors(callback=got_error_callback)
	def onVolumeSliderScroll(self, event):
		if self.voiceInstance:
			self.voiceInstance.volume = self._volumeSlider.GetValue()
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(self.voiceInstance)

	@guard_errors(callback=got_error_callback)
	def onInflectionSliderScroll(self, event):
		if self.voiceInstance:
			self.voiceInstance.inflection = self._inflectionSlider.GetValue()
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(self.voiceInstance)

	@guard_errors(callback=got_error_callback)
	def onRateBoostChange(self, event):
		if self.voiceInstance:
			self.voiceInstance.rateBoost = self._rateBoostCheckBox.GetValue()
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(self.voiceInstance)

	@guard_errors(callback=lambda self: None)
	def onDiscard(self):
		if self.disable or not getSynth().name == 'WorldVoice':
			return
		for instance in self._manager._instanceCache.values():
			instance.rollback()

	@guard_errors(callback=got_error_callback)
	def onSave(self):
		if self.disable or not getSynth().name == 'WorldVoice':
			return
		temp = defaultdict(lambda: {})
		for key, value in config.conf["WorldVoice"]["role"].items():
			if isinstance(value, config.AggregatedSection):
				try:
					temp[key]['voice'] = config.conf["WorldVoice"]["role"][key]["voice"]
				except KeyError:
					pass

		for locale in self._dataToPercist:
			if self._dataToPercist[locale]["voice"] != "no-select":
				temp[locale] = self._dataToPercist[locale]
			else:
				try:
					del temp[locale]
				except BaseException:
					pass

		config.conf["WorldVoice"]["role"] = temp

		config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"] = self._keepEngineConsistentCheckBox.GetValue()
		config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = self._keepParameterConsistentCheckBox.GetValue()
		config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"] = self._keepConsistentCheckBox.GetValue()

		for instance in self._manager._instanceCache.values():
			instance.commit()
			try:
				if instance.name == config.conf["speech"][getSynth().name]["voice"]:
					config.conf["speech"][getSynth().name]["rate"] = instance.rate
					config.conf["speech"][getSynth().name]["pitch"] = instance.pitch
					config.conf["speech"][getSynth().name]["volume"] = instance.volume
					config.conf["speech"][getSynth().name]["inflection"] = instance.inflection
					config.conf["speech"][getSynth().name]["rateBoost"] = instance.rateBoost
			except BaseException:
				pass
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]:
			self._manager.onVoiceParameterConsistent(self._manager._defaultVoiceInstance)

		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"]:
			locale = self._manager.defaultVoiceInstance.language if self._manager.defaultVoiceInstance.language else languageHandler.getLanguage()
			try:
				different = self._dataToPercist[locale]["voice"] != self._manager.defaultVoiceInstance.name and self._dataToPercist[locale]["voice"] != "no-select"
			except KeyError:
				different = False
			if different:
				if getSynth().name == 'WorldVoice':
					getSynth().voice = self._dataToPercist[locale]["voice"]
				config.conf["speech"]["WorldVoice"]["voice"] = self._dataToPercist[locale]["voice"]


class UnicodeDetectionSettingsPanel(SettingsPanel):
	title = _("Unicode Detection")

	def makeSettings(self, sizer):
		self.disable = False
		if not getSynth().name == 'WorldVoice':
			infoCtrl = wx.TextCtrl(
				self,
				value=_('Your current speech synthesizer is not WorldVoice.'),
				style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE
			)
			infoCtrl.SetBackgroundColour(self.GetBackgroundColour())
			sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)
			self.disable = True
			return

		self._manager = getSynth()._voiceManager
		self.ready = self._manager.ready()
		if not self.ready:
			infoCtrl = wx.TextCtrl(
				self,
				value=_('Your current speech synthesizer is not ready.'),
				style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE
			)
			infoCtrl.SetBackgroundColour(self.GetBackgroundColour())
			sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)
			self.disable = True
			return

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
			label=_("Ignore numbers when detecting text language")
		)
		self._ignoreNumbersCheckBox.SetValue(config.conf["WorldVoice"]["autoLanguageSwitching"]["ignoreNumbersInLanguageDetection"])
		settingsSizerHelper.addItem(self._ignoreNumbersCheckBox)

		self._ignorePunctuationCheckBox = wx.CheckBox(
			self,
			# Translators: Either to ignore or not ASCII punctuation when language detection is active
			label=_("Ignore common punctuation when detecting text language")
		)
		self._ignorePunctuationCheckBox.SetValue(config.conf["WorldVoice"]["autoLanguageSwitching"]["ignorePunctuationInLanguageDetection"])
		settingsSizerHelper.addItem(self._ignorePunctuationCheckBox)

		latinChoiceLocaleNames = [self.localesToNames[l] for l in self._latinLocales]
		self._latinChoice = settingsSizerHelper.addLabeledControl(_("Language assumed for latin characters:"), wx.Choice, choices=latinChoiceLocaleNames)
		latinLocale = config.conf["WorldVoice"]["autoLanguageSwitching"]["latinCharactersLanguage"]
		try:
			self._latinChoice.Select(self._latinLocales.index(latinLocale))
		except ValueError:
			self._latinChoice.Select(0)
		if not latinChoiceLocaleNames:
			self._latinChoice.Disable()

		CJKChoiceLocaleNames = [self.localesToNames[l] for l in self._CJKLocales]
		self._CJKChoice = settingsSizerHelper.addLabeledControl(_("Language assumed for CJK characters:"), wx.Choice, choices=CJKChoiceLocaleNames)
		CJKLocale = config.conf["WorldVoice"]["autoLanguageSwitching"]["CJKCharactersLanguage"]
		try:
			self._CJKChoice.Select(self._CJKLocales.index(CJKLocale))
		except ValueError:
			self._CJKChoice.Select(0)
		if not CJKChoiceLocaleNames:
			self._CJKChoice.Disable()

		arabicChoiceLocaleNames = [self.localesToNames[l] for l in self._arabicLocales]
		self._arabicChoice = settingsSizerHelper.addLabeledControl(_("Language assumed for arabic characters:"), wx.Choice, choices=arabicChoiceLocaleNames)
		arabicLocale = config.conf["WorldVoice"]["autoLanguageSwitching"]["arabicCharactersLanguage"]
		try:
			self._arabicChoice.Select(self._arabicLocales.index(arabicLocale))
		except ValueError:
			self._arabicChoice.Select(0)
		if not arabicChoiceLocaleNames:
			self._arabicChoice.Disable()

		DetectLanguageTimingLabel = [
			_("Before NVDA processes speech commands"),
			_("After NVDA processes speech commands")
		]
		self._DetectLanguageTimingValue = ["before", "after"]
		self._DLTChoice = settingsSizerHelper.addLabeledControl(
			_("Language detection timing:"),
			wx.Choice,
			choices=DetectLanguageTimingLabel
		)
		self._DetectLanguageTiming = config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"]
		try:
			self._DLTChoice.Select(self._DetectLanguageTimingValue.index(self._DetectLanguageTiming))
		except ValueError:
			self._DLTChoice.Select(0)

	def onSave(self):
		if self.disable or not getSynth().name == 'WorldVoice':
			return
		config.conf["WorldVoice"]["autoLanguageSwitching"]["ignoreNumbersInLanguageDetection"] = self._ignoreNumbersCheckBox.GetValue()
		config.conf["WorldVoice"]["autoLanguageSwitching"]["ignorePunctuationInLanguageDetection"] = self._ignorePunctuationCheckBox.GetValue()
		if self._latinChoice.IsEnabled():
			config.conf["WorldVoice"]["autoLanguageSwitching"]["latinCharactersLanguage"] = self._latinLocales[self._latinChoice.GetCurrentSelection()]
		if self._CJKChoice.IsEnabled():
			config.conf["WorldVoice"]["autoLanguageSwitching"]["CJKCharactersLanguage"] = self._CJKLocales[self._CJKChoice.GetCurrentSelection()]

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
		enabled = [eng for eng in EngineType]
		self.voice_classes: dict[str, type] = self._load_voice_classes(enabled)

		self.readyEngine = []
		for eng in enabled:
			cls = self.voice_classes[eng.name]
			try:
				if cls.ready():
					self.readyEngine.append(eng.name)
			except Exception as e:
				log.error("engine %s not ready: %s", eng.name, e)

		self.settings = OrderedDict({
			eng.name: {"label": eng.label}
			for eng in EngineType
			if eng.name in self.readyEngine
		})

		super().makeSettings(sizer)

		self.previousActiveEngine = set([
			key
			for key, value in config.conf["WorldVoice"]["engine"].items()
			if key in self.readyEngine and value
		])

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
				_("No Speech Engine Enabled"), wx.OK | wx.ICON_WARNING, self
			)
			return False
		if self.activeEngine != self.previousActiveEngine:
			self.confirm = gui.messageBox(
				# Translators: The message displayed
				_("To enable or disable the speech engine, NVDA needs to save your configuration and restart. Would you like to restart now?"),
				# Translators: The title of the dialog
				_("Speech Engine Change"), wx.YES | wx.NO | wx.CANCEL | wx.ICON_WARNING, self
			)
			if self.confirm == wx.CANCEL:
				return False
		return True

	def onSave(self):
		if self.activeEngine != self.previousActiveEngine:
			if self.confirm == wx.YES:
				gui.mainFrame.onSaveConfigurationCommand(None)
				queueHandler.queueFunction(queueHandler.eventQueue, core.restart)
			super().onSave()

	def _load_voice_classes(self, engines: list[EngineType]) -> dict[str, type]:
		"""
		Dynamically import voice classes based on EngineType definitions.
		Returns a dict mapping engine-name (e.g. "VE") to the class object.
		"""
		classes: dict[str, type] = {}
		for eng in engines:
			module_path = eng.module_path	  # e.g. "voice.VEVoice"
			class_name = eng.class_name	   # e.g. "VEVoice"
			module = importlib.import_module(module_path)
			cls = getattr(module, class_name)
			classes[eng.name] = cls
		return classes


class LogSettingsPanel(BaseSettingsPanel):
	# Translators: Title of a setting dialog.
	title = _("Log Record")
	field = "log"
	settings = OrderedDict({
		"ignore_comma_between_number": {"label": _("Ignore comma between number")},
		"number_mode": {"label": _("Number mode")},
		"number_language": {"label": _("Number language")},
		"number_wait_factor": {"label": _("number wait factor")},
		"item_wait_factor": {"label": _("item wait factor")},
		"chinesespace_wait_factor": {"label": _("chinese space wait factor")},
	})

	def makeSettings(self, settingsSizer):
		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self._enable_checkbox = wx.CheckBox(
			self,
			label=_("Enable logging of WorldVoice’s speech pipeline")
		)
		settingsSizerHelper.addItem(self._enable_checkbox)
		self.Bind(wx.EVT_CHECKBOX, self.onEnableCheckboxChange, self._enable_checkbox)
		self._enable_checkbox.SetValue(config.conf["WorldVoice"]["log"]["enable"])
		super().makeSettings(settingsSizer, settingsSizerHelper=settingsSizerHelper)
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
		enabled_before = config.conf["WorldVoice"]["log"]["enable"]
		enabled_after = self._enable_checkbox.GetValue()
		if enabled_before != enabled_after:
			if enabled_after:
				self.confirm = gui.messageBox(
					# Translators: The message displayed
					_("Enabling logging of WorldVoice’s speech pipeline will reduce speech response speed. If you are not debugging, we recommend keeping it disabled. Would you like to enable it anyway?"),
					# Translators: The title of the dialog
					_("Speech Pipeline Logging"),
					wx.YES | wx.NO | wx.CANCEL, gui.mainFrame
				)
				if self.confirm == wx.CANCEL:
					self._enable_checkbox.SetValue(False)
					self.onEnableCheckboxChange(None)
					return False
		return True

	def onSave(self):
		enabled_before = config.conf["WorldVoice"]["log"]["enable"]
		enabled_after = self._enable_checkbox.GetValue()
		if enabled_before != enabled_after:
			if enabled_after:
				if self.confirm == wx.YES:
					config.conf["WorldVoice"]["log"]["enable"] = True
			else:
				config.conf["WorldVoice"]["log"]["enable"] = False
				if gui.messageBox(
					# Translators: The message displayed
					_("Logging of WorldVoice’s speech pipeline has been disabled. Would you like to export the pipeline log now?"),
					# Translators: The title of the dialog
					_("Speech Pipeline Logging"),
					wx.YES | wx.NO, gui.mainFrame
				) == wx.YES:
					wx.CallAfter(pl.export)

		super().onSave()


class WorldVoiceSettingsDialog(MultiCategorySettingsDialog):
	dialogTitle = _("Settings")
	INITIAL_SIZE = (1000, 480)
	MIN_SIZE = (470, 240)

	def __init__(self, parent):
		if getSynth().name == 'WorldVoice':
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

		self.__class__.wvd = self
		self.Bind(wx.EVT_WINDOW_DESTROY, self._onDestroy)

	def _onDestroy(self, evt):
		self.__class__.wvd = None
		evt.Skip()
