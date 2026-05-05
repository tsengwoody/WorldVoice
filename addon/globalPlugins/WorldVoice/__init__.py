import os
from zipfile import ZipFile, BadZipFile

import addonHandler
import config
import globalPluginHandler
import globalVars
import gui
from logHandler import log
from scriptHandler import script
from synthDriverHandler import getSynth
import ui
import wx

from .speechSettingsDialog import WorldVoiceSettingsDialog
from generics.speechSymbols.views import SpeechSymbolsDialog

from synthDrivers.WorldVoice import WVStart, WVEnd
from synthDrivers.WorldVoice.pipeline import pl
from synthDrivers.WorldVoice.pipeline.settings import (
	apply_global_pipeline_scope,
	apply_pipeline_after_worldvoice_end,
	clear_global_pipeline_scope,
	load_pipeline_settings,
)
from synthDrivers.WorldVoice.sayAll import patch, unpatch

addonHandler.initTranslation()
ADDON_SUMMARY = addonHandler.getCodeAddon().manifest["summary"]
workspace_path = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace")


def on_worldvoice_start():
	clear_global_pipeline_scope(load_pipeline_settings())


def on_worldvoice_end():
	apply_pipeline_after_worldvoice_end(load_pipeline_settings())


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()

		WVStart.register(on_worldvoice_start)
		WVEnd.register(on_worldvoice_end)

		patch()
		if getSynth().name != "WorldVoice":
			apply_global_pipeline_scope(load_pipeline_settings(), getSynth().name)

		if globalVars.appArgs.secure:
			return

		self.createMenu()

		wx.CallAfter(self.check_log_record)

	def terminate(self):
		try:
			self.removeMenu()
		except wx.PyDeadObjectError:
			pass

		unpatch()
		if getSynth().name != "WorldVoice":
			clear_global_pipeline_scope(load_pipeline_settings())

		WVStart.unregister(on_worldvoice_start)
		WVEnd.unregister(on_worldvoice_end)

	def createMenu(self):
		self.submenu_WorldVoice = wx.Menu()

		item = self.submenu_WorldVoice.Append(wx.ID_ANY, _("&Settings"), _("Settings."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.popup_SpeechSettingsDialog, item)
		item = self.submenu_WorldVoice.Append(wx.ID_ANY, _("&Unicode Settings"), _("Unicode Settings."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.popup_SpeechSymbolsDialog, item)
		item = self.submenu_WorldVoice.Append(wx.ID_ANY, _("&File Import"), _("Import File."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onFileImport, item)
		# if not AisoundVoice.install():
		# 	item = self.submenu_WorldVoice.Append(wx.ID_ANY, _("&Aisound Core Install"), _("Install Aisound Core."))
		# 	gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onAisoundCoreInstall, item)

		self.submenu_item = gui.mainFrame.sysTrayIcon.menu.Insert(2, wx.ID_ANY, _("WorldVoice"), self.submenu_WorldVoice)

	def removeMenu(self):
		if self.submenu_item is not None:
			try:
				gui.mainFrame.sysTrayIcon.menu.Remove(self.submenu_item)
			except AttributeError:  # We can get this somehow from wx python when NVDA is shuttingdown, just ignore
				pass
			self.submenu_item.Destroy()

	def onFileImport(self, event):
		with wx.FileDialog(gui.mainFrame, message=_("Import file..."), wildcard="zip files (*.zip)|*.zip") as entryDialog:
			if entryDialog.ShowModal() != wx.ID_OK:
				return
			core_zip_path = entryDialog.GetPath()

		workspace_path = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace")

		try:
			os.makedirs(workspace_path, exist_ok=True)

			with ZipFile(core_zip_path, 'r') as core_file:
				try:
					core_file.testzip()
				except (BadZipFile, RuntimeError) as e:
					log.error(f"Cannot extract corrupted archive '{os.path.basename(core_zip_path)}': {e}")
					return

				skipped_files = []
				for member in core_file.infolist():
					try:
						core_file.extract(member, path=workspace_path)
					except Exception as e:
						# Catching a broad Exception is intentional. Locked files (e.g., in-use DLLs)
						# can raise different errors on different OSes. This safely skips them.
						log.warning(f"Could not extract '{member.filename}' (likely in use): {e}")
						skipped_files.append(member.filename)

				if skipped_files:
					log.warning(f"Update complete. Skipped {len(skipped_files)} in-use file(s): {skipped_files}")
				else:
					log.info("All components extracted successfully.")

		except Exception:
			# Catch any other unexpected errors during I/O or ZipFile init.
			log.exception(f"An unexpected error occurred while processing '{os.path.basename(core_zip_path)}'")

			gui.messageBox(
				_("Import fail"),
				_("Import File"), wx.OK
			)
		else:
			if gui.messageBox(
				_("For the new file to import, NVDA must be restarted. Are you want to restart NVDA now ?"),
				_("Import File"), wx.OK | wx.CANCEL | wx.ICON_WARNING
			) == wx.OK:
				import core
				import queueHandler
				queueHandler.queueFunction(queueHandler.eventQueue, core.restart)

	def popup_SpeechSettingsDialog(self, event):
		wx.CallAfter(gui.mainFrame.popupSettingsDialog, WorldVoiceSettingsDialog)

	def popup_SpeechSymbolsDialog(self, event):
		if SpeechSymbolsDialog._instance is None:
			gui.mainFrame.popupSettingsDialog(SpeechSymbolsDialog)
		else:
			ui.message(_("SpeechSymbolsDialog have already been opened"))

	@script(
		description=_("popup speech settings dialog"),
		category=ADDON_SUMMARY,
	)
	def script_popup_SpeechSettingsDialog(self, gesture):
		self.popup_SpeechSettingsDialog(None)

	@script(
		description=_("popup unicode settings dialog"),
		category=ADDON_SUMMARY,
	)
	def script_popup_unicode_settings_dialog(self, gesture):
		self.popup_SpeechSymbolsDialog(None)

	@script(
		description=_("switch log record"),
		category=ADDON_SUMMARY,
	)
	def script_switch_log_record(self, gesture):
		if not config.conf["WorldVoice"]["log"]["enable"]:
			wx.CallAfter(self.enable_log_record)
		else:
			wx.CallAfter(self.disable_log_record)

	def check_log_record(self):
		if config.conf["WorldVoice"]["log"]["enable"]:
			if gui.messageBox(
				# Translators: The message displayed
				_("Logging of WorldVoice’s speech pipeline is enabled. This may reduce speech response speed. If you are not debugging, we recommend disabling it. Would you like to disable it now?"),
				# Translators: The title of the dialog
				_("Speech Pipeline Logging"),
				wx.YES | wx.NO, gui.mainFrame
			) == wx.YES:
				config.conf["WorldVoice"]["log"]["enable"] = False
				try:
					pl.export()
				except Exception:
					pass

	def enable_log_record(self):
		if gui.messageBox(
			# Translators: The message displayed
			_("Enabling logging of WorldVoice’s speech pipeline will reduce speech response speed. If you are not debugging, we recommend keeping it disabled. Would you like to enable it anyway?"),
			# Translators: The title of the dialog
			_("Speech Pipeline Logging"),
			wx.YES | wx.NO, gui.mainFrame
		) == wx.YES:
			config.conf["WorldVoice"]["log"]["enable"] = True
			ui.message(_("turn on WorldVoice`s log record"))

	def disable_log_record(self):
		config.conf["WorldVoice"]["log"]["enable"] = False
		if gui.messageBox(
			# Translators: The message displayed
			_("Logging of WorldVoice’s speech pipeline has been disabled. Would you like to export the pipeline log now?"),
			# Translators: The title of the dialog
			_("Speech Pipeline Logging"),
			wx.YES | wx.NO, gui.mainFrame
		) == wx.YES:
			try:
				pl.export()
			except Exception:
				pass
			ui.message(_("turn off WorldVoice`s log record"))
