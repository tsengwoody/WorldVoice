# F4 Voice Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 Voice 設定只在下一段語音開始時套用，且同一 Voice、設定未變時不重複呼叫引擎 setter。

**Architecture:** 每個 Voice 保存待生效設定及執行期間的 revision；每個引擎保留一個 core，由 EngineSession 記錄上次成功套用的 core、Voice 與 revision。TaskManager 的 worker 取得設定快照並啟用 Session，然後播放。取消與暫停仍直接控制目前的 core。

**Tech Stack:** Python、NVDA SynthDriver API、現有 TaskManager worker、pytest。

**Spec:** `docs/superpowers/specs/2026-09-25-f4-voice-activation-design.md`

## Global Constraints

- 每個 Voice 建構及初始設定載入完成後，revision 為 0；revision 不寫入設定檔。
- 設定實際改變時才增加 revision；取消編輯還原值時也增加，不回退 revision。
- 語音段落開始時取得一次不可變快照；段落開始後的修改留到下一段。
- 同一 core、Voice、revision 不重設參數；Voice 切換或 core 重建時完整套用。
- 建構、設定載入和 UI 設定 setter 不寫 core；取消、暫停與恢復保持即時。
- 套用中途失敗時不得播放該段，並清除 Session 已套用記錄。
- 保留 F2／F3 已完成的資源清理與設定取消語意；不加入產品依賴。
- 目前工作區已有未提交的 F2／F3 修改與測試；執行時保留這些檔案，只提交本計畫新增的變更區塊。

## Review Focus

1. 套用到一半失敗：core 可能部分改變；Task 1 測試 Session 清除記錄並完整重試。
2. A → B → A：A 的 revision 未變；Task 1 測試切回 A 仍完整套用。
3. 重複指派相同值：Task 2 測試 revision 不增加，也不觸發下一段設定 setter。
4. 編輯後取消及播放中修改：Task 2 測試還原值與下一段快照邊界。
5. VE／Cerence 選回「default」變體：Task 3 測試恢復原生實例初次開啟時讀得的預設變體，而不是保留先前的自訂變體。

## File Map

- 新增 `addon/synthDrivers/WorldVoice/driver/engineSession.py`：不可變 VoiceSnapshot 與每引擎的 EngineSession；不依賴 NVDA，方便單獨驗證。
- 修改 `addon/synthDrivers/WorldVoice/driver/__init__.py`：Voice 待生效設定、revision、快照及 core／Session 生命週期；移除 setter 與建構時的 core 寫入。
- 修改 `addon/synthDrivers/WorldVoice/voiceManager.py`：將所屬 Session 配給快取 Voice；保留現有引擎開關與 F3 預覽／取消流程。
- 檢查 `addon/synthDrivers/WorldVoice/taskManager.py`：沿用 worker 已有的啟用點及事件、取消流程，不改寫其狀態機。
- 修改 `addon/synthDrivers/WorldVoice/driver/{VE,Cerence,OneCore}/__init__.py`：將引擎專用設定延後到 Session 啟用時。
- 新增 `tests/test_f4_engine_session.py`、`tests/test_f4_voice_state.py`、`tests/test_f4_engine_adapters.py`：使用 fake core／既有 stub harness 覆蓋上述行為。
- 沿用 `tests/test_worldvoice_request_manager.py`、`tests/test_voice_settings_transaction.py`、`tests/test_worldvoice_lifecycle.py` 的既有情境；若這些檔案仍未納入版本控制，執行時保留其現有內容。

---

### Task 1: 建立設定快照與 EngineSession

**Files:**
- Create: `addon/synthDrivers/WorldVoice/driver/engineSession.py`
- Create: `tests/test_f4_engine_session.py`

**Interfaces:**
- Consumes: 具有 `voice`、`supportedSettings` 及參數 setter 的既有 core 介面。
- Produces: `VoiceSnapshot`（下列固定欄位）；`EngineSession(core)`、`activate(snapshot, apply_engine)`、`replace_core(core)`、`invalidate()`。`activate` 回傳是否實際套用設定。

- [ ] **Step 1: 寫失敗的單元測試。** 測試檔以 `importlib.util.spec_from_file_location` 載入不依賴 NVDA 的新模組，建立記錄 setter 呼叫的 fake core，並涵蓋相同 stamp、版本改變、A → B → A、core 更換及部分失敗後重試。關鍵案例：

```python
def test_same_stamp_skips_setters_and_voice_switch_reapplies(session, snap):
    a = snap("a", 0)
    b = snap("b", 0)
    assert session.activate(a, lambda core, value: None) is True
    before = len(session.core.writes)
    assert session.activate(a, lambda core, value: None) is False
    assert len(session.core.writes) == before
    assert session.activate(b, lambda core, value: None) is True
    assert session.activate(a, lambda core, value: None) is True

def test_partial_failure_invalidates_stamp(session, snap):
    a = snap("a", 0)
    session.activate(a, lambda core, value: None)
    changed = snap("a", 1)
    with pytest.raises(RuntimeError, match="variant"):
        session.activate(changed, lambda core, value: (_ for _ in ()).throw(RuntimeError("variant")))
    assert session.activate(a, lambda core, value: None) is True
```

測試 fixture `snap` 建立 `VoiceSnapshot(voice_id=id, revision=rev, language="en", rate=50, pitch=50, volume=50, variant="default", inflection=50, rateBoost=False, waitfactor=0)`；fake core 的 `supportedSettings` 含 `rate`、`pitch`、`volume`，`__setattr__` 把這些欄位及 `voice` 寫入 `writes`。更換 core 的案例呼叫 `session.replace_core(new_core)`，再驗證同一快照仍被套用。

- [ ] **Step 2: 執行新測試，確認因模組不存在而失敗。**

Run: `python3 -m pytest tests/test_f4_engine_session.py -q -p no:cacheprovider`

Expected: FAIL，尚無 `engineSession.py`。

- [ ] **Step 3: 建立最小實作。** 將快照欄位明確列在 frozen dataclass；Session 只記錄成功套用的 stamp，按固定順序設定通用參數，並在任何 setter 失敗時 `invalidate()` 後重新拋出：

```python
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class VoiceSnapshot:
    voice_id: str
    revision: int
    language: str
    rate: int
    pitch: int
    volume: int
    variant: str
    inflection: int
    rateBoost: bool
    waitfactor: int

class EngineSession:
    def __init__(self, core):
        self.core = core
        self.invalidate()

    def invalidate(self):
        self._applied_core = None
        self._applied_voice = None
        self._applied_revision = None

    def replace_core(self, core):
        self.core = core
        self.invalidate()

    def activate(self, snapshot: VoiceSnapshot, apply_engine: Callable) -> bool:
        if (self._applied_core is self.core
                and self._applied_voice == snapshot.voice_id
                and self._applied_revision == snapshot.revision):
            return False
        try:
            self.core.voice = snapshot.voice_id
            supported = {item.id for item in self.core.supportedSettings}
            for name in ("rateBoost", "rate", "pitch", "volume", "inflection"):
                if name in supported:
                    setattr(self.core, name, getattr(snapshot, name))
            apply_engine(self.core, snapshot)
        except Exception:
            self.invalidate()
            raise
        self._applied_core = self.core
        self._applied_voice = snapshot.voice_id
        self._applied_revision = snapshot.revision
        return True
```

- [ ] **Step 4: 執行新測試並確認通過。**

Run: `python3 -m pytest tests/test_f4_engine_session.py -q -p no:cacheprovider`

Expected: PASS。

- [ ] **Step 5: 只提交本任務的模組與測試。**

```bash
git add addon/synthDrivers/WorldVoice/driver/engineSession.py tests/test_f4_engine_session.py
git commit -m "feat: add per-engine voice activation session"
```

### Task 2: Voice 僅保存設定，worker 在段落開始時啟用

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/__init__.py:30-66,143-199,201-252`
- Modify: `addon/synthDrivers/WorldVoice/voiceManager.py:90-160,218-255`
- Read: `addon/synthDrivers/WorldVoice/taskManager.py:291-330`（沿用既有 worker 啟用點）
- Create: `tests/test_f4_voice_state.py`

**Interfaces:**
- Consumes: Task 1 的 `VoiceSnapshot`、`EngineSession.activate()`、`invalidate()`。
- Produces: `Voice.snapshot() -> VoiceSnapshot`、`Voice.update_settings(**values)`、`Voice.applyEngineSettings(core, snapshot)`；`Voice.active()` 只在 worker 呼叫 Session；`VoiceManager._createVoiceInstance()` 把 `cls.session` 指派給 Voice。

- [ ] **Step 1: 寫失敗的 Voice／排程測試。** 沿用 `tests/test_worldvoice_lifecycle.py::_load_voice_manager` 與 `tests/test_voice_settings_transaction.py::_create_voices` 的 NVDA stub，驗證建構及設定 setter 不寫 core、revision 從 0 開始、相同值不加版、`rollback()` 還原後加版，以及快照讀取後的修改留到下一次 `active()`。接上 Task 1 的 fake core／Session，驗證同一 Voice 連續兩段時第二段只在 revision 有變時才再次寫 core。另以收集 `append_speech` 閉包的 fake TaskManager，確認閉包本身不再啟用 Voice；現有 `TaskManager._run_one()` 仍啟用一次。關鍵斷言：

```python
a, b = _create_voices(monkeypatch, config)
assert (a.revision, b.revision) == (0, 0)
a.rate = 72
assert a.revision == 1
a.rate = 72
assert a.revision == 1
first = a.snapshot()
a.rate = 81
assert (first.rate, first.revision) == (72, 1)
assert (a.snapshot().rate, a.snapshot().revision) == (81, 2)
a.rollback()
assert (a.rate, a.revision) == (50, 3)
```

另外覆蓋修改中的取消：worker 在啟用後、呼叫 `speak` 前若 token 已取消，不呼叫 `core.speak`；用 `tests/test_worldvoice_request_manager.py` 的事件 fixture 加一個有同步閘門的案例。再讓 `active()` 拋出 `RuntimeError("apply failed")`，斷言 `core.speak` 未被呼叫、task future 帶有該例外、request 的既有失敗完成流程仍執行。

- [ ] **Step 2: 執行新案例，確認因缺少 revision／snapshot 而失敗。**

Run: `python3 -m pytest tests/test_f4_voice_state.py -q -p no:cacheprovider`

Expected: FAIL，Voice 尚無 `revision` 與 `snapshot()`。

- [ ] **Step 3: 改造 Voice 的待生效狀態。** 在 Voice 建構最先建立 `threading.RLock()`、`_revision = 0`、`_initializing = True`、`_waitfactor = 0`；保留原有預設值與 `loadParameter()`，結束後設 `_initializing = False`、`_revision = 0`，刪除建構時 `setCoreParameter()`。通用 property、`variant`、`waitfactor` 都以同一個鎖處理，且只在值不同時增加 revision。對多欄位的 `loadParameter()`、`rollback()`、`update_settings()` 以外層 RLock 包住整批變更。

```python
def percent_property(name):
    private_name = f"_{name}"
    def getter(self):
        with self._settingsLock:
            return getattr(self, private_name)
    def setter(self, value):
        with self._settingsLock:
            if getattr(self, private_name, None) != value:
                setattr(self, private_name, value)
                if not self._initializing:
                    self._revision += 1
    return property(getter, setter)

def update_settings(self, **values):
    allowed = {name for name, _, _ in VOICE_PARAMETERS} | {"waitfactor"}
    if set(values) - allowed:
        raise ValueError("Unknown voice setting")
    with self._settingsLock:
        for name, value in values.items():
            setattr(self, name, value)

def snapshot(self):
    with self._settingsLock:
        return VoiceSnapshot(self.id, self._revision, self.language,
            self._rate, self._pitch, self._volume, self._variant,
            self._inflection, self._rateBoost, self._waitfactor)

def applyEngineSettings(self, core, snapshot):
    return None

def active(self):
    return self.session.activate(self.snapshot(), self.applyEngineSettings)
```

用同樣的 getter／setter 規則實作 `variant`、`waitfactor` 與唯讀 `revision`。`loadParameter()` 和 `rollback()` 的原有 config／commit 行為保留，只將整段本地設定賦值包在鎖內。`Voice.speak()` 閉包移除 `self.active()`，保留取消檢查與 token aware 呼叫；TaskManager `_run_one()` 的 `task.voiceInstance.active()` 是唯一啟用點。`Voice.engineOn()` 建立 core 後建立 `cls.session = EngineSession(cls.core)`；`engineOff()` 在 `finally` 中清除 Session 與 core，保留現有 terminate 呼叫。`VoiceManager._createVoiceInstance()` 於建構後指定 `voiceInstance.session = cls.session`；`VoiceManager` 原有 eager `engineOn()`／`engineOff()` 順序維持。

- [ ] **Step 4: 執行 Voice、request、生命週期及 F3 設定案例。**

Run: `python3 -m pytest tests/test_f4_voice_state.py tests/test_worldvoice_request_manager.py tests/test_worldvoice_lifecycle.py tests/test_voice_settings_transaction.py -q -p no:cacheprovider`

Expected: PASS；確認 TaskManager 的 done/index 身分比對、取消、F3 預覽／還原沒有回歸。

- [ ] **Step 5: 只提交本任務改動。** 對已有 F2／F3 未提交修改的檔案逐段 staging；提交前檢查 staged diff 不含舊修改。

```bash
git add addon/synthDrivers/WorldVoice/driver/__init__.py tests/test_f4_voice_state.py
git add -p addon/synthDrivers/WorldVoice/voiceManager.py
git diff --cached --check
git diff --cached
git commit -m "fix: defer voice settings to speech segment start"
```

### Task 3: 延後引擎專用設定並完成跨引擎驗收

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py:164-203`
- Modify: `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py:164-206`
- Modify: `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py:5-16`
- Modify: `addon/synthDrivers/WorldVoice/voiceManager.py:194-255`（多欄位一致性預覽改走 `update_settings()`）
- Create: `tests/test_f4_engine_adapters.py`
- Modify: `tests/test_f4_voice_state.py`（補充 A 播放時預覽 B、取消及下一段的整合情境）

**Interfaces:**
- Consumes: Task 2 的 `Voice.applyEngineSettings(core, snapshot)`、`Voice.update_settings()`、`Voice.snapshot()`。
- Produces: VE／Cerence 在 Session 啟用時才套用 variant 與 waitfactor；OneCore 在每次需要啟用時才套用 language；UI 保持現有設定方式但不再碰 core。

- [ ] **Step 1: 寫失敗的引擎差異測試。** 使用 `tests/worldvoice_cancel_wrapper_harness.py::load_real_driver_with_native_stubs` 載入 VE／Cerence wrapper；其 adapter 的 `applyEngineSettings()` 以 `object.__new__(Voice)` 建立實例，搭配 `types.SimpleNamespace` fake core，不觸發原生初始化。fake core 提供 `getVoiceInstance()`、`getParameter()`、`availableVariants`、`waitfactor`，並攔截 wrapper 的 `TtsSetParamList`。Task 2 已驗證本地 `variant`／`waitfactor` setter；本測試另確認 wrapper 移除即時寫入的覆寫。測試 `default` 恢復首次讀到的原生預設變體、無效的非預設變體失敗。以 AST 載入 OneCore Voice class，驗證建構不寫 language、`applyEngineSettings()` 寫入快照的 language。關鍵案例：

```python
adapter = object.__new__(engine_harness.module.Voice)
writes = []
monkeypatch.setattr(engine_harness.module, "TtsSetParamList",
    lambda instance, pair: lambda: writes.append((instance, pair[1])))
core = types.SimpleNamespace(waitfactor=0)
core.getVoiceInstance = lambda voice_id: f"native:{voice_id}"
core.getParameter = lambda instance, parameter, type_: "plain"
core.availableVariants = {"plain": object(), "bright": object()}
adapter.applyEngineSettings(core, replace(snapshot, variant="bright"))
snapshot = replace(snapshot, variant="default", waitfactor=4)
adapter.applyEngineSettings(core, snapshot)
assert writes[-1] == ("native:a", "plain")
assert core.waitfactor == 4
with pytest.raises(ValueError, match="Unavailable variant"):
    adapter.applyEngineSettings(core, replace(snapshot, variant="missing"))
```

UI 整合案例沿用 `tests/test_voice_settings_transaction.py` 的 panel stub：A 正在使用的 fake core 記錄 setter；選取／預覽 B 後記錄不變；B 對應的 worker 啟用後才出現 B 的參數；取消預覽後再啟用 B 會回到還原值。

- [ ] **Step 2: 執行新案例，確認 wrapper 的 setter 仍即時寫 core 或缺少啟用 hook。**

Run: `python3 -m pytest tests/test_f4_engine_adapters.py tests/test_f4_voice_state.py -q -p no:cacheprovider`

Expected: FAIL，指出待改造的 VE／Cerence／OneCore 寫入路徑。

- [ ] **Step 3: 移動引擎專用寫入。** 刪除 VE／Cerence Voice 的 `variant`、`waitfactor` setter/getter 覆寫，繼承 Task 2 的純本地 property；保留變體清單的讀取功能。各 Voice 在第一次啟用某個 core 時、改動原生變體前，讀取該原生實例的預設變體，並以 core 身分一起快取。兩個 wrapper 的 `applyEngineSettings()` 使用相同決策：

```python
def applyEngineSettings(self, core, snapshot):
    instance = core.getVoiceInstance(snapshot.voice_id)
    if getattr(self, "_defaultVariantCore", None) is not core:
        self._defaultVariant = core.getParameter(
            instance, VE_PARAM_VOICE_OPERATING_POINT, type_=str)
        self._defaultVariantCore = core
    if snapshot.variant != "default" and snapshot.variant not in core.availableVariants:
        raise ValueError(f"Unavailable variant: {snapshot.variant}")
    selected = self._defaultVariant if snapshot.variant == "default" else snapshot.variant
    TtsSetParamList(instance, (VE_PARAM_VOICE_OPERATING_POINT, selected))()
    core.waitfactor = snapshot.waitfactor
```

OneCore 刪除建構子中的 `self.core.language = self.language`，改成：

```python
def applyEngineSettings(self, core, snapshot):
    core.language = snapshot.language
```

`VoiceManager.previewVoiceParameterConsistent()` 把每個 Voice 的五次個別指派換成一次 `instance.update_settings(rate=baseInstance.rate, pitch=baseInstance.pitch, volume=baseInstance.volume, inflection=baseInstance.inflection, rateBoost=baseInstance.rateBoost)`；此方法只更新本地值。若 VE／Cerence 的 `variants` 中繼資料讀取需要開啟另一個原生實例，保持目前已啟用 Voice 與其參數不變；測試要記錄 `core.voice` 及參數確認此點。

- [ ] **Step 4: 執行新測試及既有回歸案例。**

Run: `python3 -m pytest tests -q -p no:cacheprovider`

Expected: PASS；再執行 `git diff --check`，預期沒有空白錯誤。若 Windows／NVDA 原生引擎不可用，記錄未能做原生語音輸出的限制；stub 測試仍須通過。

- [ ] **Step 5: 只提交本任務改動。** `voiceManager.py` 仍只選本任務的 hunk；先檢查 staged diff。

```bash
git add addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py tests/test_f4_engine_adapters.py tests/test_f4_voice_state.py
git add -p addon/synthDrivers/WorldVoice/voiceManager.py
git diff --cached --check
git diff --cached
git commit -m "fix: defer engine-specific voice parameters"
```

## Completion Check

依規格逐項核對：同 Voice 不變時無 native setter、修改後下一段套用、A → B → A、F3 Cancel、core 重建、引擎特殊參數、套用失敗、取消及暫停。僅在完成計畫且取得實際驗證輸出後，才將 `review_gpt1.md` 的 F4 狀態改為已修正；保留工作區中與本計畫無關的現有修改。
