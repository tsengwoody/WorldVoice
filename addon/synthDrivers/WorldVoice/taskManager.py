import queue
import threading

import config
from logHandler import log
from synthDriverHandler import getSynth


class TaskManager:
	def __init__(self, lock, table):
		self.lock = lock
		self._table = table

		self.dispatchQueue = queue.Queue()
		self.listenQueue = {}
		self.speakingVoiceInstance = None

		self.reset_SAPI5()

		from . import WVConfigure
		WVConfigure.register(self.reset_SAPI5)

		self.dispatch_thread = None
		self.dispatch_start()

	def __del__(self):
		self.dispatch_end()

	@property
	def SAPI5(self):
		if isinstance(self._SAPI5, bool):
			return self._SAPI5
		self._SAPI5 = False
		voice = getSynth().voice if getSynth() else None
		if voice:
			row = list(filter(lambda row: row['name'] == voice, self._table))[0]
			if row['engine'] == "SAPI5":
				self._SAPI5 = True
				return self._SAPI5

		for key, value in config.conf["WorldVoice"]['speechRole'].items():
			if isinstance(value, config.AggregatedSection):
				try:
					row = list(filter(lambda row: row['name'] == value['voice'], self._table))[0]
				except BaseException:
					self._SAPI5 = True
					break
				if row['engine'] == "SAPI5":
					self._SAPI5 = True
					break

		return self._SAPI5

	def reset_SAPI5(self):
		self._SAPI5 = None
		log.debug("WorldVoice reset task SAPI5 to {}".format(self.SAPI5))

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
			if not self.SAPI5:
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
