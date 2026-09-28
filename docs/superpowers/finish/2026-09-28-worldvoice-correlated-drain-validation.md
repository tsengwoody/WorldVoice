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
