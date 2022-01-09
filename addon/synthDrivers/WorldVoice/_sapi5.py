from enum import IntEnum
import queue
import threading
import weakref

import comtypes.client
import config
from logHandler import log
import nvwave

class Sapi5Error(RuntimeError):
	def __init__(self, code, msg):
		self.code = code
		super().__init__(msg)


class SapiSink(object):
	"""Handles SAPI event notifications.
	See https://msdn.microsoft.com/en-us/library/ms723587(v=vs.85).aspx
	"""

	def Bookmark(self, streamNum, pos, bookmark, bookmarkId):
		pass

	def EndStream(self, streamNum, pos):
		sapi5Queue.task_done()


class SpeechVoiceEvents(IntEnum):
	# https://msdn.microsoft.com/en-us/previous-versions/windows/desktop/ms720886(v=vs.85)
	EndInputStream = 4
	Bookmark = 16


class SpeechVoiceSpeakFlags(IntEnum):
	# https://docs.microsoft.com/en-us/previous-versions/windows/desktop/ms720892(v=vs.85)
	Async = 1
	PurgeBeforeSpeak = 2
	IsXML = 8


class Sapi5Thread(threading.Thread):
	def __init__(self, sapi5Queue):
		super().__init__()
		self.sapi5Queue = sapi5Queue
		self.setDaemon(True)
		self.start()

	def run(self):
		while True:
			voiceInstance, text = self.sapi5Queue.get()
			if not voiceInstance:
				break
			try:
				# flags = SpeechVoiceSpeakFlags.IsXML
				flags = SpeechVoiceSpeakFlags.IsXML | SpeechVoiceSpeakFlags.Async
				voiceInstance.tts.Speak(text, flags)
			except Exception:
				log.error("Error running function from queue", exc_info=True)
			# self.sapi5Queue.task_done()


sapi5Queue = None
sapi5Thread = None

def initialize():
	global sapi5Thread, sapi5Queue
	sapi5Queue = queue.Queue()
	sapi5Thread = Sapi5Thread(
		sapi5Queue=sapi5Queue
	)

def open(name=None):
	tts = comtypes.client.CreateObject("SAPI.SPVoice")
	voices = tts.getVoices()
	if name is None:
		voice = [v.getattribute('name') for v in voices][0]
	# Set Initial parameters
	for v in voices:
		if name == v.getattribute('name'):
			voice = v
			break
	else:
		raise Sapi5Error("SAPI5 voice not found by name")

	tts.voice = voice
	_eventsConnection = comtypes.client.GetEvents(tts, SapiSink())
	outputDeviceID=nvwave.outputDeviceNameToID(config.conf["speech"]["outputDevice"], True)
	if outputDeviceID>=0:
		tts.audioOutput = tts.getAudioOutputs()[outputDeviceID]
	tts.EventInterests = SpeechVoiceEvents.Bookmark | SpeechVoiceEvents.EndInputStream
	from comInterfaces.SpeechLib import ISpAudio
	try:
		ttsAudioStream = tts.audioOutputStream.QueryInterface(ISpAudio)
	except COMError:
		log.debugWarning("SAPI5 voice does not support ISPAudio") 
		ttsAudioStream=None

	return tts, ttsAudioStream, _eventsConnection

def terminate():
	global sapi5Thread, sapi5Queue
	if sapi5Thread:
		sapi5Queue.put((None, None),)
		sapi5Thread.join()
	del sapi5Queue
	del sapi5Thread
	sapi5Thread, sapi5Queue = None, None


def processText2Speech(instance, text):
	sapi5Queue.put((instance, text),)

def stop():
	try:
		while True:
			sapi5Queue.get_nowait()
			sapi5Queue.task_done()
	except queue.Empty:
		pass


def pause():
	global speakingInstance
	if speakingInstance  is not None:
		instance = speakingInstance
		instance.pause()

def resume():
	global speakingInstance
	if speakingInstance  is not None:
		instance = speakingInstance
		instance.resume()
