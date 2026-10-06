# 階段 26 實作計畫：斷言改以公開行為為準，等待統一

Spec：`docs/superpowers/specs/2026-10-06-phase26-public-assertions-design.md`。分支 `phase26-public-assertions`，基準 `ffdbbb5`。

1. 等待統一，依檔案群組一個 commit：runtime／scheduler／session → segment host／lifecycle → Vocalizer → RHVoice → OneCore → SAPI5 → eSpeak → request manager 與其他 → failed futures 與 delivery join。卡住 worker 的假件改用 `HOLD_TIMEOUT`（`2 * WAIT_TIMEOUT`），避免卡住在正向等待之前先到期。
2. 私有狀態斷言，依檔案群組一個 commit：scheduler → segment host／lifecycle → eSpeak → runtime（不再為讀取而取鎖）→ RHVoice → OneCore → SAPI5 → VE／Cerence → composition 與主驅動。第 2 類集中成 harness 的具名查詢函式。
3. 收尾：`finally` 中後續檢查依賴的 join 改用 `WAIT_TIMEOUT`。
4. 驗證：收集清單不變、全套與逐檔通過、ruff 乾淨、壓力測試（4 個 worker × 6 輪）與極端負載（8 個 worker × 1 輪）；Opus 5.5 審查；fast-forward 合併。
