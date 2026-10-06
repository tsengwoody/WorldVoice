"""WorldVoice's copy of NVDA's settings-panel code stays in step with NVDA."""

import ast
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NVDA = ROOT / "ref/nvda/source/gui/settingsDialogs.py"
COPY = ROOT / "addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py"
# ref/nvda 1406f9f8a: AutoSettingsMixin._updateValueForControl. WorldVoice's override reloads
# string options on purpose, so only a change on NVDA's side is detected; when this fails,
# review the override against NVDA's new version, then update the fingerprint.
UPDATE_VALUE_FINGERPRINT = "8c92887331265d7885bd02245295a188111dffdd500c2f2b3eaee5c2166c17ae"


def method(path, cls, name):
	tree = ast.parse(path.read_text(encoding="utf-8"))
	(owner,) = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == cls]
	(function,) = [node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == name]
	return function


def without_docstring(function):
	first = function.body[0]
	if (
		isinstance(first, ast.Expr)
		and isinstance(first.value, ast.Constant)
		and isinstance(first.value.value, str)
	):
		return function.body[1:]
	return function.body


class AllSettings(ast.NodeTransformer):
	"""NVDA iterates supportedSettings; the copy iterates its local list of all settings."""

	def visit_For(self, node):
		self.generic_visit(node)
		if ast.unparse(node.iter) == "settingsInst.supportedSettings":
			node.iter = ast.Name("supportedSettings", ast.Load())
		return node


def is_settings_source(statement):
	return isinstance(statement, ast.Assign) and [ast.unparse(t) for t in statement.targets] == [
		"supportedSettings",
	]


@pytest.fixture
def nvda():
	if not NVDA.is_file():
		pytest.skip("ref/nvda is not checked out")
	return NVDA


def test_create_driver_settings_is_nvdas_update_driver_settings_over_all_settings(nvda):
	theirs = [
		AllSettings().visit(s)
		for s in without_docstring(method(nvda, "AutoSettingsMixin", "updateDriverSettings"))
	]
	ours = [
		s
		for s in without_docstring(method(COPY, "WorldVoiceVoiceSettingsPanel", "createDriverSettings"))
		if not is_settings_source(s)
	]
	assert [ast.unparse(s) for s in ours] == [ast.unparse(s) for s in theirs]
	assert [ast.dump(s) for s in ours] == [ast.dump(s) for s in theirs]
	# The one intended difference: the copy lists every setting, not only the supported ones.
	(source,) = [
		s
		for s in without_docstring(method(COPY, "WorldVoiceVoiceSettingsPanel", "createDriverSettings"))
		if is_settings_source(s)
	]
	assert ast.unparse(source.value) == (
		"settingsInst.allSupportedSettings if hasattr(settingsInst, 'allSupportedSettings') "
		"else settingsInst.supportedSettings"
	)


def test_nvda_update_value_for_control_is_the_reviewed_version(nvda):
	function = method(nvda, "AutoSettingsMixin", "_updateValueForControl")
	# unparse, not dump: dump's format changes between Python versions.
	assert hashlib.sha256(ast.unparse(function).encode()).hexdigest() == UPDATE_VALUE_FINGERPRINT
