from ctypes import *
import os
import contextlib
from collections import OrderedDict
import queue
import threading
from io import BytesIO

import addonHandler
import synthDriverHandler
import config
import globalVars
from logHandler import log
import nvwave
import winKernel
from ._languages import getLocaleNameFromTLW
# Import Vocalizer type definitions, constants and helpers.
from ._veTypes import *

import time

BIN_DICT_CONTENT_TYPE = "application/edct-bin-dictionary"
TEXT_RULESET_CONTENT_TYPE = "application/x-vocalizer-rettt+text"

_voiceDicts = {}

class BgThread(threading.Thread):

	def __init__(self, bgQueue):
		super().__init__()
		self._bgQueue = bgQueue
		self.setDaemon(True)
		self.start()

	def run(self):
		global speakingInstance, feedBuf
		while True:
			breakCommand = False
			instance, inText = self._bgQueue.get()
			if isinstance(inText, int):
				time.sleep(inText/1000)
				breakCommand = True
			if not instance:
				break
			if not breakCommand:
				try:
					speakingInstance = instance
					feedBuf = BytesIO()
					veDll.ve_ttsProcessText2Speech(instance, byref(inText))
					# We use the callback to stop speech but if this returns make sure isSpeaking is False
					# Sometimes the synth don't deliver all messages
					speakingInstance = None
				except Exception:
					log.error("Error running function from queue", exc_info=True)
			self._bgQueue.task_done()


@VE_CBOUTNOTIFY
def callback(instance, userData, message):
	""" Callback to handle assynchronous requests and messages from the synthecizer."""
	global speakingInstance, feedBuf
	try:
		outData = cast(message.contents.pParam, POINTER(VE_OUTDATA))
		messageType = message.contents.eMessage
		if speakingInstance is None and messageType != VE_MSG_ENDPROCESS:
			feedBuf = BytesIO()
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
			if outData.contents.cntPcmBufLen > 0:
				data = string_at(outData.contents.pOutPcmBuf, size=outData.contents.cntPcmBufLen)
				feedBuf.write(data)
				if feedBuf.tell() >= pcmBufLen:
					player.feed(feedBuf.getvalue())
					feedBuf = BytesIO()
			# And check for bookmarks
			for i in range(int(outData.contents.cntMrkListLen)):
				if outData.contents.pMrkList[i].eMrkType != VE_MRK_BOOKMARK:
					continue
				onIndexReached(outData.contents.pMrkList[i].ulMrkId)
		elif messageType == VE_MSG_PAUSE:
			# Synth was paused.
			player.pause(True)
		elif messageType == VE_MSG_RESUME:
			# Synth was resumed
			player.pause(False)
		elif messageType == VE_MSG_ENDPROCESS:
			# Speaking ended (because there is no more text or it was stopped)
			if speakingInstance is not None:
				player.feed(feedBuf.getvalue())
			feedBuf = BytesIO()
			player.idle()
			onIndexReached(None)
			speakingInstance = None
	except:
		log.error("Vocalizer callback", exc_info=True)
	return NUAN_OK

_basePath = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace")
if not os.path.isdir(os.path.join(_basePath, 'common')):
	_basePath = os.path.dirname(__file__)

_tuningDataDir = os.path.join(_basePath, "tuningData")
msvcrDll = None
veDll = None
platformDll = None
hSpeechClass = None
installResources = None
speakingInstance = None
onIndexReached = None
bgThread = None
pcmBufLen = 8192
pcmBuf = None
markBuf = None
markBufSize = 100
feedBuf = None
bgQueue = None
player = None

# Vocalizer voices
availableVoices = [addon.path for addon in addonHandler.getRunningAddons() if addon.name.startswith("vocalizer-expressive-voice")]
freedomScientificVoices = os.path.join(os.getenv("PROGRAMDATA", ""), "Freedom Scientific", "VocalizerExpressive", "2.2", "languages")
try:
	if os.listdir(freedomScientificVoices):
		availableVoices.append(freedomScientificVoices)
except IOError:
	pass

def preInitialize():
	global msvcrDll, veDll, platformDll, hSpeechClass, installResources
	# Load dlls
	dllPath = os.path.join(_basePath, "libs")
	msvcrDll = cdll.LoadLibrary(os.path.join(dllPath, "msvcr110.dll")) # required for ve.dll
	veDll = loadVeDll(os.path.join(dllPath, "ve.dll"))
	platformDll = loadPlatformDll(os.path.join(dllPath, "nuan_platform.dll"))
	# Provide external services to vocalizer
	installResources = VE_INSTALL()
	installResources.fmtVersion = VE_CURRENT_VERSION
	installResources.pBinBrokerInfo = None
	platformResources = VPLATFORM_RESOURCES()
	platformResources.fmtVersion = VPLATFORM_CURRENT_VERSION
	platformResources.licenseToken = None
	platformResources.u16NbrOfDataInstall = c_ushort(len(availableVoices) + 1)
	platformResources.apDataInstall = (c_wchar_p * (len(availableVoices) + 1))()
	platformResources.apDataInstall[0] = c_wchar_p(_basePath)
	for i, v in enumerate(availableVoices):
		platformResources.apDataInstall[i+1] = c_wchar_p(v)
	platformResources.pDatPtr_Table = None
	platformDll.vplatform_GetInterfaces(byref(installResources), byref(platformResources))

	# Initialize TTS class
	hSpeechClass = VE_HSAFE()
	veDll.ve_ttsInitialize(byref(installResources), byref(hSpeechClass))


def initialize(indexCallback=None):
	""" Initializes communication with vocalizer libraries. """
	global veDll, platformDll, hSpeechClass, installResources, bgThread, bgQueue
	global pcmBuf, pcmBufLen, feedBuf, markBufSize, markBuf, player, onIndexReached
	onIndexReached = indexCallback
	# load dlls and stuff:
	preInitialize()
	# Start background thread
	bgQueue = queue.Queue()
	bgThread = BgThread(bgQueue)

	# and allocate PCM and mark buffers
	pcmBuf = (c_byte * pcmBufLen)()
	feedBuf = BytesIO()
	markBuf = (VE_MARKINFO * markBufSize)()
	# Create a wave player
	#sampleRate = sampleRateConversions[getParameter(VE_PARAM_FREQUENCY)]
	sampleRate = 22050
	player = nvwave.WavePlayer(1, sampleRate, 16, outputDevice=config.conf["speech"]["outputDevice"])

def _onVoiceLoad(instance, voiceName):
	# Ruleset
	rulesetPath = os.path.join(_tuningDataDir, "%s.rules" % voiceName.lower())
	if os.path.exists(rulesetPath):
		with open(rulesetPath, "rb") as f:
			content = f.read()
		log.debug("Loading ruleset from %s", rulesetPath)
		try:
			resourceLoad(TEXT_RULESET_CONTENT_TYPE, content, instance)
		except VeError:
			log.warning("Error Loading vocalizer rules from %s", rulesetPath, exc_info=True)
	# Load custom dictionary if one exists
	if voiceName not in _voiceDicts:
		dictPath = os.path.join(_tuningDataDir, "%s.dcb" % voiceName.lower())
		if os.path.exists(dictPath):
			with open(dictPath, "rb") as f:
				_voiceDicts[voiceName] = f.read()
				log.debug("Loading vocalizer dictionary from %s", dictPath)
	if voiceName in _voiceDicts:
		try:
			resourceLoad(BIN_DICT_CONTENT_TYPE, _voiceDicts[voiceName], instance)
		except VeError:
			log.warning("Error loading Vocalizer dictionary.", exc_info=True)

def open(voice=None):
	""" Opens and returns a TTS instance."""
	global installResources
	# Open tts instance
	instance = VE_HSAFE()
	veDll.ve_ttsOpen(hSpeechClass, installResources.hHeap, installResources.hLog, byref(instance))

	if voice is None:
		# Initialize to some voice and language so the synth will not complain...
		language = getLanguageList()[0].szLanguage
		voice = getVoiceList(language)[0].szVoiceName
		voice = voice.decode('utf-8')
	# Set Initial parameters
	setParameters(instance,
	[(VE_PARAM_VOICE, voice),
	(VE_PARAM_MARKER_MODE, VE_MRK_ON),
	(VE_PARAM_INITMODE, VE_INITMODE_LOAD_ONCE_OPEN_ALL),
	(VE_PARAM_WAITFACTOR, 1),
	(VE_PARAM_TEXTMODE, VE_TEXTMODE_STANDARD),
	(VE_PARAM_TYPE_OF_CHAR, VE_TYPE_OF_CHAR_UTF16),
	(VE_PARAM_READMODE, VE_READMODE_SENT),
	(VE_PARAM_FREQUENCY, 22)])

	# Set callback
	outDevInfo = VE_OUTDEVINFO()
	outDevInfo.pfOutNotify  = callback
	veDll.ve_ttsSetOutDevice(instance, byref(outDevInfo))
	_onVoiceLoad(instance, voice)
	log.debug(u"Created synth instance for voice %s", voice)
	return (instance, voice)

def close(instance):
	""" Closes a tts instance."""
	veDll.ve_ttsClose(instance)

def terminate():
	""" Terminates communication with vocalizer, freeing resources."""
	global bgQueue, bgThread, player
	if bgThread:
		bgQueue.put((None, None),)
		bgThread.join()
	del bgQueue
	del bgThread
	bgThread, bgQueue = None, None
	player.close()
	player = None
	postTerminate()

# FIXME: this should be moved to NVDA's winKernel
def freeLibrary(handle):
	if winKernel.kernel32.FreeLibrary(handle) == 0:
		raise WindowsError()
	return True

def postTerminate():
	global hSpeechClass, msvcrDll, veDll, platformDll
	global pcmBuf, feedBuf, markBuf
	if hSpeechClass is not None:
		try:
			veDll.ve_ttsUnInitialize(hSpeechClass)
		except VeError:
			pass # Wrong state or something, not too much deal.
		hSpeechClass = None
	pcmBuf = None
	feedBuf = None
	markBuf = None
	platformDll.vplatform_ReleaseInterfaces(byref(installResources))
	try:
		freeLibrary(veDll._handle)
		freeLibrary(platformDll._handle)
		freeLibrary(msvcrDll._handle)
	except WindowsError:
		log.exception("Can not unload dll.")
	finally:
		del veDll
		del platformDll
		del msvcrDll

def processText2Speech(instance, text):
	""" Sends text to be spoken."""
	inText = VE_INTEXT()
	inText.eTextFormat = 0 # this is the only supported format...
	# Text length in bytes (utf16 has 2).
	inText.cntTextLength = c_size_t(len(text) * 2)
	inText.szInText = cast(c_wchar_p(text), c_void_p)
	bgQueue.put((instance, inText),)

def processBreak(instance, breakTime):
	bgQueue.put((instance, breakTime),)

def stop():
	""" Stops speaking of some text. """
	global speakingInstance
	try:
		while True:
			bgQueue.get_nowait()
			bgQueue.task_done()
	except queue.Empty:
		pass

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
			bgQueue.join()

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
	return params[0].uValue.usValue if type_ == int else params[0].uValue.szStringValue.decode("utf-8")

def setParameters(instance, idAndValues):
	""" Sets the values for many parameters in one call. """
	size = len(idAndValues)
	params = (VE_PARAM * size)()
	for i, pair in enumerate(idAndValues):
		params[i].ID = pair[0]
		if isinstance(pair[1], int):
			params[i].uValue.usValue = c_ushort(pair[1])
		else:
			params[i].uValue.szStringValue = pair[1].encode("utf-8")
	try:
		veDll.ve_ttsSetParamList(instance, params, c_ushort(size))
	except VeError:
		log.debugWarning("Error setting parameters")

def setParameter(instance, param, value):
	""" Sets a parameter value. """
	setParameters(instance, [(param,value)])

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
	languageName = languageName.encode("utf-8")
	voiceName = voiceName.encode("utf-8")
	""" Gets the available speech databases for voice and language (voice models). """
	nItems = c_ushort()
	# Double Call.
	veDll.ve_ttsGetSpeechDBList(hSpeechClass, c_char_p(languageName), c_char_p(voiceName), None, byref(nItems))
	speechDBInfos = (VE_SPEECHDBINFO * nItems.value)()
	veDll.ve_ttsGetSpeechDBList(hSpeechClass, c_char_p(languageName), c_char_p(voiceName), byref(speechDBInfos), byref(nItems))
	voiceModels = []
	for i in range(nItems.value):
		voiceModels.append(speechDBInfos[i].szVoiceOperatingPoint.decode("utf-8"))
	return voiceModels

def resourceLoad(contentType, content, instance):
	length = len(content)
	log.debug("Loading resource with %d bytes.", length)
	hout = VE_HSAFE()
	veDll.ve_ttsResourceLoad(instance, contentType, length, content, byref(hout))
	return hout

def getAvailableResources():
	resources = OrderedDict()
	for l in getLanguageList():
		languageInfo = synthDriverHandler.LanguageInfo(getLocaleNameFromTLW(l.szLanguageTLW.decode("utf-8")))

		if not languageInfo.displayName:
			languageInfo.displayName = l.szLanguage
		resources[languageInfo] = []

		for v in getVoiceList(l.szLanguage):
			name = "%s - %s" % (v.szVoiceName.decode("utf-8"), languageInfo.displayName)
			voiceInfo = synthDriverHandler.VoiceInfo(v.szVoiceName.decode("utf-8"), name, languageInfo.id or None)
			resources[languageInfo].append(voiceInfo)

	return resources

@contextlib.contextmanager
def preOpenVocalizer():
	try:
		if hSpeechClass is None:
			preInitialize()
		status = True
	except VeError:
		log.debugWarning("Vocalizer not available.", exc_info=True)
		status = False

	try:
		yield status
	finally:
		if player is None:
			postTerminate()
