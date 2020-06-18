#vocalizer/_vocalizer.py
#A part of the vocalizer driver for NVDA (Non Visual Desktop Access)
#Copyright (C) 2012, 2013 Rui Batista <ruiandrebatista@gmail.com>
#Copyright (C) 2012, 2013 Tiflotecnia, lda. <www.tiflotecnia.com>
#This file is covered by the GNU General Public License.
#See the file GPL.txt for more details.

import base64
from ctypes import *
import os.path
import queue
import threading
import addonHandler
import config
import globalVars
from logHandler import log
import nvwave
import winKernel
from .storage import getLicenseData
# Import Vocalizer type definitions, constants and helpers.
from ._veTypes import *

from . import _tuningData

# Python functions and callbacks
class BgThread(threading.Thread):
	""" Background thread to process assynchronous requeusts."""
	def __init__(self):
		threading.Thread.__init__(self)
		self.setDaemon(True)

	def run(self):
		global isSpeaking
		while True:
			func, args, kwargs = bgQueue.get()
			if not func:
				break
			try:
				func(*args, **kwargs)
			except:
				log.error("Error running function from queue", exc_info=True)
			bgQueue.task_done()

def _execWhenDone(func, *args, **kwargs):
	""" Make the passed function and arguments run assynchronous or when no assynchrnous task  is running. """
	global bgQueue
	# This can't be a kwarg in the function definition because it will consume the first non-keywor dargument which is meant for func.
	mustBeAsync = kwargs.pop("mustBeAsync", False)
	if mustBeAsync or bgQueue.unfinished_tasks != 0:
		# Either this operation must be asynchronous or There is still an operation in progress.
		# Therefore, run this asynchronously in the background thread.
		bgQueue.put((func, args, kwargs))
	else:
		func(*args, **kwargs)

#: Keeps count of the number of bytes pushed for the current utterance.
_numBytesPushed = 0

@VE_CBOUTNOTIFY
def callback(instance, userData, message):
	""" Callback to handle assynchronous requests and messages from the synthecizer."""
	global speakingInstance, _numBytesPushed
	try:
		outData = cast(message.contents.pParam, POINTER(VE_OUTDATA))
		messageType = message.contents.eMessage
		if speakingInstance is None and messageType != VE_MSG_ENDPROCESS:
			feedBuf.truncate(0)
			return NUAN_E_TTS_USERSTOP
		elif messageType == VE_MSG_OUTBUFREQ:
			# Request for storage to put sound and mark data.
			# Here we fill the pointers to our already allocated buffers (on initialize).
			outData.contents.pOutPcmBuf = cast(pcmBuf, c_void_p)
			outData.contents.cntPcmBufLen = c_uint(pcmBufLen)
			outData.contents.pMrkList = cast(markBuf, POINTER(VE_MARKINFO))
			outData.contents.cntMrkListLen = c_uint(markBufSize * sizeof(VE_MARKINFO))
			return NUAN_OK
		if messageType == VE_MSG_OUTBUFDONE:
			# Sound data and mark buffers were produced by vocalizer.
			# Send wave data to be played:
			data = string_at(outData.contents.pOutPcmBuf, size=outData.contents.cntPcmBufLen)
			prevByte = 0
			for i in range(int(outData.contents.cntMrkListLen)):
				mark = outData.contents.pMrkList[i]
				if mark.eMrkType != VE_MRK_BOOKMARK:
					continue
				index = mark.ulMrkId
				sampleStart = mark.cntDestPos
				BYTES_PER_SAMPLE = 2
				indexByte = (sampleStart * BYTES_PER_SAMPLE)
				# Subtract bytes in the utterance that have already been handled
				# to give us the byte offset into the samples for this callback.
				indexByte -= _numBytesPushed
				player.feed(
					data[prevByte:indexByte],
					onDone=lambda index=index: onIndexReached(index)
				)
				prevByte = indexByte
			player.feed(data[prevByte:])
			_numBytesPushed += len(data)
		elif messageType == VE_MSG_PAUSE:
			# Synth was paused.
			player.pause(True)
		elif messageType == VE_MSG_RESUME:
			# Synth was resumed
			player.pause(False)
		elif messageType == VE_MSG_ENDPROCESS:
			# Speaking ended (because there is no more text or it was stopped)
			player.idle()
			onIndexReached(None)
			speakingInstance = None
	except:
		log.error("Vocalizer callback", exc_info=True)
	return NUAN_OK



_basePath = os.path.abspath(os.path.dirname(__file__))
veDll = None
platformDll = None
hSpeechClass = None
installResources = None
speakingInstance = None
onIndexReached = None
bgThread = None
pcmBufLen = 0x2000  # 8kb
pcmBuf = None
markBuf = None
markBufSize = 100
bgQueue = None
Player = None
syncEvent = threading.Event()

def preInitialize():
	global veDll, platformDll, hSpeechClass, installResources
	# Load dlls
	dllPath = os.path.join(_basePath, r"common\speech\components")
	veDll = loadVeDll(os.path.join(dllPath, "ve.dll"))
	platformDll = loadPlatformDll(os.path.join(_basePath, r"common\speech\components\nuan_platform.dll"))
	# Provide external services to vocalizer
	# Check addons for installed voices
	voiceAddons = [addon for addon in addonHandler.getRunningAddons() if addon.name.startswith("vocalizer-expressive-voice")]
	installResources = VE_INSTALL()
	installResources.fmtVersion = VE_CURRENT_VERSION
	installResources.pBinBrokerInfo = None
	platformResources = VPLATFORM_RESOURCES()
	platformResources.fmtVersion = VPLATFORM_CURRENT_VERSION
	license = getLicenseData()
	if license:
		token = base64.b64decode(license['data'])
		sessionKey = base64.b64decode(license['sessionKey'])
		platformResources.licenseToken = token
		platformResources.licenseTokenLen = len(token)
		platformResources.licensor = license['licensor']
		platformResources.sessionKey = sessionKey
		platformResources.sessionKeyLen = len(sessionKey)
	else:
		platformResources.licenseToken = None
	platformResources.u16NbrOfDataInstall = c_ushort(len(voiceAddons) + 1)
	platformResources.apDataInstall = (c_wchar_p * (len(voiceAddons) + 1))()
	platformResources.apDataInstall[0] = c_wchar_p(_basePath)
	for i, addon in enumerate(voiceAddons):
		platformResources.apDataInstall[i+1] = c_wchar_p(addon.path)
	platformResources.pDatPtr_Table = None
	platformDll.vplatform_GetInterfaces(byref(installResources), byref(platformResources))

	# Initialize TTS class
	hSpeechClass = VE_HSAFE()
	veDll.ve_ttsInitialize(byref(installResources), byref(hSpeechClass))


def initialize(indexCallback=None):
	""" Initializes communication with vocalizer libraries.

	@param indexCallback: A function which is called when the synth reaches an index.
		It is called with one argument:
		the number of the index or C{None} when speech stops.
	"""
	global veDll, platformDll, hSpeechClass, installResources, bgThread, bgQueue
	global pcmBuf, pcmBufLen, markBufSize, markBuf, player
	global onIndexReached
	# load dlls and stuff:
	preInitialize()
	onIndexReached = indexCallback
	# Start background thread
	bgThread = BgThread()
	bgQueue = queue.Queue()
	bgThread.start()

	# and allocate PCM and mark buffers
	pcmBuf = (c_byte * pcmBufLen)()
	markBuf = (VE_MARKINFO * markBufSize)()
	# Create a wave player
	#sampleRate = sampleRateConversions[getParameter(VE_PARAM_FREQUENCY)]
	sampleRate = 22050
	player = nvwave.WavePlayer(
		channels=1,
		samplesPerSec=sampleRate,
		bitsPerSample=16,
		outputDevice=config.conf["speech"]["outputDevice"],
	)



def open(voice=None):
	""" Opens and returns a TTS instance."""
	global installResources
	# Open tts instance
	instance = VE_HSAFE()
	veDll.ve_ttsOpen(hSpeechClass, installResources.hHeap, installResources.hLog, byref(instance))

	if voice is None:
		# Initialize to some voice and language so the synth will not complain...
		language = getLanguageList()[0].szLanguage.decode()
		voice = getVoiceList(language)[0].szVoiceName.decode()
	# Set Initial parameters
	setParameters(instance,
	[(VE_PARAM_VOICE, voice),
	(VE_PARAM_MARKER_MODE, VE_MRK_ON),
	(VE_PARAM_INITMODE, VE_INITMODE_LOAD_ONCE_OPEN_ALL),
	(VE_PARAM_WAITFACTOR, 1),
	(VE_PARAM_TEXTMODE, VE_TEXTMODE_STANDARD),
	(VE_PARAM_TYPE_OF_CHAR, VE_TYPE_OF_CHAR_UTF8)])

	# Set callback
	outDevInfo = VE_OUTDEVINFO()
	outDevInfo.pfOutNotify  = callback
	veDll.ve_ttsSetOutDevice(instance, byref(outDevInfo))
	_tuningData.onVoiceLoad(instance, voice)
	log.debug(f"Created synth instance for voice {voice}")
	return (instance, voice)

def close(instance):
	""" Closes a tts instance."""
	_execWhenDone(veDll.ve_ttsClose, instance)

def terminate():
	""" Terminates communication with vocalizer, freeing resources."""
	global bgQueue, bgThread, player, onIndexReached
	if bgThread:
		bgQueue.put((None, None, None),)
		bgThread.join()
	del bgQueue
	del bgThread
	bgThread, bgQueue = None, None
	player.close()
	player = None
	onIndexReached = None
	postTerminate()

# FIXME: this should be moved to NVDA's winKernel
def freeLibrary(handle):
	if winKernel.kernel32.FreeLibrary(handle) == 0:
		raise WindowsError()
	return True

def postTerminate():
	global hSpeechClass, veDll, platformDll
	global pcmBuf, markBuf
	if hSpeechClass is not None:
		try:
			veDll.ve_ttsUnInitialize(hSpeechClass)
		except VeError:
			pass # Wrong state or something, not too much deal.
		hSpeechClass = None
	pcmBuf = None
	markBuf = None
	platformDll.vplatform_ReleaseInterfaces(byref(installResources))
	try:
		freeLibrary(veDll._handle)
		freeLibrary(platformDll._handle)
	except WindowsError as e:
		log.exception("Can not unload dll.")
	finally:
		del veDll
		del platformDll

def processText2Speech(instance, text):
	""" Sends text to be spoken."""
	# encode text to UTF-8
	text = text.encode("utf-8", errors="surrogatepass")
	inText = VE_INTEXT()
	inText.eTextFormat = VE_NORM_TEXT # this is the only supported format...
	inText.cntTextLength = c_uint(len(text))
	inText.szInText = cast(c_char_p(text), c_void_p)
	_execWhenDone(_processText2Speech, instance, inText, mustBeAsync=True)

def _processText2Speech(instance, inText):
	global speakingInstance, _numBytesPushed
	speakingInstance = instance
	_numBytesPushed = 0
	veDll.ve_ttsProcessText2Speech(instance, byref(inText))
	# We use the callback to stop speech but if this returns make sure isSpeaking is False
	# Sometimes the synth don't deliver all messages
	speakingInstance = None

def stop():
	""" Stops speaking of some text. """
	global speakingInstance
	# Kill all speech from now.
	# Although we just stop an instance, others must also not speak.
	# We still want parameter changes to occur, so requeue them.
	params = []
	try:
		while True:
			item = bgQueue.get_nowait()
			if item[0] != _processText2Speech:
				params.append(item)
			bgQueue.task_done()
	except queue.Empty:
		# Let the exception break us out of this loop, as queue.empty() is not reliable anyway.
		pass
	for item in params:
		bgQueue.put(item)
	# Stop audio as soon as possible:
	if speakingInstance is not None:
		instance = speakingInstance
		try:
			veDll.ve_ttsStop(instance)
		except VeError as e:
			# Sometimes we may stop the synth when it is already stoped due to lake of proper synchronization.
			# As this is a rare case we just catch the expception for wrong state
			# that is returned by vocalizer.
			# This avoids  the overhead of synchronization but should be further investigated.
			if e.code == NUAN_E_WRONG_STATE:
				log.debug("Wrong state when stopping vocalizer")
			else:
				raise
		finally:
			player.stop()


def pause():
	""" Pauses Speaking. """
	global speakingInstance
	if speakingInstance  is not None:
		try:
			veDll.ve_ttsPause(speakingInstance)
		except VeError as e:
			if e.code != NUAN_E_WRONG_STATE:
				# Ignore because synth is probably stopping.
				raise

def resume():
	""" Resumes Speaking. """
	global speakingInstance
	if speakingInstance is not None:
		veDll.ve_ttsResume(speakingInstance)

def getParameter(instance, paramId, type_=int):
	""" Gets a parameter value. """
	params = (VE_PARAM * 1)()
	params[0].ID = paramId
	veDll.ve_ttsGetParamList(instance, params, c_ushort(1))
	return params[0].uValue.usValue if type_ == int else params[0].uValue.szStringValue.decode()

def setParameters(instance, idAndValues):
	""" Sets the values for many parameters in one call. """
	_execWhenDone(_setParameters, instance, idAndValues)

def _setParameters(instance, idAndValues):
	size = len(idAndValues)
	params = (VE_PARAM * size)()
	for i, pair in enumerate(idAndValues):
		params[i].ID = pair[0]
		if isinstance(pair[1], str):
			params[i].uValue.szStringValue = pair[1].encode()
		else:
			params[i].uValue.usValue = c_ushort(pair[1])
	veDll.ve_ttsSetParamList(instance, params, c_ushort(size))

def setParameter(instance, param, value):
	""" Sets a parameter value. """
	setParameters(instance, [(param,value)])

def sync():
	syncEvent.clear()
	_execWhenDone(lambda : syncEvent.set())
	syncEvent.wait()

def _newCopy(src):
	"""Returns a new ctypes object which is a bitwise copy of an existing one"""
	dst = type(src)()
	pointer(dst)[0] = src
	return dst


def getLanguageList():
	""" Gets the list of available languages. """
	nItems = c_ushort()
	# Double call. First get number of items.
	veDll.ve_ttsGetLanguageList(hSpeechClass, None, byref(nItems))
	# Alocate array for language structures
	langs = (VE_LANGUAGE * nItems.value)()
	# Now the real call:
	veDll.ve_ttsGetLanguageList(hSpeechClass, langs, byref(nItems))
	languages = []
	for i in range(nItems.value):
		languages.append(_newCopy(langs[i]))
	return languages

def getVoiceList(languageName):
	""" Lists the available voices for language. """
	languageName = languageName.encode()
	nItems = c_ushort()
	# Double call.
	veDll.ve_ttsGetVoiceList(hSpeechClass, c_char_p(languageName), None, byref(nItems))
	voiceInfos = (VE_VOICEINFO * nItems.value)()
	veDll.ve_ttsGetVoiceList(hSpeechClass, c_char_p(languageName), byref(voiceInfos), byref(nItems))
	l = []
	for i in range(nItems.value):
		l.append(_newCopy(voiceInfos[i]))
	return l

def getSpeechDBList(languageName, voiceName):
	""" Gets the available speech databases for voice and language (voice models). """
	languageName = languageName.encode()
	voiceName = voiceName.encode()
	nItems = c_ushort()
	# Double Call.
	veDll.ve_ttsGetSpeechDBList(hSpeechClass, c_char_p(languageName), c_char_p(voiceName), None, byref(nItems))
	speechDBInfos = (VE_SPEECHDBINFO * nItems.value)()
	veDll.ve_ttsGetSpeechDBList(hSpeechClass, c_char_p(languageName), c_char_p(voiceName), byref(speechDBInfos), byref(nItems))
	voiceModels = []
	for i in range(nItems.value):
		voiceModels.append(speechDBInfos[i].szVoiceOperatingPoint)
	return voiceModels

def resourceLoad(contentType, content, instance):
	length = len(content)
	log.debug("Loading resource with %d bytes.", length)
	hout = VE_HSAFE()
	veDll.ve_ttsResourceLoad(instance, contentType, length, content, byref(hout))
	return hout

def getLicenseInfo():
	info = ValidationInfo()
	platformDll.VAUTONVDA_getLicenseInfo(byref(info))
	return info
