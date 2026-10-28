"""The shared kinds of segment barrier.

A barrier is a label a wrapper declares on each NativeRecord and marks reached once its
evidence arrives; SegmentHost treats the labels opaquely and fails a record that retires with
one unreached. Wrappers name a barrier by one of these kinds when its evidence proves exactly
that. Evidence that proves something else keeps an engine-specific name in its wrapper
(tests/test_native_strategy_guards.py lists them, with the reasons in the phase 52 spec).
"""

# Every native synthesis call the engine made for the record has returned. These engines
# synthesize synchronously, so all of the record's audio callbacks ran inside those calls.
SYNTHESIZED = "synthesized"

# The engine's own end-of-utterance notification for the record arrived.
ENGINE_DONE = "engine_done"

# WavePlayer.idle() returned for the record: its audio finished playing (idle syncs first)
# and the continuous segment was closed. A bare sync() is not this kind.
PLAYED_OUT = "played_out"
