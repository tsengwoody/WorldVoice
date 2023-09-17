import ctypes
import threading

from logHandler import log
from winUser import WM_QUIT, VK_SHIFT, VK_LSHIFT, VK_RSHIFT, VK_VOLUME_DOWN, VK_VOLUME_UP

from . import keyboard_hook
from synthDriverHandler import getSynth


class Hook:
	def __init__(self):
		self.pressed = set()
		self.pressed_max_count = 0
		self.reset_flag = False
		self.hook_thread = None

	def start(self):
		self.hook_thread = threading.Thread(target=self.hook)
		self.hook_thread.daemon = True
		self.hook_thread.start()

	def end(self):
		if self.hook_thread is not None:
			ctypes.windll.user32.PostThreadMessageW(self.hook_thread.ident, WM_QUIT, 0, 0)
			self.hook_thread.join()
			self.hook_thread = None

	def hook(self):
		log.debug("Hook thread start")
		keyhook = keyboard_hook.KeyboardHook()
		keyhook.register_callback(self.hook_callback)
		msg = ctypes.wintypes.MSG()
		while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
			pass
		log.debug("Hook thread end")
		keyhook.free()

	def hook_callback(self, **kwargs):
		if not getSynth():
			return False
		if not getSynth().name == "WorldVoice":
			return False
		taskManager = getSynth()._voiceManager.taskManager
		if not taskManager.SAPI5:
			return False
		if kwargs['pressed'] and not kwargs['vk_code'] in [
			VK_SHIFT,
			VK_LSHIFT,
			VK_RSHIFT,
			VK_VOLUME_DOWN,
			VK_VOLUME_UP,
		]:
			if self.reset_flag:
				self.reset_flag = False
				taskManager.reset()
				taskManager.cancel()
			self.pressed.add(kwargs['vk_code'])
		elif not kwargs['pressed']:
			try:
				self.pressed.remove(kwargs['vk_code'])
			except KeyError:
				pass
		self.pressed_max_count = max(self.pressed_max_count, len(self.pressed))
		if self.pressed_max_count >= 1 and self.pressed_max_count < 3:
			self.reset_flag = True
		if len(self.pressed) == 0:
			self.pressed_max_count = 0
		return False
