# F5／F6／A1／A4 runtime 邊界驗證（2026-09-26）

## 範圍與基底

工作目錄：`/workspace/WorldVoice-runtime-boundaries`。基底包含 `6256a23` 的 F2／F3 修正及 `2146422` 的已核准 spec／plan；`git merge-base --is-ancestor 6256a23 HEAD` 成功。未還原 F2／F3，未修改原生 DLL、NVDA 原始碼或 `ref/`，未納入無關翻譯修改。F7 仍明確不在本次範圍。

## 架構與行為證據

| 項目 | 實作位置與測試 |
| --- | --- |
| F5 快取切回 A | `runtime/session.py` 依 source、voice key、revision 啟用。沿用 OneCore 既有 `applyEngineSettings()` hook；`test_onecore_cached_a_b_a_restores_language`、`test_cached_onecore_voice_round_trip_through_manager` 與共用契約均確認 language／voice ID／參數 |
| F6 跳過與恢復 | `runtime/requestBuilder.py` 繼續處理 SelectVoice；跳過不可用區段的文字、index、break，之後恢復可用語音；`tests/test_runtime_request_builder.py` 同時覆蓋失敗與取消建構 |
| A1 設定與引擎分責 | `runtime/models.py`、`settings.py`、`session.py`、`configRepository.py` 各自擁有資料、編輯狀態、資源與保存；facade/UI 共用 Store 與 VoiceEditSession |
| A4 事件與 request | `runtime/scheduler.py` 唯一 worker／狀態機；`nvdaEventBridge.py` 處理 NVDA 邊界；同步完成、index、取消、Future callback 重入及關閉測試保留 |
| 相容層可移除 | `tests/test_runtime_adapter_contract.py` 五個案例，各以 native／legacy 執行，使用同一正式 Store、EngineSession、TaskManager 與相同斷言；legacy 使用正式 LegacyEngineAdapter |

共用案例包含 A → B → A、pending72 → apply → pending81 → discard、同步 done／index 去重、取消／後續請求、重複關閉一次。native 的匯入限制在 runtime 載入前安裝，直到 worker／Session teardown 完成才解除；同時攔截普通 import 與 importlib.import_module，避免已快取的舊模組繞過限制。`tests/runtime_harness.py` 僅組裝正式核心並提供硬體、Repository、通知出口替身，沒有第二份排程或設定邏輯。

native 在此指直接實作 EngineAdapter 的測試替身。共用契約通過證明核心可以不依賴相容層；它不代表生產入口已移除相容層，也不等於 Windows 原生引擎整合已通過。

## 執行結果

| 命令 | 實際結果 |
| --- | --- |
| `python3 -m pytest tests/test_runtime_adapter_contract.py -q -p no:cacheprovider` | 10 passed in 0.10s |
| `python3 -m pytest tests -q -p no:cacheprovider` | 338 passed in 3.28s |
| `git diff --check`（完整 tests 通過後） | exit 0，無輸出 |

只收集本專案 `tests/`，未收集 `ref/nvda`。完整回歸包含既有 F2／F3、F4、取消包裝、pipeline、UI 與本次 runtime 測試。

測試有效性驗證：暫時移除 Session 快取的 voice key 比較，執行共用契約 `-k cached_a_b_a`，native／legacy 均失敗（2 failed，B 錯用 A 的 ID、language 與參數）；還原後通過。暫時省略成功保存後的 checkpoint，執行 `-k apply_rebases`，兩者均失敗（2 failed，discard 錯回 50 而非 72）；還原後通過。這些 mutation 僅用於驗證測試敏感度，正式 runtime 沒有留下變更。

## 邊界稽核

檢視 `runtime/` 全部 import 及搜尋 `voice.core`／`READY_ENGINE_CLASS`，確認只引用標準庫及 runtime 同層介面，沒有 config、synthDriverHandler、logHandler、compat、driver 匯入或舊型別分支。

搜尋 worker、commit、rollback、save 並閱讀相容轉交方法：唯一 runtime worker 是 `runtime/scheduler.py:TaskManager._worker`；`taskManager.py` 與 `driver/engineSession.py` 僅重新匯出。保存交易由 `VoiceSettingsStore.commit` 統一呼叫 Repository，config 格式寫入只在 `ConfigVoiceSettingsRepository.save`（首次預設初始化也在同一 Repository）。回復值與基準由 `VoiceState` 管理；Store／VoiceEditSession／VoiceFacade 轉交，沒有另存一套取消基準或第二份設定保存實作。內嵌底層引擎本身的 worker 不在這項 runtime 排程遷移範圍。

## Windows／NVDA／原生限制

目前環境為 Linux，沒有可執行的 Windows／NVDA 實機或外部原生引擎版本。

| 實機情境 | 狀態 |
| --- | --- |
| OneCore A → B → 已快取 A（實際發音、language 與參數） | 尚未實機驗證 |
| 跨引擎長文朗讀 | 尚未實機驗證 |
| NVDA 說全部 | 尚未實機驗證 |
| 真實 index callback 與位置更新 | 尚未實機驗證 |
| 尾端停頓與完成時間 | 尚未實機驗證 |
| 快速取消後播放下一筆 | 尚未實機驗證 |
| pause/resume | 尚未實機驗證 |
| 設定 GUI 套用 | 尚未實機驗證 |
| 設定 GUI 取消 | 尚未實機驗證 |
| VE／Cerence／RHVoice／Espeak／SAPI5 原生接入 | 尚未實機驗證 |
| 外部引擎接入及可取得版本 | 尚未實機驗證；此環境未取得可運行版本 |

F7 的同 core 取消後延遲回呼可能被下一筆接收，仍未處理。Bridge 不會憑空建立引擎未提供的 request ID；fake 同步事件與取消測試不能證明原生 callback 已排空。

## 本次提交對照

以下 short SHA 可由分支 git history 解析。

| 任務 | Commit | Subject |
| --- | --- | --- |
| 計畫 | `2146422` | docs: plan voice runtime and compatibility migration |
| 1 | `091d307` | feat: add independent voice state and runtime models |
| 2 | `148c47c` | refactor: separate voice settings persistence and editing |
| 3 | `f9132e2` | feat: add engine session playback contract |
| 4 | `826f4ac` | feat: add removable legacy voice and engine adapters |
| 5 | `0b433d1` | refactor: isolate NVDA speech event bridge |
| 6 | `e09f171` | refactor: decouple speech scheduler from voices and NVDA |
| 6 修正 | `7565a07` | fix: settle cancelled requests and wake cancelled speech tasks |
| 7 | `0f9d546` | fix: recover voice routing after unavailable engines |
| 7 修正 | `4e7a9fd` | fix: preserve cancellation result when request abort races |
| 8 | `bb2673f` | refactor: wire voice sessions and event bridge into WorldVoice |
| 8 修正 | `1b042d6` | fix: preserve shared engines and close admission before shutdown |
| 9 | `5824dcc` | refactor: share voice editing state across settings interfaces |
| 9 補測 | `c71df56` | test: cover main-locale voice consistency apply and discard |
| 10 | `22cdb3d` | test: verify removable compatibility layer and runtime regressions |

文件撰寫時任務 1–9 及其修正已通過逐任務審查；Task 10 的逐任務審查與全分支最終獨立審查尚待執行，不將 self-review 當成獨立審查。另依使用者要求保留 `docs/superpowers/finish_task.md` 原 F4 報告並追加本次完成說明；`review_gpt1.md` 僅追加後續紀錄。
