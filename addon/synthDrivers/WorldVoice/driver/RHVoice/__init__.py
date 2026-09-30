"""WorldVoice's context-aware boundary around the vendored RHVoice worker."""

from threading import Condition, RLock, Thread, local
import weakref

from logHandler import log

from . import driver as rhvoice
from synthDrivers.WorldVoice.driver import Voice
from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import DrainSupport, PlaybackWork
from ...runtime.session import CancellationView


class _Speech:
	def __init__(self, work):
		self.work = work
		self.identity = None
		self.cancelled = False
		self.closed = False
		self.done = False
		self.returned = False
		self.final_idle = False
		self.message_created = False
		self.error = None
		self.consumers = 0

	def valid(self):
		return not self.cancelled and not self.closed and (self.work is None or self.work.is_valid())


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
				self._owner()._record_error(self._speech, error)
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
		speech = owner._admit_consumer()
		if speech is None:
			return
		def index_done():
			if owner._admit_consumer(speech) is None:
				return
			try:
				if speech.valid():
					onDone()
			except Exception as error:
				owner._record_error(speech, error)
			finally:
				owner._release_consumer(speech)
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
				owner._release_consumer(speech)

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
				return
			owner._segmentCurrent = self._speech
		owner._segmentLocal.speech = self._speech
		try:
			if self._speech.valid() and owner._segmentControlError is None:
				self._task()
		except Exception as error:
			owner._record_error(self._speech, error)
		finally:
			owner._segmentLocal.speech = None
			with owner._segmentCondition:
				self._speech.closed = True
				owner._segmentCondition.wait_for(lambda: self._speech.consumers == 0)
			try:
				self._library.cleanup()
			except Exception as error:
				owner._record_error(self._speech, error)
			with owner._segmentCondition:
				owner._segmentCurrent = None
				owner._segmentById.pop(self._speech.identity, None)
				if self._speech in owner._segmentPending:
					owner._segmentPending.remove(self._speech)
				owner._segmentCondition.notify_all()
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
			if speech is None or speech is not self._segmentCurrent or not speech.valid():
				return None if is_done else 0
			speech.consumers += 1
		previous = getattr(self._segmentLocal, "speech", None)
		self._segmentLocal.speech = speech
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
			self._release_consumer(speech)

	def _associated_speech(self):
		return getattr(self._segmentLocal, "speech", None)

	def _admit_consumer(self, speech=None):
		with self._segmentCondition:
			speech = speech or self._associated_speech()
			if speech is None or speech is not self._segmentCurrent or not speech.valid():
				return None
			speech.consumers += 1
			return speech

	def _release_consumer(self, speech):
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

	def _dispatch(self, speech):
		work = speech.work
		if work is None or not work.is_valid():
			return
		error = speech.error or self._segmentControlError
		if error is None and not (speech.done and speech.returned and speech.final_idle and speech.message_created):
			error = RuntimeError("RHVoice segment ended without all completion barriers")
		def deliver():
			try:
				if error is None:
					work.complete_drained()
				else:
					work.fail(error)
			except Exception:
				log.error("RHVoice segment event sink", exc_info=True)
		Thread(target=deliver, daemon=True, name="RHVoice segment event").start()

	def get_segment_drain_support(self, *, nvda_version=None, audio_mode=None):
		return DrainSupport(False, "RHVoice/%s/%s" % (nvda_version or "unknown", audio_mode or "unknown"),
			"RHVoice callback retirement and physical playback have not been verified for this profile")

	def speak_segment(self, commands: SpeechCommands, token: CancellationView, *,
			context: PlaybackContext, on_event: SegmentEventSink):
		self._queue_speech(commands, PlaybackWork(context, token, on_event))

	def speak(self, speechSequence):
		self._queue_speech(speechSequence, None)

	def _queue_speech(self, commands, work):
		with self._segmentAdmission:
			if self._segmentTerminated or (work is not None and not work.is_valid()):
				if work is not None:
					work.cancel()
				return
			speech = _Speech(work)
			with self._segmentCondition:
				control_error = self._segmentControlError
				if control_error is not None:
					speech.error = control_error
				else:
					speech.identity = self._segmentNextId
					self._segmentNextId += 1
					self._segmentById[speech.identity] = speech
					self._segmentPending.append(speech)
			if control_error is not None:
				self._dispatch(speech)
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
				raise

	def cancel(self):
		with self._segmentAdmission:
			with self._segmentCondition:
				self._segmentCancelling += 1
				current = self._segmentCurrent
				for speech in tuple(self._segmentPending):
					speech.cancelled = True
					if speech.work is not None:
						speech.work.cancel()
					if speech is not current:
						speech.closed = True
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
