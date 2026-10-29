"""Standalone VE / Cerence VE_MSG_ENDPROCESS probe; needs Windows and Python, not NVDA.

Read docs/superpowers/handoff/2026-10-29-ve-endprocess-sdk-test.md first.

	python ve_endprocess_probe.py                 # both engines, every installed voice
	python ve_endprocess_probe.py --engine VE --voices Mei-Jia Samantha
	py -3-32 ve_endprocess_probe.py               # 32-bit Python: lib\\x86 (VE) and lib\\x32 (Cerence)

The probe picks each engine's lib folder with the add-on's own rule (VE: the
PROCESSOR_ARCHITECTURE environment variable, which is x86 in a 32-bit process on
64-bit Windows; Cerence: x64 or x32 from the Python bitness), so a 32-bit Python
tests the libraries NVDA 2024.1-2025.x loads and a 64-bit Python those NVDA
2026.1+ loads. It loads each engine's own ctypes layer from the WorldVoice add-on
(driver/VE/driver/ve2, driver/Cerence/driver/ttsapi), opens every voice the way
the add-on does, sends the text pieces the add-on can send, and records every
callback message and the result of each ve_ttsProcessText2Speech call. It plays
no audio.
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

BITS = 64 if sys.maxsize > 2**32 else 32

ENGINES = {
	# engine: (ctypes package under driver/<Engine>/driver, workspace folder, msvcr, voice add-on prefix)
	"VE": ("ve2", "VE", True, "vocalizer-expressive2-voice"),
	"Cerence": ("ttsapi", "Cerence", False, "CerenceTTS-voice"),
}

PCM_BUF_LEN = 8192  # same as the add-on's pcmBufLen
MARK_BUF_SIZE = 100  # same as the add-on's markBufSize
MAX_TEXT_LENGTH = 100  # text/chunker.py: plain characters per piece; escapes are not counted


def _mark(index):
	return f"\x1b\\mrk={index}\\"


def _spellPieces(count, first=1):
	"""The pieces the add-on sends when it spells count characters with an index after each.

	The inner speak() joins CharacterModeCommand(True) as \\tn=spell\\, each lower-cased
	character (no separator in character mode) followed by its IndexCommand as \\mrk=\\,
	and CharacterModeCommand(False) as \\tn=normal\\. The chunker counts only the
	characters, cuts after every 100th one and moves the escapes after a cut to the next
	piece, so a piece holds 100 characters and up to 100 escapes.
	"""
	letters = "abcdefghijklmnopqrstuvwxyz"
	chars = [letters[i % len(letters)] for i in range(count)]
	marks = [_mark(first + i) for i in range(count)]
	pieces = []
	for start in range(0, count, MAX_TEXT_LENGTH):
		end = min(start + MAX_TEXT_LENGTH, count)
		piece = marks[start - 1] if start else "\x1b\\tn=spell\\"
		piece += "".join(chars[i] + (marks[i] if i < end - 1 else "") for i in range(start, end))
		pieces.append(piece)
	pieces[-1] += marks[count - 1] + "\x1b\\tn=normal\\"
	return pieces


_SPELL_FIRST, _SPELL_MIDDLE, _SPELL_LAST = _spellPieces(250)

# Counted (pass/FAIL): the exact strings the add-on can hand to ve_ttsProcessText2Speech.
# The inner speak() strips each text item, removes ESC from it and turns commands into
# these escapes; the wrapper's _speak() cuts the joined text with text/chunker.py every
# 100 characters, so a record's last piece can be punctuation, space or escapes alone.
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
	("bookmark", _mark(9001)),
	("pause", "\x1b\\pause=300\\"),
	("pitch", "\x1b\\pitch=110\\"),
	("rate", "\x1b\\rate=150\\"),
	("volume", "\x1b\\vol=80\\"),
	("spell-on", "\x1b\\tn=spell\\"),
	("spell-a", "\x1b\\tn=spell\\a\x1b\\tn=normal\\"),
	("text-bookmark", "Hello" + _mark(9002)),
	("bookmark-punct", _mark(9003) + "."),
	("space-bookmark", " " + _mark(9004)),
	("long-100", "word " * 20),
	# Control characters: strip() keeps the ones that are not whitespace and only ESC is
	# removed, so text made of them alone reaches the SDK.
	("bel", "\x07"),
	("del", "\x7f"),
	("c0-controls", "\x01\x02\x03"),
	("c1-control", "\x9b"),
	("text-bel", "Hello\x07"),
	# Zero-width and format characters: Python's strip() does not treat them as space.
	("zwsp", "\u200b"),
	("zwnj", "\u200c"),
	("zwj", "\u200d"),
	("word-joiner", "\u2060"),
	("bom", "\ufeff"),
	("lrm", "\u200e"),
	("rlm", "\u200f"),
	("soft-hyphen", "\xad"),
	("zero-width-mix", "\u200b\u200c\u200d\u2060\ufeff"),
	("text-zwsp", "Hello\u200b"),
	("bom-text", "\ufeffHello"),
	# A lone surrogate from a UTF-16 source: encode("utf-8", "replace") sends "?".
	("lone-surrogate", "\ud800"),
	# Spelling (character mode) with a capital: PitchCommand(offset) and PitchCommand().
	("spell-cap", "\x1b\\tn=spell\\\x1b\\pitch=130\\a\x1b\\pitch=100\\" + _mark(1) + "\x1b\\tn=normal\\"),
	# A sequence of index commands only: the chunker keeps it whole as one piece.
	("bookmarks-x100", "".join(_mark(9100 + i) for i in range(100))),
	# 250 spelled characters: 100 characters with 99 bookmarks after \tn=spell\, then
	# 100 characters with 100 bookmarks, then 50 characters, 51 bookmarks and \tn=normal\.
	("spell-100-first", _SPELL_FIRST),
	("spell-100-middle", _SPELL_MIDDLE),
	("spell-last", _SPELL_LAST),
]
# Counted for these engines only; info elsewhere. Cerence's inner speak() has no
# RateCommand/VolumeCommand branch, so it never sends \rate= or \vol=.
ENGINE_ONLY = {"rate": {"VE"}, "volume": {"VE"}}
# Info only: shapes the add-on never sends.
INFO_PIECES = [
	# The chunker returns no piece for empty text.
	("empty", ""),
	# NVDA's text comes from C strings that end at NUL, so it never carries one.
	("nul", "\x00"),
]
# Info only: stop mid-synthesis by returning USERSTOP from the callback, as the add-on
# does on cancel; the add-on raises on a USERSTOP result, so its ENDPROCESS is not used.
STOP_PIECE = ("stop-after-2-buffers", "word " * 60, 2)
# Counted: after a cancel the add-on speaks the next text on the same instance.
AFTER_STOP_PIECES = [("after-stop-text", "Hello world."), ("after-stop-punct", ".")]
# Counted: the voice settings the add-on sets with TtsSetParamList before it speaks
# (the variant is re-set to the voice's current one, as applyEngineSettings does), at the
# ends of their ranges (NVDA rate 0 and 100 give 50 and 400, pitch 50 and 200).
PARAM_PRESETS = [
	("min-params", {"SPEECHRATE": 50, "PITCH": 50, "VOLUME": 0, "WAITFACTOR": 0}),
	("max-params", {"SPEECHRATE": 400, "PITCH": 200, "VOLUME": 100, "WAITFACTOR": 9}),
]
PARAM_PIECES = ["text", "punct", "space", "bookmark", "spell-a", "zwsp"]
# The settings the inner driver keeps per voice (VOICE_PARAMETERS), restored afterwards.
PARAM_NAMES = ["VOICE_OPERATING_POINT", "SPEECHRATE", "PITCH", "VOLUME", "WAITFACTOR"]


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


def _libChoice(engine):
	"""The lib folder name the add-on's initialize() uses in this process, and why."""
	if engine == "VE":
		# ve2/__init__.py: os.environ["PROCESSOR_ARCHITECTURE"]; WOW64 sets it to x86.
		arch = os.environ.get("PROCESSOR_ARCHITECTURE", "")
		return arch, f"PROCESSOR_ARCHITECTURE={arch or '(unset)'}"
	# ttsapi/__init__.py: "x64" if sys.maxsize > 2**32 else "x32".
	return ("x64" if BITS == 64 else "x32"), f"sys.maxsize: {BITS}-bit"


def _resourcePaths(engine, workspace, addonsDir):
	_, folder, _, prefix = ENGINES[engine]
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
	"""The add-on's initialize(), with the lib folder the add-on would choose."""
	_, _, needsMsvcr, _ = ENGINES[engine]
	libName, rule = _libChoice(engine)
	libDir = os.path.join(engineDir, "lib", libName)
	if not libName or not os.path.isdir(libDir):
		raise SystemExit(
			f"{engine}: the add-on would load {libDir} ({rule}) in this {BITS}-bit Python, "
			"but it does not exist; check --workspace, or use a Python of the other bitness"
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


def _cases(engine):
	"""(label, text, stopAfter, counted) for one voice, in the order they are sent."""
	cases = [(label, text, None, engine in ENGINE_ONLY.get(label, {engine})) for label, text in PIECES]
	cases += [(label, text, None, False) for label, text in INFO_PIECES]
	cases.append((STOP_PIECE[0], STOP_PIECE[1], STOP_PIECE[2], False))
	cases += [(label, text, None, True) for label, text in AFTER_STOP_PIECES]
	return cases


def _paramIds(api):
	return [
		(getattr(api, f"VE_PARAM_{name}"), str if name == "VOICE_OPERATING_POINT" else int)
		for name in PARAM_NAMES
	]


def runEngine(engine, args):
	lines = []
	api = _loadPackage(engine, args.driver_dir)
	engineDir, resourcePaths = _resourcePaths(engine, args.workspace, args.addons_dir)
	libDir = _initialize(engine, api, engineDir, resourcePaths)
	libName, rule = _libChoice(engine)
	# Every result line carries this tag, so the 32-bit and 64-bit runs stay apart.
	tag = f"py{BITS} lib={libName}"
	names = _names(api)
	recorder = _Recorder(api)
	try:
		version = api.getProductVersion()
		versionText = f"{version.major}.{version.minor}.{version.maint}"
	except Exception as error:  # noqa: BLE001
		versionText = f"? ({error!r})"
	wow64 = os.environ.get("PROCESSOR_ARCHITEW6432")
	_log(
		lines,
		f"=== {engine} probe {time.strftime('%Y-%m-%d %H:%M:%S')} SDK {versionText} Python "
		f"{sys.version.split()[0]} {BITS}-bit lib {libName} ({rule}; "
		f"{'WOW64 on ' + wow64 if wow64 else 'native process'}) {libDir} ===",
	)
	_log(lines, f"resources: {resourcePaths}")
	counts = {}
	failures = []

	def record(verdict, line):
		counts[verdict] = counts.get(verdict, 0) + 1
		_log(lines, line)
		if verdict in ("FAIL", "WARN"):
			failures.append(line)

	def run(head, label, text, stopAfter, counted):
		try:
			call = _process(api, recorder, instance, text, stopAfter)
		except Exception as error:  # noqa: BLE001
			record("ERROR", f"[ERROR] {head} {label}: {error!r}")
			return
		verdict, status, ends = _verdict(api, call, counted)
		sameThread = call["threads"] <= {call["thread"]}
		record(
			verdict,
			f"[{verdict}] {head} {label} {status} endprocess={ends} audio={call['audioBytes']}B "
			f"sameThread={sameThread} msgs={_compress(call['messages'], names)}",
		)

	voices = _voices(api, set(args.voices or ()))
	if not voices:
		_log(lines, f"{engine}: no voices found")
	texts = dict(PIECES)
	instances = []
	try:
		for language, voice in voices:
			try:
				instance, opened = api.open(voice, recorder.native)
			except Exception as error:  # noqa: BLE001 - report and go on with the next voice
				record("ERROR", f"[ERROR] {engine} {tag} {voice} ({language}) open: {error!r}")
				continue
			instances.append(instance)
			head = f"{engine} {tag} {opened} ({language})"
			for label, text, stopAfter, counted in _cases(engine):
				run(head, label, text, stopAfter, counted)
			try:
				ids = _paramIds(api)
				saved = api.getParamList(instance, *ids)
			except Exception as error:  # noqa: BLE001
				record("ERROR", f"[ERROR] {head} read params: {error!r}")
				continue
			try:
				for preset, values in PARAM_PRESETS:
					settings = [(ids[0][0], saved[0])]
					settings += [(getattr(api, f"VE_PARAM_{name}"), value) for name, value in values.items()]
					try:
						api.setParamList(instance, *settings)
					except Exception as error:  # noqa: BLE001
						record("ERROR", f"[ERROR] {head} set {preset}: {error!r}")
						continue
					for label in PARAM_PIECES:
						run(head, f"{label}@{preset}", texts[label], None, True)
			finally:
				try:
					api.setParamList(instance, *((paramId, value) for (paramId, _), value in zip(ids, saved)))
				except Exception as error:  # noqa: BLE001
					record("ERROR", f"[ERROR] {head} restore params: {error!r}")
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
		f"=== {engine} summary ({BITS}-bit Python, lib {libName}): {len(voices)} voices, {counts}, "
		f"{len(recorder.stray)} callbacks outside a call ===",
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
	# The installed add-on looks for its SDKs in the folder next to its addons folder.
	parser.add_argument("--workspace", default=os.path.join(appdata, "nvda", "WorldVoice-workspace"))
	parser.add_argument("--addons-dir", default=os.path.join(appdata, "nvda", "addons"))
	parser.add_argument(
		"--driver-dir",
		default=os.path.normpath(repoDriverDir if os.path.isdir(repoDriverDir) else installedDriverDir),
		help="the add-on's synthDrivers/WorldVoice/driver folder",
	)
	parser.add_argument("--log", default=os.path.join(here, f"ve_endprocess_probe-{BITS}bit.log"))
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
