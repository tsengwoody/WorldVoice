# Phase 47a: layered naming rule, its guard, and the core-side renames Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice complex flow (DEVELOPMENT_WORKFLOW.md §4): one implementer runs every task in order,
> applying the `File:`/`Edit:` blocks byte for byte; every commit's tree ids must match this plan.
> The orchestrator dispatches the final Fable 5.1 review (§3.3, §4.5).
> 7 tasks: no batch reviews (§3.2).

**Goal:** Put refactor9 §6.1's layered naming rule into an AST guard whose docstring states it, list every current host-layer and plugin-contract violation for phases 47b/47c, and rename every camelCase name the portable core defines to snake_case, with all callers and no compatibility aliases — with no user-visible change.

**Architecture:** Task 1 adds `tests/test_naming_layers.py`: a path table puts each add-on module in the core, host, pending or excluded layer; a walker reads every name a module binds (except imports); a name breaking its layer's style fails unless a readable add-on base class defines it, `INTERFACE_NAMES` lists it, or a transitional list names it (`TRANSITIONAL_47A` for the core names this phase renames, `TRANSITIONAL_47B` for the host layer, `TRANSITIONAL_47C` for the plugin contract). Tasks 2–6 each first delete their names from `TRANSITIONAL_47A` (red), then rename them — by a word-rename script with an explicit name list per file, plus `Edit:` blocks where an occurrence must stay or ruff re-wraps a line — and prove with an order-sensitive token check that the commit changes nothing else. Task 6 deletes the empty core list. Task 7 runs the §7 verification.

**Tech Stack:** Python 3 (NVDA add-on; tests on Python 3.14), `ast`/`tokenize`, pytest, ruff `==0.16.3` and add-trailing-comma through prek.

**Spec:** `docs/superpowers/specs/2026-10-27-phase47a-naming-rule-core-design.md`

**Base:** `master` `8e1df5b` — `HEAD:addon` = `b62ed75314a91f666f195771ec025f77886d128c`, `HEAD:tests` = `0cbb15eaac511bddf3d7969c0b8049b709814b72`; `python3 -m pytest -q tests` → 3269 passed, 0 skipped; `prek run --all-files` all Passed; `git diff --check` clean. The spec and this plan are committed under `docs/` before Task 1 (`git add -f`: `docs/` is git-ignored but tracked); `docs/` does not enter the tree ids.

**Dry run:** see the end of this plan.

## Global Constraints

- Shell variables used below: `$SCRATCH` is the session scratchpad directory (`/tmp/claude-0/-workspace-WorldVoice/<session>/scratchpad`), exported in the shell; every command runs from the repository root of the worktree. `bash $SCRATCH/runtests.sh <repo> <pytest args>` (written in Task 1) runs one pytest process and kills it when MemAvailable < 3 GB.
- Apply every `Edit:` block as one exact replacement (the "Replace" text occurs exactly once in the file at that point). Block text is whole lines. Blocks and scripts leave files in the form prek leaves them (ruff's isort order and format, add-trailing-comma), so each commit passes the hooks on the first try. If a hook still changes a file, stop: the tree ids will not match (§4.4).
- No user-visible change: no panel, label, message, log text, setting id, config key, gesture, translation, readme or changelog changes.
- Renames are mechanical: every new name is `snake(old)` (an underscore before each capital that follows a lowercase letter or digit, then lowercase). No compatibility aliases (refactor9 §5.3). Host-layer names (47b), the plugin contract `driver.Voice`/`VoiceFacade.update_settings` (47c), `engineRegistry/`, `workspace.py`, NVDA override names, names of vendored interfaces and config keys stay.
- `typing.override` is not used: the add-on supports NVDA 2024.1 (Python 3.11), see spec §4.3.
- Never modify `driver/<Engine>/driver/`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; engine drivers stay independently installable; never stage Neural or `ref`.
- ruff pinned `0.16.3`; tabs; line length 110. Commits: English `<type>: <summary>` with a body saying why, no `Co-Authored-By`, `git add` with explicit paths only, check `git diff --cached --stat` first, never `--no-verify`, never `git stash`, no push, never touch the main checkout.
- Tests: one pytest process at a time, under `$SCRATCH/runtests.sh`.
- Deviations go to `.superpowers/sdd/2026-10-27-phase47a-naming-rule-core/progress.md` as `Ruling: <decision> — <reason> — <cost if wrong>`.

## Review Focus

1. **Starting WorldVoice.** The synth builds the manager with the keyword `task_manager=` (`__init__.py:237`); a missed keyword would raise `TypeError` in `_initialize`, and WorldVoice would not load. Task 2: the fake `VoiceManager` of `tests/test_worldvoice_lifecycle.py` takes `task_manager`, so `test_failed_synth_construction_releases_acquired_resources[…]` and the other lifecycle tests fail if the synth still passes `taskManager=`; `tests/test_runtime_composition.py` builds real managers.
2. **Choosing the main voice.** NVDA's `loadSettings` repairs a saved voice only when the `default_voice_name` setter raises `LookupError` (`voices/manager.py:191`), and the setter must still apply both consistency rules (`on_keep_engine_consistent`, `on_keep_main_locale_voice_consistent`). Task 3: `test_runtime_composition.py::test_an_unavailable_main_voice_raises_and_keeps_the_current_one`, `test_role_presenter.py::test_main_locale_voice_consistency_switches_then_mirrors_new_voice`, `test_voice_settings_transaction.py`, `test_voice_manager_roles.py`.
3. **Vocalizer and Cerence voices.** The vendored VE/Cerence core has its own `getVoiceInstance`, `_instanceCache` and `getVoiceNameForLanguage`, which the vendored code calls; renaming them would break voice creation and language switching in those engines. Task 3: the rename lists leave those files out; Task 7's leftover grep A shows only those names left; `test_vocalizer_segment_drain.py`, `test_runtime_drain_integration.py::test_language_change_active_native_call_cannot_escape_cancel[…]`, `test_worldvoice_cancel_wrappers.py`.
4. **NVDA calling a renamed parameter.** The speech filter passes the sequence positionally (`ref/nvda/source/extensionPoints/__init__.py:114`), say-all calls the wrapped `getTextInfoSpeech` through `*args, **kwargs`, and the vendored RHVoice and OneCore call `LeasedPlayer.feed(…, onDone=…)` by keyword, so `feed` keeps `onDone`. Tasks 4 and 6: `test_pipeline_stages.py`, `test_worldvoice_speak.py`, `test_say_all.py::test_say_all_adds_the_scaled_pause_after_nvdas_speech`, `test_segment_host.py::test_feed_admitted_serves_subclasses_that_choose_their_record`, the RHVoice/OneCore/SAPI5 drain tests; Task 7's leftover grep B shows the kept `onDone` and NVDA's `getTextInfoSpeech`.
5. **A language without an installed voice.** Detection must still skip a language whose voice is not installed (`available_languages`) and keep the current language. Task 5: `test_language_detector.py::test_unavailable_language_does_not_cover_its_script[…]`, `test_script_without_an_installed_language_keeps_the_current_language`, `test_property_letters_go_to_installed_languages`.

Also watched: the guard itself (Task 1): a base class that resolves to the class itself would exempt everything (`test_the_guard_reads_the_imported_base_of_a_class_with_its_name`), and the probe of Task 1 Step 3 shows a new camelCase core name fails.

---

### Task 1: The naming guard with today's lists

**Files:**
- Create: `tests/test_naming_layers.py`
- Create (scratch, not committed): `$SCRATCH/runtests.sh`

**Interfaces:**
- Consumes: the base tree.
- Produces: `tests/test_naming_layers.py` with `layer(path)`, `follows_layer(definition, layer)`, `violations(index)`, `_Index`, `INTERFACE_NAMES` (3 core entries), `TRANSITIONAL_47A` (68 core names), `TRANSITIONAL_47B` (317 host names), `TRANSITIONAL_47C` (6 contract names) and 18 tests.

- [ ] **Step 1: Write the test runner and the guard**

**File:** `$SCRATCH/runtests.sh`

```bash
#!/bin/bash
# Usage: runtests.sh <repo> [pytest args...]; kills pytest when MemAvailable < 3 GB.
repo=$1; shift
cd "$repo" || exit 2
python3 -m pytest -q -p no:cacheprovider "$@" &
pid=$!
while kill -0 $pid 2>/dev/null; do
	avail=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
	if [ "$avail" -lt 3000000 ]; then echo "MEMORY GUARD: killing pytest ($avail kB)"; pkill -P $pid; kill $pid; fi
	sleep 2
done
wait $pid
```

**File:** `tests/test_naming_layers.py`

```python
"""Names follow the layer of the module that defines them (refactor9 §6.1, decided 2026-10-27).

1. The layer of a module decides the style of the names it defines itself:
   - portable core (CORE): PEP 8 snake_case;
   - NVDA host layer (HOST): NVDA's mixedCase (ref/nvda/projectDocs/dev/codingStandards.md), a
     lowercase first letter and no underscore apart from the prefixes script_, event_, _get_, _set_;
   - both: classes in CapWords; module and class names may also be UPPER_CASE constants or
     CapWords type aliases; leading underscores and dunder names are free.
   PENDING modules wait for the command model (refactor9 §6.2) and are not checked. EXCLUDED code
   (vendored engine drivers, NVDA's sonic, generated Unicode data) and tests/ are not renamed.
2. A name that implements or overrides someone else's interface keeps that name:
   - a method or field whose name a base class defines, when the guard can read that base: a class
     of the add-on named in the class statement (a Protocol or ABC of the core, a vendored driver
     class, driver.Voice). The parameters of such a method mirror the base as well;
   - a name from an interface the guard cannot read (NVDA, the standard library, a stored setting
     id) is listed in INTERFACE_NAMES with the interface it mirrors.
   typing.override cannot be the marker yet: see test_no_module_imports_typing_override.
3. Config keys and driver setting ids are strings, not names: renaming one needs a config
   migration, so they stay as stored.

Every name a module binds is checked except imports: functions, methods, classes, parameters
(lambdas included), class and dataclass fields, attributes set on self, module variables and
local variables. TRANSITIONAL_47B lists the host-layer names that break the rule until phase 47b
renames them or marks them as interface names; TRANSITIONAL_47C the plugin contract driver.Voice
and VoiceFacade, until phase 47c.
"""

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"
SYNTH = "synthDrivers/WorldVoice/"

CORE = tuple(
	SYNTH + path
	for path in (
		"runtime/",
		"unicodeScripts/",
		"text/",
		"languageDetection/",
		"pipeline/",
		"voices/",
		"locales.py",
		"numberLanguage.py",
		"bringup.py",
		"speechCommands.py",
	)
)
HOST = (
	SYNTH + "bridge/",
	SYNTH + "driver/",
	SYNTH + "ui/",
	SYNTH + "__init__.py",
	"globalPlugins/WorldVoice/",
	"installTasks.py",
	"generics/",
)
PENDING = (SYNTH + "engineRegistry/", SYNTH + "workspace.py")
EXCLUDED = re.compile(
	r"synthDrivers/WorldVoice/(driver/[^/]+/driver/|driver/sonic/|unicodeScripts/\w+_data\.py$)",
)

SNAKE_CASE = re.compile(r"_*[a-z][a-z0-9_]*")
MIXED_CASE = re.compile(r"_*(script_|event_|_get_|_set_)?[a-z][a-zA-Z0-9]*")
CAP_WORDS = re.compile(r"_*[A-Z][a-zA-Z0-9]*")
UPPER_CASE = re.compile(r"_*[A-Z][A-Z0-9_]*")

# Names from interfaces outside the add-on: {module path: {qualified name: the interface}}.
INTERFACE_NAMES = {
	SYNTH + "runtime/models.py": {
		"VoiceSnapshot.rateBoost": "the voice setting id rateBoost (runtime/voiceSettings.VOICE_PARAMETERS), "
		"stored in nvda.ini and NVDA's SynthDriver setting of that name",
	},
	SYNTH + "runtime/segmentHost.py": {
		"LeasedPlayer.feed.<locals>.onDone": "NVDA nvwave.WavePlayer.feed(data, size=None, onDone=None), "
		"which engine wrappers call by keyword",
	},
	SYNTH + "speechCommands.py": {
		"WVLangChangeCommand.isDefault": "NVDA speech.commands.SynthParamCommand.isDefault, which "
		"ParamChangeTracker.update reads (speech/manager.py)",
	},
}


# Core names that phase 47a renames to snake_case; empty at the end of the phase.
TRANSITIONAL_47A: dict[str, set[str]] = {
	"synthDrivers/WorldVoice/languageDetection/detector.py": {
		"LanguageDetector.__init__.<locals>.availableLanguages",
		"LanguageDetector.add_detected_language_commands.<locals>.curLang",
		"LanguageDetector.add_detected_language_commands.<locals>.defaultLang",
		"LanguageDetector.add_detected_language_commands.<locals>.speechSequence",
		"LanguageDetector.add_detected_language_commands.<locals>.targetLang",
		"LanguageDetector.add_detected_language_commands.<locals>.tmpLang",
		"LanguageDetector.availableLanguages",
	},
	"synthDrivers/WorldVoice/pipeline/breaks.py": {
		"_merge_edge_breaks.<locals>.speechSequence",
		"_plain_breaks.<locals>.speechSequence",
	},
	"synthDrivers/WorldVoice/pipeline/items.py": {
		"_insert_item_breaks.<locals>.speechSequence",
		"item_wait_factor.<locals>.speechSequence",
	},
	"synthDrivers/WorldVoice/pipeline/languageCommands.py": {
		"deduplicate_language_command.<locals>.speechSequence",
		"inject_langchange_reorder.<locals>.speechSequence",
		"lang_cmd_to_voice.<locals>.speechSequence",
		"remove_language_command.<locals>.speechSequence",
	},
	"synthDrivers/WorldVoice/pipeline/numberStages.py": {
		"_inject_item_numbers.<locals>.speechSequence",
		"_insert_number_breaks.<locals>.speechSequence",
		"_remove_space.<locals>.speechSequence",
		"_split_numbers.<locals>.speechSequence",
		"_spoken_later.<locals>.speechSequence",
		"detect_with_number_language.<locals>.speechSequence",
		"inject_numbers.<locals>.speechSequence",
		"number_wait_factor.<locals>.speechSequence",
		"remove_thousands_separators.<locals>.speechSequence",
		"wrap_numbers_for_detection.<locals>.speechSequence",
	},
	"synthDrivers/WorldVoice/pipeline/punctuation.py": {
		"_punctuation_pauses.<locals>.speechSequence",
		"inject_punctuation_pause.<locals>.speechSequence",
	},
	"synthDrivers/WorldVoice/pipeline/registry.py": {
		"_run_logged.<locals>.speechSequence",
		"_stage_handler.<locals>.handler.<locals>.speechSequence",
		"apply_speech_dictionaries.<locals>.speechSequence",
		"listable.<locals>.wrapper.<locals>.speechSequence",
		"speech_viewer.<locals>.speechSequence",
	},
	"synthDrivers/WorldVoice/pipeline/sayAll.py": {
		"_wrap_get_text_info_speech_with_sayall_break.<locals>.getTextInfoSpeech",
		"_wrap_get_text_info_speech_with_sayall_break.<locals>.getTextInfoSpeechWithSayAllBreak",
		"_wrap_get_text_info_speech_with_sayall_break.<locals>.getTextInfoSpeechWithSayAllBreak.<locals>.waitFactor",
	},
	"synthDrivers/WorldVoice/pipeline/unspaced.py": {
		"inject_unspaced_script_space_pause.<locals>.speechSequence",
	},
	"synthDrivers/WorldVoice/runtime/segmentHost.py": {
		"LeasedPlayer._callback.<locals>.onDone",
		"LeasedPlayer._feed_admitted.<locals>.onDone",
	},
	"synthDrivers/WorldVoice/voices/manager.py": {
		"VoiceManager.__init__.<locals>.taskManager",
		"VoiceManager._createVoiceInstance",
		"VoiceManager._createVoiceInstance.<locals>.voiceInstance",
		"VoiceManager._createVoiceInstance.<locals>.voiceName",
		"VoiceManager._defaultVoiceInstance",
		"VoiceManager._getConfiguredVoiceNameForLanguage",
		"VoiceManager._getDefaultVoiceSpec",
		"VoiceManager._instanceCache",
		"VoiceManager._setVoiceDatas",
		"VoiceManager.allLanguages",
		"VoiceManager.beginVoiceSettingsEdit",
		"VoiceManager.defaultVoiceInstance",
		"VoiceManager.defaultVoiceName",
		"VoiceManager.getVoiceCapabilities",
		"VoiceManager.getVoiceInstance",
		"VoiceManager.getVoiceInstance.<locals>.voiceName",
		"VoiceManager.getVoiceLocaleForLanguage",
		"VoiceManager.getVoiceNameForLanguage",
		"VoiceManager.getVoiceSpec",
		"VoiceManager.getVoiceVariants",
		"VoiceManager.localeToVoicesMap",
		"VoiceManager.localesToNamesMap",
		"VoiceManager.onKeepEngineConsistent",
		"VoiceManager.onKeepMainLocaleVoiceConsistent",
		"VoiceManager.onVoiceParameterConsistent",
		"VoiceManager.onVoiceParameterConsistent.<locals>.baseInstance",
		"VoiceManager.previewVoiceParameterConsistent",
		"VoiceManager.previewVoiceParameterConsistent.<locals>.baseInstance",
		"VoiceManager.taskManager",
		"VoiceManager.voiceInfos",
	},
}

# Host-layer names that phase 47b renames to mixedCase or marks as interface names.
TRANSITIONAL_47B: dict[str, set[str]] = {
	"generics/coreArchive.py": {
		"extract_core_archive",
		"extract_core_archive.<locals>.archive_path",
		"extract_core_archive.<locals>.bad_member",
		"extract_core_archive.<locals>.core_file",
		"extract_core_archive.<locals>.workspace_path",
	},
	"globalPlugins/WorldVoice/__init__.py": {
		"GlobalPlugin.check_log_record",
		"GlobalPlugin.disable_log_record",
		"GlobalPlugin.enable_log_record",
		"GlobalPlugin.onFileImport.<locals>.core_zip_path",
		"GlobalPlugin.popup_SpeechSettingsDialog",
		"GlobalPlugin.script_popup_SpeechSettingsDialog",
		"GlobalPlugin.script_switch_log_record",
		"GlobalPlugin.submenu_WorldVoice",
		"GlobalPlugin.submenu_item",
	},
	"globalPlugins/WorldVoice/panels/base.py": {
		"BaseSettingsPanel._write_settings",
		"_as_bool",
	},
	"globalPlugins/WorldVoice/panels/detection.py": {
		"UnicodeDetectionSettingsPanel._add_script_choice",
		"UnicodeDetectionSettingsPanel.makeSettings.<locals>.DetectLanguageTimingLabel",
	},
	"globalPlugins/WorldVoice/panels/engine.py": {
		"SpeechEngineSettingsPanel.makeSettings.<locals>.group_sizer",
	},
	"globalPlugins/WorldVoice/panels/log.py": {
		"LogSettingsPanel._enable_checkbox",
		"LogSettingsPanel.makeSettings.<locals>.group_sizer",
		"LogSettingsPanel.onSave.<locals>.enabled_after",
		"LogSettingsPanel.onSave.<locals>.enabled_before",
	},
	"globalPlugins/WorldVoice/panels/role.py": {
		"SpeechRoleSettingsPanel.makeSettings.<locals>.set_main_voice",
		"got_error_callback",
	},
	"globalPlugins/WorldVoice/pipelineLog.py": {
		"PipelineLogService.__init__.<locals>.conf_provider",
		"PipelineLogService._conf_provider",
		"ask_disable_on_start",
		"ask_export",
		"confirm_enable",
		"confirm_enable.<locals>.allow_cancel",
		"export_with_dialog",
		"export_with_dialog.<locals>.pipeline_log_file",
		"pipeline_log",
	},
	"globalPlugins/WorldVoice/rolePresenter.py": {
		"RolePanelPresenter.__init__.<locals>.set_main_voice",
		"RolePanelPresenter.__init__.<locals>.speech_section",
		"RolePanelPresenter._before_parameter_preview",
		"RolePanelPresenter._main_parameters",
		"RolePanelPresenter._read_flags",
		"RolePanelPresenter._set_main_voice",
		"RolePanelPresenter._speech_section",
		"RolePanelPresenter.keep_engine",
		"RolePanelPresenter.keep_parameters",
		"RolePanelPresenter.keep_voice",
		"RolePanelPresenter.select_voice",
		"RolePanelPresenter.selected_voice",
		"RolePanelPresenter.set_engine_consistency",
		"RolePanelPresenter.set_parameter",
		"RolePanelPresenter.set_parameter_consistency",
		"RolePanelPresenter.set_variant",
		"RolePanelPresenter.set_voice_consistency",
	},
	"globalPlugins/WorldVoice/utils.py": {
		"guard_errors",
	},
	"installTasks.py": {
		"_extract_core_archive",
		"_extract_core_archive.<locals>.archive_path",
		"_extract_core_archive.<locals>.workspace_path",
		"_load_by_path",
		"_load_core_archive",
		"_workspace_path",
		"onInstall.<locals>.archive_path",
		"onInstall.<locals>.core_dir",
		"onInstall.<locals>.core_zip_paths",
		"onInstall.<locals>.workspace_path",
	},
	"synthDrivers/WorldVoice/__init__.py": {
		"SynthDriver._apply_pipeline_settings",
		"SynthDriver._detect_languages",
		"SynthDriver._driver_settings",
		"SynthDriver._initialize.<locals>.shutdown_tasks",
		"SynthDriver._is_stored_number_language",
		"SynthDriver._number_language",
		"SynthDriver._on_detection_settings",
		"SynthDriver._pipeline_driver_setting",
		"SynthDriver._set_voice_parameter",
		"SynthDriver.add_detected_language_commands",
		"SynthDriver.refresh_language_detection",
		"SynthDriver.speech_context",
		"SynthDriver.voice_manager",
		"base_dir",
	},
	"synthDrivers/WorldVoice/bridge/commands.py": {
		"normalize_legacy_commands",
	},
	"synthDrivers/WorldVoice/bridge/completionPolicies.py": {
		"CompletionPolicy.__init__.<locals>.force_unverified_drain",
		"CompletionPolicy.__init__.<locals>.nvda_version",
		"CompletionPolicy.audio_mode",
		"CompletionPolicy.audio_mode.<locals>.use_wasapi",
		"CompletionPolicy.audio_mode.<locals>.voice_class",
		"CompletionPolicy.contract_for",
		"CompletionPolicy.contract_for.<locals>.audio_mode",
		"CompletionPolicy.contract_for.<locals>.nvda_version",
		"CompletionPolicy.contract_for.<locals>.voice_class",
		"CompletionPolicy.drain_support",
		"CompletionPolicy.drain_support.<locals>.audio_mode",
		"CompletionPolicy.drain_support.<locals>.module_name",
		"CompletionPolicy.drain_support.<locals>.nvda_version",
		"CompletionPolicy.drain_support.<locals>.voice_class",
		"CompletionPolicy.force_unverified_drain",
		"CompletionPolicy.nvda_version",
		"CompletionPolicy.select.<locals>.audio_mode",
		"CompletionPolicy.select.<locals>.voice_class",
	},
	"synthDrivers/WorldVoice/bridge/engineAdapter.py": {
		"LegacyEngineAdapter.__init__.<locals>.index_ledger",
		"LegacyEngineAdapter.__init__.<locals>.resolve_voice",
		"LegacyEngineAdapter.__init__.<locals>.voice_class",
		"LegacyEngineAdapter._completion_configured",
		"LegacyEngineAdapter._index_ledger",
		"LegacyEngineAdapter._resolve_voice",
		"LegacyEngineAdapter._segment_events",
		"LegacyEngineAdapter._source_id",
		"LegacyEngineAdapter._voice_class",
		"LegacyEngineAdapter.configure_completion",
		"LegacyEngineAdapter.configure_segment_events",
		"LegacyEngineAdapter.finish_segment",
		"LegacyEngineAdapter.list_voices",
		"LegacyEngineAdapter.list_voices.<locals>.voice_id",
		"LegacyEngineAdapter.notification_source",
		"LegacyEngineAdapter.speak.<locals>.on_event",
		"_speak_plain",
		"_speak_plain.<locals>.on_event",
		"_speak_segment",
		"_speak_segment.<locals>.on_event",
	},
	"synthDrivers/WorldVoice/bridge/indexCodec.py": {
		"encode_segment",
	},
	"synthDrivers/WorldVoice/bridge/indexLedger.py": {
		"IndexAllocation.end_index",
		"IndexAllocation.wire_indexes",
		"IndexLedger._pending_indexes",
		"IndexLedger._pending_indexes.<locals>.source_id",
		"IndexLedger._remove_indexes",
		"IndexLedger._remove_indexes.<locals>.keep_terminal",
		"IndexLedger.bind.<locals>.index_range",
		"IndexLedger.bind.<locals>.source_id",
		"IndexLedger.prepare.<locals>.original_indexes",
		"IndexLedger.prepare.<locals>.segment_id",
		"IndexLedger.prepare.<locals>.source_id",
		"IndexLedger.receive_index",
		"IndexLedger.receive_index.<locals>.binding_token",
		"IndexLedger.receive_index.<locals>.source_id",
		"IndexLedger.receive_index.<locals>.wire_index",
		"IndexLedger.receive_segment_event",
		"IndexLedger.receive_segment_event.<locals>.binding_token",
		"IndexLedger.retire_segment",
		"IndexLedger.retire_segment.<locals>.segment_id",
		"IndexLedger.retire_segment.<locals>.source_id",
		"IndexLedger.retire_source",
		"IndexLedger.retire_source.<locals>.source_id",
		"IndexLedger.unbind.<locals>.source_id",
		"_Binding.source_id",
		"_Segment.drain_seen",
		"_Segment.end_seen",
		"_Segment.segment_id",
		"_Source.next_index",
		"_find_start",
	},
	"synthDrivers/WorldVoice/bridge/nvdaEvents.py": {
		"NvdaEventBridge.__init__.<locals>.done_event",
		"NvdaEventBridge.__init__.<locals>.get_synth",
		"NvdaEventBridge.__init__.<locals>.index_event",
		"NvdaEventBridge.__init__.<locals>.index_ledger",
		"NvdaEventBridge._batch_handler",
		"NvdaEventBridge._binding_is_active",
		"NvdaEventBridge._can_notify",
		"NvdaEventBridge._done_event",
		"NvdaEventBridge._index_event",
		"NvdaEventBridge._index_ledger",
		"NvdaEventBridge._on_done",
		"NvdaEventBridge._on_index",
		"NvdaEventBridge._receive.<locals>.batch_handler",
		"NvdaEventBridge._receive.<locals>.load_events",
		"NvdaEventBridge.bind.<locals>.cleanup_error",
		"NvdaEventBridge.bind.<locals>.ledger_token",
		"NvdaEventBridge.bind.<locals>.source_id",
		"NvdaEventBridge.close.<locals>.first_error",
		"NvdaEventBridge.done_speaking",
		"NvdaEventBridge.index_reached",
		"NvdaEventBridge.segment_sink",
		"NvdaEventBridge.segment_sink.<locals>.batch_handler",
		"NvdaEventBridge.segment_sink.<locals>.receive.<locals>.load_events",
		"NvdaEventBridge.start.<locals>.batch_handler",
		"NvdaEventBridge.start.<locals>.cleanup_error",
		"NvdaEventBridge.unbind.<locals>.source_id",
		"_Binding.ledger_token",
		"_Binding.source_id",
		"_BindingEvents.__new__.<locals>.is_active",
	},
	"synthDrivers/WorldVoice/driver/Cerence/__init__.py": {
		"SynthDriver._begin_record",
		"SynthDriver._callback_admission",
		"SynthDriver._close_admission",
		"SynthDriver._confirm_native_quiescence",
		"SynthDriver._drop_queued_speech",
		"SynthDriver._feed_callback",
		"SynthDriver._finish_termination",
		"SynthDriver._guard_installed",
		"SynthDriver._idle_player",
		"SynthDriver._initialize_native",
		"SynthDriver._install_guard",
		"SynthDriver._install_guard.<locals>.restoration_errors",
		"SynthDriver._is_reentrant_termination",
		"SynthDriver._player_operation",
		"SynthDriver._real_player",
		"SynthDriver._record_valid",
		"SynthDriver._reset_callback_audio",
		"SynthDriver._retire_player_operation",
		"SynthDriver._retire_record",
		"SynthDriver._run_native",
		"SynthDriver._stop_player",
		"SynthDriver.get_segment_drain_support",
		"SynthDriver.get_segment_drain_support.<locals>.audio_mode",
		"SynthDriver.get_segment_drain_support.<locals>.nvda_version",
		"SynthDriver.speak_segment",
		"SynthDriver.speak_segment.<locals>.on_event",
		"_ContextualCerenceCallback._process.<locals>.message_type",
		"_GuardedPlayer.__init__.<locals>.real_player",
		"_SilenceGate._inside_native_call",
		"_SilenceGate.is_set",
		"_SilenceGate.token_cancelled",
		"_strip_bytes_repr",
	},
	"synthDrivers/WorldVoice/driver/Espeak/__init__.py": {
		"SynthDriver._beginSpeech.<locals>.index_callback",
		"SynthDriver._beginSpeech.<locals>.owner_ref",
		"SynthDriver.get_segment_drain_support",
		"SynthDriver.get_segment_drain_support.<locals>.audio_mode",
		"SynthDriver.get_segment_drain_support.<locals>.nvda_version",
		"SynthDriver.speak_segment",
		"SynthDriver.speak_segment.<locals>.on_event",
		"_EspeakPort.mark_not_speaking",
		"_EspeakPort.run_when_done",
		"_EspeakPort.set_index_callback",
		"_EspeakPort.stop_player",
		"_SegmentNative.espeak_Synth",
		"_SegmentNative.espeak_ng_Cancel",
	},
	"synthDrivers/WorldVoice/driver/OneCore/__init__.py": {
		"SynthDriver._callback.<locals>.control_failed",
		"SynthDriver._checkSegmentAdmission.<locals>.control_error",
		"SynthDriver._feedSegment.<locals>.on_done",
		"SynthDriver._segmentPlayback.<locals>.bytes_per_sec",
		"SynthDriver._segmentPlayback.<locals>.data_len",
		"SynthDriver.get_segment_drain_support",
		"SynthDriver.get_segment_drain_support.<locals>.audio_mode",
		"SynthDriver.get_segment_drain_support.<locals>.nvda_version",
		"SynthDriver.speak_segment",
		"SynthDriver.speak_segment.<locals>.on_event",
		"_DetachableCallback.__call__.<locals>.driver_ref",
	},
	"synthDrivers/WorldVoice/driver/RHVoice/__init__.py": {
		"SynthDriver.__init__.<locals>.get_player",
		"SynthDriver.__init__.<locals>.original_get_player",
		"SynthDriver._native_callback",
		"SynthDriver._native_callback.<locals>.is_done",
		"SynthDriver.get_segment_drain_support",
		"SynthDriver.get_segment_drain_support.<locals>.audio_mode",
		"SynthDriver.get_segment_drain_support.<locals>.nvda_version",
		"SynthDriver.speak_segment",
		"SynthDriver.speak_segment.<locals>.on_event",
		"_NativeCallback.__init__.<locals>.is_done",
		"_NativeCallback._is_done",
		"_NativeLibrary.RHVoice_delete_message",
		"_NativeLibrary.RHVoice_new_message",
		"_NativeLibrary.RHVoice_speak",
		"_RHVoiceInner.cancel_flag",
		"_RHVoiceInner.rate_boost",
		"_RHVoiceInner.tts_engine",
		"_RHVoiceInner.tts_queue",
		"_RHVoiceInner.tts_thread",
		"_WavePlayer._callback.<locals>.index_done",
	},
	"synthDrivers/WorldVoice/driver/SAPI5/__init__.py": {
		"SynthDriver._speakThread.<locals>.control_error",
		"SynthDriver.get_segment_drain_support",
		"SynthDriver.get_segment_drain_support.<locals>.audio_mode",
		"SynthDriver.get_segment_drain_support.<locals>.nvda_version",
		"SynthDriver.speak_segment",
		"SynthDriver.speak_segment.<locals>.on_event",
		"_Sapi5Strategy.drain.<locals>.control_error",
		"_SapiRequest.index_lock",
		"_SegmentAudioStream.ISequentialStream_RemoteWrite",
		"_SegmentSapiSink.Bookmark",
		"_SegmentSapiSink.EndStream",
		"_SegmentSapiSink.ISpNotifySink_Notify",
		"_SegmentSapiSink.StartStream",
		"_purge_flags",
	},
	"synthDrivers/WorldVoice/driver/VE/__init__.py": {
		"SynthDriver._begin_record",
		"SynthDriver._callback_admission",
		"SynthDriver._close_admission",
		"SynthDriver._confirm_native_quiescence",
		"SynthDriver._drop_queued_speech",
		"SynthDriver._feed_callback",
		"SynthDriver._finish_termination",
		"SynthDriver._guard_installed",
		"SynthDriver._idle_player",
		"SynthDriver._initialize_native",
		"SynthDriver._install_guard",
		"SynthDriver._install_guard.<locals>.restoration_errors",
		"SynthDriver._is_reentrant_termination",
		"SynthDriver._player_operation",
		"SynthDriver._real_player",
		"SynthDriver._record_valid",
		"SynthDriver._reset_callback_audio",
		"SynthDriver._retire_player_operation",
		"SynthDriver._retire_record",
		"SynthDriver._run_native",
		"SynthDriver._stop_player",
		"SynthDriver.get_segment_drain_support",
		"SynthDriver.get_segment_drain_support.<locals>.audio_mode",
		"SynthDriver.get_segment_drain_support.<locals>.nvda_version",
		"SynthDriver.speak_segment",
		"SynthDriver.speak_segment.<locals>.on_event",
		"_ContextualVECallback._process.<locals>.message_type",
		"_GuardedPlayer.__init__.<locals>.real_player",
		"_SilenceGate._inside_native_call",
		"_SilenceGate.is_set",
		"_SilenceGate.token_cancelled",
		"_strip_bytes_repr",
	},
	"synthDrivers/WorldVoice/ui/controls.py": {
		"apply_dependencies",
		"apply_dependencies.<locals>.control_of",
		"control_row",
		"control_value",
		"make_control",
		"read_control",
		"read_control.<locals>.driver_options",
	},
	"synthDrivers/WorldVoice/ui/panelLayout.py": {
		"choice_index",
		"choice_values",
		"controller_keys",
		"creation_followers",
		"creation_followers.<locals>.driver_id",
		"dependent_states",
		"driver_attribute",
		"from_display",
		"label_text",
		"panel_specs",
		"pipeline_attribute",
		"selected_value",
		"to_display",
		"voice_attribute",
	},
}

# The plugin contract, which phase 47c renames together with Neural (refactor9 §6.1).
TRANSITIONAL_47C: dict[str, set[str]] = {
	"synthDrivers/WorldVoice/bridge/voiceFacade.py": {
		"VoiceFacade.update_settings",
	},
	"synthDrivers/WorldVoice/driver/__init__.py": {
		"Voice.create_core",
		"Voice.destroy_core",
		"Voice.drain_profile",
		"Voice.extra_capabilities",
		"Voice.synth_driver_class",
	},
}


@dataclass(frozen=True)
class Definition:
	path: str
	qualname: str
	name: str
	kind: str  # class, function, parameter, field, variable or local
	line: int


def layer(path: str) -> str | None:
	"""core, host, pending or excluded for a module path relative to addon/; None when unknown."""
	if EXCLUDED.match(path):
		return "excluded"
	for name, prefixes in (("pending", PENDING), ("core", CORE), ("host", HOST)):
		if path.startswith(prefixes):
			return name
	return None


def follows_layer(definition: Definition, module_layer: str) -> bool:
	name = definition.name
	if name.startswith("__") and name.endswith("__") or not name.strip("_"):
		return True
	if definition.kind == "class":
		return bool(CAP_WORDS.fullmatch(name))
	if definition.kind in ("field", "variable") and (UPPER_CASE.fullmatch(name) or CAP_WORDS.fullmatch(name)):
		return True
	return bool((SNAKE_CASE if module_layer == "core" else MIXED_CASE).fullmatch(name))


def _module_name(path: str) -> str:
	parts = path.removesuffix(".py").split("/")
	return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _arguments(arguments: ast.arguments) -> list[ast.arg]:
	extra = [arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None]
	return [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs, *extra]


def _self_fields(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[ast.Attribute]:
	"""The attributes a method sets on its first parameter (self, or cls in a class method)."""
	arguments = node.args.posonlyargs + node.args.args
	if not arguments or any(getattr(item, "id", None) == "staticmethod" for item in node.decorator_list):
		return
	for target in ast.walk(node):
		if (
			isinstance(target, ast.Attribute)
			and isinstance(target.ctx, ast.Store)
			and isinstance(target.value, ast.Name)
			and target.value.id == arguments[0].arg
		):
			yield target


def _class_members(node: ast.ClassDef) -> set[str]:
	"""The method and field names a class defines itself."""
	members = set()
	pending = list(node.body)
	while pending:
		item = pending.pop()
		if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
			members.add(item.name)
			members |= {target.attr for target in _self_fields(item)}
		elif isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store):
			members.add(item.id)
		elif not isinstance(item, ast.ClassDef):
			pending += ast.iter_child_nodes(item)
	return members


class _Module:
	"""One parsed module: what its imported names refer to, and its top-level classes."""

	def __init__(self, path: str, source: str):
		self.path = path
		self.tree = ast.parse(source)
		package = _module_name(path).split(".")
		if not path.endswith("/__init__.py"):
			package = package[:-1]
		# name -> (module, attribute), attribute None for an imported module.
		self.imports: dict[str, tuple[str, str | None]] = {}
		for node in ast.walk(self.tree):
			if isinstance(node, ast.ImportFrom):
				source_module = node.module or ""
				if node.level:
					parent = package[: len(package) - node.level + 1]
					source_module = ".".join([*parent, *filter(None, [node.module])])
				for alias in node.names:
					self.imports[alias.asname or alias.name] = (source_module, alias.name)
			elif isinstance(node, ast.Import):
				for alias in node.names:
					bound = alias.asname or alias.name.partition(".")[0]
					self.imports[bound] = (alias.name if alias.asname else bound, None)
		self.classes = {node.name: node for node in self.tree.body if isinstance(node, ast.ClassDef)}


class _Index:
	"""Modules by dotted name, to read the base classes that a checked class names."""

	def __init__(self, sources: dict[str, str]):
		self.modules = {_module_name(path): _Module(path, source) for path, source in sources.items()}
		self._owners = {
			id(node): module for module in self.modules.values() for node in module.classes.values()
		}

	@classmethod
	def of_addon(cls) -> "_Index":
		files = sorted(ADDON.rglob("*.py"))
		return cls({file.relative_to(ADDON).as_posix(): file.read_text(encoding="utf-8") for file in files})

	def _lookup(self, module_name: str, name: str, depth: int = 0) -> ast.ClassDef | None:
		"""The class module_name defines or imports as name, following re-exports."""
		module = self.modules.get(module_name)
		if module is None or depth > 5:
			return None
		if name in module.classes:
			return module.classes[name]
		source, attribute = module.imports.get(name, ("", None))
		return None if attribute is None else self._lookup(source, attribute, depth + 1)

	def _resolve(self, module: _Module, base: ast.expr, line: int) -> ast.ClassDef | None:
		"""The class base names in a class statement at line of module (class X(X) names the import)."""
		if isinstance(base, ast.Subscript):
			base = base.value
		if isinstance(base, ast.Name):
			if base.id in module.classes and module.classes[base.id].lineno < line:
				return module.classes[base.id]
			source, attribute = module.imports.get(base.id, ("", None))
			return None if attribute is None else self._lookup(source, attribute)
		if (
			isinstance(base, ast.Attribute)
			and isinstance(base.value, ast.Name)
			and base.value.id in module.imports
		):
			source, attribute = module.imports[base.value.id]
			return self._lookup(source if attribute is None else f"{source}.{attribute}", base.attr)
		return None

	def inherited(self, module: _Module, node: ast.ClassDef) -> frozenset[str]:
		"""The member names of every base class of node that the index can read, transitively."""
		names: set[str] = set()
		pending = [(module, base, node.lineno) for base in node.bases]
		seen = set()
		while pending:
			owner, base, line = pending.pop()
			found = self._resolve(owner, base, line)
			if found is None or id(found) in seen:
				continue
			seen.add(id(found))
			names |= _class_members(found)
			pending += [(self._owners[id(found)], parent, found.lineno) for parent in found.bases]
		return frozenset(names)


class _Walker:
	"""Each name one module binds, with whether a base class of its class defines it (rule 2)."""

	def __init__(self, index: _Index, module: _Module):
		self.index = index
		self.module = module
		self.found: list[tuple[Definition, bool]] = []
		self.body(module.tree.body, "", "variable", frozenset(), frozenset())

	def add(self, scope: str, name: str, kind: str, line: int, overrides: bool = False) -> None:
		self.found.append((Definition(self.module.path, scope + name, name, kind, line), overrides))

	def body(self, nodes, scope, kind, inherited, declared_global):
		for node in nodes:
			self.visit(node, scope, kind, inherited, declared_global)

	def visit(self, node, scope, kind, inherited, declared_global):
		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
			self.function(node, scope, kind == "field", inherited)
			return
		if isinstance(node, ast.ClassDef):
			self.add(scope, node.name, "class", node.lineno)
			self.body(
				node.body,
				f"{scope}{node.name}.",
				"field",
				self.index.inherited(self.module, node),
				frozenset(),
			)
			return
		if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
			if node.id in declared_global:
				self.add("", node.id, "variable", node.lineno)
			else:
				self.add(scope, node.id, kind, node.lineno, node.id in inherited)
		elif isinstance(node, ast.ExceptHandler) and node.name:
			self.add(scope, node.name, kind, node.lineno)
		elif isinstance(node, ast.Lambda):
			for argument in _arguments(node.args):
				self.add(scope, argument.arg, "parameter", argument.lineno)
		for child in ast.iter_child_nodes(node):
			self.visit(child, scope, kind, inherited, declared_global)

	def function(self, node, scope, is_method, inherited):
		overrides = is_method and node.name in inherited
		self.add(scope, node.name, "function", node.lineno, overrides)
		inner = f"{scope}{node.name}.<locals>."
		for argument in _arguments(node.args):
			self.add(inner, argument.arg, "parameter", argument.lineno, overrides)
		declared = frozenset(
			name for child in ast.walk(node) if isinstance(child, ast.Global) for name in child.names
		)
		self.body(node.body, inner, "local", frozenset(), declared)
		if is_method:
			for target in _self_fields(node):
				self.add(scope, target.attr, "field", target.lineno, target.attr in inherited)


def violations(index: _Index) -> dict[tuple[str, str], Definition]:
	"""The definitions in checked modules that break their layer's style and override nothing."""
	found = {}
	for module in index.modules.values():
		module_layer = layer(module.path)
		if module_layer not in ("core", "host"):
			continue
		for definition, overrides in _Walker(index, module).found:
			if not overrides and not follows_layer(definition, module_layer):
				found.setdefault((definition.path, definition.qualname), definition)
	return found


def _listed(*tables: dict) -> set[tuple[str, str]]:
	return {(path, name) for table in tables for path, names in table.items() for name in names}


@pytest.fixture(scope="module")
def addon_violations():
	return violations(_Index.of_addon())


def test_every_add_on_module_has_a_layer():
	paths = sorted(file.relative_to(ADDON).as_posix() for file in ADDON.rglob("*.py"))
	assert [path for path in paths if layer(path) is None] == []


def test_naming_follows_layer(addon_violations):
	listed = _listed(INTERFACE_NAMES, TRANSITIONAL_47A, TRANSITIONAL_47B, TRANSITIONAL_47C)
	assert [
		f"{definition.path}:{definition.line} {definition.qualname}"
		for key, definition in sorted(addon_violations.items())
		if key not in listed
	] == []


def test_lists_hold_only_names_that_break_the_rule(addon_violations):
	# A renamed or removed name must leave the lists, so they only shrink.
	listed = _listed(INTERFACE_NAMES, TRANSITIONAL_47A, TRANSITIONAL_47B, TRANSITIONAL_47C)
	assert sorted(listed - set(addon_violations)) == []


def test_only_the_host_layer_waits_for_a_rename():
	assert [path for path in TRANSITIONAL_47B if layer(path) != "host"] == []
	assert sorted(TRANSITIONAL_47C) == [SYNTH + "bridge/voiceFacade.py", SYNTH + "driver/__init__.py"]


def test_no_module_imports_typing_override():
	# typing.override is new in Python 3.12, and NVDA runs Python 3.11 before 2026.1
	# (ref/nvda/user_docs/en/changes.md, 2026.1: "NVDA is now built with Python 3.13"). While the
	# add-on supports an older NVDA, the import would stop the synth from loading there.
	build_vars = (ROOT / "buildVars.py").read_text(encoding="utf-8")
	minimum = re.search(r'addon_minimumNVDAVersion="(\d+)\.(\d+)', build_vars)
	assert minimum
	if (int(minimum.group(1)), int(minimum.group(2))) >= (2026, 1):
		pytest.skip("the minimum NVDA version runs Python 3.13")
	importers = []
	for file in sorted(ADDON.rglob("*.py")):
		path = file.relative_to(ADDON).as_posix()
		if layer(path) == "excluded":
			continue
		for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
			if (
				isinstance(node, ast.ImportFrom)
				and node.module in ("typing", "typing_extensions")
				and any(alias.name == "override" for alias in node.names)
			):
				importers.append(f"{path}:{node.lineno}")
	assert importers == []


CORE_MODULE = SYNTH + "voices/example.py"
HOST_MODULE = SYNTH + "bridge/example.py"


@pytest.mark.parametrize(
	("path", "source", "expected"),
	[
		(CORE_MODULE, "def getVoice():\n\tpass\n", ["getVoice"]),
		(CORE_MODULE, "def get_voice(voiceName):\n\tpass\n", ["get_voice.<locals>.voiceName"]),
		(CORE_MODULE, "class Spec:\n\tvoiceName: str\n", ["Spec.voiceName"]),
		(CORE_MODULE, "class Spec:\n\tdef __init__(self):\n\t\tself.voiceName = 1\n", ["Spec.voiceName"]),
		(CORE_MODULE, "def run():\n\tfor voiceName in ():\n\t\tpass\n", ["run.<locals>.voiceName"]),
		(CORE_MODULE, "speak = lambda speechSequence: None\n", ["speechSequence"]),
		(
			CORE_MODULE,
			"MAX_RATE = 1\nVoiceKey = str\n\n\nclass VoiceSpec:\n\tdef __repr__(self):\n\t\tpass\n",
			[],
		),
		(HOST_MODULE, "def get_voice():\n\tpass\n", ["get_voice"]),
		(HOST_MODULE, "class Panel:\n\tdef _get_rateBoost(self):\n\t\tpass\n", []),
		(HOST_MODULE, "class Plugin:\n\tdef script_toggle(self, gesture):\n\t\tpass\n", []),
		(
			HOST_MODULE,
			"import wx\n\n\nclass Panel(wx.Panel):\n\tdef Destroy(self):\n\t\tpass\n",
			["Panel.Destroy"],
		),
	],
)
def test_the_guard_reads_each_kind_of_name(path, source, expected):
	assert [qualname for _path, qualname in violations(_Index({path: source}))] == expected


def test_the_guard_lets_an_override_keep_the_base_name():
	sources = {
		SYNTH
		+ "runtime/port.py": "class Port:\n\tdef speak_segment(self, segment_id):\n\t\tself.last_id = 0\n",
		HOST_MODULE: (
			"from ..runtime.port import Port\n\n\n"
			"class Adapter(Port):\n"
			"\tdef speak_segment(self, segment_id):\n\t\tself.last_id = segment_id\n\n"
			"\tdef own_name(self):\n\t\tpass\n"
		),
	}
	assert [qualname for _path, qualname in violations(_Index(sources))] == ["Adapter.own_name"]


def test_the_guard_reads_the_imported_base_of_a_class_with_its_name():
	# class SynthDriver(SynthDriver) derives from the imported class, not from itself.
	source = (
		"from synthDriverHandler import SynthDriver\n\n\n"
		"class SynthDriver(SynthDriver):\n"
		"\tdef own_name(self):\n\t\tpass\n"
	)
	found = violations(_Index({HOST_MODULE: source}))
	assert [qualname for _path, qualname in found] == ["SynthDriver.own_name"]
```

- [ ] **Step 2: Run the guard**

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | tail -1
```

Expected: `18 passed`.

- [ ] **Step 3: Probe (not committed): a new camelCase core name fails the guard**

```bash
printf '\n\ndef badName():\n\treturn None\n' >> addon/synthDrivers/WorldVoice/locales.py
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | grep -E "Left contains|passed|failed"
git checkout -- addon/synthDrivers/WorldVoice/locales.py
git status --short
```

Expected: `E      Left contains one more item: 'synthDrivers/WorldVoice/locales.py:18 badName'` and `1 failed, 17 passed`; afterwards `git status --short` shows only `?? tests/test_naming_layers.py`.

- [ ] **Step 4: Run the suite and commit**

```bash
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
```

Expected: `3287 passed` (3269 + 18).

```bash
git add tests/test_naming_layers.py
git diff --cached --stat | tail -1
git commit -q -m "test: guard that names follow their layer" -m "refactor9 §6.1 styles names by the layer of their module: snake_case in the portable core, NVDA mixedCase in the host layer. ruff has no pep8-naming rules enabled, so an AST test now classifies every add-on module, reads every name it binds, and lets a name keep a base class's spelling when the base is an add-on class or an interface listed in INTERFACE_NAMES. Today's exceptions are listed per phase: the core names 47a renames next, the host layer for 47b and the plugin contract for 47c."
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: the stat line `1 file changed, 911 insertions(+)`; every hook Passed (yaml Skipped); `git status --short` prints nothing.

Expected after the commit: `HEAD:addon` = `b62ed75314a91f666f195771ec025f77886d128c` (unchanged), `HEAD:tests` = `17cab13cf2c27e8ea9aa8b68b030ed6794236bac`

---

### Task 2: VoiceManager's private names, fields, parameters and locals

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voices/manager.py`, `addon/synthDrivers/WorldVoice/__init__.py:237`
- Test: `tests/test_naming_layers.py`, `tests/test_f4_voice_state.py`, `tests/test_role_presenter.py`, `tests/test_runtime_composition.py`, `tests/test_voice_manager_roles.py`, `tests/test_voice_settings_transaction.py`, `tests/test_worldvoice_lifecycle.py`, `tests/worldvoice_harness.py`
- Create (scratch, not committed): `$SCRATCH/phase47a_rename.py`, `$SCRATCH/phase47a_rename_check.py`

**Interfaces:**
- Consumes: Task 1's tree.
- Produces: `VoiceManager(task_manager, settings, bridge, *, …)` and its attribute `task_manager`; private `_instance_cache`, `_default_voice_instance`, `_get_default_voice_spec()`, `_create_voice_instance(voice_name)`, `_set_voice_datas()`, `_get_configured_voice_name_for_language(language)`; parameters `voice_name`, `base_instance`. The rename script (tasks `2`–`5`) and the token check, used by Tasks 2–5.

- [ ] **Step 1: Take the names off the core list and see the guard fail**

**Edit:** `tests/test_naming_layers.py` (1/4)

Replace:

```text
	"synthDrivers/WorldVoice/voices/manager.py": {
		"VoiceManager.__init__.<locals>.taskManager",
		"VoiceManager._createVoiceInstance",
		"VoiceManager._createVoiceInstance.<locals>.voiceInstance",
		"VoiceManager._createVoiceInstance.<locals>.voiceName",
		"VoiceManager._defaultVoiceInstance",
		"VoiceManager._getConfiguredVoiceNameForLanguage",
		"VoiceManager._getDefaultVoiceSpec",
		"VoiceManager._instanceCache",
		"VoiceManager._setVoiceDatas",
```

With:

```text
	"synthDrivers/WorldVoice/voices/manager.py": {
```

**Edit:** `tests/test_naming_layers.py` (2/4)

Replace:

```text
		"VoiceManager.getVoiceInstance",
		"VoiceManager.getVoiceInstance.<locals>.voiceName",
```

With:

```text
		"VoiceManager.getVoiceInstance",
```

**Edit:** `tests/test_naming_layers.py` (3/4)

Replace:

```text
		"VoiceManager.onVoiceParameterConsistent",
		"VoiceManager.onVoiceParameterConsistent.<locals>.baseInstance",
```

With:

```text
		"VoiceManager.onVoiceParameterConsistent",
```

**Edit:** `tests/test_naming_layers.py` (4/4)

Replace:

```text
		"VoiceManager.previewVoiceParameterConsistent",
		"VoiceManager.previewVoiceParameterConsistent.<locals>.baseInstance",
		"VoiceManager.taskManager",
```

With:

```text
		"VoiceManager.previewVoiceParameterConsistent",
```

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | grep -E "Left contains|passed|failed"
```

Expected: `E      Left contains 13 more items, first extra item: 'synthDrivers/WorldVoice/voices/manager.py:37 VoiceManager.__init__.<locals>.taskManager'` and `1 failed, 17 passed`.

- [ ] **Step 2: Write the rename script and the token check, and rename**

**File:** `$SCRATCH/phase47a_rename.py`

```python
"""Phase 47a renames: every whole-word occurrence of each listed name in each listed file.

Usage (from the repository root): python3 phase47a_rename.py TASK
Each new name is snake(old). A listed name missing from its file stops the script before it
writes anything, so a drifted base is noticed. Occurrences that must stay are not in these
lists; the plan edits around them with Edit blocks.
"""

import re
import sys
from pathlib import Path


def snake(name):
	lead = len(name) - len(name.lstrip("_"))
	return name[:lead] + re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name[lead:]).lower()


MANAGER = "addon/synthDrivers/WorldVoice/voices/manager.py"
PIPELINE = "addon/synthDrivers/WorldVoice/pipeline/"
PUBLIC = (
	"getVoiceSpec",
	"getVoiceCapabilities",
	"getVoiceVariants",
	"beginVoiceSettingsEdit",
	"defaultVoiceInstance",
	"defaultVoiceName",
	"getVoiceInstance",
	"previewVoiceParameterConsistent",
	"onVoiceParameterConsistent",
	"onKeepEngineConsistent",
	"onKeepMainLocaleVoiceConsistent",
	"voiceInfos",
	"allLanguages",
	"localeToVoicesMap",
	"localesToNamesMap",
	"getVoiceNameForLanguage",
	"getVoiceLocaleForLanguage",
)
TASKS = {
	"2": {
		MANAGER: (
			"taskManager",
			"_instanceCache",
			"_defaultVoiceInstance",
			"_getDefaultVoiceSpec",
			"_createVoiceInstance",
			"_setVoiceDatas",
			"_getConfiguredVoiceNameForLanguage",
			"voiceName",
			"baseInstance",
			"voiceInstance",
		),
		"tests/test_f4_voice_state.py": ("_instanceCache",),
		"tests/test_role_presenter.py": ("_instanceCache", "_defaultVoiceInstance"),
		"tests/test_runtime_composition.py": ("_setVoiceDatas",),
		"tests/test_voice_manager_roles.py": ("_defaultVoiceInstance",),
		"tests/test_voice_settings_transaction.py": ("_instanceCache", "_defaultVoiceInstance"),
		"tests/test_worldvoice_lifecycle.py": ("taskManager", "_instanceCache"),
		"tests/worldvoice_harness.py": ("_instanceCache",),
	},
	"3": {
		MANAGER: PUBLIC,
		"addon/synthDrivers/WorldVoice/__init__.py": (
			"getVoiceCapabilities",
			"defaultVoiceName",
			"allLanguages",
			"defaultVoiceInstance",
			"getVoiceNameForLanguage",
			"getVoiceLocaleForLanguage",
			"onVoiceParameterConsistent",
			"voiceInfos",
			"getVoiceVariants",
		),
		"addon/globalPlugins/WorldVoice/rolePresenter.py": (
			"beginVoiceSettingsEdit",
			"localesToNamesMap",
			"localeToVoicesMap",
			"getVoiceInstance",
			"getVoiceCapabilities",
			"getVoiceVariants",
			"defaultVoiceInstance",
			"previewVoiceParameterConsistent",
			"defaultVoiceName",
		),
		"addon/globalPlugins/WorldVoice/panels/detection.py": ("localesToNamesMap",),
		"tests/test_f4_voice_state.py": ("previewVoiceParameterConsistent",),
		"tests/test_pipeline_stages.py": ("getVoiceNameForLanguage",),
		"tests/test_pipeline_voice_lookup.py": (
			"defaultVoiceInstance",
			"getVoiceNameForLanguage",
			"getVoiceSpec",
			"getVoiceLocaleForLanguage",
			"defaultVoiceName",
		),
		"tests/test_plugin_voice_contract.py": ("getVoiceInstance", "getVoiceVariants"),
		"tests/test_role_presenter.py": (
			"getVoiceInstance",
			"defaultVoiceName",
			"getVoiceCapabilities",
			"getVoiceVariants",
		),
		"tests/test_runtime_composition.py": (
			"defaultVoiceName",
			"getVoiceInstance",
			"voiceInfos",
			"getVoiceCapabilities",
			"getVoiceVariants",
			"defaultVoiceInstance",
		),
		"tests/test_settings_order.py": ("defaultVoiceName", "getVoiceCapabilities"),
		"tests/test_unicode_panel.py": ("localesToNamesMap",),
		"tests/test_voice_manager_roles.py": (
			"localeToVoicesMap",
			"localesToNamesMap",
			"onKeepEngineConsistent",
			"onKeepMainLocaleVoiceConsistent",
			"getVoiceNameForLanguage",
		),
		"tests/test_voice_settings_transaction.py": (
			"getVoiceInstance",
			"getVoiceCapabilities",
			"getVoiceVariants",
			"defaultVoiceName",
		),
		"tests/test_worldvoice_lifecycle.py": ("allLanguages",),
		"tests/test_worldvoice_pipeline_settings.py": (
			"defaultVoiceName",
			"getVoiceCapabilities",
			"defaultVoiceInstance",
			"onVoiceParameterConsistent",
			"getVoiceNameForLanguage",
			"getVoiceLocaleForLanguage",
		),
		"tests/test_worldvoice_speak.py": (
			"defaultVoiceName",
			"defaultVoiceInstance",
			"allLanguages",
			"getVoiceNameForLanguage",
			"getVoiceLocaleForLanguage",
		),
	},
	"4": {
		PIPELINE + module: ("speechSequence",)
		for module in (
			"breaks.py",
			"items.py",
			"languageCommands.py",
			"numberStages.py",
			"punctuation.py",
			"registry.py",
			"unspaced.py",
		)
	},
	"5": {
		"addon/synthDrivers/WorldVoice/languageDetection/detector.py": (
			"availableLanguages",
			"speechSequence",
			"defaultLang",
			"curLang",
			"tmpLang",
			"targetLang",
		),
	},
}


def main():
	renamed = {}
	for path, names in TASKS[sys.argv[1]].items():
		text = Path(path).read_text(encoding="utf-8")
		for name in names:
			pattern = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")
			if not pattern.search(text):
				sys.exit(f"{path}: {name} not found")
			text = pattern.sub(snake(name), text)
		renamed[path] = text
	for path, text in renamed.items():
		Path(path).write_text(text, encoding="utf-8", newline="\n")
		print(f"renamed {path}")


main()
```

**File:** `$SCRATCH/phase47a_rename_check.py`

```python
"""Check that HEAD differs from REV only by renaming NAMES to snake_case, token by token in order.

Usage (from the repository root): python3 phase47a_rename_check.py REV NAME...
tests/test_naming_layers.py, whose lists the tasks edit, is left out. A name, comment or string token
of HEAD must equal REV's token or REV's token with NAMES renamed; ruff's line breaks and trailing
commas are ignored.
"""

import io
import re
import subprocess
import sys
import tokenize

rev, *names = sys.argv[1:]


def snake(name):
	lead = len(name) - len(name.lstrip("_"))
	return name[:lead] + re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name[lead:]).lower()


pattern = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, names)) + r")(?!\w)")


def tokens(source):
	found = [
		(token.type, token.string)
		for token in tokenize.generate_tokens(io.StringIO(source).readline)
		if token.type != tokenize.NL
	]
	return [
		token
		for index, token in enumerate(found)
		if not (token == (tokenize.OP, ",") and index + 1 < len(found) and found[index + 1][1] in ")]}")
	]


def git(*args):
	return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


paths = [p for p in git("diff", "--name-only", rev, "HEAD").split() if p != "tests/test_naming_layers.py"]
renamed = 0
for path in paths:
	old, new = tokens(git("show", f"{rev}:{path}")), tokens(git("show", f"HEAD:{path}"))
	if len(old) != len(new):
		sys.exit(f"{path}: {len(old)} tokens before, {len(new)} after")
	for before, after in zip(old, new, strict=True):
		if before == after:
			continue
		allowed = pattern.sub(lambda match: snake(match.group(1)), before[1])
		if before[0] != after[0] or after[1] != allowed:
			sys.exit(f"{path}: {before[1]!r} became {after[1]!r}")
		renamed += 1
print(f"pure rename: OK ({len(paths)} files, {renamed} tokens renamed)")
```

```bash
python3 $SCRATCH/phase47a_rename.py 2
```

Expected: eight `renamed …` lines, for `voices/manager.py` and the seven test files of the list.

The synth's own `self.taskManager` stays (a host name for 47b); only the keyword it passes to the manager changes:

**Edit:** `addon/synthDrivers/WorldVoice/__init__.py`

Replace:

```text
					taskManager=self.taskManager,
```

With:

```text
					task_manager=self.taskManager,
```

- [ ] **Step 3: Check, run the suite and commit**

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | tail -1
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
```

Expected: `18 passed`; then `3287 passed`.

```bash
git add addon/synthDrivers/WorldVoice/__init__.py addon/synthDrivers/WorldVoice/voices/manager.py tests/test_f4_voice_state.py tests/test_naming_layers.py tests/test_role_presenter.py tests/test_runtime_composition.py tests/test_voice_manager_roles.py tests/test_voice_settings_transaction.py tests/test_worldvoice_lifecycle.py tests/worldvoice_harness.py
git diff --cached --stat | tail -1
git commit -q -m "refactor: snake_case VoiceManager's private names and parameters" -m "voices/ is portable core (refactor9 §6.1), so VoiceManager's own names follow PEP 8. This commit renames what only the manager and its tests touch: the task_manager parameter and attribute, the private helpers and fields, and the parameters and locals of its methods. The synth passes task_manager= when it builds the manager. No compatibility aliases: VoiceManager is not a plugin path (refactor9 §5.3)."
git status --short
git rev-parse HEAD:addon HEAD:tests
python3 $SCRATCH/phase47a_rename_check.py HEAD~1 taskManager _instanceCache _defaultVoiceInstance _getDefaultVoiceSpec _createVoiceInstance _setVoiceDatas _getConfiguredVoiceNameForLanguage voiceName baseInstance voiceInstance
```

Expected: the stat line `10 files changed, 45 insertions(+), 58 deletions(-)`; every hook Passed (yaml Skipped); `git status --short` prints nothing; `pure rename: OK (9 files, 52 tokens renamed)`.

Expected after the commit: `HEAD:addon` = `a7cc208014ce62ba5bdfe53db48ae3805575795a`, `HEAD:tests` = `f17006939e07a434e097f1b1b77b85847fe5d0d2`

---

### Task 3: VoiceManager's public names and their callers

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voices/manager.py`, `addon/synthDrivers/WorldVoice/__init__.py`, `addon/globalPlugins/WorldVoice/rolePresenter.py`, `addon/globalPlugins/WorldVoice/panels/detection.py:29`
- Test: `tests/test_naming_layers.py`, `tests/test_f4_voice_state.py`, `tests/test_pipeline_stages.py`, `tests/test_pipeline_voice_lookup.py`, `tests/test_plugin_voice_contract.py`, `tests/test_role_presenter.py`, `tests/test_runtime_composition.py`, `tests/test_settings_order.py`, `tests/test_unicode_panel.py`, `tests/test_voice_manager_roles.py`, `tests/test_voice_settings_transaction.py`, `tests/test_worldvoice_lifecycle.py`, `tests/test_worldvoice_pipeline_settings.py`, `tests/test_worldvoice_speak.py`

**Interfaces:**
- Consumes: Task 2's tree; `$SCRATCH/phase47a_rename.py` task `3`.
- Produces: `VoiceManager.get_voice_spec(key)`, `get_voice_capabilities(key)`, `get_voice_variants(key)`, `begin_voice_settings_edit()`, `default_voice_instance`, `default_voice_name` (property with setter), `get_voice_instance(voice_name)`, `preview_voice_parameter_consistent(base_instance)`, `on_voice_parameter_consistent(base_instance)`, `on_keep_engine_consistent()`, `on_keep_main_locale_voice_consistent()`, `voice_infos`, `all_languages`, `locale_to_voices_map`, `locales_to_names_map`, `get_voice_name_for_language(language)`, `get_voice_locale_for_language(language)`.

- [ ] **Step 1: Take the names off the core list and see the guard fail**

**Edit:** `tests/test_naming_layers.py`

Replace:

```text
		"LeasedPlayer._feed_admitted.<locals>.onDone",
	},
	"synthDrivers/WorldVoice/voices/manager.py": {
		"VoiceManager.allLanguages",
		"VoiceManager.beginVoiceSettingsEdit",
		"VoiceManager.defaultVoiceInstance",
		"VoiceManager.defaultVoiceName",
		"VoiceManager.getVoiceCapabilities",
		"VoiceManager.getVoiceInstance",
		"VoiceManager.getVoiceLocaleForLanguage",
		"VoiceManager.getVoiceNameForLanguage",
		"VoiceManager.getVoiceSpec",
		"VoiceManager.getVoiceVariants",
		"VoiceManager.localeToVoicesMap",
		"VoiceManager.localesToNamesMap",
		"VoiceManager.onKeepEngineConsistent",
		"VoiceManager.onKeepMainLocaleVoiceConsistent",
		"VoiceManager.onVoiceParameterConsistent",
		"VoiceManager.previewVoiceParameterConsistent",
		"VoiceManager.voiceInfos",
```

With:

```text
		"LeasedPlayer._feed_admitted.<locals>.onDone",
```

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | grep -E "Left contains|passed|failed"
```

Expected: `E      Left contains 17 more items, first extra item: 'synthDrivers/WorldVoice/voices/manager.py:277 VoiceManager.allLanguages'` and `1 failed, 17 passed`.

- [ ] **Step 2: Rename**

```bash
python3 $SCRATCH/phase47a_rename.py 3
```

Expected: seventeen `renamed …` lines: `voices/manager.py`, the synth's `__init__.py`, `rolePresenter.py`, `panels/detection.py` and thirteen test files. The script leaves alone every file that uses the VE/Cerence core's own `getVoiceInstance`, `_instanceCache` or `getVoiceNameForLanguage` (spec §5).

The longer name makes one test line too long; this is ruff's wrapping of it, with add-trailing-comma's comma:

**Edit:** `tests/test_role_presenter.py`

Replace:

```text
	env.manager.get_voice_capabilities = lambda key: types.SimpleNamespace(settings={"rateBoost", "inflection"})
```

With:

```text
	env.manager.get_voice_capabilities = lambda key: types.SimpleNamespace(
		settings={"rateBoost", "inflection"},
	)
```

- [ ] **Step 3: Check, run the suite and commit**

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | tail -1
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
```

Expected: `18 passed`; then `3287 passed`.

```bash
git add addon/globalPlugins/WorldVoice/panels/detection.py addon/globalPlugins/WorldVoice/rolePresenter.py addon/synthDrivers/WorldVoice/__init__.py addon/synthDrivers/WorldVoice/voices/manager.py tests/test_f4_voice_state.py tests/test_naming_layers.py tests/test_pipeline_stages.py tests/test_pipeline_voice_lookup.py tests/test_plugin_voice_contract.py tests/test_role_presenter.py tests/test_runtime_composition.py tests/test_settings_order.py tests/test_unicode_panel.py tests/test_voice_manager_roles.py tests/test_voice_settings_transaction.py tests/test_worldvoice_lifecycle.py tests/test_worldvoice_pipeline_settings.py tests/test_worldvoice_speak.py
git diff --cached --stat | tail -1
git commit -q -m "refactor: snake_case VoiceManager's public names" -m "The rest of VoiceManager's camelCase API becomes PEP 8 snake_case (refactor9 §6.1): get_voice_instance, default_voice_name, default_voice_instance, locale_to_voices_map, get_voice_name_for_language and the others. The synth driver, the role presenter, the Unicode detection panel and the tests call the new names; each new name is the old one in snake_case. No compatibility aliases (refactor9 §5.3): the manager is reached only through the synth, never by plugins."
git status --short
git rev-parse HEAD:addon HEAD:tests
python3 $SCRATCH/phase47a_rename_check.py HEAD~1 getVoiceSpec getVoiceCapabilities getVoiceVariants beginVoiceSettingsEdit defaultVoiceInstance defaultVoiceName getVoiceInstance previewVoiceParameterConsistent onVoiceParameterConsistent onKeepEngineConsistent onKeepMainLocaleVoiceConsistent voiceInfos allLanguages localeToVoicesMap localesToNamesMap getVoiceNameForLanguage getVoiceLocaleForLanguage
```

Expected: the stat line `18 files changed, 152 insertions(+), 169 deletions(-)`; every hook Passed (yaml Skipped); `git status --short` prints nothing; `pure rename: OK (17 files, 156 tokens renamed)`.

Expected after the commit: `HEAD:addon` = `4ad1d3418b60e3560778e2e0be30ca214dcf8da6`, `HEAD:tests` = `80037caeb14a1ee0cfbcfd0bae31413104ed3804`

---

### Task 4: The pipeline stages' `speech_sequence` parameter

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/{breaks,items,languageCommands,numberStages,punctuation,registry,unspaced}.py`
- Test: `tests/test_naming_layers.py`

**Interfaces:**
- Consumes: Task 3's tree; `$SCRATCH/phase47a_rename.py` task `4`.
- Produces: every stage `fn(speech_sequence, settings, ctx)` and helper with `speech_sequence` in place of `speechSequence`; `registry.listable(func)`'s wrapper and `_stage_handler`'s handler take `speech_sequence` (NVDA passes it positionally).

- [ ] **Step 1: Take the names off the core list and see the guard fail**

**Edit:** `tests/test_naming_layers.py` (1/2)

Replace:

```text
	},
	"synthDrivers/WorldVoice/pipeline/breaks.py": {
		"_merge_edge_breaks.<locals>.speechSequence",
		"_plain_breaks.<locals>.speechSequence",
	},
	"synthDrivers/WorldVoice/pipeline/items.py": {
		"_insert_item_breaks.<locals>.speechSequence",
		"item_wait_factor.<locals>.speechSequence",
	},
	"synthDrivers/WorldVoice/pipeline/languageCommands.py": {
		"deduplicate_language_command.<locals>.speechSequence",
		"inject_langchange_reorder.<locals>.speechSequence",
		"lang_cmd_to_voice.<locals>.speechSequence",
		"remove_language_command.<locals>.speechSequence",
	},
	"synthDrivers/WorldVoice/pipeline/numberStages.py": {
		"_inject_item_numbers.<locals>.speechSequence",
		"_insert_number_breaks.<locals>.speechSequence",
		"_remove_space.<locals>.speechSequence",
		"_split_numbers.<locals>.speechSequence",
		"_spoken_later.<locals>.speechSequence",
		"detect_with_number_language.<locals>.speechSequence",
		"inject_numbers.<locals>.speechSequence",
		"number_wait_factor.<locals>.speechSequence",
		"remove_thousands_separators.<locals>.speechSequence",
		"wrap_numbers_for_detection.<locals>.speechSequence",
	},
	"synthDrivers/WorldVoice/pipeline/punctuation.py": {
		"_punctuation_pauses.<locals>.speechSequence",
		"inject_punctuation_pause.<locals>.speechSequence",
	},
	"synthDrivers/WorldVoice/pipeline/registry.py": {
		"_run_logged.<locals>.speechSequence",
		"_stage_handler.<locals>.handler.<locals>.speechSequence",
		"apply_speech_dictionaries.<locals>.speechSequence",
		"listable.<locals>.wrapper.<locals>.speechSequence",
		"speech_viewer.<locals>.speechSequence",
	},
```

With:

```text
	},
```

**Edit:** `tests/test_naming_layers.py` (2/2)

Replace:

```text
		"_wrap_get_text_info_speech_with_sayall_break.<locals>.getTextInfoSpeechWithSayAllBreak.<locals>.waitFactor",
	},
	"synthDrivers/WorldVoice/pipeline/unspaced.py": {
		"inject_unspaced_script_space_pause.<locals>.speechSequence",
```

With:

```text
		"_wrap_get_text_info_speech_with_sayall_break.<locals>.getTextInfoSpeechWithSayAllBreak.<locals>.waitFactor",
```

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | grep -E "Left contains|passed|failed"
```

Expected: `E      Left contains 26 more items, first extra item: 'synthDrivers/WorldVoice/pipeline/breaks.py:52 _merge_edge_breaks.<locals>.speechSequence'` and `1 failed, 17 passed`.

- [ ] **Step 2: Rename**

```bash
python3 $SCRATCH/phase47a_rename.py 4
```

Expected: seven `renamed …` lines, one per pipeline module.

The longer name makes one call in `inject_numbers` too long; this is ruff's wrapping of it, with add-trailing-comma's comma:

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/numberStages.py`

Replace:

```text
		yield from _merge_edge_breaks(_inject_item_numbers(list(speech_sequence), settings, ctx, wraps, edges))
```

With:

```text
		yield from _merge_edge_breaks(
			_inject_item_numbers(list(speech_sequence), settings, ctx, wraps, edges),
		)
```

- [ ] **Step 3: Check, run the suite and commit**

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | tail -1
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
```

Expected: `18 passed`; then `3287 passed`.

```bash
git add addon/synthDrivers/WorldVoice/pipeline/breaks.py addon/synthDrivers/WorldVoice/pipeline/items.py addon/synthDrivers/WorldVoice/pipeline/languageCommands.py addon/synthDrivers/WorldVoice/pipeline/numberStages.py addon/synthDrivers/WorldVoice/pipeline/punctuation.py addon/synthDrivers/WorldVoice/pipeline/registry.py addon/synthDrivers/WorldVoice/pipeline/unspaced.py tests/test_naming_layers.py
git diff --cached --stat | tail -1
git commit -q -m "refactor: snake_case the pipeline stages' speech_sequence parameter" -m "The pipeline is portable core (refactor9 §6.1), and its stages, the logged runner and the NVDA filter handler named their sequence parameter speechSequence. NVDA's Filter.apply passes the sequence positionally (ref/nvda/source/extensionPoints/__init__.py), and every caller passes it by position, so the rename changes no call."
git status --short
git rev-parse HEAD:addon HEAD:tests
python3 $SCRATCH/phase47a_rename_check.py HEAD~1 speechSequence
```

Expected: the stat line `8 files changed, 82 insertions(+), 120 deletions(-)`; every hook Passed (yaml Skipped); `git status --short` prints nothing; `pure rename: OK (7 files, 86 tokens renamed)`.

Expected after the commit: `HEAD:addon` = `c3f8e830470d829dd049221c415ee4ff00c50e15`, `HEAD:tests` = `a1b522eed864c146f13b1e21ed64af063ecd52a4`

---

### Task 5: LanguageDetector's own names

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/detector.py`
- Test: `tests/test_naming_layers.py`

**Interfaces:**
- Consumes: Task 4's tree; `$SCRATCH/phase47a_rename.py` task `5`.
- Produces: `LanguageDetector(available_languages, *, settings, language, number_language=…)`, attribute `available_languages`, `add_detected_language_commands(speech_sequence)`.

- [ ] **Step 1: Take the names off the core list and see the guard fail**

**Edit:** `tests/test_naming_layers.py`

Replace:

```text
TRANSITIONAL_47A: dict[str, set[str]] = {
	"synthDrivers/WorldVoice/languageDetection/detector.py": {
		"LanguageDetector.__init__.<locals>.availableLanguages",
		"LanguageDetector.add_detected_language_commands.<locals>.curLang",
		"LanguageDetector.add_detected_language_commands.<locals>.defaultLang",
		"LanguageDetector.add_detected_language_commands.<locals>.speechSequence",
		"LanguageDetector.add_detected_language_commands.<locals>.targetLang",
		"LanguageDetector.add_detected_language_commands.<locals>.tmpLang",
		"LanguageDetector.availableLanguages",
	},
```

With:

```text
TRANSITIONAL_47A: dict[str, set[str]] = {
```

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | grep -E "Left contains|passed|failed"
```

Expected: `E      Left contains 7 more items, first extra item: 'synthDrivers/WorldVoice/languageDetection/detector.py:14 LanguageDetector.__init__.<locals>.availableLanguages'` and `1 failed, 17 passed`.

- [ ] **Step 2: Rename**

```bash
python3 $SCRATCH/phase47a_rename.py 5
```

Expected: `renamed addon/synthDrivers/WorldVoice/languageDetection/detector.py`.

- [ ] **Step 3: Check, run the suite and commit**

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | tail -1
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
```

Expected: `18 passed`; then `3287 passed`.

```bash
git add addon/synthDrivers/WorldVoice/languageDetection/detector.py tests/test_naming_layers.py
git diff --cached --stat | tail -1
git commit -q -m "refactor: snake_case LanguageDetector's own names" -m "languageDetection/ is portable core (refactor9 §6.1). The detector's available_languages parameter and attribute, its speech_sequence parameter and the locals of add_detected_language_commands become snake_case. Every caller passes the languages and the sequence by position, and nothing outside the detector reads the attribute."
git status --short
git rev-parse HEAD:addon HEAD:tests
python3 $SCRATCH/phase47a_rename_check.py HEAD~1 availableLanguages speechSequence defaultLang curLang tmpLang targetLang
```

Expected: the stat line `2 files changed, 17 insertions(+), 26 deletions(-)`; every hook Passed (yaml Skipped); `git status --short` prints nothing; `pure rename: OK (1 files, 26 tokens renamed)`.

Expected after the commit: `HEAD:addon` = `cff5438f1392c687545a208b839fd46e1fd7ca4d`, `HEAD:tests` = `fae672a0cdda6dc38ea61e97ee46e844e51c5cd0`

---

### Task 6: Say All's wrapper, LeasedPlayer's private hooks, and the end of the core list

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/sayAll.py:20-31`, `addon/synthDrivers/WorldVoice/runtime/segmentHost.py:667-692`
- Test: `tests/test_naming_layers.py`

**Interfaces:**
- Consumes: Task 5's tree.
- Produces: `sayAll._wrap_get_text_info_speech_with_sayall_break(get_text_info_speech)` returning `get_text_info_speech_with_say_all_break`; `LeasedPlayer._feed_admitted(record, data, size, on_done)` and `_callback(record, on_done)`; `LeasedPlayer.feed(data, size=None, onDone=None)` unchanged. `tests/test_naming_layers.py` without `TRANSITIONAL_47A`.

- [ ] **Step 1: Delete the core list and see the guard fail**

The last five core names go with the list itself and its two uses:

**Edit:** `tests/test_naming_layers.py` (1/3)

Replace:

```text


# Core names that phase 47a renames to snake_case; empty at the end of the phase.
TRANSITIONAL_47A: dict[str, set[str]] = {
	"synthDrivers/WorldVoice/pipeline/sayAll.py": {
		"_wrap_get_text_info_speech_with_sayall_break.<locals>.getTextInfoSpeech",
		"_wrap_get_text_info_speech_with_sayall_break.<locals>.getTextInfoSpeechWithSayAllBreak",
		"_wrap_get_text_info_speech_with_sayall_break.<locals>.getTextInfoSpeechWithSayAllBreak.<locals>.waitFactor",
	},
	"synthDrivers/WorldVoice/runtime/segmentHost.py": {
		"LeasedPlayer._callback.<locals>.onDone",
		"LeasedPlayer._feed_admitted.<locals>.onDone",
	},
}

# Host-layer names that phase 47b renames to mixedCase or marks as interface names.
```

With:

```text


# Host-layer names that phase 47b renames to mixedCase or marks as interface names.
```

**Edit:** `tests/test_naming_layers.py` (2/3)

Replace:

```text
	listed = _listed(INTERFACE_NAMES, TRANSITIONAL_47A, TRANSITIONAL_47B, TRANSITIONAL_47C)
	assert [
```

With:

```text
	listed = _listed(INTERFACE_NAMES, TRANSITIONAL_47B, TRANSITIONAL_47C)
	assert [
```

**Edit:** `tests/test_naming_layers.py` (3/3)

Replace:

```text
	listed = _listed(INTERFACE_NAMES, TRANSITIONAL_47A, TRANSITIONAL_47B, TRANSITIONAL_47C)
```

With:

```text
	listed = _listed(INTERFACE_NAMES, TRANSITIONAL_47B, TRANSITIONAL_47C)
```

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | grep -E "Left contains|passed|failed"
```

Expected: `E      Left contains 5 more items, first extra item: 'synthDrivers/WorldVoice/pipeline/sayAll.py:20 _wrap_get_text_info_speech_with_sayall_break.<locals>.getTextInfoSpeech'` and `1 failed, 17 passed`.

- [ ] **Step 2: Rename, sparing NVDA's names**

These are edits, not the script: `sayAll.py` keeps NVDA's `speech.speech.getTextInfoSpeech` (`:38`, `:47`) and the docstring that names it, and `segmentHost.py` keeps `feed`'s `onDone` (INTERFACE_NAMES) and the `onDone=` keyword it passes to NVDA's player.

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/sayAll.py` (1/4)

Replace:

```text
	getTextInfoSpeech: Callable[..., Iterable[SpeechSequence]],
```

With:

```text
	get_text_info_speech: Callable[..., Iterable[SpeechSequence]],
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/sayAll.py` (2/4)

Replace:

```text
	def getTextInfoSpeechWithSayAllBreak(*args, **kwargs):
		yield from getTextInfoSpeech(*args, **kwargs)
```

With:

```text
	def get_text_info_speech_with_say_all_break(*args, **kwargs):
		yield from get_text_info_speech(*args, **kwargs)
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/sayAll.py` (3/4)

Replace:

```text
		waitFactor = pipeline_settings.effective(current_context().supports_roles).scaled_sayall_wait()
		if waitFactor > 0:
			yield [BreakCommand(waitFactor + 100)]
```

With:

```text
		wait_factor = pipeline_settings.effective(current_context().supports_roles).scaled_sayall_wait()
		if wait_factor > 0:
			yield [BreakCommand(wait_factor + 100)]
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/sayAll.py` (4/4)

Replace:

```text
	return getTextInfoSpeechWithSayAllBreak
```

With:

```text
	return get_text_info_speech_with_say_all_break
```

**Edit:** `addon/synthDrivers/WorldVoice/runtime/segmentHost.py` (1/4)

Replace:

```text
	def _feed_admitted(self, record: NativeRecord, data, size, onDone):
```

With:

```text
	def _feed_admitted(self, record: NativeRecord, data, size, on_done):
```

**Edit:** `addon/synthDrivers/WorldVoice/runtime/segmentHost.py` (2/4)

Replace:

```text
		callback = None if onDone is None else self._callback(record, onDone)
```

With:

```text
		callback = None if on_done is None else self._callback(record, on_done)
```

**Edit:** `addon/synthDrivers/WorldVoice/runtime/segmentHost.py` (3/4)

Replace:

```text
	def _callback(self, record: NativeRecord, onDone: Callable[[], None]) -> Callable[[], None]:
```

With:

```text
	def _callback(self, record: NativeRecord, on_done: Callable[[], None]) -> Callable[[], None]:
```

**Edit:** `addon/synthDrivers/WorldVoice/runtime/segmentHost.py` (4/4)

Replace:

```text
						onDone()
```

With:

```text
						on_done()
```

- [ ] **Step 3: Check, run the suite and commit**

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | tail -1
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
```

Expected: `18 passed`; then `3287 passed`.

```bash
git add addon/synthDrivers/WorldVoice/pipeline/sayAll.py addon/synthDrivers/WorldVoice/runtime/segmentHost.py tests/test_naming_layers.py
git diff --cached --stat | tail -1
git commit -q -m "refactor: snake_case the last core names and close the core list" -m "Say All's wrapper and its getTextInfoSpeech parameter, and LeasedPlayer's private feed hooks, used camelCase in the portable core (refactor9 §6.1). LeasedPlayer.feed keeps onDone, the keyword of NVDA's WavePlayer.feed that wrappers call it with, as INTERFACE_NAMES records. The core now breaks the rule nowhere, so the guard's list for this phase goes away: only the host layer (47b) and the plugin contract (47c) still wait for a rename."
git status --short
git rev-parse HEAD:addon HEAD:tests
python3 $SCRATCH/phase47a_rename_check.py HEAD~1 getTextInfoSpeech getTextInfoSpeechWithSayAllBreak waitFactor onDone
```

Expected: the stat line `3 files changed, 13 insertions(+), 26 deletions(-)`; every hook Passed (yaml Skipped); `git status --short` prints nothing; `pure rename: OK (2 files, 12 tokens renamed)`.

Expected after the commit: `HEAD:addon` = `5e9cb1fbc5bff84d56ae3669a2fba3c316de6b47`, `HEAD:tests` = `9ebbdff74ed7505e7ea9cc01fc62f1571971b972`

---

### Task 7: Full verification (DEVELOPMENT_WORKFLOW.md §7)

**Files:** none.

**Interfaces:**
- Consumes: Task 6's tree.
- Produces: the verification record of the hand-off.

- [ ] **Step 1: Run every check**

```bash
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
prek run --all-files
git diff --check 8e1df5b
git diff --stat 8e1df5b -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
git rev-parse HEAD:addon HEAD:tests
```

Expected: `3287 passed`, 0 skipped; every hook Passed (yaml Skipped); the `git diff --check`, protected-path and Neural commands print nothing; the tree ids of Task 6.

- [ ] **Step 2: Leftover old names**

Grep A, the manager's old API anywhere outside the vendored code:

```bash
git grep -nwE "_instanceCache|_defaultVoiceInstance|_getDefaultVoiceSpec|_createVoiceInstance|_setVoiceDatas|_getConfiguredVoiceNameForLanguage|getVoiceSpec|getVoiceCapabilities|getVoiceVariants|beginVoiceSettingsEdit|defaultVoiceInstance|defaultVoiceName|getVoiceInstance|previewVoiceParameterConsistent|onVoiceParameterConsistent|onKeepEngineConsistent|onKeepMainLocaleVoiceConsistent|voiceInfos|allLanguages|localeToVoicesMap|localesToNamesMap|getVoiceNameForLanguage|getVoiceLocaleForLanguage" -- addon tests ':!addon/synthDrivers/WorldVoice/driver/*/driver/*' ':!tests/test_naming_layers.py'
```

Expected: exactly these lines, all the VE/Cerence core's own names (spec §5):

```text
addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py:71:			"_instanceCache",
addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py:419:		self._instanceCache = {}
addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py:970:		instance = core.getVoiceInstance(snapshot.voice_id)
addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py:990:				self.core.getVoiceInstance(self.id),
addon/synthDrivers/WorldVoice/driver/VE/__init__.py:71:			"_instanceCache",
addon/synthDrivers/WorldVoice/driver/VE/__init__.py:417:		self._instanceCache = {}
addon/synthDrivers/WorldVoice/driver/VE/__init__.py:963:		instance = core.getVoiceInstance(snapshot.voice_id)
addon/synthDrivers/WorldVoice/driver/VE/__init__.py:982:			self.core.getVoiceInstance(self.id),
tests/test_f4_engine_adapters.py:18:	core.getVoiceInstance = lambda voice_id: f"native:{voice_id}"
tests/test_f4_engine_adapters.py:59:			getVoiceInstance=lambda voice_id: f"native:{voice_id}",
tests/test_f4_engine_adapters.py:71:	core.getVoiceInstance = lambda voice_id: f"native:{voice_id}"
tests/test_runtime_drain_integration.py:355:	monkeypatch.setattr(control.core, "getVoiceNameForLanguage", lambda language: "fr", raising=False)
tests/test_runtime_legacy_adapter.py:183:	core.getVoiceInstance = lambda key: "native:" + key
tests/test_vocalizer_segment_drain.py:724:	monkeypatch.setattr(env.core, "getVoiceNameForLanguage", lambda language: "fr", raising=False)
tests/test_worldvoice_cancel_wrappers.py:42:	core.voiceInstance = core.getVoiceInstance("fake")
tests/test_worldvoice_cancel_wrappers.py:596:	core._instanceCache["voice"] = "instance"
tests/test_worldvoice_request_manager.py:679:	core.voiceInstance = core.getVoiceInstance("fake")
tests/worldvoice_cancel_wrapper_harness.py:384:	return dict(core._instanceCache)
```

Grep B, every old name of the phase in the core:

```bash
C=addon/synthDrivers/WorldVoice
git grep -nwE "taskManager|_instanceCache|_defaultVoiceInstance|_getDefaultVoiceSpec|_createVoiceInstance|_setVoiceDatas|_getConfiguredVoiceNameForLanguage|voiceName|baseInstance|voiceInstance|getVoiceSpec|getVoiceCapabilities|getVoiceVariants|beginVoiceSettingsEdit|defaultVoiceInstance|defaultVoiceName|getVoiceInstance|previewVoiceParameterConsistent|onVoiceParameterConsistent|onKeepEngineConsistent|onKeepMainLocaleVoiceConsistent|voiceInfos|allLanguages|localeToVoicesMap|localesToNamesMap|getVoiceNameForLanguage|getVoiceLocaleForLanguage|speechSequence|availableLanguages|defaultLang|curLang|tmpLang|targetLang|getTextInfoSpeech|getTextInfoSpeechWithSayAllBreak|waitFactor|onDone" -- $C/runtime $C/unicodeScripts $C/text $C/languageDetection $C/pipeline $C/voices $C/locales.py $C/numberLanguage.py $C/bringup.py $C/speechCommands.py
```

Expected: exactly these lines — NVDA's `getTextInfoSpeech` and `onDone` (spec §4.3, §5):

```text
addon/synthDrivers/WorldVoice/pipeline/sayAll.py:3:patch() hands NVDA's say-all a getTextInfoSpeech that adds the pause, through the same
addon/synthDrivers/WorldVoice/pipeline/sayAll.py:38:		_wrap_get_text_info_speech_with_sayall_break(speech.speech.getTextInfoSpeech),
addon/synthDrivers/WorldVoice/pipeline/sayAll.py:47:		speech.speech.getTextInfoSpeech,
addon/synthDrivers/WorldVoice/runtime/segmentHost.py:345:		``audio=True`` admits a delayed player callback (e.g. an index onDone)
addon/synthDrivers/WorldVoice/runtime/segmentHost.py:649:	Engines adjust three hooks: how a feed's onDone callback is wrapped, how a
addon/synthDrivers/WorldVoice/runtime/segmentHost.py:661:	def feed(self, data, size=None, onDone=None):
addon/synthDrivers/WorldVoice/runtime/segmentHost.py:665:			return self._feed_admitted(record, data, size, onDone)
addon/synthDrivers/WorldVoice/runtime/segmentHost.py:672:				return self._player.feed(data, onDone=callback)
addon/synthDrivers/WorldVoice/runtime/segmentHost.py:673:			return self._player.feed(data, size, onDone=callback)
```

---

## Dry run record

2026-10-27, fresh clone of `/workspace/WorldVoice` at `8e1df5b` in the scratchpad (`ref` symlinked, `prek install`), every step applied from this plan's text by a script that runs the step's bash blocks, writes its `File:` blocks and applies its `Edit:` blocks by exact replacement in document order (phase 42's `planrun.py`, with relative `File:` paths resolved against the repository); pytest under the MemAvailable < 3 GB guard; a checker matched every expected output below in order:

| Commit | Files | Focused runs | Full suite | Token check | Tree ids |
| --- | --- | --- | --- | --- | --- |
| Task 1 | 1 (new) | `18 passed`; probe red `1 failed, 17 passed` (`locales.py:18 badName`) | 3287 passed | — | match |
| Task 2 | 10 | red `13 more items`, then `18 passed` | 3287 passed | `9 files, 52 tokens` | match |
| Task 3 | 18 | red `17 more items`, then `18 passed` | 3287 passed | `17 files, 156 tokens` | match |
| Task 4 | 8 | red `26 more items`, then `18 passed` | 3287 passed | `7 files, 86 tokens` | match |
| Task 5 | 2 | red `7 more items`, then `18 passed` | 3287 passed | `1 files, 26 tokens` | match |
| Task 6 | 3 | red `5 more items`, then `18 passed` | 3287 passed | `2 files, 12 tokens` | match |

Every commit passed the hooks on the first try and left a clean tree. Task 7 in the clone: `3287 passed`, 0 skipped; `prek run --all-files` all Passed; `git diff --check 8e1df5b`, both protected-path commands and the Neural command printed nothing; leftover greps A and B printed exactly the listed lines; final tree ids as Task 6; the final root tree `567d8e3f…` equals the prototype's.

The plan text was produced from a prototype branch (same tree ids). A first replay failed at Task 6 (`HEAD:tests` `5baa2123…`): an `Edit:` block whose "With" text was one blank line, which the replay script reads as empty, so a blank line was lost. The blocks now always carry a line of text on both sides, and this record is the second replay, from the base, of the final text.

## 修正

Review: `docs/superpowers/finish/2026-10-27-phase47a-naming-rule-core-review.md` (`41dd318`): 0 Critical, 0 Important, 5 Minor. The orchestrator asked for all five to be fixed before merge, each test-first (a probe or a red test, then green). Tasks 8–12 fix M5, M1, M2, M3 and M4 in that order (M5 first, so the walker's existing reach is pinned before M1 and M2 change the walker); Task 13 repeats the §7 verification.

Starts from the end of Task 7: `feeb7f0` (`HEAD:addon` = `5e9cb1fbc5bff84d56ae3669a2fba3c316de6b47`, `HEAD:tests` = `9ebbdff74ed7505e7ea9cc01fc62f1571971b972`; the commits `2354744` and `41dd318` after it change only `docs/`). 3287 passed, 0 skipped. Global Constraints above still apply; the new tests raise the count to 3293.

### Task 8: Pin more kinds of names the guard reads (review M5)

**Files:**
- Test: `tests/test_naming_layers.py`
- Create (scratch, not committed): `$SCRATCH/phase47a_probe_global.py`

**Interfaces:**
- Consumes: Task 7's tree.
- Produces: four more cases of `test_the_guard_reads_each_kind_of_name` (nested function, walrus target, `global` name, `cls.x`).

- [ ] **Step 1: Probe (not committed): a walker that ignores `global` passes every guard test**

**File:** `$SCRATCH/phase47a_probe_global.py`

```python
"""Probe: break, or restore, the naming guard's handling of names declared global.

Usage (from the repository root): python3 phase47a_probe_global.py break|restore
"""

import sys
from pathlib import Path

path = Path("tests/test_naming_layers.py")
text = path.read_text(encoding="utf-8")
real, broken = "\t\t\tif node.id in declared_global:\n", "\t\t\tif False:\n"
old, new = (real, broken) if sys.argv[1] == "break" else (broken, real)
assert text.count(old) == 1
path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
```

```bash
python3 $SCRATCH/phase47a_probe_global.py break
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | tail -1
python3 $SCRATCH/phase47a_probe_global.py restore
git status --short
```

Expected: `18 passed` (the gap), and afterwards `git status --short` prints nothing.

- [ ] **Step 2: Add the cases, and see the probe caught**

**Edit:** `tests/test_naming_layers.py`

Replace:

```text
		(CORE_MODULE, "speak = lambda speechSequence: None\n", ["speechSequence"]),
```

With:

```text
		(CORE_MODULE, "speak = lambda speechSequence: None\n", ["speechSequence"]),
		(CORE_MODULE, "def run():\n\tdef innerStep():\n\t\tpass\n", ["run.<locals>.innerStep"]),
		(
			CORE_MODULE,
			"def run(items):\n\tif itemCount := len(items):\n\t\tpass\n",
			["run.<locals>.itemCount"],
		),
		(CORE_MODULE, "def run():\n\tglobal lastValue\n\tlastValue = 1\n", ["lastValue"]),
		(
			CORE_MODULE,
			"class Spec:\n\t@classmethod\n\tdef build(cls):\n\t\tcls.lastSpec = None\n",
			["Spec.lastSpec"],
		),
```

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | tail -1
python3 $SCRATCH/phase47a_probe_global.py break
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | grep -E "^FAILED|passed|failed"
python3 $SCRATCH/phase47a_probe_global.py restore
git status --short
```

Expected: `22 passed`; with the probe, one `FAILED tests/test_naming_layers.py::test_the_guard_reads_each_kind_of_name[…]` line, the case whose source declares `global lastValue`, and `1 failed, 21 passed`; afterwards `git status --short` shows only ` M tests/test_naming_layers.py`.

- [ ] **Step 3: Run the suite and commit**

```bash
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
git add tests/test_naming_layers.py
git diff --cached --stat | tail -1
git commit -q -m "test: pin more kinds of names the naming guard reads" -m "Review M5: the walker already reads nested functions, walrus targets, names declared global and attributes set on cls, but no case pinned them, so a walker change could drop one unnoticed (a probe that ignores global declarations left every guard test green)."
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `3291 passed`; the stat line `1 file changed, 12 insertions(+)`; every hook Passed (yaml Skipped); `git status --short` prints nothing.

Expected after the commit: `HEAD:addon` = `5e9cb1fbc5bff84d56ae3669a2fba3c316de6b47` (unchanged), `HEAD:tests` = `72a52b59ac0e584770b11495005f2c649fccea9a`

---

### Task 9: Exempt only the override parameters the base method takes (review M1)

**Files:**
- Test: `tests/test_naming_layers.py` (`_class_members`, `_Index.inherited`, `_Walker.function`, docstring rule 2, one new test)

**Interfaces:**
- Consumes: Task 8's tree.
- Produces: `_class_members(node) -> dict[str, set[str]]` (member name to the parameter names of the method, empty for a field); `_Index.inherited(module, node) -> dict[str, set[str]]`, merged over the readable bases; a parameter of an overriding method is exempt only when it is in the base method's set. New test `test_the_guard_flags_an_override_parameter_the_base_lacks`.

- [ ] **Step 1: Write the test and see it fail**

**Edit:** `tests/test_naming_layers.py`

Replace:

```text

def test_the_guard_reads_the_imported_base_of_a_class_with_its_name():
```

With:

```text

def test_the_guard_flags_an_override_parameter_the_base_lacks():
	# An override mirrors the parameters of the base method; one the base lacks is the class's own.
	sources = {
		SYNTH + "runtime/port.py": "class Port:\n\tdef speak_segment(self, segment_id):\n\t\tpass\n",
		HOST_MODULE: (
			"from ..runtime.port import Port\n\n\n"
			"class Adapter(Port):\n"
			"\tdef speak_segment(self, segment_id, extra_flag=None):\n\t\tpass\n"
		),
	}
	found = violations(_Index(sources))
	assert [qualname for _path, qualname in found] == ["Adapter.speak_segment.<locals>.extra_flag"]


def test_the_guard_reads_the_imported_base_of_a_class_with_its_name():
```

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | grep -E "Right contains|passed|failed"
```

Expected: `E      Right contains one more item: 'Adapter.speak_segment.<locals>.extra_flag'` and `1 failed, 22 passed`.

- [ ] **Step 2: Read the base methods' parameters**

**Edit:** `tests/test_naming_layers.py` (1/8)

Replace:

```text
     class, driver.Voice). The parameters of such a method mirror the base as well;
```

With:

```text
     class, driver.Voice), and a parameter of such a method that the base method also takes;
```

**Edit:** `tests/test_naming_layers.py` (2/8)

Replace:

```text
def _class_members(node: ast.ClassDef) -> set[str]:
	"""The method and field names a class defines itself."""
	members = set()
```

With:

```text
def _class_members(node: ast.ClassDef) -> dict[str, set[str]]:
	"""The method and field names a class defines itself, each with its parameter names (none for a field)."""
	members: dict[str, set[str]] = {}
```

**Edit:** `tests/test_naming_layers.py` (3/8)

Replace:

```text
			members.add(item.name)
			members |= {target.attr for target in _self_fields(item)}
```

With:

```text
			members.setdefault(item.name, set()).update(argument.arg for argument in _arguments(item.args))
			for target in _self_fields(item):
				members.setdefault(target.attr, set())
```

**Edit:** `tests/test_naming_layers.py` (4/8)

Replace:

```text
			members.add(item.id)
```

With:

```text
			members.setdefault(item.id, set())
```

**Edit:** `tests/test_naming_layers.py` (5/8)

Replace:

```text
	def inherited(self, module: _Module, node: ast.ClassDef) -> frozenset[str]:
		"""The member names of every base class of node that the index can read, transitively."""
		names: set[str] = set()
```

With:

```text
	def inherited(self, module: _Module, node: ast.ClassDef) -> dict[str, set[str]]:
		"""The members of every base class of node that the index can read, transitively, each with
		the parameter names its methods take."""
		names: dict[str, set[str]] = {}
```

**Edit:** `tests/test_naming_layers.py` (6/8)

Replace:

```text
			names |= _class_members(found)
```

With:

```text
			for name, parameters in _class_members(found).items():
				names.setdefault(name, set()).update(parameters)
```

**Edit:** `tests/test_naming_layers.py` (7/8)

Replace:

```text
		return frozenset(names)
```

With:

```text
		return names
```

**Edit:** `tests/test_naming_layers.py` (8/8)

Replace:

```text
			self.add(inner, argument.arg, "parameter", argument.lineno, overrides)
```

With:

```text
			mirrored = overrides and argument.arg in inherited[node.name]
			self.add(inner, argument.arg, "parameter", argument.lineno, mirrored)
```

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | tail -1
```

Expected: `23 passed` (no add-on definition changes its verdict, so the lists stay as they are).

- [ ] **Step 3: Run the suite and commit**

```bash
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
git add tests/test_naming_layers.py
git diff --cached --stat | tail -1
git commit -q -m "test: exempt only the override parameters the base method takes" -m "Review M1: the naming guard exempted every parameter of a method that overrides a readable base, so a parameter the override adds on its own escaped the check. The guard now reads the parameter names of each base method and exempts an override's parameter only when the base method takes it too. No current definition changes its verdict."
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `3292 passed`; the stat line `1 file changed, 31 insertions(+), 13 deletions(-)`; every hook Passed (yaml Skipped); `git status --short` prints nothing.

Expected after the commit: `HEAD:addon` = `5e9cb1fbc5bff84d56ae3669a2fba3c316de6b47` (unchanged), `HEAD:tests` = `e187a4308e4ff882b19a78642226231ff3e74f3c`

---

### Task 10: Read `match` capture names; say what the guard cannot see (review M2)

**Files:**
- Test: `tests/test_naming_layers.py` (`_Walker.visit`, docstring, one case)

**Interfaces:**
- Consumes: Task 9's tree.
- Produces: the walker binds `ast.MatchAs`/`ast.MatchStar` names and `ast.MatchMapping.rest` like other names of their scope; the docstring lists what is not checked (`setattr(obj, "name", value)`, attributes set on objects other than `self`/`cls`).

- [ ] **Step 1: Write the case and see it fail**

**Edit:** `tests/test_naming_layers.py`

Replace:

```text
			CORE_MODULE,
			"class Spec:\n\t@classmethod\n\tdef build(cls):\n\t\tcls.lastSpec = None\n",
```

With:

```text
			CORE_MODULE,
			(
				"def run(value):\n\tmatch value:\n\t\tcase [firstItem, *otherItems]:\n\t\t\tpass\n"
				"\t\tcase {**allItems}:\n\t\t\tpass\n"
			),
			["run.<locals>.firstItem", "run.<locals>.otherItems", "run.<locals>.allItems"],
		),
		(
			CORE_MODULE,
			"class Spec:\n\t@classmethod\n\tdef build(cls):\n\t\tcls.lastSpec = None\n",
```

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | grep -E "Right contains|passed|failed"
```

Expected: `E      Right contains 3 more items, first extra item: 'run.<locals>.firstItem'` and `1 failed, 23 passed`.

- [ ] **Step 2: Read the captures and document the limits**

**Edit:** `tests/test_naming_layers.py` (1/3)

Replace:

```text
(lambdas included), class and dataclass fields, attributes set on self, module variables and
local variables. TRANSITIONAL_47B lists the host-layer names that break the rule until phase 47b
renames them or marks them as interface names; TRANSITIONAL_47C the plugin contract driver.Voice
and VoiceFacade, until phase 47c.
```

With:

```text
(lambdas included), class and dataclass fields, attributes set on self or cls, module variables and
local variables (match captures included). Not checked: a name given as a string, as in
setattr(obj, "name", value), and an attribute set on another object than self or cls.
TRANSITIONAL_47B lists the host-layer names that break the rule until phase 47b renames them or
marks them as interface names; TRANSITIONAL_47C the plugin contract driver.Voice and VoiceFacade,
until phase 47c.
```

**Edit:** `tests/test_naming_layers.py` (2/3)

Replace:

```text
		elif isinstance(node, ast.ExceptHandler) and node.name:
```

With:

```text
		elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name:
```

**Edit:** `tests/test_naming_layers.py` (3/3)

Replace:

```text
			self.add(scope, node.name, kind, node.lineno)
```

With:

```text
			self.add(scope, node.name, kind, node.lineno)
		elif isinstance(node, ast.MatchMapping) and node.rest:
			self.add(scope, node.rest, kind, node.lineno)
```

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | tail -1
```

Expected: `24 passed`.

- [ ] **Step 3: Run the suite and commit**

```bash
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
git add tests/test_naming_layers.py
git diff --cached --stat | tail -1
git commit -q -m "test: read match capture names in the naming guard" -m "Review M2: the walker missed the names a match statement binds (case captures, starred captures and a mapping's rest). It now reads them like other locals. Its docstring also says what an AST guard cannot see: a name passed as a string to setattr, and attributes set on objects other than self or cls."
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `3293 passed`; the stat line `1 file changed, 17 insertions(+), 5 deletions(-)`; every hook Passed (yaml Skipped); `git status --short` prints nothing.

Expected after the commit: `HEAD:addon` = `5e9cb1fbc5bff84d56ae3669a2fba3c316de6b47` (unchanged), `HEAD:tests` = `91a09f89f25a0da64aab7332fb2ef8b887253575`

---

### Task 11: Fail instead of skip once `typing.override` is safe (review M3)

**Files:**
- Test: `tests/test_naming_layers.py` (`test_no_module_imports_typing_override`)

**Interfaces:**
- Consumes: Task 10's tree.
- Produces: with a minimum NVDA version of 2026.1 or later the test fails with a message to delete it; with today's 2024.1 it passes as before.

- [ ] **Step 1: Probe (not committed): a 2026.1 minimum skips the test**

```bash
sed -i 's/addon_minimumNVDAVersion="2024.1"/addon_minimumNVDAVersion="2026.1"/' buildVars.py
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py -rs 2>&1 | grep -E "SKIPPED|passed|failed"
git checkout -- buildVars.py
git status --short
```

Expected: `SKIPPED [1] tests/test_naming_layers.py:755: the minimum NVDA version runs Python 3.13` and `23 passed, 1 skipped` (the gap: the suite's 0-skipped baseline would break); afterwards `git status --short` prints nothing.

- [ ] **Step 2: Fail with a message to delete the test**

**Edit:** `tests/test_naming_layers.py`

Replace:

```text
		pytest.skip("the minimum NVDA version runs Python 3.13")
```

With:

```text
		# Not a skip: the suite keeps 0 skipped, so the test must go when its reason does.
		pytest.fail(
			"The minimum NVDA version now runs Python 3.13, so typing.override imports there: delete this test.",
		)
```

```bash
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | tail -1
sed -i 's/addon_minimumNVDAVersion="2024.1"/addon_minimumNVDAVersion="2026.1"/' buildVars.py
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | grep -E "Failed:|passed|failed"
git checkout -- buildVars.py
git status --short
```

Expected: `24 passed`; with the probe, `E     Failed: The minimum NVDA version now runs Python 3.13, so typing.override imports there: delete this test.` and `1 failed, 23 passed`; afterwards `git status --short` shows only ` M tests/test_naming_layers.py`.

- [ ] **Step 3: Run the suite and commit**

```bash
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
git add tests/test_naming_layers.py
git diff --cached --stat | tail -1
git commit -q -m "test: fail instead of skip once typing.override is safe" -m "Review M3: test_no_module_imports_typing_override skipped itself once the minimum NVDA version reached 2026.1, which would break the suite's 0-skipped baseline (DEVELOPMENT_WORKFLOW.md §7). It now fails there with a message to delete it; with today's minimum, NVDA 2024.1, it passes as before."
git status --short
git rev-parse HEAD:addon HEAD:tests
```

Expected: `3293 passed`; the stat line `1 file changed, 4 insertions(+), 1 deletion(-)`; every hook Passed (yaml Skipped); `git status --short` prints nothing.

Expected after the commit: `HEAD:addon` = `5e9cb1fbc5bff84d56ae3669a2fba3c316de6b47` (unchanged), `HEAD:tests` = `3e00fcfc577883025f0e770006abe9c3779f0e2f`

---

### Task 12: Smooth the two mechanical names (review M4)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voices/manager.py:88`, `:263`; `addon/synthDrivers/WorldVoice/pipeline/sayAll.py:24`, `:31`
- Test: `tests/test_runtime_composition.py:106`
- Modify (scratch, not committed): `$SCRATCH/phase47a_rename_check.py` (accepts `OLD=NEW` pairs)

**Interfaces:**
- Consumes: Task 11's tree.
- Produces: `VoiceManager._set_voice_data()` (was `_set_voice_datas`); Say All's inner `get_text_info_speech_with_sayall_break` (was `get_text_info_speech_with_say_all_break`), spelled `sayall` like its enclosing `_wrap_get_text_info_speech_with_sayall_break` and the `sayall_wait_factor` setting. Both private; no other caller.

- [ ] **Step 1: Probe: the two names**

```bash
git grep -nwE "_set_voice_datas|get_text_info_speech_with_say_all_break" -- addon tests
```

Expected (the gap):

```text
addon/synthDrivers/WorldVoice/pipeline/sayAll.py:24:	def get_text_info_speech_with_say_all_break(*args, **kwargs):
addon/synthDrivers/WorldVoice/pipeline/sayAll.py:31:	return get_text_info_speech_with_say_all_break
addon/synthDrivers/WorldVoice/voices/manager.py:88:		self._set_voice_datas()
addon/synthDrivers/WorldVoice/voices/manager.py:263:	def _set_voice_datas(self):
tests/test_runtime_composition.py:106:	manager._set_voice_datas()
```

- [ ] **Step 2: Rename, and let the token check take explicit pairs**

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/sayAll.py` (1/2)

Replace:

```text
	def get_text_info_speech_with_say_all_break(*args, **kwargs):
```

With:

```text
	def get_text_info_speech_with_sayall_break(*args, **kwargs):
```

**Edit:** `addon/synthDrivers/WorldVoice/pipeline/sayAll.py` (2/2)

Replace:

```text
	return get_text_info_speech_with_say_all_break
```

With:

```text
	return get_text_info_speech_with_sayall_break
```

**Edit:** `addon/synthDrivers/WorldVoice/voices/manager.py` (1/2)

Replace:

```text
		self._set_voice_datas()
```

With:

```text
		self._set_voice_data()
```

**Edit:** `addon/synthDrivers/WorldVoice/voices/manager.py` (2/2)

Replace:

```text
	def _set_voice_datas(self):
```

With:

```text
	def _set_voice_data(self):
```

**Edit:** `tests/test_runtime_composition.py`

Replace:

```text
	manager._set_voice_datas()
```

With:

```text
	manager._set_voice_data()
```

**File:** `$SCRATCH/phase47a_rename_check.py`

```python
"""Check that HEAD differs from REV only by renaming NAMES, token by token in order.

Usage (from the repository root): python3 phase47a_rename_check.py REV NAME...
A NAME is renamed to snake(NAME), and an OLD=NEW pair to NEW.
tests/test_naming_layers.py, whose lists the tasks edit, is left out. A name, comment or string token
of HEAD must equal REV's token or REV's token with NAMES renamed; ruff's line breaks and trailing
commas are ignored.
"""

import io
import re
import subprocess
import sys
import tokenize


def snake(name):
	lead = len(name) - len(name.lstrip("_"))
	return name[:lead] + re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name[lead:]).lower()


rev, *names = sys.argv[1:]
renames = dict(name.split("=", 1) if "=" in name else (name, snake(name)) for name in names)
pattern = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, renames)) + r")(?!\w)")


def tokens(source):
	found = [
		(token.type, token.string)
		for token in tokenize.generate_tokens(io.StringIO(source).readline)
		if token.type != tokenize.NL
	]
	return [
		token
		for index, token in enumerate(found)
		if not (token == (tokenize.OP, ",") and index + 1 < len(found) and found[index + 1][1] in ")]}")
	]


def git(*args):
	return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


paths = [p for p in git("diff", "--name-only", rev, "HEAD").split() if p != "tests/test_naming_layers.py"]
renamed = 0
for path in paths:
	old, new = tokens(git("show", f"{rev}:{path}")), tokens(git("show", f"HEAD:{path}"))
	if len(old) != len(new):
		sys.exit(f"{path}: {len(old)} tokens before, {len(new)} after")
	for before, after in zip(old, new, strict=True):
		if before == after:
			continue
		allowed = pattern.sub(lambda match: renames[match.group(1)], before[1])
		if before[0] != after[0] or after[1] != allowed:
			sys.exit(f"{path}: {before[1]!r} became {after[1]!r}")
		renamed += 1
print(f"pure rename: OK ({len(paths)} files, {renamed} tokens renamed)")
```

```bash
git grep -nwE "_set_voice_datas|get_text_info_speech_with_say_all_break" -- addon tests
bash $SCRATCH/runtests.sh . tests/test_naming_layers.py 2>&1 | tail -1
```

Expected: the grep prints nothing; `24 passed`.

- [ ] **Step 3: Run the suite, commit and check**

```bash
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
git add addon/synthDrivers/WorldVoice/pipeline/sayAll.py addon/synthDrivers/WorldVoice/voices/manager.py tests/test_runtime_composition.py
git diff --cached --stat | tail -1
git commit -q -m "refactor: smooth two names from the mechanical rename" -m "Review M4: the strict snake_case conversion left VoiceManager._set_voice_datas and Say All's inner get_text_info_speech_with_say_all_break, which disagrees with its enclosing _wrap_get_text_info_speech_with_sayall_break and the sayall_wait_factor setting. They become _set_voice_data and get_text_info_speech_with_sayall_break; both are private, so only the manager's one test follows."
git status --short
git rev-parse HEAD:addon HEAD:tests
python3 $SCRATCH/phase47a_rename_check.py HEAD~1 _set_voice_datas=_set_voice_data get_text_info_speech_with_say_all_break=get_text_info_speech_with_sayall_break
```

Expected: `3293 passed`; the stat line `3 files changed, 5 insertions(+), 5 deletions(-)`; every hook Passed (yaml Skipped); `git status --short` prints nothing; `pure rename: OK (3 files, 5 tokens renamed)`.

Expected after the commit: `HEAD:addon` = `c26c20f4f947a4529df94033ae0dd9aec9b0bf82`, `HEAD:tests` = `0824ffae4a2ff62df773057a8fbbbb12ec62f1d5`

---

### Task 13: Full verification after the fixes

**Files:** none.

**Interfaces:**
- Consumes: Task 12's tree.
- Produces: the verification record of the hand-off.

- [ ] **Step 1: Run every check**

```bash
bash $SCRATCH/runtests.sh . tests 2>&1 | tail -1
prek run --all-files
git diff --check 8e1df5b
git diff --stat 8e1df5b -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
git rev-parse HEAD:addon HEAD:tests
```

Expected: `3293 passed` (3287 + 4 + 1 + 1), 0 skipped; every hook Passed (yaml Skipped); the `git diff --check`, protected-path and Neural commands print nothing; the tree ids of Task 12.

### Dry run record (修正)

2026-10-27, fresh clone of the task branch at `41dd318` (the end of Task 7 plus the docs-only commits; `ref` symlinked, `prek install`), Tasks 8–13 applied from this section's text by the same replay script; a checker matched every expected output in order:

| Commit | Files | Probe / red | Green | Full suite | Tree ids |
| --- | --- | --- | --- | --- | --- |
| Task 8 (M5) | 1 | probe `18 passed` (gap) | `22 passed`; probe now `1 failed, 21 passed` | 3291 passed | match |
| Task 9 (M1) | 1 | red `1 failed, 22 passed` | `23 passed` | 3292 passed | match |
| Task 10 (M2) | 1 | red `1 failed, 23 passed` | `24 passed` | 3293 passed | match |
| Task 11 (M3) | 1 | probe `23 passed, 1 skipped` (gap) | `24 passed`; probe now `1 failed, 23 passed` | 3293 passed | match |
| Task 12 (M4) | 3 | grep: 5 lines (gap) | grep empty; `24 passed`; `pure rename: OK (3 files, 5 tokens renamed)` | 3293 passed | match |

Every commit passed the hooks on the first try and left a clean tree. Task 13 in the clone: `3293 passed`, 0 skipped; `prek run --all-files` all Passed; `git diff --check 8e1df5b`, both protected-path commands and the Neural command printed nothing; final tree ids as Task 12. The text was produced from a prototype branch with the same tree ids; this record is the first replay of the final text.
