"""Load the pure runtime without executing the WorldVoice/NVDA entry point."""

import builtins
import importlib
import importlib.util
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Condition, Event
from types import SimpleNamespace
from typing import TYPE_CHECKING

from addon_loader import WORLDVOICE, alias_package, load_source
from waiting import WAIT_TIMEOUT

if TYPE_CHECKING:
	from addon.synthDrivers.WorldVoice.runtime.scheduler import SpeechRequest


RUNTIME = WORLDVOICE / "runtime"
PACKAGE = "worldvoice_runtime_test"


def load_runtime(monkeypatch, package_name=PACKAGE):
	def load(name, path):
		return load_source(monkeypatch, name, path)

	package = load(package_name, RUNTIME / "__init__.py")
	models = load(f"{package_name}.models", RUNTIME / "models.py")
	voice_settings = load(f"{package_name}.voiceSettings", RUNTIME / "voiceSettings.py")
	session = load(f"{package_name}.session", RUNTIME / "session.py")
	playback_work = load(f"{package_name}.playbackWork", RUNTIME / "playbackWork.py")
	return SimpleNamespace(
		package=package,
		models=models,
		voice_settings=voice_settings,
		session=session,
		playback_work=playback_work,
	)


def load_scheduler(monkeypatch, rt):
	return load_source(monkeypatch, f"{rt.package.__name__}.scheduler", RUNTIME / "scheduler.py")


class RecordingOutput:
	def __init__(self):
		self.indexes = []
		self.done_count = 0
		self.condition = Condition()

	def index_reached(self, index):
		with self.condition:
			self.indexes.append(index)
			self.condition.notify_all()

	def done_speaking(self):
		with self.condition:
			self.done_count += 1
			self.condition.notify_all()

	def wait_done(self, timeout=WAIT_TIMEOUT, count=1):
		with self.condition:
			self.condition.wait_for(lambda: self.done_count >= count, timeout)
			return self.done_count


def make_spec(key="Fake:a", language="en"):
	engine, voice_id = key.split(":", 1)
	return sys.modules[f"{PACKAGE}.models"].VoiceSpec(
		voice_id,
		key,
		f"Voice {voice_id}",
		language,
		engine,
		language,
	)


class MemoryRepository:
	def __init__(self):
		self.values = {}
		self.loads = []
		self.saves = []
		self.fail_next_save = False
		self.before_save = None

	def load(self, spec):
		self.loads.append(spec.name)
		return self.values.get(spec.name, {}).copy()

	def save(self, spec, values):
		self.saves.append((spec.name, dict(values)))
		if self.before_save is not None:
			self.before_save(spec, values)
		if self.fail_next_save:
			self.fail_next_save = False
			raise OSError("Save failed")
		self.values[spec.name] = dict(values)


class FakeAdapter:
	"""An observable engine boundary with explicit blocking/failure hooks."""

	def __init__(self, capabilities=None, voices=(), voice_variants=None):
		self.notificationSource = object()
		self.capabilities = capabilities
		self.voices = voices
		self.voice_variants = voice_variants or {}
		self.applied = []
		self.spoken = []
		self.contexts = []
		self.finished = []
		self.paused = []
		self.open_count = 0
		self.close_count = 0
		self.cancel_count = 0
		self.cancel_entered = Event()
		self.before_apply = None
		self.before_speak = None
		self.open_error = None
		self.close_error = None

	def open(self):
		self.open_count += 1
		if self.open_error is not None:
			raise self.open_error

	def close(self):
		self.close_count += 1
		if self.close_error is not None:
			raise self.close_error

	def listVoices(self):
		return self.voices

	def variants(self, key):
		return self.voice_variants.get(key, ())

	def apply(self, spec, snapshot):
		self.applied.append((spec, snapshot))
		if self.before_apply is not None:
			self.before_apply(spec, snapshot)

	def speak(self, commands, token, *, context=None):
		self.contexts.append(context)
		self.spoken.append((commands, token))
		if self.before_speak is not None:
			self.before_speak(commands, token)

	def finish_segment(self, context):
		self.finished.append(context)

	def cancel(self):
		self.cancel_count += 1
		self.cancel_entered.set()

	def pause(self, switch):
		self.paused.append(switch)


class FakePlayback(FakeAdapter):
	"""Pure playback port; hooks run at the actual engine-call boundary."""

	def __init__(self, completion=None):
		super().__init__()
		self.source_id = object()
		self.completion = completion or sys.modules[f"{PACKAGE}.models"].CompletionContract()
		self.activated = []
		self.on_activate = None
		self.on_speak = None
		self.on_cancel = None
		self.entered = Event()

	def activate(self, key):
		self.activated.append(key)
		if self.on_activate:
			self.on_activate()
		return True

	def speak(self, commands, token, *, context=None):
		super().speak(commands, token, context=context)
		self.entered.set()
		if self.on_speak:
			self.on_speak()

	def cancel(self):
		super().cancel()
		if self.on_cancel:
			self.on_cancel()


def load_settings_repository(monkeypatch, rt):
	# Supply only the package namespace: never execute the NVDA entry point.
	package_name = "worldvoice_repository_test"
	alias_package(monkeypatch, package_name, RUNTIME.parent)
	monkeypatch.setitem(sys.modules, f"{package_name}.runtime", rt.package)
	monkeypatch.setitem(sys.modules, f"{package_name}.runtime.models", rt.models)
	monkeypatch.setitem(sys.modules, f"{package_name}.runtime.voiceSettings", rt.voice_settings)
	return load_source(
		monkeypatch,
		f"{package_name}.voices.settingsRepository",
		RUNTIME.parent / "voices/settingsRepository.py",
	)


@contextmanager
def forbid_legacy_runtime_imports(monkeypatch):
	"""Reject old boundaries even when another test already cached a module."""
	forbidden = {
		"driver",
		"synthDrivers",
		"config",
		"synthDriverHandler",
		"logHandler",
		"languageHandler",
		"speech",
		"globalVars",
		"addonHandler",
		"gui",
		"nvwave",
		"winKernel",
		"api",
		"NVDA",
		"nvda",
	}

	# bridge/ is the legacy boundary, except the ledger and the NVDA event bridge: both are pure
	# Python, and a native engine uses them too. The names they had before phase 36 (root
	# indexLedger and nvdaEventBridge, compat/) no longer exist, so they need no rule.
	bridge_allowed = {"indexLedger", "nvdaEvents"}

	def check(name):
		parts = name.split(".")
		if forbidden.intersection(parts) or ("bridge" in parts and bridge_allowed.isdisjoint(parts)):
			raise AssertionError(f"Forbidden runtime dependency: {name}")

	original_import = builtins.__import__
	original_import_module = importlib.import_module

	def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
		# A relative import names only the sibling ("voiceFacade"); check where it resolves to.
		if level and globals and globals.get("__package__"):
			check(importlib.util.resolve_name("." * level + name, globals["__package__"]))
		else:
			check(name)
		for item in fromlist or ():
			check(item)
		return original_import(name, globals, locals, fromlist, level)

	def guarded_import_module(name, package=None):
		check(name)
		return original_import_module(name, package)

	with monkeypatch.context() as guard:
		guard.setattr(builtins, "__import__", guarded_import)
		guard.setattr(importlib, "import_module", guarded_import_module)
		yield


class ContractCore:
	"""Only the hardware/event source is fake; runtime ownership stays real."""

	def __init__(self):
		self.open_count = self.close_count = self.cancel_count = 0
		self.spoken = []
		self.entered = Event()
		self.complete_synchronously = True
		self.emit = None
		self.apply_count = 0
		self.segment_ids = []
		self.internal_wire_indexes = []
		self.wire_indexes = []
		self.marker_mode = False
		self.end_only = False

	def speak(self, commands):
		self.spoken.append(
			(
				commands,
				self.voice,
				self.language,
				self.rate,
				self.pitch,
				self.volume,
			),
		)
		if self.marker_mode:
			self.internal_wire_indexes.extend(
				command.index for command in commands if isinstance(command, self.marker_type)
			)
			self.wire_indexes.extend(
				command.index for command in commands if isinstance(getattr(command, "index", None), int)
			)
		self.entered.set()
		if self.complete_synchronously and self.marker_mode:
			indexes = (
				[commands[-1].index]
				if self.end_only
				else [
					command.index for command in commands if isinstance(getattr(command, "index", None), int)
				]
			)
			for index in indexes:
				self.emit("INDEX", index)
				self.emit("INDEX", index)
			self.emit("DONE")
		elif self.complete_synchronously:
			self.emit("INDEX", 7)
			self.emit("INDEX", 7)
			self.emit("DONE")
			self.emit("DONE")
			self.emit("INDEX", 8)

	def cancel(self):
		self.cancel_count += 1

	def pause(self, switch):
		pass


def assemble_adapter_contract(monkeypatch, adapter_kind, *, completion_mode="LEGACY_DONE", commands=None):
	"""Use the identical production Store, Session and scheduler for both ports.

	The caller installs the native import guard before calling this function
	and keeps it installed through worker/session teardown.
	"""
	rt = load_runtime(monkeypatch, "worldvoice_contract_runtime")
	scheduler = load_scheduler(monkeypatch, rt)
	voices = tuple(
		rt.models.VoiceSpec(
			key,
			"Contract:" + key,
			key,
			language,
			"Contract",
			language,
		)
		for key, language in (("a", "en"), ("b", "zh_TW"))
	)
	core = ContractCore()
	core.marker_mode = completion_mode != "LEGACY_DONE"
	completion = rt.models.CompletionContract(
		rt.models.CompletionMode[completion_mode],
		rt.models.IndexRange(501, 516) if core.marker_mode else None,
	)
	# Ledger is pure Python; native may use it without importing any legacy boundary.
	name = "worldvoice_contract_boundary"
	alias_package(monkeypatch, name, RUNTIME.parent)
	for suffix, module in (
		("", rt.package),
		(".models", rt.models),
		(".voiceSettings", rt.voice_settings),
		(".session", rt.session),
	):
		monkeypatch.setitem(sys.modules, name + ".runtime" + suffix, module)
	for suffix in (
		"bridge",
		"bridge.indexLedger",
		"bridge.nvdaEvents",
		"bridge.engineAdapter",
		"bridge.indexCodec",
		"speechCommands",
	):
		monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
	ledger = importlib.import_module(name + ".bridge.indexLedger").IndexLedger()

	@dataclass
	class NativeIndex:
		index: int

	class NativeMarker(NativeIndex):
		pass

	core.marker_type = NativeMarker
	index_command = commands.IndexCommand if commands is not None else NativeIndex
	supported = frozenset({"rate", "pitch", "volume"})
	if adapter_kind == "native":

		class NativeAdapter:
			notificationSource = core
			capabilities = rt.models.EngineCapabilities(supported, completion=completion)

			def open(self):
				core.open_count += 1

			def close(self):
				core.close_count += 1

			def listVoices(self):
				return voices

			def variants(self, key):
				return ()

			def apply(self, spec, snapshot):
				core.apply_count += 1
				core.voice, core.language = spec.id, snapshot.language
				core.rate, core.pitch, core.volume = snapshot.rate, snapshot.pitch, snapshot.volume

			def speak(self, commands, token, *, context=None):
				core.segment_ids.append(context.segment_id)
				if core.marker_mode:
					originals = tuple(
						command.index for command in commands if isinstance(command, NativeIndex)
					)
					if any(not isinstance(index, int) for index in originals):
						raise ValueError("Index command requires an integer")
					allocation = ledger.prepare(context, originals)
					indexes = iter(allocation.wireIndexes)
					# As bridge/indexCodec.py: a segment without wire indexes is sent without its indexes.
					commands = tuple(
						NativeIndex(next(indexes)) if isinstance(command, NativeIndex) else command
						for command in commands
						if allocation.wireIndexes or not isinstance(command, NativeIndex)
					) + (NativeMarker(allocation.endIndex),)
				if not token.is_cancelled():
					core.speak(commands)

			def finish_segment(self, context):
				ledger.retireSegment(context)

			def cancel(self):
				core.cancel()

			def pause(self, switch):
				core.pause(switch)

		adapter = NativeAdapter()
	elif adapter_kind == "legacy":
		legacy = importlib.import_module(name + ".bridge.engineAdapter")
		if core.marker_mode:
			core.marker_type = importlib.import_module(name + ".speechCommands").WorldVoiceIndexCommand

		class LegacyVoice:
			@classmethod
			def createCore(cls):
				core.open_count += 1
				return core

			@classmethod
			def destroyCore(cls, target):
				core.close_count += 1

			@classmethod
			def supportedSettings(cls):
				return supported

			@classmethod
			def voices(cls, target):
				return [vars(spec) for spec in voices]

			def applyEngineSettings(self, target, snapshot):
				core.apply_count += 1
				target.language = snapshot.language

			variants = ()

		cached = {spec.name: LegacyVoice() for spec in voices}
		adapter = legacy.VoiceClassAdapter(
			LegacyVoice,
			cached.__getitem__,
			indexLedger=ledger,
			completion=completion,
		)
		original_speak = adapter.speak

		def record_context(commands, token, *, context=None):
			core.segment_ids.append(context.segment_id)
			return original_speak(commands, token, context=context)

		adapter.speak = record_context
	else:
		raise ValueError(adapter_kind)
	repo = MemoryRepository()
	store = rt.voice_settings.VoiceSettingsStore(repo)
	session = rt.session.EngineSession(adapter, store)
	session.open()
	for spec in adapter.listVoices():
		store.ensure(spec)
	output = RecordingOutput()
	tasks = scheduler.TaskManager(output)
	bridge = None
	if core.marker_mode and adapter_kind == "legacy":

		class EventSource:
			def __init__(self):
				self.handlers = []

			def register(self, handler):
				self.handlers.append(handler)

			def unregister(self, handler):
				self.handlers.remove(handler)

			def notify(self, **kwargs):
				for handler in tuple(self.handlers):
					handler(**kwargs)

		done, index_event = EventSource(), EventSource()
		bridge_type = importlib.import_module(name + ".bridge.nvdaEvents").NvdaEventBridge
		bridge = bridge_type(
			output,
			doneEvent=done,
			indexEvent=index_event,
			getSynth=lambda: output,
			indexLedger=ledger,
		)
		bridge.start(tasks.on_event, batchHandler=tasks.on_events)
		bridge.bind(core, session.source_id, completion=completion)

		def emit(kind, index=None):
			if kind == "INDEX":
				index_event.notify(synth=core, index=index)
			else:
				done.notify(synth=core)

		core.emit = emit
	elif core.marker_mode:
		ledger.bind(core, session.source_id, completion)

		def emit(kind, index=None):
			if kind == "INDEX":
				tasks.on_events(lambda: ledger.receiveIndex(session.source_id, index))
			else:
				tasks.on_event(rt.models.PlaybackEvent(rt.models.EventKind[kind], session.source_id))

		core.emit = emit
	else:
		core.emit = lambda kind, index=None: tasks.on_event(
			rt.models.PlaybackEvent(
				rt.models.EventKind[kind],
				session.source_id,
				index,
			),
		)
	monkeypatch.delitem(sys.modules, rt.package.__name__ + ".requestBuilder", raising=False)
	builder = importlib.import_module(rt.package.__name__ + ".requestBuilder")
	return SimpleNamespace(
		rt=rt,
		scheduler=scheduler,
		core=core,
		repo=repo,
		store=store,
		session=session,
		tasks=tasks,
		output=output,
		bridge=bridge,
		ledger=ledger,
		index_command=index_command,
		builder=builder,
	)


def submit_contract_request(c, sequence, *, default_key: str) -> "SpeechRequest":
	"""Observe the production builder's request without changing its lifecycle."""
	requests = []
	original = c.tasks.new_request

	def new_request():
		request = original()
		requests.append(request)
		return request

	c.tasks.new_request = new_request
	try:
		assert c.builder.queue_speech_sequence(
			c.tasks,
			sequence,
			default_key,
			lambda key: c.session if key in {"Contract:a", "Contract:b"} else None,
		)
	finally:
		c.tasks.new_request = original
	assert len(requests) == 1
	return requests[0]


def load_index_support(monkeypatch, rt, package_name):
	"""Load real ledger/commands into an isolated addon namespace."""
	if package_name not in sys.modules:
		alias_package(monkeypatch, package_name, RUNTIME.parent)
	monkeypatch.setitem(sys.modules, package_name + ".runtime", rt.package)
	monkeypatch.setitem(sys.modules, package_name + ".runtime.models", rt.models)
	for suffix in ("bridge.indexLedger", "speechCommands", "bridge.indexCodec"):
		monkeypatch.delitem(sys.modules, package_name + "." + suffix, raising=False)
	return SimpleNamespace(
		package=package_name,
		ledger=importlib.import_module(package_name + ".bridge.indexLedger"),
		commands=importlib.import_module(package_name + ".speechCommands"),
	)


# Named views of runtime internals. Tests check these where no public API shows the fact
# (a leaked request, an operation never retired, a worker thread that died); each private
# name is read here only, so renaming it touches this module alone. Most read without a
# lock, as the tests did, because a test may hold the system mid-way with that lock taken;
# collections come back as copies, which the GIL makes atomic. Those that replaced a wait
# under the owner's condition read under it.


def tracked_requests(manager):
	"""The requests the scheduler still tracks; finished, failed and cancelled ones must leave."""
	return dict(manager._requests)


def worker_queue_empty(manager):
	"""Whether no task waits for the scheduler's worker thread."""
	return manager._q.empty()


def worker_alive(manager):
	"""Whether the scheduler's worker thread still runs."""
	return manager._thread.is_alive()


def done_signalled(manager):
	"""Whether the worker was told that its current task finished."""
	return manager._current_done_event.is_set()


def accepted_indexes(manager):
	"""The indexes the scheduler accepted for its current request."""
	with manager._state_cond:
		return set(manager._current_indexes)


def segment_host(driver):
	"""The SegmentHost an engine wrapper runs its segments on."""
	return driver._segmentHost


def segment_lifecycle(host):
	"""The SegmentLifecycle inside a SegmentHost."""
	return host._lifecycle


def accepted_operations(host):
	"""Accepted operations the host still tracks, mapped to whether it cancelled them."""
	return dict(host._accepted)


def pending_records(host):
	"""Native records queued behind the current one."""
	return tuple(host._pending)


def native_record(host, operation):
	"""The NativeRecord the host created for an accepted segment operation."""
	return host._records[operation]


def live_operations(lifecycle):
	"""Operations the lifecycle has not retired yet."""
	return tuple(lifecycle._operations)


def queued_deliveries(lifecycle):
	"""Operations whose event still waits for the delivery thread."""
	return tuple(lifecycle._delivery_queue)


def delivery_thread(lifecycle):
	"""The thread that runs the lifecycle's sinks."""
	return lifecycle._delivery_thread


def resource_busy(lifecycle):
	"""Whether an operation owns the native resource."""
	return lifecycle._resource_busy


def lifecycle_terminated(lifecycle):
	"""Whether terminate() has shut the lifecycle."""
	with lifecycle._condition:
		return lifecycle._terminated


def still_admitting(lifecycle, operation):
	"""Whether ``operation`` still admits producers (it has not passed its native boundary)."""
	with lifecycle._condition:
		return operation._admitting


def waiting_for_resource(lifecycle, operation):
	"""Whether ``operation`` waits for the resource inside run()."""
	with lifecycle._condition:
		return operation._waiting


def stop_completion(operation):
	"""The event a cancelled operation sets once its native stop finished, or None before it."""
	with operation._lifecycle._condition:
		return operation._stop_done


def lifecycle_hooks(lifecycle):
	"""The engine hooks the lifecycle calls (the SegmentHost that owns it)."""
	return lifecycle._hooks
