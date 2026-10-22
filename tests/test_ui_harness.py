"""The wx fakes keep window order and Tab order apart, as wx on Windows does.

NVDA's object navigation follows the HWND sibling order, which is the creation order; wx's
MoveAfterInTabOrder changes only where Tab goes. ui_harness models the first with a parent's
``children`` and the second with its ``tab_order``.
"""

from ui_harness import BoxSizerHelper, Label, SettingsPanel, Sizer, TextCtrl, make_panel


def test_move_after_in_tab_order_leaves_window_order():
	panel = make_panel(SettingsPanel)
	a, b, c = (TextCtrl(panel, label=name) for name in "abc")

	a.MoveAfterInTabOrder(c)

	assert panel.children == [a, b, c]
	assert panel.tab_order == [b, c, a]


def test_a_labeled_control_follows_its_label():
	panel = make_panel(SettingsPanel)
	sizer = Sizer()

	control = BoxSizerHelper(panel, sizer=sizer).addLabeledControl("X:", TextCtrl)

	label = panel.children[-2]
	assert panel.children[-1] is control
	assert (type(label), label.label) == (Label, "X:")
	(row,) = [entry.item for entry in sizer.items]
	assert [entry.item for entry in row.items] == [label, control]
	assert row.controls() == [control]


def test_clear_destroys_labels_and_drops_them_from_both_orders():
	panel = make_panel(SettingsPanel)
	sizer = Sizer()
	control = BoxSizerHelper(panel, sizer=sizer).addLabeledControl("X:", TextCtrl)
	label = panel.children[-2]

	sizer.Clear(delete_windows=True)

	assert label.destroyed and control.destroyed
	assert panel.children == panel.tab_order == []
