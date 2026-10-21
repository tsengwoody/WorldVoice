"""Make, read and locate the control of one pipeline setting, for both settings panels.

The NVDA Voice panel and the Speech Pipeline panel build the controls WorldVoice owns from the
pipeline settings table through these functions, so a control kind is built the same way in
both. The layout rules themselves are in pipeline/panelLayout.py. No engine driver imports this.
"""

from typing import Any

import wx
from gui import nvdaControls

from .pipeline.panelLayout import (
	choice_index,
	choice_values,
	from_display,
	label_text,
	selected_value,
	to_display,
)

# The change event of each control kind that may control other settings.
CHANGE_EVENTS = {"checkbox": wx.EVT_CHECKBOX, "choice": wx.EVT_CHOICE}


def make_control(parent: Any, helper: Any, spec: Any, value: Any) -> Any:
	"""Add the control for spec to helper's sizer, showing value, and return it.

	The caller passes the helper: one helper keeps NVDA's spacing between rows, a fresh one per
	control leaves no spacer behind when the row is moved.
	"""
	label = label_text(spec)
	if spec.control == "checkbox":
		control = helper.addItem(wx.CheckBox(parent, label=label))
		control.SetValue(value)
	elif spec.control == "choice":
		control = helper.addLabeledControl(
			label,
			wx.Choice,
			choices=[choiceLabel for _value, choiceLabel in spec.choices],
		)
		control.Select(choice_index(choice_values(spec), value))
	elif spec.control == "slider":
		control = helper.addLabeledControl(
			label,
			wx.Slider,
			value=to_display(spec, value),
			minValue=to_display(spec, spec.min_value),
			maxValue=to_display(spec, spec.max_value),
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


def control_value(spec: Any, control: Any) -> Any:
	"""The value to save from control; None for a choice with no selection."""
	if spec.control == "choice":
		return selected_value(choice_values(spec), control.GetCurrentSelection())
	if spec.control == "slider":
		return from_display(spec, control.GetValue())
	return control.GetValue()


def control_row(control: Any, spec: Any) -> Any:
	"""The settings-sizer item of control: a checkbox is added as itself, others in their own sizer."""
	return control if spec.control == "checkbox" else control.GetContainingSizer()
