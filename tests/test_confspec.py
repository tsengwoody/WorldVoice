"""The [WorldVoice] confspec: its sections, in order, and the owners each one comes from."""

from types import SimpleNamespace

from addon_loader import load_definitions
from nvda_stubs import CONFSPEC_SOURCE

OWNERS = {
	"DETECTION_CONFSPEC": {"a": "string(default=x)"},
	"PIPELINE_CONFSPEC": {"p": "integer(default=1)"},
	"LOG_SWITCHES": ("s1", "s2"),
	"VOICE_CONFSPEC": {"rate": "integer(default=50)"},
}


def install_confspec():
	return load_definitions(CONFSPEC_SOURCE, ["installConfspec"], dict(OWNERS))["installConfspec"]


def test_confspec_sections():
	conf = SimpleNamespace(spec={"speech": {}})
	install_confspec()(conf)
	# Only the WorldVoice section is set; NVDA's own sections stay.
	assert list(conf.spec) == ["speech", "WorldVoice"]
	spec = conf.spec["WorldVoice"]
	assert list(spec) == ["autoLanguageSwitching", "pipeline", "role", "engine", "log", "voices"]
	assert spec["autoLanguageSwitching"] == {
		"a": "string(default=x)",
		"keepMainLocaleVoiceConsistent": "boolean(default=true)",
		"keepMainLocaleParameterConsistent": "boolean(default=false)",
		"keepMainLocaleEngineConsistent": "boolean(default=true)",
	}
	assert spec["pipeline"] == {"p": "integer(default=1)"}
	# A copy: NVDA's config may change its spec without changing the owner's table.
	assert spec["pipeline"] is not OWNERS["PIPELINE_CONFSPEC"]
	assert spec["role"] == {}
	assert spec["engine"] == {"__many__": "boolean(default=false)"}
	assert spec["log"] == {
		"enable": "boolean(default=false)",
		"s1": "boolean(default=false)",
		"s2": "boolean(default=false)",
	}
	assert spec["voices"] == {"__many__": {"rate": "integer(default=50)"}}
	assert spec["voices"]["__many__"] is not OWNERS["VOICE_CONFSPEC"]
