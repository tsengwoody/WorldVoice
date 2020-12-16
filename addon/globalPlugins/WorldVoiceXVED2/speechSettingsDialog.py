from collections import defaultdict

import wx
from autoSettingsUtils.utils import paramToPercent, percentToParam
import addonHandler
import config
import gui
from gui import guiHelper
import speech

addonHandler.initTranslation()

def SpeechSettingsDialog():
	from synthDrivers.WorldVoiceXVED2 import _config, _core, VoiceManager
	class Dialog(gui.SettingsDialog):
		title = _("Speech Rate Settings")
		def __init__(self, parent):
			_config.load()
			self.ready = False
			with _core.preOpen() as check:
				if check:
					self.ready = True
					self._synthInstance = speech.getSynth()
					if self._synthInstance.name == 'WorldVoiceXVED2':
						self._manager = self._synthInstance._voiceManager
					else:
						_core.initialize(lambda x: None)
						self._manager = VoiceManager()
					self._localeToVoices = self._manager.localeToVoicesMap
					self.localesToNames = self._manager.localesToNamesMap
					self._locales = sorted([l for l in self._localeToVoices if len(self._localeToVoices[l]) > 0])
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

		def postInit(self):
			if not self.ready:
				return
			self._updateVoicesSelection()
			self._localesChoice.SetFocus()
			self.sliderDisable()

		def _updateVoicesSelection(self):
			localeIndex = self._localesChoice.GetCurrentSelection()
			if localeIndex < 0:
				self._voicesChoice.SetItems([])
			else:
				locale = self._locales[localeIndex]
				voices = ["default"] + sorted(self._localeToVoices[locale])
				self._voicesChoice.SetItems(voices)
				if locale in _config.vocalizerConfig["autoLanguageSwitching"]:
					voice = _config.vocalizerConfig["autoLanguageSwitching"][locale]["voice"]
					if voice:
						self._voicesChoice.Select(voices.index(voice))
						self.onVoiceChange(None)
				else:
					self._voicesChoice.Select(0)
					self.onVoiceChange(None)

		def sliderEnable(self):
			self._rateSlider.Enable()
			self._pitchSlider.Enable()
			self._volumeSlider.Enable()

		def sliderDisable(self):
			self._rateSlider.Disable()
			self._pitchSlider.Disable()
			self._volumeSlider.Disable()

		def onLocaleChanged(self, event):
			self._updateVoicesSelection()

		def onVoiceChange(self, event):
			voiceName = self._voicesChoice.GetStringSelection()
			if voiceName == "default":
				self.sliderDisable()
				return
			self.sliderEnable()
			voiceInstance = self._manager.getVoiceInstance(voiceName)

			self._rateSlider.SetValue(voiceInstance.rate)
			self._pitchSlider.SetValue(voiceInstance.pitch)
			self._volumeSlider.SetValue(voiceInstance.volume)

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
			for instance in self._manager._instanceCache.values():
				instance.rollback()
			return super(Dialog, self).onCancel(event)

		def onOk(self, event):
			for instance in self._manager._instanceCache.values():
				instance.commit()
				try:
					if instance.name == config.conf["speech"][self._synthInstance.name]["voice"]:
						config.conf["speech"][self._synthInstance.name]["rate"] = instance.rate
						config.conf["speech"][self._synthInstance.name]["pitch"] = instance.pitch
						config.conf["speech"][self._synthInstance.name]["volume"] = instance.volume
				except:
					pass

			if not self._synthInstance.name == 'WorldVoiceXVED2':
				self._manager.close()
			return super(Dialog, self).onOk(event)

	return Dialog
