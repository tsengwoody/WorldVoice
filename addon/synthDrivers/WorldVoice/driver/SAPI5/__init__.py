from dataclasses import dataclass, field
from threading import RLock, Thread, local
import weakref

from synthDrivers import sapi5
from synthDrivers.sapi5 import SynthDriver as BaseSynthDriver
from synthDriverHandler import synthIndexReached
from logHandler import log
from synthDrivers.WorldVoice.driver import Voice
from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import DrainSupport, PlaybackWork
from ...runtime.session import CancellationView


@dataclass(eq=False)
class _NativeRequest:
	request: object
	work: PlaybackWork | None
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
			# Ordinary PCM callbacks also retain this request's resources. Voice
			# reload/termination must join the worker only after they have retired.
			native.feeds += 1
		previous = getattr(driver._segmentCallbackLocal, "native", None)
		driver._segmentCallbackLocal.native = native
		try:
			return super().ISequentialStream_RemoteWrite(this, pv, cb, pcbWritten)
		except Exception as error:
			if native is not None:
				driver._recordSegmentError(native, error)
			raise
		finally:
			driver._segmentCallbackLocal.native = previous
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
				native.feeds += 1
			else:
				native = None
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
			result = self._player.idle()
			if (native is not None and native.work is not None and native.work.is_valid()
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
				native.stream = stream
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
				return
			driver._isCompleted = True
			driver._threadCond.notify()


class SynthDriver(BaseSynthDriver):
	"""Correlate each WASAPI request with its final real idle barrier."""

	def __init__(self, *args, **kwargs):
		self._segmentRequests = {}
		self._segmentWorks = set()
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
		return DrainSupport(False, "sapi5-wasapi-unverified",
			"SAPI callback retirement, loaded profile provenance and physical playback have not been verified")

	def speak_segment(self, commands: SpeechCommands, token: CancellationView, *,
		context: PlaybackContext, on_event: SegmentEventSink) -> None:
		work = PlaybackWork(context, token, on_event)
		if not work.is_valid():
			return
		try:
			with self._threadCond:
				if self._segmentTerminated:
					raise RuntimeError("SAPI5 driver has terminated")
				if self._segmentControlError is not None:
					raise self._segmentControlError
				if not self.useWasapi or self.player is None:
					raise RuntimeError("Correlated SAPI5 playback requires the WASAPI player")
				self._segmentWorks.add(work)
				# Retain NVDA's complete XML/index conversion. Its reentrant queue
				# lock prevents the worker from taking this request before binding.
				super().speak(tuple(commands))
				request = self._speakRequests[-1]
				self._segmentRequests[id(request)] = work
		except Exception as error:
			self._deliverSegment(work, error)

	def _invalidateSegments(self):
		with self._threadCond:
			if self._segmentNative is not None:
				self._segmentNative.cancelled = True
			for work in self._segmentWorks:
				work.cancel()
			self._segmentWorks.clear()
			self._segmentRequests.clear()
			self._speakRequests.clear()

	def _initTts(self, voice=None):
		self._invalidateSegments()
		if self._segmentSink is not None:
			self._segmentSink.detach()
		self._segmentSink = None
		self._segmentAudio = None
		super()._initTts(voice)
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

	def _deliverSegment(self, work, error=None):
		def deliver():
			try:
				if error is None:
					work.complete_drained()
				else:
					work.fail(error)
			except Exception:
				log.error("SAPI5 segment event delivery failed", exc_info=True)
			finally:
				with self._threadCond:
					self._segmentWorks.discard(work)
		# A terminal sink can synchronously terminate/join the SAPI worker.
		# It must never run on that worker or a COM/player callback stack.
		Thread(target=deliver, name="WorldVoice SAPI5 completion", daemon=True).start()

	def _failSegmentControl(self, error):
		with self._threadCond:
			if self._segmentControlError is not None:
				return
			self._segmentControlError = error
			current = self._segmentNative.work if self._segmentNative is not None else None
			works = tuple(work for work in self._segmentWorks if work is not current)
			self._speakRequests.clear()
			self._segmentRequests.clear()
			self._threadCond.notify_all()
		for work in works:
			self._deliverSegment(work, error)

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
					work = self._segmentRequests.pop(id(request), None)
					if work is not None and not work.is_valid():
						self._segmentWorks.discard(work)
						continue
					native = _NativeRequest(request, work)
					self._segmentNative = native
					self._isCompleted = False
					tts, player, sonic = self.tts, self.player, self.sonicStream
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
					if work is not None or not self._requestsAvailable():
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
					try:
						player.stop()
					finally:
						if work is not None:
							# A player failure does not establish native quiescence.
							# Purge while retaining this callback identity.
							tts.Speak(None, sapi5.SpeechVoiceSpeakFlags.Async | sapi5.SpeechVoiceSpeakFlags.PurgeBeforeSpeak)
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
				if work is not None:
					self._deliverSegment(work, error)

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
		if self._segmentSink is not None:
			self._segmentSink.detach()
		self._segmentSink = None
		self._segmentAudio = None
		return super().terminate()


class Voice(Voice):
	core = None
	engine = "SAPI5"

	synth_driver_class = SynthDriver
