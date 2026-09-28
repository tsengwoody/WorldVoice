# Correlated drain validation

## Task 5: OneCore source contract evidence (2026-09-28)

Reference checkout: `ref/nvda`, commit `9ef645dca8139332b8e929e1f61f3d930ebf72c7`
(`Add visual highlighting for web math navigation (#20372)`); `source/buildVersion.py`
identifies 2026.3 development sources. This is source/API evidence, not Windows
playback or compatibility certification.

| Reviewed source | SHA-256 |
| --- | --- |
| `ref/nvda/source/synthDrivers/oneCore.py` | `e762db4a0d2fd106c2fe0bbdfbc3fc50f36e72aa541a788240fa6a35c8b55692` |
| `ref/nvda/nvdaHelper/localWin10/oneCoreSpeech.cpp` | `c9a6362e39c8e6be92619375a706d1bcfa5a35c4da4d01dacf9723a8ad340abe` |
| `ref/nvda/nvdaHelper/localWin10/oneCoreSpeech.h` | `50fe7ef1d411dcaeee89ffc59fc195d6fdcd80efcbbc0f7fab0332264529527d` |
| `ref/nvda/source/nvwave.py` | `20168fa23f980d6a3857bfe8e4efab72f558fe1460f890f504eda4c8616338fc` |
| `ref/nvda/nvdaHelper/local/wasapi.cpp` | `10acce6270a54af7c76ca41373759743dae8698f59b39870e396d6c708f4e922` |

The Python constructor installs one fixed CFUNCTYPE callback in
`ocSpeech_initialize`; no per-call identifier is returned. Python's queue submits
one text at a time; settings tuples are applied without speech callbacks. Native
`ocSpeech_speak` captures the original token, synthesizer and callback before its
coroutine resumes in the thread pool. The success path calls `protectedCallback_`
with the full WAV and marker string and immediately returns. Both caught WinRT
synthesis/read failures call it with `(nullptr, 0, nullptr)` and immediately return.
The wrapper may retire this call when that single terminal callback is consumed;
cancellation alone proves no such retirement. A cancelled call must keep its
identity until its eventual success/zero-length callback is consumed.

`WavePlayer.feed` queues audio before playback ends; `sync` invokes native
`wasPlay_sync`, which waits for sent frames. Native `stop` sets stopping state and
signals the wake event, releasing feed/sync. Since sync also returns successfully
when playback is stopped, the wrapper must recheck the captured work afterward.
Python WASAPI feed swallows some native device errors; this wrapper can report
raised/observable errors, not claim detection of every device failure.

Important source limitations: invalid tokens and outer native exceptions can
return without any callback. Such a call remains pending until termination; no
successful drain is invented. `ocSpeech_terminate` normally excludes callbacks via
a unique mutex, but its three-second lock timeout returns without invalidating the
token. Therefore retaining the callback after termination is required; a return
alone is insufficient proof that its function pointer can be released.

The reviewed candidate profile is `nvda-source-9ef645d-wasapi`. Runtime checks
reject release versions and other revisions, non-WASAPI modes, changed/missing
loaded source hashes, foreign helper locations, missing native bindings and
partial initialization. Even matching source hashes/version/path return
**unsupported**: no loaded native helper DLL has verified build provenance.
A caller-supplied synthetic source version cannot attest DLL contents. No real
NVDA profile is enabled by Task 5; Task 9 must retain legacy fallback until that
evidence exists. No support is inferred from method names. Windows hardware
tests remain outstanding.

### Implemented and exercised boundary

The real outer subclass and inner language subclass are loaded over the pinned
NVDA Python OneCore implementation. Only native/Windows dependencies, converter
and player are controlled test boundaries. Frozen queued/native records capture
the original PlaybackWork before `ocSpeech_speak`. Settings tuples do not consume
speech work identity. Cancelled native identity is kept until its one terminal
callback is consumed; native submission remains blocked during an old feed and
during the caller's cancelling stop. All real feed/sync/stop/native operations
and segment notification run outside the queue state lock.

The callback feeds the full marker tail, then calls `sync` on its background
thread. Successful work is checked after the barrier and any pause; zero-length
responses, malformed/truncated WAV or unordered/out-of-range markers, raised
feed/sync and submission errors cannot be converted into a drain by the parent
queue. A paused first segment transfers its pause to a newly initialized player.
Legacy `speak` still accepts the parent interface and emits parent notifications,
including when used after correlated work.

Initial red: focused command produced 23 missing-entry/capability failures and
one passing legacy regression. Additional observed red→green regressions cover
partial initialization, actual resume before completion, legacy DONE after a
segment, rejecting unproven helper provenance, stop still in progress after an
old callback retires, and pause before initial player creation.

Focused command: `python3 -m pytest tests/test_onecore_segment_drain.py -q -p no:cacheprovider`.
Initial implementation focused result: **33 passed**. Coverage includes full tail versus blocked
sync, source/segment ownership, settings and queued cancellation, stale cancelled
success/len=0 callbacks, native/parse/player errors, empty/index/break segments,
pause/resume, terminate, sync returning due to stop, feed admission cancellation,
partial initialization and unsupported profiles.

The initial addon run found the existing composition harness assumes the first
class declaration is the Voice facade. The outer module retains that declaration
order and assigns its final `synth_driver_class` to the correlated subclass after
definition; its focused composition regression passed. Initial implementation addon suite:
`python3 -m pytest tests -q -p no:cacheprovider`: **775 passed**. Full-tree
`python3 -m pytest -q -p no:cacheprovider` exits **2**, with **191 collection
errors** in vendored NVDA suites (missing NVDA/Windows and liblouis dependencies).
The complete collection error names are in the Task 5 implementer report.
`git diff --check` passed. No Windows device, NVDA release or native helper binary
provenance has been validated.

### Task 5 review corrections

The review reproduced a cancellation gap in the parent's legacy callback after
correlated playback: an admitted feed could return after cancel's stop and leave
old audio queued. The wrapper now keeps that legacy native record/admission until
the callback's post-feed/post-sync cancellation checks and final stop complete.
The next correlated native submission waits for this cleanup. Legacy DONE is
checked after sync and idle and suppressed when cancellation/termination wins.
The regression blocks the old feed and then its final stop independently, proving
that neither barrier admits the next native call early.

The constructor now installs a ctypes callback trampoline that owns a weak,
detachable driver reference rather than a bound driver method. Terminate detaches
the trampoline before retaining its callable pointer for the helper's possible
timeout. Entered callbacks retain the driver only until their work exits; late
calls after detach safely no-op. Ordinary legacy and correlated instances are
garbage-collected in tests even while the callable pointer remains retained.
This releases the driver/player/work graph without guessing native quiescence.

Observed review red: **4 failed, 33 passed**, covering the legacy feed final stop,
cancelled legacy sync DONE, and collection in both instance modes. Review green:
focused OneCore **37 passed**, addon suite **779 passed**, diff check passed.
Full-tree pytest still exits **2** with the same **191 vendored collection errors**;
error names are retained in the implementer report, with review log
`/tmp/worldvoice-task5-review-fix-full-pytest.log`. Runtime/helper provenance remains
unverified and all current OneCore drain profiles remain unsupported.

## Task 6: Neural SDK boundary and implementation (2026-09-28)

Required user baseline: commit `eb605cd307b4e3f4665143d065788f577e6626bc`.
The original Neural snapshot (inner driver, speechapi/CFFI and DLLs) is required
to reproduce these tests or package the wrapper; an outer-only checkout is
insufficient. This task changes only `Neural/__init__.py`, its two new test files
and this validation file. All inner sources and native files retain the baseline
bytes. The SHA-256 invariant is also exercised by the focused suite.

| Baseline file relative to `driver/Neural` | Bytes | SHA-256 |
| --- | ---: | --- |
| `driver/__init__.py` | 13382 | `d866d5921434a475d240d97d88e31f81bae82cb6da5b54b06c44f9c705a48ef6` |
| `driver/speechapi/__init__.py` | 4668 | `7a86eeadfffd0cea2c00cce49b39d43ce79de0aa3c605ff944a37ca3325b881b` |
| `driver/speechapi/speechapi_cffi.py` | 47298 | `618a5d2d64574a4a0129a512b7bb73844d76d511d9b86a04243a1395fbd5d652` |
| `driver/speechapi/Microsoft.CognitiveServices.Speech.core.dll` | 2270008 | `3e3c8caaf342d99fcc144d16d72cdcccc4f979a1ba309a12b20c5457a9e57656` |
| `driver/speechapi/Microsoft.CognitiveServices.Speech.extension.audio.sys.dll` | 141624 | `3d15877e59495ffce1f818b962e7f6d9f90365cc7d328c939dac2de646ee335e` |
| `driver/speechapi/Microsoft.CognitiveServices.Speech.extension.codec.dll` | 114528 | `1210e818bbc1c35e739b48b9896ccd9d7c8a1d14c141f64056e94b3d6ed50af4` |
| `driver/speechapi/Microsoft.CognitiveServices.Speech.extension.embedded.tts.dll` | 5984568 | `89521bda1f32867625cea05887ceaf071c9e7dbe85cac6099cc73606c33bb56f` |
| `driver/speechapi/Microsoft.CognitiveServices.Speech.extension.kws.dll` | 326456 | `b69f6934483aa6c3af9d5334d23e1e5f4274465c40e8dc9f819f0885462c1d57` |
| `driver/speechapi/Microsoft.CognitiveServices.Speech.extension.kws.ort.dll` | 3137888 | `708e9de8dacd105fa40fd6985d7003c273871da7e9a149e59cb4f1597b81334b` |
| `driver/speechapi/Microsoft.CognitiveServices.Speech.extension.onnxruntime.dll` | 9959776 | `3f1e42f4fe9283267145ebd489f3600e510b9478c2bb0cbddc2e586b57a8a081` |
| `driver/speechapi/msvcp140_codecvt_ids.dll` | 31392 | `ae8d922b00cdd93e3ebecc37beb46c800f383ebdeb9f9e5b84e04a72428b6fb3` |

The core/embedded/audio/codec/kws DLL `VS_FIXEDFILEINFO` file version is
**1.50.0.28**. The ONNX Runtime DLLs identify **1.23.2.0** and the Microsoft runtime
DLL identifies **14.50.35719.0**. File versions establish what the supplied files
claim, not verified build provenance or a callback-lifetime contract.

The supplied `speechapi` registers a fixed audio callback with a CFFI handle at
stream construction. Its bookmark setter replaces its CFFI handle; its synchronous
`speak_ssml` waits for a result and reads the result reason. The existing
`stop_async` creates an async handle, wraps it with `ffi.gc`, then discards that
wrapper without waiting. The outer wrapper does not call that method. Its own
stop operation holds the handle from `synthesizer_stop_speaking_async`, waits with
`synthesizer_stop_speaking_async_wait_for(handle, 0xffffffff)`, and explicitly
releases it with `synthesizer_async_handle_release` in the background, including
wait-error paths. These three symbols are present in the supplied CFFI binding.
Their presence proves an API declaration only.

Reviewed primary documentation:
[Microsoft C++ SpeechSynthesizer](https://learn.microsoft.com/en-us/cpp/cognitive-services/speech/speechsynthesizer)
describes synchronous SSML synthesis and an asynchronous stop future;
[Microsoft .NET StopSpeakingAsync](https://learn.microsoft.com/en-us/dotnet/api/microsoft.cognitiveservices.speech.speechsynthesizer.stopspeakingasync?view=azure-dotnet)
describes stopping synthesis and discarding unread pull-stream data.
Neither establishes that the delivered Embedded SDK 1.50.0.28 stops initiating
push-audio and bookmark callbacks before stop completion or synchronous speak
return. No matching SDK implementation/source contract or loaded binary build
provenance was delivered. This absence is not filled by temporarily observing
zero callbacks.

Accordingly, **all actual Neural profiles remain unsupported** with profile
`embedded-speech-1.50.0.28-unverified` and a specific reason naming the missing
audio/bookmark quiescence, SDK provenance and NVDA playback profile. Task 9 must
choose legacy before playback. This task does not enable Neural DRAIN. The public
segment implementation remains available, but its default native-proof boundary
raises after waiting stop; it closes admission, waits entered leases, reports
failure and keeps the old call identity instead of finishing/reopening its gate.
An unproven call cannot turn its eventual late audio into the next segment.

### Real-wrapper boundary exercised

Tests load the real outer class, the delivered inner driver and `speechapi` Python
constructors over a controlled fake CFFI/native DLL boundary. The native stream
retains the constructor-installed callback handle; tests verify that it owns the
same `_ContextualAudioCallback` used by the core. The fake's explicitly promised
stop-quiescence boundary is injected only after the real stop-handle wait/release
code. It never changes `get_segment_drain_support` and supplies no real SDK proof.

LangChange tasks capture one PlaybackWork, original voice/synth, command tuples
and independent settings snapshots. They flush after native proof and entered
audio/bookmark callback retirement, and one final task waits `player.idle()` and
resume before publishing a single contextual drain. SDK non-success, task,
player and post-start Sonic processing/flush failures latch one failure. Sonic
initialization before speech retains native-rate fallback; cancellation discards
an old Sonic stream's internal PCM after its callbacks retire.

Cancel invalidates queued/active work, closes old admission, stops the player and
requests stop on the saved actual native synth. New work waits the cancelling
player stop, synchronous speak exit, SDK stop completion/proof and admitted
callback exit. Tests independently withhold each barrier, including a bookmark
handler. Old bookmark handles survive the barriers and old callables never borrow
a successor's context. Stop initiated before speak entry is followed by another
owned stop after speak exits. No SDK global callback/class symbol is patched.

Legacy playback remains available with the same settings/language splitting and
anonymous DONE behavior, while cancellation suppresses old index/DONE and waits
the captured native synth's stop handle. Legacy-to-correlated switching is
rejected after pending or prior legacy work because its SDK callback lifetimes
are unproven. Termination waits entered callbacks and the worker, including when
no native quiescence proof exists. Reentrant termination from a failure sink
defers joining until that callback exits. Unknown native resources/handles stay
retained with detached or weak callbacks until process exit; they do not retain
the driver/player/work graph. This retention is a consequence of the missing
native destruction/quiescence guarantee, not hardware validation.

Observed TDD red: **25 failed, 1 passed** (missing segment/capability/callback
ownership APIs plus a passing legacy regression). Further observed red→green
regressions covered cancel's still-running stop, termination with an admitted
callback, cancelled legacy indexes, legacy driver retention, reentrant callback
termination, queued legacy switching, and cancelled Sonic internal tail leakage.

Final focused command:
`python3 -m pytest tests/test_neural_segment_drain.py -q -p no:cacheprovider`:
**36 passed**. Final addon command:
`python3 -m pytest tests -q -p no:cacheprovider`: **815 passed**.
`git diff --check` passed. Full-tree
`python3 -m pytest -q -p no:cacheprovider` exits **2**, with the existing **191
vendored NVDA collection errors** (unavailable Windows/NVDA/liblouis dependencies).
Log: `/tmp/worldvoice-task6-full-pytest.log`; all error paths are copied to the
Task 6 implementer report. No Windows device, SDK callback-quiescence contract,
loaded native provenance or real NVDA audio profile was certified.

## Task 7: VE constructor, callback ownership and drain boundary (2026-09-28)

Implementation baseline: `85a25b7`. The inner VE driver and ve2 binding remain
unchanged; no base module class or global callback symbol is patched. Task 6
sources and tests are unchanged.

| Reviewed file relative to `driver/VE` | SHA-256 |
| --- | --- |
| `driver/__init__.py` | `1245b038be229ba4427e51b87a2dbb9f40f7ea5e7f0aed1c1927ce0ef8ba2f85` |
| `driver/ve2/__init__.py` | `ad3b1f67d27f090121954e9a249dea322334df6f7d3a28ae5a4dec21a54d86d5` |
| `driver/ve2/veTypes.py` | `9efbb425b977780e1a0521f23098dd69f7795e3059215cab968fff8bc9395d1b` |

The binding loads external `WorldVoice-workspace/VE/lib/<architecture>/ve.dll`
and `vplatform.dll`; this checkout supplies no matching SDK binaries, headers or
native implementation. A loaded SDK version or build provenance cannot be
established here. `ve2.open` registers the supplied `VE_CBOUTNOTIFY` in
`ve_ttsSetOutDevice`. `ve2.processText2Speech` builds a UTF-8 `VE_INTEXT`, calls
`ve_ttsProcessText2Speech` directly, then discards its return value. Its native
errcheck accepts both `NUAN_OK` and `NUAN_E_TTS_USERSTOP`. The supplied Python
source provides no guarantee that a returned call cannot initiate another PCM,
bookmark or ENDPROCESS callback, including after cancellation or an error.

Primary documentation reviewed:
[Nuance Vocalizer API architecture](https://docs.nuance.com/nuance-vocalizer-for-enterprise/voc-dev/arch_stand.html)
describes synchronous synthesis and streamed destination callbacks for an
`lhstts` library. Its [TtsProcessEx API](https://docs.nuance.com/nuance-vocalizer-for-enterprise/voc-dev/fn-TtsProcessEx.html)
describes a different entry point and structure. These pages do not establish
the exact callback-exclusion contract for this externally loaded VE `ve.dll`
profile. Synchronous function naming, ENDPROCESS, idle return and a temporary
zero callback count supply no missing native evidence.

Consequently **all real VE drain profiles remain unsupported**, with profile
`vocalizer-expressive2-ve2-unverified` and a concrete reason identifying
`ve_ttsProcessText2Speech` callback exclusion, loaded SDK version/build provenance
and NVDA playback profile. A failed/missing guard has its own unsupported reason.
Task 9 must select legacy before playback. This task does not certify or enable
VE DRAIN on any real SDK or NVDA release.

### Implemented and exercised boundary

The outer `SynthDriver(BaseSynthDriver)` owns initialization, constructs its
`_ContextualVECallback` and ctypes callable before the first `ve2.open`, and
retains `CancellableSynthDriver = SynthDriver` plus the Voice facade binding.
The harness executes that real constructor over controlled NVDA/native
boundaries; it no longer replaces the VE base constructor with an original
callback. The native open stub retains the actual constructor-created ctypes
callable, and tests invoke it to check ownership and rejection outside a call.
Guard installation, partial-field fallback and complete reference restoration
remain covered for both VE and the existing Cerence wrapper.

A synchronous batch has one saved work across text pieces and LangChange voice
instances. Each native chunk saves its actual instance and opaque call token.
PCM, Sonic, `ulMrkId` bookmarks and ENDPROCESS use the admitted call lease,
including any post-feed cancellation stop. ENDPROCESS flushes only its chunk;
anonymous index `None` never completes contextual work. Processing errors latch
the first error, close admission, safely return USERSTOP to native and deliver
one failure after callback retirement. The outer ProcessText2Speech helper uses
the original `VE_INTEXT` layout and native entry point while retaining its return
status: an unsolicited USERSTOP cannot become success; cancellation-triggered
USERSTOP remains silent and preserves legacy anonymous DONE behavior.

The final real `player.idle()` supplies this batch's playback evidence. Work is
rechecked after idle, pause/resume and cancelling stop retirement. Direct cancel
invalidates pending/active contextual work through terminal publication, even
when idle has already returned. Serialization prevents the next native call
from taking the player until all admitted callbacks and their final stops exit.
Sonic initialization fallback remains available; cancelled internal Sonic tails
are discarded before new work, and write/read/flush failures remain failures.

Tests inject `_confirm_native_quiescence` only with an explicit fake contract
that excludes future native callbacks after call return. This injection does
not alter capability reporting. The production boundary raises instead: it
closes admission, waits already-entered leases, reports failure and keeps the
old call identity without finishing or reopening its correlated gate. Late
callbacks cannot mutate a later buffer. Legacy playback keeps its existing
return-time compatibility assumption, with callback/stop retirement added;
prior legacy use prevents switching that core into correlated mode because its
native callback lifetimes remain unproven. No fake test supplies real SDK proof.

Observed initial red: **21 failed**, covering missing callback ownership,
segment and capability APIs. Additional observed red-to-green regressions
covered dropped native USERSTOP status, direct cancellation after idle return,
and cancellation-triggered USERSTOP legacy compatibility.

Final required command:
`python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py -q -p no:cacheprovider`:
**97 passed**. Addon command `python3 -m pytest tests -q -p no:cacheprovider`:
**854 passed**. `git diff --check` passed. Full-tree
`python3 -m pytest -q -p no:cacheprovider` exits **2** with the existing **191
vendored NVDA collection errors**, caused by unavailable Windows/NVDA/liblouis
dependencies. Log: `/tmp/worldvoice-task7-full-pytest.log`; all error paths are
copied to the Task 7 implementer report. No Windows playback device, matching VE
SDK callback-exclusion contract, loaded binary provenance or real audio profile
was validated; VE DRAIN enablement acceptance remains outstanding.

### Task 7 review corrections

Review found that the initial raw-result path still used the binding's shared
ctypes function with its installed `veCheckForError`. That checker returns
`None` for both accepted native statuses, so the first harness, which returned
integers directly, did not represent the delivered ABI behavior. The corrected
harness uses a real ctypes CFuncPtr and the real checker, including deterministic
end-to-end success, USERSTOP and native error cases.

The outer ProcessText2Speech now creates an independent callable from the
original ctypes function class and address and copies its declared restype and
argtypes. This preserves the original calling convention and ABI declarations.
It invokes the captured original checker for native error handling while keeping
the raw result. It never changes the shared callable's checker, restype,
argtypes or library metadata. A concurrency regression blocks the outer call
inside native and independently invokes the original function, proving its
installed checker still masks accepted status while the outer call retains it.
Unknown native error codes still raise the original `VeError`; unsolicited
USERSTOP produces a contextual failure, and cancellation-triggered USERSTOP
remains silent with the existing legacy DONE behavior.

Cancellation now clears the wrapper's pause state and wakes waiters, matching
WavePlayer.stop's pause reset. A pause/cancel/fresh-speech regression reaches
real idle and legacy DONE without requiring pause(False).

Index and DONE notification listeners can request termination reentrantly.
Termination immediately invalidates work and rejects new native submission,
then returns to the notification when its thread owns the speech batch or a
callback lease. That batch performs cleanup after native return, callback
retirement and release of the serialization lock. Ordinary/repeated termination
waits for that cleanup. Tests cover empty speech DONE termination and native
bookmark termination, including proving that player close happens after the
synchronous native call exits. The native callback and resource ownership
barriers remain in place.

Observed review red: **6 failed, 1 passed**, covering masked accepted statuses,
concurrent original/outer function behavior, pause/cancel and both reentrant
notification paths. The passing case retained the native `VeError` contract.
The stronger harness also exposed a request-manager fixture using a string
instead of a VE_HSAFE; that fixture now uses the actual opened VE instance and
keeps the Cerence branch unchanged. Its focused regression passes **2 tests**.
Required two-file suite now passes **105 tests**. Full-tree pytest still exits
**2** with the same **191 vendored NVDA collection errors**; review log:
`/tmp/worldvoice-task7-review-fix-full-pytest.log`. Inner VE and Task 6 files remain
unchanged. Real VE drain profiles remain unsupported; native callback exclusion
and Windows playback validation are still outstanding.
Final addon suite after these corrections: **862 passed**. Final diff check passed.


## Task 8: Cerence native contract and correlated drain boundary (2026-09-28)

Implementation baseline: `22df6da`. The outer Cerence subclass uses the Task 3
`CallbackGate`/`PlaybackWork` lifecycle and the reviewed Task 7 serialization,
fault, cancellation, pause and termination barriers. Cerence retains an
independent native adapter and constructor; it does not import or assume VE's
marker layout. The inner Cerence driver, ttsapi, manifest and native files are
unchanged. Twenty baseline hashes covering the VE/Cerence/Neural inner sources,
Neural SDK/CFFI DLLs and Cerence manifest were checked without changes.

| Reviewed file relative to `driver/Cerence` | SHA-256 |
| --- | --- |
| `driver/__init__.py` | `f6f4e86c3c74e9a42061dae0588f623220158384a3ef845171cef76e6f4c7f1d` |
| `driver/ttsapi/__init__.py` | `590697c5ff3595dc140f5dcd43bdeec5ccc9b2556ca267ec8388359606c1517e` |
| `driver/ttsapi/veTypes.py` | `6235f180a4888a9db4fa84be9434b06ff9519c8dd4dc8425d705dd915b26194e` |
| `driver/ttsapi/languages.py` | `3c6016ddbbba9e2a861eddfa793e12b73376ebfc1b0fa3886d81beab32d65aa8` |
| `manifest.json` | `a4a44e20a2bed726b637b53d5e8acb99517a1373a67207ab86362dd93915ac8b` |

`ttsapi.veTypes` declares `VE_CURRENT_VERSION = 0x0520` and
`VPLATFORM_CURRENT_VERSION = 0x0200`. These installation structure versions do
not identify a loaded SDK product/build. The binding exposes
`getProductVersion` and `getAdditionalProductInfo`, but no matching SDK DLLs are
available to call them. It loads external
`WorldVoice-workspace/Cerence/lib/<architecture>/ve.dll` and `vplatform.dll`;
this checkout has no Cerence DLLs, and `/workspace/WorldVoice-workspace/Cerence`
does not exist. **Cerence ve.dll/vplatform.dll versions and SHA-256 hashes are
unavailable**, rather than assumed equal to VE or any other supplied SDK.

The supplied callback ABI is its own `CFUNCTYPE(c_uint, VE_HSAFE, c_void_p,
POINTER(VE_CALLBACKMSG))`. Its `VE_MARKINFO` contains `szValue: c_char_p` and
numeric value fields, with no VE `ulMrkId` contract. The owned callback decodes
bookmarks with `int(szValue)` as the Cerence base does; invalid, empty or null
values latch a failure and return USERSTOP instead of escaping ctypes or being
swallowed as success. `ttsapi.open` registers the constructor-owned callable in
`ve_ttsSetOutDevice`; every cached/LangChange voice instance uses that same
callable. Foreign or missing callback instances are rejected without touching
the current Sonic/feed buffer.

`ttsapi.processText2Speech` builds its own UTF-8 `VE_INTEXT`, calls
`ve_ttsProcessText2Speech` and discards the result. The installed checker accepts
OK and USERSTOP, mapping both to None. The outer helper preserves raw status by
cloning the ctypes callable using the original function type/address and declared
ABI, then invokes the original checker without mutating it. Unsolicited USERSTOP
fails contextual work; cancelled USERSTOP remains silent and legacy direct cancel
keeps its anonymous DONE behavior. The real Cerence checker still raises its own
`VeError` for an unaccepted native status.

No supplied header, implementation, binary provenance or matching API contract
establishes callback exclusion after this exact synthesis/stop/destruction API.
The exact unsupported reason is:

> The loaded Cerence ttsapi SDK has no verified callback-exclusion contract after ve_ttsProcessText2Speech returns; SDK version/build provenance and the NVDA playback profile are unverified

Consequently **all real Cerence profiles remain unsupported**, with profile
`cerence-ttsapi-0x0520-unverified`; Task 9 must choose legacy before playback.
Missing guard installation has a separate unsupported reason. No production
quiescence guarantee or Windows audio profile is inferred from synchronous return,
ENDPROCESS, player idle or a temporarily empty callback count. The default native
proof boundary closes admission, retires entered callbacks, reports failure and
retains the old call identity without reopening it for a successor.

The real outer constructor creates `_ContextualCerenceCallback` before native
voice opening, retains `CancellableSynthDriver is SynthDriver`, and binds
`Voice.synth_driver_class` to that outer class. One synchronous work owns all text
chunks and voice instances; only the final real idle plus resume and validity
check can produce its single contextual drain. Callback errors latch once on the
original context. Cancellation/termination invalidate queued and active work and
hold successor native submission until old callbacks, post-feed stops and the
caller stop retire. Reentrant index/DONE termination returns to its listener and
closes resources after the native batch exits. Sonic fallback, cancelled-tail
reset, repeated-text/chunker handling and variant/waitfactor behavior remain.

Tests run both engines through real outer/native Python constructors and ctypes
callables with the real installed checker. Only native/Windows/player boundaries
are controlled. An explicit fake `_confirm_native_quiescence` promise exercises
successful drain without changing production capability reporting. The two old
fixtures in `test_worldvoice_cancel_wrappers.py` and
`test_worldvoice_request_manager.py` now use actual opened Cerence `VE_HSAFE`
instances rather than the former string sentinel; ABI validation was preserved.

Observed initial Cerence red: **45 failed, 3 passed, 6 skipped**, covering the
missing callback, segment/capability and raw-status APIs. Final required command:
`python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py tests/test_f4_engine_adapters.py -q -p no:cacheprovider`:
**160 passed**. Addon suite `python3 -m pytest tests -q -p no:cacheprovider`:
**910 passed**. `git diff --check` passed. Full-tree
`python3 -m pytest -q -p no:cacheprovider` exits **2** with the existing **191
vendored NVDA collection errors** due to unavailable Windows/NVDA/liblouis
modules. Full log: `/tmp/worldvoice-task8-full-pytest.log`; every error path is
copied into the Task 8 implementer report. No Cerence SDK/DLL provenance,
callback-exclusion contract or real Windows playback device was validated.
