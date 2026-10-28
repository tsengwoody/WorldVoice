"""VE and Cerence offer their WorldVoice-workspace folder as a resource path only when it exists.

Decided by the user (2026-10-28), an approved change to the inner drivers: without the folder, the
resource list can come out empty, so the wrapper's "no resources available" check can apply.
"""

import os

import pytest
from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs


@pytest.fixture(params=["VE", "Cerence"])
def inner(request, monkeypatch):
	monkeypatch.delenv("PROGRAMDATA", raising=False)
	harness = load_real_driver_with_native_stubs(monkeypatch, request.param)
	return request.param, harness


def _workspace(engine):
	return os.path.join("WorldVoice-workspace", engine)


def test_a_missing_workspace_folder_is_not_offered(inner, monkeypatch):
	_, harness = inner
	monkeypatch.setattr(harness.original_driver.os.path, "isdir", lambda path: False)
	assert harness.get_resource_paths() == []


def test_an_existing_workspace_folder_is_offered(inner, monkeypatch):
	engine, harness = inner
	monkeypatch.setattr(
		harness.original_driver.os.path,
		"isdir",
		lambda path: path.endswith(_workspace(engine)),
	)
	(path,) = harness.get_resource_paths()
	assert path.endswith(_workspace(engine))
