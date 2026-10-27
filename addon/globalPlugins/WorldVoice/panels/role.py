"""The Speech Role panel: the wx side of RolePanelPresenter."""

import addonHandler
import config
import gui
import wx
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel
from logHandler import log
from synthDrivers.WorldVoice.pipeline.context import worldvoice_synth

from ..rolePresenter import RolePanelPresenter
from ..utils import guard_errors, reportError
from .base import notWorldVoiceNotice

addonHandler.initTranslation()


def got_error_callback(panel):
	dialog = wx.GetTopLevelParent(panel)
	dialog.onCancel(None)
	wx.CallAfter(gui.mainFrame.popupSettingsDialog, type(dialog))


class SpeechRoleSettingsPanel(SettingsPanel):
	title = _("Speech Role")
	NO_SELECT = "no-select"

	def makeSettings(self, sizer):
		self.disable = False
		synth = worldvoice_synth()
		if synth is None:
			notWorldVoiceNotice(self, sizer)
			self.disable = True
			return

		self._manager = synth.voiceManager

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
		if current.voiceManager is not self._manager:
			# NVDA rebuilt WorldVoice (e.g. after an audio device change); the panel edits the old one.
			log.warning("WorldVoice restarted while the voice settings were open; role settings not saved")
			return
		try:
			self._presenter.apply()
		except Exception as error:
			log.error("Failed to save voice settings", exc_info=True)
			reportError(error)
			# NVDA's settings dialog aborts the save and stays open only on ValueError.
			raise ValueError("WorldVoice voice settings were not saved") from error
