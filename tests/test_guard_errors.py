"""guard_errors keeps a failing settings handler from reaching wx and tells the user."""

import pytest
from ui_harness import load_utils


@pytest.fixture
def env(monkeypatch):
	return load_utils(monkeypatch)


def guarded(env, body, callback=None):
	class Panel:
		@env.module.guard_errors(callback=callback)
		def onChange(self, *args, **kwargs):
			return body(*args, **kwargs)

	return Panel()


def test_a_handler_that_succeeds_returns_its_result_silently(env):
	panel = guarded(env, lambda value, *, scale: value * scale)
	assert panel.onChange(3, scale=2) == 6
	assert panel.onChange.__name__ == "onChange"
	assert env.shown == [] and env.logged == []


def test_a_failing_handler_logs_shows_the_error_and_runs_the_callback(env):
	called = []

	def fail(event):
		raise KeyError("voice")

	panel = guarded(env, fail, callback=called.append)

	assert panel.onChange("event") is None

	assert env.logged == [("error", "Unhandled exception in guarded.<locals>.Panel.onChange")]
	((message, caption, style),) = env.shown
	assert message.startswith("An unexpected error occurred while processing your action.")
	assert "Details: 'voice'" in message
	assert caption == "WorldVoice Setting Dialog - Error"
	assert style == env.wx.OK | env.wx.ICON_ERROR
	assert called == [panel]


def test_a_failing_callback_is_logged_not_raised(env):
	def fail():
		raise RuntimeError("handler")

	def broken_callback(panel):
		raise RuntimeError("callback")

	guarded(env, fail, callback=broken_callback).onChange()

	assert [entry[1] for entry in env.logged] == [
		"Unhandled exception in guarded.<locals>.Panel.onChange",
		"Error in guard_errors callback",
	]
	assert len(env.shown) == 1


def test_without_a_callback_only_the_message_is_shown(env):
	def fail():
		raise RuntimeError("handler")

	guarded(env, fail).onChange()
	assert len(env.shown) == 1


def test_interrupts_are_not_trapped(env):
	def interrupt():
		raise KeyboardInterrupt

	with pytest.raises(KeyboardInterrupt):
		guarded(env, interrupt).onChange()
	assert env.shown == []
