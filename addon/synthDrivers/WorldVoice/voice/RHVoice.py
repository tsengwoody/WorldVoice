import globalVars
import languageHandler
from logHandler import log
import NVDAHelper
from synthDriverHandler import getSynth
import winreg
import winVersion

from .RH import RHManager
from . import Voice

import ctypes
import os

ocSpeech_Callback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)


class RHVoice(Voice):
	core = None

	def __init__(self, id, name, taskManager, language=None):
		self.engine = "RH"
		self.id = id
		self.taskManager = taskManager
		self.name = name
		self.language = language if language else "unknown"

		super().__init__()

	def active(self):
		if self.core.voice == self.id:
			return
		self.core.voice = self.id
		self.core.language = self.language
		self.core.pitch = self._pitch
		self.core.rate = self._rate
		self.core.volume = self._volume

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, name):
		self._name = name

	@property
	def rate(self):
		return self._rate

	@rate.setter
	def rate(self, percent):
		self._rate = percent
		self.core.rate = self._rate

	@property
	def pitch(self):
		return self._pitch

	@pitch.setter
	def pitch(self, percent):
		self._pitch = percent
		self.core.pitch = self._pitch

	@property
	def volume(self):
		return self._volume

	@volume.setter
	def volume(self, percent):
		self._volume = percent
		self.core.volume = self._volume

	@property
	def variants(self):
		self._variants = []
		return self._variants

	@property
	def variant(self):
		return self._variant

	@variant.setter
	def variant(self, value):
		self._variant = value

	@property
	def waitfactor(self):
		return self._waitfactor

	@waitfactor.setter
	def waitfactor(self, value):
		self._waitfactor = value

	def speak(self, text):
		def _speak():
			self.active()
			self.core.speak(text)
		self.taskManager.add_dispatch_task((self, _speak),)

	def stop(self):
		self.core.cancel()

	def pause(self):
		self.core.pause(True)

	def resume(self):
		self.core.pause(False)

	def close(self):
		pass

	@classmethod
	def ready(cls):
		return True

	@classmethod
	def engineOn(cls, lock=None):
		if not cls.core:
			cls.core = RHManager(lock)

	@classmethod
	def engineOff(cls):
		if cls.core:
			cls.core.terminate()
			cls.core = None

	@classmethod
	def voices(cls):
		if not cls.core:
			return []
		return cls.core.availableVoices
