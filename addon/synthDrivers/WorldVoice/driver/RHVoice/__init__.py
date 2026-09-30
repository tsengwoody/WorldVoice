"""WorldVoice's context-aware boundary around the vendored RHVoice worker."""

from threading import Condition, Event, RLock, Thread, current_thread, local
import weakref

from logHandler import log

from . import driver as rhvoice
from synthDrivers.WorldVoice.driver import Voice
from ...runtime.models import EventKind, PlaybackContext, PlaybackEvent, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import DrainSupport, PlaybackWork
from ...runtime.session import CancellationView
from ...runtime.segmentLifecycle import SegmentLifecycle


class _Speech:
	def __init__(self, work, operation=None):
		self.work = work
		self.operation = operation
		self.boundary = Event() if operation is not None else None
		self.retired = Event() if operation is not None else None
		self.handoff = Event() if operation is not None else None
		self.producer = None
		self.identity = None
		self.cancelled = False
		self.closed = False
		self.audio_closed = False
		self.done = False
		self.returned = False
		self.final_idle = False
		self.message_created = False
		self.error = None
		self.consumers = 0
		self.delivering = False
		self.delivery_thread = None

	def valid(self):
		return not self.cancelled and (self.work is None or self.work.is_valid())


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

	def __init__(self, owner, native, speech):
		self._owner = weakref.ref(owner)
		self._native = native
		self._speech = speech
		self._message = None

	def __getattr__(self, name):
		return getattr(self._native, name)

	def RHVoice_new_message(self, *args):
		owner = self._owner()
		try:
			message = self._native.RHVoice_new_message(*args[:-1], self._speech.identity)
			self._message = message
			self._speech.message_created = bool(message)
			if not message:
				owner._record_error(self._speech, RuntimeError("RHVoice did not create a message"))
			return message
		except Exception as error:
			owner._record_error(self._speech, error)
			raise

	def RHVoice_speak(self, message):
		owner = self._owner()
		try:
			result = self._native.RHVoice_speak(message)
			if not result:
				owner._record_error(self._speech, RuntimeError("RHVoice synthesis failed"))
			else:
				with owner._segmentCondition:
					self._speech.returned = True
			return result
		except Exception as error:
			owner._record_error(self._speech, error)
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
				owner = self._owner()
				owner._record_error(self._speech, error)
				# The native message may still own resources after a failed delete.
				# Stop reusing this engine and player, even if stop succeeds.
				owner._record_control_error(error)
				raise


class _WavePlayer:
	"""Keep a queued index callback tied to its originating native message."""

	def __init__(self, owner, player):
		self._owner = weakref.ref(owner)
		self._player = player

	def __getattr__(self, name):
		return getattr(self._player, name)

	def feed(self, data, onDone=None):
		owner = self._owner()
		admitted = owner._admit_consumer()
		if admitted is None:
			return
		speech, feed_lease = admitted
		def index_done():
			child = owner._admit_consumer(speech, admitted_audio=True, parent=speech.producer)
			if child is None:
				return
			previous = getattr(owner._segmentLocal, "speech", None)
			previous_lease = getattr(owner._segmentLocal, "lease", None)
			owner._segmentLocal.speech = speech
			owner._segmentLocal.lease = child[1]
			try:
				if speech.valid():
					onDone()
			except Exception as error:
				owner._record_error(speech, error)
			finally:
				owner._segmentLocal.speech = previous
				owner._segmentLocal.lease = previous_lease
				owner._release_consumer(speech, child[1])
		try:
			return self._player.feed(data, onDone=index_done if onDone else None)
		except Exception as error:
			owner._record_error(speech, error)
			raise
		finally:
			try:
				if not speech.valid():
					self.stop()
			finally:
				owner._release_consumer(speech, feed_lease)

	def idle(self):
		owner = self._owner()
		speech = owner._associated_speech()
		try:
			return self._player.idle()
		except Exception as error:
			owner._record_error(speech, error)
			raise

	def stop(self):
		try:
			return self._player.stop()
		except Exception as error:
			self._owner()._record_control_error(error)
			raise


class _QueuedSpeech:
	def __init__(self, owner, speech, task, library):
		self._owner = weakref.ref(owner)
		self._speech = speech
		self._task = task
		self._library = library

	def __call__(self):
		owner = self._owner()
		if owner is None:
			return
		with owner._segmentCondition:
			owner._segmentCondition.wait_for(lambda: self._speech.closed or owner._segmentCancelling == 0)
			if self._speech.closed:
				if self._speech.operation is not None:
					self._speech.boundary.set()
					if self._speech.producer is not None:
						owner._segmentLifecycle.retire_producer(self._speech.producer)
					self._speech.retired.set()
				return
			owner._segmentCurrent = self._speech
		owner._segmentLocal.speech = self._speech
		owner._segmentLocal.lease = self._speech.producer
		try:
			if self._speech.valid() and owner._segmentControlError is None:
				self._task()
		except Exception as error:
			owner._record_error(self._speech, error)
		finally:
			if self._speech.boundary is not None:
				self._speech.boundary.set()
			with owner._segmentCondition:
				# Stop new native/feed admission, but let callbacks that already
				# hold a lease finish their player work before the last idle.
				self._speech.closed = True
				owner._segmentCondition.wait_for(lambda: self._speech.consumers == 0)
				self._speech.final_idle = False
				should_idle = (self._speech.done and self._speech.returned
					and self._speech.valid() and self._speech.error is None
					and owner._segmentControlError is None)
			if should_idle and self._speech.valid():
				try:
					owner._SynthDriver__player.idle()
				except Exception as error:
					owner._record_error(self._speech, error)
			with owner._segmentCondition:
				self._speech.audio_closed = True
				owner._segmentCondition.wait_for(lambda: self._speech.consumers == 0)
			try:
				self._library.cleanup()
			except Exception as error:
				owner._record_error(self._speech, error)
			owner._segmentLocal.speech = None
			owner._segmentLocal.lease = None
			with owner._segmentCondition:
				owner._segmentCurrent = None
				owner._segmentById.pop(self._speech.identity, None)
				owner._segmentCondition.notify_all()
			if self._speech.producer is not None:
				owner._segmentLifecycle.retire_producer(self._speech.producer)
				self._speech.retired.set()
				self._speech.handoff.wait()
				owner._SynthDriver__cancel_flag.clear()
			else:
				owner._dispatch(self._speech)


class SynthDriver(rhvoice.SynthDriver):
	"""Retain RHVoice's single worker and observe its actual completion barriers."""

	def __init__(self):
		self._segmentCondition = Condition(RLock())
		self._segmentAdmission = RLock()
		self._segmentLocal = local()
		self._segmentCurrent = None
		self._segmentPending = []
		self._segmentById = {}
		self._segmentNextId = 1
		self._segmentControlError = None
		self._segmentCancelling = 0
		self._segmentTerminated = False
		self._segmentLifecycle = SegmentLifecycle(self)
		self._segmentOperations = {}
		self._segmentAccepted = set()
		super().__init__()
		player = self._SynthDriver__player
		original_get_player = player.get_player
		original_idle = player.idle
		wrapped = {}
		def get_player():
			real = original_get_player()
			if real is None:
				return None
			if real not in wrapped:
				wrapped[real] = _WavePlayer(self, real)
			return wrapped[real]
		def idle():
			speech = self._associated_speech()
			try:
				result = original_idle()
				if speech is not None:
					with self._segmentCondition:
						if speech.returned:
							speech.final_idle = True
				return result
			except Exception as error:
				self._record_error(speech, error)
				raise
		player.get_player = get_player
		player.idle = idle

	def __setattr__(self, name, value):
		# Inner init creates C callbacks just after assigning Python callables.
		if name in ("_SynthDriver__sample_rate_callback", "_SynthDriver__speech_callback",
				"_SynthDriver__mark_callback", "_SynthDriver__done_callback"):
			value = _NativeCallback(self, value, name == "_SynthDriver__done_callback")
		super().__setattr__(name, value)

	def _native_callback(self, callback, is_done, *args):
		identity = args[-1]
		with self._segmentCondition:
			speech = self._segmentById.get(identity)
			if (speech is None or speech is not self._segmentCurrent
					or speech.closed or not speech.valid()):
				return None if is_done else 0
			speech.consumers += 1
			lease = (self._segmentLifecycle.admit_producer(speech.operation, speech.producer)
				if speech.operation is not None else None)
		previous = getattr(self._segmentLocal, "speech", None)
		previous_native = getattr(self._segmentLocal, "native_speech", None)
		previous_lease = getattr(self._segmentLocal, "lease", None)
		self._segmentLocal.speech = speech
		self._segmentLocal.native_speech = speech
		self._segmentLocal.lease = lease
		try:
			result = callback(*args)
			if is_done:
				with self._segmentCondition:
					speech.done = True
			elif not result:
				self._record_error(speech, RuntimeError("RHVoice callback failed"))
			return result
		except Exception as error:
			self._record_error(speech, error)
			return None if is_done else 0
		finally:
			self._segmentLocal.speech = previous
			self._segmentLocal.native_speech = previous_native
			self._segmentLocal.lease = previous_lease
			self._release_consumer(speech, lease)

	def _associated_speech(self):
		return getattr(self._segmentLocal, "speech", None)

	def _admit_consumer(self, speech=None, *, admitted_audio=False, parent=None):
		with self._segmentCondition:
			speech = speech or self._associated_speech()
			# A native callback already holding a lease may start its nested feed
			# after retirement closes admission to new native callbacks.
			if (speech is None or speech is not self._segmentCurrent or not speech.valid()
					or speech.audio_closed or (speech.closed and not admitted_audio
						and getattr(self._segmentLocal, "native_speech", None) is not speech)):
				return None
			speech.consumers += 1
			lease = None
			if speech.operation is not None:
				parent = parent or getattr(self._segmentLocal, "lease", None)
				lease = self._segmentLifecycle.admit_producer(speech.operation, parent)
				if lease is None:
					speech.consumers -= 1
					return None
			return speech, lease

	def _release_consumer(self, speech, lease=None):
		if lease is not None:
			self._segmentLifecycle.retire_producer(lease)
		with self._segmentCondition:
			speech.consumers -= 1
			self._segmentCondition.notify_all()

	def _record_error(self, speech, error):
		with self._segmentCondition:
			if speech is not None and speech.error is None:
				speech.error = error

	def _record_control_error(self, error):
		with self._segmentCondition:
			if self._segmentControlError is None:
				self._segmentControlError = error
			for speech in self._segmentPending:
				if speech.error is None:
					speech.error = self._segmentControlError
			for operation in tuple(self._segmentAccepted):
				self._segmentLifecycle.fail(operation, self._segmentControlError)

	def _dispatch(self, speech):
		work = speech.work
		if work is None or not work.is_valid():
			with self._segmentCondition:
				if speech in self._segmentPending:
					self._segmentPending.remove(speech)
				self._segmentCondition.notify_all()
			return
		def deliver():
			with self._segmentCondition:
				if speech not in self._segmentPending or not work.is_valid():
					if speech in self._segmentPending:
						self._segmentPending.remove(speech)
					self._segmentCondition.notify_all()
					return
				speech.delivering = True
				speech.delivery_thread = current_thread()
				error = speech.error or self._segmentControlError
				if error is None and not (speech.done and speech.returned
						and speech.final_idle and speech.message_created):
					error = RuntimeError("RHVoice segment ended without all completion barriers")
			try:
				if error is None:
					work.complete_drained()
				else:
					work.fail(error)
			except Exception:
				log.error("RHVoice segment event sink", exc_info=True)
			finally:
				with self._segmentCondition:
					speech.delivering = False
					speech.delivery_thread = None
					if speech in self._segmentPending:
						self._segmentPending.remove(speech)
					self._segmentCondition.notify_all()
		Thread(target=deliver, daemon=True, name="RHVoice segment event").start()

	def get_segment_drain_support(self, *, nvda_version=None, audio_mode=None):
		return DrainSupport(True, "RHVoice/%s/%s" % (nvda_version or "unknown", audio_mode or "unknown"),
			"DRAIN explicitly enabled; callback retirement and physical playback are unverified")

	def speak_segment(self, commands: SpeechCommands, token: CancellationView, *,
			context: PlaybackContext, on_event: SegmentEventSink):
		def deliver(event):
			try:
				if not operation._rhvoice_cancelled and not token.is_cancelled() and not self._segmentTerminated:
					with self._segmentCondition:
						control_error = self._segmentControlError
					if control_error is not None and event.kind is EventKind.SEGMENT_DRAINED:
						event = PlaybackEvent(EventKind.SEGMENT_FAILED, event.source_id,
							segment_id=event.segment_id, error=control_error)
					on_event(event)
			finally:
				with self._segmentCondition:
					self._segmentAccepted.discard(operation)
		with self._segmentAdmission:
			with self._segmentCondition:
				if self._segmentTerminated:
					return
				control_error = self._segmentControlError
			if control_error is not None:
				self._segmentLifecycle.reject_new(context, token, on_event, control_error)
				return
			operation = self._segmentLifecycle.accept(context, token, deliver)
			operation._rhvoice_cancelled = False
			with self._segmentCondition:
				self._segmentAccepted.add(operation)
		def run():
			self._run_segment(operation, tuple(commands))
		Thread(target=run,
			name="WorldVoice RHVoice lifecycle", daemon=True).start()

	def _run_segment(self, operation, commands):
		try:
			self._segmentLifecycle.run(operation, commands)
		except Exception as error:
			self._segmentLifecycle.reject_new(operation.work.context, operation.work.token,
				lambda event: None if operation._rhvoice_cancelled else operation._sink(event),
				self._segmentControlError or error.__cause__ or error)
		finally:
			with self._segmentCondition:
				speech = self._segmentOperations.pop(operation, None)
				if speech in self._segmentPending:
					self._segmentPending.remove(speech)
				if operation._rhvoice_cancelled or operation.work.token.is_cancelled():
					self._segmentAccepted.discard(operation)
			if speech is not None:
				speech.handoff.set()

	def submit_native(self, operation, commands):
		self._queue_speech(commands, operation.work, operation)

	def request_stop(self, operation):
		with self._segmentCondition:
			speech = self._segmentOperations.get(operation)
			if speech is None:
				return
			speech.cancelled = True
			active = speech is self._segmentCurrent
		if active:
			self._SynthDriver__cancel_flag.set()
			self._SynthDriver__player.stop()

	def wait_native_boundary(self, operation):
		with self._segmentCondition:
			speech = self._segmentOperations.get(operation)
		if speech is not None:
			speech.boundary.wait()

	def wait_native_retired(self, operation):
		with self._segmentCondition:
			speech = self._segmentOperations.get(operation)
		if speech is None:
			return
		speech.retired.wait()
		if speech.error is not None:
			self._segmentLifecycle.fail(operation, speech.error)

	def wait_playback_drained(self, operation):
		with self._segmentCondition:
			speech = self._segmentOperations.get(operation)
		if speech is None:
			return
		if not operation.work.is_valid() or speech.error is not None:
			self._SynthDriver__player.stop()
			return
		if not (speech.message_created and speech.done and speech.returned and speech.final_idle):
			self._segmentLifecycle.fail(operation, RuntimeError(
				"RHVoice segment ended without all completion barriers"))
			self._SynthDriver__player.stop()

	def speak(self, speechSequence):
		self._queue_speech(speechSequence, None)

	def _queue_speech(self, commands, work, operation=None):
		with self._segmentAdmission:
			if self._segmentTerminated or (work is not None and not work.is_valid()):
				if work is not None:
					work.cancel()
				return
			speech = _Speech(work, operation)
			with self._segmentCondition:
				control_error = self._segmentControlError
				self._segmentPending.append(speech)
				if operation is not None:
					self._segmentOperations[operation] = speech
				if control_error is not None:
					speech.error = control_error
				else:
					speech.identity = self._segmentNextId
					self._segmentNextId += 1
					self._segmentById[speech.identity] = speech
			if control_error is not None:
				if operation is not None:
					self._segmentLifecycle.fail(operation, control_error)
					speech.boundary.set()
					speech.retired.set()
					with self._segmentCondition:
						self._segmentPending.remove(speech)
				else:
					with self._segmentCondition:
						self._segmentPending.remove(speech)
					raise control_error
				return
			if operation is not None:
				speech.producer = self._segmentLifecycle.admit_producer(operation)
				if speech.producer is None:
					with self._segmentCondition:
						self._segmentById.pop(speech.identity, None)
						self._segmentPending.remove(speech)
						self._segmentOperations.pop(operation, None)
					return
			try:
				converter = rhvoice.SsmlConverter(self, self.language)
				text = converter.convertToXml(commands)
				lib = _NativeLibrary(self, self._SynthDriver__lib, speech)
				task = rhvoice.SpeakText(lib, self._SynthDriver__tts_engine, text,
					self._SynthDriver__cancel_flag, self._SynthDriver__player)
				task.set_voice_profile(self._SynthDriver__profile)
				task.set_rate(self._SynthDriver__rate)
				task.set_pitch(self._SynthDriver__pitch)
				task.set_volume(self._SynthDriver__volume)
				task.configure_rate_boost(self._SynthDriver__rate_boost)
				self._SynthDriver__tts_queue.put(_QueuedSpeech(self, speech, task, lib))
			except Exception:
				with self._segmentCondition:
					self._segmentById.pop(speech.identity, None)
					self._segmentPending.remove(speech)
					self._segmentOperations.pop(operation, None)
				if speech.producer is not None:
					self._segmentLifecycle.retire_producer(speech.producer)
				raise

	def cancel(self):
		with self._segmentAdmission:
			with self._segmentCondition:
				operations = tuple(self._segmentAccepted)
			for operation in operations:
				operation._rhvoice_cancelled = True
				self._segmentLifecycle.cancel(operation)
			with self._segmentCondition:
				self._segmentCancelling += 1
				current = self._segmentCurrent
				callback_origin = self._associated_speech() is not None
				in_delivery = any(speech.delivery_thread is current_thread()
					for speech in self._segmentPending)
				deliveries = tuple(speech for speech in self._segmentPending
					if speech.delivering and speech.delivery_thread is not current_thread())
				for speech in tuple(self._segmentPending):
					speech.cancelled = True
					if speech.work is not None:
						speech.work.cancel()
					if speech is not current and not speech.delivering:
						speech.closed = True
						if speech.operation is not None:
							speech.boundary.set()
							if speech.producer is not None:
								self._segmentLifecycle.retire_producer(speech.producer)
							speech.retired.set()
						self._segmentById.pop(speech.identity, None)
						self._segmentPending.remove(speech)
			error = None
			try:
				super().cancel()
			except Exception as exc:
				self._record_control_error(exc)
				error = exc
		try:
			with self._segmentCondition:
				# Legacy done listeners can call cancel from inside the native
				# callback. That callback itself holds the retirement lease.
				if current is not None and self._associated_speech() is not current:
					self._segmentCondition.wait_for(lambda: self._segmentCurrent is not current)
				# A delivery sink may be waiting for this native/audio callback
				# to retire. The callback must not wait for that delivery in turn.
				if not in_delivery and not callback_origin:
					self._segmentCondition.wait_for(lambda: all(not speech.delivering
						for speech in deliveries))
			try:
				self._SynthDriver__player.stop()
			except Exception as exc:
				self._record_control_error(exc)
				if error is None:
					error = exc
		finally:
			with self._segmentCondition:
				self._segmentCancelling -= 1
				self._segmentCondition.notify_all()
		if error is not None:
			raise error

	def terminate(self):
		with self._segmentAdmission:
			if self._SynthDriver__tts_engine is None:
				return
			self._segmentTerminated = True
			self._segmentLifecycle.terminate()
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
	synth_driver_class = SynthDriver
