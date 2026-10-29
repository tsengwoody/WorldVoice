"""Standalone VE / Cerence VE_MSG_ENDPROCESS probe; needs Windows and Python, not NVDA.

Read docs/superpowers/handoff/2026-10-29-ve-endprocess-sdk-test.md first.

	python ve_endprocess_probe.py                 # both engines, every installed voice
	python ve_endprocess_probe.py --engine VE --voices Mei-Jia Samantha

The Python bitness must match the SDK libraries in WorldVoice-workspace (32-bit
Python for lib\\x86 or lib\\x32, 64-bit for lib\\AMD64 or lib\\x64). The probe loads
each engine's own ctypes layer from the WorldVoice add-on (driver/VE/driver/ve2,
driver/Cerence/driver/ttsapi), opens every voice the way the add-on does, sends
the text pieces the add-on can send, and records every callback message and the
result of each ve_ttsProcessText2Speech call. It plays no audio.
"""

import argparse
import importlib.util
import os
import subprocess
import sys
import threading
import time
from ctypes import (
	POINTER,
	byref,
	c_byte,
	c_char_p,
	c_size_t,
	c_ushort,
	c_void_p,
	c_wchar_p,
	cast,
	cdll,
	sizeof,
)

ENGINES = {
	# engine: (ctypes package under driver/<Engine>/driver, workspace folder, lib folders, msvcr, voice add-on prefix)
	"VE": (
		"ve2",
		"VE",
		("AMD64", "x64") if sys.maxsize > 2**32 else ("x86", "x32"),
		True,
		"vocalizer-expressive2-voice",
	),
	"Cerence": (
		"ttsapi",
		"Cerence",
		("x64", "AMD64") if sys.maxsize > 2**32 else ("x32", "x86"),
		False,
		"CerenceTTS-voice",
	),
}

PCM_BUF_LEN = 8192  # same as the add-on's pcmBufLen
MARK_BUF_SIZE = 100  # same as the add-on's markBufSize

# The exact strings the add-on can hand to ve_ttsProcessText2Speech: the inner driver
# turns commands into these escapes, and the chunker cuts text every 100 characters,
# so a record's last piece can be punctuation, space or escapes alone.
PIECES = [
	("text", "Hello world."),
	("text-no-punct", "Hello"),
	("digits", "123."),
	("cjk-text", "你好。"),
	("punct", "."),
	("cjk-punct", "。"),
	("comma", ","),
	("exclaim-question", "!?"),
	("dash", "-"),
	("ellipsis", "…"),
	("space", " "),
	("spaces", "   "),
	("ideographic-space", "　"),
	("newline", "\n"),
	("bookmark", "\x1b\\mrk=9001\\"),
	("pause", "\x1b\\pause=300\\"),
	("pitch", "\x1b\\pitch=110\\"),
	("rate", "\x1b\\rate=150\\"),
	("volume", "\x1b\\vol=80\\"),
	("spell-on", "\x1b\\tn=spell\\"),
	("spell-a", "\x1b\\tn=spell\\a\x1b\\tn=normal\\"),
	("text-bookmark", "Hello\x1b\\mrk=9002\\"),
	("bookmark-punct", "\x1b\\mrk=9003\\."),
	("space-bookmark", " \x1b\\mrk=9004\\"),
	("long-100", "word " * 20),
]
# Never sent by the add-on (the chunker returns no piece for empty text); reported only.
INFO_PIECES = [("empty", "")]
# Stop mid-synthesis by returning USERSTOP from the callback, as the add-on does on cancel.
STOP_PIECE = ("stop-after-2-buffers", "word " * 60, 2)


def _log(lines, line):
	lines.append(line)
	print(line, flush=True)


def _loadPackage(engine, driverDir):
	package, *_ = ENGINES[engine]
	path = os.path.join(driverDir, engine, "driver", package)
	init = os.path.join(path, "__init__.py")
	if not os.path.isfile(init):
		raise SystemExit(f"{engine}: cannot find {init}; pass --driver-dir")
	spec = importlib.util.spec_from_file_location(
		f"wvprobe_{package}", init, submodule_search_locations=[path]
	)
	module = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


def _resourcePaths(engine, workspace, addonsDir):
	_, folder, _, _, prefix = ENGINES[engine]
	engineDir = os.path.join(workspace, folder)
	paths = [os.path.join(engineDir, "common")]
	if os.path.isdir(addonsDir):
		for name in sorted(os.listdir(addonsDir)):
			if name.startswith(prefix):
				paths.append(os.path.join(addonsDir, name))
	if os.path.isdir(engineDir):
		paths.append(engineDir)
	programdata = os.getenv("PROGRAMDATA")
	if engine == "VE" and programdata:
		for version in ("2.2", "21"):
			path = os.path.join(
				programdata, "Freedom Scientific", "VocalizerExpressive", version, "languages"
			)
			if os.path.isdir(path) and os.listdir(path):
				paths.append(path)
	return engineDir, paths


def _initialize(engine, api, engineDir, resourcePaths):
	"""The add-on's initialize(), with the library folder chosen for this Python."""
	_, _, libNames, needsMsvcr, _ = ENGINES[engine]
	libDir = next(
		(
			os.path.join(engineDir, "lib", name)
			for name in libNames
			if os.path.isdir(os.path.join(engineDir, "lib", name))
		),
		None,
	)
	if libDir is None:
		bits = 64 if sys.maxsize > 2**32 else 32
		raise SystemExit(
			f"{engine}: no lib\\{'|'.join(libNames)} under {engineDir} for this {bits}-bit Python; try the other bitness"
		)
	if needsMsvcr:
		cdll.LoadLibrary(os.path.join(libDir, "msvcr110.dll"))
	api.veDll = api._loadVeDll(os.path.join(libDir, "ve.dll"))
	api.platformDll = api._loadPlatformDll(os.path.join(libDir, "vplatform.dll"))
	api.installResources = api.VE_INSTALL()
	api.installResources.fmtVersion = api.VE_CURRENT_VERSION
	api.installResources.pBinBrokerInfo = None
	platform = api.VPLATFORM_RESOURCES()
	platform.fmtVersion = api.VPLATFORM_CURRENT_VERSION
	platform.u16NbrOfDataInstall = c_ushort(len(resourcePaths))
	platform.apDataInstall = (c_wchar_p * len(resourcePaths))()
	for i, path in enumerate(resourcePaths):
		platform.apDataInstall[i] = c_wchar_p(path)
	platform.pDatPtr_Table = None
	api.platformDll.vplatform_GetInterfaces(byref(api.installResources), byref(platform))
	api.hSpeechClass = api.VE_HSAFE()
	api.veDll.ve_ttsInitialize(byref(api.installResources), byref(api.hSpeechClass))
	return libDir


class _Recorder:
	"""The output callback: supplies buffers like the add-on and records every message."""

	def __init__(self, api):
		self.api = api
		self.pcm = (c_byte * PCM_BUF_LEN)()
		self.marks = (api.VE_MARKINFO * MARK_BUF_SIZE)()
		self.call = None
		self.stray = []
		self.native = api.VE_CBOUTNOTIFY(self)

	def __call__(self, instance, userData, message):
		api = self.api
		try:
			kind = message.contents.eMessage
			call = self.call
			if call is None:
				self.stray.append((kind, threading.get_ident()))
				return api.NUAN_OK
			call["messages"].append(kind)
			call["threads"].add(threading.get_ident())
			if kind == api.VE_MSG_OUTBUFREQ:
				data = cast(message.contents.pParam, POINTER(api.VE_OUTDATA)).contents
				data.pOutPcmBuf = cast(self.pcm, c_void_p)
				data.cntPcmBufLen = c_size_t(PCM_BUF_LEN)
				data.pMrkList = cast(self.marks, POINTER(api.VE_MARKINFO))
				data.cntMrkListLen = c_size_t(MARK_BUF_SIZE * sizeof(api.VE_MARKINFO))
			elif kind == api.VE_MSG_OUTBUFDONE:
				data = cast(message.contents.pParam, POINTER(api.VE_OUTDATA)).contents
				call["audioBytes"] += int(data.cntPcmBufLen)
				call["buffers"] += 1
				if call["stopAfter"] is not None and call["buffers"] >= call["stopAfter"]:
					call["stopReturned"] = True
					return api.NUAN_E_TTS_USERSTOP
			if call["stopReturned"]:
				return api.NUAN_E_TTS_USERSTOP
			return api.NUAN_OK
		except Exception as error:  # noqa: BLE001 - never raise into the SDK
			self.stray.append((f"callback error {error!r}", threading.get_ident()))
			return api.NUAN_OK


def _process(api, recorder, instance, text, stopAfter=None):
	"""The add-on's ProcessText2Speech: raw call, so the result code is kept."""
	encoded = text.encode("utf-8", "replace")
	data = api.VE_INTEXT()
	data.eTextFormat = api.VE_NORM_TEXT
	data.cntTextLength = len(encoded)
	buffer = c_char_p(encoded)
	data.szInText = cast(buffer, c_void_p)
	native = api.veDll.ve_ttsProcessText2Speech
	raw = type(native)(cast(native, c_void_p).value)
	raw.restype = native.restype
	raw.argtypes = native.argtypes
	call = {
		"messages": [],
		"threads": set(),
		"audioBytes": 0,
		"buffers": 0,
		"stopAfter": stopAfter,
		"stopReturned": False,
		"thread": threading.get_ident(),
	}
	recorder.call = call
	try:
		call["result"] = raw(instance, byref(data))
	finally:
		recorder.call = None
	return call


def _names(api):
	return {getattr(api, name): name[len("VE_MSG_") :] for name in dir(api) if name.startswith("VE_MSG_")}


def _compress(kinds, names):
	out = []
	for kind in kinds:
		label = names.get(kind, hex(kind) if isinstance(kind, int) else str(kind))
		if out and out[-1][0] == label:
			out[-1][1] += 1
		else:
			out.append([label, 1])
	return ",".join(label if count == 1 else f"{label}x{count}" for label, count in out)


def _verdict(api, call, counted):
	kinds = call["messages"]
	ends = kinds.count(api.VE_MSG_ENDPROCESS)
	result = call["result"]
	status = (
		"OK"
		if result == api.NUAN_OK
		else "USERSTOP"
		if result == api.NUAN_E_TTS_USERSTOP
		else f"0x{result:x}"
	)
	if not counted or status != "OK":
		return "info", status, ends
	if ends == 0:
		return "FAIL", status, ends
	if ends > 1 or kinds[-1] != api.VE_MSG_ENDPROCESS:
		return "WARN", status, ends
	return "pass", status, ends


def _voices(api, wanted):
	found = []
	for language in api.getLanguageList():
		for info in api.getVoiceList(language.szLanguage):
			name = info.szVoiceName.decode("utf-8", "replace")
			if not wanted or name in wanted:
				found.append((language.szLanguage.decode("utf-8", "replace"), name))
	return found


def runEngine(engine, args):
	lines = []
	api = _loadPackage(engine, args.driver_dir)
	engineDir, resourcePaths = _resourcePaths(engine, args.workspace, args.addons_dir)
	libDir = _initialize(engine, api, engineDir, resourcePaths)
	names = _names(api)
	recorder = _Recorder(api)
	try:
		version = api.getProductVersion()
		versionText = f"{version.major}.{version.minor}.{version.maint}"
	except Exception as error:  # noqa: BLE001
		versionText = f"? ({error!r})"
	bits = 64 if sys.maxsize > 2**32 else 32
	_log(
		lines,
		f"=== {engine} probe {time.strftime('%Y-%m-%d %H:%M:%S')} SDK {versionText} lib {libDir} Python {sys.version.split()[0]} {bits}-bit ===",
	)
	_log(lines, f"resources: {resourcePaths}")
	counts = {}
	failures = []
	voices = _voices(api, set(args.voices or ()))
	if not voices:
		_log(lines, f"{engine}: no voices found")
	instances = []
	try:
		for language, voice in voices:
			try:
				instance, opened = api.open(voice, recorder.native)
			except Exception as error:  # noqa: BLE001 - report and go on with the next voice
				_log(lines, f"[ERROR] {engine} {voice} ({language}) open: {error!r}")
				counts["ERROR"] = counts.get("ERROR", 0) + 1
				continue
			instances.append(instance)
			cases = [(label, text, None, True) for label, text in PIECES]
			cases += [(label, text, None, False) for label, text in INFO_PIECES]
			cases.append((STOP_PIECE[0], STOP_PIECE[1], STOP_PIECE[2], False))
			for label, text, stopAfter, counted in cases:
				try:
					call = _process(api, recorder, instance, text, stopAfter)
				except Exception as error:  # noqa: BLE001
					_log(lines, f"[ERROR] {engine} {opened} ({language}) {label}: {error!r}")
					counts["ERROR"] = counts.get("ERROR", 0) + 1
					continue
				verdict, status, ends = _verdict(api, call, counted)
				counts[verdict] = counts.get(verdict, 0) + 1
				sameThread = call["threads"] <= {call["thread"]}
				line = (
					f"[{verdict}] {engine} {opened} ({language}) {label} {status} endprocess={ends} "
					f"audio={call['audioBytes']}B sameThread={sameThread} msgs={_compress(call['messages'], names)}"
				)
				_log(lines, line)
				if verdict in ("FAIL", "WARN"):
					failures.append(line)
	finally:
		for instance in instances:
			try:
				api.close(instance)
			except Exception as error:  # noqa: BLE001
				_log(lines, f"[close-error] {error!r}")
		try:
			api.veDll.ve_ttsUnInitialize(api.hSpeechClass)
			api.platformDll.vplatform_ReleaseInterfaces(byref(api.installResources))
		except Exception as error:  # noqa: BLE001
			_log(lines, f"[teardown-error] {error!r}")
	_log(
		lines,
		f"=== {engine} summary: {len(voices)} voices, {counts}, {len(recorder.stray)} callbacks outside a call ===",
	)
	for line in failures:
		_log(lines, f"  {line}")
	for kind, thread in recorder.stray[:20]:
		_log(lines, f"  stray: {names.get(kind, kind)} thread={thread}")
	with open(args.log, "a", encoding="utf-8") as file:
		file.write("\n".join(lines) + "\n")
	return 1 if failures or counts.get("ERROR") else 0


def main():
	appdata = os.getenv("APPDATA", "")
	here = os.path.dirname(os.path.abspath(__file__))
	repoDriverDir = os.path.join(here, "..", "..", "..", "addon", "synthDrivers", "WorldVoice", "driver")
	installedDriverDir = os.path.join(
		appdata, "nvda", "addons", "WorldVoice", "synthDrivers", "WorldVoice", "driver"
	)
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--engine", choices=["VE", "Cerence", "all"], default="all")
	parser.add_argument("--voices", nargs="*", help="voice names to test (default: every installed voice)")
	parser.add_argument("--workspace", default=os.path.join(appdata, "WorldVoice-workspace"))
	parser.add_argument("--addons-dir", default=os.path.join(appdata, "nvda", "addons"))
	parser.add_argument(
		"--driver-dir",
		default=os.path.normpath(repoDriverDir if os.path.isdir(repoDriverDir) else installedDriverDir),
		help="the add-on's synthDrivers/WorldVoice/driver folder",
	)
	parser.add_argument("--log", default=os.path.join(here, "ve_endprocess_probe.log"))
	args = parser.parse_args()
	if args.engine != "all":
		return runEngine(args.engine, args)
	# Both SDKs ship a ve.dll and a vplatform.dll: run each engine in its own process.
	status = 0
	for engine in ENGINES:
		command = [sys.executable, os.path.abspath(__file__), "--engine", engine]
		command += [
			"--workspace",
			args.workspace,
			"--addons-dir",
			args.addons_dir,
			"--driver-dir",
			args.driver_dir,
			"--log",
			args.log,
		]
		if args.voices:
			command += ["--voices", *args.voices]
		status |= subprocess.call(command)
	return status


if __name__ == "__main__":
	sys.exit(main())
