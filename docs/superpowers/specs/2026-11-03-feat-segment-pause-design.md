# Segment pause: a pipeline stage replaces the VE/Cerence 100-character chunking

Date: 2026-11-03.
Baseline: `master` `73eb8c8`. Branch: `feat/segment-pause`, worktree `/workspace/WorldVoice-segment` (`ref` is a git-ignored symlink to `/workspace/WorldVoice/ref`).
Baseline numbers (Linux, Python 3.14): `python3 -m pytest -q -p no:cacheprovider tests` -> 3633 passed, 0 skipped; `prek run --all-files` all Passed.
Flow: normal flow (`DEVELOPMENT_WORKFLOW.md` §3.1). This is the spec only; plan and implementation follow (§3.2).

Status:

- U1–U7 were decided by the user (2026-11-03) and are not reopened here (§2.1).
- O1–O12 are orchestrator defaults: `Decided by orchestrator with the recommended default; user may override before merge` (§2.2, §11.1).
- Three questions are open for the user (§11.2). Q1 widens the scope beyond U1–U7; Q2 and Q3 refine U4. Each has a recommended answer that this spec already assumes, so implementation can start.

References used throughout (`<alias>:<line>`):

- Chunker: `addon/synthDrivers/WorldVoice/text/chunker.py` (`chunker:`).
- Settings table: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (`psettings:`).
- Stage table: `addon/synthDrivers/WorldVoice/pipeline/registry.py` (`registry:`).
- Break classes and merge: `addon/synthDrivers/WorldVoice/pipeline/breaks.py` (`breaks:`).
- Number stages: `addon/synthDrivers/WorldVoice/pipeline/numberStages.py` (`stages:`).
- Synth: `addon/synthDrivers/WorldVoice/__init__.py` (`synth:`).
- Request builder: `addon/synthDrivers/WorldVoice/runtime/requestBuilder.py` (`builder:`); bridge: `addon/synthDrivers/WorldVoice/bridge/commands.py` (`bcommands:`).
- VE / Cerence outer wrappers: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py` (`ve:`), `driver/Cerence/__init__.py` (`cerence:`); VE inner driver `driver/VE/driver/__init__.py` (`veinner:`, read only, never edited).
- NVDA: `ref/nvda/source/...`.

How the claims were checked:

- The cut rule of §4.1 was prototyped in the scratchpad on top of the real `_attached` (`chunker:21-37`), nothing in the worktree. The examples of §5 are its output. A random check of 100 000 cases (items of 0–12 characters drawn from Latin letters, spaces, a newline, U+0301, a Thai vowel, ZWJ, a skin tone and a Han character; 1–5 items; N 1–15) found no violation of P1–P4 (§9.3).
- The state-loss finding (F2) was traced through the code paths cited; it was not heard on Windows.

## 0. Findings

### F1. Root cause of the mid-sentence pauses in 7.0 (for information; the user's diagnosis, confirmed)

- The VE and Cerence outer wrappers pass every native text through `split_speech_text_pieces` and queue one `ProcessText2Speech` per piece (`ve:537-542`, `cerence:541-546`). The limit is `MAX_TEXT_LENGTH = 100` plain characters (`chunker:10`), cut after the last space (`chunker:111-113`). The engine treats each call as a complete utterance: final intonation and its trailing silence land mid-sentence.
- 6.2 (`318bc90`) sent the whole text in one call: `git show 318bc90:addon/synthDrivers/WorldVoice/driver/VE/driver/__init__.py`, lines 412-415 (`text = "".join(chunks)`; one `ProcessText2Speech`). The chunker came with `a3493ba` (2026-09-24). The SDK binding has no length limit either (`driver/VE/driver/ve2/__init__.py:169-175` passes `len(text)` bytes).

### F2. In WorldVoice, synth parameter commands do not survive a pause (affects every existing pause too)

- A `BreakCommand` becomes `Pause` (`bcommands:15-16`); the request builder flushes the chunks collected so far as one segment at a `Pause` (`builder:44-50`) and at a `SelectVoice` (`builder:37-41`); every other command is appended to the current segment only (`builder:52`). The scheduler then calls the engine once per segment with that segment's commands only (`runtime/scheduler.py:212-234`, `:598`; `bridge/engineAdapter.py:174-211`).
- So a `CharacterModeCommand(True)`, or a `PitchCommand`/`RateCommand`/`VolumeCommand` with a non-default offset or multiplier, that precedes a pause is not in the next segment's commands. Each engine call starts from defaults: the inner VE `speak` starts with `charMode = False` (`veinner:354`) and turns those commands into inline escapes of that one call only (`veinner:376-379`, `:405-431`); NVDA's own drivers build each call's SSML from its own sequence.
- Language is not affected: `lang_cmd_to_voice` turns every language command into `SelectVoice` before the bridge (`pipeline/languageCommands.py:75-88`, `synth:338-346`), and the builder keeps `voice_key` across a `Pause` (`builder:21`, `:44-50`).
- NVDA itself replays the changed parameters at the start of every utterance it builds (`ref/nvda/source/speech/manager.py:83-112` `ParamChangeTracker`, `:293-322` `_ensureEndUtterance`, `:448-457` `_buildNextUtterance`), so the first segment of a WorldVoice `speak` call has them; only the segments after a pause or voice switch lose them.
- Today this is rare: spelling ends an utterance after each character (`ref/nvda/source/speech/speech.py:545-546`), and the item pause goes only between two adjacent text items (`pipeline/items.py:36-51`), which `CharacterModeCommand` separates in NVDA's spelling (`speech.py:367-386`). The new stage can cut anywhere in a long run of text, for example inside MathCAT speech, which uses prosody multipliers (`ref/nvda/source/mathPres/MathCAT/speech.py:89-96`). See §4.6 and Q1.

### F3. The stage counts text before NVDA's symbol processing and separators (for information)

- NVDA runs `filter_speechSequence` first (`ref/nvda/source/speech/speech.py:1137`); only afterwards does it run `processText` (symbol names) on each text item and append `CHUNK_SEPARATOR` (two spaces, `speech.py:172`) to each text item outside character mode (`speech.py:1214-1233`). The count therefore covers the text the pipeline hands on (after speech dictionaries and the number stages), not the text the engine finally receives. The old chunker counted the engine's final text. N is a pause spacing now, not an engine limit, so this is acceptable; the readme describes it in plain words (§6.4).

### F4. A boundary between two text items is a word boundary for every synth (input to O4)

- NVDA appends `CHUNK_SEPARATOR` to every text item outside character mode (`speech.py:1232`), and the VE/Cerence inner drivers put `speech.CHUNK_SEPARATOR` between two text chunks again (`veinner:368-370`; Cerence inner `:370`). In the old flow the chunker saw those separators as spaces. The new stage sees items without them, so it treats an item boundary like a space (§4.1).

### F5. After the change, a VE/Cerence record still can make several native calls (for information)

- The inner `speak` calls `_speak` once per voice switch and once at the end (`veinner:399-402`, `:433-434`). Inside WorldVoice a segment never holds a language command (F2), so a record makes one native call, but the wrappers' several-calls handling (`ve:515-517`, `:589`; `cerence:519-521`, `:593`) stays reachable through the inner driver's own language-change path, and stays.

### F6. `split_speech_text_pieces` has no other caller (input to O7)

- Its only callers are the two wrappers (`ve:13`, `:541`; `cerence:13`, `:545`). The Neural plugin source (`/workspace/WorldVoice/ref/Neural`) does not import `text.chunker`. `storage/refactor8.md:23` lists the module path `text.chunker` as public because a third-party wrapper may copy a built-in one; `text/__init__.py:1-5` says the same.

### F7. The utterance-end test already exists (input to O5)

- `_ends_utterance` (`stages:311-318`) is true for `EndUtteranceCommand` and `ConfigProfileTriggerCommand`, where NVDA's speech manager ends an utterance (`manager.py:342-365`). A `BaseCallbackCommand` splits sequences but `_buildNextUtterance` joins them again into one utterance (`manager.py:332-341`, `:458-463`), so it is not an utterance end.

### F8. The zh_TW readme has no `## 下一版更新` section yet (for information)

- `addon/doc/zh_TW/readme.md:88-90` goes from `# WorldVoice 更新日誌` straight to `## WorldVoice 7 更新`. The section is created (§6.4).

## 1. Problem

With WorldVoice 7.0, Vocalizer Expressive and Cerence pause audibly in the middle of long English or other Latin text at plain spaces, even with punctuation pauses off. 6.2 did not (F1). The 100-character limit has no recorded reason, and no other engine chunks.

Some users may still want long text broken into shorter engine calls, with a pause they control, for every engine.

## 2. Goals and non-goals

### 2.1 Goals (Decided by the user, 2026-11-03)

- U1. Replace the hard-coded VE/Cerence chunking with a speech-pipeline stage that applies to every engine: at each cut point it inserts a `BreakCommand`. In WorldVoice that break becomes a `Pause` that flushes the segment, so each piece is its own engine call (`bcommands:15-16`, `builder:44-50`). For another synthesizer (scope "all") it is an SSML break inside one call; accepted.
- U2. Two new pipeline settings:
  - Segment wait factor (zh_TW「分段停頓參數」): slider 0..100 like the other wait factors; pause ms = `global_factor_units × segment_wait_factor`, as `scaled_punctuation_wait` (`psettings:336-337`). Default 0.
  - Segment length (zh_TW「分段字數」): integer spin like Group size (`psettings:197-211`): 0..`SPIN_MAX`, an invalid or out-of-range value reads or resets to the default, like `group_size`. Default 0.
- U3. If the segment length is 0, or the computed pause is 0 ms (segment wait factor 0 or global wait factor below 10), the stage leaves the sequence completely untouched; it never inserts a 0 ms break (as `pipeline/unspaced.py:60-63`, `pipeline/items.py:29-32`). With both defaults 0 nothing is split: VE/Cerence behave as in 6.2.
- U4. The cut rule is today's chunker rule, parameterized: cut after the last space within N plain characters; if none, hard-cut at N but never between a letter and its combining marks (`_attached`, `_cut_before_marks`, `chunker:21-47`); non-text commands do not count toward N. (Refinements: O4, Q2, Q3.)
- U5. Remove `split_speech_text_pieces` from the VE and Cerence outer wrappers' `_speak`; keep `break_repeated_runs` (the Arabic run breaker, `text/arabic.py:18`).
- U6. UI order: the two items come right after "Punctuation pause characters": segment wait factor first, then segment length.
- U7. Docs: only `addon/locale/zh_TW/LC_MESSAGES/nvda.po` and `addon/doc/zh_TW/readme.md` (with its `## 下一版更新` changelog). Other languages later, in a separate pass. Readme text concise and user-facing. Labels carry `# Translators:` comments.

### 2.2 Orchestrator defaults (Decided by orchestrator with the recommended default; user may override before merge)

- O1. Keys and mirrors: `segment_wait_factor` mirrors `punctuation_wait_factor` (`psettings:274-284`): `driver_id="segmentWaitFactor"`, shown in the Voice panel, the Speech Pipeline panel and the settings ring, slider 0..100. `segment_length` mirrors `group_size` (`psettings:197-211`): no `driver_id`, so no synth setting and no ring entry; spin in both panels. Checked: both mirrors fit. The UI is table-driven (`ui/panelLayout.py:35-37`, `ui/controls.py:48-63`, `addon/globalPlugins/WorldVoice/panels/pipeline.py:44`), a driver setting gets its NVDA slider and a ring entry through `synth:101-121`, `:159-162` and a descriptor through `synth:555-558`, and a non-driver entry is made right after the row of the nearest earlier driver setting (`ui/panelLayout.py:95-113`), the same chain as `number_mode` → `group_size` → `number_wait_factor` today.
- O2. Neither setting depends on `punctuation_pause_enabled` (no `depends_on`), and neither depends on the other.
- O3. `PipelineSettings.effective()` zeroes `segment_wait_factor` for a synth without roles unless scope is "all", like the other waits (`psettings:339-358`); `segment_length` is kept, like `group_size`.
- O4. Cut candidates (refines U4): a position right after any whitespace character (`str.isspace`, not only U+0020), and the boundary between two text items (F4). Counting for a piece starts at its first non-blank character. A cut needs non-blank text on both sides within the run. See §4.1 and Q2, Q3.
- O5. The count resets at every `BreakCommand` (any subclass, any time, 0 ms included: in WorldVoice each one flushes a segment) and at every utterance end (`_ends_utterance`, F7). It does not reset at a language command, so N means the same for every synth.
- O6. The stage runs after `number_wait_factor` and before `speech_viewer` (§4.3).
- O7. Delete `split_speech_text_pieces`, `MAX_TEXT_LENGTH`, `_ESCAPE_RE` and `_break` with their tests; keep the module path `text/chunker.py`, which now holds the sequence cut rule and the mark helpers (§4.8, F6).
- O8. The inserted break is a new `SegmentBreakCommand(BreakCommand)` in `breaks.py`, like `PunctuationBreakCommand` (`breaks:50-51`); another synth gets a plain `BreakCommand` through `_plain_breaks` as for every stage (`registry:117`, `breaks:82-91`).
- O9. The stage's log key is `segment_wait_factor`; its Log Record switch is `segmentWaitFactor`, labelled with the setting's label, as for `punctuation_wait_factor` (`registry:148-168`, `addon/globalPlugins/WorldVoice/panels/log.py:25-26`). `segment_length` gets no switch of its own.
- O10. In WorldVoice, the bridge replays the synth parameter commands in effect at the start of every segment after a pause or a voice switch (§4.6). This fixes F2 for every pause, not only the new one. See Q1.
- O11. `_ends_utterance` moves from `numberStages.py` to `pipeline/sequence.py` ("the checks several stages share", `pipeline/sequence.py:1`) and both stages import it.
- O12. The changelog entry goes under a new `## 下一版更新`, directly below `# WorldVoice 更新日誌` (F8).

### 2.3 Non-goals

- No change to the inner drivers (`driver/<Engine>/driver/`), to `break_repeated_runs`, or to the wrappers' several-native-calls handling (F5).
- No engine-specific length limit; nothing replaces the 100-character limit for VE/Cerence by default.
- The stage does not avoid cutting inside a number's reading (for example number mode's `"1 2 3 …"`): a long digit run is text like any other.
- No migration and no change to other languages' docs or `.po` files (U7).
- No change to Say All's own pause (`pipeline/sayAll.py:19-31`).

## 3. What an NVDA user hears and sees

- Defaults (segment length 0, segment wait factor 0): VE and Cerence read a long paragraph in one engine call again, without mid-sentence pauses at spaces, as in 6.2. Every other engine is unchanged.
- Segment length N > 0 and a pause > 0 ms: in a stretch of text with no pause, WorldVoice cuts at the last space (or item boundary) within N characters and pauses there for `global wait factor ÷ 10 × segment wait factor` ms. Text without spaces (Chinese, Japanese, Thai) is cut every N characters, never between a letter and its combining marks. In WorldVoice each piece is a separate engine call, so the engine also ends each piece like a sentence; even a 1 ms pause is audible as a phrase end (accepted by U1).
- Any other pause (punctuation, item, number, CJK space, a break from NVDA or an add-on) and every utterance end starts the count again: a pause point already within N characters means no segment pause.
- Another synthesizer with scope "all": the same cuts, as SSML breaks inside one call; with scope "WorldVoice", nothing.
- Settings: two new items after "Punctuation pause characters" (§6). "Segment wait factor" is also in the settings ring, after "Punctuation wait factor".
- O10 also changes, in WorldVoice, what follows any pause: pitch, rate, volume offsets and character mode that were in effect before the pause stay in effect after it (F2).

## 4. Design

### 4.1 The cut rule (`text/chunker.py`, NVDA-free, snake_case)

New function (name `segment_cuts`; the implementer may adjust the name, not the contract):

```python
def segment_cuts(texts: Sequence[str], max_length: int) -> list[tuple[int, int]]:
    """Where to cut the text items of one run: (item index, offset), the piece ending
    after texts[index][:offset], with 0 < offset <= len(texts[index]); in order."""
```

Let `T` be `"".join(texts)` and `L = len(T)` (code points; an astral character counts once). Candidates are positions `b` in `T` with `T[b - 1].isspace()`, or `b` the end of an item that is followed by another item (an item boundary), provided `not _attached(T, b)`. Then:

1. `max_length <= 0`, or `T` is blank: no cut.
2. Start with `start = 0`. Let `s0` be the first non-blank position at or after `start`; if there is none, or `L - s0 <= max_length`, stop.
3. `limit = s0 + max_length`. Take the largest candidate `b` with `s0 < b <= min(limit, last)`, where `last` is the last non-blank position of `T`.
4. If there is none, hard-cut: `c = limit`, moved back while `c > s0 and _attached(T, c)` (`_cut_before_marks` with a lower bound); if it reaches `s0`, `c` is the end of the cluster at `s0` (`_end_of_marks`), which may pass `limit`. If `c > last`, stop (only whitespace would follow).
5. Record the cut, set `start` to it, and repeat from 2.

A cut position is mapped to the first item whose span ends at or after it (`acc < c <= acc + len(item)`), so an item-boundary cut is `(i, len(texts[i]))` and an empty item never owns a cut.

Guarantees (pinned by §9.3): the pieces concatenate to `T`; every cut has non-blank text before and after it; no cut separates a character from what `_attached` attaches to it; each piece, without its leading whitespace (and, for the last piece, its trailing whitespace), has at most `max_length` characters, except a single cluster longer than `max_length`. Running time is linear in `L` (precomputed candidates and non-blank positions; the old chunker once had a quadratic case, phase 30 notes).

`_cut_before_marks(token, cut)` gains a lower bound (`start`, default 0) so it never moves before the piece's start; `_attached` and `_end_of_marks` stay as they are (`chunker:21-37`, `:50-54`).

### 4.2 The stage (`pipeline/segments.py`, new; snake_case)

```python
def inject_segment_pause(speech_sequence, settings, ctx) -> Iterator[SpeechCmd]:
```

- `length = settings.segment_length`, `pause = settings.scaled_segment_wait()`. If `length <= 0` or `pause <= 0`: `yield from speech_sequence` and return (U3).
- Walk the sequence, collecting a run of items. At an item that is a `BreakCommand` (`isinstance`, so every subclass and every plain break with `_EDGE_MARKER`) or for which `_ends_utterance` holds: emit the run cut, then the item, and start a new run (O5). At the end, emit the last run cut.
- Cutting a run: `segment_cuts([item for item in run if isinstance(item, str)], length)`; split the text items at the returned offsets and put the break right after each cut piece, before any command that follows it (a cut at an item boundary goes right after that item). This is where every stage puts its pause: right after the text (`pipeline/punctuation.py:177-178`, `pipeline/items.py:45-46`). Commands keep their order and are never counted.
- One `SegmentBreakCommand(pause)` instance per call, shared by every cut, as the item and unspaced stages share theirs (`pipeline/items.py:33`, `pipeline/unspaced.py:65`); the synths read only `.time`.
- The stage reads no context; `ctx` is accepted for the stage signature.
- The structure guard's import limits apply (`tests/test_pipeline_structure.py:102-118`): no `unicodedata` in the stage module, which is why the cut rule lives in `text/chunker.py`.

### 4.3 Position in `STAGES` (`registry:148-157`)

```
apply_speech_dictionaries, number_mode (thousands), number_mode (inject_numbers),
unspaced_script_space_wait_factor, item_wait_factor, punctuation_wait_factor,
number_wait_factor, segment_wait_factor, speech_viewer
```

- Every stage that adds a break runs before it, `number_wait_factor` last (`stages:107-130`), so the count sees every existing pause and resets there (O5). `speech_viewer` is a pass-through that logs the final sequence (`registry:49-50`); it stays last.
- Break merging: `_merge_edge_breaks` merges breaks that meet between two non-blank text items (`breaks:54-79`). The segment break always has non-blank text between it and any other break or the run's ends (§4.1), so it is never in a run with another break, and no stage after it merges. Nothing to merge, and edge markers need no handling: the stage only tests `isinstance(item, BreakCommand)`.
- `number_wait_factor` strips text items and drops blank ones when its wait is above 0 (`stages:112-127`); the stage simply counts what it gets.

### 4.4 Break class (`breaks.py`)

`class SegmentBreakCommand(BreakCommand): """Pause at a segment cut: after at most segment_length characters with no other pause."""`, next to `PunctuationBreakCommand`. For a synth without roles, `_stage_handler` turns it into a plain `BreakCommand` (`registry:117`), so NVDA's `speechXml` finds its converter (`breaks:82-91`).

### 4.5 Settings (`psettings`)

- Two table entries, after `punctuation_pause_characters` (`psettings:285-294`), in this order (U6):
  - `PipelineSettingSpec("segment_wait_factor", int, 0, driver_id="segmentWaitFactor", label=_("Segment wait factor"), control="slider")`, Translators comment as for `punctuation_wait_factor` (`psettings:279-280`): "Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel; also the label of the setting's pipeline log switch in the Log Record panel."
  - `PipelineSettingSpec("segment_length", int, 0, label=_("Segment length"), min_value=0, max_value=SPIN_MAX, reset_out_of_range=True, control="spin")`, Translators comment: "Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel: the most characters spoken before a segment pause (0: no segments)." A code comment says why it resets like `group_size` (decided by the user, 2026-11-03, U2).
- `PipelineSettings` gets `segment_wait_factor: int` and `segment_length: int`, and `scaled_segment_wait()` = `global_factor_units * segment_wait_factor`.
- `effective()`: `segment_wait_factor=0` in the `replace` for scope "WorldVoice" (O3); docstring unchanged ("every pause and removal is off").
- Derived automatically: confspec `segmentWaitFactor = integer(default=0,min=0,max=100)`, `segmentLength = integer(default=0,min=0,max=2147483647)` (`psettings:135-140`, `:298-302`); the synth setting and ring entry for `segmentWaitFactor` (`synth:159-162`, `:101-121`) and its descriptor (`synth:555-558`); the Log Record switch (`registry:160-168`, `confspec.py:27-30`).

### 4.6 Parameter replay after a segment start (`bcommands`, NVDA layer, camelCase; O10)

`normalizeNvdaCommands` (`bcommands:11-18`) keeps a tracker with NVDA's `ParamChangeTracker` semantics (`manager.py:83-112`): for each `SynthParamCommand` other than a language command (in WorldVoice those are already `SelectVoice`), store it by type, or drop the type when `command.isDefault` (`ref/nvda/source/speech/commands.py:143-185`, `:249-274`).

- After it yields a `Pause` (from a `BreakCommand`) or passes a `SelectVoice` on, a replay is pending.
- While a replay is pending, a parameter command only updates the tracker and is not yielded; other commands (index, beep, wave) are yielded in place.
- At the next text item, if a replay is pending, it yields the tracker's commands first, then the text, and the replay is done.
- If the sequence ends with a replay pending, nothing more is yielded: no text follows, and a segment of parameter commands alone would make an engine call with no text.
- The `WorldVoiceIndexCommand` check (`bcommands:13-14`) is unchanged.

Why the bridge and not the stage: the loss comes from WorldVoice's segmenting at a pause or voice switch (F2), not from the stage. Fixing it where a pause becomes a segment boundary fixes every pause (punctuation, item, number, CJK space, a break from NVDA or an add-on) and never touches another synth, whose break stays inside one SSML call. A stage-local re-emit would leave the other pauses broken and add redundant SSML for other synths; "never cut inside a character-mode region" would not cover prosody.

### 4.7 VE and Cerence wrappers (`ve:537-542`, `cerence:541-546`; U5)

`_speak` queues one `_NativeTask` with `break_repeated_runs("".join(chunks))`, and none when that text is empty (what the chunker's `if not text: return []` did, `chunker:78-79`). The `text.chunker` import goes (`ve:13`, `cerence:13`). The comments on several native calls per record stay true (F5).

### 4.8 Code removed, kept and added

- Removed: `split_speech_text_pieces`, `MAX_TEXT_LENGTH`, `_ESCAPE_RE`, `_break` (`chunker:8-13`, `:57-130`), their tests, and the wrapper imports (O7).
- Kept: `text/chunker.py` (public path), `_attached`, `_end_of_marks`, `_cut_before_marks` (with the lower bound), `text/arabic.py`. The module docstring and `text/__init__.py:1-5` say that `text.chunker` now holds the segment cut rule the pipeline uses, while `text.arabic` stays wrapper-facing.
- Added: `segment_cuts` (`text/chunker.py`), `pipeline/segments.py`, `SegmentBreakCommand`, two table entries and two fields, the bridge replay, `_ends_utterance` in `pipeline/sequence.py` (O11).

### 4.9 Spelling, Say All and the pipeline log

- Spelling: `speakSpelling` speaks through `speak` and so through the filters (`speech.py:350-364`, `:1137`; WorldVoice's `patchedSpeakSpelling`, `synth:358-363`, only splits by language first). NVDA ends an utterance after each spelled character (`speech.py:545-546`), so the count restarts per character; only a tiny N can cut inside "cap A", and then O10 keeps the cap pitch and character mode.
- Say All: each sequence it speaks is one `speak` call and ends an utterance (`manager.py:375`), so the count restarts per sequence. Say All's own pause is a separate `[BreakCommand]` sequence (`pipeline/sayAll.py:27-29`).
- Log: `Stage("segment_wait_factor", inject_segment_pause)` logs before/after under its switch through `_run_logged` (`registry:87-108`); `LOG_SWITCHES` and the confspec follow from `STAGES` (`registry:160-168`, `confspec.py:27-30`). The Log Record panel labels the switch "Segment wait factor" (`panels/log.py:25-26`).

## 5. Worked examples (prototype output; N = segment length; `SB` = the segment break)

| Input (run) | N | Output |
| --- | --- | --- |
| `"The quick brown fox jumps over the lazy dog. " × 3`, stripped | 50 | `"The quick brown fox jumps over the lazy dog. The "`, SB, `"quick brown fox jumps over the lazy dog. The "`, SB, `"quick brown fox jumps over the lazy dog."` (49, 45, 40 chars) |
| `["Hello world", BreakCommand(10), "foo bar baz"]` | 8 | `["Hello ", SB, "world", BreakCommand(10), "foo bar ", SB, "baz"]`: the existing break restarts the count |
| `["one two", IndexCommand(1), "three"]` | 8 | `["one two", SB, IndexCommand(1), "three"]`: item-boundary cut, break before the command |
| `["a" × 30, "b" × 30]` | 40 | `["a" × 30, SB, "b" × 30]`: the boundary beats a hard cut inside `b` |
| `"中文語音合成" × 3` | 5 | `"中文語音合"`, SB, `"成中文語音"`, SB, `"合成中文語"`, SB, `"音合成"` |
| `"é" × 3` | 3 | `"é"`, SB, `"é"`, SB, `"é"`: a cut never lands before U+0301 |
| `"x" × 10 + "   "` | 10 | unchanged: only whitespace would follow a cut |
| `["Hello world", EndUtteranceCommand(), "foo bar"]` | 8 | `["Hello ", SB, "world", EndUtteranceCommand(), "foo bar"]` |
| any sequence | 0, or factor 0, or global < 10 | the same objects in the same order |

## 6. Panels, ring, strings and documentation

### 6.1 Voice settings panel (NVDA's, WorldVoice as the synth)

- Rows, Tab order and window order: … Punctuation wait factor (slider), Punctuation pause characters (edit), Segment wait factor (NVDA slider for `segmentWaitFactor`), Segment length (WorldVoice spin `segmentLengthSpin`). The spin is made right after the `segmentWaitFactor` row (`ui/panelLayout.py:95-113`, `ui/voicePanel.py:112-159`), so its label is the window just before it.
- NVDA reads: "Segment wait factor slider 0", "Segment length spin button 0" (wx spin through NVDA's `SelectOnFocusSpinCtrl`, `ui/controls.py:57-63`; it selects its text on focus). Neither is ever disabled.
- Another synth: no WorldVoice controls in this panel (`ui/voicePanel.py:118-120`); the settings are changed in the Speech Pipeline panel.
- Saved: the spin through `onSave` with the other WorldVoice controls (`ui/voicePanel.py:219-229`); the slider by NVDA as a driver setting stored in the pipeline section (`synth:540-553`).

### 6.2 Speech Pipeline panel and ring

- The panel's controls follow the table (`panels/pipeline.py:27-44`): … Punctuation pause characters, Segment wait factor (slider 0–100, `panel_scale` 1), Segment length (spin 0–2147483647).
- Settings ring: "Segment wait factor" after "Punctuation wait factor", step 1, 0–100. Segment length is not in the ring.
- Log Record panel: a "Segment wait factor" switch between "Number wait factor" and "Speech viewer".

### 6.3 Strings (zh_TW in `nvda.po`, `msgfmt --check`)

| msgid | msgstr | Translators comment |
| --- | --- | --- |
| `Segment wait factor` | `分段停頓參數` | Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel; also the label of the setting's pipeline log switch in the Log Record panel. |
| `Segment length` | `分段字數` | Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel: the most characters spoken before a segment pause (0: no segments). |

### 6.4 User guide (`addon/doc/zh_TW/readme.md`; U7)

- "支援全域的語音流程" list (`readme.md:37`): append「分段停頓相關設定」.
- New block right after the 標點停頓 block (after `readme.md:66`):

  ```
  * 分段停頓：在很長、中間沒有停頓的文字中切出停頓。
   * 分段停頓參數：每個分段處的停頓長度，計算方式與其他停頓參數相同（全域停頓參數 ÷ 10 × 分段停頓參數 毫秒）。0（預設）為不分段。
   * 分段字數：每一段最多幾個字元，空白與標點也算。WorldVoice 在這個字數內最後一個空白處切開；沒有空白時（例如中文）就在剛好這個字數處切開，但不會把字母和它的附加符號分開。其他停頓或一段朗讀的開頭都會重新計算字數。0（預設）為不分段。
   * 分段字數、分段停頓參數或全域停頓參數為 0 時都不分段。使用 WorldVoice 時，每一段會分別送給語音引擎，所以即使停頓很短，每段結尾聽起來也像句尾。
  ```

- New `## 下一版更新` directly below `# WorldVoice 更新日誌` (O12):

  ```
  * **長文字不再在句子中間停頓：** WorldVoice 7.0 使用 Vocalizer Expressive 或 Cerence 時，會把超過 100 個字元的文字在空白處切開，因此即使關閉標點停頓，長句中間也會明顯停頓。現在預設不再切開，與 6.2 相同。需要時可以用新的「分段停頓參數」與「分段字數」分段，所有語音引擎都適用。
  * **停頓後保留音調與拼讀設定：** WorldVoice 停頓或切換語音之後，停頓前的音高、語速、音量與逐字拼讀設定會繼續作用，不再回到預設值。
  ```

  The second bullet is written only if Q1 keeps O10.

## 7. Settings, data, compatibility and errors

- New keys in `[WorldVoice][pipeline]`: `segmentWaitFactor` (default 0, 0..100), `segmentLength` (default 0, 0..2147483647); new `[WorldVoice][log]` switch `segmentWaitFactor` (default false). No existing key changes; no migration: a missing key reads its default, which keeps the 6.2 behavior (U3).
- Invalid stored values: NVDA refuses a value outside the confspec on read and `read_stored` returns the default, logging once (`psettings:365-385`); `convert` clamps the wait factor into 0..100 and resets a segment length outside 0..SPIN_MAX to 0 (`psettings:126-132`), as for `group_size`.
- A user who wants the 7.0 VE/Cerence splitting back sets segment length 100 and a factor above 0; the pause is then WorldVoice's plus the engine's own phrase end.
- Errors: the stage raises nothing of its own. NVDA's `Filter.apply` logs a stage exception and keeps its input (`ref/nvda/source/extensionPoints/__init__.py:112-117`), as for every stage.

## 8. Affected layers

- Core, NVDA-free (snake_case): `text/chunker.py`.
- Core pipeline (snake_case): `pipeline/segments.py` (new), `pipeline/breaks.py`, `pipeline/sequence.py`, `pipeline/numberStages.py` (import only), `pipeline/registry.py`, `pipeline/settings.py`.
- Bridge (camelCase): `bridge/commands.py`.
- Engine outer wrappers: `driver/VE/__init__.py`, `driver/Cerence/__init__.py`. Each still imports nothing from the other (independently installable).
- UI: no code change (table-driven).
- Docs and translation: `addon/locale/zh_TW/LC_MESSAGES/nvda.po`, `addon/doc/zh_TW/readme.md`. Build config: `pyproject.toml` mutmut `source_paths`.
- Untouched: `driver/*/driver/*`, `driver/sonic/`, the generated Unicode data files.

## 9. Test plan

### 9.1 Existing tests that change

- `tests/pipeline_harness.py`: `ORDER` and `LOG_SWITCH_ORDER` (`:246-266`) gain `segment_wait_factor` / `segmentWaitFactor` before `speech_viewer` / `speechViewer`; `punctuation_settings` (`:229-241`) gains `segment_length=0`, `scaled_segment_wait=lambda: 0`.
- `tests/test_pipeline_settings_service.py`: `OLD_DEFAULTS` and `STORED_KEYS` (`:10-40`); the canonical order list (`:110-130`); `reset_out_of_range` keys become `["group_size", "segment_length"]` (`:98-108`); `test_effective_matches_the_old_synth_scoping` (`:321-372`) also checks `segment_wait_factor` 0 and `segment_length` kept; a `scaled_segment_wait` case in `:375-382`.
- `tests/test_pipeline_pause_properties.py`: `SCALED_WAITS` (`:645-651`) gains `segment_wait_factor`; the group size convert property (`:680-687`) also covers `segment_length`.
- `tests/test_settings_order.py`: `VOICE_KEYS` (`:180-193`) and any order list of the panels and ring.
- `tests/test_panel_layout.py`: `Q1` (`:15-29`); `test_creation_followers_of_the_table` and `…_skip_an_unlisted_driver` (`:113-126`) gain `"segmentWaitFactor": ("segment_length",)`; attribute-name cases (`:150-172`) gain `segment_length` → `_segment_length_spin`, `segmentLengthSpin`, `None` and `segment_wait_factor` → `_segment_wait_factor_slider`, `segmentWaitFactorSlider`, `segmentWaitFactorSlider`.
- `tests/test_worldvoice_pipeline_settings.py`: `EXPECTED_IDS` (`:22-42`) gains `segmentWaitFactor` last; segment length has no synth setting or descriptor.
- `tests/test_settings_table_guard.py`: a test like `test_group_size_is_an_independent_panel_only_spin` (`:425-431`) for `segment_length`.
- `tests/test_pipeline_structure.py`: `STAGE_MODULES` (`:87-97`) gains `segments`.
- `tests/test_text_preprocessing.py`: the `split_speech_text_pieces` tests and property (`:19-153`, `:225-244`) are replaced by §9.2/§9.3 tests of `segment_cuts`; the Arabic tests stay.
- `tests/test_vocalizer_segment_drain.py` (`:805`, `:2040`, `:2094`, `:2127`) and `tests/test_worldvoice_cancel_wrappers.py` (`:147`, `:190`): they patch `split_speech_text_pieces` to get several native calls in one record. Rewrite them to get those calls from the inner driver's language switch (`veinner:380-402`), as `test_multichunk_langchange_has_one_work_and_final_drain` already does (`:801-825`), and the zero-call case from a segment of blank text only (`veinner:357-360`). What they check (ENGINE_DONE only from the last call, cancel between calls, no restart) keeps its coverage. `tests/worldvoice_cancel_wrapper_harness.py:153` drops the `text.chunker` stub.
- `tests/test_pipeline_nvda_ssml.py` (`:50-68`): add a segment case to the scope-all SSML property (every word kept, a `<break>` at each cut).
- `tests/test_translator_comments.py` covers the two labels without change.

### 9.2 New unit tests (red first)

- `segment_cuts`: the §5 rows; N ≤ 0; blank input; leading whitespace not counted; a boundary before a combining-mark item is not a candidate; newline and tab are candidates; an astral character counts once; a cluster longer than N stays whole; offsets map to the first item whose span ends there (empty items own no cut).
- Stage: pass-through objects-identical for length 0, factor 0, global 0..9, and scope "WorldVoice" for a synth without roles; reset at `BreakCommand`, `NumberEdgeBreakCommand`, a marked plain break, `EndUtteranceCommand`, `ConfigProfileTriggerCommand`; no reset at `LangChangeCommand`, `WVLangChangeCommand`, `IndexCommand`, a callback; break placed before following commands; one shared break instance; plain break for another synth through the handler.
- Registry: `STAGES` order; the `segmentWaitFactor` switch logs before/after rows under `segment_wait_factor`.
- Bridge: `[Pitch(offset=30), "a b", BreakCommand(10), "c"]` → `Pitch, "a b", Pause, Pitch, "c"`; `CharacterModeCommand(True)` replayed after a `SelectVoice`; a default command clears the type; a parameter command after the pause and before the text is replayed once, not twice; no replay at the end of a sequence; index commands keep their place; the external `WorldVoiceIndexCommand` still raises.
- WorldVoice speak end to end (`tests/test_worldvoice_speak.py` harness): length 20, factor 10, a 60-character English sentence → three engine segments with breaks between; defaults → one segment.
- VE/Cerence wrappers: one native call with the whole text for a 300-character segment; none for empty text; `break_repeated_runs` still applied.

### 9.3 Property tests (Hypothesis; text from Latin letters, spaces, newlines, Han, Thai, combining marks, ZWJ, skin tones; commands from Index, Pitch, Break subclasses, utterance ends)

- P1. Concatenating the text pieces reproduces the original text, item by item, with every command in its original order.
- P2. Each piece, without its leading whitespace (and the last piece's trailing whitespace), has at most N characters, unless it is one letter with its attached marks.
- P3. Length 0, factor 0 or global below 10 → output identical (same objects, same order) to the input.
- P4. No inserted break at the start or end of the output, next to an utterance end, or with only blank text and commands between it and another break: between an inserted break and any other break, sequence edge or utterance end there is non-blank text.
- P5. No cut separates a character from what `_attached` attaches to it.
- P6. Inserting the segment breaks and then removing them, and joining text items split by the stage, gives back the input (the stage adds nothing else).
- P7. Bridge: for any sequence, the parameter state in effect at every text item of every segment equals NVDA's tracker state at that item in the unsegmented sequence.

### 9.4 Mutation testing

Add `text/chunker.py`, `pipeline/segments.py` and `bridge/commands.py` to `[tool.mutmut] source_paths` (`pyproject.toml:45-68`); run mutmut on them on Linux and record surviving mutants with reasons in the review or handoff.

### 9.5 Windows / NVDA manual items

1. VE and Cerence, defaults, punctuation pauses off: read a long English paragraph (300+ characters, say all and arrow-down): no pauses at plain spaces; compare with 6.2.
2. Segment length 100, segment wait factor 10, global 10: VE, Cerence, eSpeak, OneCore, RHVoice and SAPI5 each pause about every 100 characters at a space; Chinese text pauses every 100 characters.
3. Scope "All Synthesizers (Global)" with NVDA's own eSpeak or OneCore: the same cut points as pauses within one utterance; Speech Viewer shows the text unchanged.
4. A comma or period pause within N characters: no extra segment pause next to it.
5. Panels: order, Tab order, labels read by NVDA, spin selects its text on focus, values saved and reread in both panels and across profiles; the ring offers "Segment wait factor", not "Segment length".
6. O10: with a small segment length, spell a capital letter with "Say cap before capitals" and a capital pitch change; and read MathCAT math with prosody: pitch and character mode hold after each pause.
7. Log Record: the "Segment wait factor" switch writes before/after rows.

## 10. Risks

- Each piece is a separate engine call in WorldVoice, with the engine's own phrase end; users may expect a short pause to be inaudible (§3, U1).
- O10 changes, in WorldVoice, what follows existing pauses (F2). It restores what NVDA intends; heard only where parameter commands precede a pause.
- N counts text before symbol processing (F3); a symbol-heavy piece can be longer than N when spoken.
- Third-party wrappers copied from VE/Cerence that import `split_speech_text_pieces` would fail to import (O7, F6).

## 11. Questions and the defaults applied

### 11.1 Orchestrator defaults (Decided by orchestrator with the recommended default; user may override before merge)

O1–O12 of §2.2.

### 11.2 Open questions for the user

- Q1 (scope; widens U1–U7). Keep the parameter replay of §4.6 in this branch? It fixes F2 for every WorldVoice pause, so it also changes, slightly, what is heard after today's punctuation, item and number pauses. Options: (a) keep it here, for every pause and voice switch (recommended; the spec assumes it); (b) split it into its own branch after this one; (c) drop it and accept the loss after a cut, as today.
- Q2 (refines U4). The chunker looked only for U+0020 within one text token. The spec also cuts after any whitespace (newline, tab, ideographic space) and at the boundary between two text items, which NVDA and the VE/Cerence inner drivers speak as a space (F4). Options: (a) both (recommended; the spec assumes it); (b) U+0020 only, item boundaries not candidates (a long item after a short one is then hard-cut inside a word).
- Q3 (refines U4). Leading whitespace of a piece is not counted, and a cut needs non-blank text on both sides, so no piece is only whitespace and no pause lands before trailing spaces. Options: (a) as specified (recommended); (b) count every character from the cut, as the chunker did (then a whitespace-only piece and a pause before trailing spaces are possible, and need extra rules).
