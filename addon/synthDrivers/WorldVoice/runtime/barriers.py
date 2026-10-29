"""The shared kinds of segment barrier.

A barrier is a label a wrapper declares on each NativeRecord and marks reached once its
evidence arrives; SegmentHost fails a record that retires with one unreached. A barrier is
classified by what its evidence proves, not by how the engine delivers it: wrappers name a
barrier by one of these kinds when its evidence proves exactly that. No engine-specific barrier
name exists now. Evidence that proves something else would get one in its wrapper, and that name
must be listed, with its reason, in ENGINE_SPECIFIC_BARRIERS in tests/test_native_strategy_guards.py.
SegmentHost requires only that every strategy declares PLAYED_OUT; the guard tests also require
every strategy to declare AUDIO_FED.
"""

# All of this record's audio has been fed to the player, and no further audio callback for
# it will come. The evidence differs by engine: a synchronous synthesis call returned
# (eSpeak, RHVoice, VE/Cerence); the asynchronous delivery callback fed every chunk
# (OneCore); the SAPI5 worker flushed Sonic and fed the tail after EndStream (SAPI5).
# RHVoice's and VE/Cerence's prove "all audio fed" only together with ENGINE_DONE: RHVoice's
# inner player holds back the last chunk until the done callback feeds it, and the VE/Cerence
# wrapper feeds the Sonic and buffered tail only at the last call's VE_MSG_ENDPROCESS.
AUDIO_FED = "audio_fed"

# The engine's own end-of-utterance notification for the record arrived. For VE/Cerence it is
# the VE_MSG_ENDPROCESS of the record's last ve_ttsProcessText2Speech call, admitted while the
# record was valid, after which the wrapper has flushed Sonic and fed the tail (a Windows SDK
# probe of VE SDK 2.2.0 and Cerence SDK 21.6.0, both the 32-bit lib\x86 / lib\x32 and the 64-bit
# lib\AMD64 / lib\x64 libraries, saw exactly one ENDPROCESS, always last, on every successful
# call). Optional: OneCore has no separate terminal notification (its delivery callback is
# also its terminal notification, so it proves AUDIO_FED only).
ENGINE_DONE = "engine_done"

# The player has played all of this record's audio, proven by WavePlayer.idle() returning, or
# by sync() returning plus the engine's own unpause wait. Only idle() also closes the
# continuous segment (re-arms leading-silence trimming, releases ducking). OneCore's segment
# drain only calls sync(), so draining a segment does not close it; ordinary speech in
# segment mode still calls idle() once the queue empties (its _legacyCallback). This barrier
# does not guarantee those side effects.
PLAYED_OUT = "played_out"
