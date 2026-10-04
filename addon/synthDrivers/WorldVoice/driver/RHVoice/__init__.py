"""WorldVoice's context-aware boundary around the vendored RHVoice worker."""

from dataclasses import dataclass
from threading import Condition, RLock
import weakref

from . import driver as rhvoice
from synthDrivers.WorldVoice.driver import Voice
from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import DrainProfile, runtime_profile, unverified_drain_support
from ...runtime.segmentHost import SegmentHost
from ...runtime.session import CancellationView


@dataclass(eq=False)
class _RHVoiceMessage:
	"""RHVoice data carried on a NativeRecord: its callback identity and library."""

	identity: int
	library: "_NativeLibrary | None" = None


class _NativeCallback:
	"""Preserve the inner callback's public state, including lastIndex."""

	def __init__(self, owner, callback, is_done):
		self._owner = weakref.ref(owner)
		self._callback = callback
		self._is_done = is_done

	def __getattr__(self, name):
		return getattr(self._callback, name)

	def __call__(self, *args):
		return self._owner()._native_callback(self._callback, self._is_done, *args)


class _NativeLibrary:
	"""Observe synchronous native outcomes that SpeakText does not inspect."""

	def __init__(self, owner, native, record):
		self._owner = weakref.ref(owner)
		self._native = native
		self._record = record
		self._message = None

	def __getattr__(self, name):
		return getattr(self._native, name)

	def RHVoice_new_message(self, *args):
		host = self._owner()._segmentHost
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
		host = self._owner()._segmentHost
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
				self._owner()._segmentHost.latch_control_error(error)
				raise


class _WavePlayer:
	"""Keep a queued index callback tied to its originating native message."""

	def __init__(self, owner, player):
		self._owner = weakref.ref(owner)
		self._player = player

	def __getattr__(self, name):
		return getattr(self._player, name)

	def feed(self, data, onDone=None):
		host = self._owner()._segmentHost
		bound = host.callback_record()
		if bound is None:
			return None
		with host.consumer(bound) as record:
			if record is None:
				return None

			def index_done():
				# The worker's final idle may release this after the native gate closes.
				with host.consumer(record, audio=True) as admitted:
					if admitted is None:
						return
					with host.bound_callback(record):
						try:
							onDone()
						except Exception as error:
							host.record_error(record, error)

			try:
				return self._player.feed(data, onDone=index_done if onDone else None)
			except Exception as error:
				host.record_error(record, error)
				raise
			finally:
				if not record.is_valid():
					self.stop()

	def idle(self):
		host = self._owner()._segmentHost
		record = host.callback_record()
		try:
			return self._player.idle()
		except Exception as error:
			host.record_error(record, error)
			raise

	def stop(self):
		try:
			return self._player.stop()
		except Exception as error:
			self._owner()._segmentHost.latch_control_error(error)
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
			owner._segmentCondition.wait_for(lambda: record.closed or owner._segmentCancelling == 0)
			if record.closed:
				# NVDA cancel already abandoned this queued record.
				return
			host.begin(record)
		try:
			if record.is_valid() and host.control_error is None:
				with host.bound_callback(record):
					self._task()
		except Exception as error:
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
				owner._SynthDriver__player.idle()
				host.reach(record, "idle")
			except Exception as error:
				host.record_error(record, error)
		host.retire(record, finish=record.native.library.cleanup)
		with owner._segmentCondition:
			owner._segmentById.pop(record.native.identity, None)
		if record.operation is not None:
			owner._SynthDriver__cancel_flag.clear()
		else:
			host.forget(record)


class _RHVoiceStrategy:
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
			library = record.native.library = _NativeLibrary(driver, driver._SynthDriver__lib, record)
			task = rhvoice.SpeakText(
				library,
				driver._SynthDriver__tts_engine,
				text,
				driver._SynthDriver__cancel_flag,
				driver._SynthDriver__player,
			)
			task.set_voice_profile(driver._SynthDriver__profile)
			task.set_rate(driver._SynthDriver__rate)
			task.set_pitch(driver._SynthDriver__pitch)
			task.set_volume(driver._SynthDriver__volume)
			task.configure_rate_boost(driver._SynthDriver__rate_boost)
			driver._SynthDriver__tts_queue.put(_QueuedSpeech(driver, record, task))
		except Exception:
			with driver._segmentCondition:
				driver._segmentById.pop(identity, None)
			raise

	def stop_native(self, host, record):
		driver = self._driver()
		driver._SynthDriver__cancel_flag.set()
		driver._SynthDriver__player.stop()

	def stop_player(self, host):
		self._driver()._SynthDriver__player.stop()


class SynthDriver(rhvoice.SynthDriver):
	"""Retain RHVoice's single worker and observe its actual completion barriers."""

	def __init__(self):
		self._segmentHost = SegmentHost(
			"RHVoice", _RHVoiceStrategy(self), fail_accepted_on_control_error=True
		)
		self._segmentCondition = Condition(RLock())
		self._segmentById = {}
		self._segmentNextId = 1
		self._segmentCancelling = 0
		super().__init__()
		player = self._SynthDriver__player
		original_get_player = player.get_player
		wrapped = {}

		def get_player():
			real = original_get_player()
			if real is None:
				return None
			if real not in wrapped:
				wrapped[real] = _WavePlayer(self, real)
			return wrapped[real]

		player.get_player = get_player

	def __setattr__(self, name, value):
		# Inner init creates C callbacks just after assigning Python callables.
		if name in (
			"_SynthDriver__sample_rate_callback",
			"_SynthDriver__speech_callback",
			"_SynthDriver__mark_callback",
			"_SynthDriver__done_callback",
		):
			value = _NativeCallback(self, value, name == "_SynthDriver__done_callback")
		super().__setattr__(name, value)

	def _native_callback(self, callback, is_done, *args):
		host = self._segmentHost
		identity = args[-1]
		with self._segmentCondition:
			record = self._segmentById.get(identity)
		refused = None if is_done else 0
		if record is None:
			return refused
		with host.consumer(record) as admitted:
			if admitted is None:
				return refused
			with host.bound_callback(record):
				try:
					result = callback(*args)
					if is_done:
						host.reach(record, "done")
					elif not result:
						host.record_error(record, RuntimeError("RHVoice callback failed"))
					return result
				except Exception as error:
					host.record_error(record, error)
					return refused

	def get_segment_drain_support(self, *, nvda_version=None, audio_mode=None):
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
		with host.admission():
			host.cancel()
			with self._segmentCondition:
				self._segmentCancelling += 1
				current = host.current()
				dropped = [record for record in self._segmentById.values() if record is not current]
				for record in dropped:
					self._segmentById.pop(record.native.identity, None)
			# Queued records never reach the worker; the inner cancel clears them.
			for record in dropped:
				host.abandon(record)
			error = None
			try:
				super().cancel()
			except Exception as exc:
				host.latch_control_error(exc)
				error = exc
		try:
			host.wait_settled(current)
			try:
				self._SynthDriver__player.stop()
			except Exception as exc:
				host.latch_control_error(exc)
				if error is None:
					error = exc
		finally:
			with self._segmentCondition:
				self._segmentCancelling -= 1
				self._segmentCondition.notify_all()
		if error is not None:
			raise error

	def terminate(self):
		with self._segmentHost.admission():
			if self._SynthDriver__tts_engine is None:
				return
			self._segmentHost.terminate()
		error = None
		try:
			self.cancel()
		except Exception as exc:
			error = exc
		self._SynthDriver__tts_queue.put(None)
		self._SynthDriver__tts_thread.join()
		try:
			self._SynthDriver__player.close()
		finally:
			self._SynthDriver__lib.RHVoice_delete_tts_engine(self._SynthDriver__tts_engine)
			self._SynthDriver__tts_engine = None
		if error is not None:
			raise error


class Voice(Voice):
	core = None
	engine = "RHVoice"
	drain_profile = DrainProfile()
	synth_driver_class = SynthDriver
