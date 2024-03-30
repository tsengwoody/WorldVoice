import comtypes.client
from comtypes import COMError
import languageHandler
import locale
from logHandler import log

from . import _sapi5
from . import Voice
from ._sapi5 import SPAudioState, SpeechVoiceSpeakFlags, SapiSink, SpeechVoiceEvents


class Sapi5Voice(Voice):
	def __init__(self, id, name, taskManager, language=None):
		self.engine = "SAPI5"
		self.id = id
		self.taskManager = taskManager
		self.tts, self.ttsAudioStream = _sapi5.open(name) if name != "default" else _sapi5.open()
		self.tts.EventInterests = SpeechVoiceEvents.Bookmark | SpeechVoiceEvents.StartInputStream | SpeechVoiceEvents.EndInputStream
		self._eventsConnection = comtypes.client.GetEvents(self.tts, SapiSink())
		self.name = self.tts.voice.getattribute('name')
		if not language:
			try:
				language = locale.windows_locale[int(self.tts.voice.getattribute('language').split(';')[0], 16)]
			except KeyError:
				language = None
		self.language = language

		super().__init__()

	@property
	def rate(self):
		self._rate = self.tts.Rate
		return (self._rate * 5) + 50

	@rate.setter
	def rate(self, percent):
		self._rate = (percent - 50) // 5
		self.tts.Rate = self._rate

	@property
	def pitch(self):
		return (self._pitch + 25) * 2

	@pitch.setter
	def pitch(self, percent):
		self._pitch = percent // 2 - 25

	@property
	def volume(self):
		self._volume = self.tts.Volume
		return self._volume

	@volume.setter
	def volume(self, percent):
		self._volume = percent
		self.tts.Volume = self._volume

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
			_sapi5.speakBlock(self, text)
		self.taskManager.add_dispatch_task((self, _speak),)

	def stop(self):
		try:
			# SAPI5's default means of stopping speech can sometimes lag at end of speech, especially with Win8 / Win 10 Microsoft Voices.
			# Therefore  instruct the underlying audio interface to stop first, before interupting and purging any remaining speech.
			if self.ttsAudioStream:
				self.ttsAudioStream.setState(SPAudioState.STOP, 0)
			self.tts.Speak(None, SpeechVoiceSpeakFlags.Async | SpeechVoiceSpeakFlags.PurgeBeforeSpeak)
		except COMError:
			log.warning("Could not interupting and purging any remaining speech and instruct the underlying audio interface to stop...")

	def pause(self):
		try:
			# SAPI5's default means of pausing in most cases is either extremely slow
			# (e.g. takes more than half a second) or does not work at all.
			# Therefore instruct the underlying audio interface to pause instead.
			if self.ttsAudioStream:
				self.ttsAudioStream.setState(SPAudioState.PAUSE, 0)
		except BaseException:
			pass

	def resume(self):
		try:
			# SAPI5's default means of pausing in most cases is either extremely slow
			# (e.g. takes more than half a second) or does not work at all.
			# Therefore instruct the underlying audio interface to pause instead.
			if self.ttsAudioStream:
				self.ttsAudioStream.setState(SPAudioState.RUN, 0)
		except BaseException:
			pass

	def close(self):
		self._eventsConnection = None
		self.tts = None
		self.ttsAudioStream = None

	@classmethod
	def install(cls):
		return True

	@classmethod
	def ready(cls):
		return True

	@classmethod
	def engineOn(cls, lock=None):
		try:
			_sapi5.initialize(lock)
		except BaseException:
			raise

	@classmethod
	def engineOff(cls):
		_sapi5.terminate()

	@classmethod
	def voices(cls):
		result = []
		if not cls.ready():
			return result

		tts = comtypes.client.CreateObject("SAPI.SPVoice")
		for voice in tts.getVoices():
			try:
				name = voice.getattribute('name')
				description = voice.GetDescription()
				try:
					language = locale.windows_locale[int(voice.getattribute('language').split(';')[0], 16)]
				except KeyError:
					language = "unknown"

				langDescription = languageHandler.getLanguageDescription(language)
				if not langDescription:
					try:
						langDescription = description.split("-")[1]
					except IndexError:
						langDescription = language

				result.append({
					"id": voice.Id,
					"name": name,
					"locale": language,
					"language": language,
					"langDescription": langDescription,
					"description": "%s - %s" % (name, langDescription),
					"engine": "SAPI5",
				})
			except COMError:
				log.warning("Could not get the voice info. Skipping...")

		return result
