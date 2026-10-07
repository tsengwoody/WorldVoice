# 階段 29：性質測試與變異測試試跑

日期：2026-10-07。
基準：`master`（`f2b9d44`，階段 30 合併完成）。分支：`phase29-property-tests`。
狀態：使用者選擇「A 和 B 都做」（2026-10-07）：A 正式加入 Hypothesis 性質測試；B 在 scratchpad 副本試跑 mutmut（`runtime/completion.py`），結果先回報使用者再決定是否擴大。六家引擎共用契約測試不做。

## A. 性質測試

設定（`tests/conftest.py`）：profile `default`（每個測試 200 例、不設 deadline）每次執行；`deep`（2 萬例）以 `HYPOTHESIS_PROFILE=deep` 手動開啟。找到的反例存在 `.hypothesis/`（已 gitignore）並在之後每次重跑。

| 測試 | 性質 |
| --- | --- |
| `test_text_preprocessing.py::test_property_chunk_pieces_rebuild_the_text_within_the_limit` | 串接等於原文；沒有空段；escape 不被切開；沒有只含 escape 的段；純文字不超過上限（例外：單一字元加附屬字元）；斷開處的尾端 escape 移到下一段；切點不在附屬字元之前（除非緊鄰 escape） |
| `test_text_preprocessing.py::test_property_arabic_runs_only_gain_spaces` | escape 不變；只增加空白；不留下四個以上相同字母的連續；冪等 |
| `test_language_detector.py::test_property_detection_only_inserts_language_changes` | 文字串接不變、沒有空字串；輸入的命令原物件、原順序保留；新增的命令都是 `WVLangChangeCommand` |
| `test_index_codec.py::test_property_encoding_keeps_commands_and_reports_each_index_once_in_order` | 輸入不被修改；非 index 命令原物件保留；index 換成遞增、不重複、在範圍內的 wire index，結尾 marker 在最後；任一 wire index 回報到它為止的原始 index，marker 回報其餘並結束；同一段內重複的原始 index 只在首次出現處回報一次 |

`languageDetection/scripts.py::get_script` 的輸入空間由偵測器的性質測試以任意字元涵蓋，不另寫。

發現：codec 性質第一次執行就找到「同一段內重複的原始 index 只回報一次」。追查 `indexLedger._pending_indexes` 的 `segment.delivered` 集合，這是刻意去重；NVDA 的 SpeechManager 在同一段內不會產生重複 index，所以是設計而非 bug，性質依此描述。

成本：四個測試在 default profile 合計約 2.3 秒（全套 41 → 44 秒）；deep profile 約 4.5 分鐘，全部通過。

## B. mutmut 試跑

見下方「試跑結果」（試跑完成後補上）。
