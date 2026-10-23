# 階段 33 交接紀錄：移除符號對話框、恢復基準語言優先

**分支：** `phase33-remove-symbols`（已 fast-forward merge 到 `master`，`c1a6852`）

**日期：** 2026-10-23

**文件：**

- spec：`docs/superpowers/specs/2026-10-23-phase33-remove-symbols-design.md`
- plan：`docs/superpowers/plans/2026-10-23-phase33-remove-symbols.md`
- review 與修正記錄：`docs/superpowers/finish/2026-10-23-phase33-remove-symbols-review.md`

## 內容

- **A 移除符號功能：** 刪除 `addon/generics/speechSymbols/`、系統匣「Unicode Settings」選單項與 script、主驅動載入 `unicode.dic`、偵測器的 `speechSymbols` 參數與符號分支；zh_TW `nvda.po` 刪除 25 條不再使用的字串。使用者既有的 `unicode.dic` 保留不動。
- **B 恢復基準語言優先：** 判斷順序為目前語言 → 基準語言 → 字元集假設的語言 → 第一個已安裝的候選語言 → 維持目前語言。修正 9816ce0（6.2）起的倒退；拼讀（`process_for_spelling`）採用相同規則。
- **C 只算已安裝的語言：** 目前語言與基準語言都必須有已安裝的語音，才算涵蓋該文字。
- **文件：** 英文與 zh_TW readme 說明新規則；六份 readme 刪除已不存在的「忽略常見標點符號」選項與引言中的「標點符號」。
- **守門：** pytest 遇到 DeprecationWarning 一律失敗（`pyproject.toml`）；`languageDetection/__init__.py` 加入 mutmut 範圍；守門測試確保符號功能不會被加回。

## 驗證（Linux）

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q tests`（merge 後 master） | 2412 passed，0 skipped，0 warnings（基準 2372 passed，2 warnings） |
| `prek run --all-files` | 8 個 hook 全部 Passed |
| `git diff --check`、受保護路徑、Neural `ls-files` | 皆無輸出 |
| `msgfmt --check` zh_TW | exit 0 |
| mutmut（偵測器） | 142 個 mutant，124 killed，18 個存活皆為等價變異（理由見 plan 檔尾） |
| 覆蓋率 | TOTAL 95% → 96%；偵測器 98% → 100% |

## 尚未驗證

未打包，未在 Windows／NVDA 上驗證。需要時從 `c1a6852` 建乾淨的 detached worktree 打包（`DEVELOPMENT_WORKFLOW.md` §6），再逐項確認：

1. NVDA 功能表 → WorldVoice：只剩「Settings」與「File Import」兩項，方向鍵可讀出，兩者都能正常開啟。
2. 輸入手勢 → WorldVoice：沒有「popup unicode settings dialog」。`gestures.ini` 仍綁著這個 script 的設定檔，啟動時 NVDA log 沒有錯誤，按下該鍵沒有反應。
3. 設定檔中有非空的 `unicode.dic`：WorldVoice 啟動後檔案不變（大小與時間戳相同）；全新設定檔不會產生 `unicode.dic`。
4. VE 或 Cerence 加 OneCore，主語音 zh_TW、漢字假設語言 ja、有日文語音：念「你好 hello 世界」，「世界」由中文語音念。
5. 主語音 ja_JP、漢字假設語言 zh_TW：「漢字 hello 漢字」除了 hello 都由日文語音念。
6. 開啟 NVDA 自動語言切換，網頁 `lang="de"` 且沒有德文語音：德文由英文角色的語音念，其中的中文由中文語音念；德文段落裡的數字由主語音念（已知限制）。
7. 主語音 ja_JP 並開啟「信任語音的語言」，拼讀（或逐字閱讀）`a漢`：漢使用日文的字元說明。
8. 合成器載入時，NVDA log 沒有「SpeechSymbols」的計時行，也沒有錯誤。

## 待使用者確認的預設

review 文件「使用者還沒確認的使用者可見預設」一節列出 spec §11 的 Q1–Q7 與其他幾項。最需要留意的是：主語言本身能念的文字，不再套用「字元集假設的語言」設定；6.2 使用者若曾調整這個設定繞過倒退，會聽到不同結果。

## 清理

主 checkout 留有被 git 忽略的 `addon/generics/speechSymbols/__pycache__/`，無害（守門測試允許），但直接在主 checkout 打包會被包進去。可由使用者自行刪除。
