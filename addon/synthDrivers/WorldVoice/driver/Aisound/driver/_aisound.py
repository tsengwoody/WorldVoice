#_aisound.py
#A part of NVDA AiSound 5 Synthesizer Add-On

import os
import threading
import weakref
import audioDucking
from ctypes import *
from ctypes.wintypes import HANDLE, WORD, DWORD, UINT, LPUINT
from logHandler import log
from synthDriverHandler import synthIndexReached,synthDoneSpeaking

# synthDriverHost don't support NVDAHelper.
try:
	import NVDAHelper
except ModuleNotFoundError:
	supportedNVDAHelper = False
else:
	supportedNVDAHelper = True

user_folder = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))))
workspaceAisound_path = os.path.join(user_folder, "WorldVoice-workspace", "Aisound")

wrapperDLL=None
lastIndex=None
isPlaying=False
synthRef=None
_currentGeneration=0
_nextCbToken=1
_tokenToGeneration={}
_tokenToIndex={}
_generationPending={}
_stateLock=threading.Lock()

aisound_callback_t=CFUNCTYPE(None,c_int,c_void_p)
SPEECH_BEGIN=0
SPEECH_END=1


HWAVEOUT = HANDLE
LPHWAVEOUT = POINTER(HWAVEOUT)


class WAVEFORMATEX(Structure):
	_fields_ = [
		("wFormatTag", WORD),
		("nChannels", WORD),
		("nSamplesPerSec", DWORD),
		("nAvgBytesPerSec", DWORD),
		("nBlockAlign", WORD),
		("wBitsPerSample", WORD),
		("cbSize", WORD),
	]


LPWAVEFORMATEX = POINTER(WAVEFORMATEX)

# Set argument types.
windll.winmm.waveOutOpen.argtypes = (
	LPHWAVEOUT,
	UINT,
	LPWAVEFORMATEX,
	DWORD,
	DWORD,
	DWORD
)
windll.winmm.waveOutGetID.argtypes = (HWAVEOUT, LPUINT)


class FunctionHooker(object):

	def __init__(
		self,
		targetDll: str,
		importDll: str,
		funcName: str,
		newFunction # result of ctypes.WINFUNCTYPE
	):
		# dllImportTableHooks_hookSingle expects byte strings.
		try:
			self._hook=NVDAHelper.localLib.dllImportTableHooks_hookSingle(
				targetDll.encode("mbcs"),
				importDll.encode("mbcs"),
				funcName.encode("mbcs"),
				newFunction
			)
		except UnicodeEncodeError:
			log.error("Error encoding FunctionHooker input parameters", exc_info=True)
			self._hook = None
		if self._hook:
			log.debug(f"Hooked {funcName}")
		else:
			log.error(f"Could not hook {funcName}")
			raise RuntimeError(f"Could not hook {funcName}")

	def __del__(self):
		if self._hook:
			NVDAHelper.localLib.dllImportTableHooks_unhookSingle(self._hook)

_duckersByHandle={}

@WINFUNCTYPE(windll.winmm.waveOutOpen.restype,*windll.winmm.waveOutOpen.argtypes,use_errno=False,use_last_error=False)
def waveOutOpen(pWaveOutHandle,deviceID,wfx,callback,callbackInstance,flags):
	# Normalize callback pointers to the current winmm argtypes. This avoids
	# ctypes rejecting equivalent pointer types when the module has been reloaded.
	expected_handle_type = windll.winmm.waveOutOpen.argtypes[0]
	expected_wfx_type = windll.winmm.waveOutOpen.argtypes[2]
	if pWaveOutHandle:
		pWaveOutHandle = cast(pWaveOutHandle, expected_handle_type)
	if wfx:
		wfx = cast(wfx, expected_wfx_type)
	try:
		res=windll.winmm.waveOutOpen(pWaveOutHandle,deviceID,wfx,callback,callbackInstance,flags) or 0
	except WindowsError as e:
		res=e.winerror
	if res==0 and pWaveOutHandle:
		h=pWaveOutHandle.contents.value
		d=audioDucking.AudioDucker()
		d.enable()
		_duckersByHandle[h]=d
	return res

@WINFUNCTYPE(c_long,c_long)
def waveOutClose(waveOutHandle):
	try:
		res=windll.winmm.waveOutClose(waveOutHandle) or 0
	except WindowsError as e:
		res=e.winerror
	if res==0 and waveOutHandle:
		_duckersByHandle.pop(waveOutHandle,None)
	return res

_waveOutHooks=[]
def ensureWaveOutHooks(dllPath):
	if not _waveOutHooks and audioDucking.isAudioDuckingSupported():
		_waveOutHooks.append(FunctionHooker(dllPath,"WINMM.dll","waveOutOpen",waveOutOpen))
		_waveOutHooks.append(FunctionHooker(dllPath,"WINMM.dll","waveOutClose",waveOutClose))


def _handle_utterance_end(token):
	"""Handles cleanup for an utterance. Must be called with _stateLock held."""
	global isPlaying
	gen = _tokenToGeneration.pop(token, None)
	_tokenToIndex.pop(token, None)

	if gen is not None:
		# Utterance was found, decrement pending count for its generation.
		remaining = _generationPending.get(gen, 0)
		if remaining > 1:
			_generationPending[gen] = remaining - 1
		elif remaining == 1:
			_generationPending.pop(gen, None)

	# Always update isPlaying to reflect the current state for robustness.
	currentPending = _generationPending.get(_currentGeneration, 0)
	isPlaying = currentPending > 0

	# Notify only if the utterance was from the current generation and it was the last one.
	return gen is not None and gen == _currentGeneration and currentPending == 0


@aisound_callback_t
def callback(type,cbData):
	global lastIndex,isPlaying,synthRef
	token = int(cbData) if cbData else None
	if type==SPEECH_BEGIN:
		if token is None:
			lastIndex=0
			return
		with _stateLock:
			index = _tokenToIndex.get(token)
		if index is not None:
			lastIndex=index
			synthIndexReached.notify(synth=synthRef(),index=lastIndex)
	elif type==SPEECH_END:
		shouldNotify=False
		with _stateLock:
			if token is None:
				return
			shouldNotify = _handle_utterance_end(token)
		if shouldNotify:
			synthDoneSpeaking.notify(synth=synthRef())

def Initialize(synth: weakref.ReferenceType):
	global wrapperDLL,isPlaying,synthRef
	synthRef = synth
	if wrapperDLL==None:
		# dllPath=os.path.abspath(os.path.join(os.path.dirname(__file__), r"aisound.dll"))
		dllPath=os.path.join(workspaceAisound_path, "aisound.dll")
		if supportedNVDAHelper:
			ensureWaveOutHooks(dllPath)
		wrapperDLL=cdll.LoadLibrary(dllPath)
		wrapperDLL.aisound_callback.restype=c_bool
		wrapperDLL.aisound_callback.argtypes=[aisound_callback_t]
		wrapperDLL.aisound_configure.restype=c_bool
		wrapperDLL.aisound_configure.argtypes=[c_char_p,c_char_p]
		wrapperDLL.aisound_speak.restype=c_bool
		wrapperDLL.aisound_speak.argtypes=[c_char_p,c_void_p]
		wrapperDLL.aisound_cancel.restype=c_bool
		wrapperDLL.aisound_pause.restype=c_bool
		wrapperDLL.aisound_resume.restype=c_bool
	wrapperDLL.aisound_initialize()
	wrapperDLL.aisound_callback(callback)

def Terminate():
	global wrapperDLL
	wrapperDLL.aisound_terminate()

def Configure(name,value):
	global wrapperDLL
	return wrapperDLL.aisound_configure(name.encode("utf-8"),value.encode("utf-8"))

def Speak(text,index=None):
	global wrapperDLL,isPlaying,_nextCbToken
	with _stateLock:
		token = _nextCbToken
		_nextCbToken += 1
		# c_void_p(0) becomes None on callback; keep token non-zero.
		if _nextCbToken > 0x7FFFFFFF:
			_nextCbToken = 1
		gen = _currentGeneration
		_tokenToGeneration[token] = gen
		if index is not None:
			_tokenToIndex[token] = index
		_generationPending[gen] = _generationPending.get(gen, 0) + 1
		isPlaying=True
	ok = wrapperDLL.aisound_speak(text.encode("utf-8"),c_void_p(token))
	if not ok:
		shouldNotify=False
		with _stateLock:
			shouldNotify = _handle_utterance_end(token)
		if shouldNotify:
			synthDoneSpeaking.notify(synth=synthRef())
	return ok

def Cancel():
	global wrapperDLL,isPlaying,synthRef,_currentGeneration
	with _stateLock:
		_currentGeneration += 1
		_tokenToGeneration.clear()
		_tokenToIndex.clear()
		_generationPending.clear()
		isPlaying=False
	synthDoneSpeaking.notify(synth=synthRef())
	return wrapperDLL.aisound_cancel()

def Pause():
	global wrapperDLL
	return wrapperDLL.aisound_pause()

def Resume():
	global wrapperDLL
	return wrapperDLL.aisound_resume()


# vim: set tabstop=4 shiftwidth=4 wm=0:
