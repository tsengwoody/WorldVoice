import ctypes
import queue
import threading

from logHandler import log

from . import keyboard_hook

class TaskManager:
	def __init__(self, lock):
		super().__init__()
		self.dispatchQueue = queue.Queue()
		self.listenQueue = {}
		self.speakingVoiceInstance = None
		self.lock = lock

		self.pressed = set()
		self.pressed_max_count = 0
		self.reset_flag = False

		self.dispatch_thread = None
		self.dispatch_start()

		self.hook_thread = None
		self.hook_start()

	def __del__(self):
		self.dispatch_end()
		self.hook_end()

	def add_listen_queue(self, key, queue):
		self.listenQueue[key] = queue

	def remove_listen_queue(self, key):
		del self.listenQueue[key]

	def add_dispatch_task(self, item):
		self.dispatchQueue.put(item)

	def reset(self):
		try:
			while True:
				self.dispatchQueue.get_nowait()
		except:
			pass
		try:
			while True:
				self.dispatchQueue.task_done()
		except:
			pass

		for q in self.listenQueue.values():
			try:
				while True:
					q.get_nowait()
			except:
				pass
			"""try:
				while True:
					q.task_done()
			except:
				pass"""

		try:
			self.lock.release()
		except RuntimeError:
			pass

	def clear(self):
		try:
			while True:
				self.dispatchQueue.get_nowait()
				self.dispatchQueue.task_done()
		except:
			pass

		for q in self.listenQueue.values():
			try:
				while True:
					q.get_nowait()
					q.task_done()
			except:
				pass

	def cancel(self):
		self.clear()
		if self.speakingVoiceInstance:
			self.speakingVoiceInstance.stop()

	def dispatch_start(self):
		self.dispatch_thread = threading.Thread(target=self.dispatch)
		self.dispatch_thread.daemon = True
		self.dispatch_thread.start()

	def dispatch_end(self):
		if self.dispatch_thread is not None:
			self.dispatchQueue.put((None, None),)
			self.dispatch_thread.join()
			self.dispatch_thread = None

	def dispatch(self):
		while True:
			voiceInstance, task = self.dispatchQueue.get()
			if not voiceInstance:
				break

			self.speakingVoiceInstance = voiceInstance
			self.lock.acquire()
			try:
				task()
			except Exception:
				log.error("Error running function from queue", exc_info=True)
			self.dispatchQueue.task_done()

			self.lock.acquire()
			self.lock.release()
			# for q in self.listenQueue.values():
				# q.join()
			self.speakingVoiceInstance = None

	def hook_start(self):
		self.hook_thread = threading.Thread(target=self.hook)
		self.hook_thread.daemon = True
		self.hook_thread.start()

	def hook_end(self):
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
		if kwargs['pressed']:
			if self.reset_flag:
				self.reset_flag = False
				self.reset()
				self.cancel()
			self.pressed.add(kwargs['vk_code'])
		elif not kwargs['pressed']:
			try:
				self.pressed.remove(kwargs['vk_code'])
			except KeyError:
				pass
		self.pressed_max_count = max(self.pressed_max_count, len(self.pressed))
		if len(self.pressed) == 0:
			if self.pressed_max_count >= 1 and self.pressed_max_count < 3:
				self.reset_flag = True
			self.pressed_max_count = 0
		return False #Don't pass it on
