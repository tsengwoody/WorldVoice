# coding: utf-8

import copy
import os
import wx

import addonHandler
import core
import globalVars
import gui
from gui import nvdaControls
from gui import guiHelper
from gui.settingsDialogs import SettingsDialog
import queueHandler

from .contextHelp import *
from .models import SpeechSymbols, SpeechSymbol, SPEECH_SYMBOL_LANGUAGE_LABELS, SPEECH_SYMBOL_MODE_LABELS

addonHandler.initTranslation()

base_path = globalVars.appArgs.configPath


class AddSymbolDialog(
		ContextHelpMixin,
		wx.Dialog  # wxPython does not seem to call base class initializer, put last in MRO
):

	helpId = "SymbolPronunciation"
	
	def __init__(self, parent):
		# Translators: This is the label for the add symbol dialog.
		super().__init__(parent, title=_("Add Symbol"))
		mainSizer=wx.BoxSizer(wx.VERTICAL)
		sHelper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)

		# Translators: This is the label for the edit field in the add symbol dialog.
		symbolText = _("&Symbol:")
		self.identifierTextCtrl = sHelper.addLabeledControl(symbolText, wx.TextCtrl)

		sHelper.addDialogDismissButtons(self.CreateButtonSizer(wx.OK | wx.CANCEL))

		mainSizer.Add(sHelper.sizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL)
		mainSizer.Fit(self)
		self.SetSizer(mainSizer)
		self.identifierTextCtrl.SetFocus()
		self.CentreOnScreen()


class SpeechSymbolsDialog(SettingsDialog):
	_instance = None

	def __new__(cls, *args, **kwargs):
		obj = super(SpeechSymbolsDialog, cls).__new__(cls, *args, **kwargs)
		cls._instance = obj
		return obj

	def __init__(self,parent):
		# Translators: This is the label for the unicode setting dialog.
		self.speechSymbols = None
		self.title = _("Unicode Setting")
		super(SpeechSymbolsDialog, self).__init__(
			parent,
			resizeable=True,
		)

	def makeSettings(self, settingsSizer):
		if not self.speechSymbols:
			self.speechSymbols = SpeechSymbols()
			self.speechSymbols.load('unicode.dic')
			self.filteredSymbols = self.symbols = [copy.copy(symbol) for symbol in self.speechSymbols.symbols.values()]
		self.pendingRemovals = {}

		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		# Translators: The label of a text field to search for symbols in the speech symbols dialog.
		filterText = pgettext("speechSymbols", "&Filter by:")
		self.filterEdit = sHelper.addLabeledControl(
			labelText = filterText,
			wxCtrlClass=wx.TextCtrl,
			size=(self.scaleSize(310), -1),
		)
		self.filterEdit.Bind(wx.EVT_TEXT, self.onFilterEditTextChange)

		# Translators: The label for symbols list in symbol pronunciation dialog.
		symbolsText = _("&Symbols")
		self.symbolsList = sHelper.addLabeledControl(
			symbolsText,
			nvdaControls.AutoWidthColumnListCtrl,
			autoSizeColumn=2,  # The replacement column is likely to need the most space
			itemTextCallable=self.getItemTextForList,
			style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VIRTUAL
		)

		# Translators: The label for a column in symbols list used to identify a symbol.
		self.symbolsList.InsertColumn(0, _("Unicode"), width=self.scaleSize(150))
		# Translators: The label for a column in symbols list used to identify a replacement.
		self.symbolsList.InsertColumn(1, _("Replacement"))
		# Translators: The label for a column in symbols list used to identify a symbol's speech level (either none, some, most, all or character).
		self.symbolsList.InsertColumn(2, _("Language"))
		# Translators: The label for a column in symbols list which specifies when the actual symbol will be sent to the synthesizer (preserved).
		# See the "Punctuation/Symbol Pronunciation" section of the User Guide for details.
		self.symbolsList.InsertColumn(3, _("Mode"))
		self.symbolsList.Bind(wx.EVT_LIST_ITEM_FOCUSED, self.onListItemFocused)

		# Translators: The label for the group of controls in symbol pronunciation dialog to change the pronunciation of a symbol.
		changeSymbolText = _("Change selected symbol")
		changeSymbolHelper = sHelper.addItem(guiHelper.BoxSizerHelper(
			parent=self,
			sizer=wx.StaticBoxSizer(
				parent=self,
				label=changeSymbolText,
				orient=wx.VERTICAL,
			)
		))

		# Used to ensure that event handlers call Skip(). Not calling skip can cause focus problems for controls. More
		# generally the advice on the wx documentation is: "In general, it is recommended to skip all non-command events
		# to allow the default handling to take place. The command events are, however, normally not skipped as usually
		# a single command such as a button click or menu item selection must only be processed by one handler."
		def skipEventAndCall(handler):	
			def wrapWithEventSkip(event):
				if event:
					event.Skip()
				return handler()
			return wrapWithEventSkip

		# Translators: The label for the edit field in symbol pronunciation dialog to change the replacement text of a symbol.
		replacementText = _("&Replacement")
		self.replacementEdit = changeSymbolHelper.addLabeledControl(
			labelText=replacementText,
			wxCtrlClass=wx.TextCtrl,
			size=(self.scaleSize(300), -1),
		)
		self.replacementEdit.Bind(wx.EVT_TEXT, skipEventAndCall(self.onSymbolEdited))

		languageText = _("&language")
		languageChoices = [SPEECH_SYMBOL_LANGUAGE_LABELS[language] for language in SPEECH_SYMBOL_LANGUAGE_LABELS]
		self.languageList = changeSymbolHelper.addLabeledControl(languageText, wx.Choice, choices=languageChoices)
		self.languageList.Bind(wx.EVT_CHOICE, skipEventAndCall(self.onSymbolEdited))

		modeText = _("&Detect language mode")
		modeChoices = [SPEECH_SYMBOL_MODE_LABELS[mode] for mode in SPEECH_SYMBOL_MODE_LABELS]
		self.modeList = changeSymbolHelper.addLabeledControl(modeText, wx.Choice, choices=modeChoices)
		self.modeList.Bind(wx.EVT_CHOICE, skipEventAndCall(self.onSymbolEdited))

		bHelper = sHelper.addItem(guiHelper.ButtonHelper(orientation=wx.HORIZONTAL))
		# Translators: The label for a button in the Symbol Pronunciation dialog to add a new symbol.
		addButton = bHelper.addButton(self, label=_("&Add"))

		# Translators: The label for a button in the Symbol Pronunciation dialog to remove a symbol.
		self.removeButton = bHelper.addButton(self, label=_("Re&move"))
		self.removeButton.Disable()

		addButton.Bind(wx.EVT_BUTTON, self.OnAddClick)
		self.removeButton.Bind(wx.EVT_BUTTON, self.OnRemoveClick)

		# Populate the unfiltered list with symbols.
		self.filter()

	def postInit(self):
		self.symbolsList.SetFocus()

	def filter(self, filterText=''):
		NONE_SELECTED = -1
		previousSelectionValue = None
		previousIndex = self.symbolsList.GetFirstSelected()  # may return NONE_SELECTED
		if previousIndex != NONE_SELECTED:
			previousSelectionValue = self.filteredSymbols[previousIndex]

		if not filterText:
			self.filteredSymbols = self.symbols
		else:
			# Do case-insensitive matching by lowering both filterText and each symbols's text.
			filterText = filterText.lower()
			self.filteredSymbols = [
				symbol for symbol in self.symbols
				if filterText in symbol.displayName.lower()
				or filterText in symbol.replacement.lower()
			]
		self.symbolsList.ItemCount = len(self.filteredSymbols)

		# sometimes filtering may result in an empty list.
		if not self.symbolsList.ItemCount:
			self.editingItem = None
			# disable the "change symbol" controls, since there are no items in the list.
			self.replacementEdit.Disable()
			self.languageList.Disable()
			self.modeList.Disable()
			self.removeButton.Disable()
			return  # exit early, no need to select an item.

		# If there was a selection before filtering, try to preserve it
		newIndex = 0  # select first item by default.
		if previousSelectionValue:
			try:
				newIndex = self.filteredSymbols.index(previousSelectionValue)
			except ValueError:
				pass

		# Change the selection
		self.symbolsList.Select(newIndex)
		self.symbolsList.Focus(newIndex)
		# We don't get a new focus event with the new index.
		self.symbolsList.sendListItemFocusedEvent(newIndex)

	def getItemTextForList(self, item, column):
		symbol = self.filteredSymbols[item]
		if column == 0:
			return symbol.displayName
		elif column == 1:
			return symbol.replacement
		elif column == 2:
			return SPEECH_SYMBOL_LANGUAGE_LABELS[symbol.language]
		elif column == 3:
			return SPEECH_SYMBOL_MODE_LABELS[symbol.mode]
		else:
			raise ValueError("Unknown column: %d" % column)

	def onSymbolEdited(self):
		if self.editingItem is not None:
			# Update the symbol the user was just editing.
			item = self.editingItem
			symbol = self.filteredSymbols[item]
			symbol.replacement = self.replacementEdit.Value
			symbol.language = list(SPEECH_SYMBOL_LANGUAGE_LABELS.keys())[self.languageList.Selection]
			symbol.mode = list(SPEECH_SYMBOL_MODE_LABELS.keys())[self.modeList.Selection]

	def onListItemFocused(self, evt):
		# Update the editing controls to reflect the newly selected symbol.
		item = evt.GetIndex()
		symbol = self.filteredSymbols[item]
		self.editingItem = item
		# ChangeValue and Selection property used because they do not cause EVNT_CHANGED to be fired.
		self.replacementEdit.ChangeValue(symbol.replacement)
		self.languageList.Selection = list(SPEECH_SYMBOL_LANGUAGE_LABELS.keys()).index(symbol.language)
		self.modeList.Selection = list(SPEECH_SYMBOL_MODE_LABELS.keys()).index(symbol.mode)
		self.removeButton.Enable()
		self.replacementEdit.Enable()
		self.languageList.Enable()
		self.modeList.Enable()
		evt.Skip()

	def OnAddClick(self, evt):
		with AddSymbolDialog(self) as entryDialog:
			if entryDialog.ShowModal() != wx.ID_OK:
				return
			identifier = entryDialog.identifierTextCtrl.GetValue()
			if not identifier:
				return
		# Clean the filter, so we can select the new entry.
		self.filterEdit.Value=""
		self.filter()
		for index, symbol in enumerate(self.symbols):
			if identifier == symbol.identifier:
				# Translators: An error reported in the Symbol Pronunciation dialog when adding a symbol that is already present.
				gui.messageBox(_('Symbol "%s" is already present.') % identifier,
					_("Error"), wx.OK | wx.ICON_ERROR)
				self.symbolsList.Select(index)
				self.symbolsList.Focus(index)
				self.symbolsList.SetFocus()
				return
		addedSymbol = SpeechSymbol(identifier)
		try:
			del self.pendingRemovals[identifier]
		except KeyError:
			pass
		addedSymbol.displayName = identifier
		addedSymbol.replacement = ""
		addedSymbol.language = list(SPEECH_SYMBOL_LANGUAGE_LABELS.keys())[0]
		addedSymbol.mode = list(SPEECH_SYMBOL_MODE_LABELS.keys())[0]
		self.symbols.append(addedSymbol)
		self.symbolsList.ItemCount = len(self.symbols)
		index = self.symbolsList.ItemCount - 1
		self.symbolsList.Select(index)
		self.symbolsList.Focus(index)
		# We don't get a new focus event with the new index.
		self.symbolsList.sendListItemFocusedEvent(index)
		self.symbolsList.SetFocus()

	def OnRemoveClick(self, evt):
		index = self.symbolsList.GetFirstSelected()
		symbol = self.filteredSymbols[index]
		self.pendingRemovals[symbol.identifier] = symbol
		del self.filteredSymbols[index]
		if self.filteredSymbols is not self.symbols:
			self.symbols.remove(symbol)
		self.symbolsList.ItemCount = len(self.filteredSymbols)
		# sometimes removing may result in an empty list.
		if not self.symbolsList.ItemCount:
			self.editingItem = None
			# disable the "change symbol" controls, since there are no items in the list.
			self.replacementEdit.Disable()
			self.languageList.Disable()
			self.modeList.Disable()
			self.removeButton.Disable()
		else:
			index = min(index, self.symbolsList.ItemCount - 1)
			self.symbolsList.Select(index)
			self.symbolsList.Focus(index)
			# We don't get a new focus event with the new index.
			self.symbolsList.sendListItemFocusedEvent(index)
		self.symbolsList.SetFocus()

	def onCancel(self, event):
		self.__class__._instance = None
		super(SpeechSymbolsDialog, self).onCancel(event)

	def onOk(self, evt):
		self.onSymbolEdited()
		self.editingItem = None
		for symbol in self.pendingRemovals.values():
			self.speechSymbols.deleteSymbol(symbol)
		for symbol in self.symbols:
			self.speechSymbols.updateSymbol(symbol)
		try:
			self.speechSymbols.save()
		except IOError as e:
			log.error("Error saving user symbols info: %s" % e)
		self.speechSymbols = None
		if gui.messageBox(
			# Translators: The message displayed
			_("For the edited unicode rule to apply, NVDA must be restarted. Press enter to restart NVDA, or cancel to exit at a later time."),
			# Translators: The title of the dialog
			_("unicode rule edited"),wx.OK|wx.CANCEL|wx.ICON_WARNING,self
		)==wx.OK:
			queueHandler.queueFunction(queueHandler.eventQueue,core.restart)

		self.__class__._instance = None
		super(SpeechSymbolsDialog, self).onOk(evt)

	def _refreshVisibleItems(self):
		count = self.symbolsList.GetCountPerPage()
		first = self.symbolsList.GetTopItem()
		self.symbolsList.RefreshItems(first, first+count)

	def onFilterEditTextChange(self, evt):
		self.filter(self.filterEdit.Value)
		self._refreshVisibleItems()
		evt.Skip()
