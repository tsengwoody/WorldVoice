"""The WorldVoice config stub keeps the defaults the add-on itself declares."""

from nvda_stubs import _confspec_default, worldvoice_conf
from pipeline_harness import load_settings_module


def test_pipeline_defaults_match_the_confspec_the_add_on_registers(monkeypatch):
	# worldvoice_conf reads the PIPELINE_SETTINGS table; NVDA gets PIPELINE_CONFSPEC built from it.
	settings = load_settings_module(monkeypatch, worldvoice_conf())
	registered = {key: _confspec_default(check) for key, check in settings.PIPELINE_CONFSPEC.items()}
	assert worldvoice_conf()["WorldVoice"]["pipeline"] == registered
