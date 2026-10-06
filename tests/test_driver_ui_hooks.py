"""Public driver hooks the settings panels use instead of private members."""

import types

import pytest
from pipeline_harness import load_synth


@pytest.fixture
def synth(monkeypatch):
	# Timing lives only behind the detection settings service, never in the config the class sees.
	conf = {"WorldVoice": {"pipeline": {}}}
	synth_class, _ = load_synth(monkeypatch, conf)
	calls = []
	globals_ = synth_class.refresh_language_detection.__globals__
	detection = types.SimpleNamespace(timing="before")
	monkeypatch.setitem(
		globals_,
		"detection_settings",
		types.SimpleNamespace(
			get=lambda: types.SimpleNamespace(timing=detection.timing),
		),
	)
	monkeypatch.setitem(
		globals_,
		"filter_speechSequence",
		types.SimpleNamespace(
			register=lambda handler: calls.append(("register", handler)),
			unregister=lambda handler: calls.append(("unregister", handler)),
		),
	)
	monkeypatch.setitem(globals_, "order_move_to_start_register", lambda: calls.append(("reorder",)))
	instance = object.__new__(synth_class)
	instance.add_detected_language_commands = handler = object()
	return types.SimpleNamespace(synth=instance, calls=calls, detection=detection, handler=handler)


def test_voice_manager_is_the_private_manager_or_none(synth):
	manager = object()
	synth.synth._voiceManager = manager
	assert synth.synth.voice_manager is manager
	synth.synth._voiceManager = None
	assert synth.synth.voice_manager is None


def test_refresh_without_detection_only_unregisters(synth):
	synth.synth.uwv = False
	synth.synth.refresh_language_detection()
	assert synth.calls == [("unregister", synth.handler)]


@pytest.mark.parametrize(
	"timing,expected",
	[
		("before", ["register", "reorder"]),
		("after", ["unregister"]),
	],
)
def test_refresh_registers_only_for_detection_before_nvda(synth, timing, expected):
	synth.detection.timing = timing
	synth.synth.uwv = True
	synth.synth.refresh_language_detection()
	assert [call[0] for call in synth.calls] == expected


def test_setting_uwv_refreshes_language_detection(synth, monkeypatch):
	# NVDA's AutoPropertyObject maps uwv to _get_uwv; the exec harness has no such metaclass.
	monkeypatch.setattr(type(synth.synth), "uwv", property(lambda self: self._get_uwv()), raising=False)
	synth.synth._set_uwv(False)
	assert synth.synth.uwv is False
	assert synth.calls == [("unregister", synth.handler)]


def test_detection_timing_comes_from_the_settings_service(synth):
	synth.detection.timing = "after"
	assert synth.synth._detectLanguageTiming() == "after"


def test_a_timing_change_refreshes_language_detection(synth):
	synth.synth.uwv = True
	synth.synth._on_detection_settings(object(), frozenset({"timing"}))
	assert [call[0] for call in synth.calls] == ["register", "reorder"]


def test_other_detection_changes_leave_the_filter_order_alone(synth):
	synth.synth.uwv = True
	synth.synth._on_detection_settings(object(), frozenset({"ignore_numbers", "script_language"}))
	assert synth.calls == []
