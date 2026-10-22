"""The NVDA settings-panel internals WorldVoice's Voice panel relies on are the reviewed ones.

The panel inherits NVDA's AutoSettingsMixin and overrides updateDriverSettings and
_updateValueForControl; each guard says what to review when NVDA changes.
"""

import ast
import hashlib

import pytest
from addon_loader import REF

NVDA = REF / "nvda/source/gui/settingsDialogs.py"
# ref/nvda 1406f9f8a: AutoSettingsMixin._updateValueForControl. WorldVoice's override reloads
# string options on purpose, so only a change on NVDA's side is detected; when this fails,
# review the override against NVDA's new version, then update the fingerprint.
UPDATE_VALUE_FINGERPRINT = "8c92887331265d7885bd02245295a188111dffdd500c2f2b3eaee5c2166c17ae"
# ref/nvda 7d25bc76e: AutoSettingsMixin._createNewControl. The Voice panel's pre-pass calls it for
# every driver setting and moves its own rows afterwards because it inserts at
# len(self.sizerDict) - 1, an index that counts driver rows only. When this fails, check the
# insertion index, that a failed maker still leaves no row, and that the row still lands in
# sizerDict; then review _placePipelineRows and update the fingerprint.
CREATE_NEW_CONTROL_FINGERPRINT = "1eb40ecae0a0ed9de30f9c14b672b5ed5bb6c2952c35d0ccf351b3f2f8a0ff6f"
# ref/nvda 7d25bc76e: AutoSettingsMixin.updateDriverSettings. The Voice panel's override creates
# every control first, then calls this to hide unsupported rows and update values. When this
# fails, check that it still creates nothing the pre-pass already made, still skips changedSetting
# and private settings, and still hides and shows by sizerDict; then update the fingerprint.
UPDATE_DRIVER_SETTINGS_FINGERPRINT = "ba74b139720bb30928d502c9a976aaa5f7557322b9c0a95298122cf17321e497"
# ref/nvda 7d25bc76e: AutoSettingsMixin.refreshGui. On a synth change it clears sizerDict,
# destroys every window, keeps lastControl, then runs makeSettings again: the Voice panel counts a
# destroyed control as absent (final review I1). When this fails, check that a rebuild still
# destroys the earlier windows and still goes through makeSettings; then update the fingerprint.
REFRESH_GUI_FINGERPRINT = "b2019b0b6057db3a5dfd8da3d95537b20c90aef0f94a38d755d27795ef993597"
MAKERS = ("_makeSliderSettingControl", "_makeStringSettingControl", "_makeBooleanSettingControl")


def method(path, cls, name):
	tree = ast.parse(path.read_text(encoding="utf-8"))
	(owner,) = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == cls]
	(function,) = [node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == name]
	return function


@pytest.fixture
def nvda():
	if not NVDA.is_file():
		pytest.skip("ref/nvda is not checked out")
	return NVDA


def test_nvda_update_value_for_control_is_the_reviewed_version(nvda):
	function = method(nvda, "AutoSettingsMixin", "_updateValueForControl")
	# unparse, not dump: dump's format changes between Python versions.
	assert hashlib.sha256(ast.unparse(function).encode()).hexdigest() == UPDATE_VALUE_FINGERPRINT


@pytest.mark.parametrize(
	("name", "fingerprint"),
	[
		("_createNewControl", CREATE_NEW_CONTROL_FINGERPRINT),
		("updateDriverSettings", UPDATE_DRIVER_SETTINGS_FINGERPRINT),
		("refreshGui", REFRESH_GUI_FINGERPRINT),
	],
	ids=["_createNewControl", "updateDriverSettings", "refreshGui"],
)
def test_nvda_mixin_method_is_the_reviewed_version(nvda, name, fingerprint):
	function = method(nvda, "AutoSettingsMixin", name)
	assert hashlib.sha256(ast.unparse(function).encode()).hexdigest() == fingerprint


@pytest.mark.parametrize("name", MAKERS)
def test_nvda_makers_chain_last_control(nvda, name):
	# The Voice panel sets lastControl to each control it makes, so NVDA's next driver control
	# moves after it in Tab order instead of before it.
	body = [ast.unparse(statement) for statement in method(nvda, "AutoSettingsMixin", name).body]
	(index,) = [i for i, line in enumerate(body) if line.startswith("if self.lastControl:")]
	control = body[index + 1].removeprefix("self.lastControl = ")
	assert body[index] == f"if self.lastControl:\n    {control}.MoveAfterInTabOrder(self.lastControl)"


def test_nvda_voice_panel_makes_driver_settings_first(nvda):
	# The Voice panel's updateDriverSettings override creates its controls before NVDA's own ones.
	(first, *_rest) = method(nvda, "VoiceSettingsPanel", "makeSettings").body
	assert ast.unparse(first) == "self.updateDriverSettings()"


def test_nvda_voice_change_updates_the_driver_settings(nvda):
	# A voice switch reaches the override, which then has nothing to create.
	calls = [ast.unparse(node) for node in ast.walk(method(nvda, "StringDriverSettingChanger", "__call__"))]
	assert "self.container.updateDriverSettings(changedSetting=self.setting.id)" in calls
