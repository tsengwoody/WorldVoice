# Task 4 Neural follow-up

## Diagnosis and change

`test_neural_cancelled_callback_cannot_feed_successor` released the fake SDK's shared `speak_release` before sending successor PCM. Both native calls could then return; the successor correctly closed callback admission before that PCM arrived. A per-call return gate now keeps the successor native producer live through the callback. The LangChange Sonic test needed the same gate for its second native call, as observed in the focused suite.

`speak_segment` previously accepted a lifecycle operation before registering its driver work. `cancel()` snapshots `_segmentWorks`, so cancellation in that gap missed the operation. The driver now holds `_segmentCondition` through lifecycle acceptance and work registration. The condition is released before task construction, queue publication, native SDK calls, player calls, or event delivery. The new test pauses after lifecycle acceptance, starts cancellation, then pauses task construction to prove cancellation sees the registered work. It checks that no native submission or terminal event escapes.

## Verification

- RED: `python3 -m pytest -q tests/test_neural_segment_drain.py -k 'cancel_sees_work_accepted_before_driver_registration'` — 1 failed, 67 deselected; cancellation completed during the paused acceptance gap.
- GREEN: `python3 -m pytest -q tests/test_neural_segment_drain.py -k 'cancel_sees_work_accepted_before_driver_registration or cancelled_callback_cannot_feed_successor'` — 2 passed, 66 deselected.
- `for i in $(seq 1 30); do python3 -m pytest -q tests/test_neural_segment_drain.py -k 'shared_lifecycle_waits_for_all_langchange_tasks_and_sonic_idle or cancel_sees_work_accepted_before_driver_registration or cancelled_callback_cannot_feed_successor' > /tmp/neural-followup-pytest.log || { cat /tmp/neural-followup-pytest.log; exit 1; }; done; cat /tmp/neural-followup-pytest.log` — 30/30 iterations passed; final iteration 3 passed, 65 deselected.
- `python3 -m pytest -q tests/test_neural_segment_drain.py tests/test_segment_lifecycle.py` — 89 passed on final rerun. An earlier run had one intermittent `test_late_cancel_cannot_stop_successor_resource` failure, then passed on immediate rerun; that lifecycle test was not changed.
- `python3 -m pytest -q tests` — 1276 passed, 9 skipped on final rerun. A prior rerun had one intermittent `test_old_feed_final_stop_retires_before_next_native_call[VE]` failure (1275 passed, 9 skipped); VE code and tests were not changed.
- `python3 -m pytest -q` — collection stopped with 191 errors from vendored NVDA tests under `ref/`, including missing `louis` and `monkeyPatches` modules. The project `tests/` suite above completed.
- `git diff --check` — passed.

These are Linux fake SDK/player boundary tests; no Windows SDK or physical playback validation was performed.
