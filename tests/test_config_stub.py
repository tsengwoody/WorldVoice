"""The WorldVoice config stub keeps the defaults the add-on itself declares."""

import pytest
from nvda_stubs import _confspec_default, worldvoice_conf
from pipeline_harness import load_settings_module


def test_pipeline_defaults_match_the_confspec_the_add_on_registers(monkeypatch):
	# worldvoice_conf reads the PIPELINE_SETTINGS table; NVDA gets PIPELINE_CONFSPEC built from it.
	settings = load_settings_module(monkeypatch, worldvoice_conf())
	registered = {key: _confspec_default(check) for key, check in settings.PIPELINE_CONFSPEC.items()}
	assert worldvoice_conf()["WorldVoice"]["pipeline"] == registered


def test_the_stub_refuses_a_key_its_section_lacks():
	# A key outside the confspec would be a stale name the add-on never reads, so a test relying on
	# its value would pass without reading it. Data sections (engines, roles, voices) take any key.
	with pytest.raises(KeyError, match="pair_wait_factor"):
		worldvoice_conf(pipeline={"pair_wait_factor": 10})
	with pytest.raises(KeyError, match="DetectLanguageTiming"):
		worldvoice_conf(autoLanguageSwitching={"DetectLanguageTiming": "before"})
	conf = worldvoice_conf(engine={"Espeak": True}, role={"en": {"voice": "v"}})
	assert conf["WorldVoice"]["engine"] == {"Espeak": True}
