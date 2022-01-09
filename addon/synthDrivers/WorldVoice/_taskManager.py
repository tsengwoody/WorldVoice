import queue
import threading

from logHandler import log


class TaskManager(threading.Thread):
	def __init__(self):
		from ._vocalizer import bgQueue as veQueue
		from ._sapi5 import sapi5Queue

		super().__init__()
		self.dispatchQueue = queue.Queue()
		self.veQueue = veQueue
		self.sapi5Queue = sapi5Queue
		self.speakingVoiceInstance = None
		self.setDaemon(True)
		self.start()

	def __del__(self):
		self.dispatchQueue.put((None, None),)
		self.join()

	def add(self, item):
				self.dispatchQueue.put(item)

	def clear(self):
		try:
			while True:
				self.dispatchQueue.get_nowait()
				self.dispatchQueue.task_done()
		except queue.Empty:
			pass

		if self.speakingVoiceInstance:
			self.speakingVoiceInstance.stop()

	def run(self):
		while True:
			voiceInstance, task = self.dispatchQueue.get()
			if not voiceInstance:
				break
			try:
				task()
			except Exception:
				log.error("Error running function from queue", exc_info=True)
			self.dispatchQueue.task_done()
			self.speakingVoiceInstance = voiceInstance
			self.veQueue.join()
			self.sapi5Queue.join()
			self.speakingVoiceInstance = None
