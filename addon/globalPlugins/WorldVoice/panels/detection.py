"""The Unicode Detection panel: the language assumed for each script of the detection table."""

import addonHandler
import wx
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel
from synthDrivers.WorldVoice.languageDetection.scriptLanguages import DETECTION_SCRIPTS, SCRIPT_LANGUAGES
from synthDrivers.WorldVoice.languageDetection.settings import detection_settings
from synthDrivers.WorldVoice.pipeline.context import worldvoice_synth

from .base import notWorldVoiceNotice

addonHandler.initTranslation()


class UnicodeDetectionSettingsPanel(SettingsPanel):
	title = _("Unicode Detection")

	def makeSettings(self, sizer):
		self.disable = False
		synth = worldvoice_synth()
		if synth is None:
			notWorldVoiceNotice(self, sizer)
			self.disable = True
			return

		self._manager = synth.voice_manager

		self.localesToNames = self._manager.locales_to_names_map
		self._locales = self._manager.languages
		self._detection = detection_settings.get()

		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=sizer)

		# One choice per script of the table, in its order; the labels are this panel's own.
		labels = self._script_labels()
		self._scriptChoices = {
			detectionScript.script: self._add_script_choice(
				settingsSizerHelper,
				detectionScript.script,
				labels[detectionScript.script],
			)
			for detectionScript in DETECTION_SCRIPTS
		}

		DetectLanguageTimingLabel = [
			_("Before NVDA processes speech commands"),
			_("After NVDA processes speech commands"),
		]
		self._DetectLanguageTimingValue = ["before", "after"]
		self._DLTChoice = settingsSizerHelper.addLabeledControl(
			_("Language detection timing:"),
			wx.Choice,
			choices=DetectLanguageTimingLabel,
		)
		self._DetectLanguageTiming = self._detection.timing
		try:
			self._DLTChoice.Select(self._DetectLanguageTimingValue.index(self._DetectLanguageTiming))
		except ValueError:
			self._DLTChoice.Select(0)

	def _script_labels(self):
		return {
			# Translators: Label of the choice of the language assumed for Latin letters.
			"Latin": _("Language assumed for latin characters:"),
			# Translators: Label of the choice of the language assumed for Han characters (CJK ideographs).
			"Han": _("Language assumed for CJK characters:"),
			# Translators: Label of the choice of the language assumed for Arabic letters.
			"Arabic": _("Language assumed for arabic characters:"),
			# Translators: Label of the choice of the language assumed for Cyrillic letters.
			"Cyrillic": _("Language assumed for cyrillic characters:"),
			# Translators: Label of the choice of the language assumed for Devanagari letters.
			"Devanagari": _("Language assumed for devanagari characters:"),
		}

	def _add_script_choice(self, helper, script, label):
		"""A choice of the available two-letter languages written in script."""
		candidates = set(SCRIPT_LANGUAGES[script])
		locales = sorted(candidates & {locale for locale in self._locales if len(locale) == 2})
		names = [self.localesToNames[locale] for locale in locales]
		choice = helper.addLabeledControl(label, wx.Choice, choices=names)
		stored = self._detection.script_language[script]
		try:
			choice.Select(locales.index(stored))
		except ValueError:
			choice.Select(0)
		if not names:
			choice.Disable()
		return choice, locales

	def onSave(self):
		if self.disable or worldvoice_synth() is None:
			return
		# The driver subscribes to these settings and re-registers detection when the timing changes.
		detection_settings.update(
			script_language={
				script: locales[choice.GetCurrentSelection()]
				for script, (choice, locales) in self._scriptChoices.items()
				if choice.IsEnabled()
			},
			timing=self._DetectLanguageTimingValue[self._DLTChoice.GetCurrentSelection()],
		)
