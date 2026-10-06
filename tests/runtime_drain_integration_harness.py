"""Real runtime composition and wrappers over controllable native/audio ports.

The explicit quiescence promise applies only to these controlled native fakes.
It does not change a wrapper's production capability inspection.
"""

import importlib
import sys
from threading import Condition, Event
from types import ModuleType, SimpleNamespace

from onecore_drain_harness import ROOT, in_thread, load_onecore
from runtime_harness import MemoryRepository, load_runtime, load_scheduler
from worldvoice_cancel_wrapper_harness import emit, load_real_driver_with_native_stubs
from worldvoice_harness import EventStub

PACKAGE = "synthDrivers.WorldVoice"
ENGINES = ("OneCore", "VE", "Cerence")


class NativeCall:
	def __init__(self, instance, text, context, commands):
		self.instance, self.text = instance, text
		self.context, self.commands = context, commands
		self.release = Event()
		self.callback = None


class AudioBarrier:
	"""One actual player idle/sync invocation, released independently."""

	def __init__(self):
		self.release = Event()
		self.returned = Event()


class EngineControl:
	def __init__(self, env, engine, monkeypatch):
		self.env, self.engine = env, engine
		self.core = env.driver if engine == "OneCore" else env.core
		self.player = env.player if engine == "OneCore" else self.core._real_player
		self.condition = Condition()
		self.started = Event()
		self.calls, self.contexts, self.commands, self.sinks, self.applied = [], [], [], [], []
		self.idles, self.callbacks = [], []
		self.feed_entered, self.feed_release = Event(), Event()
		self.feed_release.set()
		self.closing = False
		original_feed = self.player.feed

		def feed(*args, **kwargs):
			self.feed_entered.set()
			assert self.feed_release.wait(4), "Audio feed was never released"
			return original_feed(*args, **kwargs)

		def idle():
			barrier = AudioBarrier()
			with self.condition:
				self.idles.append(barrier)
				if self.closing:
					barrier.release.set()
				self.condition.notify_all()
			assert barrier.release.wait(4), "Audio idle was never released"
			barrier.returned.set()

		original_stop = self.player.stop

		def stop():
			original_stop()
			for barrier in tuple(self.idles):
				barrier.release.set()

		monkeypatch.setattr(self.player, "feed", feed)
		monkeypatch.setattr(self.player, "idle", idle)
		if engine == "OneCore":
			monkeypatch.setattr(self.player, "sync", idle)
		monkeypatch.setattr(self.player, "stop", stop)
		original_segment = self.core.speak_segment

		def speak_segment(commands, token, *, context, on_event):
			with self.condition:
				self.contexts.append(context)
				self.commands.append(tuple(commands))
				self.sinks.append(on_event)
				self.condition.notify_all()
			return original_segment(commands, token, context=context, on_event=on_event)

		monkeypatch.setattr(self.core, "speak_segment", speak_segment)
		if engine == "OneCore":
			original_native = env.native.ocSpeech_speak.function

			def speak(token, text):
				original_native(token, text)
				self._start(token, text)

			monkeypatch.setattr(env.native.ocSpeech_speak, "function", speak)
		else:

			def speak(instance, text):
				call = self._start(instance, text)
				assert call.release.wait(4), "Vocalizer native result was never released"
				indexes = [
					command.index
					for command in call.commands
					if isinstance(command, self.env.commands.IndexCommand)
				]
				emit(env, instance, payload=b"pcm-tail", index=indexes[0]) if indexes else emit(
					env,
					instance,
					payload=b"pcm-tail",
				)

			monkeypatch.setattr(env.native, "processText2Speech", speak)

	def _start(self, instance, text):
		call = NativeCall(
			instance,
			text,
			self.contexts[-1] if self.contexts else None,
			self.commands[-1] if self.commands else (),
		)
		with self.condition:
			self.calls.append(call)
			if self.closing:
				call.release.set()
			self.started.set()
			self.condition.notify_all()
		return call

	def wait_call(self, number=1):
		with self.condition:
			assert self.condition.wait_for(lambda: len(self.calls) >= number, 2), (
				f"{self.engine} native call {number} did not start"
			)
			return self.calls[number - 1]

	def wait_idle(self, number=1):
		with self.condition:
			assert self.condition.wait_for(lambda: len(self.idles) >= number, 2), (
				f"{self.engine} player idle {number} did not start"
			)
			return self.idles[number - 1]

	def complete_native(self, number=1, *, frames=8):
		"""Release a native result, preserving real callback/feed ownership."""
		call = self.wait_call(number)
		if self.engine == "OneCore":
			indexes = [
				command.index
				for command in call.commands
				if isinstance(command, self.env.commands.IndexCommand)
			]
			markers = "|".join(f"{index}:{20000 if frames else 0}" for index in indexes)
			callback = in_thread(lambda: self.env.native.respond(frames=frames, markers=markers))
			call.callback = callback
			self.callbacks.append(callback)
		else:
			call.release.set()
		return call

	def tail(self, number=1, *, frames=8, idle_number=None):
		"""Native completes and all tail is fed, while actual audio stays busy."""
		self.complete_native(number, frames=frames)
		return self.wait_idle(number if idle_number is None else idle_number)

	def wait_contexts(self, count):
		with self.condition:
			assert self.condition.wait_for(lambda: len(self.contexts) >= count, 2)

	def release_all(self):
		self.closing = True
		self.feed_release.set()
		for call in tuple(self.calls):
			call.release.set()
		for barrier in tuple(self.idles):
			barrier.release.set()
		if self.engine == "OneCore":
			self.env.player.sync_release.set()


def assemble(monkeypatch, tmp_path, *, supported=True):
	# Clear cached Python boundaries so every test uses one models/commands graph.
	for name in tuple(sys.modules):
		if name.startswith(PACKAGE + "."):
			monkeypatch.delitem(sys.modules, name)
	synth_drivers = ModuleType("synthDrivers")
	synth_drivers.__path__ = [str(ROOT / "addon/synthDrivers")]
	monkeypatch.setitem(sys.modules, "synthDrivers", synth_drivers)
	package = ModuleType(PACKAGE)
	package.__path__ = [str(ROOT / "addon/synthDrivers/WorldVoice")]
	monkeypatch.setitem(sys.modules, PACKAGE, package)
	language = ModuleType("languageHandler")
	language.getLanguageDescription = lambda value: value
	monkeypatch.setitem(sys.modules, "languageHandler", language)
	rt = load_runtime(monkeypatch, PACKAGE + ".runtime")
	scheduler = load_scheduler(monkeypatch, rt)
	voice_base = importlib.import_module(PACKAGE + ".driver").Voice
	commands = ModuleType("speech.commands")

	class SpeechCommand:
		pass

	class IndexCommand(SpeechCommand):
		def __init__(self, index):
			self.index = index

		def __repr__(self):
			return f"IndexCommand({self.index})"

	class BreakCommand(SpeechCommand):
		def __init__(self, time):
			self.time = time

	class LangChangeCommand(SpeechCommand):
		def __init__(self, lang):
			self.lang = lang

	commands.SpeechCommand = commands.SynthCommand = SpeechCommand
	commands.SynthParamCommand = type("SynthParamCommand", (SpeechCommand,), {})
	commands.IndexCommand, commands.BreakCommand = IndexCommand, BreakCommand
	commands.LangChangeCommand = LangChangeCommand
	for name in ("CharacterModeCommand", "PitchCommand", "RateCommand", "VolumeCommand", "PhonemeCommand"):
		setattr(commands, name, type(name, (SpeechCommand,), {}))
	controls = {}
	controls["OneCore"] = EngineControl(
		load_onecore(
			monkeypatch,
			rt=rt,
			scheduler=scheduler,
			voice_base=voice_base,
			commands=commands,
		),
		"OneCore",
		monkeypatch,
	)
	for engine in ("VE", "Cerence"):
		env = load_real_driver_with_native_stubs(
			monkeypatch,
			engine,
			rt=rt,
			voice_base=voice_base,
			commands=commands,
			property_setters=True,
		)
		env.commands = commands
		parameters = {}

		def get_params(instance, *pairs, parameters=parameters, env=env):
			return [
				parameters.get(
					(instance.pHandleData, id),
					"en" if id == env.types.VE_PARAM_LANGUAGE else "default" if kind is str else 100,
				)
				for id, kind in pairs
			]

		def set_params(instance, *pairs, parameters=parameters):
			for id, value in pairs:
				parameters[(instance.pHandleData, id)] = value

		monkeypatch.setattr(env.native, "getParamList", get_params)
		monkeypatch.setattr(env.native, "setParamList", set_params)
		monkeypatch.setattr(env.native, "getSpeechDBList", lambda *args: ["default"])
		if engine == "VE":
			# A second VE voice lets a request switch voices within one engine.
			monkeypatch.setattr(
				env.native,
				"getVoiceList",
				lambda language: [
					SimpleNamespace(szVoiceName=b"fake"),
					SimpleNamespace(szVoiceName=b"fake2"),
				],
			)
		monkeypatch.setattr(env.native, "close", lambda *args: None)
		monkeypatch.setattr(env.native, "terminate", lambda: None)
		env.core = env.new_core()
		env.core._veCallbackHandler._ensureSonicStream = lambda: False
		controls[engine] = EngineControl(env, engine, monkeypatch)
	# Mocked NVDA setting descriptors and VoiceInfo supply realistic metadata.
	for engine, control in controls.items():
		outer = control.env.outer if engine == "OneCore" else control.env.module
		monkeypatch.setattr(
			outer.SynthDriver,
			"supportedSettings",
			[SimpleNamespace(id=name) for name in ("voice", "rate", "rateBoost", "pitch", "volume")],
			raising=False,
		)
		monkeypatch.setattr(outer.Voice, "create_core", classmethod(lambda cls, core=control.core: core))
		if engine != "OneCore":
			monkeypatch.setattr(control.core, "_confirm_native_quiescence", lambda native: None)

	handler = sys.modules["synthDriverHandler"]
	monkeypatch.setattr(
		handler,
		"VoiceInfo",
		lambda id, description, language: SimpleNamespace(id=id, description=description, language=language),
	)
	monkeypatch.setattr(sys.modules["languageHandler"], "getLanguage", lambda: "en", raising=False)
	config = sys.modules["config"]
	config.conf["WorldVoice"] = {
		"autoLanguageSwitching": {
			"KeepMainLocaleEngineConsistent": False,
			"KeepMainLocaleParameterConsistent": False,
		},
		"engine": {},
		"role": {},
	}
	engine_classes = {
		name: (controls[name].env.outer if name == "OneCore" else controls[name].env.module).Voice
		for name in ENGINES
		if name in controls
	}
	manager_module = importlib.import_module(PACKAGE + ".voiceManager")
	ledger = importlib.import_module(PACKAGE + ".indexLedger").IndexLedger()
	bridge_type = importlib.import_module(PACKAGE + ".nvdaEventBridge").NvdaEventBridge
	output = SimpleNamespace(indexes=[], dones=[], drains=[], timeline=[], condition=Condition())
	owner = object()

	def index_seen(synth, index):
		if synth is owner:
			with output.condition:
				output.indexes.append(index)
				output.timeline.append(("index", index))
				output.condition.notify_all()

	def done_seen(synth):
		if synth is owner:
			with output.condition:
				output.dones.append(synth)
				output.timeline.append(("done", None))
				output.condition.notify_all()

	done, index = EventStub(done_seen), EventStub(index_seen)
	# The loaded wrappers retain different NVDA Notification objects; reconnect
	# each hardware notification to the same production event bridge.
	for control in controls.values():
		wrapper = control.env.outer if control.engine == "OneCore" else control.env.original_driver
		monkeypatch.setattr(wrapper.synthIndexReached, "notify", index.notify)
		monkeypatch.setattr(wrapper.synthDoneSpeaking, "notify", done.notify)
	bridge = bridge_type(
		owner,
		done_event=done,
		index_event=index,
		get_synth=lambda: owner,
		index_ledger=ledger,
	)
	tasks = scheduler.TaskManager(bridge)
	bridge.start(tasks.on_event, batch_handler=tasks.on_events)
	original_sink = bridge.segment_sink

	def segment_sink(source, context):
		sink = original_sink(source, context)

		def receive(event):
			output.drains.append(event)
			output.timeline.append(("drain", event.segment_id))
			sink(event)

		return receive

	monkeypatch.setattr(bridge, "segment_sink", segment_sink)
	repo = MemoryRepository()
	store = rt.settings.VoiceSettingsStore(repo)

	def completion_for(cls, core):
		if supported and cls.drain_profile is not None:
			# Explicit fake-native callback exclusion evidence, not certification
			# of any installed SDK or physical Windows playback profile.
			return rt.models.CompletionContract(rt.models.CompletionMode.DRAIN, rt.models.IndexRange(1, 9999))
		# Exercise the generic fallback independently of the wrappers' own
		# drain support checks.
		return rt.models.CompletionContract()

	manager = manager_module.VoiceManager(
		tasks,
		store,
		bridge,
		index_ledger=ledger,
		completion_for=completion_for,
		engine_classes=engine_classes,
		conf_provider=lambda: config.conf,
		get_language=lambda: "en",
	)
	builder = importlib.import_module(PACKAGE + ".runtime.requestBuilder")
	for name, control in controls.items():
		session = manager.resolve_playback(next(spec.name for spec in manager.table if spec.engine == name))
		control.session = session
		original_apply = session._adapter.apply

		def apply(spec, snapshot, control=control, original=original_apply):
			control.applied.append(snapshot)
			return original(spec, snapshot)

		monkeypatch.setattr(session._adapter, "apply", apply)
	return DrainComposition(
		rt,
		scheduler,
		commands,
		controls,
		manager,
		tasks,
		output,
		bridge,
		ledger,
		builder,
		store,
	)


class DrainComposition:
	def __init__(
		self,
		rt,
		scheduler,
		commands,
		controls,
		manager,
		tasks,
		output,
		bridge,
		ledger,
		builder,
		store,
	):
		self.rt, self.scheduler, self.commands = rt, scheduler, commands
		self.controls, self.manager, self.tasks = controls, manager, tasks
		self.output, self.bridge, self.ledger = output, bridge, ledger
		self.builder, self.store = builder, store

	def key(self, engine):
		return next(spec.name for spec in self.manager.table if spec.engine == engine)

	def submit(self, sequence, engine="OneCore"):
		requests = []
		original = self.tasks.new_request

		def new_request():
			request = original()
			requests.append(request)
			return request

		self.tasks.new_request = new_request
		try:
			assert self.builder.queue_speech_sequence(
				self.tasks,
				sequence,
				self.key(engine),
				self.manager.resolve_playback,
			)
		finally:
			self.tasks.new_request = original
		assert len(requests) == 1
		return requests[0]

	def wait_done(self, count=1):
		with self.output.condition:
			assert self.output.condition.wait_for(lambda: len(self.output.dones) >= count, 2)

	def close(self):
		for control in self.controls.values():
			control.release_all()
		# Consume outstanding fixed OneCore responses before native shutdown.
		onecore = self.controls["OneCore"]
		if onecore.core._segmentNative is not None:
			onecore.env.native.respond(failure=True)
		self.tasks.shutdown(self.manager.playback_ports)
		self.bridge.close()
		self.manager.terminate(commit=False)
		self.ledger.close()
		for control in self.controls.values():
			for callback in control.callbacks:
				assert callback.done.wait(2)
				assert callback.errors == []
