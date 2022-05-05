import queue
import threading

import config
from logHandler import log
try:
	from synthDriverHandler import getSynth
except BaseException:
	from speech import getSynth


class TaskManager:
	def __init__(self, lock, table):
		self.lock = lock
		self._table = table

		self.dispatchQueue = queue.Queue()
		self.listenQueue = {}
		self.speakingVoiceInstance = None

		self.reset_block()
		from synthDrivers.WorldVoice import WVConfigure
		WVConfigure.register(self.reset_block)

		self.dispatch_thread = None
		self.dispatch_start()

	def __del__(self):
		self.dispatch_end()

	@property
	def block(self):
		if isinstance(self._block, bool):
			return self._block
		self._block = False
		voice = getSynth().voice if getSynth() else None
		if not voice:
			engine = None
		else:
			row = list(filter(lambda row: row['name'] == voice, self._table))[0]
			engine = row['engine']

		for key, value in config.conf["WorldVoice"]['autoLanguageSwitching'].items():
			if isinstance(value, config.AggregatedSection):
				try:
					row = list(filter(lambda row: row['name'] == value['voice'], self._table))[0]
				except BaseException:
					self._block = True
					break
				if engine is None:
					engine = row['engine']
				if not engine == row['engine'] or row['engine'] == 'SAPI5':
					self._block = True
					break

		return self._block

	@block.setter
	def block(self, value):
		if value is not None:
			raise ValueError("block setter only accept None")
		self._block = value

	def reset_block(self):
		self._block = None
		log.debug("WorldVoice reset task block to {}".format(self.block))

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
		except BaseException:
			pass
		try:
			while True:
				self.dispatchQueue.task_done()
		except BaseException:
			pass

		for q in self.listenQueue.values():
			try:
				while True:
					q.get_nowait()
			except BaseException:
				pass
			"""try:
				while True:
					q.task_done()
			except BaseException:
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
		except BaseException:
			pass

		for q in self.listenQueue.values():
			try:
				while True:
					q.get_nowait()
					q.task_done()
			except BaseException:
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

			if self._block:
				self.speakingVoiceInstance = voiceInstance
				self.lock.acquire()
			try:
				task()
			except Exception:
				log.error("Error running function from queue", exc_info=True)
			self.dispatchQueue.task_done()

			if self._block:
				self.lock.acquire()
				self.lock.release()
				self.speakingVoiceInstance = None
