import builtins
import importlib.util
import sys
import threading
import types
from pathlib import Path


class FakePlayer:
	def __init__(self):
		self.fed = []
		self.stops = 0
		self.idles = 0
		self.pauses = []
		self.closes = 0

	def feed(self, data):
		self.fed.append(data)

	def stop(self):
		self.stops += 1

	def idle(self):
		self.idles += 1

	def pause(self, switch):
		self.pauses.append(switch)

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

	class LanguageInfo:
		def __init__(self, language):
			self.id = language
			self.displayName = language

	class VoiceInfo:
		def __init__(self, *args):
			self.id = args[0]

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
	module("config", conf={})
	module("nvwave", WavePlayer=FakePlayer)
	module("languageHandler", getLanguageDescription=lambda language: language)
	module("addonHandler", initTranslation=lambda: None, getRunningAddons=lambda: [])
	package("speech", root, commands=None)
	module("speech.commands", **{name: type(name, (Command,), {}) for name in (
		"IndexCommand", "CharacterModeCommand", "LangChangeCommand", "PitchCommand",
		"BreakCommand", "SpeechCommand", "RateCommand", "VolumeCommand",
	)})
	module("synthDriverHandler", SynthDriver=BaseSynthDriver, LanguageInfo=LanguageInfo,
		VoiceInfo=VoiceInfo, synthIndexReached=Notification(), synthDoneSpeaking=Notification())
	package("autoSettingsUtils", root)
	module("autoSettingsUtils.driverSetting", DriverSetting=Setting)
	module("autoSettingsUtils.utils", StringParameterInfo=Setting)
	module("logHandler", log=log)
	package("synthDrivers", root.parents[1])
	package("synthDrivers.WorldVoice", root.parent)
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

	def fake_init(self):
		self._player = FakePlayer()
		self._isSilence = threading.Event()
		self._veCallbackHandler = original.VECallback(self._player, self._isSilence,
			self._onIndexReached)
		self._voice = "fake"
		self._instanceCache = {}

	monkeypatch.setattr(original.SynthDriver, "__init__", fake_init)

	def new_core(missing=None, callback_proxy=None):
		if missing is None and callback_proxy is None:
			return wrapped.CancellableSynthDriver()
		def custom_init(self):
			fake_init(self)
			if callback_proxy:
				self._veCallbackHandler = callback_proxy(self._veCallbackHandler)
			if missing:
				owner = self._veCallbackHandler if missing.startswith("callback.") or missing == "_feedBuf" else self
				field = missing.removeprefix("callback.")
				delattr(owner, field)
		with monkeypatch.context() as patch:
			patch.setattr(original.SynthDriver, "__init__", custom_init)
			return wrapped.CancellableSynthDriver()

	return types.SimpleNamespace(engine=engine, module=wrapped, original_driver=original,
		native=getattr(original, native_name), types=getattr(original, native_name).veTypes,
		new_core=new_core)
