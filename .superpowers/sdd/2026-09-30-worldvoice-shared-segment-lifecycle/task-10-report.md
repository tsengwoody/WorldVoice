# Task 10: Cross-engine integration and delivery

Commits:

- `e1ebe34 test: verify seven shared lifecycle profiles and cross-engine handoff`
- `d69b823 docs: record shared segment lifecycle delivery`

Added the exact requested integration and policy checks. The seven enabled-profile case loads the actual outer core for each engine, asserts common `SegmentLifecycle` ownership and DRAIN policy before speech, and checks the runtime session contract for the four-engine composition. The switch case holds original player drain, verifies no successor native call, then checks the original DRAIN event's source and segment identity. Existing SAPI5 legacy selection test was renamed to the requested case and strengthened with the outer support decision; unknown/external fallback has a named assertion. No production files changed.

## Verification

- `python3 -m pytest -q tests/test_runtime_drain_integration.py tests/test_runtime_completion_policies.py`: **205 passed** in 7.06s.
- `python3 -m pytest -q tests`: **1,275 passed, 9 skipped** in 37.82s. No Neural timing failure occurred in final runs.
- `git diff --check`, `git diff --cached --check`, and final `git show --check HEAD`: exit 0. Tracked checkout clean after commits.
- SCons 4.11.1/Markdown 3.11 in a temporary venv built `WorldVoice-6.2-test-correlated-drain-1-9999.nvda-addon` from detached `ee6d0b8` using `scons version=6.2-test-correlated-drain-1-9999 channel=dev`, exit 0. Size **10,613,480 bytes**, SHA-256 `bfec2cbdebc7653443ff3885166e58f97df63cf03f3f2b331d1f5aeeaa1fe2ab`. The archive has 122 unique entries, valid CRCs, safe paths, and no cache or bytecode; 99 tracked add-on files match source and 20 protected Neural/VE/Cerence files match the prior activation package. Version and `dev` channel match the request.
- The new artifact stays in `/tmp/worldvoice-task10-build-ee6d0b8`; the ignored root package and its README hash remain the earlier activation artifact. No Windows NVDA/audio/SDK validation was available.

## Self review

Reviewed the committed test diff and delivery record against the brief. The tests assert real coordinator and wrapper behavior while faking only external native/player boundaries. Checked that the delivery record lists all 24 exact design, plan, implementation, fix, and integration SHA/subject pairs through `e1ebe34` against `git log`; the self-referential documentation SHA is listed above. Removed a meaningless private-field assertion before final verification. No outstanding issue found in the Task 10 scope. A later holistic review may add follow-up commits, which must be appended to the delivery record by the coordinator.

## Post-Task 10 Neural follow-up

`6caceb5 fix: close Neural segment admission cancellation gap` made lifecycle acceptance and driver work registration atomic under `_segmentCondition`, which `cancel()` also uses to snapshot `_segmentWorks`. A deterministic regression pauses after acceptance, starts cancellation, and holds task construction to verify that cancellation sees the work; no native submission or terminal event escapes. The subsequent `python3 -m pytest -q tests` rerun passed **1,276 tests, 9 skipped** in 36.63s. The package audited above was built from `ee6d0b8` and predates this fix.
