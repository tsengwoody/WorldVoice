from enum import IntEnum

import comtypes.client
from comtypes import COMError
import config
from logHandler import log
from synthDriverHandler import getSynth
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

	def StartStream(self, streamNum, pos):
		synth = getSynth()
		if synth is None:
			log.debugWarning("Called StartStream method on SapiSink while driver is dead")
			return

	def Bookmark(self, streamNum, pos, bookmark, bookmarkId):
		synth = getSynth()
		if synth is None:
			log.debugWarning("Called Bookmark method on SapiSink while driver is dead")
			return
		synthIndexReached.notify(synth=synth, index=bookmarkId)

	def EndStream(self, streamNum, pos):
		synth = getSynth()
		if synth is None:
			log.debugWarning("Called Bookmark method on EndStream while driver is dead")
			return
		synthDoneSpeaking.notify(synth=synth)

		global voiceLock
		if voiceLock:
			try:
				voiceLock.release()
			except RuntimeError:
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

voiceLock = None

def initialize(lock):
	global voiceLock
	voiceLock = lock


def terminate():
	global voiceLock
	voiceLock = None


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
	outputDeviceID = nvwave.outputDeviceNameToID(config.conf["speech"]["outputDevice"], True)
	if outputDeviceID >= 0:
		tts.audioOutput = tts.getAudioOutputs()[outputDeviceID]
	from comInterfaces.SpeechLib import ISpAudio
	try:
		ttsAudioStream = tts.audioOutputStream.QueryInterface(ISpAudio)
	except COMError:
		log.debugWarning("SAPI5 voice does not support ISPAudio")
		ttsAudioStream = None

	return tts, ttsAudioStream


def speakBlock(instance, arg):
	voiceInstance = instance
	text = arg
	if not voiceInstance:
		return
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


def pause():
	global speakingInstance
	if speakingInstance is not None:
		instance = speakingInstance
		instance.pause()


def resume():
	global speakingInstance
	if speakingInstance is not None:
		instance = speakingInstance
		instance.resume()

