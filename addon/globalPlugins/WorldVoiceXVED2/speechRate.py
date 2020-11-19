import wx
from autoSettingsUtils.utils import paramToPercent, percentToParam
from gui import guiHelper
import addonHandler
import gui
from collections import defaultdict
import speech
from synthDrivers.WorldVoiceXVED2 import _config, _vocalizer
from synthDrivers.WorldVoiceXVED2._voiceManager import VoiceManager

addonHandler.initTranslation()

class SpeechRateSettingsDialog(gui.SettingsDialog):
	title = _("Speech Rate Settings")
	def __init__(self, parent):
		_config.load()
		self.ready = False
		with _vocalizer.preOpenVocalizer() as check:
			if check:
				self.ready = True
				_vocalizer.initialize(lambda x: None)
				manager = VoiceManager()
				self._synthInstance = speech.getSynth()
				if self._synthInstance.name == 'WorldVoiceXVED2':
					self._manager = self._synthInstance._voiceManager
				else:
					self._manager = manager
				self._localeToVoices = manager.localeToVoicesMap
				self.localesToNames = manager.localesToNamesMap
				self._locales = sorted([l for l in self._localeToVoices if len(self._localeToVoices[l]) > 0])
		super(SpeechRateSettingsDialog, self).__init__(parent)

	def makeSettings(self, sizer):
		synthInfo = _('Your current speech synthesizer is not ready.')
		if not self.ready:
			infoLabel = wx.StaticText(self, label = synthInfo)
			infoLabel.Wrap(self.GetSize()[0])
			sizer.Add(infoLabel)
			return False

		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)

		helpLabel = wx.StaticText(self, label=_("Select a language, and then configure the voice to be used:"))
		helpLabel.Wrap(self.GetSize()[0])
		settingsSizerHelper.addItem(helpLabel)

		localeNames = [self.localesToNames[l] for l in self._locales]
		self._localesChoice = settingsSizerHelper.addLabeledControl(_("Locale Name:"), wx.Choice, choices=localeNames)
		self.Bind(wx.EVT_CHOICE, self.onLocaleChanged, self._localesChoice)

		self._voicesChoice = settingsSizerHelper.addLabeledControl(_("Voice Name:"), wx.Choice, choices=[])
		self.Bind(wx.EVT_CHOICE, self.onVoiceChange, self._voicesChoice)

		self._speechRateSlider = settingsSizerHelper.addLabeledControl(_("&Rate:"), wx.Slider, value = 50, minValue = 0, maxValue = 100, style = wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onSpeechRateSliderScroll, self._speechRateSlider)

		self._pitchSlider = settingsSizerHelper.addLabeledControl(_("&Pitch:"), wx.Slider, value = 50, minValue = 0, maxValue = 100, style = wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onPitchSliderScroll, self._pitchSlider)

		self._volumeSlider = settingsSizerHelper.addLabeledControl(_("V&olume:"), wx.Slider, value = 50, minValue = 0, maxValue = 100, style = wx.SL_HORIZONTAL)
		self.Bind(wx.EVT_SLIDER, self.onVolumeSliderScroll, self._volumeSlider)

	def postInit(self):
		if not self.ready:
			return False
		self._updateVoicesSelection()
		self._localesChoice.SetFocus()
		self.sliderDisable()

	def _updateVoicesSelection(self):
		localeIndex = self._localesChoice.GetCurrentSelection()
		if localeIndex < 0:
			self._voicesChoice.SetItems([])
		else:
			locale = self._locales[localeIndex]
			voices = sorted(self._localeToVoices[locale])
			self._voicesChoice.SetItems(voices)
			if locale in _config.vocalizerConfig["autoLanguageSwitching"]:
				voice = _config.vocalizerConfig["autoLanguageSwitching"][locale]["voice"]
				if voice:
					self.sliderEnable()
					self._voicesChoice.Select(voices.index(voice))
					self.onVoiceChange(None)

	def sliderEnable(self):
		self._speechRateSlider.Enable()
		self._pitchSlider.Enable()
		self._volumeSlider.Enable()

	def sliderDisable(self):
		self._speechRateSlider.Disable()
		self._pitchSlider.Disable()
		self._volumeSlider.Disable()

	def onLocaleChanged(self, event):
		self._updateVoicesSelection()

	def onVoiceChange(self, event):
		voiceName = self._voicesChoice.GetStringSelection()
		if voiceName == '':
			self.sliderDisable()
			return False
		self.sliderEnable()
		voiceInstance = self._manager.getVoiceInstance(voiceName)

		value = _vocalizer.getParameter(voiceInstance, _vocalizer.VE_PARAM_SPEECHRATE)
		speechRate = paramToPercent(value, _vocalizer.RATE_MIN, _vocalizer.RATE_MAX)
		self._speechRateSlider.SetValue(speechRate)

		value = _vocalizer.getParameter(voiceInstance, _vocalizer.VE_PARAM_PITCH)
		pitch = paramToPercent(value, _vocalizer.PITCH_MIN, _vocalizer.PITCH_MAX)
		self._pitchSlider.SetValue(pitch)

		volume = value = _vocalizer.getParameter(voiceInstance, _vocalizer.VE_PARAM_VOLUME)
		self._volumeSlider.SetValue(volume)

	def onSpeechRateSliderScroll(self, event):
		voiceName = self._voicesChoice.GetStringSelection()
		if voiceName == '':
			return False
		voiceInstance = self._manager.getVoiceInstance(voiceName)
		value = self._speechRateSlider.GetValue()
		speechrate = percentToParam(value, _vocalizer.RATE_MIN, _vocalizer.RATE_MAX)
		_vocalizer.setParameter(voiceInstance, _vocalizer.VE_PARAM_SPEECHRATE, speechrate)

	def onPitchSliderScroll(self, event):
		voiceName = self._voicesChoice.GetStringSelection()
		if voiceName == '':
			return False
		voiceInstance = self._manager.getVoiceInstance(voiceName)
		value = self._pitchSlider.GetValue()
		pitch = percentToParam(value, _vocalizer.PITCH_MIN, _vocalizer.PITCH_MAX)
		_vocalizer.setParameter(voiceInstance, _vocalizer.VE_PARAM_PITCH, pitch)

	def onVolumeSliderScroll(self, event):
		voiceName = self._voicesChoice.GetStringSelection()
		if voiceName == '':
			return False
		voiceInstance = self._manager.getVoiceInstance(voiceName)
		value = self._volumeSlider.GetValue()
		_vocalizer.setParameter(voiceInstance, _vocalizer.VE_PARAM_VOLUME, int(value))

	def onOk(self, event):
		if not self._synthInstance.name == 'WorldVoiceXVED2':
			self._manager.close()
		return super(SpeechRateSettingsDialog, self).onOk(event)
