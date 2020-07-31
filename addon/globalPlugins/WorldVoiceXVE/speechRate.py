#vocalizer_globalPlugin/dialogs.py
#A part of the vocalizer driver for NVDA (Non Visual Desktop Access)
#Copyright (C) 2012, 2013 Rui Batista <ruiandrebatista@gmail.com>
#Copyright (C) 2012, 2013 Tiflotecnia, lda. <www.tiflotecnia.com>
#This file is covered by the GNU General Public License.
#See the file GPL.txt for more details.

from collections import defaultdict
import wx
import addonHandler
addonHandler.initTranslation()
import config
import gui
import languageHandler
from logHandler import log
from synthDrivers.WorldVoiceXVE import _config, storage
from synthDrivers.WorldVoiceXVE._voiceManager import VoiceManager
from synthDrivers.WorldVoiceXVE import languageDetection
from .utils import VocalizerOpened
import speech
from synthDrivers.WorldVoiceXVE import _vocalizer

class SpeechRateSettingsDialog(gui.SettingsDialog):
	title = _("Speech Rate Settings")
	def __init__(self, parent):
		with VocalizerOpened():
			manager = VoiceManager()
			self._localeToVoices = manager.localeToVoicesMap
			manager.close()
		self._locales = sorted([l for l in self._localeToVoices if len(self._localeToVoices[l]) > 0])
		self._synthInstance = speech.getSynth()
		super(SpeechRateSettingsDialog, self).__init__(parent)

	def makeSettings(self, sizer):
		synthInfo = _('Your current speech synthesizer is the %s. Please select the WorldVoiceXVE as the speech synthesizer in the NVDA speech settings.')
		synthName = self._synthInstance.description
		synthInfo = synthInfo.replace('%s', synthName)
		if not self._synthInstance.name == 'WorldVoiceXVE':
			infoLabel = wx.StaticText(self, label = synthInfo)
			infoLabel.Wrap(self.GetSize()[0])
			sizer.Add(infoLabel)
			return False

		helpLabel = wx.StaticText(self, label=_("Select a locale, and then configure the voice to be used:"))
		helpLabel.Wrap(self.GetSize()[0])
		sizer.Add(helpLabel)
		localesSizer = wx.BoxSizer(wx.HORIZONTAL)
		localesLabel = wx.StaticText(self, label=_("Locale Name:"))
		localesSizer.Add(localesLabel)
		localeNames = list(map(self._getLocaleReadableName, self._locales))
		self._localesChoice = wx.Choice(self, choices=localeNames)
		self.Bind(wx.EVT_CHOICE, self.onLocaleChanged, self._localesChoice)
		localesSizer.Add(self._localesChoice)
		voicesSizer = wx.BoxSizer(wx.HORIZONTAL)
		voicesLabel = wx.StaticText(self, label=_("Voice Name:"))
		voicesSizer.Add(voicesLabel)
		self._voicesChoice = wx.Choice(self, choices=[])
		self.Bind(wx.EVT_CHOICE, self.onVoiceChange, self._voicesChoice)
		voicesSizer.Add(self._voicesChoice)
		speechRateSizer = wx.BoxSizer(wx.HORIZONTAL)
		speechRateLabel = wx.StaticText(self, label=_("&Rate:"))
		speechRateSizer.Add(speechRateLabel)
		self._speechRateSlider = wx.Slider(self, value = 50, minValue = 0, maxValue = 100, style = wx.SL_HORIZONTAL)	
		self.Bind(wx.EVT_SLIDER, self.onSpeechRateSliderScroll, self._speechRateSlider)
		speechRateSizer.Add(self._speechRateSlider)

		sizer.Add(localesSizer)
		sizer.Add(voicesSizer)
		sizer.Add(speechRateSizer)

	def postInit(self):
		if self._synthInstance.name == 'WorldVoiceXVE':
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
			if locale in _config.vocalizerConfig['autoLanguageSwitching']:
				voice = _config.vocalizerConfig['autoLanguageSwitching'][locale]['voice']
				if voice:
					self.sliderEnable()
					self._voicesChoice.Select(voices.index(voice))
					self.onVoiceChange(None)

	def sliderEnable(self):
		self._speechRateSlider.Enable()

	def sliderDisable(self):
		self._speechRateSlider.Disable()

	def onLocaleChanged(self, event):
		self._updateVoicesSelection()

	def onVoiceChange(self, event):
		voiceName = self._voicesChoice.GetStringSelection()
		if voiceName == '':
			self.sliderDisable()
			return False
		self.sliderEnable()
		voiceInstance = self._synthInstance._voiceManager.getVoiceInstance(voiceName)

		import math
		value = _vocalizer.getParameter(voiceInstance, _vocalizer.VE_PARAM_SPEECHRATE)
		norm = value / 100.0
		factor = 25 if norm  >= 1 else 50
		speechRate = int(round(50 + factor * math.log(norm, 2)))
		self._speechRateSlider.SetValue(speechRate)

	def onSpeechRateSliderScroll(self, event):
		voiceName = self._voicesChoice.GetStringSelection()
		if voiceName == '':
			return False
		voiceInstance = self._synthInstance._voiceManager.getVoiceInstance(voiceName)
		speechRate = value = self._speechRateSlider.GetValue()
		factor = 25.0 if value >= 50 else 50.0
		norm = 2.0 ** ((value - 50.0) / factor)
		speechrate = value = int(round(norm * 100))
		_vocalizer.setParameter(voiceInstance, _vocalizer.VE_PARAM_SPEECHRATE, speechrate)

	def onOk(self, event):
		return super(SpeechRateSettingsDialog, self).onOk(event)

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s - %s" % (description, locale) if description else locale
