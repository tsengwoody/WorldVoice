# Phase 59 (test-clean3) final review

Branch `phase59-test-clean3`, base `f1bbec0`, HEAD `5dd619a` (61 commits). Review only; nothing committed.

## Verdict: merge after fixes

One Important finding (I1) must be fixed before the merge; three Minors can go in the same pass.
Everything else holds: all whole-branch invariants pass, batch 3 loses no assertion, and X1/X2 are correct for every catalog the repository has.

| Severity | Count |
|---|---|
| Critical | 0 |
| Important | 1 |
| Minor | 3 |

All paths below are relative to the branch unless absolute. My scratch area is
`/tmp/claude-0/-workspace-WorldVoice/9e65e0e5-7706-45c2-8166-5a831b64aee2/scratchpad/p59-final/` (called `$F`):
worktrees `base` (f1bbec0), `head` (5dd619a), `mut` (5dd619a, mutants applied and restored; clean now), `premerge` (34a58a4).

---

## Findings

### I1 (Important): G6-M4 still loses strength after fix 742424f — a "no selection saves the first choice" bug passes the whole suite

`tests/test_settings_panels.py:136-158` (`test_pipeline_panel_keeps_the_stored_choice_when_nothing_is_selected[mode|scope]`).

Fix 742424f changed the stored values from `number`/`WorldVoice` to `none`/`all` so that a "last choice" or "default" bug fails.
But `none` and `all` are the **first** choice of each list (`addon/synthDrivers/WorldVoice/pipeline/settings.py:35-40` for the scope; the mode list is `none, value, number`).
A panel that saves the first choice when nothing is selected now passes. Before the merge the `[number]` and `[WorldVoice]` cases caught it.

No single stored value per control can cover this: the scope has only two choices, `all` (first) and `WorldVoice` (last and default).
So the audit's premise for G6-M4 ("the second value takes no other branch") is true for coverage but not for strength.

Evidence (mutant in `panels/pipeline.py` `onSave`: `None` → `{"number_mode": "none", "scope": "all"}[key]`):

```
$ python3 $F/mutate.py "G6-M4 @HEAD full suite: no selection saves the FIRST choice" addon/globalPlugins/WorldVoice/panels/pipeline.py ... tests
3646 passed in 258.90s

$ MUTROOT=premerge python3 $F/mutate.py "G6-M4 @34a58a4 (before the merge): same mutant" ... tests/test_settings_panels.py
FAILED ...::test_pipeline_panel_keeps_the_stored_mode_when_nothing_is_selected[number]   ('none', 33) == ('number', 33)
FAILED ...::test_pipeline_panel_keeps_the_stored_scope_when_nothing_is_selected[WorldVoice]   ('all', 33) == ('WorldVoice', 33)
2 failed, 59 passed
```

Fix (tried in my scratch copy; keeps the ids `[mode]`/`[scope]` and the count 3646): store the first and the last choice in turn inside the one test.

```python
@pytest.mark.parametrize(
	("attribute", "stored_key", "values"),
	[
		("_number_mode_choice", "numberMode", ("none", "number")),
		("_scope_choice", "scope", ("all", "WorldVoice")),
	],
	ids=["mode", "scope"],
)
def test_pipeline_panel_keeps_the_stored_choice_when_nothing_is_selected(monkeypatch, attribute, stored_key, values):
	# ... The first and the last choice are both stored in turn: one stored value alone is what a
	# panel saving the first choice, the last choice (index -1) or the default would also leave.
	for stored in values:
		with monkeypatch.context() as patch:
			env = pipeline_env(patch, **{stored_key: stored})
			panel, _sizer = build(env, "SpeechPipelinePanel")
			getattr(panel, attribute).Select(-1)
			panel._number_wait_factor_slider.SetValue(33)
			panel.onSave()
			saved = env.conf["WorldVoice"]["pipeline"]
			assert (saved[stored_key], saved["numberWaitFactor"]) == (stored, 33)
```

With it: unmutated 56 passed; first-choice, last-choice and default mutants each fail both ids
(`$F/proposed-G6-M4-fix.diff`; it needs `ruff format`, which only wraps the table as shown above).
The alternative is four ids (the original 2 × 2 in one function), which changes the count to 3648 and the spec arithmetic.
The fix-diff review of 742424f may report the same thing; it is listed here because it is a whole-branch strength loss.

### M1 (Minor): `_catalog` drops an entry, or reads a good one as untranslated, on two legal .po layouts

`tests/test_translator_comments.py:54-67`.

1. An entry is flushed only at a blank line. Two entries with no blank line between them (legal; `msgfmt` accepts it) lose the first one: X2 would not see an unused entry there, and X1 would report a translated string as missing.
2. `fuzzy` is reset only when an active entry is flushed. `msgmerge` writes `#, fuzzy` above obsolete `#~` entries; if an active entry follows one, it reads as untranslated.

Neither occurs today, and both are much more likely to fail loudly than to hide anything. The first is the old parser's behaviour, not new in this branch.

Evidence (`python3 $F/pocheck.py`, comparing `_catalog` with `msgfmt` + `gettext.GNUTranslations`):

```
no-blank-between: DIFFERENT            _catalog: {'b': 'B'}   msgfmt: {'a': 'A', 'b': 'B'}
fuzzy-on-obsolete-then-active: DIFFERENT   _catalog: {}       msgfmt: {'a': 'A'}
```

Fix: flush the pending entry when a `msgid ` line arrives while `field == "msgstr"`, and reset `fuzzy` on every blank line (or when a `#~` line is read).

### M2 (Minor): the spec still describes shapes the branch does not have

`docs/superpowers/specs/2026-11-10-phase59-test-clean3-design.md`:
- `:265` (§6.6 G6-M4) lists `"number"`/`"WorldVoice"` and the rule "one non-default stored value per control". `WorldVoice` is the scope default, so the row contradicts itself, and the implemented values differ (and will differ again after I1).
- `:213` (§6.1 G1-M13) lists `fed` `[]` for the empty case; the test asserts `[0]` (ledger Ruling, Task 5).

Yes, the spec should be corrected. Master's history does this for post-review deviations (`f1bbec0 docs: record the fix review's N1-N4 results`), and the spec is the document a later audit will read.
Fix: one `docs:` commit that rewrites the G6-M4 row to the final shape with the reason (first/last/default must all fail), changes G1-M13's `[]` to `[0]`, and notes the explicit ids of FIX-M2 (G2-M7, G4-M3) and the batch 1 review M2 renames, which §7 does not list.

### M3 (Minor): X1/X2 see only bare-name gettext calls

`tests/test_translator_comments.py:126-131` (and `_translated_modules`, `:81-84`).

Only `ast.Name` calls named `_`, `pgettext`, `ngettext`, `npgettext` are read. `xgettext` also extracts `gettext("x")` and attribute calls such as `translation.gettext("x")` (its default Python keywords). Such a call would be in the .pot but invisible to X1, and its catalog entry would be reported by X2 as unused.
None exists (`grep -rnE '\bgettext\(' addon --include=*.py` outside the inner drivers finds nothing), and NVDA add-ons do not write them, so this is a note on the limit of "every source string".
Fix (optional): add `gettext` to `GETTEXT_NAMES` and treat an `ast.Attribute` whose `attr` is in the set as unsupported.

---

## 1. Batch 3 merges, tidy edits, renames (full depth)

Compared old bodies (`0a3e906`) with HEAD line by line, then mutated the code under test in `$F/mut`.

| Row | Result | Notes |
|---|---|---|
| G7-M1 | no loss | Same message regex, same `not destination.exists()`; keyword and digest per row. |
| G7-M2 | stronger | The class case had `endswith` + level only; now the full record. Versions kept per kind. |
| G7-M3 | no loss | `missing` is computed by the helper and then asserted equal to the literal `synthDrivers.sapi5.…` name, so the literal check stays. |
| G7-M4 | no loss | Byte-exact compare and CRLF check unchanged; only the file table is shared. |
| G8-M1 | no loss | Exact non-debug record list replaces two `in` checks; `== {}` on `load_enabled_engine_classes` stands for the rows' `is None`. |
| G8-M2 | no loss | Whole stored entry asserted for all four refused values (the source had one). |
| G8-M3 | no loss | `BadZipFile` instead of `OSError`; full `env.shown` and the log record. The real-archive link is `test_install_always_removes_the_archive[True]`: `installTasks` catches only `BadZipFile` (`addon/installTasks.py:33`), so that test proves the real function raises it. |
| G8-M4 | stronger | Secure mode: exact `[("unpatch",), ("detach",)]` (was `in` + last). Dead menu: also `item.destroyed is False`. |
| G8-M5 | no loss | Six field checks in one test. |
| T1–T9 | neutral | Each one-row parametrize is inlined with the same literals; T8 keeps every statement and both users of `PAUSE_DEPENDENTS`. |
| T4 | neutral | Drops a "removed comment stays gone" check only. |
| T10 | neutral | `test_six_enabled_profiles_use_shared_lifecycle` asserts `outer.Voice.synthDriverClass is type(core)` for all six engines (`tests/test_runtime_completion_policies.py:428`). |
| Renames (421f4bf) | neutral | Names and comments only; parameters equal (prove.py step 3). |

## 2. Translator checks X1/X2

**Correct for what exists.** `_catalog` gives exactly what `msgfmt` compiles for all seven catalogs in the repository:

```
$ python3 $F/pocheck.py
ar: SAME  ru: SAME  tr: SAME  uk: SAME  zh_CN: SAME  zh_HK: SAME  zh_TW: SAME
multiline+escapes: SAME  crlf: SAME  fuzzy: SAME  fuzzy+format-flag: SAME  previous-msgid: SAME
obsolete: SAME  obsolete-multiline: SAME  no-final-newline: SAME  untranslated: SAME
```

- **Source side.** `_("literal")` with one positional `str` constant is read (implicit concatenation is one constant). `ngettext`, `pgettext`, a non-literal argument, an f-string, keywords or extra arguments are all reported as unsupported with `file:line`. `buildVars.py`'s three calls are included. The inner drivers' `_()` calls are correctly left out: `buildVars.pythonSources` does not reach `driver/<Engine>/driver/`, so `scons pot` never extracts them.
- **Catalog side.** Multi-line strings, escapes, obsolete `#~` entries, `#| msgid` lines and the header are handled. `msgctxt` and plural entries are not parsed, but both fail loudly (X2 reports the msgid as unused or X1 as untranslated), and the source side already rejects those forms. Limits: M1 and M3.
- **Platform-neutral.** Paths are built with `pathlib` and compared as `as_posix()`; every read names `encoding="utf-8"`; `read_text` uses universal newlines, and the CRLF copy of a catalog parses the same (`crlf: SAME`). Nothing depends on the working directory.
- **Replaces D10.** X1 is a superset of "each changed label has a zh_TW msgstr"; X2 is a superset of "no dead msgid in the catalog" and of "each listed label is still used". What is gone is only the `# Translators:` presence check for 18 labels, which spec N8 records as the user's decision.

Mutants (all restored):

```
X1: new source string without a catalog entry   -> X1 fails {'Brand new': [...dialog.py:17]}
X2: source string no longer used                -> X2 fails ['Settings']
X1: multi-line msgid changed in the catalog     -> X1 and X2 fail
X1: fuzzy multi-line entry                      -> X1 fails
X1: multi-line entry msgstr blanked             -> X1 fails
X1: ngettext in source / non-literal argument   -> X1 fails, unsupported [...dialog.py:17]
X1: buildVars summary untranslated              -> X1 fails {'WorldVoice': ['buildVars.py:21']}
```

## 3. Whole-branch invariants

| Invariant | Result | Evidence |
|---|---|---|
| 3646 pass, 0 skipped | holds | `cd $F/head && python3 -m pytest tests -q -p no:cacheprovider` → `3646 passed in 163.13s`. Base: `3998 passed`. |
| `addon/` untouched | holds | `git diff --stat f1bbec0..HEAD -- addon/` prints nothing. Only `tests/` and six `docs/superpowers` files change. |
| Inner drivers untouched | holds | `git diff --name-only f1bbec0..HEAD -- 'driver/*/driver/*'` prints nothing. |
| Removed ids = spec list | holds | My own `--co` diff: 443 ids gone = 294 remove + 131 merge olds + 16 renames + 2 renumbered (N5). No removed id is still collected. |
| Merge olds = `-merge.txt` | holds | All 132 gone except `test_log_labels_come_from_the_table`, which G5-M5 keeps as its target id (spec §9.1 step 2). |
| prove.py | PROOF OK | On jsonl I collected myself from `$F/base` and `$F/head`: `base 3998 head 3646 removed 294 merge-old 132 merge-new 74 kept= 3 renames 16 pairs 2`. |
| Coverage arcs | holds exactly | Coverage API (`$F/arcs.py base.db head.db`): base 14504 arcs, head 14501; lost exactly `(-1,28)`, `(-1,81)`, `(81,-1)` of `globalPlugins/WorldVoice/__init__.py`; gained none. The timing arcs did not differ in my two runs. |

The known Hypothesis failure (`test_property_pause_settings_do_not_change_voices`, `['中文中文-12']`, `segment_length` 4) did not appear in any of my four full runs (fresh worktrees have no example database). It is a master bug and still open.

## 4. Rulings

| Ruling | Judgement |
|---|---|
| collect_params.py sorts set reprs | Sound. Set order is run-dependent; sorted reprs compare equal sets as equal. |
| OneCore-only parametrize in its own commit | Sound. Keeps the deletion commits pure deletions. |
| Report the Hypothesis property failure and continue; set the example db aside | Sound. Reproduced on master by the implementer; no `addon/` change is allowed here. It needs its own fix phase, or it will come back at random. |
| Batch 1 M1: G3-M2 also asserts `"unverified"` | Sound. Present at `tests/test_runtime_completion_policies.py:455-457`. |
| Batch 1 M2: rename kept tests named after deleted cases | Sound. Nothing in `pyproject.toml`, `tools/`, `tests/`, `.github` or the hook config refers to an old name (grep: no hit). |
| G1-M13 empty case asserts `fed == [0]`, not the spec's `[]` | Sound; the source made no claim on `fed`. The spec row should say `[0]` (M2). |
| T10's SAPI5 line goes in the G1-M13 commit | Sound. |
| prove.py `=` lines for G2-M8c | Sound. Three ids are compared by id only; batch 2's review compared their bodies. |
| G6-M4 uses `none`/`all`, "cost if wrong: none" | The reason is right (the spec's values could not catch a last-choice or default bug), but the conclusion is not: the new values cannot catch a first-choice bug (I1). The spec must be corrected either way (M2). |
| A fuzzy entry counts as untranslated | Sound. The build runs `msgfmt -o $TARGET $SOURCE` without `--use-fuzzy` (`site_scons/site_tools/gettexttool/__init__.py:41`), so a fuzzy msgstr is not in the .mo and NVDA shows English. `pocheck.py` confirms `_catalog` equals `msgfmt` on fuzzy entries. |
| Spec defaults N3 (three fragment arcs), N7 (changelog is a source string), §5.2, §5.4, §6 item 5, §7 | Sound. N3: lines 28 and 81 stay covered through the real module, and exactly those three arcs are lost. N7: without it X2 would report the changelog entry. |

## 5. Spot red checks (my own mutants, `$F/mutate.py`, caches deleted before each run)

| Change | Mutant | Result |
|---|---|---|
| G7-M2/M3 | `hostNames.py`: class names never reported missing | 3 class cases fail |
| G7-M2/M3 | module names reported without their module | 3 module cases fail |
| G7-M1 | no checksum check for a download | both cases fail |
| G8-M1 | failure result kept in the mapping | `test_failures_are_logged_and_timed` fails (+4 others) |
| G8-M1 | `ready()` failure logged twice / missing Voice not logged | fails each time |
| G8-M2 | load drops the invalid value from the config | all 4 cases fail |
| G8-M3 | `onFileImport` catches only `OSError` | fails |
| G8-M4 | `terminate` lets `RuntimeError` out | dead-menu test fails |
| G8-M4 | `terminate` skips cleanup without a menu | secure-mode test fails |
| G8-M4 | `removeMenu` swallows `RuntimeError` and destroys | dead-menu test fails (`destroyed`) |
| G8-M4 | detach before unpatch | 4 tests fail |
| G6-M4 (batch 2 fix) | no selection saves the first choice | **survives the whole suite** → I1 |

One mutant of mine for G7-M1 (comparing UnicodeData with the other option's digest) was badly built and failed three unrelated download tests instead; it shows nothing about the merge and is not counted.

## 6. Commit hygiene

- No `Co-Authored-By` in any of the 61 commits (`git log f1bbec0..HEAD --format=%B | grep -ci co-authored` → 0).
- All subjects are `test:` or `docs:`, at most 72 characters, each with a body that says why.
- `git diff --check f1bbec0..HEAD` → clean (rc 0).
- `prek run --all-files` in `$F/head` → all eight hooks Passed, worktree still clean.
- Deletion commits add only shortened lines (`+0`…`+9` added lines each, all cut-down parametrize lists).

## Not checked

- The three fix commits' diffs in depth (742424f, 8073df8, 0a3e906): left to the fix-diff review, except the strength of G6-M4, which is I1.
- Batches 1 and 2 beyond the invariants, the deletion-commit numstat and the G6-M4 mutant: their batch reviews stand.
- Windows itself: X1/X2 were judged by reading and by a CRLF catalog, not run on Windows.

## 修正記錄（Fix results）

每項修正都在 scratch 複本上做過 red check（先清掉 pyc）、單獨跑過改到的檔案、跑過完整測試，並記在進度帳本。

| 來源 | 發現 | Commit | 結果 |
|---|---|---|---|
| 批次 1 review | M1：drain 支援的理由不再要求 `unverified` | `770a9af` | 已修。G3-M2 對每個 drain-supported 模式斷言 `"unverified" in support.reason`；eSpeak 突變（理由不含 unverified）會讓 `[Espeak]` 失敗。 |
| 批次 1 review | M2：保留的測試名稱描述已刪除的案例 | `421f4bf`、`c4e9094` | 已修。兩個測試改名（`test_a_stored_group_mode_reads_numbers_as_values`、`test_group_pieces_of_a_negative_size_is_the_whole_match`），三個「every stored mode」測試加註解說明為何一個模式可代表全部。 |
| 批次 2 review | I1：G6-M4 存的是最後一個選項／預設值 | `742424f` | 改成 `none`／`all`；之後被 final I1 取代（見下）。 |
| 批次 2 review | M1：G1-M7 少了「feed 後仍要等 idle」 | `8073df8` | 已修。idle 在 feed 結束後才放行，`[False]` 先確認進了 idle 且尚未發布。 |
| 批次 2 review | M2：G2-M7、G4-M3 的 id 不好讀 | `0a3e906` | 已修。改成明確的 id；13 個 id 的對應記在帳本。 |
| 修正 review | m1：`none`／`all` 是第一個選項，「存第一個選項」的錯誤抓不到 | `b6c638d` | 已修（同 final I1）。 |
| 修正 review | m2：`events == []` 只檢查一個時間點 | `1d124a3` | 已修。改用 `stays_false`；`bgidle` 突變（drain 在另一個執行緒啟動 idle 後就返回）10/10 抓到，不突變 10/10 通過。 |
| Final review | I1：G6-M4 仍抓不到「存第一個選項」 | `b6c638d` | 已修。同一個測試依序存第一個與最後一個選項；`onSave` 存第一個選項、最後一個選項、預設值三種突變都讓兩個案例失敗。id 與數量不變。 |
| Final review | M1：`_catalog` 在兩種合法的 .po 版面讀錯 | `8df2386` | 已修。遇到空白行、註解或下一個 `msgid` 就結束一筆，fuzzy 標記在每個空白行結束；新增四列的 `_catalog` 表格測試（舊版讀法其中三列失敗）。測試數 3646 → 3650。 |
| Final review | M2：spec 與分支不一致 | `a8cfccd` | 已修。G6-M4、G1-M13 舊值以刪除線保留，新增 §15「Corrections after review」。 |
| Final review | M3：X1/X2 只看裸名稱的 gettext 呼叫 | `ac12bbf` | 已修。依 xgettext 的方式找 `_`、`gettext`、`pgettext`、`ngettext`、`npgettext`（裸名稱或屬性呼叫），掃描所有非排除的 add-on 模組；在 scratch 複本加入 `x.gettext("…")`、`gettext("…")`、`x._("…")` 都會被 X1 指出位置，`x.ngettext(…)` 列為 unsupported。 |

最後驗證：完整測試 3650 passed、0 skipped；`prek run --all-files` 全部 Passed；`git diff --check master` 乾淨；受保護路徑指令無輸出；`git diff --stat master -- addon/` 為空；arc gate（對 `cov-before.db`）只失去 N3 允許的三個 fragment arc。
