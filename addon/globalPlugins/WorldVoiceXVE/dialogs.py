from collections import defaultdict
import wx
import addonHandler
addonHandler.initTranslation()
import gui
import languageHandler
from logHandler import log
from synthDrivers.WorldVoiceXVE import _config, languageDetection
from synthDrivers.WorldVoiceXVE._voiceManager import VoiceManager
from .utils import VocalizerOpened

class VocalizerLanguageSettingsDialog(gui.SettingsDialog):
	title = _("Automatic Language Switching Settings")
	def __init__(self, parent):
		with VocalizerOpened():
			manager = VoiceManager()
			self._localeToVoices = manager.localeToVoicesMap
			manager.close()
		self._dataToPercist = defaultdict(lambda : {})
		self._locales = sorted([l for l in self._localeToVoices if len(self._localeToVoices[l]) > 0])
		latinSet = set(languageDetection.ALL_LATIN) & set(l for l in self._locales if len(l) == 2)
		self._latinLocales = sorted(list(latinSet))
		super(VocalizerLanguageSettingsDialog, self).__init__(parent)

	def makeSettings(self, sizer):
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
		self._useUnicodeDetectionCheckBox = wx.CheckBox(self,
		# Translators: Wether to use or not unicode characters based language detection.
			label=_("Detect text language based on unicode characters"))
		self._useUnicodeDetectionCheckBox.SetValue(_config.vocalizerConfig['autoLanguageSwitching']['useUnicodeLanguageDetection'])
		
		self._ignorePonctuationAndNumbersCheckBox = wx.CheckBox(self,
		# Translators: Either to ignore or not ASCII punctuation and numbers when language detection is active
		label=_("Ignore numbers and common punctuation when detecting text language"))
		self._ignorePonctuationAndNumbersCheckBox.SetValue(_config.vocalizerConfig['autoLanguageSwitching']['ignorePonctuationAndNumbersInLanguageDetection'])
		
		latinSizer = wx.BoxSizer(wx.HORIZONTAL)
		latinLabel = wx.StaticText(self,
		# Translators: Option to set what language to assume for latin characters, in language detection
		label=_("Language assumed for latin characters:"))
		latinChoiceLocaleNames = [self._getLocaleReadableName(l) for l in self._latinLocales]
		self._latinChoice = wx.Choice(self, choices=latinChoiceLocaleNames)
		latinLocale = _config.vocalizerConfig['autoLanguageSwitching']['latinCharactersLanguage']
		try:
			self._latinChoice.Select(self._latinLocales.index(latinLocale))
		except ValueError:
			self._latinChoice.Select(0)
		latinSizer.Add(latinLabel)
		latinSizer.Add(self._latinChoice)
		
		sizer.Add(localesSizer)
		sizer.Add(voicesSizer)
		sizer.Add(self._useUnicodeDetectionCheckBox)
		sizer.Add(self._ignorePonctuationAndNumbersCheckBox)
		sizer.Add(latinSizer)

	def postInit(self):
		self._updateVoicesSelection()
		self._localesChoice.SetFocus()

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
					self._voicesChoice.Select(voices.index(voice))

	def onLocaleChanged(self, event):
		self._updateVoicesSelection()

	def onVoiceChange(self, event):
		localeIndex = self._localesChoice.GetCurrentSelection()
		if localeIndex >= 0:
			locale = self._locales[localeIndex]
			self._dataToPercist[locale]['voice'] = self._voicesChoice.GetStringSelection()
		else:
			self._dataToPercist[locale]['voice'] = None

	def onOk(self, event):
		# Update Configuration
		_config.vocalizerConfig['autoLanguageSwitching'].update(self._dataToPercist)
		_config.vocalizerConfig['autoLanguageSwitching']['useUnicodeLanguageDetection'] = self._useUnicodeDetectionCheckBox.GetValue()
		_config.vocalizerConfig['autoLanguageSwitching']['ignorePonctuationAndNumbersInLanguageDetection'] = self._ignorePonctuationAndNumbersCheckBox.GetValue()
		_config.vocalizerConfig['autoLanguageSwitching']['latinCharactersLanguage'] = self._latinLocales[self._latinChoice.GetCurrentSelection()]
		_config.save()
		return super(VocalizerLanguageSettingsDialog, self).onOk(event)

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s - %s" % (description, locale) if description else locale
