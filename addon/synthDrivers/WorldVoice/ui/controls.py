"""Make, read and locate the control of one pipeline setting, for both settings panels.

The NVDA Voice panel and the Speech Pipeline panel build the controls WorldVoice owns from the
pipeline settings table through these functions, so a control kind is built the same way in
both. Both panels also read their controller controls and apply the table's depends_on rules
here, so a dependent control is enabled the same way in both. The layout rules themselves are in
ui/panelLayout.py. No engine driver imports this.
"""

from collections.abc import Callable, Sequence
from typing import Any

import wx
from gui import nvdaControls

from .panelLayout import (
	ABSENT,
	choiceIndex,
	choiceValues,
	dependentStates,
	fromDisplay,
	labelText,
	selectedValue,
	toDisplay,
)

# The change event of each control kind that may control other settings.
CHANGE_EVENTS = {"checkbox": wx.EVT_CHECKBOX, "choice": wx.EVT_CHOICE}


def makeControl(parent: Any, helper: Any, spec: Any, value: Any) -> Any:
	"""Add the control for spec to helper's sizer, showing value, and return it.

	The caller passes the helper: one helper keeps NVDA's spacing between rows, a fresh one per
	control leaves no spacer behind when the row is moved.
	"""
	label = labelText(spec)
	if spec.control == "checkbox":
		control = helper.addItem(wx.CheckBox(parent, label=label))
		control.SetValue(value)
	elif spec.control == "choice":
		control = helper.addLabeledControl(
			label,
			wx.Choice,
			choices=[choiceLabel for _value, choiceLabel in spec.choices],
		)
		control.Select(choiceIndex(choiceValues(spec), value))
	elif spec.control == "slider":
		control = helper.addLabeledControl(
			label,
			wx.Slider,
			value=toDisplay(spec, value),
			minValue=toDisplay(spec, spec.min_value),
			maxValue=toDisplay(spec, spec.max_value),
			style=wx.SL_HORIZONTAL,
		)
	elif spec.control == "spin":
		control = helper.addLabeledControl(
			label,
			nvdaControls.SelectOnFocusSpinCtrl,
			min=spec.min_value,
			max=spec.max_value,
			initial=value,
		)
	elif spec.control == "text":
		control = helper.addLabeledControl(label, wx.TextCtrl)
		control.SetValue(value)
	else:
		raise ValueError(f"Unknown control for pipeline setting {spec.key}: {spec.control!r}")
	return control


def controlValue(spec: Any, control: Any) -> Any:
	"""The value to save from control; None for a choice with no selection."""
	if spec.control == "choice":
		return selectedValue(choiceValues(spec), control.GetCurrentSelection())
	if spec.control == "slider":
		return fromDisplay(spec, control.GetValue())
	return control.GetValue()


def controlRow(control: Any, spec: Any) -> Any:
	"""The settings-sizer item of control: a checkbox is added as itself, others in their own sizer."""
	return control if spec.control == "checkbox" else control.GetContainingSizer()


def readControl(spec: Any, control: Any, driverOptions: Sequence[str] | None = None) -> Any:
	"""A controller's value as its control shows it, for panelLayout.dependentStates.

	ABSENT without a control (another synth has none). driverOptions are the option ids of a
	choice NVDA made for a driver setting, in list order; None for a control WorldVoice made from
	the table, which reads as controlValue. No selection reads as None.
	"""
	if control is None:
		return ABSENT
	if driverOptions is not None and spec.control == "choice":
		# No selection (-1) names no option, although the list's last option is at -1.
		return selectedValue(driverOptions, control.GetSelection())
	return controlValue(spec, control)


def applyDependencies(
	specs: Sequence[Any],
	read: Callable[[str], Any],
	controlOf: Callable[[Any], Any],
) -> None:
	"""Enable or disable each dependent control of specs from read(controller key).

	controlOf(spec) is the panel's control for spec, or None. A dependent with no control, or
	whose controller reads ABSENT, is left alone. Only Enable is called: disabled controls keep
	their values, and onSave still stores them.
	"""
	states = dependentStates(specs, read)
	for spec in specs:
		control = controlOf(spec)
		if spec.key in states and control is not None:
			control.Enable(states[spec.key])
