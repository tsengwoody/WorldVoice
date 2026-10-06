# 階段 27 實作計畫：補上主路徑與覆蓋缺口

Spec：`docs/superpowers/specs/2026-10-06-phase27-coverage-gaps-design.md`。分支 `phase27-coverage-gaps`，基準 `0f536bc`。

A、B 兩組不碰同一個檔案，各在一個 git worktree 平行進行（從 `9b4a036` 開出 `phase27-group-a`、`phase27-group-b`），完成後依序 cherry-pick 回 `phase27-coverage-gaps`。

- A 組（9 個 commit）：`speak()` 端到端、pipeline 指令與空輸入、engine discovery 與 engine package、text chunker 與 Arabic、Say All、core 安裝與 log rotation、event bridge 契約錯誤、script lookup 與基底 Voice、installTasks 改載入真檔。
- B 組（4 個 commit）：`tests/ui_harness.py`（假 wx 與 NVDA 設定面板 mixin）與 `guard_errors`、各設定面板 `makeSettings`、WorldVoice 語音設定面板、global plugin 選單與處理器。

驗證：全套、逐檔單獨執行、ruff、覆蓋率 ≥ 92%、壓力測試；Opus 5.5 審查；fast-forward 合併。
