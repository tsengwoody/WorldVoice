# Number mode and grouping become independent settings

Date: 2026-11-01.
Baseline: `master` `65856d26` (after `feat/number-mode-spaces`: `4fba7887`, `fdb60577`, `65856d26`). Branch: `feat/number-group-independent`, worktree `D:/NVDA/NVDA_development/WorldVoice-number-group` (`ref/` is a folder of junctions; `ref/nvda` -> `D:/NVDA/nvda`, NVDA `master` `0041ab653`).
Baseline numbers (Windows, Python 3.14 venv): `pytest -q tests` -> 3375 passed, 9 failed (all in `tests/test_generated_unicode_data.py`, a Windows line-ending artefact), 1 skipped.
Flow: normal flow (`DEVELOPMENT_WORKFLOW.md` §3.1). This is the spec only; plan and implementation follow (§3.2).

Status:

- U1–U10 were decided by the user (2026-11-01) and are not reopened here (§2.1).
- O1–O8 are orchestrator defaults taken while writing this spec: `Decided by orchestrator with the recommended default; user may override before merge` (§2.2, §12).
- No question is open for the user (§12.2).

References used throughout:

- Number stages: `addon/synthDrivers/WorldVoice/pipeline/numberStages.py` (below: `stages:<line>`).
- Number definitions: `addon/synthDrivers/WorldVoice/pipeline/numbers.py` (below: `numbers:<line>`).
- Break classes and merge: `addon/synthDrivers/WorldVoice/pipeline/breaks.py` (below: `breaks:<line>`).
- Settings table: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (below: `psettings:<line>`).
- Stage table: `addon/synthDrivers/WorldVoice/pipeline/registry.py` (below: `registry:<line>`).
- Synth: `addon/synthDrivers/WorldVoice/__init__.py` (below: `synth:<line>`).
- Panel helpers: `addon/synthDrivers/WorldVoice/ui/{controls,panelLayout,voicePanel}.py`; Speech Pipeline panel: `addon/globalPlugins/WorldVoice/panels/pipeline.py` (below: `ppanel:<line>`).
- NVDA: `ref/nvda/source/...`.

How the claims were checked:

- The design of §4 was prototyped in place in the worktree and reverted with `git checkout` (nothing committed). Every sequence in §3 and §5 is the prototype's output, both the number stage alone and the whole `STAGES` run (`registry:148-157`), through the harness of `tests/test_pipeline_number_edges.py`.
- A Hypothesis check of the U5 rule ran 3000 examples on the prototype through every stage: numbers of 1–7 ASCII digits joined by a space, two spaces, a no-break space, an ideographic space or an item boundary; every mode, group 0–4, item wait 0/10/30, number language default/main/en, number wait 1–40. It passed: no break-free run of output text holds two source numbers, and with group 0 every break-free run is exactly one whole source number (so number mode's joining spaces are never split). This is property P-U5 in §9.3.
- The configobj and wx facts of §7 were checked against the NVDA installed on this machine (`C:/Program Files/NVDA`, `library.zip`, run with its own Python 3.13 and wxPython 4.2.4).

## 0. Findings

### F1. The U5 gap must not depend on the edges any more (resolved by the design, §4.3)

- Today the break between two numbers that only whitespace separates comes from two places (`feat/number-mode-spaces`, `4fba7887`):
  - in the number and group modes, from the number stage's `gap_break`, which `_number_item_segments` puts in only while edges are on (`stages:429-431`, `edge is not None`), and edges are on only in those modes with a pause above 0 (`stages:291-297`);
  - in value and "none", from `number_wait_factor`'s `split_spaced_numbers` (`stages:126-129`, `numbers:36-60`). Number mode skips that split, because it would cut the digits number mode joins with spaces (`stages:127-128`).
- With U4, number + group 0 has no edges. Without a change, `"10 20"` would become the one item `"1 0 2 0"`, and two whole-number items `["10", "20"]` would become `"1 0"`, `"2 0"`, because `number_wait_factor`'s whole-item test (`_both_numbers`, `stages:65-71`) does not recognize `"1 0"` as a number. Both would read as one number of four digits.
- §4.3 states the rule and where each break comes from; §9.3 P-U5 pins it.

### F2. Two numbers in two items: today number mode keeps them apart through the item edges (for information)

- `["10", "20"]` in number mode today gives `"1 0"`, E, `"2 0"`: the item edge breaks of `fix/number-edge-pause-items` (`stages:383-384`), merged into one (`breaks:52-69`). `["第1", "2章"]` gives `"第"`, E, `"1"`, E, `"2"`, E, `"章"`.
- In number mode, `"1"` `"2"` with nothing between sounds like the number 12 read digit by digit, so the break between two numbers matters there more than in value mode. O2 (§2.2) keeps exactly today's break between such numbers in number + group 0 and drops only the edges next to text (U4).

### F3. configobj accepts an integer confspec with `min` only, and any size of integer (U6)

- NVDA validates a stored value on every read (`ref/nvda/source/config/__init__.py:1269-1273`, `_cacheLeaf` -> `validator.check`), and `get` only catches `KeyError` (`:1250-1254`). A missing key reads as the confspec default (`:1220-1228`).
- With NVDA's own configobj (`configobj 5.1.0.dev0` in `library.zip`), `Validator().check("integer(default=0,min=0)", v)` gives: `"0"` -> 0, `"5"` -> 5, `"99999999999999999999"` -> that integer, `"-1"` -> `VdtValueTooSmallError`, `"abc"` and `"3.5"` -> `VdtTypeError`. With `max=2147483647`, `"2147483648"` -> `VdtValueTooBigError`. All three are subclasses of `ValidateError`, which `read_stored` catches and turns into the default, with one debug warning per key and message (`psettings:362-382`).
- On write NVDA validates the new value too (`ref/nvda/source/config/__init__.py:1352`), and skips it when its `str` equals the stored or default value (`:1354-1366`).

### F4. A wx `SpinCtrl` holds a signed 32-bit int; a larger value silently becomes something else (U6)

- `nvdaControls.SelectOnFocusSpinCtrl` is a plain `wx.SpinCtrl` taking `min`, `max`, `initial` (`ref/nvda/source/gui/nvdaControls.py:103-123`). NVDA's largest spin range is a port, `min=1, max=65535` (`ref/nvda/source/gui/settingsDialogs.py:4081-4083`, `ref/nvda/source/_remoteClient/dialogs.py:206-212`); the other spins take their bounds from the confspec (`settingsDialogs.py:1943-1945`).
- Checked with NVDA's installed wxPython 4.2.4 (wxWidgets 3.2.8): `max=2147483647` works and `GetMax()` returns it; `max=2147483648` wraps to `-2147483648`. `initial=2147483648` or `2**40` silently shows 0, and `SetValue(2**31)` shows 0. `ref/nvda/pyproject.toml:29` pins wxPython 4.3.2 for the next NVDA; it still wraps wxWidgets' `int` spin control (manual item M7).
- So a stored size above 2147483647 could not be shown: the panel would show 0 and its next save would write 0. O4 (§2.2) gives the confspec the same maximum, so NVDA refuses such a value on read and it reads as the default 0, as any other invalid value does.

### F5. No migration is needed for the stored mode "group" (U7)

- `number_mode` is normalized on read and on write: an unknown value reads as "value" (`psettings:67-69`, `:188`). After "group" leaves `NUMBER_MODE_CHOICES`, a stored "group" reads as "value"; the ring then finds "value" in `availableNummods` (`ref/nvda/source/synthSettingsRing.py:86-90`), so it never meets an unknown id.
- A user who never changed the group size has nothing stored: the panels write every value, but NVDA skips a value equal to the default it reads (`ref/nvda/source/config/__init__.py:1220-1228`, `:1354-1366`; `psettings:433-437`). Such a user gets the new default 0, as U7 says.

### F6. The 7.0 changelog will describe a mode that no longer exists (for information; U9 keeps it untouched)

- `readme.md:93` (7.0 changelog) says "In digit mode and group mode, the number pause now also separates every number from the text next to it". After this change there is no group mode, and digit mode with group size 0 has no such pause. U9 leaves the 7.0 section as it is; if 7.0 has not been released yet, the coordinator may want to recheck that sentence before the release. O7 adds no new changelog section on this branch.

## 1. Problem

- Number mode mixes two questions: how a number is spoken (as is, as a value, digit by digit) and whether its digits are cut into groups. Grouping exists only as a fourth mode, "group", which always names symbols, never strips thousands separators and always adds edge pauses (`psettings:43-52`, `numbers:63-92`, `stages:291-297`).
- So a user cannot hear a long number in groups read as values ("123", "456") without also losing value mode's thousands rule, cannot hear digits grouped ("1 2 3", "4 5 6"), and cannot get groups while leaving numbers otherwise alone.
- The group size control is enabled only in group mode (`psettings:207`), so its effect is invisible in the other modes.

## 2. Goals and non-goals

### 2.1 Goals (Decided by the user, 2026-11-01)

- **U1. Two independent settings.**
  - Number mode is how one piece of a number is spoken: "none" (off), "value", "number". "group" is removed from the dropdown and from the synth settings ring (`nummod`).
  - Grouping is how runs of digits are cut: `group_size` is 0 or any positive integer; 0 = no grouping.
  - The two combine freely. Group size is enabled in both panels whatever the mode (its `depends_on` is dropped). It stays panel-only, with no ring entry.
- **U2. Group first, then the number mode renders each piece.**
  - Group 0: the whole number match is one piece.
  - Group N > 0: every digit run is cut from the left into pieces of N digits (a leading sign joins the first piece, as now), and every symbol is a piece of its own; a `NumberBreakCommand` (NB) goes between every two pieces.
  - Rendering by mode: none -> digits raw, symbol raw (no symbol name; NVDA's symbol processing decides). value -> digits raw, symbol by its name (or itself when NVDA has no name). number -> digits joined with single spaces, symbol by its name (or itself); with group 0 the whole number, digits and symbol names, is one item joined with spaces, exactly today's number-mode output.
  - "none" with group > 0 does group; none + group 0 keeps today's pass-through (no dot rule, no edges; only a locale number language wrapper applies).
- **U3. Thousands separators.** Value mode strips valid thousands runs first (`remove_thousands_separators`, `stages:23-36`), then groups: `"1,234,567"` value+3 -> `"123"`, NB, `"456"`, NB, `"7"`. Other modes do not strip.
- **U4. Edge pauses** (before and after a number next to spoken text, the item-edge variant and `_merge_edge_breaks` included) are added when group > 0 and the pause > 0, whatever the mode; never when group is 0. Number + group 0 loses them (`"共123元"` -> one item `"共1 2 3元"`); value + group N gains them. A user who wants edge pauses without cutting sets a group larger than the number.
- **U5. Two numbers separated only by whitespace** (`"10 20"`) keep a pause between them in every mode and every group value when the pause > 0, as today. Number mode's own joining spaces are never split. The rule is in §4.3.
- **U6. The `group_size` setting** keeps its stored key (`groupSize`, `stored_key_for("group_size")`, `psettings:77-83`) and field name. Default 0 (was 3). Minimum 0; no practical maximum. An invalid stored value (negative, not an int) reads as the default 0, through `read_stored` and `reset_out_of_range` (`psettings:122-128`, `:362-382`).
- **U7. No migration.** A stored mode "group" reads as "value"; a stored group size, if any, applies as the new grouping whatever the mode. No conversion code.
- **U8. Unchanged:** the dot rule follows the mode (`dot_rule = mode != "none" and ...`, `stages:375`); the number language wrapper and its detection path (`stages:157-225`); value + group 0 output; none + group 0 output.
- **U9. Docs:** the implementer updates the number mode / group paragraphs and the number wait factor bullet of `readme.md` and `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md`; the 7.0 changelog section is not touched. §6.4 gives the en and zh_TW wording.
- **U10.** The coordinator adds "Corrected by" notes to the older specs on `master` after the merge; §11 lists what this reverses.

### 2.2 Orchestrator defaults (Decided by orchestrator with the recommended default; user may override before merge)

- **O1. Pause 0 with group > 0 keeps today's group-mode separators.** The pieces of a number get `NumberBreakCommand(0)` between them, so each reaches the synth as an item of its own, as group mode does today (`stages:245-250`, `tests/test_pipeline_number_edges.py` `test_no_edge_break_without_a_number_pause`). There are no edge and no gap breaks at pause 0 (U4, U5). Alternative: join the pieces at pause 0; rejected because it changes today's group-mode output at pause 0.
- **O2. Number + group 0 keeps today's break between two numbers in two items.** Where one spoken item ends with a number and the next spoken item of the same utterance starts with one, the number stage puts one `NumberItemEdgeBreakCommand` there (rule G2 in §4.3). This is exactly today's number-mode output between such numbers (`["10", "20"]` -> `"1 0"`, E, `"2 0"`; with an item wait of 30, `"1 0"`, B30, `"2 0"`), and it only drops the edges next to text. Value and none + group 0 keep today's whole-item rule of `number_wait_factor` (U8).
- **O3. Number mode + group > 0 renders each digit piece with single spaces, the sign on the first digit:** `"-123456"` number+3 -> `"-1 2 3"`, NB, `"4 5 6"`, as today's number mode puts the sign (`tests/test_pipeline_number_edges.py` row `15` and `"-1 2 3"` in `4fba7887`).
- **O4. The group size's maximum is 2147483647 (`2**31 - 1`) in both the confspec and the spin control** (F3, F4): the largest value a wx `SpinCtrl` holds, so the stored range and the control agree and a larger stored value reads as 0 instead of being shown as 0 and silently saved. `reset_out_of_range` stays on.
- **O5. The label stays "Group size" (zh_TW "每組位數").** All seven locales translate it today (`addon/locale/*/LC_MESSAGES/nvda.po`); a new msgid would put six of them back to English until translators catch up. "0 = no grouping" is made discoverable in the user guide (§6.4). Alternative for the user: `_("Group size (0 = no grouping)")`, zh_TW "每組位數（0 為不分組）" (§6.3).
- **O6. The `.po` files are not edited.** No msgid is added or changed (O5); the msgid "group" simply stops being used, which gettext and `msgfmt --check` accept. The next catalog update (`scons pot` + merge) drops it.
- **O7. No new changelog section** on this branch (F6); release notes are the coordinator's.
- **O8. Mutation testing** (§7 of the workflow) runs only on Linux; on this Windows setup the implementer states that mutmut was not run on `numbers.py` and `numberStages.py`, unless a Linux environment is available.

### 2.3 Non-goals

- `NUMBER_RE`, `NUMBER_TOKEN_RE`, `THOUSANDS_RE`, the sign and hyphen rules and the digit set (`numbers:11-28`, `stages:42-62`).
- Symbol naming and its locale (`pipeline/symbols.py`).
- `remove_thousands_separators` (`stages:23-36`), `split_spaced_numbers` (`numbers:36-60`), `_insert_number_breaks` (`stages:132-154`), `_merge_edge_breaks` (`breaks:52-77`), the item stage (`pipeline/items.py`), the punctuation stage (`pipeline/punctuation.py`) and the unspaced-script stage: none reads the number mode (`grep number_mode`: only `numberStages.py`, `registry.py`, `settings.py`), and they only see the same break classes as today.
- Language detection, `wrap_numbers_for_detection` and `detect_with_number_language` (`stages:157-225`) (U8).
- A ring entry for the group size (U1).
- Known interactions kept as they are since `feat/number-mode-spaces`: a space listed as a punctuation pause character makes every space a pause point, including the spaces number mode puts between digits (`pipeline/punctuation.py`, readme "Punctuation pause characters"); the unspaced-script space pause applies to spaces between Thai or other unspaced-script digits.
- Engine wrappers, the upstream drivers under `driver/<Engine>/driver/`, Neural.

## 3. What an NVDA user hears and sees

### 3.1 Settings

| Where | Today | After |
|---|---|---|
| Number mode list (Voice panel, Speech Pipeline panel) | off, value, number, group | off, value, number |
| Synth settings ring, "Number mode" | off, value, number, group | off, value, number |
| Group size spin | 1–10, default 3, enabled only while the mode is "group" | 0–2147483647, default 0, always enabled |
| Stored `numberMode=group` | group mode | reads as value (U7) |
| Stored `groupSize=4` | used in group mode only | groups every number in every mode (U7) |
| Nothing stored for the group size | 3 | 0 (no grouping) |
| Stored `groupSize=-1`, `abc`, `3000000000` | reads 3 (outside 1..10) | reads 0, one debug warning |

### 3.2 Output (number wait 10, item wait 0, number language "Follow", no punctuation pause, unless stated)

Notation: `|` separates the items the synth gets; NB = `NumberBreakCommand`, E = edge break (`NumberEdgeBreakCommand` or its item variant), PB = punctuation break, B30 = item break of 30. ⟨x⟩ = NVDA's name of symbol x in the number language (or x when NVDA has none). "Today group" is today's group mode with size 3; "today" in the other rows is the same mode today.

| Text | Mode | Today | After, group 0 | After, group 3 |
|---|---|---|---|---|
| `123456` | none | `123456` | same | `123` NB `456` |
| | value | `123456` | same | `123` NB `456` |
| | number | `1 2 3 4 5 6` | same | `1 2 3` NB `4 5 6` |
| | today group | `123` NB `456` | — | — |
| `-123456` | value | `-123456` | same | `-123` NB `456` |
| | number | `-1 2 3 4 5 6` | same | `-1 2 3` NB `4 5 6` |
| `123456.78` | none | `123456.78` | same | `123` NB `456` NB `.` NB `78` |
| | value | `123456.78` | same | `123` NB `456` NB ⟨.⟩ NB `78` |
| | number | `1 2 3 4 5 6 ⟨.⟩ 7 8` | same | `1 2 3` NB `4 5 6` NB ⟨.⟩ NB `7 8` |
| `1234.5678` | value | `1234.5678` | same | `123` NB `4` NB ⟨.⟩ NB `567` NB `8` |
| | number | `1 2 3 4 ⟨.⟩ 5 6 7 8` | same | `1 2 3` NB `4` NB ⟨.⟩ NB `5 6 7` NB `8` |
| `1,234,567` | none | `1,234,567` | same | `1` NB `,` NB `234` NB `,` NB `567` |
| | value | `1234567` | same | `123` NB `456` NB `7` |
| | number | `1 ⟨,⟩ 2 3 4 ⟨,⟩ 5 6 7` | same | `1` NB ⟨,⟩ NB `2 3 4` NB ⟨,⟩ NB `5 6 7` |
| | today group | `1` NB ⟨,⟩ NB `234` NB ⟨,⟩ NB `567` | — | — |
| `5-3` | none | `5-3` | same | `5` NB `-` NB `3` |
| | value | `5-3` | same | `5` NB ⟨-⟩ NB `3` |
| | number | `5 ⟨-⟩ 3` | same | `5` NB ⟨-⟩ NB `3` |
| `10 20` | none, value | `10` NB `20` | same | `10` NB `20` |
| | number | `1 0` NB `2 0` | same | `1 0` NB `2 0` |
| `a 10 20 b` | none, value | `a` \| `10` NB `20` \| `b` | same | `a` E `10` NB `20` E `b` |
| | number | `a` E `1 0` NB `2 0` E `b` | `a 1 0` NB `2 0 b` | `a` E `1 0` NB `2 0` E `b` |
| `["10", "20"]` (two items) | none, value | `10` NB `20` | same | `10` E `20` |
| | number | `1 0` E `2 0` | same (O2) | `1 0` E `2 0` |
| same, item wait 30 | every mode | `…` B30 `…` | same | same |
| `["第1", "2章"]` | none, value | `第1` \| `2章` | same | `第` E `1` E `2` E `章` |
| | number | `第` E `1` E `2` E `章` | `第1` E `2章` (O2) | `第` E `1` E `2` E `章` |
| `共123元` | none, value | `共123元` | same | `共` E `123` E `元` |
| | number | `共` E `1 2 3` E `元` | `共1 2 3元` (U4) | `共` E `1 2 3` E `元` |
| `共123元`, number language en | value | `共` L(en) `123` L(zh) `元` | same | `共` E L(en) `123` L(zh) E `元` |
| | number | `共` E L(en) `1 2 3` L(zh) E `元` | `共` L(en) `1 2 3` L(zh) `元` | `共` E L(en) `1 2 3` L(zh) E `元` |
| | none | `共` L(en) `123` L(zh) `元` | same | `共` E L(en) `123` L(zh) E `元` |
| `COVID-19` | value | `COVID-19` | same | `COVID-` E `19` |
| | number | `COVID-` E `1 9` | `COVID-1 9` | `COVID-` E `1 9` |
| `a -5` | number | `a` E `-5` | `a -5` | `a` E `-5` |
| `12. Next` | none | `12. Next` | same | `12` E `. Next` |
| | value | `12 . Next` | same | `12` E `. Next` |
| | number | `1 2` E `. Next` | `1 2 . Next` | `1 2` E `. Next` |
| `Total. 12`, `.` a pause character | every mode | `Total` `.` PB `12` (number: `1 2`) | same | same |

At a number wait of 0 (U4, U5, O1):

| Text | Mode | Today | After, group 0 | After, group 3 |
|---|---|---|---|---|
| `123456` | none, value | `123456` | same | `123` NB(0) `456` |
| | number | `1 2 3 4 5 6` | same | `1 2 3` NB(0) `4 5 6` |
| `10 20` | none, value | `10 20` | same | `10 20` |
| | number | `1 0 2 0` | same | `1 0 2 0` |
| `共123元` | value | `共123元` | same | `共123元` |
| | number | `共1 2 3元` | same | `共1 2 3元` |

What the user hears, in short:

- Defaults (value mode, group 0) are unchanged.
- Number mode with group 0 (what every number-mode user gets after the update unless a group size is stored): digits joined with spaces, as today, but no pause next to the text around a number. Two numbers still never run together.
- Group size above 0 gives every mode today's group-mode cutting and edge pauses; value mode also keeps its thousands rule, and off mode leaves the groups and symbols to NVDA.
- Old group-mode users with the default size hear plain value mode; those who changed the size keep that grouping, now read in value mode (thousands stripped first) (U7).

## 4. Design

### 4.1 Pieces and rendering (`numbers.py`)

`number_pieces(raw, mode, group_size, name_of)` (`numbers:63-92`) keeps its name and signature, so its callers stay the same, and changes its meaning: it returns the rendered pieces of one number match, in order, one piece when `group_size` is 0. It is built from two pure steps:

1. **Cut** (suggested helper `group_pieces(raw, group_size) -> list[str]`):
   - `group_size <= 0`: `[raw]`.
   - Otherwise, over `NUMBER_TOKEN_RE.findall(raw)` (`numbers:24`): a digit token (leading sign included) is cut into runs of `group_size` digits from the left, the sign joining the first run; a symbol token is a piece of its own. This is today's group cutting (`numbers:80-91`) without the naming.
   - Invariant: `"".join(group_pieces(raw, n)) == raw`.
2. **Render** each piece (suggested helper `render_piece(piece, mode, name_of) -> str`):
   - "none": the piece as it is.
   - "value": a symbol piece (no decimal digit in it; only possible with group > 0) is its name, or itself when `name_of` gives None; any other piece as it is. With group 0 the whole match is one piece and stays raw, as today (`numbers:78-79`).
   - "number": the tokens of the piece, each digit apart (the sign stays on the first digit, O3), each symbol by its name or itself, joined with single spaces. With group 0 this is exactly today's number-mode string (`numbers:80-92` with size 1, joined at `stages:242-244`).

The docstring states the rule and cites U1/U2 (decided by the user, 2026-11-01); the module stays standard-library only (`numbers:3`).

### 4.2 One number (`_translate_number`, `stages:228-250`)

- `pieces = number_pieces(raw, mode, group_size, name_of)`; yield them with one `NumberBreakCommand(number_pause)` instance between every two (the existing loop, `stages:245-250`).
- The number-mode branch that joins the pieces (`stages:242-244`) goes away: with group 0 there is one piece; with group > 0 the pieces are apart by U2. The separators are added at any pause, 0 included (O1).

### 4.3 The number stage (`inject_numbers`, `stages:253-297`; `_inject_item_numbers`, `stages:328-390`; `_number_item_segments`, `stages:393-451`)

**Pass-through.** `if mode == "none" and not wraps` (`stages:284-286`) becomes `if mode == "none" and group_size == 0 and not wraps`. With a group, "none" runs the stage (U2).

**Rendering.** `_number_item_segments` loses its `if mode == "none": yield value` branch (`stages:442-445`); every number goes through `_translate_number`, which renders "none" pieces raw. The dot rule (`stages:375`) is unchanged (U8): never in "none".

**Edges (U4).** The condition `mode in ("number", "group") and pause > 0` (`stages:291`) becomes `group_size > 0 and pause > 0`, whatever the mode. Everything inside is today's mechanism: edge, gap and item-edge break instances (`stages:292`), `_spoken_later` (`stages:314-325`), `_merge_edge_breaks` (`breaks:52-77`).

**The gap rule (U5).** With a number pause above 0, two numbers get exactly one break between them (after all stages: one break of the number pause, or the item pause where an item break meets it and is longer) in two cases:

- **G1.** Inside one text item, only whitespace separates them (`str.isspace()`, a no-break or ideographic space included, as decided on 2026-10-22, `numbers:44-46`).
- **G2.** They are in two text items of one utterance: the last spoken part of the first item is a number, the first spoken part of the next spoken item is a number, and nothing is spoken between them (any commands may lie between; an `EndUtteranceCommand` or `ConfigProfileTriggerCommand` ends the utterance, `stages:304-311`).

Where each break comes from:

| Setting | G1 | G2 |
|---|---|---|
| group > 0, any mode, pause > 0 | the number stage's `gap_break` (a `NumberBreakCommand`), as group mode today (`stages:429-431`) | the item-edge breaks, merged into one (`stages:383-384`, `breaks:52-77`), as today |
| group 0, number, pause > 0 | the number stage's `gap_break` | one `NumberItemEdgeBreakCommand` (O2): `edge_after` on the first item only when the next spoken item starts with a number; no `edge_before` (corrected by the review, M1: it would sit in the same run as `edge_after`, with the same time, after it, so `_merge_edge_breaks` always dropped it) |
| group 0, value or none, pause > 0 | `number_wait_factor`'s `split_spaced_numbers` (`stages:126-129`), unchanged | only for two whole-number items, `_insert_number_breaks` (`stages:132-154`), unchanged (U8) |
| any setting, pause ≤ 0 | none (`stages:122-125`; the stage adds no gap) | none |

Implementation of the group-0 number row:

- `_number_item_segments` puts `gap_break` in where `gap_break is not None` (was `edge is not None`, `stages:429`), and `edge` stays None, so no edge next to text is added.
- `inject_numbers` passes `edges = (None, NumberBreakCommand(pause), NumberItemEdgeBreakCommand(pause))` and runs the list path with `_merge_edge_breaks` for `mode == "number" and group_size == 0 and pause > 0`.
- `_inject_item_numbers` computes, in that case, "the next spoken item of the utterance starts with a number" (a reverse pass like `_spoken_later`, `stages:314-325`, reading the first spoken kind of `_split_numbers_for_language`) and passes it as `edge_after`; it passes no `edge_before` (corrected by the review, M1: a forward "the previous spoken item ended with a number" held under the same condition, and `_merge_edge_breaks` always kept the `edge_after` before it). The existing check `spoken_kinds[-1:] == ["number"]` (`stages:450`) still decides that the first item ends with a number.
- Why the item-edge class: the item stage puts its break in before such a break and keeps the longer of the two (`items.py:16-51`), which gives today's `"1 0"`, B30, `"2 0"` at an item wait of 30; a plain `NumberBreakCommand` there would hide the item break (`items.py:45`). The punctuation stage's edge rules (an edge break does not suppress a boundary pause, `punctuation.py:195`) never apply, because the text before it ends with a number, not a mark.

Number mode's joining spaces are never split:

- `number_wait_factor` keeps skipping `split_spaced_numbers` in number mode, whatever the group (`stages:127-128`, code unchanged; docstring updated to say the number stage places every gap break in number mode).
- In value and none with group > 0, `split_spaced_numbers` still runs but finds nothing: the number stage has already replaced every whitespace gap between two numbers with a break, and its pieces hold no whitespace (as in today's group mode).
- `_insert_number_breaks` never adds a second break: between two pieces or numbers there is already a break, which is not a whole number (`stages:145`).

### 4.4 Settings (`psettings`)

- `NUMBER_MODE_CHOICES` (`psettings:43-52`) loses `("group", _("group"))` and its translator comment. `NUMBER_MODES` follows (`psettings:64`); `_number_mode` maps a stored or written "group" to "value" (`psettings:67-69`).
- `group_size` (`psettings:192-208`):
  - default `0`, `min_value=0`, `max_value=2**31 - 1` (O4; a named constant, for example `SPIN_MAX = 2**31 - 1`, with a comment citing F4), `reset_out_of_range=True`, `control="spin"`, no `depends_on`, no `driver_id` (so no driver setting and no ring entry, `synth:159-161`).
  - confspec: `integer(default=0,min=0,max=2147483647)` (`psettings:130-136`, unchanged code).
  - the comment above it says: grouping is independent of the number mode; 0 is no grouping; a stored value outside 0..max, or not an integer, reads as 0 (NVDA refuses it on read, F3; `read_stored`); `convert` resets one written outside the range the same way (decided by the user, 2026-11-01).
- The comment "Digits per group in group number mode; set in the panels only" (`psettings:192`) becomes "Digits per group, in every number mode (0: no grouping); set in the panels only, so no synth setting".
- `PipelineSettings` (`psettings:302-315`) and `effective` (`psettings:336-355`) are unchanged: `effective` leaves `group_size` and `number_mode` alone, as today.

### 4.5 Panels and synth

- No panel code changes. Both panels build the spin from the table (`ui/controls.py:57-64`, `min=spec.min_value`, `max=spec.max_value`), bind only controller keys (`ppanel:36-39`, `ui/voicePanel.py:62-68`) and apply `depends_on` (`ui/controls.py:102-117`, `ui/panelLayout.py:72-92`). Without the group size's `depends_on`, the number mode is no longer a controller: nothing is bound to its choice, and the spin is never disabled.
- The synth's `availableNummods` comes from `NUMBER_MODE_CHOICES` (`synth:531-532`), so the ring loses "group" by itself.

### 4.6 Break docstrings (`breaks:11-24`)

- `NumberBreakCommand`: "Pause between numbers, between two numbers that only whitespace separates, and, with a group size above 0, between the pieces of a number."
- `NumberEdgeBreakCommand`: "Pause between a number and the spoken text next to it (group size above 0)."
- `NumberItemEdgeBreakCommand`: add "In number mode with no grouping, it is only the pause between a number that ends one item and a number that starts the next."

### 4.7 Code removed, kept and added

- Removed: the "group" choice; the number-mode join branch of `_translate_number`; the "none" branch of `_number_item_segments`; `depends_on` of `group_size`.
- Kept: every break class, `_merge_edge_breaks`, `number_wait_factor`, `split_spaced_numbers`, the thousands stage, the detection path, the dot rule.
- Added: the cut/render helpers (or their equivalent inside `number_pieces`); the "next spoken item starts with a number" pass and the forward flag for the group-0 number case.

## 5. Worked examples for the unit tables

Settings as in §3.2 unless stated (`make_settings` of `tests/test_pipeline_number_edges.py:21-43`: number wait 10, punctuation wait 50, item wait 0). "same" = the full run equals the stage output.

| Id | Sequence | Mode + group, options | Stage output | After `STAGES` |
|---|---|---|---|---|
| i1 | `["123456"]` | number+3 | `"1 2 3"`, NB, `"4 5 6"` | same |
| i2 | `["123456"]` | value+3 | `"123"`, NB, `"456"` | same |
| i3 | `["123456.78"]` | none+3 | `"123"`, NB, `"456"`, NB, `"."`, NB, `"78"` | same |
| i4 | `["1234.5678"]` | value+3 | `"123"`, NB, `"4"`, NB, N("."), NB, `"567"`, NB, `"8"` | same |
| i5 | `["1234.5678"]` | number+3 | `"1 2 3"`, NB, `"4"`, NB, N("."), NB, `"5 6 7"`, NB, `"8"` | same |
| i6 | `["1,234,567"]` | value+3 | (stage alone) `"1"`, NB, N(","), NB, `"234"`, NB, N(","), NB, `"567"` | `"123"`, NB, `"456"`, NB, `"7"` |
| i7 | `["1,234,567"]` | none+3 | `"1"`, NB, `","`, NB, `"234"`, NB, `","`, NB, `"567"` | same |
| i8 | `["-123456"]` | number+3 | `"-1 2 3"`, NB, `"4 5 6"` | same |
| i9 | `["共123元"]` | number+0 | `"共1 2 3元"` | same |
| i10 | `["共123元"]` | value+3 | `"共"`, E, `"123"`, E, `"元"` | same |
| i11 | `["共123元"]` | none+3, numlan en | `"共"`, E, L(en), `"123"`, L(zh), E, `"元"` | same |
| i12 | `["共123元"]` | number+0, numlan en | `"共"`, L(en), `"1 2 3"`, L(zh), `"元"` | same |
| i13 | `["10 20"]` | number+0 | `"1 0"`, NB, `"2 0"` | same |
| i14 | `["10 20"]` | value+0 | `"10 20"` | `"10"`, NB, `"20"` |
| i15 | `["a 10 20 b"]` | number+0 | `"a 1 0"`, NB, `"2 0 b"` | same |
| i16 | `["10", "20"]` | number+0 | `"1 0"`, E, `"2 0"` | same |
| i17 | `["10", "20"]` | number+0, item 30 | `"1 0"`, E, `"2 0"` | `"1 0"`, B30, `"2 0"` |
| i18 | `["第1", "2章"]` | number+0 | `"第1"`, E, `"2章"` | same |
| i19 | `["第1", "2章"]` | value+3 | `"第"`, E, `"1"`, E, `"2"`, E, `"章"` | same |
| i20 | `["5-3"]` | number+3 | `"5"`, NB, N("-"), NB, `"3"` | same |
| i21 | `["COVID-19"]` | number+0 | `"COVID-1 9"` | same |
| i22 | `["12. Next"]` | number+0 | `"1 2 . Next"` | same |
| i23 | `["12. Next"]` | value+3 | `"12"`, E, `" . Next"` | `"12"`, E, `". Next"` |
| i24 | `["123456"]` | none+3, wait 0 | `"123"`, NB(0), `"456"` | same |
| i25 | `["10 20"]` | number+3, wait 0 | `"1 0 2 0"` | same |
| i26 | `["Total. 12"]` | number+0, chars `.` | — | `"Total"`, `"."`, PB, `"1 2"` |
| i27 | `["123"]` | value+10 | `"123"` | same |
| i28 | `["第123章"]` | value+10 | `"第"`, E, `"123"`, E, `"章"` (edges without cutting, U4) | same |
| i29 | `["1", M, "2"]` (M an unknown command) | number+0 | `"1"`, E, M, `"2"` (the two item-edge breaks merge; the first stays) | same |
| i30 | `["10", EU, "20"]` (EU an `EndUtteranceCommand`) | number+0 | `"1 0"`, EU, `"2 0"` (no break across an utterance end) | same |

## 6. Panels, ring, strings and documentation

### 6.1 Voice settings panel (NVDA's, with WorldVoice as the synth)

- Order and focus are unchanged: … Number language, Number mode, Group size, Number wait factor … (the group size is made right after the `nummod` row, `ui/panelLayout.py:95-113`, `tests/test_voice_settings_panel.py:229`).
- NVDA reads the mode list as "Number mode combo box value" with the choices "off", "value", "number". Changing it no longer enables or disables anything.
- NVDA reads the spin as "Group size spin button 0" (label unchanged, O5). It is always enabled; arrow keys step by 1 from 0; typing replaces the selected value (`SelectOnFocusSpinCtrl` selects on focus, `nvdaControls.py:126-129`).
- With another synth, the WorldVoice controls are not made (unchanged).

### 6.2 Speech Pipeline panel

- Same order: Effect scope, Global wait factor, Number mode, Group size, Number wait factor, … (`psettings:140-292`, `panels=("voice", "pipeline")` default).
- Same names as in §6.1; Group size always enabled; Save writes the shown value (`fix/uniform-settings-save`, `psettings:424-443`).

### 6.3 Strings

| msgid | Change | zh_TW |
|---|---|---|
| `group` (number mode choice) | removed from the source | (entry left in the `.po`, unused; O6) |
| `Group size` | unchanged (O5) | 每組位數 (unchanged) |
| `off`, `value`, `number`, `Number &mode`, `Number mode` | unchanged | 不處理, 數值, 數字, 數字模式(&M), 數字模式 |
| Alternative to O5 (only if the user overrides): `Group size (0 = no grouping)` | new msgid | 每組位數（0 為不分組） |

### 6.4 User guide (U9; the implementer also updates ru, uk, zh_CN, zh_HK to match)

English, `readme.md`: replace the "Number mode" bullet and its sub-bullets (`readme.md:46-50`) and the "Number wait factor" bullet (`readme.md:53-56`) with:

```markdown
* Number mode: How each piece of a number is read; "Group size" below decides how a number is cut into pieces.
  * Off: Numbers are left as they are.
  * Numeric mode: Reads numbers as values. For example, "12345" is read as "twelve thousand three hundred forty-five." Commas used as thousands separators, as in "12,345,678", are removed so the number is read as one value; other commas, as in "3,14", are kept.
  * Digit mode: Reads numbers digit by digit. For example, "12345" is read as "one two three four five." Symbols between digits, as in "12.5" or "5-3", are read by their names, such as "dot" or "dash", in the number language. The digits and symbols of a piece are separated by spaces and read without the number pause between them.
* Group size: Cuts the digits of every number into groups counted from the left, in every number mode. 0 (the default) means no grouping: each number is read as one piece. With a size above 0, every symbol between digits is a piece of its own, and the pieces are separated by the pause of the number wait factor. For example, with size 3, "1234.5678" is read as "123", "4", "dot", "567", "8" in numeric mode and as "1 2 3", "4", "dot", "5 6 7", "8" in digit mode. Numeric mode removes thousands separators first, so "1,234,567" is read as "123", "456", "7". With Off and a size above 0, the groups and symbols are left as they are and NVDA reads them as usual; to leave numbers completely alone, choose Off and a group size of 0. A size larger than the longest number keeps numbers whole but still pauses before and after them. The group size is set in the Speech Pipeline panel or the Voice settings panel.
```

and, under "Speech pause adjustment":

```markdown
  * Number wait factor:
    * Two numbers separated only by whitespace get the pause, as in "123 456", in every number mode and with any group size.
    * With a group size above 0, the pause goes between every group and symbol, and also before and after a number, as in "第3章", even when the number is read in the same language as the text. With a group size of 0, a number gets no pause next to the text around it, and in digit mode the digits and symbols of a number get no pause between them.
```

zh_TW, `addon/doc/zh_TW/readme.md`: replace `:46-50` and `:53-56` with:

```markdown
* 數字模式：每一段數字的讀法；數字如何切成幾段，由下方的「每組位數」決定。
 * 不處理：數字保持原樣。
 * 數值模式：將數字作為數值朗讀，例如「12345」會讀作「一萬兩千三百四十五」。作為千分位的逗號（例如「12,345,678」）會被移除，數字以單一數值朗讀；其他逗號（例如「3,14」）保留。
 * 數字模式：逐字朗讀數字，例如「12345」會讀作「一二三四五」。數字之間的符號（例如「12.5」、「5-3」）會以數字語言的符號名稱讀出。同一段的各位數字與符號以空白分開，之間不會依數字停頓參數停頓。
* 每組位數：不論選擇哪一種數字模式，都從左邊開始把每個數字的位數分組。0（預設）為不分組，每個數字整個作為一段朗讀。大於 0 時，數字之間的每個符號自成一段，各段之間會依數字停頓參數停頓。例如每組 3 位時，「1234.5678」在數值模式會讀成「123」、「4」、符號名稱、「567」、「8」，在數字模式會讀成「1 2 3」、「4」、符號名稱、「5 6 7」、「8」。數值模式會先移除千分位逗號，因此「1,234,567」會讀成「123」、「456」、「7」。選擇「不處理」且每組位數大於 0 時，各組數字與符號保持原樣，由 NVDA 照常朗讀；若要完全不處理數字，請選擇「不處理」並把每組位數設為 0。每組位數大於最長的數字時，數字不會被切開，但前後仍會停頓。每組位數可以在語音流程面板或語音設定面板調整。
```

and:

```markdown
 * 數字停頓參數：
  * 只以空白分隔的兩個數字之間會停頓，例如「123 456」，不論數字模式與每組位數為何。
  * 每組位數大於 0 時，每組數字與符號之間會停頓，數字的前後也會停頓，例如「第3章」，即使數字與文字以相同的語言朗讀。每組位數為 0 時，數字與前後文字之間不停頓；在數字模式中，同一個數字的各位數字與符號之間也不停頓。
```

- The features bullet (`readme.md:13`) and the list of global settings (`readme.md:37`, "number mode, group size, …") stay accurate and are not changed.
- The 7.0 changelog sections (`readme.md:89-` and the same sections of the translations) are not touched (U9, F6).

## 7. Settings, data, compatibility and errors

- **Stored keys:** `numberMode` and `groupSize` in `[WorldVoice][pipeline]` keep their names (U6).
- **Confspec:** `groupSize = integer(default=0,min=0,max=2147483647)` (was `integer(default=3,min=1,max=10)`).
- **Reading** (F3, F5): a missing key -> 0; `0..2147483647` -> as stored; `-1`, `abc`, `3.5`, `2147483648` -> NVDA raises a `ValidateError` subclass, `read_stored` returns 0 and logs one debug warning per key and message (`psettings:362-382`); the value stays in the file until the next save of a panel, which writes the shown 0 (`psettings:424-437`).
- **Writing:** `convert` (`psettings:122-128`) returns the default 0 for an int outside 0..2147483647 (`reset_out_of_range`); the spin cannot produce one.
- **Mode:** a stored or written "group" (or "pair", or anything unknown) reads and writes as "value" (`psettings:67-69`, `:188`).
- **No migration code** (U7): a stored group size applies as grouping in whatever mode is stored or read.
- **Profiles:** each NVDA configuration profile keeps its own stored values; nothing else changes.
- **Other synths** (scope "all"): the same stages run; `effective` zeroes the pauses outside scope "all" (`psettings:344-354`), so there a group size above 0 cuts with `NumberBreakCommand(0)` and adds no edges, as group mode does today. Other synths get plain marked breaks (`breaks:80-98`, `registry:111-118`).
- **Errors:** no new failure path. `group_pieces` with a huge size makes one piece per digit run (`range(0, len, size)`); `number_pieces` is total over `NUMBER_RE` matches.

## 8. Affected layers

- Core pipeline (shared by every engine, no engine-specific code): `pipeline/numbers.py`, `pipeline/numberStages.py`, `pipeline/breaks.py` (docstrings), `pipeline/settings.py`.
- UI: no code change (`ui/controls.py`, `ui/panelLayout.py`, `ui/voicePanel.py`, `globalPlugins/WorldVoice/panels/pipeline.py` read the table).
- Synth: no code change (`synth:531-532`).
- Docs: `readme.md`, `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md`.
- Not touched: engine wrappers, `driver/<Engine>/driver/`, generated Unicode data, Neural.

## 9. Test plan

Tests first, red against `master`, then the code. Verification follows the workflow §7 with the Windows specifics: full `pytest -q tests` against the baseline (3375 passed, 9 known failures in `tests/test_generated_unicode_data.py`, 1 skipped), `prek.exe run --files <changed files>`, `git diff --check`, protected paths unchanged.

### 9.1 Existing expectations that change

On the prototype, with the test stand-in settings left at group size 3 there were 178 failures; with their default set to 0, 244 (most of them the edge tests, which assume edges in number mode). Every failure was in these places, and each is an intended change:

- **Stand-in defaults** that mirror the table: `tests/pipeline_harness.py:244`, `tests/test_worldvoice_speak.py:346` (`stage_settings`), `tests/test_pipeline_unspaced_space.py:184` change `group_size=3` to `0`.
- **Edge tests** (`tests/test_pipeline_number_edges.py`, `tests/test_pipeline_number_edge_properties.py`): edges now come from the group, not the mode. `make_settings` (`tests/test_pipeline_number_edges.py:21-43`) and `stage_settings` (`tests/test_pipeline_number_edge_properties.py:29`) keep `size=3` as their default, so the number-mode edge rows keep their expectations with number+3 (every number in them has at most 3 digits and no symbol, except `o4-range`, below). Then:
  - rows meant as value or none (`1v`, `2v`, `6`, `7`, `8v`, `9v`, `13v`, `26v`, `42v`, `o4-plus-value`, the value/none `ITEM_ROWS` and `46`) pass `"size": 0` explicitly and keep their expectations (U8);
  - rows in mode "group" (`4`, `13g`, `group`) become `"mode": "value"` with their size, same expectations (old group mode = value + group N, except thousands);
  - `o4-range` (`"5-3"`) becomes `"5"`, NB, N("-"), NB, `"3"` at number+3, and a new row `o4-range-0` keeps `f"5 {N('-')} 3"` at number+0;
  - `test_number_mode_joins_the_pieces_of_a_number_with_spaces` and `test_no_break_at_all_in_number_mode_without_a_number_pause` pin number+0 (no edges);
  - `test_off_mode_with_a_locale_keeps_the_dots_as_they_are` passes size 0.
- **`tests/test_pipeline_filters.py`**: the number-mode tables (`test_number_mode`, `:402`; `test_number_and_group_modes_name_each_symbol`, `:432`; symbol tests `:440-640`; `test_group_mode_keeps_leading_zeros_and_every_digit`, `:641`; `test_group_separator_is_one_instance_per_number`, `:648`; `test_group_and_number_modes_keep_the_original_digits`, `:688`; `test_off_mode_wraps_only_for_a_locale`, `:777`; `test_group_mode_then_number_wait_breaks_with_the_number_wait`, `:322`) replace mode "group" by value + size, pass size 0 where they mean no grouping, and add none + size and number + size columns. `test_a_stored_pair_mode_reads_numbers_as_values` (`:659`) gains a stored "group" case.
- **Property tests** (§9.3): `MODES`/`SPACED_MODES` (`tests/test_pipeline_number_edge_properties.py:18-19`), `test_property_no_edge_outside_digit_and_group_modes` (`:117-133`), `test_property_one_break_between_numbers` (`:136-160`); `run_group_mode`, `MODE_SIZES`, `GROUP_SIZES` (`tests/test_pipeline_pause_properties.py:262-330`), `test_property_off_mode_is_the_identity_for_the_thousands_and_number_stages` (`:468-477`), `test_property_every_symbol_is_its_own_item_when_some_have_no_name` (`:480-`), `test_property_group_size_convert_keeps_or_resets` (`:704`).
- **Settings** (`tests/test_pipeline_settings_service.py`): `test_table_drives_fields_defaults_keys_and_confspec` (`:42`), `test_number_mode_choices_put_off_first` (`:87`), `test_group_size_confspec_is_its_range` (`:99`), `test_group_size_outside_its_range_reads_as_the_default` (`:177`), the number-mode read/write rows with "group", and the tests whose stored fixtures use the old default.
- **Panels**: `tests/test_settings_panels.py:125-170` (enable/disable by mode) become "always enabled" tests; `:245-294` (out-of-range sizes) use -1 and 2147483648; `tests/test_voice_settings_panel.py:229-330` likewise, and `spin.GetMin(), spin.GetMax()` becomes `(0, 2147483647)` (`:244`); `tests/test_ui_controls.py` dependency tests use the punctuation dependents instead of the group size; `tests/test_panel_layout.py:87-92` (controller keys now only `punctuation_pause_enabled`; the number-mode dependent-state rows go); `tests/test_pipeline_panels.py`, `tests/test_worldvoice_pipeline_settings.py` stored fixtures.
- **Table guard** (`tests/test_settings_table_guard.py:360-361`): "default below the bounds" uses `default=-1` (0 is now valid); "default above the bounds" uses a value above 2147483647.
- **Speak harness** (`tests/test_worldvoice_speak.py`): `test_number_mode_edges_with_detection` runs with group 3 (edges) and gains group-0 rows without edges; `test_value_mode_has_no_edges_with_detection` pins value + group 0.
- **Other**: `tests/test_pipeline_stages.py`, `tests/test_pipeline_nvda_ssml.py`, `tests/test_pipeline_passthrough.py` pass the group size their rows mean.

### 9.2 New unit tests (red first)

- **Worked examples**: rows i1–i30 of §5 in `tests/test_pipeline_number_edges.py` `ROWS` (stage and full run).
- **Pieces** (`tests/test_pipeline_filters.py` or a new `tests/test_pipeline_number_groups.py`), `number_pieces(raw, mode, size, name_of)` with the harness names:

| raw | size | none | value | number |
|---|---|---|---|---|
| `123456` | 0 | `["123456"]` | `["123456"]` | `["1 2 3 4 5 6"]` |
| `123456` | 3 | `["123", "456"]` | same | `["1 2 3", "4 5 6"]` |
| `-1234` | 3 | `["-123", "4"]` | same | `["-1 2 3", "4"]` |
| `+0012` | 3 | `["+001", "2"]` | same | `["+0 0 1", "2"]` |
| `12.5` | 0 | `["12.5"]` | `["12.5"]` | `[f"1 2 {N('.')} 5"]` |
| `12.5` | 2 | `["12", ".", "5"]` | `["12", N("."), "5"]` | `["1 2", N("."), "5"]` |
| `1.,2` (two symbols) | 1 | `["1", ".", ",", "2"]` | `["1", N("."), N(","), "2"]` | same as value |
| `１２３４５` (full-width) | 3 | `["１２３", "４５"]` | same | `["１ ２ ３", "４ ５"]` |
| `5×3` (symbol without a name) | 1 | `["5", "×", "3"]` | `["5", "×", "3"]` | `["5", "×", "3"]` |
| `123` | 2147483647 | `["123"]` | same | `["1 2 3"]` |

- **Stage switches**: none + group 0 without a wrapper returns the same objects (identity, as `tests/test_pipeline_passthrough.py`); none + group 3 is not identity for `"1234"`; value + group 0 output is the same at pause 0 and pause 10; edges appear iff group > 0 and pause > 0, for each mode.
- **Gap rule** (G1/G2): `"10 20"`, `"10\u00a020"`, `"10\u300020"` in each mode × group {0, 3} at pause 10: one break; `["10", "20"]`, `["10", M, "20"]`, `["10", " ", "20"]`, `["10", L(en), "20"]` in number+0: one break; `["10", EU, "20"]`: none; `["第1", "2章"]` number+0: one break between 1 and 2 and none next to 第 or 章; `["第1", "章"]` number+0: none.
- **Thousands then groups**: `"1,234,567"`, `"12,345.678"` value+3 after the thousands and number stages; `"1,23"` (not a valid run) value+3 keeps the comma as a named piece.
- **Settings**: confspec string `integer(default=0,min=0,max=2147483647)`; `convert` of 0, 1, 2147483647 keeps, of -1 and 2147483648 gives 0; reading stored `"-1"`, `"abc"`, `"3.5"`, `"2147483648"` gives 0 with one warning each (with the configobj stub's validation, and the real one where the harness has it); stored "group" reads "value", `synth.nummod = "group"` stores "value"; `NUMBER_MODES == ("none", "value", "number")`; `availableNummods` keys equal `NUMBER_MODES`.
- **Panels**: in both panels the spin is enabled for every stored mode and after every mode choice; the mode choice is not bound (no controller); the spin's range is `(0, 2147483647)`; saving 0 and 2147483647 stores them; a stored `-1` shows 0 and a save writes 0.
- **Guards** (`tests/test_settings_table_guard.py`): `group_size` has no `depends_on`, no `driver_id`, `ring` irrelevant (no driver setting is made, `synth:159-161`), `min_value == 0`, `max_value == 2**31 - 1`, default 0; no entry depends on `number_mode`; the spin's max of every `control="spin"` entry is at most `2**31 - 1` (new check, so a later spin cannot overflow wx, F4).

### 9.3 Property tests (Hypothesis)

New or rewritten (default profile 200 examples; `HYPOTHESIS_PROFILE=deep` for the review):

- **P-G1 (cut).** For any `NUMBER_RE` match `raw` and size n ≥ 1: the cut pieces join to `raw`; each digit piece, sign excluded, has at most n digits and all but the last piece of a run exactly n; each symbol piece is one symbol. Size 0 gives `[raw]`.
- **P-G2 (render).** "none" pieces equal the cut pieces; "value" digit pieces equal the cut ones and symbol pieces are `name_of(s) or s`; "number" pieces, names read back (`read_back_names`, `tests/pipeline_harness.py:27-34`) and spaces removed, equal the cut pieces, and every digit is separated from the next by exactly one space.
- **P-G3 (order).** For every mode and n ≥ 1, the number stage's text items for a lone number, in order, are the rendered pieces with exactly one `NumberBreakCommand` between each two (replaces `test_property_groups_are_separate_items_of_the_chosen_size` and `test_property_breaks_and_names_stay_inside_numbers`, now over all three modes).
- **P-U4 (edges).** For any sequence, mode, number language, roles and wait: with group 0 or wait ≤ 0 the number stage adds no edge-class break next to spoken text that is not a number (with group 0 in number mode, every edge-class break it adds has a number as the last spoken part before it and the first after it); value + group 0 output does not depend on the wait (replaces `test_property_no_edge_outside_digit_and_group_modes`). The existing edge properties (`test_property_edges_keep_the_text`, `test_property_edges_sit_at_number_boundaries`, `test_property_edges_never_meet_another_break`, `test_property_no_edge_at_the_start_or_end_of_the_sequence`, `test_property_no_edge_at_an_utterance_end`, `test_property_items_do_not_change_the_edges`) run over all three modes with sizes 1–10 instead of `SPACED_MODES`.
- **P-U5 (gap, the prototype's check).** Text of numbers of 1–7 digits joined by a space, two spaces, a no-break space, an ideographic space or an item boundary; every mode, group 0–10, item wait {0, 10, 30}, number language default/main/en, wait 1–60; after every stage, split the output at breaks: no run holds two source numbers, and with group 0 every run is exactly one whole source number. `test_property_one_break_between_numbers` counts `NumberBreakCommand`s as (pieces − 1 for every number when group > 0) + whitespace gaps, in every mode.
- **P-U3 (thousands).** For any text, value + n after both number stages equals value + n on `strip_thousands(text)` after the number stage alone.
- **P-none (off).** none + group 0 is the identity of both number stages for any sequence (the existing property, `:468-477`, with `group_size=0`); none + group n keeps every character of the text: without a wrapper, the stage's strings, joined, equal the input text, except that with a wait above 0 each whitespace run that only separates two numbers is replaced by the gap break (G1).
- **P-S (settings).** `convert(v)` is v for 0 ≤ v ≤ 2147483647 and 0 otherwise (`st.integers()`); `read_stored` of `str(v)` for v < 0 gives 0 (replaces `test_property_group_size_convert_keeps_or_resets`).
- **Unchanged and still required:** `test_property_digit_mode_joins_every_digit_with_spaces`, `test_property_number_mode_joins_digits_and_symbols_with_spaces` (now at group 0), the `split_spaced_numbers` properties (`tests/test_pipeline_pause_properties.py:592-640`), `test_property_zero_number_wait_changes_nothing`.

### 9.4 Mutation testing

`numbers.py` and the number stage are core decision modules. On Linux, run mutmut on `numbers.py` and on `inject_numbers`, `_inject_item_numbers`, `_number_item_segments`, `_translate_number`, and record surviving mutants in the review. On this Windows setup mutmut is not available; the implementer says so (O8).

### 9.5 Windows / NVDA manual items

- **M1. Voice settings panel** (WorldVoice): Tab from Number mode to Group size; NVDA says "Group size spin button 0"; the mode list has off, value, number; changing the mode never disables Group size; type 12, Tab away, OK, reopen: 12.
- **M2. Speech Pipeline panel**: the same; Save and reopen; values agree with the Voice panel.
- **M3. Settings ring**: Number mode cycles off, value, number, no "group"; no Group size entry.
- **M4. Upgrade from 7.0**: profile with `numberMode = group` and no `groupSize`: the panels show value and 0, numbers read as values; profile with `numberMode = group`, `groupSize = 4`: value and 4, `"12345678"` read as "1234", "5678" with the pause.
- **M5. Invalid stored values**: hand-edit `groupSize = -1`, `abc`, `3000000000`: WorldVoice loads, reads 0, one debug warning in the log; the panel shows 0; Save writes 0.
- **M6. Listening** (OneCore and one other engine): `123456`, `1234.5678`, `1,234,567`, `共123元`, `10 20`, a two-line selection ending and starting with a number, in each mode with group 0 and 3, number wait 10 and 0; number + group 0 has no pause around `123` in `共123元`; `10 20` never sounds like one number; another synth with scope "all" (eSpeak) gets the pieces as plain breaks.
- **M7. wx range**: the spin accepts 2147483647 and stops there; its width and layout in both panels look right with the 10-digit maximum (installed wxPython 4.2.4; recheck with an NVDA build on wxPython 4.3.2, `ref/nvda/pyproject.toml:29`).

## 10. Risks

- **Number-mode users lose the edge pauses** they had since 7.0 development (U4, decided). The guide (§6.4) tells them to set a group size to get them back.
- **Old group-mode users with the default size lose grouping** (U7, decided).
- **Number + group > 0 cuts at every symbol**, so `3.14` number+3 is `"3"`, NB, ⟨.⟩, NB, `"1 4"`, with pauses that number + group 0 does not have (U2, decided).
- **None + group > 0 hands lone symbols to NVDA** as items of their own; whether NVDA says them depends on the symbol level (U2, decided; M6).
- **The punctuation stage meets "none" symbol pieces** (`"."` as an item between two number breaks) as it met unnamed symbols in group mode; its removal rule keeps one number break (`pipeline/punctuation.py:197-205`), pinned by the existing `test_an_unnamed_symbol_is_left_to_the_punctuation_stage` with none + group n added.

## 11. Earlier decisions this reverses (U10)

For the coordinator's "Corrected by `feat/number-group-independent`" notes after the merge:

- `docs/superpowers/specs/2026-10-21-feat-number-group-mode-design.md:22-23` (group as a mode with size 1–10, default 3; size and wait enabled only in group mode, G4), `:173` (`group_size` default 3, bounds 1–10), `:184-185` (`NUMBER_MODES` with "group").
- `docs/superpowers/specs/2026-10-22-feat-number-unify-design.md:38` (Q5: every break inside a match is NB; now only with a group size above 0, in every mode), `:41-44` (dropdown with "number" and "group"; group sizes and default 3), `:50` (V4: group size enabled only in group mode), `:77` (number and group modes as one algorithm with a size), `:226-227` (mode table rows "number" and "group"), `:337-343` (`group_size` bounds and `depends_on`), `:436` (spin enabled only when "group" is selected).
- `docs/superpowers/specs/2026-10-22-feat-symbol-locale-and-settings-fallback-design.md:84-88` (confspec `default=3, max=10`; out-of-range reads 3), `:107-108` (table rows "reads 3").
- `docs/superpowers/specs/2026-10-24-feat-number-edge-pause-design.md:1` (title), `:92` (U1: edge pauses only in the number and group modes), `:114-117` (O3: where the gap break comes from by mode), `:225` (edges "in the number and group modes").
- `feat/number-mode-spaces` (no spec file; commit `4fba7887`): "the digits-with-pauses reading stays available as group mode with size 1" and the group size range 1..10, in the code comments `psettings:192`, `:199-202`, `numbers:69-76`, `stages:118-120`, `:235-240`, `:263-265`, `:288-290`, `breaks:12-13`, `:17`, which the implementer rewrites.

## 12. Questions and the defaults applied

### 12.1 Orchestrator defaults (Decided by orchestrator with the recommended default; user may override before merge)

O1–O8 in §2.2: separators at pause 0 with a group (O1); number + group 0 keeps today's break between numbers in two items (O2); the sign on the first digit in number mode with a group (O3); maximum 2147483647 in confspec and spin (O4); label unchanged (O5); `.po` files untouched (O6); no new changelog section (O7); mutmut only on Linux (O8).

### 12.2 Open questions for the user

None. No decision of U1–U10 turned out impossible in the code; F1 needed a design, not a new choice (§4.3), and F6 is for information.
