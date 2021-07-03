from collections import defaultdict

import wx
import addonHandler
import gui
from gui import guiHelper
import synthDriverHandler

addonHandler.initTranslation()


def SpeechSettingsDialog():
	from synthDrivers.WorldVoiceXVED2 import _config, _core, VoiceManager
	from synthDrivers.WorldVoiceXVED2 import languageDetection
	class Dialog(gui.SettingsDialog):
		_instance = None
		title = _("Speech Settings")

		def __new__(cls, *args, **kwargs):
			obj = super(Dialog, cls).__new__(cls, *args, **kwargs)
			cls._instance = obj
			return obj

		def __init__(self, parent):
			_config.load()
			self.ready = False
			with _core.preOpen() as check:
				if check:
					self.ready = True
					self._synthInstance = synthDriverHandler.getSynth()
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
			super(Dialog, self).__init__(parent)

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

			self._rateSlider = settingsSizerHelper.addLabeledControl(_("&Rate:"), wx.Slider, value = 50, minValue = 0, maxValue = 100, style = wx.SL_HORIZONTAL)
			self.Bind(wx.EVT_SLIDER, self.onSpeechRateSliderScroll, self._rateSlider)
			self._pitchSlider = settingsSizerHelper.addLabeledControl(_("&Pitch:"), wx.Slider, value = 50, minValue = 0, maxValue = 100, style = wx.SL_HORIZONTAL)
			self.Bind(wx.EVT_SLIDER, self.onPitchSliderScroll, self._pitchSlider)
			self._volumeSlider = settingsSizerHelper.addLabeledControl(_("V&olume:"), wx.Slider, value = 50, minValue = 0, maxValue = 100, style = wx.SL_HORIZONTAL)
			self.Bind(wx.EVT_SLIDER, self.onVolumeSliderScroll, self._volumeSlider)
			self.sliderDisable()

			self._useUnicodeDetectionCheckBox = wx.CheckBox(self,
			# Translators: Wether to use or not unicode characters based language detection.
				label=_("Detect text language based on unicode characters"))
			self._useUnicodeDetectionCheckBox.SetValue(_config.vocalizerConfig["autoLanguageSwitching"]["useUnicodeLanguageDetection"])
			settingsSizerHelper.addItem(self._useUnicodeDetectionCheckBox)

			self._afterSymbolDetectionCheckBox = wx.CheckBox(self,
			# Translators: Wether to use or not after symbol detection.
				label=_("Detect text language after symbol process"))
			self._afterSymbolDetectionCheckBox.SetValue(_config.vocalizerConfig["autoLanguageSwitching"]["afterSymbolDetection"])
			settingsSizerHelper.addItem(self._afterSymbolDetectionCheckBox)

			self._ignoreNumbersCheckBox = wx.CheckBox(self,
			# Translators: Either to ignore or not numbers when language detection is active
			label=_("Ignore numbers when detecting text language"))
			self._ignoreNumbersCheckBox.SetValue(_config.vocalizerConfig["autoLanguageSwitching"]["ignoreNumbersInLanguageDetection"])
			settingsSizerHelper.addItem(self._ignoreNumbersCheckBox)

			self._ignorePunctuationCheckBox = wx.CheckBox(self,
			# Translators: Either to ignore or not ASCII punctuation when language detection is active
			label=_("Ignore common punctuation when detecting text language"))
			self._ignorePunctuationCheckBox.SetValue(_config.vocalizerConfig["autoLanguageSwitching"]["ignorePunctuationInLanguageDetection"])
			settingsSizerHelper.addItem(self._ignorePunctuationCheckBox)

			latinChoiceLocaleNames = [self.localesToNames[l] for l in self._latinLocales]
			self._latinChoice = settingsSizerHelper.addLabeledControl(_("Language assumed for latin characters:"), wx.Choice, choices=latinChoiceLocaleNames)
			latinLocale = _config.vocalizerConfig["autoLanguageSwitching"]["latinCharactersLanguage"]
			try:
				self._latinChoice.Select(self._latinLocales.index(latinLocale))
			except ValueError:
				self._latinChoice.Select(0)
			if not latinChoiceLocaleNames:
				self._latinChoice.Disable()

			CJKChoiceLocaleNames = [self.localesToNames[l] for l in self._CJKLocales]
			self._CJKChoice = settingsSizerHelper.addLabeledControl(_("Language assumed for CJK characters:"), wx.Choice, choices=CJKChoiceLocaleNames)
			CJKLocale = _config.vocalizerConfig["autoLanguageSwitching"]["CJKCharactersLanguage"]
			try:
				self._CJKChoice.Select(self._CJKLocales.index(CJKLocale))
			except ValueError:
				self._CJKChoice.Select(0)
			if not CJKChoiceLocaleNames:
				self._CJKChoice.Disable()

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
				if locale in _config.vocalizerConfig["autoLanguageSwitching"]:
					voice = _config.vocalizerConfig["autoLanguageSwitching"][locale]["voice"]
					if voice:
						self._voicesChoice.Select(voices.index(voice))
						self.onVoiceChange(None)
				else:
					self._voicesChoice.Select(0)
					self.onVoiceChange(None)

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

				self._rateSlider.SetValue(voiceInstance.rate)
				self._pitchSlider.SetValue(voiceInstance.pitch)
				self._volumeSlider.SetValue(voiceInstance.volume)
			else:
				self._dataToPercist[locale]["voice"] = "no-select"
				self.sliderDisable()

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

		def onPitchSliderScroll(self, event):
			voiceName = self._voicesChoice.GetStringSelection()
			if voiceName == '':
				return
			voiceInstance = self._manager.getVoiceInstance(voiceName)
			voiceInstance.pitch = self._pitchSlider.GetValue()

		def onVolumeSliderScroll(self, event):
			voiceName = self._voicesChoice.GetStringSelection()
			if voiceName == '':
				return
			voiceInstance = self._manager.getVoiceInstance(voiceName)
			voiceInstance.volume = self._volumeSlider.GetValue()

		def onCancel(self, event):
			if not self.ready:
				self.__class__._instance = None
				super(Dialog, self).onCancel(event)
				return

			for instance in self._manager._instanceCache.values():
				instance.rollback()

			self.__class__._instance = None
			super(Dialog, self).onCancel(event)

		def onOk(self, event):
			if not self.ready:
				self.__class__._instance = None
				super(Dialog, self).onOk(event)
				return

			# Update Configuration
			for locale in self._dataToPercist:
				if self._dataToPercist[locale]["voice"] != "no-select":
					_config.vocalizerConfig["autoLanguageSwitching"][locale] = self._dataToPercist[locale]
				else:
					try:
						del _config.vocalizerConfig["autoLanguageSwitching"][locale]
					except BaseException as e:
						pass

			_config.vocalizerConfig["autoLanguageSwitching"]["useUnicodeLanguageDetection"] = self._useUnicodeDetectionCheckBox.GetValue()
			_config.vocalizerConfig["autoLanguageSwitching"]["afterSymbolDetection"] = self._afterSymbolDetectionCheckBox.GetValue()
			_config.vocalizerConfig["autoLanguageSwitching"]["ignoreNumbersInLanguageDetection"] = self._ignoreNumbersCheckBox.GetValue()
			_config.vocalizerConfig["autoLanguageSwitching"]["ignorePunctuationInLanguageDetection"] = self._ignorePunctuationCheckBox.GetValue()
			if self._latinChoice.IsEnabled():
				_config.vocalizerConfig["autoLanguageSwitching"]["latinCharactersLanguage"] = self._latinLocales[self._latinChoice.GetCurrentSelection()]
			if self._CJKChoice.IsEnabled():
				_config.vocalizerConfig["autoLanguageSwitching"]["CJKCharactersLanguage"] = self._CJKLocales[self._CJKChoice.GetCurrentSelection()]

			import config
			for instance in self._manager._instanceCache.values():
				instance.commit()
				try:
					if instance.name == config.conf["speech"][self._synthInstance.name]["voice"]:
						config.conf["speech"][self._synthInstance.name]["rate"] = instance.rate
						config.conf["speech"][self._synthInstance.name]["pitch"] = instance.pitch
						config.conf["speech"][self._synthInstance.name]["volume"] = instance.volume
				except BaseException as e:
					pass

			if not self._synthInstance.name == 'WorldVoiceXVED2':
				self._manager.close()

			self.__class__._instance = None
			super(Dialog, self).onOk(event)

	return Dialog
