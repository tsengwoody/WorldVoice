# Phase 51 Review：eSpeak／SAPI5／OneCore 的執行時 NVDA 名稱檢查＋多版本測試

日期：2026-10-28。分支：`phase51-nvda-private-check`（`2fff780..d0fd99b`，9 個 commit：3 個 docs、2 個 feat、1 個 refactor、3 個 test；基準 `master` `2fff780`，3363 passed／0 skipped）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）；6 個 task 少於 10，沒有批次 review，本次是第一次也是唯一一次 review，看整個分支。

依據：

- spec `docs/superpowers/specs/2026-10-28-phase51-nvda-private-check-design.md`（§1.1 發現、§3 清單、§4.2「存在」的定義、§5 版本表、§10 實作紀錄）。
- plan `docs/superpowers/plans/2026-10-28-phase51-nvda-private-check.md`（Review Focus 1–5）。
- 進度帳本 `.superpowers/sdd/2026-10-28-phase51-nvda-private-check/progress.md`（git 忽略；7 個 `Ruling:`）。
- 決策紀錄 `storage/refactor9.md` §6 P51 列（唯讀；使用者選方案 B）。
- 程式碼：`addon/synthDrivers/WorldVoice/runtime/hostNames.py`（新）、`tests/nvda_releases.py`（新）、`driver/Espeak/__init__.py`、`driver/SAPI5/__init__.py`、`driver/OneCore/__init__.py`、`tests/test_native_strategy_guards.py`、`tests/test_nvda_ready.py`、`tests/test_nvda_release_names.py`、`tests/test_runtime_host_names.py`；`engineRegistry/discovery.py:162-225`（未改，只讀）。
- NVDA 原始碼：`ref/nvda` 工作樹（2027.1 dev）與 tag `release-2024.1`…`release-2026.3beta6`，一律用 `git -C ref/nvda show <tag>:<path>` 讀，沒有 checkout。
- 行號以 head `d0fd99b` 為準。

## 結論

**可以 merge，先修 2 項 Important（都是測試強度，不是產品程式碼的錯）。** 沒有 Critical。

- 產品程式碼正確：`missing_host_names` 的「存在」定義（module `hasattr`；class `hasattr` 或 MRO 上任何函式的 `STORE_ATTR`）在每個支援的 NVDA 版本上都沒有假「缺」：我用自己寫的 AST 檢查（不是 bytecode，見驗證表）逐版重算，每個列出的 class 名稱都在 class body 綁定或用 `self.x =` 存，每個 module 名稱都在模組頂層無條件綁定（沒有 `if`／`try` 裡的綁定、沒有 `setattr`／`__dict__`／`__slots__`／`del`、沒有包裝式 decorator）。結果和實作者的 §1.1 表完全一致：SAPI5 在 2024.1–2024.4 缺 22 個、2025.1 缺 16 個、2025.2 缺 15 個，2025.3 起齊全；eSpeak、OneCore 每版齊全。
- 實作者的主要發現屬實：`master` 的 SAPI5 wrapper 在 NVDA 2024.x 連 import 都過不了（`sapi5.SynthDriverAudioStream` 在 2024.4 的 `sapi5.py` 出現 0 次，而 master `driver/SAPI5/__init__.py:135` 在 class 陳述式讀它）；在 2025.1／2025.2 是建構時 `AttributeError`（master `:355-363` `__init__` → NVDA `__init__` → `self._initTts` 進到 wrapper 的 `_initTts` `:428-429` → `_invalidateSegments` `:420-422` `with self._threadCond`，而 2025.2 的 `sapi5.py` 沒有 `_threadCond`）。本 phase 之後是乾淨的一行 warning。
- Python 版本：把 `hostNames.py` 的原語分別在 CPython 3.11.18、3.13.18、3.14.4 下跑過（靜態視圖逐版、合成原始碼的 live 視圖、comprehension／genexpr／lambda／巢狀 class／try／with／async 裡的 `STORE_ATTR`），三個版本輸出逐字相同。Ruling「`STORE_GLOBAL`」的成因（函式內 `global x` 會讓模組層的 `x = …` 也編成 `STORE_GLOBAL`）在三個版本一樣；執行時反正用 `hasattr`，不受影響。
- 「靜態視圖一定比執行時嚴」的說法對本 phase 列出的名稱成立，但一般而言有兩個例外（M1），都已確認今天的 NVDA 沒有碰到。
- 我自己的 23 個突變 19 個被殺、4 個存活；存活的 3 個對應 I1、I2，1 個對應 M2。完整套件 3428 passed／0 skipped（和帳本一致），prek 全 Passed，`git diff --check` 乾淨，受保護路徑沒有變動。

## Critical

無。

## Important

### I1. live 視圖「繼承來的 class 層級名稱算存在」沒有測試釘住（`hostNames.py:72`）

`missing_host_names` 先用 `hasattr(host_class, name)`，所以 NVDA 把一個 method 或 class 屬性搬到基底類別（例如把 `_onEndStream` 搬進 `synthDriverHandler.SynthDriver`）時，執行時仍算存在，不會假略過，這正是 spec §4.2 的設計。但把 `hasattr(host_class, name)` 換成 `name in vars(host_class)`（突變 H1），81 個相關測試全過：`test_inherited_instance_attribute_is_present_live`（`tests/test_runtime_host_names.py:144-145`）只測基底 `__init__` 裡的 `self._base = 1`，那條路由 `_class_stored_names` 的 MRO 走訪補上了，`hasattr` 的繼承部分沒有任何測試在看。

失敗情境：日後有人為了「只看 NVDA 自己的 class」把第 72 行改成 `vars()`，測試全綠，但某版 NVDA 把 `_processQueue` 上移到共同基底後，OneCore 在使用者電腦上被假略過，這是 spec §2 列的最糟失敗。

建議修法：在 `PROBE` 的 `Base` 加一個 method `def _inherited(self): …` 和一個 class 屬性 `_inheritedFlag = 1`，新增 `test_inherited_class_attributes_are_present_live` 斷言 `missing(probe, class_names={"_inherited", "_inheritedFlag"}) == ()`；再加一個反向斷言：對一個「只在 `Base` 的 `vars` 裡、且不是 STORE_ATTR」的名稱，用 `_class_stored_names` 單獨查應該查不到，證明是 `hasattr` 在扛。

### I2. 多版本測試看不出「class 名稱根本沒被檢查」（`tests/nvda_releases.py:136-148`、`:151-171`；`tests/test_nvda_release_names.py:142-149`）

兩個突變存活：

- N1：`release_missing` 把 `class_names=class_names` 換成 `class_names=()`（完全不檢查 class 名稱）。
- N2：`port_names` 只回傳 `NVDA_PRIVATES`，丟掉 `NVDA_OVERRIDES`。

81 個相關測試仍全過，因為 `test_nvda_names_exist_from_the_first_complete_release` 對 2025.3 之前的版本只斷言 `missing` 非空（而 SAPI5 在那些版本本來就缺 3–9 個 module 名稱），對 2025.3 之後只斷言為空；`test_live_and_static_views_agree_on_ref_nvda` 兩邊都用同一個 `port_names`，所以一起少看也一致。也就是說，spec §5「同一份清單逐版比對」裡 class 名稱那一半，目前沒有任何斷言證明它真的被比對過。

失敗情境：日後重構 `nvda_releases.py`（例如把 `port_names` 改成讀 `ast` 的另一種寫法）時少接了 overrides，CI 全綠；之後 NVDA 2027.x 改掉 `_speakThread` 的名字，多版本測試仍綠，使用者更新 NVDA 後 SAPI5 被 `ready()` 略過，沒有人在 CI 先知道，這正是 P51 要防的事。

建議修法：新增一個釘住精確集合的測試，例如 `test_sapi5_boundary_names_are_exact`：`release_missing("SAPI5", "2025.2")` 等於 spec §10 列的 15 個完整限定名稱（含 overrides `_onEndStream`、`_speakThread` 與 private `_threadCond` 等），`release_missing("SAPI5", "2024.1")` 等於 22 個（含 override `_initWasapiAudio`）。一個測試同時殺 N1 和 N2，也把 §1.1 的發現變成可執行的紀錄。

## Minor

### M1. 「靜態視圖一定比較嚴」有兩個已知例外，文件沒寫（`tests/nvda_releases.py:7-8`；spec §4.2）

1. 模組名稱在 `if`／`try` 裡綁定時，靜態視圖看到 `STORE_NAME` 就算存在，但執行時那段可能沒跑（平台條件、`try: import … except ImportError`），這時是**執行時比較嚴**。測試在 Linux 編譯、使用者在 Windows 執行，`try/except ImportError` 正是會差的那種。目前清單裡沒有這種名稱（我的 AST 檢查逐版確認 `cond_module={}`）。
2. 被包裝式 decorator（`functools.wraps`、`lru_cache` 之類）包住的 method，`_function_code`（`hostNames.py:39-50`）只看到包裝函式的 `__code__`，原函式裡的 `self.x =` 看不到；靜態視圖編譯原始碼看得到。目前 NVDA 四個檔案裡的 method 只有 `@property`／`@staticmethod`／`@classmethod`（逐版 grep 確認）。

建議：在 `hostNames.py` 和 `nvda_releases.py` 的 docstring 把這兩個例外寫出來；`_function_code` 順手加 `getattr(value, "__wrapped__", None)` 當候選，一行就把第二個例外關掉。

### M2. 合成的一致性原始碼裡 `Other` 是空的，釘不住「只看指名的 class」（`tests/test_nvda_release_names.py:37-38`；`tests/nvda_releases.py:88`）

把 `const.co_name == class_name` 換成「所有大寫開頭的 class 都算」（突變 N6）仍全綠：`Other` 裡沒有任何名稱，所以聯集不改結果。真實情況是 `sapi5.py` 裡 `SapiSink`、`SynthDriverAudioStream` 有自己的 `self._x`，寫錯會讓靜態視圖把別的 class 的名稱算到 `SynthDriver` 頭上。建議在 `Other` 裡放 `_elsewhere = 1` 和一個 `self._elsewhereStore = 1`，把兩個名稱加進 `CLASS_NAMES`，預期結果多兩個 `m.Cls._elsewhere…`。

### M3. `STORE_GLOBAL` 的成因註解寫錯（`tests/nvda_releases.py:5-6`、`:84`）

註解說「a top-level `global name`（NVDA's `_espeak.py` has some）」。`_espeak.py` 每一版都沒有模組層的 `global`（只有函式內的 `global player, isSpeaking, …`，`release-2024.1:source/synthDrivers/_espeak.py:147,334,369`）；CPython 的 symtable 會把函式裡的 `global x` 記到模組的符號表，所以模組層的 `x = None` 編成 `STORE_GLOBAL`。帳本和 spec §10 的說法是對的，只有這兩處註解不對；`AGREEMENT_SOURCE` 用的「模組層 `global declared`」是另一種觸發方式，效果相同。建議改成「a name a function declares `global` is stored with STORE_GLOBAL at module level too」。

### M4. import 時期守門看不到 `from synthDrivers.<mod> import X`（`tests/test_native_strategy_guards.py:350-383`）

守門只找 `alias.attr` 形式。三個 wrapper 今天只有 `from synthDrivers.sapi5 import SynthDriver as BaseSynthDriver`（`SAPI5/__init__.py:8`、eSpeak 同），`SynthDriver` 缺了本來就什麼都做不了，所以現在沒問題。但日後若有人寫 `from synthDrivers.sapi5 import SapiSink`，2024.x 又會回到 discovery 的 import error 而不是 `ready()` 的一行 log，守門不會紅。建議把 `ImportFrom` 且 `module` 以 `synthDrivers.` 開頭、名稱不是 `SynthDriver` 的情況也列進 `found`。

### M5. 版本表和 `ref/nvda` 的最新 tag 沒有對照（`tests/test_nvda_release_names.py:159-168`）

spec §5 刻意不自動發現 tag，這合理。但更新 `ref/nvda` 後忘了加表，什麼都不會紅。可以加一個不改變結果、只提醒的斷言：`git -C ref/nvda tag -l 'release-*'` 裡最大的 feature release（去掉 beta／rc 後綴，例如 `2026.3`）必須以某個 `RELEASES` 項為前綴，否則失敗並提示「add it to RELEASES」。結果仍不依賴 checkout 內容，只是多一道維護提醒。

### M6. `ready()` 每次啟動都把整個 MRO 反組譯一次（`hostNames.py:53-60`、`:72-76`）

SAPI5 和 OneCore 列的 instance 屬性（`_threadCond`、`_dll`…）永遠不是 class 屬性，所以 `absent` 永遠非空，MRO 走訪每次啟動都會跑。在測試 harness（基底是 stub）量到 SAPI5 14 ms、OneCore 10 ms；真 NVDA 的 MRO 多 `synthDriverHandler.SynthDriver`、`driverHandler.Driver`、`AutoPropertyObject`，估計幾十 ms，而且 discovery 的 `timed(... voice.ready)` 會把時間記進 log。可接受；若日後要省，只對 `absent` 的名稱走訪，或把 `_class_stored_names` 用 `functools.lru_cache` 以 class 為 key 快取。不建議現在動。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整套件（head，序列，記憶體看門狗 3 GB） | `cd /workspace/WorldVoice-phase51 \|\| exit 1; ( while sleep 5; do … pkill -f pytest … done ) & W=$!; PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests; kill $W` | **3428 passed，0 skipped，103.35 s**（基準 3363／0；+65 和帳本一致） |
| prek | `prek run --all-files` | 8 個 hook 全 Passed |
| 空白 | `git diff --check master` | 乾淨（rc 0） |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' …sonic/ …script_data.py …unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 兩個都沒有輸出 |
| 獨立重算 §1.1（AST，不是 bytecode） | 自寫 `astcheck.py`：讀三個 Port 的三個常數；模組名稱 = 模組頂層（含 `if`／`try`／`with`）的 Assign／Import／def／class 綁定；class 名稱 = 指名 class body 的綁定 ∪ class 內任何 `Attribute(ctx=Store)`；記錄綁定的上下文 | 11 個版本 × 3 引擎：eSpeak、OneCore 全齊；SAPI5 2024.1–2024.4 缺 9 module＋13 class、2025.1 缺 3＋13、2025.2 缺 3＋12，名稱和 spec §10 逐一相同；**沒有任何列出的名稱是條件綁定或存在非 `self` 的物件上** |
| NVDA 原始碼的綁定方式 | `git -C ref/nvda show <tag>:source/synthDrivers/{sapi5,oneCore,espeak,_espeak}.py \| grep -nE '^\s*@\|setattr(\|__dict__\|__slots__\|^\s*del \|global '`（2024.1、2025.1、2025.2、2025.3、2026.1、2026.3beta6） | method 上只有 `@property`／`@staticmethod`／`@classmethod`；`setattr`／`__dict__`／`__slots__` 都沒有；`del` 只刪 dict 項；`global` 只在函式內 |
| SAPI5 在 master 的失敗點 | `git show master:…/SAPI5/__init__.py`（`:135`、`:355-363`、`:366-370`、`:420-434`）對照 `release-2024.4`（`SynthDriverAudioStream` 0 次）與 `release-2025.2:source/synthDrivers/sapi5.py:290-303,445-463`（`__init__` 呼叫 `_initTts`；沒有 `_threadCond`） | 2024.x import 失敗；2025.1／2025.2 在 `__init__` → `_initTts` → `_invalidateSegments` 的 `with self._threadCond` 丟 `AttributeError` |
| 點版本不改驅動檔（spec §5 的前提） | `git -C ref/nvda diff --stat release-X release-X.Y -- source/synthDrivers/{sapi5,oneCore,espeak,_espeak}.py`（2024.3.1、2024.4.2、2025.1.2、2025.3.3、2026.1.1） | 全部空 |
| Python 3.11／3.13／3.14 bytecode | 用 uv 裝 CPython 3.11.18、3.13.18 到 scratchpad；自寫 `pyver.py` 以 `importlib` 直接載入 `hostNames.py`，對 11 版 × 3 引擎跑靜態視圖、對 `PROBE` 跑 live 視圖、對含 list comprehension／genexpr／lambda／巢狀 class／try／with／async 的原始碼跑 `stored_attribute_names` | 三個版本的輸出 `diff` 只差版本號那一行；`stores` 都是 `_fromAsync,_fromExcept,_fromInner,_fromListComp,_fromNestedClass,_fromTry,_fromWith` |
| `STORE_GLOBAL` 成因 | 3.14 下編譯 `release-2024.1` 的 `_espeak.py`；最小重現 `x = 1\ndef f():\n\tglobal x\n\tx = 2` | 模組層 `isSpeaking`、`onIndexReached`、`player`、`espeakDLL` 等是 `STORE_GLOBAL`；重現碼也是，證明是函式內 `global` 造成，不是模組層 `global` |
| `_nvdaBase` 之外沒有 import 時期的 NVDA 讀取 | 自寫 AST 走訪列出三個 wrapper 所有 class body 的非 def 陳述式、所有 base 與 decorator、模組層非 import 陳述式 | 只有常數、dataclass 欄位、`frozenset` 清單；base 只有 `_nvdaBase('…')`、`BaseSynthDriver`、`BaseOneCoreSynthDriver`、core 類別；wrapper 的 `SynthDriver` 沒有 `_get_`／`_set_`（`AutoPropertyType.__init__` 在 2024.1 不會對它做事） |
| `dis` 在 NVDA 裡可用 | `release-2024.1:source/logHandler.py:15` 與工作樹 `:15` 都 `import inspect` | `inspect` 匯入 `dis`，frozen library 一定有 |
| `versionInfo.version` 來源 | `release-2024.1:source/versionInfo.py:12` `from buildVersion import *`；`buildVersion.py:67-80` | `version` 為 `2024.1.0` 型式；wrapper 的 `_nvdaLabel` 在函式內 import，載入 wrapper 不需要新 stub（`test_ready_on_ref_nvda_is_true_and_silent` 用會丟例外的 `UnreadVersion` 證明齊全時完全不讀） |
| discovery／voice manager 沒動 | `git diff --stat master`；`grep -rn '\.ready()'` | 11 個檔案裡沒有 `engineRegistry/`、`voices/`；`ready()` 只在 `discovery.py:219` 被呼叫，`False` → `continue` 沒有自己的 log |
| 即時檢查的成本 | 暫時 worktree 的一次性測試，harness 真 `ref/nvda` class，5 次平均 | SAPI5 14.1 ms、OneCore 10.3 ms、eSpeak 0.0 ms（M6） |

### 突變測試（審閱者自己的 23 個，暫時 worktree `scratchpad/mut`（已移除），`PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider -x`，每個 300 s timeout，先清 `__pycache__`，輸出寫到 `scratchpad/mutants.log`；測試檔 `test_runtime_host_names.py`、`test_nvda_release_names.py`、`test_nvda_ready.py`、`test_native_strategy_guards.py`）

| 編號 | 突變 | 結果 |
| --- | --- | --- |
| H1 | `hasattr(host_class, name)` → `name in vars(host_class)` | **存活**（I1） |
| H2 | MRO 走訪跳過 class 自己（`__mro__[1:]`） | 殺 |
| H3 | module 名稱永遠不缺 | 殺 |
| H5 | `_nested_code` 只走一層 | 殺 |
| H6 | `absent` 直接回報，不查 `stored` | 殺 |
| N1 | `release_missing` 不檢查 class 名稱 | **存活**（I2） |
| N2 | `port_names` 丟掉 `NVDA_OVERRIDES` | **存活**（I2） |
| N3 | 靜態 class 視圖忽略 class body 的 `STORE_NAME` | 殺 |
| N4 | tag 缺時回空字串而不 `pytest.fail` | 殺 |
| N5 | 靜態模組視圖丟掉 `STORE_GLOBAL` | 殺 |
| N6 | 靜態 class 視圖聯集所有大寫開頭的 class | **存活**（M2） |
| W0 | SAPI5 的 `Voice.ready()` 拿掉（回到基底 `True`） | 殺 |
| W1 | eSpeak `ready()` 不傳 overrides | 殺 |
| W2 | OneCore `ready()` 檢查 vendored 子類而不是 `oneCore.SynthDriver` | 殺 |
| W3 | OneCore `ready()` 不傳 module 名稱 | 殺 |
| W4 | `_nvdaBase` 預設 `None` | 殺 |
| W5 | SAPI5 `ready()` 以 `info` 記 log | 殺 |
| G1 | SAPI5 模組層讀 `sapi5.SpeechVoiceSpeakFlags` | 殺（import 時期守門） |
| G2 | SAPI5 在函式預設引數讀 `sapi5.X` | 殺 |
| G3 | SAPI5 函式內讀未列的 `sapi5.unlistedName` | 殺（module 讀取相等守門） |
| G4 | eSpeak 函式內讀未列的 `_espeak.unlistedName` | 殺 |
| G5 | `_SegmentSapiSink` 改回直接 `sapi5.SapiSink` | 殺 |
| G6 | OneCore 多列一個不存在的 module 名稱 | 殺（多版本測試） |

### Review Focus 逐項

1. class 層級預設或 property（`_get_x`）算存在：`test_class_level_and_property_names_are_present`（`:128-130`）有；`AutoPropertyType` 產生的 `Getter` 沒有 `fget`，但 `_get_x` 函式本身仍在 class dict，`_function_code` 看得到。通過。
2. 基底 `__init__` 做的 instance 屬性：live 不略過（`:144-145`）、靜態會缺（`test_static_view_does_not_see_out_of_file_bases`）。通過；class 層級的繼承沒有測（I1）。
3. 2024.x 沒有 `SynthDriverAudioStream`：`test_sapi5_imports_and_skips_without_audio_stream_class` 從真 `ref/nvda` 模組刪掉它再載入 wrapper，`ready()` False 且只有那一個名稱。通過；W4、G5 證明測試真的綁住 `_nvdaBase`。
4. 全齊時不讀 `versionInfo`、不記 log：`UnreadVersion` 會丟 `AssertionError`。通過。
5. tag 缺時失敗並提示：N4 證明。通過。

## Ruling 評估

| Ruling | 評估 |
| --- | --- |
| Task 1：缺名稱以純字串排序（class 項在小寫 module 項前） | 合理；輸出確定性即可，順序只影響讀 log。 |
| Task 4：`ENGINES`／`port_names`／`release_missing` 提早搬到 `tests/nvda_releases.py` | 合理。 |
| Task 4：靜態模組視圖加 `STORE_GLOBAL` | 必要且正確；成因是函式內 `global`（M3 只是註解寫錯），三個 Python 版本行為一致。 |
| Task 4：OneCore 的 `NVDA_MODULE_NAMES` 加 `SynthDriver` | 合理；守門是相等比對，少列反而紅。vendored 內層 `driver/OneCore/driver/__init__.py:1` `from synthDrivers.oneCore import SynthDriver` 在 wrapper import 前就會先失敗，所以 `ready()` 的引數不可能先炸，帳本說法屬實。 |
| Task 4：`_nvdaBase("X")` 算作讀 `sapi5.X` | 合理；G5 證明直接讀會被另一個守門擋下。 |
| Task 6：文字突變取代 mutmut | 可接受（§7 說「跑 mutmut」，但目標測試幾秒就跑完，mutmut 每個突變跑全套件不划算）；實作者 18 個加我 23 個，交集不多。 |
| Task 6：拿掉 MRO 走訪的 `object` 跳過 | 等價；`object` 的成員沒有 `__code__`。 |

## 使用者還沒確認的使用者可見預設

1. **SAPI5 在 NVDA 2024.1–2025.2 被略過**（spec §9 Q1，預設 (a)）：今天本來就是壞的，現在變成 log 一行 warning、沒有 SAPI5 語音。`buildVars.py:39` 仍宣告最低 2024.1，readme 沒有提 SAPI5 需要 2025.3；協調者另外向使用者提問。
2. 略過的 log 等級是 **warning**，不是 error（spec §4.1）：不會觸發 NVDA 的錯誤音效；和 discovery 其他 `Skipping … engine candidate` 行一致。
3. **module 名稱包含公開名稱**（`config`、`nvwave`、`SonicStream` 等，spec §3）：少一個就整個引擎略過，不只 underscore 名稱。
4. 版本表 **手動維護**（spec §5）：更新 `ref/nvda` 時要手動加 `RELEASES`；沒有自動發現（M5）。
5. 不改 readme／changelog（spec §6）：支援版本上的行為沒變。
6. spec §9 Q2：`SapiSink`／`SynthDriverAudioStream` 的被覆寫成員、公開 instance 屬性、eSpeak DLL 匯出都不檢查。

## 未在 Linux 驗證的項目（Windows／NVDA 手動）

1. NVDA 2026.x（≥ 2025.3）＋WorldVoice：三個引擎都列出語音、能說話；log 裡**沒有** `Skipping … engine candidate` 行；discovery 的 `ready check SAPI5 voice.ready` 計時在幾十 ms 內。
2. NVDA 2024.x 或 2025.1／2025.2（有的話）＋WorldVoice：log 恰好一行 `Skipping SAPI5 engine candidate: NVDA 2024.4.0 lacks names this engine needs: synthDrivers.sapi5.ISpEventSource, …`（2024.x 22 個、2025.1 16 個、2025.2 15 個），沒有 traceback、沒有 `Failed to load ready state for SAPI5`；eSpeak、OneCore 正常。
3. 2024.x 上 wrapper 模組 import 成功這件事只在 Linux 用刪掉 `SynthDriverAudioStream` 的 `ref/nvda` 模擬；真 2024.x 的 `comtypes`／`AutoPropertyType` 環境下 `class SynthDriver(BaseSynthDriver, SegmentDrainCore)` 的建立沒有驗證（分析上沒有問題，見驗證表）。
4. NVDA 真實 MRO 下 `ready()` 的實際耗時（M6）。

## 修正記錄

修正者：Opus 5.5（DEVELOPMENT_WORKFLOW.md §3.4）。範圍 `10da13a..50861ac`，10 個 commit。完整套件（序列，記憶體看門狗 3 GB）**3435 passed，0 skipped**（3428＋7：I1 1、I2 4、M1 1、M5 1）；`prek run --all-files` 8 個 hook 全 Passed；`git diff --check master` 乾淨；受保護路徑（內層驅動、`driver/sonic/`、兩個 Unicode 資料檔）與 Neural 沒有輸出。

突變驗證：暫時複本 `scratchpad/p51fix/wt`（已移除），`PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`，先清 `__pycache__`，每個 300 s timeout，跑本檔列的四個測試檔，輸出寫到 `scratchpad/p51fix/*.log`。

| 項目 | commit | 修法 | red／green 證據 |
| --- | --- | --- | --- |
| I1 | `38d440f` | `PROBE` 的 `Base` 加 method `_inherited` 與 class 屬性 `_inheritedFlag`；新測試 `test_inherited_class_attributes_are_present_live` 先斷言兩者不在 `_class_stored_names` 裡（證明是 `hasattr` 在扛），再斷言 live 不缺 | H1（`name in vars(host_class)`）：修前存活 → 修後**殺**（1 failed，正是新測試） |
| I2 | `06623d7` | `test_sapi5_names_missing_before_2025_3_are_exact[2024.1/2024.4/2025.1/2025.2]` 釘住 spec §10 的完整限定名稱集合：22／22／16／15 個（含 overrides `_onEndStream`、`_speakThread`、`_initWasapiAudio`） | N1（`class_names=()`）、N2（`port_names` 丟掉 `NVDA_OVERRIDES`）：修前存活 → 修後都**殺**（各 4 failed） |
| M2 | `b0bdb36` | 合成原始碼的 `Other` 加 `_elsewhere = 1` 與 `self._elsewhereStore = 1`，兩個名稱列入 `CLASS_NAMES`，預期 live 與 static 都回報 `m.Cls._elsewhere`、`m.Cls._elsewhereStore` | N6（聯集所有大寫開頭的 class）：修前存活 → 修後**殺** |
| M3 | `e7bc862` | `tests/nvda_releases.py` docstring 與 `static_missing` 的註解改成「函式宣告 `global` 的名稱在模組層也編成 `STORE_GLOBAL`（`_espeak.py` 的 `player`、`isSpeaking` 等）；模組層 `global` 陳述式效果相同」 | 只改註解，無測試 |
| M1 | `bc254a1`、`6777b5e`、`50861ac` | `_function_code` 加 `getattr(value, "__wrapped__", None)` 候選（先寫 `test_stores_under_a_wrapping_decorator_are_present`，修前 red：`1 failed, 13 passed`，修後 green）；`hostNames.py` docstring 寫明讀哪些函式；`nvda_releases.py` docstring 寫出兩個例外（`if`／`try` 裡綁定的模組名稱、沒有保留 `__wrapped__` 的包裝）並註明本次 review 逐版人工確認、新名稱不會自動檢查；spec §4.2 加註 | 反向突變 W1（拿掉 `__wrapped__` 候選）：**殺** |
| M4 | `a39d79c` | `test_wrappers_read_no_nvda_module_attribute_at_import` 也列出 import 時期的 `from synthDrivers.<mod> import X`（`level == 0`，排除 `synthDrivers.WorldVoice…`，只容許 `SynthDriver`） | G7（SAPI5 加 `from synthDrivers.sapi5 import SapiSink`）：修前存活 → 修後**殺** |
| M5 | `6d88655` | 新測試 `test_release_table_includes_the_newest_ref_nvda_release`：讀 `git -C ref/nvda tag -l 'release-*'`，取最新 feature release 的 year.minor（含 beta／rc tag），不在 `RELEASES` 時失敗並提示「add its newest tag to RELEASES」；沒有任何 tag 時 `pytest.fail`（附 fetch 提示），不 skip。`RELEASES` 上方註解同步說明 | R1（`RELEASES` 拿掉 `2026.3beta6`）：修前存活 → 修後**殺** |
| M6 | 不修 | 量到 harness 中 SAPI5 約 14 ms、OneCore 約 10 ms，每次啟動一次；真 NVDA 的 MRO 較長，列入 Windows 手動項目 4（`ready check … voice.ready` 計時）觀察。日後要省再只對 `absent` 走訪或以 class 為 key 快取 | — |
| 使用者決定（2026-10-28） | `ddd9c55` | SAPI5 在 NVDA < 2025.3 維持略過、最低版本維持 2024.1，並在文件寫明 SAPI5 需要 NVDA 2025.3 以上：根目錄 `readme.md` 與 `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` 的「Notes／注意」各加一點、「Next update／下一版更新」各加一條變更紀錄；spec §6、§9 Q1 標註 `Decided by the user (2026-10-28)` | 文件；完整套件不變 |

`Ruling:`（已寫入進度帳本）：

- M1 採用 `__wrapped__` 候選：有 red→green 測試，只會讓 live 視圖多認得名稱、和靜態視圖一致；今天 NVDA 沒有這樣包裝的 method。
- M5 比對的是最新 tag 的 year.minor，不是逐字的最新 tag：同一個 feature release 出新的 beta／rc 不會紅，套件只在使用者更新 `ref/nvda` 時才可能變動。
- M6 不修（理由如上）。
- 使用者決定覆蓋 spec §6 原本的「readme 不改」。

本輪有 Important（I1、I2），依 §3.4 由協調者另派修正 review。

## 修正 review（Opus xHigh）

日期：2026-10-28。審閱者：Opus 5.5（effort xHigh，DEVELOPMENT_WORKFLOW.md §3.4 修正 review；唯讀，只新增本段）。範圍：修正 commit `10da13a..a502278`（11 個：5 個 test、1 個 fix、5 個 docs），對照上面的 I1、I2、M1–M6 與「修正記錄」。行號以 head `a502278` 為準。

### 結論

**需要再修一輪，只有文件。** 程式碼與測試的修正都正確：I1、I2 真的修好，新測試抓得到原本存活的突變（我在修前、修後兩份 scratch 複本上自己重跑過），`__wrapped__` 候選沒有引入假「存在」或迴圈，M5 的新測試不會在 beta／rc tag、排序或不同 tag 集合下誤紅，也不會 skip。但使用者決定的 readme 變更紀錄有一句事實錯誤（新 Important NI1）：它說 SAPI5 在 NVDA 2024.1–2025.2 上「以前就不能用」，而最後一個發佈版 6.2 在這些版本上是能用的。

### 逐項確認

| 項目 | 結果 | 依據 |
| --- | --- | --- |
| I1 | **已修** | `tests/test_runtime_host_names.py:179-183`。先斷言 `_inherited`、`_inheritedFlag` 不在 `_class_stored_names` 裡，所以只能靠 `hasattr` 的繼承部分通過。突變 H1（`name in vars(host_class)`）：修前（`10da13a` 的測試）**存活**（81 passed）→ 修後**殺**（只有這個新測試失敗）。 |
| I2 | **已修** | `tests/test_nvda_release_names.py:168-212`。四個版本的完整限定集合和 spec §10 逐一相同（module 9／3 個；class 13／12 個，含 overrides `_onEndStream`、`_speakThread`、`_initWasapiAudio`）。N1（`class_names=()`）、N2（丟掉 `NVDA_OVERRIDES`）：修前都**存活** → 修後都**殺**（各 4 個 failed）。我另外加了 N2b（丟掉 `NVDA_PRIVATES`），也被殺。只釘 SAPI5 就夠，因為 eSpeak 和 OneCore 每一版都齊全，N1 在它們身上沒有可觀察的差別；它們 class 視圖整個壞掉的情況，會被 FIRST_COMPLETE 測試抓到。 |
| M1 | **已修**（見新 Minor NM1） | `hostNames.py:48` 加了 `__wrapped__` 候選，`:16-18` 的 docstring、`nvda_releases.py:8-16` 和 spec §4.2 都寫出兩個例外。W1（拿掉候選）會被 `test_stores_under_a_wrapping_decorator_are_present` 殺。 |
| M2 | **已修** | N6 修後**殺**（`test_static_and_live_views_agree_on_synthetic_source`）。 |
| M3 | **已修** | `nvda_releases.py:5-6`、`:92-93` 的成因寫對了。 |
| M4 | **已修** | G7（`from synthDrivers.sapi5 import SapiSink`）：修前**存活** → 修後**殺**。G8（`import *`）也被殺。G9（`from synthDrivers.espeak import SynthDriver …`）**沒有**被這個守門擋，符合「只容許 `SynthDriver`」的設計，所以沒有假陽性（這個突變在 `test_nvda_ready` 因為 harness 失敗，和守門無關）。見下方「未涵蓋」。 |
| M5 | **已修** | R1（`RELEASES` 拿掉 `2026.3beta6`）：修前**存活**（78 passed）→ 修後**殺**。邊界行為見下方 M5 探測。 |
| M6 | 不修，**理由成立** | 每次 discovery 跑一次，十幾 ms；已列進 Windows 手動項目 4。 |
| 使用者決定（readme） | **段落正確，事實有誤** | 6 個檔都放在 Notes／Примечания／Примітки／注意，以及 Next update／Следующее обновление／Наступне оновлення／下一版更新的最後一條；`addon/doc/en/` 和 `.html` 沒有變動。Notes 那一點正確；變更紀錄那一條有問題，見 NI1。 |

### 新發現

#### Important

**NI1. 變更紀錄說 SAPI5 在 NVDA 2024.1–2025.2「以前就不能用」，但對發佈版來說不是這樣**（`readme.md:101`；`addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md:101`，commit `ddd9c55`）

英文原句是「On NVDA 2024.1 to 2025.2, SAPI5 voices did not work in WorldVoice and errors appeared in the NVDA log」，五個翻譯的意思相同。這句話只對 6.2 之後、還沒發佈的開發版成立：會壞是因為 `2b3b159`（2026-09-29，`Add correlated SAPI5 WASAPI segment drain wrapper`），而它不在 tag `6.2` 裡（`git merge-base --is-ancestor 2b3b159 6.2` → 否）。最後一個發佈版 6.2（2026-07-31）的 `driver/SAPI5/__init__.py` 只有 8 行，`synth_driver_class = SynthDriver`，就是 NVDA 自己的 `synthDrivers.sapi5.SynthDriver`；`engineOn` 直接建構它（`git show 6.2:addon/synthDrivers/WorldVoice/driver/__init__.py:174-177`），沒有讀任何 2025.3 才有的名稱。6.2 的最低版本也是 2024.1。「下一版更新」是相對於 6.2 寫的，所以對使用者來說，這次是**移除** NVDA 2024.1–2025.2 上的 SAPI5，不是修好一個錯誤。（6.2 在這些 NVDA 上實際能說話，是從程式碼推論的，沒有在 Windows 驗證。）

失敗情境：使用者在 NVDA 2025.1 上用 WorldVoice 6.2 的 SAPI5 語音，更新後 SAPI5 語音不見了。變更紀錄卻告訴他「以前在你的版本上本來就不能用、還會出錯」，他沒辦法從文件知道這是一項支援被拿掉、要升級 NVDA 才能恢復。另外，spec §9 Q1 的選項 (a) 寫「no behaviour change」，這是相對於 `master` 說的；相對於 6.2，(a) 就是移除。使用者 2026-10-28 的決定可能是在「今天本來就壞了」的前提下做的。

建議修法：只改這 6 行，例如英文改成「**SAPI5 now needs NVDA 2025.3 or later:** WorldVoice's SAPI5 engine is now built on the speech queue NVDA 2025.3 introduced. On NVDA 2024.1 to 2025.2, WorldVoice no longer offers SAPI5 voices and writes one warning to the NVDA log instead. eSpeak, OneCore and the other engines are not affected.」，五個翻譯照著改（拿掉「以前不能用／出現錯誤」那一句，改成「不再提供」）。Notes 那一點不用改。協調者 merge 前向使用者列預設時，要寫清楚：**相對於 6.2，NVDA 2024.1–2025.2 的使用者會失去 SAPI5**（spec §9 Q1 的 (d) 仍然是唯一保留它的選項）。

#### Minor

**NM1. `__wrapped__` 只往下看一層，而且只看 class 屬性本身；docstring 讓人以為「有留 `__wrapped__` 就看得到」**（`hostNames.py:16-18`、`:48`；`tests/nvda_releases.py:12-13`；spec §4.2 `:137`）

用 `scratchpad/p51fixreview/wrapped_probe.py` 在 CPython 3.11.18、3.13.18、3.14.4 下跑，三個版本結果相同：單層 `@functools.wraps` 和 `@functools.lru_cache` 現在看得到。但兩層 `@logged @logged`、`@staticmethod @logged`、`@property @logged` 裡的 `self.x =` 仍然是 `[]`。原因是外層包裝的 `__wrapped__` 指向內層包裝，而 `staticmethod.__wrapped__`、`fget` 指向的是包裝函式本身。這三種情況裡，原函式都有被某一層保留成 `__wrapped__`，所以兩份 docstring 寫的「a function a decorator keeps as __wrapped__」和「without keeping it as __wrapped__」都不精確。這些都是 live 比較嚴的情況（會假略過），而靜態視圖照樣算存在，所以多版本測試抓不到。今天沒有影響：2024.1、2025.3、2026.3beta6 的 `synthDriverHandler`、`driverHandler`、`baseObject`、`autoSettings`、`garbageHandler` 與三個 synth 檔，除了 `@property`／`@staticmethod`／`@classmethod`／`@abstractmethod`／`.setter`，沒有別的 decorator，也沒有 `__wrapped__`、`wraps(`、`lru_cache`、`cached_property`。建議二選一：(a) docstring 改成「只看 class 屬性本身那一層 `__wrapped__`」；或 (b) 對每個候選沿 `__wrapped__` 鏈走，用 seen set 防迴圈。(b) 不會有遞迴問題：`selfloop.__wrapped__ = selfloop` 在現在的實作下只是同一段 code 產出兩次。

**NM2.（可選）zh_CN 的「或更新版本」**（`addon/doc/zh_CN/readme.md:88`、`:101`）：大陸軟體文件慣用「或更高版本」；繁中的「或更新版本」沒問題。修 NI1 時可以順手改。

#### 確認沒有新問題

- **`__wrapped__` 不會造成假「存在」**：會多認得的只有「class dict 裡某個物件帶的函式 code」，這和原本的語意一樣（例如 `b = functools.lru_cache(_helper)` 現在會讀模組層 `_helper` 的 store，而修前 `b = _helper` 本來就會讀）。帶萬用 `__getattr__` 的物件，修前就會經由 `__func__`／`fget` 被讀到（`wrapped_probe_pre.py` 用 `10da13a` 的 `hostNames.py` 跑，`WithProxy` 一樣是 `['_fromProxy']`），不是這次新增的。只做一次 `getattr`，不會遞迴也不會迴圈。`unittest.mock` 的 `Mock`／`MagicMock` 對 `__wrapped__` 回 `None`（實測），所以測試 stub 不會因此多出名稱。
- **static ⊆ live 方向仍成立**：`__wrapped__` 只會讓 live 的「存在」集合變大，所以 live 缺的名稱仍是 static 缺的名稱的子集，只差 docstring 寫的兩個例外，和 docstring 一致。
- **M5 不會誤紅、不會 skip**：`scratchpad/p51fixreview/m5probe.py` 讓測試對著假 repo 跑，結果如下。
  - 同一個 feature release 有 beta、rc、正式版、點版本（`2026.3beta6`／`rc1`／`2026.3`／`2026.3.1`）→ PASS。
  - `2026.10beta1` 和 `2026.9` 並存 → FAIL，訊息是 2026.10，證明是數值排序，不是字串排序。
  - 有 `2026.4beta1` 或 `2027.1rc1` → FAIL，附「add its newest tag」提示。
  - `0.6p3`、`2027.1-dev`、`2027.1alpha1`、`2027.1.next` 這類不符合格式的 tag 會被忽略 → PASS。
  - 只有較舊的 tag → PASS（缺的 tag 由 `release_source` 的 fetch 提示處理）。
  - 沒有 tag、不是 git 目錄、目錄不存在 → `pytest.fail` 附 fetch 提示。
  - 實際的 `ref/nvda` 有 367 個 `release-*` tag，除了 6 個 0.x 舊 tag，全部符合格式；最大的是 (2026, 3)，在 `RELEASES` 裡。
- **M4 守門沒有假陽性**：三個 wrapper 在 import 時期的 `from synthDrivers.<mod> import` 只有 `SynthDriver`。OneCore 用相對 import `.driver`，被 `level == 0` 排除；vendored 內層本來就不在掃描範圍。**未涵蓋（既有的缺口，不是這次引入的）**：在 import 時期讀 `BaseSynthDriver.X`（NVDA class 的屬性）、`from synthDrivers import sapi5 as 別名` 之後讀 `別名.X`、`synthDrivers.sapi5.X` 這種長鏈。今天都沒有，這次不用修。

### 驗證指令與結果

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 修前／修後突變 | `scratchpad/p51fixreview/mutrun.py`：把 worktree 複製到 scratch（不含 `.git`、`__pycache__`，`ref` 用 symlink）；`pre` 把 5 個修正檔換回 `git show 10da13a:<path>`。每個突變單獨套用，先清 `__pycache__`，`PYTHONDONTWRITEBYTECODE=1 timeout 300 python3 -m pytest -p no:cacheprovider -q` 跑 4 個目標測試檔，輸出在 `scratchpad/p51fixreview/{pre,post}.log`，複本已刪除 | pre：NONE 81 passed；H1、N1、N2、G7 **存活**，R1 **存活**（78 passed）。post：NONE 88 passed；H1、N1、N2、N2b、N6、W1、G7、G8、R1 全部**殺**；G9 沒有被守門擋（符合設計） |
| M5 邊界 | `scratchpad/p51fixreview/m5probe.py`（假 git repo，替換 `test_nvda_release_names.NVDA`） | 結果見上一節 |
| `__wrapped__` 行為 | `wrapped_probe.py` 在 3.11.18、3.13.18、3.14.4 下跑；`wrapped_probe_pre.py` 用修前的 `hostNames.py` 跑 | 結果見 NM1 與上一節 |
| NVDA 的 decorator | `git -C ref/nvda show <tag>:<file> \| grep -nE '^\s*@…\|__wrapped__\|wraps\(\|lru_cache\|cached_property'`（排除 property、staticmethod、classmethod、abstractmethod、setter），在 2024.1、2025.3、2026.3beta6 對 8 個檔案跑 | 沒有輸出 |
| 6.2 的 SAPI5 | `git show 6.2:addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py`；`git merge-base --is-ancestor 2b3b159 6.2`；`git log -S'_threadCond' -- …/SAPI5/__init__.py` | 6.2 是 8 行的薄包裝；破壞相容性的 commit 是 6.2 之後才有（NI1） |
| 完整套件（`a502278`，序列，記憶體看門狗 3 GB） | `cd /workspace/WorldVoice-phase51 \|\| exit 1; ( while sleep 5; do … pkill -f pytest … done ) & W=$!; PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider tests; kill $W` | **3435 passed，0 skipped，102.05 s**（和修正記錄一致） |
| prek | `prek run --all-files` | 8 個 hook 全部 Passed |
| 空白 | `git diff --check master` | 乾淨（rc 0） |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' …/driver/sonic/ …/script_data.py …/unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 兩個都沒有輸出 |
| 建置輸出 | `git diff --stat master -- addon/doc/en '*.html'` | 沒有輸出 |
| 翻譯用語 | 用 grep 對照各檔原有的用語：ru「речевой движок」「журнал」；uk「мовленнєвий рушій」「журнал」；zh_CN「语音引擎」「日志」；zh_TW／zh_HK「語音引擎」「記錄檔」（NVDA 的 log；WorldVoice 自己的功能叫「日誌記錄」，兩者有區分）；zh_HK 和 zh_TW 逐字相同，和 master 上的做法一致 | 用語一致、句子自然；只有 NI1 的事實錯誤和 NM2 |

### 給協調者

- 下一輪只需要改 NI1（6 行變更紀錄，NM2 可以順手改）；NM1 是便宜的 Minor，可以一起修（改 docstring 或沿鏈走）。改完以後是否還要再做一次修正 review，依 §3.4 由協調者決定。這一輪的新發現只有文件。
- 使用者還沒確認的預設要改寫第 1 點：**相對於發佈版 6.2，NVDA 2024.1–2025.2 的使用者會失去 SAPI5 語音**（6.2 用 NVDA 自己的 SAPI5 driver；目前的分段 drain wrapper 需要 NVDA 2025.3 的語音佇列）。

## 修正記錄（第二輪）

修正者：Opus 5.5（DEVELOPMENT_WORKFLOW.md §3.4、§8）。範圍 `7a881ba..67095ae`，4 個 commit，加上本記錄的 commit。依據：修正 review 的 NI1、NM1、NM2，以及**使用者決定（2026-10-28）**：在缺少 SAPI5 wrapper 所需 NVDA 名稱的版本（< 2025.3），SAPI5 改用 NVDA 自己的 `synthDrivers.sapi5.SynthDriver` 當整個 core，和 6.2 一樣：不做分段 drain（completion 落在 LEGACY_DONE）、直接 `speak(commands)`、不經過 WorldVoice 的 SAPI5 wrapper 程式碼。這是整個 class 的選擇，不是 wrapper 裡逐個入口的 `if`。≥ 2025.3 行為不變。

完整套件（序列，記憶體看門狗 3 GB）**3454 passed，0 skipped**（3435＋19：`test_sapi5_old_nvda.py` 16、`test_nvda_ready.py` 淨增 2、NM1 1）；`prek run --all-files` 8 個 hook 全 Passed；`git diff --check master` 乾淨；受保護路徑（內層驅動、`driver/sonic/`、兩個 Unicode 資料檔）、`addon/doc/en`、`*.html` 與 Neural 都沒有輸出。

| 項目 | commit | 修法 | red／green 證據 |
| --- | --- | --- | --- |
| 使用者決定（SAPI5 在 NVDA < 2025.3） | `543052f` | SAPI5 `Voice.ready()` 一律回 `True`，用同一份檢查（`missing_host_names` ＋ `_Sapi5Port` 三個清單）選整個 core：名稱齊全 → `synthDriverClass = SynthDriver`（wrapper）、`drainProfile = DrainProfile(wasapi_dependent=True)`；有缺 → `synthDriverClass = sapi5.SynthDriver`（NVDA 的）、`drainProfile = None`，並寫一行 `info`。每次呼叫兩個分支都會設定，所以之後在齊全的 NVDA 上再檢查會換回 wrapper。eSpeak、OneCore 仍用 `host_names_ready` 略過。`_nvdaBase` 保留，只讓模組在 2024.x 能 import | 修前：`test_nvda_ready.py` 4 failed、`test_sapi5_old_nvda.py` 12 failed（2024.1–2025.2 兩個測試都紅；2025.3 以後 4 個綠，因為行為沒變）→ 修後全綠 |
| NI1、NM2 | `041905a` | 根目錄 `readme.md` 與 `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` 的 Notes 與「下一版更新」兩行改寫：NVDA 2024.1–2025.2 上 SAPI5 使用 NVDA 內建的 SAPI5 驅動程式，和 6.2 一樣，SAPI5 語音的表現和 6.2 相同；WorldVoice 自己的 SAPI5 驅動程式（等每一段 SAPI5 語音播放完畢才開始下一段——另一個語音或停頓）只在 2025.3 以後使用；舊版會在記錄檔寫一行說明。不再說發佈版「不能用」。zh_CN 改用「或更高版本」。各語言沿用原有用語（ru「речевой движок」「журнал」、uk「мовленнєвий рушій」「журнал」、zh_CN「语音引擎」「日志」、zh_TW／zh_HK「語音引擎」「記錄檔」），zh_HK 與 zh_TW 逐字相同 | 文件 |
| NM1 | `013f24c` | 選 (a)：`hostNames.py` 模組 docstring 與 `_function_code` 註解、`tests/nvda_releases.py` 的例外說明、spec §4.2 改成「只讀 class 屬性往下一層：函式本身、staticmethod／classmethod／property 底下的函式、屬性自己的 `__wrapped__`；不沿鏈走」，並列出兩層 wrapper、`staticmethod`／`property` 包 wrapper 的情況。新增 `test_wrapped_is_read_one_level_below_the_class_attribute_only` 釘住這個限制 | 文件＋釘住現有行為的測試（綠） |
| spec 更正 | `67095ae` | §1.1、§2、§4.1、§4.3、§6、§7、§9 Q1 原本「略過」的文字加刪除線，標 *Decided by the user (2026-10-28)*；新增 §4.4（選擇方式、bridge 為何把 NVDA 的 driver 當 LEGACY_DONE 純 core、log 行、release 測試） | 文件 |

### class 怎麼選

選擇發生在 `Voice.ready()`（discovery 在 import 之後、任何 `createCore`／`supportedSettings`／completion policy 之前呼叫）。下游本來就支援純 core，不用改：`createCore()` 建 `synthDriverClass()`；`supportedSettings()` 讀它的設定；`CompletionPolicy.contractFor` 看到 `drainProfile is None` 直接回 `CompletionContract()`（LEGACY_DONE），不問 core，也不寫 fallback 警告；`VoiceClassAdapter` 因為 NVDA 的 driver 沒有 `supportsCancellationToken`，呼叫 `speak(commands)`；`voices()`、`voiceInfoToMetadata()`、`applyEngineSettings()` 都是基底 `Voice` 的。

### 在 NVDA 2024.1–2025.2 上用 bridge 驗證純 core

`tests/test_sapi5_old_nvda.py` 用 `git -C ref/nvda show release-<v>:source/synthDrivers/sapi5.py`（唯讀）載入每個 release 的 `sapi5.py`，搭配 SAPI5 harness 的 NVDA stub，再補上 release 原始碼需要的 stub（`comtypes.IUnknown`、`objidl`、`ctypes.windll.ole32`、`nvwave.outputDeviceNameToID`、`config.conf.getConfigValidation`、兩種大小寫的假 `SAPI.SpVoice`），然後載入真正的 `driver/__init__.py`（基底 `Voice`）與 SAPI5 wrapper：

- 2024.1、2024.2、2024.3、2024.4、2025.1、2025.2：`ready()` 是 `True`；`synthDriverClass` 就是該 release 的 `sapi5.SynthDriver`；`drainProfile is None`；只有一行 `info`，缺少的名稱和靜態視圖（`release_missing`）完全相同（22／22／22／22／16／15 個）。接著透過 `VoiceClassAdapter`：`open()` 建出 NVDA 的 driver（`type(core) is base.SynthDriver`、`notificationSource is core`）；`contractFor` 回 `support is None`，`select` 回 `CompletionContract()`／LEGACY_DONE，沒有警告；`supports_cancellation_token is False`；settings 等於該 release 的 `supportedSettings`；`listVoices()` 回 `SAPI5:v1`；`apply()` 設定 voice、rate、volume；`speak(["hello", IndexCommand(3)], token)` 讓假 SpVoice 收到一次 XML（含 hello 與 `<Bookmark Mark="3" />`；若傳了 token，NVDA 的 `speak(speechSequence)` 會 TypeError）；`cancel()` 送出 purge（`Speak(None, …)`）；`close()` 之後 `core.tts is None`。
- 2025.3、2026.1、2026.2、2026.3beta6：靜態視圖沒有缺名稱，`ready()` 選 wrapper（是該 release `SynthDriver` 的子類）與 `DrainProfile(wasapi_dependent=True)`，沒有 log。
- 6.2 依賴的也只是這些：6.2 的 SAPI5 wrapper 只有 `synth_driver_class = SynthDriver`。

### log 行

`info` 等級（SAPI5 能用、使用者不用處理；NVDA 預設記錄 info；warning 留給真的略過）：

```
SAPI5 engine uses NVDA's own SAPI5 driver, without WorldVoice's segment drain: NVDA 2025.1.0 lacks 16 of the names WorldVoice's SAPI5 driver needs: synthDrivers.sapi5.ISpVoice, …
```

### 突變驗證

`scratchpad/p51r2/mutrun.py`：把 worktree 複製到 scratch（不含 `.git`、`__pycache__`、`.superpowers`，`ref` 用 symlink），每個突變單獨套用到 `driver/SAPI5/__init__.py`，`PYTHONDONTWRITEBYTECODE=1 timeout 300 python3 -m pytest -p no:cacheprovider -q` 跑 `test_sapi5_old_nvda.py`、`test_nvda_ready.py`、`test_native_strategy_guards.py`、`test_runtime_completion_policies.py`，輸出寫到 `scratchpad/p51r2/<突變>.log`，複本已刪除。NONE：97 passed。**11 個突變全部被殺**：

| 突變 | 結果 |
| --- | --- |
| M1 缺名稱時仍用 wrapper class | 16 failed |
| M2 缺名稱時保留 drain profile | 16 failed |
| M3 齊全時不重設（只剩缺名稱分支） | 1 failed |
| M4 缺名稱時回 `False`（舊的略過） | 15 failed |
| M5 `log.info` → `log.warning` | 9 failed |
| M6 條件反轉 | 22 failed |
| M7 class 名稱拿掉 overrides | 7 failed |
| M8 數量寫成 0 | 9 failed |
| M9 `_nvdaBase` 拿掉 `object` 預設 | 9 failed |
| M10 不寫 log | 9 failed |
| M11 不檢查模組名稱 | 9 failed |

### `Ruling:`（已寫入進度帳本）

- SAPI5 `Voice.ready()` 在 class 上設定 `synthDriverClass` 與 `drainProfile`，每次兩個分支都設定：discovery 註冊的是模組的 `Voice` class，且在 `createCore`、`supportedSettings`、completion policy 讀取之前呼叫 `ready()`；`ready()` 不能換成另一個 class。錯了的代價：在 `ready()` 之前讀的人看到 wrapper，和這輪之前相同。
- NVDA driver 路徑同時把 `drainProfile` 設成 `None`，不只換 class：保留 profile 的話 policy 仍會選 LEGACY_DONE（core 不是自訂的外層 SynthDriver），但每次 open 多寫一行 warning；`None` 就是所有沒有 profile 的 plugin 走的純 core 路徑。錯了的代價：只有 log 不同。
- log 用 `info`（理由見上）。錯了的代價：在只看 warning 的記錄裡比較不顯眼。
- SAPI5 `ready()` 直接用 `missing_host_names`，不新增 runtime helper；清單仍在 `_Sapi5Port`，「存在」的定義仍在 `hostNames.py`，檢查仍是單一來源。
- NM1 選 (a)，不沿鏈走：經過帶萬用 `__getattr__` 的物件（例如 Mock 的 `fget` 子物件）沿 `__wrapped__`／`fget` 走需要深度上限，而 NVDA 沒有任何 release 用這種 decorator。錯了的代價：將來 NVDA 某個 method 套兩層 wrapper 並存了清單上的名稱，會被誤判缺少（SAPI5 改用 NVDA 的 driver、eSpeak／OneCore 被略過），而靜態 release 測試抓不到。
- readme 用效果描述 drain（「等每一段 SAPI5 語音播放完畢才開始下一段」），不用「segment drain」這個詞；log 行保留這個詞。

### 給協調者

- 使用者還沒確認的預設要改寫第 1 點：相對於 6.2，NVDA 2024.1–2025.2 的使用者**保留** SAPI5 語音（NVDA 自己的 driver，和 6.2 相同），只是沒有 WorldVoice 的分段 drain；log 等級選 `info`。
- 本輪沒有新的 Critical／Important，只有使用者決定的實作與文件；是否再做修正 review，依 §3.4 由協調者決定（這輪改了 SAPI5 的程式碼路徑）。

### 未在 Linux 驗證的項目（Windows／NVDA 手動）

Linux 上不能跑 NVDA 或 SAPI5，以下都沒有驗證：

1. NVDA 2024.x、2025.1、2025.2（有的話）：WorldVoice 列出 SAPI5 語音、能說話、按 Ctrl 能停下（cancel），切換到其他引擎的語音正常；NVDA 記錄檔只有一行 `SAPI5 engine uses NVDA's own SAPI5 driver …`（info），沒有 traceback；eSpeak、OneCore 正常。
2. NVDA 2025.3、2026.x：SAPI5 用 WorldVoice 的 wrapper（記錄檔沒有上面那一行，也沒有任何「Skipping … engine candidate」）；三個引擎都能列出語音並說話。
3. 原本的項目 4（`ready check … voice.ready` 計時）不變。

## 修正 review 第二輪（Opus xHigh）

日期：2026-10-28。審閱者：Opus 5.5（effort xHigh，DEVELOPMENT_WORKFLOW.md §3.4 修正 review；唯讀，只新增本段）。範圍：`7a881ba..fa25b97`，5 個 commit（1 個 fix、4 個 docs）。對照的是上一段修正 review 的 NI1、NM1、NM2、使用者決定（2026-10-28），以及「修正記錄（第二輪）」。行號以 head `fa25b97` 為準。

### 結論

**可以 merge。** 沒有新的 Critical 或 Important。

- 使用者決定的實作正確：NVDA 2024.1–2025.2 上，SAPI5 整個 core 換成 NVDA 自己的 `synthDrivers.sapi5.SynthDriver`，`drainProfile` 是 `None`，走 LEGACY_DONE，呼叫 `speak(commands)`。2025.3 以後不變。
- 新測試抓得到它聲稱要抓的錯誤：修前 16 個 failed，fixer 的 4 個突變我重跑、我自己另加 12 個突變，全部被殺。
- readme 對照 6.2 是真實的。

只有兩個新的 Minor，都是文字（ru 用詞，以及 docstring 少列 classmethod），修起來便宜，可以在 merge 前順手修，不修也可以。

### 逐項確認

| 項目 | 結果 | 依據 |
| --- | --- | --- |
| NI1 | **已修** | 6 個 readme 的 Notes（`:88`）與「下一版更新」（`:101`）都不再說發佈版「不能用、出錯」。改成：2024.1–2025.2 用 NVDA 內建的 SAPI5 驅動程式，和 6.2 相同；WorldVoice 自己的驅動程式（等每一段播放完畢）只在 2025.3 以後使用；舊版會寫一行 log。這和程式碼一致：舊版走 NVDA 的 driver，寫一行 `info`。 |
| NM1 | **已修**（見新 Minor NM4） | `hostNames.py:17-22`、`:48-49`，`tests/nvda_releases.py:12-15`，spec §4.2 `:137`，都改成「只往下一層、不沿鏈走」。`test_wrapped_is_read_one_level_below_the_class_attribute_only`（`tests/test_runtime_host_names.py:169`）釘住兩層 wrapper，以及 `staticmethod`／`property` 包 wrapper 的情況。 |
| NM2 | **已修** | zh_CN `:88`、`:101` 改用「或更高版本」；zh_TW／zh_HK 保留「或更新版本」；zh_HK 與 zh_TW 逐字相同（`cmp` 相同）。 |
| 使用者決定（SAPI5 在 < 2025.3） | **已實作，正確** | `driver/SAPI5/__init__.py:688-719`：整個 class 二選一，不是逐個入口加分支；每次呼叫兩個屬性都設定；eSpeak、OneCore 仍用 `host_names_ready` 略過。下方第 1、2 節有詳細說明。 |
| spec 更正（§4.4 等） | **正確** | §4.4 的表格、log 行、下游說明都和程式碼一致。「No wrapper code runs on this path」成立：舊版只 import 模組，`_nvdaBase` 讓 class 定義能成立，wrapper 的 `SynthDriver` 從頭到尾沒有被建構。 |

### 1. 在 `ready()` 裡改 class 屬性：設計判斷

**誰呼叫 `ready()`：** 只有一個呼叫點，`engineRegistry/discovery.py:218-219`。呼叫鏈是 `engineRegistry/__init__.py:40-42` 的 `ready_engine_classes`，而它只在 `WorldVoice/__init__.py:226` 建構 `VoiceManager` 時被呼叫一次。`ready()` 回 True 之後，class 才會放進回傳的 dict（`discovery.py:220-222`）。

**誰讀 `synthDriverClass`／`drainProfile`：** 下面這些讀的都是 `VoiceManager` 拿到的 class，也就是 discovery 回傳、已經跑過 `ready()` 的 class：

- `Voice.supportedSettings`、`createCore`（`driver/__init__.py:73-88`）
- `CompletionPolicy.audioMode`、`drainSupport`、`contractFor`（`bridge/completionPolicies.py:60`、`:80-82`、`:120`）
- `VoiceClassAdapter.capabilities`（`bridge/engineAdapter.py:112-117`）

語音引擎面板（`globalPlugins/WorldVoice/panels/engine.py:11`、`:38-48`）只讀 manifest 產生的 `ENGINE_SPECS`，不碰 Voice class。add-on 裡沒有別的地方 import `driver.SAPI5`。所以今天沒有人會在 `ready()` 之前讀到這兩個屬性。discovery 本身也有改 Voice class 的先例：`discovery.py:199-200` 的 `synth_driver_class` 對應。

**冪等：** 結果只取決於 NVDA 的 `synthDrivers.sapi5` 模組與 class，同一個 process 裡不會變。

- 我的探測測試（`test_ready_twice_same_answer_and_one_line_each`，10 個 release）確認：連續呼叫兩次，得到的 `(ready, synthDriverClass, drainProfile)` 完全相同。
- 基底 `driver.Voice` 的兩個屬性仍是 `None`；wrapper 的 `SynthDriver` 沒有被設定。
- 舊版每次呼叫寫一行 `info`，也就是每次載入 WorldVoice（例如重新切換到 WorldVoice）寫一行。

**執行緒：** `ready()` 和 `_bind` 裡的 `completion_for` 都在建構 WorldVoice 的同一個執行緒上，依序執行。兩次 setattr 不是原子操作，但第一次呼叫時還沒有人拿到這個 class，之後的呼叫寫入的值都相同，所以沒有中間狀態可以被看到。

**測試之間的洩漏：** 會載入 SAPI5 wrapper 的測試都用 `load_source` 搭配 monkeypatch，每個測試拿到新的模組物件（`tests/sapi5_drain_harness.py:324-327`；`tests/engine_contract_harness.py:117-119` 的 `SAPI5Adapter.open` 每次呼叫 `load_sapi5`；`tests/test_sapi5_old_nvda.py:154-155`；`tests/test_nvda_ready.py:199-203`），class 狀態不會跨測試。完整套件全綠也印證了這點。

**改在 `createCore()` 決定會不會比較安全：** 不會。`createCore` 只管 core。`supportedSettings` 和 `drainProfile` 也要跟著同一個選擇，所以得改成每次呼叫都重新判斷的 classmethod／property，等於要改 `driver.Voice` 這個公開的 plugin API。現在的做法只有一個地方決定，兩個屬性一定成對。漏呼叫 `ready()` 的代價（看到 wrapper，和本輪之前相同）已經寫在 `Ruling:`。

**判斷：合理，不用改。** 我找不到會實際失敗的情境。

### 2. NVDA 自己的 driver 透過今天的 bridge（2024.1–2025.2）

我用 `git -C ref/nvda show release-2024.1:source/synthDrivers/sapi5.py` 和 `release-2025.2:…` 逐段讀過（唯讀，沒有改 `ref/`），另外用 grep 比對了 2024.2–2025.1。

- **建構與關閉：** `__init__(self, _defaultVoiceToken=None)` 可以無參數建構，對應 `createCore` 的 `cls.synthDriverClass()`。`terminate()` 把 `tts` 設成 `None`（2025.2 另外關掉 player），對應 `destroyCore`。
- **設定：** `supportedSettings` 在 2024.1–2024.4 是 voice／rate／pitch／volume；2025.1 加 rateBoost；2025.2 再加 useWasapi。`APPLY_ORDER` 只套用其中的 rateBoost／rate／pitch／volume／inflection。useWasapi 不會被套用，因為 WorldVoice 不呼叫 `loadSettings`，所以 `_useWasapi` 維持 driver 預設的 True，和 6.2 一樣。
- **說話：** `speak(self, speechSequence)` 沒有 token 參數，NVDA 的 class 也沒有 `supportsCancellationToken`，所以 `_speakPlain` 呼叫的是 `speak(commands)`（`engineAdapter.py:33-37`）。`cancel()`、`pause(switch)` 都有。
- **語音清單：** `availableVoices` 由 NVDA 的 AutoPropertyObject 提供，接到 `_getAvailableVoices`，供基底 `Voice.voices` 使用。
- **SAPI5 `Voice` 的方法：** 除了 `ready()` 沒有自己的方法。`applyEngineSettings`、`variants`、`voiceInfoToMetadata`、`extraCapabilities` 都是基底的，用到的 driver 屬性只有上面這些，每個 release 都有。
- **index／done 通知：**
  - 2024.x：`SapiSink.Bookmark`、`EndStream` 呼叫 `synthIndexReached.notify(synth=synth, index=…)` 和 `synthDoneSpeaking.notify(synth=synth)`，其中 `synth` 是 core 的 weakref。
  - 2025.x：`onIndexReached`、`EndStream` 的做法相同。
  - bridge 用 `id(source)` 比對（`nvdaEvents.py:223-233`），而 `source` 就是 `notificationSource`，也就是 core（`engineAdapter.py:73`）。LEGACY_DONE 沒有 correlation，handler 直接收到 INDEX、DONE。
  - 我另外寫了探測測試 `test_index_and_done_reach_the_bridge`（scratch，沒有 commit）。每個舊 release 都用該 release 自己的 `SapiSink` 送出 Bookmark（2024.x），或 StartStream＋onIndexReached（2025.x），再送 EndStream。真正的 `NvdaEventBridge` 綁定 `adapter.notificationSource` 與 LEGACY_DONE contract 後，handler 收到 `[INDEX 7, DONE]`，source id 正確，6/6 通過。
- **和 6.2 對照：** 6.2 的接法是 `git show 6.2:…/driver/SAPI5/__init__.py`（`synth_driver_class = SynthDriver`，即 NVDA 的）和 `6.2:…/driver/__init__.py`（`engineOn` 執行 `cls.synth_driver_class()`、`speak` 執行 `core.speak(text)`、`setCoreParameter` 套用 supportedSettings ∩ {rate, pitch, volume, inflection, rateBoost}）。今天在舊版上：建構方式相同、speak 呼叫相同、套用的設定集合相同。`core.voice = id` 只在 session 的 key 或 revision 改變時才設定（`runtime/session.py:144-160`），對應 6.2 的 `active()` 只在 voice 不同時才設。

### 3. 測試是否抓得到

**修前：** 把 `7a881ba` 的 `driver/SAPI5/__init__.py` 放進 scratch 複本，跑新的 `test_sapi5_old_nvda.py` 與 `test_nvda_ready.py`，結果 **16 failed**，和修正記錄一致：old_nvda 的兩個測試在 6 個舊版各 1 個、共 12 個，nvda_ready 4 個。

**突變：** `scratchpad/p51r2rev/mutrun.py` 把 worktree 複製到 scratch（不含 `.git`、`__pycache__`、`.superpowers`，`ref` 用 symlink）。每個突變單獨套用，執行 `PYTHONDONTWRITEBYTECODE=1 timeout 300 python3 -m pytest -p no:cacheprovider -q`，跑 5 個檔：`test_sapi5_old_nvda.py`、`test_nvda_ready.py`、`test_native_strategy_guards.py`、`test_runtime_completion_policies.py`、`test_nvda_release_names.py`（B1、B2 只跑 `test_sapi5_old_nvda.py`）。log 在 `scratchpad/p51r2rev/<突變>.log`，複本已刪除。NONE 是 140 passed。**16 個突變全部被殺：**

| 突變 | 結果 | 殺掉它的測試 |
| --- | --- | --- |
| M1（重跑）缺名稱時仍用 wrapper class | 16 failed | old_nvda 12＋nvda_ready 4 |
| M3（重跑）齊全時不重設 | 1 failed | `test_sapi5_choice_follows_each_ready_call` |
| M6（重跑）條件反轉 | 22 failed | — |
| M7（重跑）class 名稱拿掉 overrides | 7 failed | — |
| R1 只決定一次：第二次呼叫直接回 True（`_chosen` 快取） | 1 failed | `test_sapi5_choice_follows_each_ready_call` |
| R2 舊版分支把屬性設在 `BaseVoice`（錯的 class） | 16 failed | — |
| R3 齊全分支把屬性設在 `BaseVoice` | 3 failed | nvda_ready |
| R4 舊版分支改用 NVDA driver 的子類，帶 `supportsCancellationToken = True`（仍像 wrapper 一樣傳 token） | 16 failed | `synthDriverClass is …`、`type(core) is base.SynthDriver` 斷言；token 路徑本身由 B1 證實會 `TypeError` |
| R5 齊全時也寫 log | 16 failed | `records` 斷言（舊版多一行、2025.3 以後不再是空的）與 `UnreadVersion` |
| R6 齊全分支丟掉 drain profile | 6 failed | 2025.3 以後 4 個＋nvda_ready 2 個 |
| R7 齊全分支用 NVDA 的 class | 6 failed | — |
| R8 `class_names=()` | 7 failed | — |
| R9 舊版分支留下 `DrainProfile()`（非 WASAPI 的 profile） | 16 failed | — |
| R10 舊版分支只換 class、不動 `drainProfile` | 16 failed | — |
| B1 bridge 的 `_speakPlain` 一律傳 token | 6 failed | 6 個舊版都是 `TypeError: SynthDriver.speak() got an unexpected keyword argument 'cancellationToken'`，證實測試註解的說法 |
| B2 bridge 的 `apply` 不套用設定 | 6 failed | `assert (0, 100) == (4, 40)`，證實設定確實經由 NVDA 自己的 class 套用 |

`test_nvda_2025_3_and_later_choose_the_wrapper_silently` 的斷言值剛好等於 class 的預設值，單獨看會被「`ready()` 什麼都不做」騙過。但 R6、R7 證明齊全分支寫錯會被它抓到，M3、R1 證明「不重設」或「只決定一次」會被 `test_sapi5_choice_follows_each_ready_call` 抓到，所以組合起來沒有缺口。

### 4. readme

- **對照 6.2 是真實的：** 6.2 在每個 NVDA 版本上都用 NVDA 的 SAPI5 driver，分段 drain 是 6.2 之後才加的（`2b3b159`）。所以兩件事都成立：「2025.3 以後 SAPI5 會等待播放完畢」相對於 6.2 是新的；「2024.1–2025.2 繼續用 NVDA 內建的驅動程式，和 6.2 相同」。文件沒有說哪個發佈版壞掉。「SAPI5 語音的表現和 6.2 一樣」指的是 core 相同，這點從程式碼讀得出來，沒有在 Windows 驗證。「寫一行 log」：等級是 `info`，NVDA 預設的記錄等級是 info，看得到。
- **用語：** 各語言沿用原有用語：ru「речевой движок」「журнал」、uk「мовленнєвий рушій」「журнал」、zh_CN「语音引擎」「日志」「自带」、zh_TW／zh_HK「語音引擎」「記錄檔」「內建」。英文自然。zh 的句子可讀。ru 有一個用詞問題，見 NM3。
- **建置輸出：** `git diff --stat master -- addon/doc/en '*.html'` 沒有輸出。
- **NM1 docstring：** 我用 3.11.18、3.13.18、3.14.4 實測（`scratchpad/p51r2rev/cm_probe.py`）。單層 `@functools.wraps` 和普通 classmethod 看得到；`@classmethod` 包 wrapper 看不到，而 docstring 只列了 `staticmethod`／`property`，見 NM4。其他敘述都正確。

### 新發現

#### Minor

**NM3. ru 的「часть речи」是文法術語「詞類」**（`addon/doc/ru/readme.md:88`、`:101`）

「пока каждая часть речи SAPI5 прозвучит до конца, прежде чем начнётся следующая часть」裡的「часть речи」在俄文是固定的文法術語（part of speech，例如名詞、動詞），讀起來像「SAPI5 的每個詞類」。看上下文能懂，但很彆扭。uk 的「частина мовлення」不是文法術語（文法上的詞類是「частина мови」），沒有這個問題。

建議修法：ru 兩處都改成「каждый фрагмент речи SAPI5 … следующий фрагмент」，例如「…который ждёт, пока каждый фрагмент речи SAPI5 не прозвучит до конца, прежде чем начнётся следующий фрагмент (другой голос или пауза)…」。uk 可以維持原樣。

**NM4. 「不沿鏈走」的例外清單少了 `classmethod`**（`addon/synthDrivers/WorldVoice/runtime/hostNames.py:21`、`tests/nvda_releases.py:14`、spec §4.2 `:137`）

三處都寫「under staticmethod or property over a wrapping decorator」。`@classmethod @logged` 的 `__func__`、`__wrapped__` 都指向 wrapper，所以原函式裡的 store 一樣看不到：`cm_probe.py` 在三個 Python 版本都回報 `C._fromClassmethod` 缺少。目前沒有影響，因為 NVDA 沒有這樣的 decorator（上一輪已逐版確認）。

建議修法：三處改成「staticmethod, classmethod or property over a wrapping decorator」。要不要在 `test_wrapped_is_read_one_level_below_the_class_attribute_only` 加一個 classmethod 的情況，可以自行決定。

#### 確認沒有新問題

- `ready()` 的設計見第 1 節，舊版 core 透過 bridge 的路徑見第 2 節，沒有發現失敗情境。
- `_nvdaBase`、`_nvdaLabel` 只改了註解。`host_names_ready` 仍給 eSpeak、OneCore 使用，SAPI5 不再 import 它，沒有殘留未用的 import（prek 的 ruff 通過）。
- commit 都沒有 `Co-Authored-By`。commit message 格式符合 §8。

### 驗證指令與結果

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 修前紅 | scratch 複本放入 `git show 7a881ba:addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py`，跑 `test_sapi5_old_nvda.py test_nvda_ready.py` | 16 failed，15 passed（複本已刪除） |
| 突變 | `scratchpad/p51r2rev/mutrun.py`（說明見第 3 節） | NONE 140 passed；16 個突變全部被殺 |
| bridge 通知探測 | `scratchpad/p51r2rev/test_probe_r2rev.py` 複製到 scratch 複本的 `tests/`，執行 `PYTHONDONTWRITEBYTECODE=1 timeout 300 python3 -m pytest -p no:cacheprovider -q tests/test_probe_r2rev.py` | 16 passed：6 個舊版的 INDEX／DONE 都送到 bridge；10 個 release 呼叫兩次結果相同（複本已刪除） |
| NVDA release 原始碼 | `git -C ref/nvda show release-{2024.1,2025.2}:source/synthDrivers/sapi5.py`；2024.1–2025.2 對 `supportedSettings`、`onIndexReached`、`SapiSink(COMObject)` 執行 grep | 結果見第 2 節 |
| 6.2 接法 | `git show 6.2:addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py`、`git show 6.2:addon/synthDrivers/WorldVoice/driver/__init__.py`；`git show 6.2:…/driver/Espeak/__init__.py \| grep -c 'drain\|segment'` → 0 | 結果見第 2、4 節 |
| classmethod 探測 | `python3.11 -I`、`python3.13 -I`、`python3 -I` 執行 `scratchpad/p51r2rev/cm_probe.py` | 三版都是 `('__main__.C._fromClassmethod',)`（NM4） |
| 完整套件（`fa25b97`，序列，記憶體看門狗 3 GB） | `cd /workspace/WorldVoice-phase51 \|\| exit 1; ( while sleep 5; do m=$(awk '/MemAvailable/{print $2}' /proc/meminfo); [ "$m" -lt 3000000 ] && pkill -f pytest && break; done ) & W=$!; python3 -m pytest -p no:cacheprovider tests; kill $W` | **3454 passed，0 skipped，102.59 s**（和修正記錄一致） |
| prek | `prek run --all-files` | 8 個 hook 全部 Passed，工作樹沒有變動 |
| 空白 | `git diff --check master` | 乾淨（rc 0） |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' …/driver/sonic/ …/script_data.py …/unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 兩個都沒有輸出 |
| 建置輸出 | `git diff --stat master -- addon/doc/en '*.html'` | 沒有輸出 |
| trailer | `git log --format='%b' 7a881ba..fa25b97 \| grep -ic co-authored` | 0 |

### 給協調者

- **可以 merge。** NM3、NM4 是便宜的 Minor，可以在 merge 前一起修，不需要再做修正 review（§3.4：只有 Minor 時不做）。
- 使用者還沒確認的預設照「修正記錄（第二輪）」的寫法列出：
  - 相對於 6.2，NVDA 2024.1–2025.2 的使用者**保留** SAPI5（NVDA 自己的 driver），只是沒有分段 drain。
  - log 等級是 `info`，每次載入 WorldVoice 寫一行。
- **觀察（不是本 phase 的範圍）：** eSpeak、OneCore、RHVoice、VE、Cerence 的分段 drain 也是 6.2 之後才有的（6.2 的 Espeak wrapper 沒有 drain／segment），但「下一版更新」只有 SAPI5 這一條提到「等待播放完畢」。讀者可能誤以為只有 SAPI5 會等。日後可以考慮補一條整體的變更紀錄。
- Windows／NVDA 手動項目和第二輪修正記錄列的相同，沒有新增。

## 修正記錄（第二輪修正 review 的 Minor）

- **NM3 已修**：`958f65c` 俄文 readme 兩處「часть речи」（文法術語「詞類」）改成「фрагмент речи … следующий фрагмент」。
- **NM4 已修**：`3fb7b80` `hostNames.py`、`tests/nvda_releases.py`、spec §4.2 的說明補上 classmethod。
- 只有 Minor，照 §3.4 不再做修正 review。
