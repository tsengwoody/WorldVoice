"""WorldVoice's context-aware boundary around the vendored RHVoice worker."""

import weakref
from dataclasses import dataclass
from threading import Condition, RLock

from synthDrivers.WorldVoice.driver import Voice as BaseVoice

from ...runtime.engineControl import StopGate
from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import DrainProfile, DrainSupport, runtime_profile, unverified_drain_support
from ...runtime.segmentHost import LeasedPlayer, NativeStrategy, SegmentDrainCore, SegmentHost
from ...runtime.session import CancellationView
from . import driver as rhvoice


@dataclass(eq=False)
class _RHVoiceMessage:
	"""RHVoice data carried on a NativeRecord: its callback identity and library."""

	identity: int
	library: "_NativeLibrary | None" = None


class _RHVoiceInner:
	"""The vendored RHVoice SynthDriver's name-mangled state this wrapper uses.

	The inner driver stays unmodified; every access to its private names goes
	through here, so an update of the vendored driver is checked in one place.
	"""

	CALLBACK_NAMES = frozenset(
		{
			"_SynthDriver__sample_rate_callback",
			"_SynthDriver__speech_callback",
			"_SynthDriver__mark_callback",
			"_SynthDriver__done_callback",
		},
	)
	DONE_CALLBACK = "_SynthDriver__done_callback"

	def __init__(self, driver):
		self._driver = weakref.ref(driver)

	@property
	def player(self):
		return self._driver()._SynthDriver__player

	@property
	def lib(self):
		return self._driver()._SynthDriver__lib

	@property
	def ttsEngine(self):
		return self._driver()._SynthDriver__tts_engine

	@ttsEngine.setter
	def ttsEngine(self, value):
		self._driver()._SynthDriver__tts_engine = value

	@property
	def ttsQueue(self):
		return self._driver()._SynthDriver__tts_queue

	@property
	def ttsThread(self):
		return self._driver()._SynthDriver__tts_thread

	@property
	def cancelFlag(self):
		return self._driver()._SynthDriver__cancel_flag

	@property
	def profile(self):
		return self._driver()._SynthDriver__profile

	@property
	def rate(self):
		return self._driver()._SynthDriver__rate

	@property
	def pitch(self):
		return self._driver()._SynthDriver__pitch

	@property
	def volume(self):
		return self._driver()._SynthDriver__volume

	@property
	def rateBoost(self):
		return self._driver()._SynthDriver__rate_boost


class _NativeCallback:
	"""Preserve the inner callback's public state, including lastIndex."""

	def __init__(self, owner, callback, isDone):
		self._owner = weakref.ref(owner)
		self._callback = callback
		self._isDone = isDone

	def __getattr__(self, name):
		return getattr(self._callback, name)

	def __call__(self, *args):
		owner = self._owner()
		if owner is None:
			# The C library may call back after the driver was collected.
			return None if self._isDone else 0
		return owner._nativeCallback(self._callback, self._isDone, *args)


class _NativeLibrary:
	"""Observe synchronous native outcomes that SpeakText does not inspect."""

	def __init__(self, host, native, record):
		self._host = host
		self._native = native
		self._record = record
		self._message = None

	def __getattr__(self, name):
		return getattr(self._native, name)

	def RHVoice_new_message(self, *args):
		host = self._host
		try:
			message = self._native.RHVoice_new_message(*args[:-1], self._record.native.identity)
			self._message = message
			if message:
				host.reach(self._record, "message")
			else:
				host.record_error(self._record, RuntimeError("RHVoice did not create a message"))
			return message
		except Exception as error:
			host.record_error(self._record, error)
			raise

	def RHVoice_speak(self, message):
		host = self._host
		try:
			result = self._native.RHVoice_speak(message)
			if not result:
				host.record_error(self._record, RuntimeError("RHVoice synthesis failed"))
			else:
				host.reach(self._record, "returned")
			return result
		except Exception as error:
			host.record_error(self._record, error)
			raise

	def RHVoice_delete_message(self, message):
		# SpeakText invokes this before its outer task can join callbacks.
		# Defer the real delete until every admitted native/audio consumer exits.
		return None

	def cleanup(self):
		if self._message:
			try:
				self._native.RHVoice_delete_message(self._message)
				self._message = None
			except Exception as error:
				# The native message may still own resources after a failed delete.
				# Stop reusing this engine and player, even if stop succeeds.
				self._host.latch_control_error(error)
				raise


class _WavePlayer(LeasedPlayer):
	"""Keep a queued index callback tied to its originating native message."""

	def __init__(self, host, player):
		super().__init__(host, player)

	def feed(self, data, onDone=None):
		host = self._host
		bound = host.callback_record()
		if bound is None:
			return None
		with host.consumer(bound) as record:
			if record is None:
				return None
			return self._feed_admitted(record, data, None, onDone)

	def _callback(self, record, onDone):
		host = self._host

		def indexDone():
			# The worker's final idle may release this after the native gate closes.
			with host.consumer(record, audio=True) as admitted:
				if admitted is None:
					return
				with host.bound_callback(record):
					try:
						onDone()
					except Exception as error:  # noqa: BLE001 - recorded on the record; the segment fails
						host.record_error(record, error)

		return indexDone

	def idle(self):
		host = self._host
		record = host.callback_record()
		try:
			return self._player.idle()
		except Exception as error:
			host.record_error(record, error)
			raise


class _QueuedSpeech:
	"""One record's turn on the RHVoice worker: native task, final idle, cleanup."""

	def __init__(self, owner, record, task):
		self._owner = weakref.ref(owner)
		self._record = record
		self._task = task

	def __call__(self):
		owner = self._owner()
		if owner is None:
			return
		host = owner._segmentHost
		record = self._record
		with owner._segmentCondition:
			owner._segmentCondition.wait_for(lambda: record.closed or owner._stopGate.clear)
			if record.closed:
				# NVDA cancel already abandoned this queued record.
				return
			host.begin(record)
		try:
			if record.is_valid() and host.control_error is None:
				with host.bound_callback(record):
					self._task()
		except Exception as error:  # noqa: BLE001 - recorded on the record; the segment fails
			host.record_error(record, error)
		# Stop new native callbacks, but let admitted ones finish their player
		# work before the final idle.
		host.close(record)
		host.wait_consumers(record)
		if (
			record.barriers["done"]
			and record.barriers["returned"]
			and record.is_valid()
			and record.error is None
			and host.control_error is None
		):
			try:
				owner._inner.player.idle()
				host.reach(record, "idle")
			except Exception as error:  # noqa: BLE001 - recorded on the record; the segment fails
				host.record_error(record, error)
		host.retire(record, finish=record.native.library.cleanup)
		with owner._segmentCondition:
			owner._segmentById.pop(record.native.identity, None)
		if record.operation is not None:
			owner._inner.cancelFlag.clear()
		else:
			host.forget(record)


class _RHVoiceStrategy(NativeStrategy):
	"""RHVoice's native queue: the inner tts queue and its single worker."""

	barriers = frozenset({"message", "done", "returned", "idle"})

	def __init__(self, driver):
		self._driver = weakref.ref(driver)

	def submit(self, host, record, commands):
		driver = self._driver()
		with driver._segmentCondition:
			identity = driver._segmentNextId
			driver._segmentNextId += 1
			record.native = _RHVoiceMessage(identity)
			driver._segmentById[identity] = record
		try:
			converter = rhvoice.SsmlConverter(driver, driver.language)
			text = converter.convertToXml(commands)
			inner = driver._inner
			library = record.native.library = _NativeLibrary(host, inner.lib, record)
			task = rhvoice.SpeakText(library, inner.ttsEngine, text, inner.cancelFlag, inner.player)
			task.set_voice_profile(inner.profile)
			task.set_rate(inner.rate)
			task.set_pitch(inner.pitch)
			task.set_volume(inner.volume)
			task.configure_rate_boost(inner.rateBoost)
			inner.ttsQueue.put(_QueuedSpeech(driver, record, task))
		except Exception:
			with driver._segmentCondition:
				driver._segmentById.pop(identity, None)
			raise

	def stop_native(self, host, record):
		driver = self._driver()
		driver._inner.cancelFlag.set()
		driver._inner.player.stop()

	def stop_player(self, host):
		self._driver()._inner.player.stop()


class SynthDriver(rhvoice.SynthDriver, SegmentDrainCore):
	"""Retain RHVoice's single worker and observe its actual completion barriers."""

	def __init__(self):
		self._segmentHost = SegmentHost("RHVoice", _RHVoiceStrategy(self))
		self._segmentCondition = Condition(RLock())
		self._stopGate = StopGate(self._segmentCondition)
		self._segmentById = {}
		self._segmentNextId = 1
		self._inner = _RHVoiceInner(self)
		super().__init__()
		player = self._inner.player
		originalGetPlayer = player.get_player
		wrapped = {}

		def getPlayer():
			real = originalGetPlayer()
			if real is None:
				return None
			if real not in wrapped:
				wrapped[real] = _WavePlayer(self._segmentHost, real)
			return wrapped[real]

		player.get_player = getPlayer

	def __setattr__(self, name, value):
		# Inner init creates C callbacks just after assigning Python callables.
		if name in _RHVoiceInner.CALLBACK_NAMES:
			value = _NativeCallback(self, value, name == _RHVoiceInner.DONE_CALLBACK)
		super().__setattr__(name, value)

	def _nativeCallback(self, callback, isDone, *args):
		host = self._segmentHost
		identity = args[-1]
		with self._segmentCondition:
			record = self._segmentById.get(identity)
		refused = None if isDone else 0
		if record is None:
			return refused
		with host.consumer(record) as admitted:
			if admitted is None:
				return refused
			with host.bound_callback(record):
				try:
					result = callback(*args)
					if isDone:
						host.reach(record, "done")
					elif not result:
						host.record_error(record, RuntimeError("RHVoice callback failed"))
					return result
				except Exception as error:  # noqa: BLE001 - recorded on the record; the segment fails
					host.record_error(record, error)
					return refused

	def get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport:
		return unverified_drain_support(
			runtime_profile("RHVoice", nvda_version, audio_mode),
			"callback retirement and physical playback are",
		)

	def speak_segment(
		self,
		commands: SpeechCommands,
		token: CancellationView,
		*,
		context: PlaybackContext,
		on_event: SegmentEventSink,
	):
		self._segmentHost.speak_segment(commands, token, context=context, on_event=on_event)

	def speak(self, speechSequence):
		self._segmentHost.enqueue(speechSequence)

	def cancel(self):
		host = self._segmentHost
		with self._stopGate.hold():
			with host.admission():
				host.cancel()
				with self._segmentCondition:
					current = host.current()
					dropped = [record for record in self._segmentById.values() if record is not current]
					for record in dropped:
						self._segmentById.pop(record.native.identity, None)
				# Every record but the current one: queued (the inner cancel also empties
				# ttsQueue), held at the stop gate, or retired but not yet popped. Abandon
				# closes each, so a worker waiting at the gate returns without speaking.
				for record in dropped:
					host.abandon(record)
				error = None
				try:
					super().cancel()
				except Exception as exc:  # noqa: BLE001 - latched, and kept to raise after the remaining cleanup
					host.latch_control_error(exc)
					error = exc
			host.wait_settled(current)
			try:
				self._inner.player.stop()
			except Exception as exc:  # noqa: BLE001 - latched, and kept to raise after the remaining cleanup
				host.latch_control_error(exc)
				if error is None:
					error = exc
		if error is not None:
			raise error

	def terminate(self):
		with self._segmentHost.admission():
			if self._inner.ttsEngine is None:
				return
			self._segmentHost.terminate()
		error = None
		try:
			self.cancel()
		except Exception as exc:  # noqa: BLE001 - kept and raised after the remaining cleanup
			error = exc
		inner = self._inner
		inner.ttsQueue.put(None)
		inner.ttsThread.join()
		try:
			inner.player.close()
		finally:
			inner.lib.RHVoice_delete_tts_engine(inner.ttsEngine)
			inner.ttsEngine = None
		if error is not None:
			raise error


class Voice(BaseVoice):
	engine = "RHVoice"
	drainProfile = DrainProfile()
	synthDriverClass = SynthDriver
