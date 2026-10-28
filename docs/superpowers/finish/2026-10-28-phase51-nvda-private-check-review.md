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
