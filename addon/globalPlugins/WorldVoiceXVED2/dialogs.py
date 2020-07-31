import wx
from gui import guiHelper
import addonHandler
import gui
from collections import defaultdict
import languageHandler
from synthDrivers.WorldVoiceXVED2 import _config, languageDetection, _vocalizer

addonHandler.initTranslation()

class VocalizerLanguageSettingsDialog(gui.SettingsDialog):
	title = _("Automatic Language Switching Settings")

	def __init__(self, parent):
		_config.load()
		self._localeToVoices = {}

		with _vocalizer.preOpenVocalizer() as check:
			if check:
				for l, v in _vocalizer.getAvailableResources().items():
					self._localeToVoices[l.id] = v
					if "_" in l.id:
						lang = l.id.split("_")[0]
						if lang not in self._localeToVoices:
							self._localeToVoices[lang] = []
						self._localeToVoices[lang].extend(v)

		self._dataToPercist = defaultdict(lambda: {})
		self._locales = sorted([l for l in self._localeToVoices if len(self._localeToVoices[l]) > 0])
		latinSet = set(languageDetection.ALL_LATIN) & set(l for l in self._locales if len(l) == 2)
		self._latinLocales = sorted(list(latinSet))
		CJKSet = set(languageDetection.CJK) & set(l for l in self._locales if len(l) == 2)
		self._CJKLocales = sorted(list(CJKSet))
		super(VocalizerLanguageSettingsDialog, self).__init__(parent)

	def makeSettings(self, sizer):
		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)

		helpLabel = wx.StaticText(self, label=_("Select a language, and then configure the voice to be used:"))
		helpLabel.Wrap(self.GetSize()[0])
		settingsSizerHelper.addItem(helpLabel)

		localeNames = list(map(self._getLocaleReadableName, self._locales))
		self._localesChoice = settingsSizerHelper.addLabeledControl(_("Locale Name:"), wx.Choice, choices=localeNames)
		self.Bind(wx.EVT_CHOICE, self.onLocaleChanged, self._localesChoice)

		self._voicesChoice = settingsSizerHelper.addLabeledControl(_("Voice Name:"), wx.Choice, choices=[])
		self.Bind(wx.EVT_CHOICE, self.onVoiceChange, self._voicesChoice)

		self._useUnicodeDetectionCheckBox = wx.CheckBox(self,
		# Translators: Wether to use or not unicode characters based language detection.
			label=_("Detect text language based on unicode characters"))
		self._useUnicodeDetectionCheckBox.SetValue(_config.vocalizerConfig["autoLanguageSwitching"]["useUnicodeLanguageDetection"])
		settingsSizerHelper.addItem(self._useUnicodeDetectionCheckBox)

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

		latinChoiceLocaleNames = [self._getLocaleReadableName(l) for l in self._latinLocales]
		self._latinChoice = settingsSizerHelper.addLabeledControl(_("Language assumed for latin characters:"), wx.Choice, choices=latinChoiceLocaleNames)
		latinLocale = _config.vocalizerConfig["autoLanguageSwitching"]["latinCharactersLanguage"]
		try:
			self._latinChoice.Select(self._latinLocales.index(latinLocale))
		except ValueError:
			self._latinChoice.Select(0)
		if not latinChoiceLocaleNames:
			self._latinChoice.Disable()

		CJKChoiceLocaleNames = [self._getLocaleReadableName(l) for l in self._CJKLocales]
		self._CJKChoice = settingsSizerHelper.addLabeledControl(_("Language assumed for CJK characters:"), wx.Choice, choices=CJKChoiceLocaleNames)
		CJKLocale = _config.vocalizerConfig["autoLanguageSwitching"]["CJKCharactersLanguage"]
		try:
			self._CJKChoice.Select(self._CJKLocales.index(CJKLocale))
		except ValueError:
			self._CJKChoice.Select(0)
		if not CJKChoiceLocaleNames:
			self._CJKChoice.Disable()

	def postInit(self):
		self._updateVoicesSelection()
		self._localesChoice.SetFocus()

	def _updateVoicesSelection(self):
		localeIndex = self._localesChoice.GetCurrentSelection()
		if localeIndex < 0:
			self._voicesChoice.SetItems([])
		else:
			locale = self._locales[localeIndex]
			voices = sorted([v.id for v in self._localeToVoices[locale]])
			self._voicesChoice.SetItems(voices)
			if locale in _config.vocalizerConfig["autoLanguageSwitching"]:
				voice = _config.vocalizerConfig["autoLanguageSwitching"][locale]["voice"]
				if voice:
					self._voicesChoice.Select(voices.index(voice))

	def onLocaleChanged(self, event):
		self._updateVoicesSelection()

	def onVoiceChange(self, event):
		localeIndex = self._localesChoice.GetCurrentSelection()
		if localeIndex >= 0:
			locale = self._locales[localeIndex]
			self._dataToPercist[locale]["voice"] = self._voicesChoice.GetStringSelection()
		else:
			self._dataToPercist[locale]["voice"] = None

	def onOk(self, event):
		# Update Configuration
		for locale in self._dataToPercist:
			_config.vocalizerConfig["autoLanguageSwitching"][locale] = self._dataToPercist[locale]

		_config.vocalizerConfig["autoLanguageSwitching"]["useUnicodeLanguageDetection"] = self._useUnicodeDetectionCheckBox.GetValue()
		_config.vocalizerConfig["autoLanguageSwitching"]["ignoreNumbersInLanguageDetection"] = self._ignoreNumbersCheckBox.GetValue()
		_config.vocalizerConfig["autoLanguageSwitching"]["ignorePunctuationInLanguageDetection"] = self._ignorePunctuationCheckBox.GetValue()
		if self._latinChoice.IsEnabled():
			_config.vocalizerConfig["autoLanguageSwitching"]["latinCharactersLanguage"] = self._latinLocales[self._latinChoice.GetCurrentSelection()]
		if self._CJKChoice.IsEnabled():
			_config.vocalizerConfig["autoLanguageSwitching"]["CJKCharactersLanguage"] = self._CJKLocales[self._CJKChoice.GetCurrentSelection()]
		super(VocalizerLanguageSettingsDialog, self).onOk(event)

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s - %s" % (description, locale) if description else locale
