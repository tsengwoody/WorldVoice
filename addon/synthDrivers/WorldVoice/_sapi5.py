from enum import IntEnum
import queue
import threading
import weakref

import comtypes.client
import config
from logHandler import log
from synthDriverHandler import synthIndexReached, synthDoneSpeaking
import nvwave

class Sapi5Error(RuntimeError):
	def __init__(self, code, msg):
		self.code = code
		super().__init__(msg)


class SapiSink(object):
	"""Handles SAPI event notifications.
	See https://msdn.microsoft.com/en-us/library/ms723587(v=vs.85).aspx
	"""

	def __init__(self):
		self.synthRef = synthRef

	def StartStream(self, streamNum, pos):
		synth = self.synthRef()
		if synth is None:
			log.debugWarning("Called StartStream method on SapiSink while driver is dead")
			return

	def Bookmark(self, streamNum, pos, bookmark, bookmarkId):
		synth = self.synthRef()
		if synth is None:
			log.debugWarning("Called Bookmark method on SapiSink while driver is dead")
			return
		synthIndexReached.notify(synth=synth, index=bookmarkId)

	def EndStream(self, streamNum, pos):
		synth = self.synthRef()
		if synth is None:
			log.debugWarning("Called Bookmark method on EndStream while driver is dead")
			return
		synthDoneSpeaking.notify(synth=synth)

		global voiceLock
		try:
			voiceLock.release()
		except RuntimeError:
			pass

		global sapi5Queue
		q = sapi5Queue
		try:
			q.task_done()
		except:
			pass


class SPAudioState(IntEnum):
	# https://docs.microsoft.com/en-us/previous-versions/windows/desktop/ms720596(v=vs.85)
	CLOSED = 0
	STOP = 1
	PAUSE = 2
	RUN = 3


class SpeechVoiceSpeakFlags(IntEnum):
	# https://docs.microsoft.com/en-us/previous-versions/windows/desktop/ms720892(v=vs.85)
	Async = 1
	PurgeBeforeSpeak = 2
	IsXML = 8


class SpeechVoiceEvents(IntEnum):
	# https://msdn.microsoft.com/en-us/previous-versions/windows/desktop/ms720886(v=vs.85)
	StartInputStream = 2
	EndInputStream = 4
	Bookmark = 16


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
				global voiceLock
				try:
					voiceLock.release()
				except RuntimeError:
					pass
				global sapi5Queue
				q = sapi5Queue
				try:
					q.task_done()
				except:
					pass
				# log.error("Error running function from queue", exc_info=True)


synthRef = None
sapi5Queue = None
sapi5Thread = None

def initialize(getSynth):
	global synthRef
	synthRef = getSynth

	global sapi5Thread, sapi5Queue
	sapi5Queue = queue.Queue()
	sapi5Thread = Sapi5Thread(
		sapi5Queue=sapi5Queue
	)


def terminate():
	global synthRef
	synthRef = None

	global sapi5Thread, sapi5Queue
	if sapi5Thread:
		sapi5Queue.put((None, None),)
		sapi5Thread.join()
	del sapi5Queue
	del sapi5Thread
	sapi5Thread, sapi5Queue = None, None

def open(name=None):
	tts = comtypes.client.CreateObject("SAPI.SPVoice")
	voices = tts.getVoices()
	if name is None:
		name = [v.getattribute('name') for v in voices][0]
	# Set Initial parameters
	for v in voices:
		if name == v.getattribute('name'):
			voice = v
			break
	else:
		raise Sapi5Error(500, "SAPI5 voice {} not found".format(name))

	tts.voice = voice
	outputDeviceID=nvwave.outputDeviceNameToID(config.conf["speech"]["outputDevice"], True)
	if outputDeviceID>=0:
		tts.audioOutput = tts.getAudioOutputs()[outputDeviceID]
	from comInterfaces.SpeechLib import ISpAudio
	try:
		ttsAudioStream = tts.audioOutputStream.QueryInterface(ISpAudio)
	except COMError:
		log.debugWarning("SAPI5 voice does not support ISPAudio") 
		ttsAudioStream=None

	return tts, ttsAudioStream

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

voiceLock = None
