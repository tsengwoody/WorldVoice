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

---

# F5／F6／A1／A4 runtime 邊界完成說明（2026-09-26）

以上 F4 內容與數字保留為歷史紀錄。以下記錄本次 `feat/voice-runtime-boundaries` 實作，基底包含已提交 F2／F3 的 `6256a23`，並保留其回收與取消還原行為。

## 完成內容

- F5 保留 OneCore 已有 `applyEngineSettings()` language hook，透過同 Session 的 A → B → 已快取 A 測試補齊 voice ID、language 與參數切換證據。
- F6 採跳過／恢復策略：不可用語音區段的文字、index、停頓一起跳過，繼續處理切換命令，遇到可用語音再恢復，不自動改用 default。
- A1 將不可變模型、待生效設定、Repository、編輯 session、引擎 Session 與舊 Voice facade 分責。設定頁共用 Store／VoiceEditSession；套用72後預覽81再取消，回到72。
- A4 保留唯一排程 worker／request 狀態機，把 NVDA 事件註冊與通知轉接交給 Bridge；維持同步 done、index 去重、取消競態及逐項資源回收行為。
- 共用契約以直接 Adapter 與正式 LegacyEngineAdapter 執行同一組五項情境；native 路徑在禁止 compat、driver、NVDA 匯入下使用正式 Store、EngineSession、TaskManager。可移除相容層的核心邊界已有測試證據，生產接入仍保留相容入口。

## 實際驗證與審查

- `python3 -m pytest tests/test_runtime_adapter_contract.py -q -p no:cacheprovider`：10 passed in 0.10s。
- `python3 -m pytest tests -q -p no:cacheprovider`：338 passed in 3.28s；未收集 `ref/nvda`。
- 完整回歸通過後 `git diff --check` 成功。移除 voice key 快取比較或保存 checkpoint 的暫時 mutation 均讓兩種 Adapter 測試失敗，還原後通過；正式程式未留下 mutation。
- 任務 1–9 及修正已通過逐任務審查。此文件初稿撰寫時，Task 10 逐任務審查與全分支最終獨立審查仍待執行；不宣稱最終審查完成。

## 本次新增 commits

- `2146422` — `docs: plan voice runtime and compatibility migration`
- `091d307` — `feat: add independent voice state and runtime models`
- `148c47c` — `refactor: separate voice settings persistence and editing`
- `f9132e2` — `feat: add engine session playback contract`
- `826f4ac` — `feat: add removable legacy voice and engine adapters`
- `0b433d1` — `refactor: isolate NVDA speech event bridge`
- `e09f171` — `refactor: decouple speech scheduler from voices and NVDA`
- `7565a07` — `fix: settle cancelled requests and wake cancelled speech tasks`
- `0f9d546` — `fix: recover voice routing after unavailable engines`
- `4e7a9fd` — `fix: preserve cancellation result when request abort races`
- `bb2673f` — `refactor: wire voice sessions and event bridge into WorldVoice`
- `1b042d6` — `fix: preserve shared engines and close admission before shutdown`
- `5824dcc` — `refactor: share voice editing state across settings interfaces`
- `c71df56` — `test: cover main-locale voice consistency apply and discard`
- `22cdb3d` — `test: verify removable compatibility layer and runtime regressions`

## 目前限制

Linux 測試環境無法提供 Windows／NVDA 真實語音輸出證據。OneCore 快取切換、跨引擎長文、說全部、index、尾端停頓、快速取消、pause/resume、GUI 套用、GUI 取消、各內建原生引擎，以及外部引擎接入與可取得版本，均尚未實機驗證；詳見逐項狀態表。**F7 同來源取消後的延遲回呼排空契約仍未處理**。

完整責任邊界稽核、測試證據、提交對照與逐項實機限制位於 [runtime 驗證紀錄](finish/2026-09-26-voice-runtime-boundaries-validation.md)。本次依使用者要求修改此 `finish_task.md`，保留原 F4 內容並追加這個獨立章節。
