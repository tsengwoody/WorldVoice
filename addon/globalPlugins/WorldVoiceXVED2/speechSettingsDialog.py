from collections import defaultdict

import wx
import addonHandler
import config
import gui
from gui import guiHelper
import languageHandler
import queueHandler
import core

try:
	from synthDriverHandler import getSynth
except:
	from speech import getSynth

from synthDrivers.WorldVoiceXVED2 import _core, VoiceManager
from synthDrivers.WorldVoiceXVED2 import languageDetection

addonHandler.initTranslation()

def SpeechSettingsDialog():
	class Dialog(gui.SettingsDialog):
		_instance = None
		title = _("Speech Settings")

		def __new__(cls, *args, **kwargs):
			obj = super().__new__(cls, *args, **kwargs)
			cls._instance = obj
			return obj

		def __init__(self, parent):
			self.ready = False
			with _core.preOpen() as check:
				if check:
					self.ready = True
					self._synthInstance = getSynth()
					if self._synthInstance.name == 'WorldVoiceXVED2':
						self._manager = self._synthInstance._voiceManager
					else:
						self._manager = VoiceManager()
						self.ready = False
					self._localeToVoices = self._manager.localeToVoicesMap
					self.localesToNames = self._manager.localesToNamesMap
					self._locales = sorted([l for l in self._localeToVoices if len(self._localeToVoices[l]) > 0])

			self._dataToPercist = defaultdict(lambda: {})
			latinSet = set(languageDetection.ALL_LATIN) & set(l for l in self._locales if len(l) == 2)
			self._latinLocales = sorted(list(latinSet))
			CJKSet = set(languageDetection.CJK) & set(l for l in self._locales if len(l) == 2)
			self._CJKLocales = sorted(list(CJKSet))
			super().__init__(parent)

		def makeSettings(self, sizer):
			synthInfo = _('Your current speech synthesizer is not ready.')
			if not self.ready:
				infoLabel = wx.StaticText(self, label = synthInfo)
				infoLabel.Wrap(self.GetSize()[0])
				sizer.Add(infoLabel)
				return

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

			self._rateSlider = settingsSizerHelper.addLabeledControl(_("&Rate:"), wx.Slider, value = 50, minValue = 0, maxValue = 100, style = wx.SL_HORIZONTAL)
			self.Bind(wx.EVT_SLIDER, self.onSpeechRateSliderScroll, self._rateSlider)
			self._pitchSlider = settingsSizerHelper.addLabeledControl(_("&Pitch:"), wx.Slider, value = 50, minValue = 0, maxValue = 100, style = wx.SL_HORIZONTAL)
			self.Bind(wx.EVT_SLIDER, self.onPitchSliderScroll, self._pitchSlider)
			self._volumeSlider = settingsSizerHelper.addLabeledControl(_("V&olume:"), wx.Slider, value = 50, minValue = 0, maxValue = 100, style = wx.SL_HORIZONTAL)
			self.Bind(wx.EVT_SLIDER, self.onVolumeSliderScroll, self._volumeSlider)
			self.sliderDisable()

			self._keepParameterConsistentCheckBox = wx.CheckBox(self,
				label=_("Keep main parameter and locale parameter consistent"))
			self._keepParameterConsistentCheckBox.SetValue(config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"])
			settingsSizerHelper.addItem(self._keepParameterConsistentCheckBox)
			self.Bind(wx.EVT_CHECKBOX, self.onKeepParameterConsistentChange, self._keepParameterConsistentCheckBox)

			self._keepConsistentCheckBox = wx.CheckBox(self,
				label=_("Keep main voice and locale voice consistent"))
			self._keepConsistentCheckBox.SetValue(config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"])
			settingsSizerHelper.addItem(self._keepConsistentCheckBox)

			self._useUnicodeDetectionCheckBox = wx.CheckBox(self,
				label=_("Detect text language based on unicode characters"))
			self._useUnicodeDetectionCheckBox.SetValue(config.conf["WorldVoice"]["autoLanguageSwitching"]["useUnicodeLanguageDetection"])
			settingsSizerHelper.addItem(self._useUnicodeDetectionCheckBox)

			self._ignoreNumbersCheckBox = wx.CheckBox(self,
			# Translators: Either to ignore or not numbers when language detection is active
			label=_("Ignore numbers when detecting text language"))
			self._ignoreNumbersCheckBox.SetValue(config.conf["WorldVoice"]["autoLanguageSwitching"]["ignoreNumbersInLanguageDetection"])
			settingsSizerHelper.addItem(self._ignoreNumbersCheckBox)

			self._ignorePunctuationCheckBox = wx.CheckBox(self,
			# Translators: Either to ignore or not ASCII punctuation when language detection is active
			label=_("Ignore common punctuation when detecting text language"))
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

			DetectLanguageTimingLabel = [_("before symbol process"), _("after symbol process")]
			self._DetectLanguageTimingValue = ["before", "after"]
			self._DLTChoice = settingsSizerHelper.addLabeledControl(_("Detect language timing:"), wx.Choice, choices=DetectLanguageTimingLabel)
			self._DetectLanguageTiming = config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"]
			try:
				self._DLTChoice.Select(self._DetectLanguageTimingValue.index(self._DetectLanguageTiming))
			except ValueError:
				self._DLTChoice.Select(0)

			self._dotText = settingsSizerHelper.addLabeledControl(
				labelText=_("Number dot replacement"),
				wxCtrlClass=wx.TextCtrl,
				value=config.conf["WorldVoice"]["autoLanguageSwitching"]["numberDotReplacement"],
			)

		def postInit(self):
			if not self.ready:
				return
			self._updateVoicesSelection()
			self._localesChoice.SetFocus()

		def _updateVoicesSelection(self):
			localeIndex = self._localesChoice.GetCurrentSelection()
			if localeIndex < 0:
				self._voicesChoice.SetItems([])
			else:
				locale = self._locales[localeIndex]
				voices = ["no-select"] + sorted(self._localeToVoices[locale])
				self._voicesChoice.SetItems(voices)
				if locale in config.conf["WorldVoice"]["autoLanguageSwitching"]:
					voice = config.conf["WorldVoice"]["autoLanguageSwitching"][locale]["voice"]
					if voice:
						self._voicesChoice.Select(voices.index(voice))
						self.onVoiceChange(None)
				else:
					self._voicesChoice.Select(0)
					self.onVoiceChange(None)

		def _updateVariantsSelection(self):
			voiceName = self._voicesChoice.GetStringSelection()
			if voiceName != "no-select":
				voiceInstance = self._manager.getVoiceInstance(voiceName)
				variants = [i for i in voiceInstance.variants if i != '']
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
				self.sliderEnable()
				voiceInstance = self._manager.getVoiceInstance(voiceName)
				if self._keepParameterConsistentCheckBox.GetValue():
					mainVoiceInstance = self._manager._defaultVoiceInstance
					voiceInstance.rate = mainVoiceInstance.rate
					voiceInstance.pitch = mainVoiceInstance.pitch
					voiceInstance.volume = mainVoiceInstance.volume
				self._rateSlider.SetValue(voiceInstance.rate)
				self._pitchSlider.SetValue(voiceInstance.pitch)
				self._volumeSlider.SetValue(voiceInstance.volume)
			else:
				self._dataToPercist[locale]["voice"] = "no-select"
				self.sliderDisable()
			self._updateVariantsSelection()

		def onVariantChange(self, event):
			voiceName = self._voicesChoice.GetStringSelection()
			if voiceName != "no-select":
				voiceInstance = self._manager.getVoiceInstance(voiceName)
				voiceInstance.variant = self._variantsChoice.GetStringSelection()

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
				self._rateSlider.SetValue(voiceInstance.rate)
				self._pitchSlider.SetValue(voiceInstance.pitch)
				self._volumeSlider.SetValue(voiceInstance.volume)
			else:
				self.sliderDisable()

			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(self._manager._defaultVoiceInstance)

		def sliderEnable(self):
			self._rateSlider.Enable()
			self._pitchSlider.Enable()
			self._volumeSlider.Enable()

		def sliderDisable(self):
			self._rateSlider.Disable()
			self._pitchSlider.Disable()
			self._volumeSlider.Disable()

		def onSpeechRateSliderScroll(self, event):
			voiceName = self._voicesChoice.GetStringSelection()
			if voiceName == '':
				return
			voiceInstance = self._manager.getVoiceInstance(voiceName)
			voiceInstance.rate = self._rateSlider.GetValue()
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(voiceInstance)

		def onPitchSliderScroll(self, event):
			voiceName = self._voicesChoice.GetStringSelection()
			if voiceName == '':
				return
			voiceInstance = self._manager.getVoiceInstance(voiceName)
			voiceInstance.pitch = self._pitchSlider.GetValue()
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(voiceInstance)

		def onVolumeSliderScroll(self, event):
			voiceName = self._voicesChoice.GetStringSelection()
			if voiceName == '':
				return
			voiceInstance = self._manager.getVoiceInstance(voiceName)
			voiceInstance.volume = self._volumeSlider.GetValue()
			if self._keepParameterConsistentCheckBox.GetValue():
				self._manager.onVoiceParameterConsistent(voiceInstance)

		def onCancel(self, event):
			if not self.ready:
				self.__class__._instance = None
				super().onCancel(event)
				return

			for instance in self._manager._instanceCache.values():
				instance.rollback()

			self.__class__._instance = None
			super().onCancel(event)

		def onOk(self, event):
			import config
			if not self.ready:
				self.__class__._instance = None
				super().onOk(event)
				return

			# Update Configuration
			for locale in self._dataToPercist:
				if self._dataToPercist[locale]["voice"] != "no-select":
					config.conf["WorldVoice"]["autoLanguageSwitching"][locale] = self._dataToPercist[locale]
				else:
					try:
						del config.conf["WorldVoice"]["autoLanguageSwitching"][locale]
					except BaseException as e:
						pass

			config.conf["WorldVoice"]["autoLanguageSwitching"]["numberDotReplacement"] = self._dotText.GetValue()
			config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = self._keepParameterConsistentCheckBox.GetValue()
			config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"] = self._keepConsistentCheckBox.GetValue()
			config.conf["WorldVoice"]["autoLanguageSwitching"]["useUnicodeLanguageDetection"] = self._useUnicodeDetectionCheckBox.GetValue()
			config.conf["WorldVoice"]["autoLanguageSwitching"]["ignoreNumbersInLanguageDetection"] = self._ignoreNumbersCheckBox.GetValue()
			config.conf["WorldVoice"]["autoLanguageSwitching"]["ignorePunctuationInLanguageDetection"] = self._ignorePunctuationCheckBox.GetValue()
			if self._latinChoice.IsEnabled():
				config.conf["WorldVoice"]["autoLanguageSwitching"]["latinCharactersLanguage"] = self._latinLocales[self._latinChoice.GetCurrentSelection()]
			if self._CJKChoice.IsEnabled():
				config.conf["WorldVoice"]["autoLanguageSwitching"]["CJKCharactersLanguage"] = self._CJKLocales[self._CJKChoice.GetCurrentSelection()]

			for instance in self._manager._instanceCache.values():
				instance.commit()
				try:
					if instance.name == config.conf["speech"][self._synthInstance.name]["voice"]:
						config.conf["speech"][self._synthInstance.name]["rate"] = instance.rate
						config.conf["speech"][self._synthInstance.name]["pitch"] = instance.pitch
						config.conf["speech"][self._synthInstance.name]["volume"] = instance.volume
				except BaseException as e:
					pass

			if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]:
				self._manager.onVoiceParameterConsistent(self._manager._defaultVoiceInstance)

			if self._DetectLanguageTimingValue[self._DLTChoice.GetCurrentSelection()] != config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"]:
				previous_DLT = config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"]
				config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"] = self._DetectLanguageTimingValue[self._DLTChoice.GetCurrentSelection()]
				if previous_DLT == "after":
					if gui.messageBox(
						# Translators: The message displayed
						_("For the detect language timing configuration to apply, NVDA must save configuration and be restarted. Do you want to do now?"),
						# Translators: The title of the dialog
						_("Detect language timing Configuration Change"),wx.OK|wx.CANCEL|wx.ICON_WARNING,self
					)==wx.OK:
						gui.mainFrame.onSaveConfigurationCommand(None)
						# wx.CallAfter(gui.mainFrame.onSaveConfigurationCommand, None)
						queueHandler.queueFunction(queueHandler.eventQueue,core.restart)

			if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"]:
				locale = self._manager.defaultVoiceInstance.language if self._manager.defaultVoiceInstance.language else languageHandler.getLanguage()
				try:
					different = self._dataToPercist[locale]["voice"] != self._manager.defaultVoiceInstance.name and self._dataToPercist[locale]["voice"] != "no-select"
				except KeyError:
					different = False
				if different:
					if self._synthInstance.name == 'WorldVoiceXVED2':
						self._synthInstance.voice = self._dataToPercist[locale]["voice"]
					config.conf["speech"]["WorldVoiceXVED2"]["voice"] = self._dataToPercist[locale]["voice"]

			if not self._synthInstance.name == 'WorldVoiceXVED2':
				self._manager.close()

			self.__class__._instance = None
			super().onOk(event)

	return Dialog
