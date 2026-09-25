# F4 語音設定延後至下一段生效

## 完成內容

- 新增不可變 `VoiceSnapshot` 與每引擎 `EngineSession`，依 core、Voice ID 和 revision 避免重複套用；設定套用失敗會清除狀態並阻止該段以舊設定播放。
- Voice 設定改為鎖定的待生效值；worker 在每段語音開始前取得一致快照並啟用 Session。UI 預覽、取消還原、語音切換與參數一致性更新都保留下一段生效的邊界。
- VE／Cerence 的 variant、waitfactor，以及 OneCore 的 language 延後到啟用時套用；同一 UI 動作以原子批次更新多個參數。
- Task 1、Task 2、Task 3 的實作與各自 review 均完成；Task 3 的兩輪修正也已 scoped re-review 通過。

## 驗證

- `python3 -m pytest tests -q -p no:cacheprovider`：149 passed（目前含工作區既有 F2/F3 測試）。
- 在乾淨的已提交 checkout 執行 F4 focused tests：20 passed；完整已提交測試集：129 passed。
- `git diff --check` 與 staged diff check 通過。Windows/NVDA 原生語音輸出未能在此環境驗證；引擎 adapter 與播放邊界以 stubs/fake core 覆蓋。

## 本次實作 commits

- `d44f031` — `feat: add per-engine voice activation session`
- `6dd2e09` — `fix: defer voice settings to speech segment start`
- `74d633a` — `fix: defer engine-specific voice parameters`
- `21487da` — `test: make voice preview regression self-contained`
- `1be34aa` — `fix: copy UI voice settings atomically`

完整 commit SHA 可由目前分支 `feat/f4-voice-activation` 的 git history 查閱。原先存在的 F2/F3 未提交變更與未追蹤測試均已保留，沒有納入上述 commits。
