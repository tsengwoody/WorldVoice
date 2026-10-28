"""The shared kinds of segment barrier.

A barrier is a label a wrapper declares on each NativeRecord and marks reached once its
evidence arrives; SegmentHost fails a record that retires with one unreached. A barrier is
classified by what its evidence proves, not by how the engine delivers it: wrappers name a
barrier by one of these kinds when its evidence proves exactly that. Evidence that proves
something else keeps an engine-specific name in its wrapper (tests/test_native_strategy_guards.py
lists them, with the reasons in the phase 52 spec).
"""

# All of this record's audio has been fed to the player, and no further audio callback for
# it will come. The evidence differs by engine: a synchronous synthesis call returned
# (eSpeak, RHVoice, VE/Cerence); the asynchronous delivery callback fed every chunk
# (OneCore); the SAPI5 worker flushed Sonic and fed the tail after EndStream (SAPI5).
AUDIO_FED = "audio_fed"

# Superseded by AUDIO_FED; removed once no wrapper names it.
SYNTHESIZED = "synthesized"

# The engine's own end-of-utterance notification for the record arrived. Optional: VE/Cerence
# and OneCore have no separate terminal notification (OneCore's delivery callback is also its
# terminal notification, so it proves AUDIO_FED only).
ENGINE_DONE = "engine_done"

# The player has played all of this record's audio, proven by WavePlayer.idle() returning, or
# by sync() returning plus the engine's own unpause wait. Only idle() also closes the
# continuous segment (re-arms leading-silence trimming, releases ducking); OneCore's segment
# mode only calls sync() and never closes it (see its drain). This barrier does not guarantee
# those side effects.
PLAYED_OUT = "played_out"
