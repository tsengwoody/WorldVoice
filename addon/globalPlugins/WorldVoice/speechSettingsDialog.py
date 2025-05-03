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
import queueHandler
from synthDriverHandler import getSynth
from synthDrivers.WorldVoice import languageDetection
from synthDrivers.WorldVoice.pipeline import order_move_to_start_register, static_register, dynamic_register, unregister
from synthDrivers.WorldVoice.voiceEngine import EngineType
import tones


addonHandler.initTranslation()


class BaseSettingsPanel(SettingsPanel):
	# Translators: Title of a setting dialog.
	title = _("WorldVoice")
	settings = OrderedDict({})
	field = "WorldVoice"

	def makeSettings(self, settingsSizer):
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		for k, v in self.settings.items():
			if "options" in v:
				attr = k + "Selection"
				options = v["options"]
				widget = sHelper.addLabeledControl(v["label"], wx.Choice, choices=list(options.values()))
				setattr(self, attr, widget)
				try:
					index = list(v["options"].keys()).index(str(config.conf["WorldVoice"][self.field][k]))
				except BaseException:
					index = 0
					tones.beep(100, 100)
				widget.Selection = index
			else:
				setattr(self, k + "CheckBox", sHelper.addItem(wx.CheckBox(self, label=v["label"])))
				value = config.conf["WorldVoice"][self.field][k]
				getattr(self, k + "CheckBox").SetValue(value)

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


class GlobalSynthesizerSettingsPanel(SettingsPanel):
	# Translators: Title of a setting dialog.
	title = _("Global Synthesizer")

	def __init__(self, parent):
		self._synthInstance = getSynth()
		super().__init__(parent)

	def makeSettings(self, sizer):
		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)

		self._enable_checkbox = wx.CheckBox(
			self,
			label=_("Apply WorldVoice’s speech command pipeline globally")
		)
		settingsSizerHelper.addItem(self._enable_checkbox)
		self.Bind(wx.EVT_CHECKBOX, self.onEnableCheckboxChange, self._enable_checkbox)
		self._enable_checkbox.SetValue(config.conf["WorldVoice"]["synthesizer"]["enable"])

		self._ignore_comma_between_number_checkbox = wx.CheckBox(
			self,
			label=_("Ignore comma between number")
		)
		settingsSizerHelper.addItem(self._ignore_comma_between_number_checkbox)
		self.Bind(wx.EVT_CHECKBOX, self.onIgnoreCommaBetweenNumberCheckboxChange, self._ignore_comma_between_number_checkbox)
		self._ignore_comma_between_number_checkbox.SetValue(config.conf["WorldVoice"]["synthesizer"]["ignore_comma_between_number"])

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
			self._number_mode_choice.Select(self.number_mode_value.index(config.conf["WorldVoice"]["synthesizer"]["number_mode"]))
		except ValueError:
			self._number_mode_choice.Select(0)

		self._global_wait_factor_slider = settingsSizerHelper.addLabeledControl(_("global wait factor:"), wx.Slider, value=5, minValue=0, maxValue=10, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onGlobalWaitFactorSliderScroll, self._global_wait_factor_slider)
		self._global_wait_factor_slider.SetValue(config.conf["WorldVoice"]["synthesizer"]["global_wait_factor"] // 10)

		self._number_wait_factor_slider = settingsSizerHelper.addLabeledControl(_("number wait factor:"), wx.Slider, value=50, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onNumberWaitFactorSliderScroll, self._number_wait_factor_slider)
		self._number_wait_factor_slider.SetValue(config.conf["WorldVoice"]["synthesizer"]["number_wait_factor"])

		self._item_wait_factor_slider = settingsSizerHelper.addLabeledControl(_("item wait factor:"), wx.Slider, value=50, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onItemWaitFactorSliderScroll, self._item_wait_factor_slider)
		self._item_wait_factor_slider.SetValue(config.conf["WorldVoice"]["synthesizer"]["item_wait_factor"])

		self._sayall_wait_factor_slider = settingsSizerHelper.addLabeledControl(_("sayall wait factor:"), wx.Slider, value=50, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onSayallWaitFactorSliderScroll, self._sayall_wait_factor_slider)
		self._sayall_wait_factor_slider.SetValue(config.conf["WorldVoice"]["synthesizer"]["sayall_wait_factor"])

		self._chinesespace_wait_factor_slider = settingsSizerHelper.addLabeledControl(_("chinese space wait factor:"), wx.Slider, value=50, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onChinesespaceWaitFactorSliderScroll, self._chinesespace_wait_factor_slider)
		self._chinesespace_wait_factor_slider.SetValue(config.conf["WorldVoice"]["synthesizer"]["chinesespace_wait_factor"])

		self.onEnableCheckboxChange(None)

	def onEnableCheckboxChange(self, event):
		if self._enable_checkbox.GetValue():
			self.sliderEnable()
			if self._synthInstance.name != "WorldVoice":
				static_register()
				dynamic_register()
				order_move_to_start_register()
		else:
			self.sliderDisable()
			if self._synthInstance.name != "WorldVoice":
				unregister()

	def onIgnoreCommaBetweenNumberCheckboxChange(self, event):
		if self._synthInstance.name == 'WorldVoice':
			self._synthInstance._cni = self._ignore_comma_between_number_checkbox.GetValue()

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
		config.conf["WorldVoice"]["synthesizer"]["enable"] = self._enable_checkbox.GetValue()
		config.conf["WorldVoice"]["synthesizer"]["ignore_comma_between_number"] = self._ignore_comma_between_number_checkbox.GetValue()
		config.conf["WorldVoice"]["synthesizer"]["number_mode"] = self.number_mode_value[self._number_mode_choice.GetCurrentSelection()]
		config.conf["WorldVoice"]["synthesizer"]["global_wait_factor"] = self._global_wait_factor_slider.GetValue() * 10
		config.conf["WorldVoice"]["synthesizer"]["number_wait_factor"] = self._number_wait_factor_slider.GetValue()
		config.conf["WorldVoice"]["synthesizer"]["item_wait_factor"] = self._item_wait_factor_slider.GetValue()
		config.conf["WorldVoice"]["synthesizer"]["sayall_wait_factor"] = self._sayall_wait_factor_slider.GetValue()
		config.conf["WorldVoice"]["synthesizer"]["chinesespace_wait_factor"] = self._chinesespace_wait_factor_slider.GetValue()


class SpeechRoleSettingsPanel(SettingsPanel):
	title = _("Speech Role")

	def makeSettings(self, sizer):
		if not getSynth().name == 'WorldVoice':
			infoLabel = wx.StaticText(self, label=_('Your current speech synthesizer is not WorldVoice.'))
			infoLabel.Wrap(self.GetSize()[0])
			sizer.Add(infoLabel)
			return

		self._manager = getSynth()._voiceManager
		self.ready = self._manager.ready()
		if not self.ready:
			infoLabel = wx.StaticText(self, label=_('Your current speech synthesizer is not ready.'))
			infoLabel.Wrap(self.GetSize()[0])
			sizer.Add(infoLabel)
			return

		self._localeToVoices = self._manager.localeToVoicesMap
		self.localesToNames = self._manager.localesToNamesMap
		self._locales = self._manager.languages

		self._dataToPercist = defaultdict(lambda: {})
		latinSet = set(languageDetection.ALL_LATIN) & set(l for l in self._locales if len(l) == 2)
		self._latinLocales = sorted(list(latinSet))
		CJKSet = set(languageDetection.CJK) & set(l for l in self._locales if len(l) == 2)
		self._CJKLocales = sorted(list(CJKSet))

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
		if not getSynth().name == 'WorldVoice':
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
			if locale in config.conf["WorldVoice"]["speechRole"]:
				try:
					voice = config.conf["WorldVoice"]["speechRole"][locale]["voice"]
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

	def onLocaleChanged(self, event):
		self._updateVoicesSelection()

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
		else:
			self._dataToPercist[locale]["voice"] = "no-select"
		self._updateVariantsSelection()
		self.sliderDisable()
		self.sliderEnable()

	def onVariantChange(self, event):
		voiceName = self._voicesChoice.GetStringSelection()
		if voiceName != "no-select":
			voiceInstance = self._manager.getVoiceInstance(voiceName)
			voiceInstance.variant = self._variantsChoice.GetStringSelection()

	def onKeepEngineConsistentChange(self, event):
		self._manager.keepMainLocaleEngineConsistent = self._keepEngineConsistentCheckBox.GetValue()
		self._manager.onKeepEngineConsistent()

		self._localeToVoices = self._manager.localeToVoicesMap
		self.localesToNames = self._manager.localesToNamesMap
		self._locales = self._manager.languages

		self._localesChoice.SetItems([self.localesToNames[l] for l in self._locales])
		self._updateVoicesSelection()

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

	def sliderDisable(self):
		self._rateSlider.Disable()
		self._pitchSlider.Disable()
		self._volumeSlider.Disable()
		self._inflectionSlider.Disable()

	def onSpeechRateSliderScroll(self, event):
		if self.voiceInstance:
			self.voiceInstance.rate = self._rateSlider.GetValue()
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(self.voiceInstance)

	def onPitchSliderScroll(self, event):
		if self.voiceInstance:
			self.voiceInstance.pitch = self._pitchSlider.GetValue()
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(self.voiceInstance)

	def onVolumeSliderScroll(self, event):
		if self.voiceInstance:
			self.voiceInstance.volume = self._volumeSlider.GetValue()
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(self.voiceInstance)

	def onInflectionSliderScroll(self, event):
		if self.voiceInstance:
			self.voiceInstance.inflection = self._inflectionSlider.GetValue()
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(self.voiceInstance)

	def onDiscard(self):
		if not getSynth().name == 'WorldVoice':
			return
		for instance in self._manager._instanceCache.values():
			instance.rollback()

	def onSave(self):
		if not getSynth().name == 'WorldVoice':
			return
		temp = defaultdict(lambda: {})
		for key, value in config.conf["WorldVoice"]["speechRole"].items():
			if isinstance(value, config.AggregatedSection):
				try:
					temp[key]['voice'] = config.conf["WorldVoice"]["speechRole"][key]["voice"]
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

		config.conf["WorldVoice"]["speechRole"] = temp

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


class LanguageSwitchingSettingsPanel(SettingsPanel):
	title = _("Unicode Detection")

	def __init__(self, parent):
		self._synthInstance = getSynth()
		super().__init__(parent)

	def makeSettings(self, sizer):
		if not self._synthInstance.name == 'WorldVoice':
			infoLabel = wx.StaticText(self, label=_('Your current speech synthesizer is not WorldVoice.'))
			infoLabel.Wrap(self.GetSize()[0])
			sizer.Add(infoLabel)
			return

		self._manager = self._synthInstance._voiceManager
		self.ready = self._manager.ready()
		if not self.ready:
			infoLabel = wx.StaticText(self, label=_('Your current speech synthesizer is not ready.'))
			infoLabel.Wrap(self.GetSize()[0])
			sizer.Add(infoLabel)
			return

		self.localesToNames = self._manager.localesToNamesMap
		self._locales = self._manager.languages

		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)
		latinSet = set(languageDetection.ALL_LATIN) & set(l for l in self._locales if len(l) == 2)
		self._latinLocales = sorted(list(latinSet))
		CJKSet = set(languageDetection.CJK) & set(l for l in self._locales if len(l) == 2)
		self._CJKLocales = sorted(list(CJKSet))

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
		if not self._synthInstance.name == 'WorldVoice':
			return False
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
			self._synthInstance.uwv = self._synthInstance.uwv


class SpeechEngineSettingsPanel(BaseSettingsPanel):
	# Translators: Title of a setting dialog.
	title = _("Speech Engine")
	field = "engine"

	def makeSettings(self, sizer):
		enabled = [eng for eng in EngineType]
		self.voice_classes: Dict[str, type] = self._load_voice_classes(enabled)

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

	def onSave(self):
		activeEngine = set()
		for k, v in self.settings.items():
			if getattr(self, k + "CheckBox").IsChecked():
				activeEngine.add(k)

		if len(activeEngine) == 0:
			gui.messageBox(
				# Translators: The message displayed
				_("Speech engine configuration changes will not to save because no speech engines are activated."),
				# Translators: The title of the dialog
				_("No speech engines are activated"), wx.OK | wx.ICON_WARNING, self
			)
			return False

		if activeEngine != self.previousActiveEngine:
			if gui.messageBox(
				# Translators: The message displayed
				_("For the active speech engine configuration to apply, NVDA must save configuration and be restarted. Do you want to do now?"),
				# Translators: The title of the dialog
				_("active engine Configuration Change"), wx.OK | wx.CANCEL | wx.ICON_WARNING, self
			) == wx.OK:
				super().onSave()
				gui.mainFrame.onSaveConfigurationCommand(None)
				queueHandler.queueFunction(queueHandler.eventQueue, core.restart)

	def _load_voice_classes(self, engines: list[EngineType]) -> dict[str, type]:
		"""
		Dynamically import voice classes based on EngineType definitions.
		Returns a dict mapping engine-name (e.g. "VE") to the class object.
		"""
		classes: Dict[str, type] = {}
		for eng in engines:
			module_path = eng.module_path	  # e.g. "voice.VEVoice"
			class_name = eng.class_name	   # e.g. "VEVoice"
			module = importlib.import_module(module_path)
			cls = getattr(module, class_name)
			classes[eng.name] = cls
		return classes


class WorldVoiceSettingsDialog(MultiCategorySettingsDialog):
	# translators: title of the dialog.
	dialogTitle = _("Speech Settings")
	title = "% s - %s" % (_("WorldVoice"), dialogTitle)
	INITIAL_SIZE = (1000, 480)
	MIN_SIZE = (470, 240)

	categoryClasses = [
		GlobalSynthesizerSettingsPanel,
		SpeechRoleSettingsPanel,
		LanguageSwitchingSettingsPanel,
		SpeechEngineSettingsPanel,
	]
