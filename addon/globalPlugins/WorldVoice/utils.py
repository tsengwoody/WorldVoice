import wx
from functools import wraps
from logHandler import log
import gui


def guard_errors(callback=None):
	"""
	Decorator that traps any unhandled exception inside an event handler.

	Parameters
	----------
	callback : Callable[[Any], None] or None
		A callback to invoke *after* the user presses OK in the dialog
		(or immediately if no dialog is shown).  `self` is passed in.
	"""
	def decorator(func):
		@wraps(func)
		def wrapper(self, *args, **kwargs):
			try:
				return func(self, *args, **kwargs)
			except Exception as e:
				log.error(f"Unhandled exception in {func.__qualname__}", exc_info=True)

				# show a modal error dialog
				gui.messageBox(
					# Body text
					_("An unexpected error occurred while processing your action.\n\n"
					  "Details: {err}\n\n"
					  "A full stack trace has been written to the NVDA log.")
					.format(err=str(e)),
					# Caption
					_("WorldVoice Setting Dialog - Error"),
					# Style flags
					wx.OK | wx.ICON_ERROR
				)

				# If the user acknowledged the dialog, invoke the callback
				if callable(callback):
					try:
						callback(self)
					except Exception:
						# Ensure callback failures don't raise further exceptions
						log.error("Error in guard_errors callback", exc_info=True)

				return None
		return wrapper
	return decorator
