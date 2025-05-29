import queue
import threading

from logHandler import log


class TaskManager:
	def __init__(self, lock):
		self.lock = lock

		self.speakingVoiceInstance = None
		self.dispatchQueue = queue.Queue()
		self.dispatch_thread = None

		self.dispatch_start()

	def __del__(self):
		self.dispatch_end()

	def add_dispatch_task(self, item):
		self.dispatchQueue.put(item)

	def reset(self):
		try:
			while True:
				self.dispatchQueue.get_nowait()
		except BaseException:
			pass
		try:
			while True:
				self.dispatchQueue.task_done()
		except BaseException:
			pass

		try:
			self.lock.release()
		except RuntimeError:
			pass

	def clear(self):
		try:
			while True:
				self.dispatchQueue.get_nowait()
				self.dispatchQueue.task_done()
		except BaseException:
			pass

	def cancel(self):
		self.clear()
		try:
			self.lock.release()
		except BaseException:
			pass
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

			self.lock.acquire()
			self.speakingVoiceInstance = voiceInstance

			try:
				task()
			except Exception:
				log.error("Error running function from queue", exc_info=True)

			with self.lock:
				self.speakingVoiceInstance = None

			try:
				self.dispatchQueue.task_done()
			except BaseException:
				pass
