"""Stand-ins for wx and NVDA's settings GUI, and loaders for WorldVoice's settings UI modules.

The fakes keep only what WorldVoice's panels, dialogs and global plugin touch: controls hold a
value, a selection and an enabled state, sizers keep their items in order and know which are
shown, and ``Bind`` records handlers so ``fire`` can deliver an event the way wx does (the
handler bound last runs first, ``Skip`` passes the event on, and a command event reaches the
panel's handlers after the control's own). A parent keeps its windows in creation order
(``children``, the order NVDA's object navigation follows) apart from its Tab order
(``tab_order``), and a labelled control's label is a window just before it. The loaders run the real add-on
modules against these fakes, so module-level code and the real ``guard_errors`` take part.
"""

from types import SimpleNamespace

from addon_loader import ADDON, WORLDVOICE, alias_package, load_source
from nvda_stubs import StubModules, configobj_stub, worldvoice_conf
from pipeline_harness import LOG_SWITCH_ORDER

PLUGIN_DIR = ADDON / "globalPlugins/WorldVoice"
NOT_FOUND = -1
# wx.BOTTOM, the border flag NVDA gives each driver row (settingsDialogs.py:1585-1590).
BOTTOM = 0x80


class Control:
	"""A wx window: label, choices, value, selection, enabled state and bound handlers."""

	def __init__(self, parent=None, label=None, choices=None, value=None, **kwargs):
		self.parent, self.label, self.choices, self.value = parent, label, list(choices or []), value
		self.kwargs = kwargs
		self.selection = NOT_FOUND
		self.enabled = True
		self.focused = False
		self.bindings = []
		self.containing_sizer = None
		self.destroyed = False
		# A parent's children stay in creation order: the HWND sibling order NVDA's object
		# navigation follows. Tab order starts the same but is kept apart, since
		# MoveAfterInTabOrder changes only the Tab order.
		for order in (getattr(parent, "children", None), getattr(parent, "tab_order", None)):
			if order is not None:
				order.append(self)

	def __repr__(self):
		return f"<{type(self).__name__} {self.label!r}>"

	def __bool__(self):
		# wxPython: a destroyed window is falsy, which NVDA's "if self.lastControl:" relies on.
		return not self.destroyed

	def __getattribute__(self, name):
		# wxPython: any wx method or property of a destroyed window raises; Python attributes the
		# test reads (label, value, destroyed, ...) stay readable, as on a real dead wrapper.
		if (
			not name.startswith("_")
			and object.__getattribute__(self, "__dict__").get("destroyed")
			and any(name in vars(cls) for cls in type(self).__mro__ if cls is not object)
		):
			raise RuntimeError(f"wrapped C/C++ object of type {type(self).__name__} has been deleted")
		return object.__getattribute__(self, name)

	# Choice
	def Select(self, index):
		self.selection = index

	SetSelection = Select

	def GetCurrentSelection(self):
		return self.selection

	GetSelection = GetCurrentSelection

	@property
	def Selection(self):
		return self.selection

	@Selection.setter
	def Selection(self, index):
		self.selection = index

	def GetStringSelection(self):
		return self.choices[self.selection] if 0 <= self.selection < len(self.choices) else ""

	def SetItems(self, items):
		self.choices = list(items)
		self.selection = NOT_FOUND

	# Value controls
	def SetValue(self, value):
		self.value = value

	def GetValue(self):
		return self.value

	def IsChecked(self):
		return bool(self.value)

	# Window
	def Enable(self, enable=True):
		self.enabled = bool(enable)

	def Disable(self):
		self.enabled = False

	def IsEnabled(self):
		return self.enabled

	def Bind(self, event, handler, source=None):
		self.bindings.append((event, handler))

	def SetFocus(self):
		self.focused = True

	def Wrap(self, width):
		pass

	def SetBackgroundColour(self, colour):
		self.background = colour

	def GetContainingSizer(self):
		return self.containing_sizer

	def MoveAfterInTabOrder(self, other):
		"""Move this window after other in Tab order only; its place among the children stays."""
		if isinstance(other, Control) and not other:
			raise RuntimeError(f"wrapped C/C++ object of type {type(other).__name__} has been deleted")
		# wx asserts when other is not a sibling; the fake must not silently leave the order alone.
		assert getattr(other, "parent", None) is self.parent, f"{other!r} is not a sibling of {self!r}"
		tab_order = getattr(self.parent, "tab_order", None)
		if tab_order is not None and self in tab_order and other in tab_order:
			tab_order.remove(self)
			tab_order.insert(tab_order.index(other) + 1, self)


class CheckBox(Control):
	pass


class Choice(Control):
	pass


class Slider(Control):
	pass


class TextCtrl(Control):
	pass


class SpinCtrl(Control):
	"""A wx.SpinCtrl, made with keyword arguments only (min, max, initial), as the panels make it.

	Neither the initial value nor SetValue is clamped to min..max, and GetValue returns what was
	set, so a test sees the value the panel passed rather than one the fake corrected.
	"""

	def __init__(self, parent=None, *, min=0, max=100, initial=0, **kwargs):
		super().__init__(parent, value=initial, **kwargs)
		self.min, self.max = min, max

	def GetMin(self):
		return self.min

	def GetMax(self):
		return self.max


class SelectOnFocusSpinCtrl(SpinCtrl):
	"""NVDA's gui.nvdaControls.SelectOnFocusSpinCtrl: a wx.SpinCtrl that selects its value on focus."""


class StaticText(Control):
	pass


class Label(StaticText):
	"""The StaticText NVDA's LabeledControlHelper makes just before a labelled control, in its row."""


class StaticBox(Control):
	pass


class Spacer:
	"""The empty space a sizer adds with AddSpacer: neither a window nor a sizer."""

	def __init__(self, size):
		self.size = size

	def __repr__(self):
		return f"<Spacer {self.size}>"


class SizerItem:
	"""A wxSizerItem. wx deletes the item when it is detached, so reading a detached one raises."""

	def __init__(self, item, proportion=0, flag=0, border=0):
		self.item, self.proportion, self.flag, self.border = item, proportion, flag, border
		self.shown = True
		self.deleted = False

	def _alive(self):
		if self.deleted:
			raise RuntimeError("wxSizerItem was deleted by Detach")
		return self

	def GetSizer(self):
		return self._alive().item if isinstance(self.item, Sizer) else None

	def GetWindow(self):
		return None if isinstance(self._alive().item, Sizer | Spacer) else self.item

	def GetProportion(self):
		return self._alive().proportion

	def GetFlag(self):
		return self._alive().flag

	def GetBorder(self):
		return self._alive().border

	def SetFlag(self, flag):
		self._alive().flag = flag

	def SetBorder(self, border):
		self._alive().border = border


class Sizer:
	"""A wx sizer: its items in order, each shown or hidden."""

	def __init__(self, *args, **kwargs):
		self.items = []
		self.layouts = 0

	def _place(self, item):
		if isinstance(item, Control):
			item.containing_sizer = self

	def Add(self, item, proportion=0, flag=0, border=0):
		self._place(item)
		self.items.append(SizerItem(item, proportion, flag, border))

	def AddSpacer(self, size):
		self.items.append(SizerItem(Spacer(size)))

	def Insert(self, index, item, proportion=0, flag=0, border=0):
		# wx release builds drop an item inserted past the end (wxCHECK_MSG in wxSizer::Insert),
		# where list.insert would clamp the index; fail instead of hiding the lost row.
		assert 0 <= index <= len(self.items), f"index {index} out of range for {len(self.items)} items"
		self._place(item)
		self.items.insert(index, SizerItem(item, proportion, flag, border))

	def _find(self, item):
		for entry in self.items:
			if entry.item is item:
				return entry
		raise LookupError(f"{item!r} is not in this sizer")

	def GetItem(self, item):
		return self._find(item)

	def GetChildren(self):
		return list(self.items)

	def Detach(self, item):
		entry = self._find(item)
		self.items.remove(entry)
		entry.deleted = True

	def Show(self, item):
		self._find(item).shown = True

	def Hide(self, item):
		self._find(item).shown = False

	def IsShown(self, item):
		return self._find(item).shown

	def Layout(self):
		self.layouts += 1

	def Clear(self, delete_windows=False):
		"""Remove every item; with delete_windows, wx destroys the windows they hold, labels too."""
		if delete_windows:
			for window in self.windows():
				window.destroyed = True
				for name in ("children", "tab_order"):
					order = getattr(window.parent, name, None)
					if order is not None and window in order:
						order.remove(window)
		self.items = []

	def _expanded(self):
		result = []
		for entry in self.items:
			result.extend(entry.item._expanded() if isinstance(entry.item, Sizer) else [entry.item])
		return result

	def windows(self):
		"""Every window in this sizer and the sizers it holds, labels included."""
		return [item for item in self._expanded() if isinstance(item, Control)]

	def contents(self):
		"""Every item but labels, with nested sizers expanded in place."""
		return [item for item in self._expanded() if not isinstance(item, Label)]

	def controls(self):
		return [item for item in self.contents() if isinstance(item, Control)]


class StaticBoxSizer(Sizer):
	def __init__(self, box, orient=None):
		super().__init__()
		self.box = box


class BoxSizerHelper:
	"""NVDA's guiHelper.BoxSizerHelper: each labelled control gets a row in the given sizer.

	As in NVDA (gui/guiHelper.py addItem), every item but the helper's first is preceded by a
	spacer, so a test can see a spacer left behind when a row is moved.
	"""

	SPACE = 10

	def __init__(self, parent, orientation=None, sizer=None):
		self.parent = parent
		self.sizer = sizer if sizer is not None else Sizer()
		self.hasFirstItemBeenAdded = False

	def addLabeledControl(self, label, cls, **kwargs):
		# NVDA's LabeledControlHelper (gui/guiHelper.py:288-291): the label, then the control, in one row.
		row = Sizer()
		row.Add(Label(self.parent, label=label))
		control = cls(self.parent, **kwargs)
		control.label = label
		row.Add(control)
		self.addItem(row)
		return control

	def addItem(self, item, **kwargs):
		if self.hasFirstItemBeenAdded:
			self.sizer.AddSpacer(self.SPACE)
		self.sizer.Add(item)
		self.hasFirstItemBeenAdded = True
		return item


class Event:
	def __init__(self, source=None):
		self.source = source
		self.skipped = False

	def GetEventObject(self):
		return self.source

	def IsChecked(self):
		return bool(self.source.GetValue())

	def Skip(self):
		self.skipped = True


def fire(control, event_type, *, panel=None):
	"""Deliver event_type from control as wx would and return the event.

	Handlers bound on the control run first, then the event propagates to those the panel bound
	for this control; within each, the one bound last runs first and the event goes on only after
	Skip().
	"""
	event = Event(control)
	handlers = [h for e, h in reversed(control.bindings) if e == event_type]
	if panel is not None:
		handlers += [h for e, h, source in reversed(panel.bindings) if e == event_type and source is control]
	if not handlers:
		raise LookupError(f"nothing handles {event_type} from {control!r}")
	for handler in handlers:
		event.skipped = False
		handler(event)
		if not event.skipped:
			break
	return event


class SettingsPanel:
	"""NVDA's gui.settingsDialogs.SettingsPanel as far as WorldVoice's panels reach it."""

	def __init__(self):
		self.bindings = []
		self.children = []
		self.tab_order = []

	def Bind(self, event, handler, source=None):
		self.bindings.append((event, handler, source))

	def GetBackgroundColour(self):
		return "panel colour"

	def GetSize(self):
		return (600, 400)


class MultiCategorySettingsDialog:
	def __init__(self, parent):
		self.parent = parent
		self.opened_with = list(self.categoryClasses)

	def SetTitle(self, title):
		self.title = title


class DriverSetting:
	def __init__(self, id, displayName=None):
		self.id, self.displayName = id, displayName or id

	def __repr__(self):
		return f"<{type(self).__name__} {self.id}>"


class NumericDriverSetting(DriverSetting):
	pass


class BooleanDriverSetting(DriverSetting):
	pass


class VoiceSettingsPanel(SettingsPanel):
	"""NVDA's VoiceSettingsPanel (AutoSettingsMixin) as far as WorldVoice's subclass reaches it.

	Controls are made as NVDA makes them: a slider or a choice in its own sizer, a checkbox as
	itself, each inserted after the driver controls made before it and bound to write the
	setting. makeSettings updates the driver controls, then adds NVDA's own controls after them.
	"""

	def __init__(self, driver):
		super().__init__()
		self.sizerDict = {}
		self.lastControl = None
		self._driver = driver
		self.settingsSizer = Sizer()
		self.base_calls = []

	@property
	def driver(self):
		return self._driver

	def getSettings(self):
		return self._driver

	def _getSettingsStorage(self):
		return self._driver

	def _createNewControl(self, setting, settingsStorage):
		value = getattr(settingsStorage, setting.id)
		if isinstance(setting, BooleanDriverSetting):
			control = made = CheckBox(self, label=setting.displayName, value=value)
			setattr(self, f"{setting.id}Checkbox", control)
			control.Bind(EVT_CHECKBOX, lambda event: setattr(settingsStorage, setting.id, event.IsChecked()))
		else:
			made = Sizer()
			# NVDA's LabeledControlHelper makes the label first, in the same row.
			made.Add(Label(self, label=f"{setting.displayName}:"))
			if isinstance(setting, NumericDriverSetting):
				control = Slider(self, label=setting.displayName, value=value)
				setattr(self, f"{setting.id}Slider", control)
			else:
				options = list(getattr(self.getSettings(), f"available{setting.id.capitalize()}s").values())
				setattr(self, f"_{setting.id}s", options)
				control = Choice(self, label=setting.displayName, choices=[x.displayName for x in options])
				control.Select([x.id for x in options].index(value))
				setattr(self, f"{setting.id}List", control)

				def write(event, id=setting.id):
					# NVDA's StringDriverSettingChanger: the option at the selection, from the list in use.
					options = getattr(self, f"_{id}s")
					setattr(settingsStorage, id, options[event.GetEventObject().GetSelection()].id)

				control.Bind(EVT_CHOICE, write)
			made.Add(control)
		# NVDA moves each new driver control after the previous one (settingsDialogs.py:1457-1459).
		if self.lastControl:
			control.MoveAfterInTabOrder(self.lastControl)
		self.lastControl = control
		self.sizerDict[setting.id] = made
		self.settingsSizer.Insert(len(self.sizerDict) - 1, made, border=10, flag=BOTTOM)

	def updateDriverSettings(self, changedSetting=None):
		# NVDA's version: hide unsupported controls, then update or create the supported ones.
		settingsInst = self.getSettings()
		for name, sizer in self.sizerDict.items():
			if name != changedSetting and not settingsInst.isSupported(name):
				self.settingsSizer.Hide(sizer)
		for setting in settingsInst.supportedSettings:
			if setting.id == changedSetting:
				continue
			if setting.id in self.sizerDict:
				self._updateValueForControl(setting, self._getSettingsStorage())
			elif not setting.id.startswith("_"):
				self._createNewControl(setting, self._getSettingsStorage())
		self.settingsSizer.Layout()

	def makeSettings(self, settingsSizer):
		self.base_calls.append("makeSettings")
		self.updateDriverSettings()
		helper = BoxSizerHelper(self, sizer=settingsSizer)
		self.autoLanguageSwitchingCheckbox = helper.addItem(
			CheckBox(self, label="Automatic language switching (when supported)"),
		)

	def onSave(self):
		self.base_calls.append("onSave")

	def onDiscard(self):
		self.base_calls.append("onDiscard")

	def refreshGui(self):
		# NVDA's AutoSettingsMixin.refreshGui once the settings instance changed (a synth change):
		# every row and window goes, then makeSettings runs again on the same panel. NVDA leaves
		# lastControl as it was, and so does this.
		self.sizerDict.clear()
		self.settingsSizer.Clear(delete_windows=True)
		self.makeSettings(self.settingsSizer)
		self.settingsSizer.Layout()


EVT_CHECKBOX, EVT_CHOICE, EVT_SLIDER, EVT_MENU, EVT_WINDOW_DESTROY = (
	"EVT_CHECKBOX",
	"EVT_CHOICE",
	"EVT_SLIDER",
	"EVT_MENU",
	"EVT_WINDOW_DESTROY",
)


class MenuItem:
	def __init__(self, label, help=None, submenu=None):
		self.label, self.help, self.submenu = label, help, submenu
		self.destroyed = False

	def Destroy(self):
		self.destroyed = True


class Menu:
	def __init__(self):
		self.items = []

	def Append(self, id, label, help=None):
		item = MenuItem(label, help)
		self.items.append(item)
		return item

	def Insert(self, position, id, label, submenu):
		item = MenuItem(label, submenu=submenu)
		self.items.insert(position, item)
		return item

	def Remove(self, item):
		self.items.remove(item)


def fake_wx(stubs):
	"""Register a wx module made of the fakes above and return it.

	CallAfter only records: tests run what was scheduled through ``wx.called_after``.
	"""
	wx = stubs.module(
		"wx",
		Control=Control,
		CheckBox=CheckBox,
		Choice=Choice,
		Slider=Slider,
		TextCtrl=TextCtrl,
		SpinCtrl=SpinCtrl,
		StaticText=StaticText,
		StaticBox=StaticBox,
		StaticBoxSizer=StaticBoxSizer,
		BoxSizer=Sizer,
		Menu=Menu,
		EVT_CHECKBOX=EVT_CHECKBOX,
		EVT_CHOICE=EVT_CHOICE,
		EVT_SLIDER=EVT_SLIDER,
		EVT_MENU=EVT_MENU,
		EVT_WINDOW_DESTROY=EVT_WINDOW_DESTROY,
		NOT_FOUND=NOT_FOUND,
		ID_ANY=-1,
		ID_OK=5100,
		ID_CANCEL=5101,
		OK=0x4,
		YES=0x2,
		NO=0x8,
		CANCEL=0x10,
		ICON_WARNING=0x100,
		ICON_ERROR=0x200,
		ICON_INFORMATION=0x800,
		VERTICAL=0x8,
		EXPAND=0x2000,
		BOTTOM=BOTTOM,
		SL_HORIZONTAL=0x4,
		TE_READONLY=0x10,
		TE_MULTILINE=0x20,
		TE_WORDWRAP=0x1,
		BORDER_NONE=0x200000,
		called_after=[],
	)
	wx.CallAfter = lambda function, *args: wx.called_after.append((function, args))
	wx.GetTopLevelParent = lambda window: window.top_level_parent
	return wx


def gui_stubs(monkeypatch, *, answers=None):
	"""Register the NVDA GUI modules every settings UI module imports; return them as one namespace.

	gui.messageBox records (message, caption, style) and answers from answers, else wx.OK.
	"""
	stubs = StubModules(monkeypatch)
	stubs.translation()
	wx = fake_wx(stubs)
	shown, logged, popped = [], [], []
	answers = list(answers or [])

	def message_box(message, caption, style=0, parent=None):
		shown.append((message, caption, style))
		return answers.pop(0) if answers else wx.OK

	main_frame = SimpleNamespace(
		popupSettingsDialog=lambda dialog, *args: popped.append(dialog),
		onSaveConfigurationCommand=lambda event: popped.append("save configuration"),
	)
	gui = stubs.module("gui", messageBox=message_box, mainFrame=main_frame, _isDebug=lambda: False)
	gui.__path__ = []
	gui.guiHelper = stubs.module("gui.guiHelper", BoxSizerHelper=BoxSizerHelper)
	gui.nvdaControls = stubs.module("gui.nvdaControls", SelectOnFocusSpinCtrl=SelectOnFocusSpinCtrl)
	gui.settingsDialogs = stubs.module(
		"gui.settingsDialogs",
		SettingsPanel=SettingsPanel,
		MultiCategorySettingsDialog=MultiCategorySettingsDialog,
		VoiceSettingsPanel=VoiceSettingsPanel,
	)

	def record(level):
		return lambda *args, **kwargs: logged.append((level, args[0] if args else None))

	log = SimpleNamespace(
		**{
			level: record(level)
			for level in ("debug", "debugWarning", "info", "warning", "error", "exception")
		},
	)
	stubs.module("logHandler", log=log)
	stubs.module("addonHandler", initTranslation=lambda: None)
	return SimpleNamespace(
		stubs=stubs,
		wx=wx,
		gui=gui,
		shown=shown,
		answers=answers,
		logged=logged,
		popped=popped,
	)


def load_utils(monkeypatch):
	"""The real globalPlugins/WorldVoice/utils.py against the GUI stubs."""
	env = gui_stubs(monkeypatch)
	env.module = load_source(monkeypatch, "worldvoice_ui_utils", PLUGIN_DIR / "utils.py")
	return env


def _pipeline_ui(monkeypatch, stubs, conf):
	"""The real pipeline settings, layout rules and control builder; return (settings, controls).

	The alias packages have no submodules of their own, so every module the panels import from
	the synth package is loaded here, after the GUI stubs it needs.
	"""
	stubs.module("config", conf=conf)
	configobj_stub(stubs)
	alias_package(monkeypatch, "synthDrivers")
	alias_package(monkeypatch, "synthDrivers.WorldVoice")
	alias_package(monkeypatch, "synthDrivers.WorldVoice.pipeline")
	alias_package(monkeypatch, "synthDrivers.WorldVoice.ui")
	load_source(monkeypatch, "synthDrivers.WorldVoice.numberLanguage", WORLDVOICE / "numberLanguage.py")
	settings = load_source(
		monkeypatch,
		"synthDrivers.WorldVoice.pipeline.settings",
		WORLDVOICE / "pipeline/settings.py",
	)
	load_source(
		monkeypatch,
		"synthDrivers.WorldVoice.ui.panelLayout",
		WORLDVOICE / "ui/panelLayout.py",
	)
	controls = load_source(
		monkeypatch,
		"synthDrivers.WorldVoice.ui.controls",
		WORLDVOICE / "ui/controls.py",
	)
	return settings, controls


def load_pipeline_controls(monkeypatch, *, conf=None):
	"""The real ui/controls.py and the pipeline settings it builds controls for."""
	env = gui_stubs(monkeypatch)
	env.conf = conf if conf is not None else worldvoice_conf()
	env.settings, env.controls = _pipeline_ui(monkeypatch, env.stubs, env.conf)
	return env


class PipelineLog:
	"""The pipeline log service the panels and the plugin switch."""

	def __init__(self, enabled=False, calls=None):
		self.enabled = enabled
		self.calls = [] if calls is None else calls

	def enable(self):
		self.enabled = True
		self.calls.append("enable")

	def disable(self):
		self.enabled = False
		self.calls.append("disable")

	def export(self):
		self.calls.append("export")


def load_settings_dialog(monkeypatch, *, conf=None, synth=None, engines=(), answers=None):
	"""The real speechSettingsDialog.py, its real utils, pipeline settings and pipeline context.

	conf defaults to a fresh WorldVoice profile plus an empty speech section; synth is what
	getSynth returns (``env.current[0]`` changes it later). engines are (name, label, default)
	for ENGINE_SPECS, and get_engine_enabled reads the stored flag. The pipeline log service and
	its prompts are recorded in ``env.log_calls``; tests replace RolePanelPresenter on the module.
	"""
	env = gui_stubs(monkeypatch, answers=answers)
	stubs = env.stubs
	env.conf = conf if conf is not None else {**worldvoice_conf(), "speech": {"WorldVoice": {}}}
	env.current = [synth]
	env.queued = []
	env.beeps = []
	env.restart = lambda: None
	stubs.module("core", restart=env.restart)
	stubs.module("tones", beep=lambda *args: env.beeps.append(args))
	stubs.module(
		"queueHandler",
		eventQueue="event queue",
		queueFunction=lambda queue, function: env.queued.append((queue, function)),
	)
	stubs.module("synthDriverHandler", getSynth=lambda: env.current[0])
	env.settings, env.controls = _pipeline_ui(monkeypatch, stubs, env.conf)
	env.pipeline_settings = env.settings.pipeline_settings
	stubs.module("synthDrivers.WorldVoice.languageDetection", SCRIPT_LANGUAGES={})
	stubs.module("synthDrivers.WorldVoice.languageDetection.settings", detection_settings=None)
	env.engine_specs = tuple(
		SimpleNamespace(name=name, label=label, default_enabled=default) for name, label, default in engines
	)

	# The flag is read by the add-on's own engine discovery rules.
	alias_package(monkeypatch, "worldvoice_ui_engines", WORLDVOICE)
	alias_package(monkeypatch, "worldvoice_ui_engines.engine", WORLDVOICE / "engine")
	load_source(monkeypatch, "worldvoice_ui_engines.assembly", WORLDVOICE / "assembly.py")
	discovery = load_source(
		monkeypatch,
		"worldvoice_ui_engines.engine.discovery",
		WORLDVOICE / "engine/discovery.py",
	)

	def get_engine_enabled(name, section):
		(spec,) = [spec for spec in env.engine_specs if spec.name == name]
		return discovery.get_engine_enabled(section, spec)

	stubs.module(
		"synthDrivers.WorldVoice.engine",
		ENGINE_SPECS=env.engine_specs,
		get_engine_enabled=get_engine_enabled,
	)
	stubs.module("synthDrivers.WorldVoice.pipeline").LOG_SWITCHES = tuple(LOG_SWITCH_ORDER)
	load_source(monkeypatch, "synthDrivers.WorldVoice.pipeline.context", WORLDVOICE / "pipeline/context.py")
	env.log_calls = []
	env.pipeline_log = PipelineLog(calls=env.log_calls)
	env.export_answer = [False]
	env.confirm_answer = [env.wx.YES]
	package = "worldvoice_ui_test"
	alias_package(monkeypatch, package, PLUGIN_DIR)
	stubs.module(
		package + ".pipelineLog",
		pipeline_log=env.pipeline_log,
		ask_export=lambda: env.log_calls.append("ask export") or env.export_answer[0],
		confirm_enable=lambda *, allow_cancel: (
			env.log_calls.append(("confirm", allow_cancel)) or env.confirm_answer[0]
		),
	)
	stubs.module(package + ".rolePresenter", RolePanelPresenter=None)
	# Loaded here, not by the dialog's relative import, so it leaves sys.modules after the test.
	load_source(monkeypatch, package + ".utils", PLUGIN_DIR / "utils.py")
	env.module = load_source(
		monkeypatch,
		package + ".speechSettingsDialog",
		PLUGIN_DIR / "speechSettingsDialog.py",
	)
	return env


def make_panel(cls):
	"""A panel instance without NVDA's constructor, which would call makeSettings itself."""
	panel = cls.__new__(cls)
	SettingsPanel.__init__(panel)
	return panel


def load_voice_settings_dialogs(monkeypatch, *, conf=None):
	"""The real synthDrivers/WorldVoice/ui/voicePanel.py with real pipeline settings."""
	env = gui_stubs(monkeypatch)
	env.conf = conf if conf is not None else worldvoice_conf()
	env.settings, env.controls = _pipeline_ui(monkeypatch, env.stubs, env.conf)
	env.pipeline_settings = env.settings.pipeline_settings
	env.stubs.module("autoSettingsUtils").__path__ = []
	env.stubs.module(
		"autoSettingsUtils.driverSetting",
		DriverSetting=DriverSetting,
		NumericDriverSetting=NumericDriverSetting,
		BooleanDriverSetting=BooleanDriverSetting,
	)
	env.module = load_source(
		monkeypatch,
		"synthDrivers.WorldVoice.ui.voicePanel",
		WORLDVOICE / "ui/voicePanel.py",
	)
	return env


def load_global_plugin(monkeypatch, *, secure=False, log_enabled=False):
	"""The real globalPlugins/WorldVoice/__init__.py with its collaborators recorded in env.calls."""
	env = gui_stubs(monkeypatch)
	stubs = env.stubs
	env.calls = []
	calls = env.calls

	def record(name):
		return lambda *args, **kwargs: calls.append((name, *args))

	tray = SimpleNamespace(menu=Menu(), bindings=[])
	tray.Bind = lambda event, handler, item: tray.bindings.append((event, handler, item))
	env.gui.mainFrame.sysTrayIcon = tray
	env.tray = tray

	class GlobalPlugin:
		def __init__(self):
			pass

	stubs.module("globalPluginHandler", GlobalPlugin=GlobalPlugin)
	stubs.module("globalVars", appArgs=SimpleNamespace(secure=secure))
	stubs.module("ui", message=record("message"))
	stubs.module("scriptHandler", script=lambda **kwargs: lambda function: function)
	stubs.module(
		"addonHandler",
		initTranslation=lambda: None,
		getCodeAddon=lambda: SimpleNamespace(manifest={"summary": "WorldVoice"}),
	)
	env.restart = lambda: None
	stubs.module("core", restart=env.restart)
	stubs.module("queueHandler", eventQueue="event queue", queueFunction=record("queue"))
	alias_package(monkeypatch, "synthDrivers")
	alias_package(monkeypatch, "synthDrivers.WorldVoice")
	alias_package(monkeypatch, "synthDrivers.WorldVoice.pipeline")
	stubs.module(
		"synthDrivers.WorldVoice.pipeline.scope",
		pipeline_scope=SimpleNamespace(attach_global=record("attach"), detach_global=record("detach")),
	)
	stubs.module("synthDrivers.WorldVoice.pipeline.sayAll", patch=record("patch"), unpatch=record("unpatch"))
	env.workspace = ["workspace"]
	stubs.module("synthDrivers.WorldVoice.workspace", workspace_path=lambda: env.workspace[0])
	alias_package(monkeypatch, "generics")
	stubs.module("generics.coreArchive", extract_core_archive=record("extract"))
	package = "worldvoice_plugin_test"
	env.pipeline_log = PipelineLog(enabled=log_enabled, calls=calls)
	env.answers_for = {"confirm": env.wx.YES, "export": True, "disable on start": True}

	def answer(name):
		def ask(*args, **kwargs):
			calls.append(("ask", name))
			return env.answers_for[name]

		return ask

	stubs.module(
		package + ".pipelineLog",
		pipeline_log=env.pipeline_log,
		ask_disable_on_start=answer("disable on start"),
		ask_export=answer("export"),
		confirm_enable=answer("confirm"),
	)
	env.settings_dialog = type("WorldVoiceSettingsDialog", (), {})
	stubs.module(package + ".speechSettingsDialog", WorldVoiceSettingsDialog=env.settings_dialog)
	env.module = load_source(monkeypatch, package, PLUGIN_DIR / "__init__.py")
	return env


def pipeline_snapshot(panel):
	"""The pipeline settings a voice settings panel saved to restore on discard, or None."""
	return panel._pipelineSnapshot
