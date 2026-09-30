from dataclasses import dataclass, field
from threading import Event, RLock, Thread, local
import weakref

from synthDrivers import sapi5
from synthDrivers.sapi5 import SynthDriver as BaseSynthDriver
from synthDriverHandler import synthIndexReached
from logHandler import log
from synthDrivers.WorldVoice.driver import Voice
from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import DrainSupport, PlaybackWork
from ...runtime.session import CancellationView
from ...runtime.segmentLifecycle import SegmentLifecycle, SegmentOperation


@dataclass(eq=False)
class _NativeRequest:
	request: object
	work: PlaybackWork | None
	operation: SegmentOperation | None = None
	binding: object | None = None
	stream: int | None = None
	ended: bool = False
	end_processed: bool = False
	error: Exception | None = None
	feeds: int = 0
	audio_closed: bool = False
	cancelled: bool = False
	index_lock: object = field(default_factory=RLock)

	def is_valid(self):
		return not self.cancelled and (self.work is None or self.work.is_valid())


@dataclass(eq=False)
class _OperationBinding:
	boundary: Event = field(default_factory=Event)
	retired: Event = field(default_factory=Event)
	playback_done: Event = field(default_factory=Event)
	handoff: Event = field(default_factory=Event)
	native: _NativeRequest | None = None
	player: object | None = None
	tts: object | None = None


class _SegmentAudioStream(sapi5.SynthDriverAudioStream):
	"""Own the complete COM PCM callback, including Sonic before feed."""

	def ISequentialStream_RemoteWrite(self, this, pv, cb, pcbWritten):
		driver = self.synthRef()
		if pcbWritten:
			pcbWritten[0] = 0
		if driver is None:
			return sapi5.hresult.E_UNEXPECTED
		with driver._threadCond:
			if self is not driver._segmentAudio:
				return sapi5.hresult.S_OK
			native = driver._segmentNative
			if native is None:
				return sapi5.hresult.S_OK
			if native.audio_closed or not native.is_valid():
				return sapi5.hresult.S_OK
			lease = (driver._segmentLifecycle.admit_producer(native.operation)
				if native.operation is not None else None)
			if native.operation is not None and lease is None:
				return sapi5.hresult.S_OK
			# Ordinary PCM callbacks also retain this request's resources. Voice
			# reload/termination must join the worker only after they have retired.
			native.feeds += 1
		previous = getattr(driver._segmentCallbackLocal, "native", None)
		previous_lease = getattr(driver._segmentCallbackLocal, "lease", None)
		driver._segmentCallbackLocal.native = native
		driver._segmentCallbackLocal.lease = lease
		try:
			return super().ISequentialStream_RemoteWrite(this, pv, cb, pcbWritten)
		except Exception as error:
			if native is not None:
				driver._recordSegmentError(native, error)
			raise
		finally:
			driver._segmentCallbackLocal.native = previous
			driver._segmentCallbackLocal.lease = previous_lease
			if lease is not None:
				driver._segmentLifecycle.retire_producer(lease)
			if native is not None:
				with driver._threadCond:
					native.feeds -= 1
					driver._threadCond.notify_all()


class _SegmentPlayer:
	"""Keep real WavePlayer operations and capture their admitted work."""

	def __init__(self, driver, player):
		self._driver = weakref.ref(driver)
		self._player = player

	def __getattr__(self, name):
		return getattr(self._player, name)

	def feed(self, data, size=None, onDone=None):
		driver = self._driver()
		if driver is None:
			return
		with driver._threadCond:
			native = driver._segmentNative
			if self is not driver.player:
				return
			if native is not None:
				admitted_pcm = getattr(driver._segmentCallbackLocal, "native", None) is native
				if not native.is_valid() or (native.audio_closed and not admitted_pcm):
					return
				parent = getattr(driver._segmentCallbackLocal, "lease", None) if admitted_pcm else None
				lease = (driver._segmentLifecycle.admit_producer(native.operation, parent=parent)
					if native.operation is not None else None)
				if native.operation is not None and lease is None:
					return
				native.feeds += 1
			else:
				native = None
				lease = None
		callback = onDone
		if native is not None and onDone is not None:
			def callback():
				if native.is_valid():
					onDone()
		try:
			return self._player.feed(data, size, callback)
		except Exception as error:
			if native is not None:
				driver._recordSegmentError(native, error)
			raise
		finally:
			if native is not None:
				try:
					if not native.is_valid():
						self._player.stop()
				finally:
					if lease is not None:
						driver._segmentLifecycle.retire_producer(lease)
					with driver._threadCond:
						native.feeds -= 1
						driver._threadCond.notify_all()

	def idle(self):
		driver = self._driver()
		if driver is None:
			return self._player.idle()
		with driver._threadCond:
			native = driver._segmentNative if self is driver.player else None
		try:
			# WavePlayer.idle may wait for playback or for stop(). Never hold
			# the request lock while it runs: cancel needs that lock to stop it.
			result = self._player.idle()
			with driver._threadCond:
				current = self is driver.player and driver._segmentNative is native
			if (current and native is not None and native.work is not None and native.work.is_valid()
					and not native.end_processed):
				raise RuntimeError("SAPI5 player idle preceded the segment end notification")
			return result
		except Exception as error:
			if native is not None and native.work is not None:
				driver._recordSegmentError(native, error)
				# An early external idle is a segment failure; its caller need not
				# reenter the runtime sink from the COM/player callback stack.
				return None
			raise


class _SegmentSapiSink(sapi5.SapiSink):
	"""Reject old stream events, retaining bookmark closures' original work."""

	def __init__(self, synthRef, eventSource):
		super().__init__(synthRef)
		self._eventSource = eventSource

	def detach(self):
		# Release original COM ownership without waiting for an admitted Notify.
		# An admitted enumerator retains only its own original source snapshot.
		self._eventSource = None

	def ISpNotifySink_Notify(self):
		driver = self.synthRef()
		source = self._eventSource
		if driver is None or source is None or self is not driver._segmentSink:
			return
		# Never fetch events from mutable driver.tts: a retained old sink must
		# not consume a replacement voice's events during/after reload.
		for event in sapi5._SapiEvent.enumerateFrom(source):
			if event.eEventId == sapi5._SPEventEnum.START_INPUT_STREAM:
				self.StartStream(event.ulStreamNum, event.ullAudioStreamOffset)
			elif event.eEventId == sapi5._SPEventEnum.END_INPUT_STREAM:
				self.EndStream(event.ulStreamNum, event.ullAudioStreamOffset)
			elif event.eEventId == sapi5._SPEventEnum.TTS_BOOKMARK:
				self.Bookmark(event.ulStreamNum, event.ullAudioStreamOffset, event.getString(), event.wParam)

	def _native(self, stream):
		driver = self.synthRef()
		if driver is None:
			return None, None
		with driver._threadCond:
			if self is not driver._segmentSink:
				return driver, None
			native = driver._segmentNative
			if native is None:
				return driver, None
			if native.stream is None:
				# SAPI may invoke StartStream before Speak returns its stream id.
				# A late notification from a previous request may also arrive in
				# this gap. It must never claim the new request's identity.
				if stream in driver._segmentSeenStreams:
					return driver, None
				native.stream = stream
				driver._segmentSeenStreams.add(stream)
			if native.stream != stream:
				return driver, None
			return driver, native

	def StartStream(self, streamNum, pos):
		driver, native = self._native(streamNum)
		if native is not None and native.is_valid():
			return super().StartStream(streamNum, pos)
		if driver is not None and self is driver._segmentSink and not driver.player:
			return super().StartStream(streamNum, pos)

	def Bookmark(self, streamNum, pos, bookmark, bookmarkId):
		driver, native = self._native(streamNum)
		if native is None:
			# Legacy audio has no worker/native record.
			if driver is not None and self is driver._segmentSink and not driver.player:
				return super().Bookmark(streamNum, pos, bookmark, bookmarkId)
			return
		if not native.is_valid():
			return
		return super().Bookmark(streamNum, pos, bookmark, bookmarkId)

	def onIndexReached(self, streamNum, index):
		driver, native = self._native(streamNum)
		if native is None:
			if driver is not None and self is driver._segmentSink and not driver.player:
				return super().onIndexReached(streamNum, index)
			return
		if not native.is_valid():
			return
		if native.work is None:
			return super().onIndexReached(streamNum, index)
		with native.index_lock:
			bookmarks = native.request.bookmarks
			if not native.work.is_valid() or index not in bookmarks:
				return
			while bookmarks:
				if bookmarks.popleft() == index:
					break
			if native.work.is_valid():
				synthIndexReached.notify(synth=driver, index=index)

	def EndStream(self, streamNum, pos):
		driver, native = self._native(streamNum)
		if native is None:
			if driver is not None and self is driver._segmentSink and not driver.player:
				return super().EndStream(streamNum, pos)
			return
		with driver._threadCond:
			# Lookup may have admitted this callback before reload replaced the
			# sink/native request. Revalidate and transition worker state together;
			# the inherited method would resolve mutable driver state again.
			if self is not driver._segmentSink or driver._segmentNative is not native:
				return
			# A cancelled token still consumes its native terminal notification
			# so the worker can retire this identity without publishing success.
			native.ended = True
			if driver._isCancelling:
				driver._bookmarkLists.clear()
				if native.binding is not None:
					native.binding.boundary.set()
				return
			driver._isCompleted = True
			driver._threadCond.notify()
			if native.binding is not None:
				native.binding.boundary.set()


class SynthDriver(BaseSynthDriver):
	"""Correlate each WASAPI request with its final real idle barrier."""

	def __init__(self, *args, **kwargs):
		self._segmentRequests = {}
		self._segmentSeenStreams = set()
		self._segmentWorks = set()
		self._segmentBindings = {}
		self._segmentLifecycle = SegmentLifecycle(self)
		self._segmentNative = None
		self._segmentSink = None
		self._segmentAudio = None
		self._segmentCallbackLocal = local()
		self._segmentTerminated = False
		self._segmentStops = 0
		self._segmentControlError = None
		super().__init__(*args, **kwargs)

	def get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport:
		if audio_mode != "wasapi" or not self.useWasapi or self.player is None:
			return DrainSupport(False, "sapi5-legacy-audio", "SAPI5 legacy audio has no owned player idle barrier")
		return DrainSupport(True, "sapi5-wasapi",
			"DRAIN explicitly enabled; callback retirement, loaded profile provenance and physical playback are unverified")

	def speak_segment(self, commands: SpeechCommands, token: CancellationView, *,
		context: PlaybackContext, on_event: SegmentEventSink) -> None:
		with self._threadCond:
			try:
				self._checkSpeechAdmission()
				if not self.useWasapi or self.player is None:
					raise RuntimeError("Correlated SAPI5 playback requires the WASAPI player")
			except Exception as error:
				self._segmentLifecycle.reject_new(context, token, on_event, error)
				return
			def deliver(event):
				try:
					on_event(event)
				finally:
					with self._threadCond:
						self._segmentWorks.discard(operation)
			operation = self._segmentLifecycle.accept(context, token, deliver)
			self._segmentWorks.add(operation)
			self._segmentBindings[operation] = _OperationBinding()
		Thread(target=self._runSegmentOperation, args=(operation, tuple(commands)),
			name="WorldVoice SAPI5 lifecycle", daemon=True).start()

	def _runSegmentOperation(self, operation, commands):
		try:
			self._segmentLifecycle.run(operation, commands)
		except Exception as error:
			log.error("SAPI5 segment lifecycle failed", exc_info=True)
			self._segmentLifecycle.fail(operation, error)
		finally:
			with self._threadCond:
				if not operation.work.is_valid():
					self._segmentWorks.discard(operation)
				binding = self._segmentBindings.pop(operation, None)
				if binding is not None:
					binding.handoff.set()

	def submit_native(self, operation, commands):
		with self._threadCond:
			self._checkSpeechAdmission()
			# NVDA owns XML conversion; bind while its reentrant queue lock is held.
			super().speak(commands)
			request = self._speakRequests[-1]
			self._segmentRequests[id(request)] = operation

	def request_stop(self, operation):
		binding = self._segmentBindings.get(operation)
		if binding is None:
			return
		with self._threadCond:
			native = binding.native
			if native is not None and self._segmentNative is native:
				native.cancelled = True
				self._isCancelling = True
				self._threadCond.notify_all()
		player = binding.player
		if player is not None:
			try:
				player.stop()
			except Exception as error:
				self._failSegmentControl(error)

	def wait_native_boundary(self, operation):
		self._segmentBindings[operation].boundary.wait()

	def wait_native_retired(self, operation):
		self._segmentBindings[operation].retired.wait()

	def wait_playback_drained(self, operation):
		binding = self._segmentBindings[operation]
		try:
			if binding.native is not None and binding.native.error is not None:
				self._segmentLifecycle.fail(operation, binding.native.error)
				return
			if binding.player is not None:
				try:
					binding.player.idle()
				except Exception as error:
					if binding.native is not None:
						binding.native.error = error
					try:
						binding.player.stop()
						binding.tts.Speak(None, sapi5.SpeechVoiceSpeakFlags.Async |
							sapi5.SpeechVoiceSpeakFlags.PurgeBeforeSpeak)
					except Exception as control_error:
						self._failSegmentControl(control_error)
					self._segmentLifecycle.fail(operation, error)
		finally:
			binding.playback_done.set()

	def _checkSpeechAdmission(self):
		if self._segmentTerminated:
			raise RuntimeError("SAPI5 driver has terminated")
		if self._segmentControlError is not None:
			raise self._segmentControlError
		if self.useWasapi and (self._thread is None or not self._thread.is_alive()):
			raise RuntimeError("SAPI5 playback worker is unavailable")

	def speak(self, speechSequence):
		with self._threadCond:
			self._checkSpeechAdmission()
			return super().speak(speechSequence)

	def _invalidateSegments(self):
		with self._threadCond:
			if self._segmentNative is not None:
				self._segmentNative.cancelled = True
			for operation in tuple(self._segmentWorks):
				self._segmentLifecycle.cancel(operation)
				binding = self._segmentBindings.get(operation)
				if binding is not None and binding.native is None:
					binding.boundary.set()
					binding.retired.set()
					binding.playback_done.set()
			self._segmentRequests.clear()
			self._speakRequests.clear()

	def _initTts(self, voice=None):
		self._invalidateSegments()
		if self._segmentSink is not None:
			self._segmentSink.detach()
		self._segmentSink = None
		self._segmentAudio = None
		super()._initTts(voice)
		self._segmentSeenStreams.clear()
		self._segmentControlError = None
		if self.player is not None:
			self.player = _SegmentPlayer(self, self.player)
		self._segmentSink = _SegmentSapiSink(weakref.ref(self), self.tts.QueryInterface(sapi5.ISpEventSource))
		self.tts.QueryInterface(sapi5.ISpNotifySource).SetNotifySink(self._segmentSink)

	def _initWasapiAudio(self):
		# The parent has already joined and replaced the old resources here.
		# Clear their control fault before the replacement worker starts.
		self._segmentControlError = None
		# The inner initializer constructs its own fixed AudioStream class.
		# Keep its format/settings/player path, substituting only our owned
		# COM callback object so pre-feed Sonic failures cannot escape capture.
		audio = self._segmentAudio = _SegmentAudioStream(weakref.ref(self))
		self.tts.QueryInterface(sapi5.ISpVoice).SetOutput(audio, True)
		wfx = audio.waveFormat
		self.player = sapi5.nvwave.WavePlayer(
			channels=wfx.nChannels, samplesPerSec=wfx.nSamplesPerSec,
			bitsPerSample=wfx.wBitsPerSample,
			outputDevice=sapi5.config.conf["audio"]["outputDevice"],
		)
		sapi5.sonicInitialize()
		self.sonicStream = sapi5.SonicStream(wfx.nSamplesPerSec, wfx.nChannels)
		self._thread = Thread(target=self._speakThread, name="Sapi5SpeakThread")
		self._thread.start()

	def _recordSegmentError(self, native, error):
		with self._threadCond:
			if self._segmentNative is native and native.error is None:
				native.error = error
				self._isCompleted = True
				self._threadCond.notify_all()

	def _onEndStream(self):
		native = self._segmentNative
		if native is None or native.work is None:
			return super()._onEndStream()
		if not native.ended:
			raise RuntimeError("SAPI5 request completed without its stream end marker")
		# Preserve ordinary source notifications, including untriggered tail
		# bookmarks, without publishing the parent's pre-idle anonymous DONE.
		with native.index_lock:
			while native.request.bookmarks:
				bookmark = native.request.bookmarks.popleft()
				if native.work.is_valid():
					synthIndexReached.notify(synth=self, index=bookmark)
		if self._bookmarkLists:
			self._bookmarkLists.popleft()
		self._isSpeaking = False
		native.end_processed = True

	def _failSegmentControl(self, error):
		with self._threadCond:
			if self._segmentControlError is not None:
				return
			self._segmentControlError = error
			current = self._segmentNative.operation if self._segmentNative is not None else None
			operations = tuple(operation for operation in self._segmentWorks if operation is not current)
			self._speakRequests.clear()
			self._segmentRequests.clear()
			self._threadCond.notify_all()
		for operation in operations:
			self._segmentLifecycle.fail(operation, error)
			binding = self._segmentBindings.get(operation)
			if binding is not None and binding.native is None:
				binding.boundary.set()
				binding.retired.set()
				binding.playback_done.set()

	def _speakThread(self):
		# NVDA publishes DONE before idle, only idles when its whole queue is
		# empty, and swallows synthesis/Sonic failures. Those hooks cannot prove
		# one segment's barrier or propagate worker faults, so the outer worker
		# retains native request identity and drains each correlated request.
		# Ordinary requests keep the parent's queue-empty idle/DONE behavior.
		while True:
			with self._threadCond:
				self._threadCond.wait_for(lambda: self._isStoppingThread or self._segmentControlError is not None or (
					self._segmentStops == 0 and self._requestsAvailable()))
				if self._isStoppingThread or self._segmentControlError is not None:
					return
				if self._isCancelling:
					native = None
				else:
					request = self._speakRequests.popleft()
					operation = self._segmentRequests.pop(id(request), None)
					work = operation.work if operation is not None else None
					if work is not None and not work.is_valid():
						binding = self._segmentBindings.get(operation)
						if binding is not None:
							binding.boundary.set()
							binding.retired.set()
							binding.playback_done.set()
						continue
					binding = self._segmentBindings.get(operation) if operation is not None else None
					native = _NativeRequest(request, work, operation, binding)
					self._segmentNative = native
					self._isCompleted = False
					tts, player, sonic = self.tts, self.player, self.sonicStream
					if binding is not None:
						binding.native = native
						binding.player = player
						binding.tts = tts
			if native is None:
				try:
					self._purgeCancelledSpeech(self.tts, self.sonicStream)
				except Exception as error:
					self._failSegmentControl(error)
				continue
			error = None
			self._bookmarkLists.append(request.bookmarks)
			try:
				stream = tts.Speak(request.text, sapi5.SpeechVoiceSpeakFlags.IsXML | sapi5.SpeechVoiceSpeakFlags.Async)
				with self._threadCond:
					if native.stream is not None and native.stream != stream:
						raise RuntimeError("SAPI5 callback stream did not match the admitted request")
					native.stream = stream
					self._segmentSeenStreams.add(stream)
					self._threadCond.wait_for(self._requestCompleted)
				if work is not None or native.cancelled:
					with self._threadCond:
						# EndStream closes new audio admission. Retire every feed
						# already admitted before flushing/final idle and checking errors.
						native.audio_closed = True
						self._threadCond.wait_for(lambda: native.feeds == 0)
				if native.error is not None:
					raise native.error
				if not self._isCancelling and not self._isStoppingThread and native.is_valid():
					sonic.flush()
					audio = sonic.readShort()
					if work is not None:
						# The worker alone owns this final feed after callback retirement.
						player._player.feed(audio, len(audio) * 2)
					else:
						player.feed(audio, len(audio) * 2)
					self._onEndStream()
					if work is None and not self._requestsAvailable():
						player.idle()
					if native.error is not None:
						raise native.error
				if self._isCancelling:
					self._purgeCancelledSpeech(tts, sonic)
			except Exception as failure:
				error = failure
				log.error("Error speaking SAPI5 request", exc_info=True)
				if self._bookmarkLists:
					self._bookmarkLists.clear()
				try:
					with self._threadCond:
						# No new PCM may enter this failed request while its native
						# callbacks retire and the SAPI stream is purged.
						native.audio_closed = True
					try:
						player.stop()
					finally:
						with self._threadCond:
							self._threadCond.wait_for(lambda: native.feeds == 0)
						# Both ordinary and correlated failures leave native speech
						# uncertain. Purge before another request can take this player.
						tts.Speak(None, sapi5.SpeechVoiceSpeakFlags.Async | sapi5.SpeechVoiceSpeakFlags.PurgeBeforeSpeak)
					if work is None:
						# One shared COM stream cannot attribute a post-purge callback
						# to a new request. Require resource replacement after an
						# ordinary failure rather than accepting a false successor drain.
						self._failSegmentControl(failure)
				except Exception as control_error:
					self._failSegmentControl(control_error)
			finally:
				# A feed admitted before cancellation may return after stop. Its
				# final stop and lease must retire before a successor uses the player.
				with self._threadCond:
					self._threadCond.wait_for(lambda: native.feeds == 0)
				if not native.is_valid() or error is not None:
					try:
						try:
							player.stop()
						finally:
							# Token-only cancellation does not enter the parent's purge
							# path. Retire this exact bookmark deque and discard Sonic
							# only after all its admitted PCM callbacks have returned.
							with native.index_lock:
								native.request.bookmarks.clear()
								for index, bookmarks in enumerate(self._bookmarkLists):
									if bookmarks is native.request.bookmarks:
										del self._bookmarkLists[index]
										break
							sonic.flush()
							sonic.readShort()
					except Exception as control_error:
						self._failSegmentControl(control_error)
				with self._threadCond:
					self._segmentNative = None
				if binding is not None:
					if error is not None:
						native.error = error
					binding.boundary.set()
					binding.retired.set()
					binding.playback_done.wait()
					binding.handoff.wait()

	def _purgeCancelledSpeech(self, tts, sonic):
		tts.Speak(None, sapi5.SpeechVoiceSpeakFlags.Async | sapi5.SpeechVoiceSpeakFlags.PurgeBeforeSpeak)
		self._bookmarkLists.clear()
		if sonic:
			sonic.flush()
			sonic.readShort()
		with self._threadCond:
			self._isCancelling = False

	def cancel(self):
		with self._threadCond:
			self._segmentStops += 1
			self._invalidateSegments()
		try:
			return super().cancel()
		finally:
			with self._threadCond:
				self._segmentStops -= 1
				self._threadCond.notify_all()

	def terminate(self):
		self._segmentTerminated = True
		self._invalidateSegments()
		self._segmentLifecycle.terminate()
		if self._segmentSink is not None:
			self._segmentSink.detach()
		self._segmentSink = None
		self._segmentAudio = None
		return super().terminate()


class Voice(Voice):
	core = None
	engine = "SAPI5"

	synth_driver_class = SynthDriver
