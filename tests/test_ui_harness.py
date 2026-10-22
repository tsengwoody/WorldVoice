"""The wx fakes keep window order and Tab order apart, as wx on Windows does.

NVDA's object navigation follows the HWND sibling order, which is the creation order; wx's
MoveAfterInTabOrder changes only where Tab goes. ui_harness models the first with a parent's
``children`` and the second with its ``tab_order``.
"""

import pytest
from ui_harness import BoxSizerHelper, Label, SettingsPanel, Sizer, TextCtrl, make_panel


def test_move_after_in_tab_order_leaves_window_order():
	panel = make_panel(SettingsPanel)
	a, b, c = (TextCtrl(panel, label=name) for name in "abc")

	a.MoveAfterInTabOrder(c)

	assert panel.children == [a, b, c]
	assert panel.tab_order == [b, c, a]


def test_move_after_in_tab_order_needs_a_sibling():
	# wx asserts when the window to follow has another parent; the fake must not ignore it.
	panel, other = make_panel(SettingsPanel), make_panel(SettingsPanel)
	a, b = TextCtrl(panel, label="a"), TextCtrl(other, label="b")

	with pytest.raises(AssertionError):
		a.MoveAfterInTabOrder(b)


@pytest.mark.parametrize("index", [-1, 2])
def test_insert_out_of_range_fails(index):
	# wx release builds drop an item inserted past the end (wxCHECK_MSG in wxSizer::Insert) instead
	# of appending it, and Python's list.insert would clamp it; the fake fails either way.
	sizer = Sizer()
	sizer.Add(Sizer())

	with pytest.raises(AssertionError):
		sizer.Insert(index, Sizer())


def test_insert_at_the_end_appends():
	sizer = Sizer()
	first, last = Sizer(), Sizer()
	sizer.Add(first)

	sizer.Insert(1, last)

	assert [entry.item for entry in sizer.items] == [first, last]


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
