#vocalizer/storage.py
#A part of the vocalizer driver for NVDA (Non Visual Desktop Access)
#Copyright (C) 2013 Rui Batista <ruiandrebatista@gmail.com>
#Copyright (C) 2013 Tiflotecnia, lda. <www.tiflotecnia.com>
#This file is covered by the GNU General Public License.
#See the file GPL.txt for more details.


from ctypes import *
from ctypes.wintypes import *
import itertools
import os.path
import pickle
import config
import globalVars
from logHandler import log
import shlobj
from fileUtils import FaultTolerantFile

# Structures to use with windows data protection API
class DATA_BLOB(Structure):
	_fields_ = (("cbData", DWORD),
		("pbData", POINTER(c_char)))

crypt32 = windll.crypt32

VOCALIZER_CONFIG_FOLDER = "vocalizer-for-nvda"
VOCALIZER_LICENSE_FILE = "activation.dat"
VOCALIZER_CREDENTIALS_FILE = "credentials.dat"

def _loadLicenseData(path):
	log.debug("Loading license data from %s", path)
	with open(path, "rb") as f:
		try:
			data = pickle.load(f)
		except pickle.UnpicklingError:
			log.warning(f"Couldn't automatically unpickle {path!r}, trying manual method")
			raw = f.read().replace(b"\r\n", b"\n")
			data = pickle.loads(raw)
		return data

def _saveLicenseData(path, data):
	log.debug("Saving license data to %s", path)
	with FaultTolerantFile(path) as f:
		pickle.dump(f, data, protocol=0)


def _getLocalConfigFolder():
	return os.path.join(shlobj.SHGetFolderPath(0, shlobj.CSIDL_APPDATA), VOCALIZER_CONFIG_FOLDER)


def _getLicenseDirs(forcePortable=False):
	if not config.isInstalledCopy() or forcePortable:
		yield os.path.join(globalVars.appArgs.configPath, VOCALIZER_CONFIG_FOLDER), False
	yield _getLocalConfigFolder(), True


def _getLicenseDir(forcePortable=False):
	return next(_getLicenseDirs(forcePortable=forcePortable))[0]

_licensePath = None
_licenseData = None

def getLicenseData(forcePortable=True):
	global _licenseData, _licensePath
	if _licenseData is None:
		path = None
		installed = False
		for p, i in _getLicenseDirs(forcePortable):
			trial= os.path.join(p, VOCALIZER_LICENSE_FILE)
			if os.path.isfile(trial):
				path = trial
				installed = i
				break
		if path is not None:
			_licenseData = _loadLicenseData(path)
			_licenseData['installed'] = installed
			_licensePath = path
		else:
			_licenseData = None
	return _licenseData

def getCredentials():
	credentialsPath = None
	installed = None
	for tryal, i in _getLicenseDirs():
		tryPath = os.path.join(tryal, VOCALIZER_CREDENTIALS_FILE)
		if os.path.isfile(tryPath):
			credentialsPath = tryPath
			installed = i
	if credentialsPath is None:
		return None, None
	log.debug("Loading credentials from %s", credentialsPath)
	with open(credentialsPath, "rb") as f:
		try:
			data = pickle.load(f)
		except pickle.UnpicklingError:
			log.warning(f"Couldn't automatically unpickle {credentialsPath!r}, trying manual method")
			raw = f.read().replace(b"\r\n", b"\n")
			data = pickle.loads(raw)
		email = data['email']
		password = data['password']
		if password is not None and installed:
			try:
				password = _decryptUserData(password)
			except:
				log.error("Could not decrypt password", exc_info=True)
				return None, None
	return email, password

def saveCredentials(email, password, forcePortable=False):
	path = os.path.join(_getLicenseDir(forcePortable=forcePortable), VOCALIZER_CREDENTIALS_FILE)
	log.debug("Saving credentials in %s", path)
	try:
		os.makedirs(os.path.dirname(path))
	except WindowsError:
		pass
	if password is not None and config.isInstalledCopy() and (not forcePortable):
		data = dict(email=email, password=_encryptUserData(password))
	else:
		data = dict(email=email, password=password)
	with FaultTolerantFile(path) as f:
		pickle.dump(data, f, protocol=0)

def deleteCredentials():
	path = os.path.join(_getLicenseDir(), VOCALIZER_CREDENTIALS_FILE)
	if os.path.isfile(path):
		os.unlink(path)


def saveLicenseData(data, forcePortable=False):
	global _licensePath, _licenseData
	_licenseData = data
	if not _licensePath or forcePortable:
		path = os.path.join(_getLicenseDir(forcePortable=forcePortable), VOCALIZER_LICENSE_FILE)
		dir = os.path.dirname(path)
		if not os.path.isdir(dir):
			os.makedirs(dir)
		_licensePath = path
	if data is not None: # Store
		with FaultTolerantFile(_licensePath) as f:
			pickle.dump(_licenseData, f, protocol=0)
	else: # Delete
		os.unlink(_licensePath)
		_licensePath = None

def _encryptUserData(data):
	data = data.encode("utf-8")
	dataIn = DATA_BLOB()
	dataIn.cbData = len(data)
	dataIn.pbData = create_string_buffer(data, len(data))
	dataOut = DATA_BLOB()
	if not crypt32.CryptProtectData(byref(dataIn), "", None, None, None, 0, byref(dataOut)):
		raise WindowsError("Can't protect data")
	return string_at(dataOut.pbData, dataOut.cbData)

def _decryptUserData(data):
	dataIn = DATA_BLOB()
	dataIn.cbData = len(data)
	dataIn.pbData = create_string_buffer(data, len(data))
	dataOut = DATA_BLOB()
	if not crypt32.CryptUnprotectData(byref(dataIn), None, None, None, None, 0, byref(dataOut)):
		raise WindowsError("Can't unprotect data")
	return string_at(dataOut.pbData, dataOut.cbData).decode("utf-8")


