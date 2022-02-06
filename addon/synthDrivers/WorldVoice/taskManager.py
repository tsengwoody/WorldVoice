import queue
import threading

from logHandler import log


class TaskManager:
	def __init__(self, lock):
		super().__init__()
		self.dispatchQueue = queue.Queue()
		self.listenQueue = {}
		self.speakingVoiceInstance = None
		self.lock = lock

		self.dispatch_thread = None
		self.dispatch_start()

	def __del__(self):
		self.dispatch_end()

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
