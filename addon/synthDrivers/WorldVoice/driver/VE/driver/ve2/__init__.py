import os.path
import contextlib
from ctypes import *

# Import Vocalizer type definitions, constants and helpers.
from .veTypes import *
from .languages import getLocaleNameFromTLW

# global variables
msvcrDll = None
veDll = None
platformDll = None
hSpeechClass = None
installResources = None

def veCheckForError(result, func, args):
	""" Checks for errors in a function from the vocalizer dlls and platform.
	
	If the error code is not positive it throws a runtime error.
	The error codes have no description, see the vocalizer SDK
	For reference."""
	if result not in (NUAN_OK, NUAN_E_TTS_USERSTOP):
		raise VeError(result, "Vocalizer Error: %s: %x" % (func.__name__, result))

def _newCopy(src):
	"""Returns a new ctypes object which is a bitwise copy of an existing one"""
	dst = type(src)()
	pointer(dst)[0] = src
	return dst

def _freeLibrary(handle):
	if windll.kernel32.FreeLibrary(handle) == 0:
		raise WindowsError()
	return True

def _loadVeDll(path):
	veDll = cdll.LoadLibrary(path)
	# Basic runtime type checks...
	veDll.ve_ttsInitialize.errcheck = veCheckForError
	veDll.ve_ttsInitialize.restype = c_uint
	veDll.ve_ttsOpen.errcheck = veCheckForError
	veDll.ve_ttsOpen.restype = c_uint
	veDll.ve_ttsOpen.argtypes = (VE_HSAFE, c_void_p, c_void_p, POINTER(VE_HSAFE))
	veDll.ve_ttsProcessText2Speech.errcheck = veCheckForError
	veDll.ve_ttsProcessText2Speech.restype = c_uint
	veDll.ve_ttsStop.errcheck = veCheckForError
	veDll.ve_ttsStop.restype = c_uint
	veDll.ve_ttsPause.errcheck = veCheckForError
	veDll.ve_ttsPause.restype = c_uint
	veDll.ve_ttsResume.errcheck = veCheckForError
	veDll.ve_ttsResume.restype = c_uint
	veDll.ve_ttsSetParamList.errcheck = veCheckForError
	veDll.ve_ttsSetParamList.restype = c_uint
	veDll.ve_ttsGetParamList.errcheck = veCheckForError
	veDll.ve_ttsGetParamList.restype = c_uint
	veDll.ve_ttsGetLanguageList.errcheck = veCheckForError
	veDll.ve_ttsGetLanguageList.restype = c_uint
	veDll.ve_ttsGetVoiceList.restype = c_uint
	veDll.ve_ttsGetVoiceList.errcheck = veCheckForError
	veDll.ve_ttsGetSpeechDBList.restype = c_uint
	veDll.ve_ttsGetSpeechDBList.errcheck = veCheckForError
	veDll.ve_ttsClose.restype = c_uint
	veDll.ve_ttsClose.errcheck = veCheckForError
	veDll.ve_ttsUnInitialize.restype = c_uint
	veDll.ve_ttsUnInitialize.errcheck = veCheckForError
	veDll.ve_ttsSetOutDevice.errcheck = veCheckForError
	veDll.ve_ttsSetOutDevice.restype = c_uint
	veDll.ve_ttsResourceLoad.errcheck = veCheckForError
	veDll.ve_ttsGetProductVersion.restype = c_uint
	veDll.ve_ttsGetProductVersion.errcheck = veCheckForError
	veDll.ve_ttsGetAdditionalProductInfo.restype = c_uint
	veDll.ve_ttsGetAdditionalProductInfo.errcheck = veCheckForError
	veDll.ve_ttsResourceLoad.restype = c_uint
	return veDll

def _loadPlatformDll(path):
	platformDll = cdll.LoadLibrary(path)
	platformDll.vplatform_GetInterfaces.errcheck = veCheckForError
	platformDll.vplatform_GetInterfaces.restype = c_uint
	platformDll.vplatform_GetInterfaces.argtypes = (POINTER(VE_INSTALL), POINTER(VPLATFORM_RESOURCES))
	platformDll.vplatform_ReleaseInterfaces.errcheck = veCheckForError
	platformDll.vplatform_ReleaseInterfaces.restype = c_uint
	return platformDll

def initialize(resourcePaths):
	""" Initializes communication with vocalizer libraries. """
	global msvcrDll, veDll, platformDll, hSpeechClass, installResources
	_basePath = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))))), "WorldVoice-workspace", "VE", "libs")
	resourcePaths.insert(0, _basePath)
	# Load dlls
	msvcrDll = cdll.LoadLibrary(os.path.join(_basePath, "msvcr110.dll")) # required for ve.dll
	veDll = _loadVeDll(os.path.join(_basePath, "ve.dll"))
	platformDll = _loadPlatformDll(os.path.join(_basePath, "nuan_platform.dll"))
	# Provide external services to vocalizer
	installResources = VE_INSTALL()
	installResources.fmtVersion = VE_CURRENT_VERSION
	installResources.pBinBrokerInfo = None
	platformResources = VPLATFORM_RESOURCES()
	platformResources.fmtVersion = VPLATFORM_CURRENT_VERSION
	platformResources.licenseToken = None
	platformResources.u16NbrOfDataInstall = c_ushort(len(resourcePaths))
	platformResources.apDataInstall = (c_wchar_p * (len(resourcePaths)))()
	for i, path in enumerate(resourcePaths):
		platformResources.apDataInstall[i] = c_wchar_p(path)
	platformResources.pDatPtr_Table = None
	platformDll.vplatform_GetInterfaces(byref(installResources), byref(platformResources))

	# Initialize TTS class
	hSpeechClass = VE_HSAFE()
	veDll.ve_ttsInitialize(byref(installResources), byref(hSpeechClass))

def open(voice, callback):
	""" Opens and returns a TTS instance."""
	global installResources
	# Open tts instance
	instance = VE_HSAFE()
	veDll.ve_ttsOpen(hSpeechClass, installResources.hHeap, installResources.hLog, byref(instance))

	if voice is None:
		# Initialize to some voice and language so the synth will not complain...
		language = getLanguageList()[0].szLanguage
		voice = getVoiceList(language)[0].szVoiceName

	# Set Initial parameters
	setParamList(instance,
		(VE_PARAM_VOICE, voice),
		(VE_PARAM_MARKER_MODE, VE_MRK_ON),
		(VE_PARAM_INITMODE, VE_INITMODE_LOAD_ONCE_OPEN_ALL),
		(VE_PARAM_TEXTMODE, VE_TEXTMODE_STANDARD),
		(VE_PARAM_TYPE_OF_CHAR, VE_TYPE_OF_CHAR_UTF8),
		(VE_PARAM_READMODE, VE_READMODE_SENT),
		(VE_PARAM_FREQUENCY, 22),
	)

	# Set callback
	outDevInfo = VE_OUTDEVINFO()
	outDevInfo.pfOutNotify  = callback
	veDll.ve_ttsSetOutDevice(instance, byref(outDevInfo))
	return (instance, voice)

def close(instance):
	""" Closes a tts instance."""
	veDll.ve_ttsClose(instance)

def terminate():
	""" Terminates communication with vocalizer, freeing resources."""
	global msvcrDll, veDll, platformDll, hSpeechClass, installResources
	if hSpeechClass is not None:
		try:
			veDll.ve_ttsUnInitialize(hSpeechClass)
		except VeError:
			pass # Wrong state or something, not too much deal.
	platformDll.vplatform_ReleaseInterfaces(byref(installResources))
	hSpeechClass = None
	installResources = None
	# trying to unload all the dlls
	try:
		_freeLibrary(veDll._handle)
		_freeLibrary(platformDll._handle)
		_freeLibrary(msvcrDll._handle)
	finally:
		veDll = None
		platformDll = None
		msvcrDll = None

def processText2Speech(instance, text):
	text = text.encode("utf-8", "replace")
	inText = VE_INTEXT()
	inText.eTextFormat = VE_NORM_TEXT # this is the only supported format...
	inText.cntTextLength = c_size_t(len(text))
	inText.szInText = cast(c_char_p(text), c_void_p)
	veDll.ve_ttsProcessText2Speech(instance, byref(inText))

def setParamList(instance, *idAndValues):
	size = len(idAndValues)
	params = (VE_PARAM * size)()
	for i, pair in enumerate(idAndValues):
		params[i].ID = pair[0]
		if isinstance(pair[1], int):
			params[i].uValue.usValue = c_ushort(pair[1])
		else:
			params[i].uValue.szStringValue = pair[1].encode("utf-8")
	veDll.ve_ttsSetParamList(instance, params, c_ushort(size))

def getParamList(instance, *idAndTypes):
	size = len(idAndTypes)
	params = (VE_PARAM * size)()
	for i, pair in enumerate(idAndTypes):
		params[i].ID = pair[0]
	veDll.ve_ttsGetParamList(instance, params, c_ushort(size))
	values = []
	for i, pair in enumerate(idAndTypes):
		values.append(params[i].uValue.usValue if pair[1] is int else params[i].uValue.szStringValue.decode("utf-8"))
	return values

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
	hout = VE_HSAFE()
	veDll.ve_ttsResourceLoad(instance, contentType, length, content, byref(hout))
	return hout

def getAdditionalProductInfo():
	additionalProductInfo = VE_ADDITIONAL_PRODUCTINFO()
	veDll.ve_ttsGetAdditionalProductInfo(byref(additionalProductInfo))
	return additionalProductInfo

def getProductVersion():
	productVersion = VE_PRODUCT_VERSION()
	veDll.ve_ttsGetProductVersion(byref(productVersion))
	return productVersion

@contextlib.contextmanager
def preOpenVocalizer(resourcePaths):
	wasInit = hSpeechClass is not None
	success = False
	try:
		if not wasInit:
			initialize(resourcePaths)
		success = True
	except VeError:
		pass
	try:
		yield success
	finally:
		if not wasInit:
			terminate()
