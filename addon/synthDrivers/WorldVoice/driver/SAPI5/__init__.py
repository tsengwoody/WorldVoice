import weakref
from dataclasses import dataclass, field
from threading import RLock, Thread

from logHandler import log
from synthDriverHandler import synthIndexReached
from synthDrivers import sapi5
from synthDrivers.sapi5 import SynthDriver as BaseSynthDriver
from synthDrivers.WorldVoice.driver import Voice

from ...runtime.engineControl import ControlFaultPolicy, QueuedRecords, StopGate
from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
from ...runtime.playbackWork import DrainProfile, DrainSupport, unverified_drain_support
from ...runtime.segmentHost import LeasedPlayer, NativeStrategy, SegmentDrainCore, SegmentHost
from ...runtime.session import CancellationView

# Ordinary requests keep the parent's queue-empty idle, so they prove no idle.
_ORDINARY_BARRIERS = frozenset({"ended", "processed"})


@dataclass(eq=False)
class _SapiRequest:
	"""SAPI5 data carried on a NativeRecord: the request and its resources."""

	request: object | None = None
	stream: int | None = None
	indexLock: object = field(default_factory=RLock)
	# Snapshots taken when the worker starts the request; a reload replaces
	# the driver's resources but this request keeps controlling its own.
	tts: object | None = None
	player: object | None = None
	sonic: object | None = None


def _purgeFlags():
	return sapi5.SpeechVoiceSpeakFlags.Async | sapi5.SpeechVoiceSpeakFlags.PurgeBeforeSpeak


class _Sapi5Port:
	"""NVDA synthDrivers.sapi5 private names this wrapper reads, writes or overrides.

	The worker (_speakThread) re-implements NVDA's own loop around these, so
	they are used in place rather than forwarded; compare this list with
	NVDA's sapi5.py on every NVDA upgrade.
	"""

	NVDA_PRIVATES = frozenset(
		{
			"_SPEventEnum",
			"_SapiEvent",
			"_bookmarkLists",
			"_isCancelling",
			"_isCompleted",
			"_isSpeaking",
			"_isStoppingThread",
			"_requestCompleted",
			"_requestsAvailable",
			"_speakRequests",
			"_thread",
			"_threadCond",
		},
	)
	NVDA_OVERRIDES = frozenset({"_initTts", "_initWasapiAudio", "_onEndStream", "_speakThread"})


class _Sapi5Strategy(NativeStrategy):
	"""SAPI5's native queue: the parent's request deque and the outer worker."""

	barriers = frozenset({"ended", "processed", "idle"})

	def __init__(self, driver):
		self._driver = weakref.ref(driver)

	def admission_error(self, host):
		driver = self._driver()
		with driver._threadCond:
			try:
				driver._checkWorker()
			except Exception as error:  # noqa: BLE001 - returned as the admission error
				return error
			if not driver.useWasapi or driver.player is None:
				return RuntimeError("Correlated SAPI5 playback requires the WASAPI player")
		return None

	def submit(self, host, record, commands):
		driver = self._driver()
		with driver._threadCond:
			driver._checkWorker()
			# NVDA owns XML conversion; bind while its reentrant queue lock is held.
			BaseSynthDriver.speak(driver, commands)
			request = driver._speakRequests[-1]
			if record.native is None:
				# Segments arrive through the lifecycle's submit_native hook.
				record.native = _SapiRequest()
			record.native.request = request
			driver._queued.add(id(request), record)

	def stop_native(self, host, record):
		driver = self._driver()
		with driver._threadCond:
			if host.current() is record:
				driver._isCancelling = True
				driver._threadCond.notify_all()
		player = record.native.player
		if player is not None:
			try:
				player.stop()
			except Exception as error:  # noqa: BLE001 - latched: the player or engine state is unknown
				driver._failSegmentControl(error)

	def stop_player(self, host):
		driver = self._driver()
		if driver.player is not None:
			driver.player.stop()

	def drain(self, host, record):
		native = record.native
		player = native.player
		if player is None:
			host.record_error(record, RuntimeError("SAPI5 segment has no WASAPI player to drain"))
			return
		try:
			player.idle()
		except Exception as error:  # noqa: BLE001 - recorded on the record; the segment fails
			host.record_error(record, error)
			try:
				player.stop()
				native.tts.Speak(None, _purgeFlags())
			except Exception as controlError:  # noqa: BLE001 - latched: the player or engine state is unknown
				self._driver()._failSegmentControl(controlError)
			return
		host.reach(record, "idle")


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
		host = driver._segmentHost
		record = host.current()
		if record is None:
			return sapi5.hresult.S_OK
		# Ordinary PCM callbacks also retain this request's resources. Voice
		# reload/termination must join the worker only after they have retired.
		with host.consumer(record) as admitted:
			if admitted is None:
				return sapi5.hresult.S_OK
			with host.bound_callback(record):
				try:
					return super().ISequentialStream_RemoteWrite(this, pv, cb, pcbWritten)
				except Exception as error:
					driver._recordSegmentError(record, error)
					raise


class _SegmentPlayer(LeasedPlayer):
	"""SAPI5's WavePlayer lease: legacy feeds pass through, index callbacks outlive admission."""

	def __init__(self, driver, player):
		super().__init__(driver._segmentHost, player, idle_barrier=None)
		self._driver = weakref.ref(driver)

	def feed(self, data, size=None, onDone=None):
		driver = self._driver()
		if driver is None:
			return None
		with driver._threadCond:
			if self is not driver.player:
				return None
		host = driver._segmentHost
		record = host.current()
		if record is None:
			return self._player.feed(data, size, onDone)
		# Admit the record just read, so a retire/begin in between cannot hand
		# this feed to the successor. A feed nested in an admitted PCM callback
		# may pass after EndStream closed admission; any other late feed is dropped.
		with host.consumer(record) as admitted:
			if admitted is None:
				return None
			return self._feed_admitted(admitted, data, size, onDone)

	def _callback(self, record, onDone):
		# NVDA queues bookmark indexes as feed(None, 0, onDone); they fire after
		# EndStream closed admission, while the record is still valid.
		def callback():
			if record.is_valid():
				onDone()

		return callback

	def _record_error(self, record, error):
		driver = self._driver()
		if driver is None:
			return super()._record_error(record, error)
		driver._recordSegmentError(record, error)

	def _stop_failed(self, error):
		driver = self._driver()
		if driver is None:
			return super()._stop_failed(error)
		driver._failSegmentControl(error)

	def idle(self):
		driver = self._driver()
		if driver is None:
			return self._player.idle()
		with driver._threadCond:
			record = driver._segmentHost.current() if self is driver.player else None
		try:
			# WavePlayer.idle may wait for playback or for stop(). Never hold
			# the request lock while it runs: cancel needs that lock to stop it.
			result = self._player.idle()
			with driver._threadCond:
				current = self is driver.player and driver._segmentHost.current() is record
			if (
				current
				and record is not None
				and record.work is not None
				and record.work.is_valid()
				and not record.barriers.get("processed")
			):
				raise RuntimeError("SAPI5 player idle preceded the segment end notification")
			return result
		except Exception as error:
			if record is not None and record.work is not None:
				driver._recordSegmentError(record, error)
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
			record = driver._segmentHost.current()
			if record is None:
				return driver, None
			native = record.native
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
			return driver, record

	def StartStream(self, streamNum, pos):
		driver, record = self._native(streamNum)
		if record is not None and record.is_valid():
			return super().StartStream(streamNum, pos)
		if driver is not None and self is driver._segmentSink and not driver.player:
			return super().StartStream(streamNum, pos)

	def Bookmark(self, streamNum, pos, bookmark, bookmarkId):
		driver, record = self._native(streamNum)
		if record is None:
			# Legacy audio has no worker/native record.
			if driver is not None and self is driver._segmentSink and not driver.player:
				return super().Bookmark(streamNum, pos, bookmark, bookmarkId)
			return
		if not record.is_valid():
			return
		return super().Bookmark(streamNum, pos, bookmark, bookmarkId)

	def onIndexReached(self, streamNum, index):
		driver, record = self._native(streamNum)
		if record is None:
			if driver is not None and self is driver._segmentSink and not driver.player:
				return super().onIndexReached(streamNum, index)
			return
		if not record.is_valid():
			return
		if record.work is None:
			return super().onIndexReached(streamNum, index)
		native = record.native
		with native.indexLock:
			bookmarks = native.request.bookmarks
			if not record.work.is_valid() or index not in bookmarks:
				return
			while bookmarks:
				if bookmarks.popleft() == index:
					break
			if record.work.is_valid():
				synthIndexReached.notify(synth=driver, index=index)

	def EndStream(self, streamNum, pos):
		driver, record = self._native(streamNum)
		if record is None:
			if driver is not None and self is driver._segmentSink and not driver.player:
				return super().EndStream(streamNum, pos)
			return
		with driver._threadCond:
			# Lookup may have admitted this callback before reload replaced the
			# sink/native request. Revalidate and transition worker state together;
			# the inherited method would resolve mutable driver state again.
			if self is not driver._segmentSink or driver._segmentHost.current() is not record:
				return
			# A cancelled token still consumes its native terminal notification
			# so the worker can retire this identity without publishing success.
			driver._segmentHost.reach(record, "ended")
			if driver._isCancelling:
				driver._bookmarkLists.clear()
				return
			driver._isCompleted = True
			driver._threadCond.notify()


class SynthDriver(BaseSynthDriver, SegmentDrainCore):
	"""Correlate each WASAPI request with its final real idle barrier."""

	def __init__(self, *args, **kwargs):
		self._segmentHost = SegmentHost("SAPI5", _Sapi5Strategy(self))
		self._queued = QueuedRecords()
		self._stopGate = None
		self._controlFault = None
		self._segmentSeenStreams = set()
		self._segmentSink = None
		self._segmentAudio = None
		super().__init__(*args, **kwargs)
		self._ensureEngineControl()

	def _ensureEngineControl(self):
		# NVDA creates _threadCond in its __init__ and may start the worker there.
		if self._controlFault is None:
			self._stopGate = StopGate(self._threadCond)
			self._controlFault = ControlFaultPolicy(self._segmentHost, self._threadCond, self._dropQueued)

	def get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport:
		if audio_mode != "wasapi" or not self.useWasapi or self.player is None:
			return DrainSupport(
				False,
				"sapi5-legacy-audio",
				"SAPI5 legacy audio has no owned player idle barrier",
			)
		return unverified_drain_support(
			"sapi5-wasapi",
			"callback retirement, loaded profile provenance and physical playback are",
		)

	def speak_segment(
		self,
		commands: SpeechCommands,
		token: CancellationView,
		*,
		context: PlaybackContext,
		on_event: SegmentEventSink,
	) -> None:
		self._segmentHost.speak_segment(commands, token, context=context, on_event=on_event)

	def _checkWorker(self):
		if self.useWasapi and (self._thread is None or not self._thread.is_alive()):
			raise RuntimeError("SAPI5 playback worker is unavailable")

	def _checkSpeechAdmission(self):
		host = self._segmentHost
		if host.terminated:
			raise RuntimeError("SAPI5 driver has terminated")
		if host.control_error is not None:
			raise host.control_error
		self._checkWorker()

	def speak(self, speechSequence):
		with self._threadCond:
			self._checkSpeechAdmission()
			if not self.useWasapi:
				# Legacy audio speaks synchronously in the parent; no worker record.
				return super().speak(speechSequence)
		self._segmentHost.enqueue(speechSequence, barriers=_ORDINARY_BARRIERS, native=_SapiRequest())

	def _dropQueued(self):
		# Called under _threadCond: the parent's request deque is being cleared,
		# so these records never reach the worker.
		self._speakRequests.clear()
		return self._queued.take_all()

	def _invalidateSegments(self):
		with self._segmentHost.admission():
			with self._threadCond:
				self._segmentHost.cancel()
				dropped = self._dropQueued()
			for record in dropped:
				self._segmentHost.abandon(record)

	def _initTts(self, voice=None):
		self._invalidateSegments()
		if self._segmentSink is not None:
			self._segmentSink.detach()
		self._segmentSink = None
		self._segmentAudio = None
		super()._initTts(voice)
		self._segmentSeenStreams.clear()
		if not self.useWasapi:
			self._segmentHost.reset()
		if self.player is not None:
			self.player = _SegmentPlayer(self, self.player)
		self._segmentSink = _SegmentSapiSink(weakref.ref(self), self.tts.QueryInterface(sapi5.ISpEventSource))
		self.tts.QueryInterface(sapi5.ISpNotifySource).SetNotifySink(self._segmentSink)

	def _initWasapiAudio(self):
		# The parent has already joined and replaced the old resources here.
		# Clear their control fault (and any lifecycle fault) before the
		# replacement worker starts.
		self._segmentHost.reset()
		self._ensureEngineControl()
		# The inner initializer constructs its own fixed AudioStream class.
		# Keep its format/settings/player path, substituting only our owned
		# COM callback object so pre-feed Sonic failures cannot escape capture.
		audio = self._segmentAudio = _SegmentAudioStream(weakref.ref(self))
		self.tts.QueryInterface(sapi5.ISpVoice).SetOutput(audio, True)
		wfx = audio.waveFormat
		self.player = sapi5.nvwave.WavePlayer(
			channels=wfx.nChannels,
			samplesPerSec=wfx.nSamplesPerSec,
			bitsPerSample=wfx.wBitsPerSample,
			outputDevice=sapi5.config.conf["audio"]["outputDevice"],
		)
		sapi5.sonicInitialize()
		self.sonicStream = sapi5.SonicStream(wfx.nSamplesPerSec, wfx.nChannels)
		self._thread = Thread(target=self._speakThread, name="Sapi5SpeakThread")
		self._thread.start()

	def _recordSegmentError(self, record, error):
		self._segmentHost.record_error(record, error)
		with self._threadCond:
			if self._segmentHost.current() is record:
				self._isCompleted = True
				self._threadCond.notify_all()

	def _onEndStream(self):
		host = self._segmentHost
		record = host.current()
		if record is None:
			return super()._onEndStream()
		if record.work is None:
			result = super()._onEndStream()
			host.reach(record, "processed")
			return result
		if not record.barriers["ended"]:
			raise RuntimeError("SAPI5 request completed without its stream end marker")
		# Preserve ordinary source notifications, including untriggered tail
		# bookmarks, without publishing the parent's pre-idle anonymous DONE.
		native = record.native
		with native.indexLock:
			while native.request.bookmarks:
				bookmark = native.request.bookmarks.popleft()
				if record.work.is_valid():
					synthIndexReached.notify(synth=self, index=bookmark)
		if self._bookmarkLists:
			self._bookmarkLists.popleft()
		self._isSpeaking = False
		host.reach(record, "processed")

	def _failSegmentControl(self, error):
		self._controlFault.fail(error)

	def _speakThread(self):
		# NVDA publishes DONE before idle, only idles when its whole queue is
		# empty, and swallows synthesis/Sonic failures. Those hooks cannot prove
		# one segment's barrier or propagate worker faults, so the outer worker
		# retains native request identity and drains each correlated request.
		# Ordinary requests keep the parent's queue-empty idle/DONE behavior.
		host = self._segmentHost
		while True:
			with self._threadCond:
				self._threadCond.wait_for(
					lambda: (
						self._isStoppingThread
						or host.control_error is not None
						or (self._stopGate.clear and self._requestsAvailable())
					),
				)
				if self._isStoppingThread or host.control_error is not None:
					return
				if self._isCancelling:
					record = None
				else:
					request = self._speakRequests.popleft()
					record = self._queued.pop(id(request))
					if record is None:
						# Not queued through the host (e.g. after a reload race).
						record = host.new_record(barriers=_ORDINARY_BARRIERS, native=_SapiRequest(request))
					work = record.work
					if work is not None and not work.is_valid():
						host.abandon(record)
						continue
					native = record.native
					host.begin(record)
					self._isCompleted = False
					tts, player, sonic = self.tts, self.player, self.sonicStream
					native.tts, native.player, native.sonic = tts, player, sonic
			if record is None:
				try:
					self._purgeCancelledSpeech(self.tts, self.sonicStream)
				except Exception as error:  # noqa: BLE001 - latched: the player or engine state is unknown
					self._failSegmentControl(error)
				continue
			error = None
			self._bookmarkLists.append(request.bookmarks)
			try:
				stream = tts.Speak(
					request.text,
					sapi5.SpeechVoiceSpeakFlags.IsXML | sapi5.SpeechVoiceSpeakFlags.Async,
				)
				with self._threadCond:
					if native.stream is not None and native.stream != stream:
						raise RuntimeError("SAPI5 callback stream did not match the admitted request")
					native.stream = stream
					self._segmentSeenStreams.add(stream)
					self._threadCond.wait_for(self._requestCompleted)
				if work is not None or record.cancelled:
					# EndStream closes new audio admission. Retire every feed
					# already admitted before flushing/final idle and checking errors.
					host.close(record)
					host.wait_consumers(record)
				if record.error is not None:
					raise record.error
				if not self._isCancelling and not self._isStoppingThread and record.is_valid():
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
					if record.error is not None:
						raise record.error
				if self._isCancelling:
					self._purgeCancelledSpeech(tts, sonic)
			except Exception as failure:
				error = failure
				log.error("Error speaking SAPI5 request", exc_info=True)
				if self._bookmarkLists:
					self._bookmarkLists.clear()
				try:
					# No new PCM may enter this failed request while its native
					# callbacks retire and the SAPI stream is purged.
					host.close(record)
					try:
						player.stop()
					finally:
						host.wait_consumers(record)
						# Both ordinary and correlated failures leave native speech
						# uncertain. Purge before another request can take this player.
						tts.Speak(None, _purgeFlags())
					if work is None:
						# One shared COM stream cannot attribute a post-purge callback
						# to a new request. Require resource replacement after an
						# ordinary failure rather than accepting a false successor drain.
						self._failSegmentControl(failure)
				except Exception as controlError:  # noqa: BLE001 - latched: the player or engine state is unknown
					self._failSegmentControl(controlError)
			finally:
				# A feed admitted before cancellation may return after stop. Its
				# final stop must retire before a successor uses the player.
				host.wait_consumers(record)
				if not record.is_valid() or error is not None:
					try:
						try:
							player.stop()
						finally:
							# Token-only cancellation does not enter the parent's purge
							# path. Retire this exact bookmark deque and discard Sonic
							# only after all its admitted PCM callbacks have returned.
							with native.indexLock:
								request.bookmarks.clear()
								for index, bookmarks in enumerate(self._bookmarkLists):
									if bookmarks is request.bookmarks:
										del self._bookmarkLists[index]
										break
							sonic.flush()
							sonic.readShort()
					except Exception as controlError:  # noqa: BLE001 - latched: the player or engine state is unknown
						self._failSegmentControl(controlError)
				if error is not None:
					host.record_error(record, error)
				# Segments wait here for the lifecycle's handoff; their drain runs
				# on the lifecycle thread. Ordinary records retire immediately.
				if host.retire(record) is not None:
					host.forget(record)

	def _purgeCancelledSpeech(self, tts, sonic):
		tts.Speak(None, _purgeFlags())
		self._bookmarkLists.clear()
		if sonic:
			sonic.flush()
			sonic.readShort()
		with self._threadCond:
			self._isCancelling = False

	def cancel(self):
		with self._stopGate.hold():
			self._invalidateSegments()
			return super().cancel()

	def terminate(self):
		self._invalidateSegments()
		self._segmentHost.terminate()
		if self._segmentSink is not None:
			self._segmentSink.detach()
		self._segmentSink = None
		self._segmentAudio = None
		return super().terminate()


class Voice(Voice):
	engine = "SAPI5"
	drain_profile = DrainProfile(wasapi_dependent=True)

	synth_driver_class = SynthDriver
