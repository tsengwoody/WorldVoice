import builtins
import ctypes
import importlib.util
import sys
import threading
import types
from pathlib import Path


class FakePlayer:
	def __init__(self, **kwargs):
		self.fed = []
		self.stops = 0
		self.idles = 0
		self.pauses = []
		self.closes = 0
		self.isPaused = False

	def feed(self, data):
		self.fed.append(data)

	def stop(self):
		self.stops += 1
		self.isPaused = False

	def idle(self):
		self.idles += 1

	def pause(self, switch):
		self.pauses.append(switch)
		self.isPaused = switch

	def close(self):
		self.closes += 1


def load_real_driver_with_native_stubs(monkeypatch, engine):
	root = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/driver"
	engine_path = root / engine
	native_name = "ve2" if engine == "VE" else "ttsapi"
	def module(name, **attributes):
		value = types.ModuleType(name)
		value.__dict__.update(attributes)
		monkeypatch.setitem(sys.modules, name, value)
		return value

	def package(name, path, **attributes):
		value = module(name, **attributes)
		value.__path__ = [str(path)]
		return value

	class Setting:
		def __init__(self, *args, **kwargs):
			pass

	class BaseSynthDriver:
		VoiceSetting = VariantSetting = RateSetting = RateBoostSetting = PitchSetting = VolumeSetting = Setting

		def __getattr__(self, name):
			for method in ("_get_" + name, "_get" + name[0].upper() + name[1:]):
				getter = getattr(type(self), method, None)
				if getter is not None:
					return getter(self)
			raise AttributeError(name)

	class LanguageInfo:
		def __init__(self, language):
			self.id = language
			self.displayName = language

	class VoiceInfo:
		def __init__(self, *args):
			self.id = args[0]
			self.displayName = args[1] if len(args) > 1 else self.id
			self.language = args[2] if len(args) > 2 else "en"

	class Command:
		pass

	class Notification:
		def notify(self, **kwargs):
			pass

	log = types.SimpleNamespace(
		debug=lambda *args, **kwargs: None,
		warning=lambda *args, **kwargs: None,
		error=lambda *args, **kwargs: None,
		debugWarning=lambda *args, **kwargs: None,
	)
	module("buildVersion", version_year=2024)
	module("config", conf={"audio": {"outputDevice": "fake"}})
	module("nvwave", WavePlayer=FakePlayer)
	module("languageHandler", getLanguageDescription=lambda language: language)
	module("addonHandler", initTranslation=lambda: None, getRunningAddons=lambda: [])
	package("speech", root, commands=None, CHUNK_SEPARATOR=" ")
	commands = module("speech.commands", **{name: type(name, (Command,), {}) for name in (
		"IndexCommand", "CharacterModeCommand", "LangChangeCommand", "PitchCommand",
		"BreakCommand", "SpeechCommand", "RateCommand", "VolumeCommand",
	)})
	sys.modules["speech"].commands = commands
	module("synthDriverHandler", SynthDriver=BaseSynthDriver, LanguageInfo=LanguageInfo,
		VoiceInfo=VoiceInfo, synthIndexReached=Notification(), synthDoneSpeaking=Notification())
	package("autoSettingsUtils", root)
	module("autoSettingsUtils.driverSetting", DriverSetting=Setting)
	module("autoSettingsUtils.utils", StringParameterInfo=Setting)
	module("logHandler", log=log)
	package("synthDrivers", root.parents[1])
	package("synthDrivers.WorldVoice", root.parent)
	from runtime_harness import load_runtime
	rt = load_runtime(monkeypatch, "synthDrivers.WorldVoice.runtime")
	package("synthDrivers.WorldVoice.driver", root, Voice=object,
		getVoiceKey=lambda engine, name: f"{engine}:{name}")
	module("synthDrivers.WorldVoice.driver.arabic_text", break_repeated_runs=lambda text: text)
	module("synthDrivers.WorldVoice.driver.chunker", split_speech_text_pieces=lambda text: [text])
	monkeypatch.setattr(builtins, "_", lambda value: value, raising=False)

	def load(name, path, is_package=False):
		spec = importlib.util.spec_from_file_location(
			name, path, submodule_search_locations=[str(path.parent)] if is_package else None,
		)
		loaded = importlib.util.module_from_spec(spec)
		monkeypatch.setitem(sys.modules, name, loaded)
		spec.loader.exec_module(loaded)
		return loaded

	original = load(f"synthDrivers.WorldVoice.driver.{engine}.driver",
		engine_path / "driver/__init__.py", True)
	wrapped = load(f"synthDrivers.WorldVoice.driver.{engine}", engine_path / "__init__.py", True)

	native = getattr(original, native_name)
	opened = []
	monkeypatch.setattr(native, "initialize", lambda resources: None)
	monkeypatch.setattr(native, "processText2Speech", lambda instance, text: None)
	callback_errors = threading.local()
	def process_native(instance, pointer):
		try:
			data = pointer.contents
			text = ctypes.string_at(data.szInText, data.cntTextLength).decode("utf-8")
			result = native.processText2Speech(instance, text)
			return result if isinstance(result, int) else native.veTypes.NUAN_OK
		except Exception as error:
			# ctypes Python callbacks cannot raise through C. Re-raise at
			# the caller's errcheck boundary, using thread-local ownership.
			callback_errors.error = error
			return 0xffffffff
	process_function = ctypes.CFUNCTYPE(ctypes.c_uint,
		native.veTypes.VE_HSAFE, ctypes.POINTER(native.veTypes.VE_INTEXT))(process_native)
	process_function.__name__ = "ve_ttsProcessText2Speech"
	def check_native_result(result, function, args):
		error = getattr(callback_errors, "error", None)
		if error is not None:
			del callback_errors.error
			raise error
		# Match the supplied binding: accepted statuses are mapped to
		# None by its real checker, rather than returned as integers.
		return native.veCheckForError(result, function, args)
	process_function.errcheck = check_native_result
	monkeypatch.setattr(native, "veDll", types.SimpleNamespace(ve_ttsProcessText2Speech=process_function,
		ve_ttsGetErrorString=lambda result: b"native error"))
	monkeypatch.setattr(native, "getLanguageList", lambda: [types.SimpleNamespace(
		szLanguageTLW=b"en", szLanguage=b"English")])
	monkeypatch.setattr(native, "getLocaleNameFromTLW", lambda value: "en")
	monkeypatch.setattr(native, "getVoiceList", lambda language: [types.SimpleNamespace(szVoiceName=b"fake")])
	def open_voice(voice, callback):
		instance = native.veTypes.VE_HSAFE()
		instance.pHandleData = len(opened) + 1
		opened.append((voice, instance, callback))
		return instance, voice
	monkeypatch.setattr(native, "open", open_voice)

	def new_core(missing=None, callback_proxy=None):
		if missing is None and callback_proxy is None:
			return wrapped.CancellableSynthDriver()
		def custom_init(self):
			initialize_native(self)
			if callback_proxy:
				self._veCallbackHandler = callback_proxy(self._veCallbackHandler)
			if missing:
				owner = self._veCallbackHandler if missing.startswith("callback.") or missing == "_feedBuf" else self
				field = missing.removeprefix("callback.")
				delattr(owner, field)
		initialize_native = getattr(wrapped.CancellableSynthDriver, "_initialize_native",
			original.SynthDriver.__init__)
		with monkeypatch.context() as patch:
			if hasattr(wrapped.CancellableSynthDriver, "_initialize_native"):
				patch.setattr(wrapped.CancellableSynthDriver, "_initialize_native", custom_init)
			else:
				patch.setattr(original.SynthDriver, "__init__", custom_init)
			return wrapped.CancellableSynthDriver()

	return types.SimpleNamespace(engine=engine, module=wrapped, original_driver=original,
		native=native, types=native.veTypes, rt=rt, opened=opened,
		new_core=new_core)
