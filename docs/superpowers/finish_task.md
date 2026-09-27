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
- 修正最終分支審查三項 Important finding 後，相關測試 88 passed；`python3 -m pytest tests -q -p no:cacheprovider`：350 passed；未收集 `ref/nvda`。
- 完整回歸通過後 `git diff --check` 成功。移除 voice key 快取比較或保存 checkpoint 的暫時 mutation 均讓兩種 Adapter 測試失敗，還原後通過；正式程式未留下 mutation。
- Task 1–10 均完成逐任務獨立審查；全分支 Astra review 找出的三項 Important finding 已修正於 `430be90`，並由 Astra scoped re-review 通過，沒有未解 Critical／Important／Minor finding。

## 本次新增 commits

- 基底 `2146422`（spec／plan）不屬於本次實作新增提交。
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
- `d73feec` — `docs: record runtime contract validation commit`
- `430be90` — `fix: preserve cancellation and legacy voice initialization contracts`（最終審查修正）

以上列出基底之後、完成報告收尾更新之前的 16 個提交；本報告收尾文件提交本身可由目前分支 history 查閱。

## 目前限制

Linux 測試環境無法提供 Windows／NVDA 真實語音輸出證據。OneCore 快取切換、跨引擎長文、說全部、index、尾端停頓、快速取消、pause/resume、GUI 套用、GUI 取消、各內建原生引擎，以及外部引擎接入與可取得版本，均尚未實機驗證；詳見逐項狀態表。**F7 同來源取消後的延遲回呼排空契約仍未處理**。

完整責任邊界稽核、測試證據、提交對照與逐項實機限制位於 [runtime 驗證紀錄](finish/2026-09-26-voice-runtime-boundaries-validation.md)。本次依使用者要求修改此 `finish_task.md`，保留原 F4 內容並追加這個獨立章節。


---

# Segment index 核心交付說明（2026-09-27）

**Tasks 1–7 與 9 已完成；Task 8 仍待 Windows／NVDA／裝置證據，不能宣稱 F7 已在生產環境修復。** 本次建立可驗證的 segment index 核心與 adapter 邊界，但正式 `_VERIFIED_CONTRACTS` 仍為空；OneCore、SAPI5 WASAPI／legacy、VE、Cerence、RHVoice、Espeak 及 external profiles 全部維持 `LEGACY_DONE`，沒有已核准的 index 範圍或實機排空保證。

完成內容包括獨立 `PlaybackContext`、adapter 附加的 `WorldVoiceIndexCommand`、同來源不重用的 ledger 編號、保留 binding generation 的解碼，以及 scheduler 的來源／segment／取消／失敗與 END＋DRAIN 判斷。builder 保留 SelectVoice、Pause、結尾分段；activation 仍只比較 `(source_id, voice_key, revision)`。request 完成仍由唯一 scheduler 決定，再由 bridge 發一次 WorldVoice done；內部 marker 不外洩為 NVDA index。

Task 8 變更後執行 `python3 -m pytest tests -q -p no:cacheprovider`：**569 passed in 7.78s，exit 0**；`git diff --check`：exit 0。runtime AST 稽核的 26 個 imports 沒有 NVDA／compat／driver 依賴，唯一正式 marker 建構位於 `compat/indexCodec.py:27`。獨立逐任務 review 的 Task 1 fixture 修正與 Task 4 generation race 修正均已納入；Task 9 沒有新增程式變更。

完整 [spec 覆蓋、稽核與驗證紀錄](finish/2026-09-27-worldvoice-segment-index-validation.md) 列出來源碼觀察、fake 契約與實機證據的界線。未完成項目是逐引擎／版本／音訊模式的安全整數範圍、子類別與索引行為、空與 command-only 情境、實際尾端音訊、取消重播、說全部、跨引擎、設定切換與 pause/resume，通過後才可新增 exact-key policy 與必要 hook。Linux 通過不能填入 Windows 結果；永久阻塞的 synchronous native call 也仍可能阻塞 shutdown。

## 本次實際新增 commits

基底 `23b176d` 不列為新增提交。以下由 `git log --reverse --format='%H %s' 23b176d..HEAD` 產生，完整列出本交付文件提交前 HEAD `568c902` 的 10 個提交，包含 Task 1 與 Task 4 的修正提交：

- `acf025d92c4666656cb7eb204c2136bc5440b8fd` — `feat: define segment completion context and index command`
- `6f10eeeb5f7521649c010a038d7ce12dc0c2aa9b` — `test: align fixtures with segment completion contracts`
- `f51a37d68899cfa0a669d29e39946608002db0c6` — `feat: correlate driver indexes with speech segments`
- `bfe77280e0419663bdb8bd7309dd7508a8bfafca` — `feat: append internal end indexes at the playback boundary`
- `66182a08cdcc4f233f5df20fc0cdd6d6c8bec52f` — `refactor: decode segment indexes at the NVDA event boundary`
- `885f5758ca0d9e1a332a149b1dc647e6c8c91b1e` — `fix: validate ledger binding generation during marker decode`
- `7eea91f59b9d91604a0945637644332a02fbdb8e` — `feat: complete speech segments with correlated end indexes`
- `1365ae3ce8b834dc7583301fd662b3205f8f24a9` — `refactor: assemble segment event ownership and completion policies`
- `4dd8a27fea12be6f9efbc1831295ed01def585e9` — `test: cover segment index contracts across runtime and legacy adapters`
- `568c9026b52766119a7edf5ab52ffa8c10cd2c13` — `docs: record pending Windows segment completion validation`

本節所在的 Task 9 文件提交訊息為 `docs: record segment index completion validation`；它的 hash 在提交前尚不存在，因此不虛構自我 hash。交付時包含此文件提交的完整清單可用上述 `git log` 命令取得，實際 Task 9 hash 與提交後完整清單另記於 `.superpowers/sdd/2026-09-27-worldvoice-segment-index/task-9-report.md`。
