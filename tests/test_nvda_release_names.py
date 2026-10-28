"""The NVDA names the eSpeak, SAPI5 and OneCore wrappers list, checked on each NVDA release (phase 51)."""

import re
import subprocess
import textwrap
from types import ModuleType

import pytest
from addon_loader import ROOT
from nvda_releases import (
	ENGINES,
	NVDA,
	RELEASES,
	WORKING_TREE,
	host_names,
	release_missing,
	release_source,
	static_missing,
)

# The first NVDA release with every name the engine lists (phase 51 spec §1.1). SAPI5's wrapper is
# built on the request-queue worker NVDA 2025.3 introduced: on older NVDA, Voice.ready() skips it.
FIRST_COMPLETE = {"Espeak": "2024.1", "SAPI5": "2025.3", "OneCore": "2024.1"}
VERSIONS = (*RELEASES, WORKING_TREE)

AGREEMENT_SOURCE = textwrap.dedent(
	"""
	import os.path
	from types import SimpleNamespace as Namespace

	top = 1

	global declared
	declared = 4

	def helper():
		pass

	class Other:
		_elsewhere = 1

		def __init__(self):
			self._elsewhereStore = 1

	if True:
		conditional = 2

	try:
		guarded = 3
	except Exception:
		pass

	class Cls:
		_flag = False

		def __init__(self):
			self._made = 1
			self.__hidden = 2

		def _method(self):
			self._later = 2

			def inner():
				self._nested = 3

			return inner

		def _get_rate(self):
			return 1

		rate = property(_get_rate)
	""",
)
MODULE_NAMES = {
	"declared",
	"os",
	"Namespace",
	"top",
	"helper",
	"Other",
	"conditional",
	"guarded",
	"absent",
	"path",
}
CLASS_NAMES = {
	"_flag",
	"_made",
	"_Cls__hidden",
	"__hidden",
	"_method",
	"_later",
	"_nested",
	"_get_rate",
	"rate",
	"_absent",
	# Bound only in Other: neither view may count another class's names.
	"_elsewhere",
	"_elsewhereStore",
}


def live_module(name, source, namespace=None):
	module = ModuleType(name)
	module.__dict__.update(namespace or {})
	exec(compile(source, name, "exec"), module.__dict__)  # noqa: S102 - a fixed test source
	return module


def test_static_and_live_views_agree_on_synthetic_source():
	module = live_module("m", AGREEMENT_SOURCE)
	live = host_names.missing_host_names(
		module,
		module.Cls,
		module_names=MODULE_NAMES,
		class_names=CLASS_NAMES,
	)
	static = static_missing(
		AGREEMENT_SOURCE,
		"m",
		"Cls",
		"m.Cls",
		module_names=MODULE_NAMES,
		class_names=CLASS_NAMES,
	)
	expected = (
		"m.Cls.__hidden",
		"m.Cls._absent",
		"m.Cls._elsewhere",
		"m.Cls._elsewhereStore",
		"m.absent",
		"m.path",
	)
	assert static == live == expected


def test_static_view_does_not_see_out_of_file_bases():
	class Base:
		def __init__(self):
			self._base = 1

	source = "class Child(Base):\n\tpass\n"
	module = live_module("m", source, {"Base": Base})
	assert host_names.missing_host_names(module, module.Child, module_names=(), class_names={"_base"}) == ()
	assert static_missing(source, "m", "Child", "m.Child", module_names=(), class_names={"_base"}) == (
		"m.Child._base",
	)


def test_static_view_ignores_globals_bound_only_inside_functions():
	source = "def f():\n\tglobal late\n\tlate = 1\n\nclass Cls:\n\tpass\n"
	module = live_module("m", source)
	live = host_names.missing_host_names(module, module.Cls, module_names={"late"}, class_names=())
	static = static_missing(source, "m", "Cls", "m.Cls", module_names={"late"}, class_names=())
	assert static == live == ("m.late",)


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("engine", sorted(ENGINES))
def test_nvda_names_exist_from_the_first_complete_release(engine, version):
	missing = release_missing(engine, version)
	if VERSIONS.index(version) >= VERSIONS.index(FIRST_COMPLETE[engine]):
		assert missing == (), f"NVDA {version} lacks names the {engine} wrapper lists: {', '.join(missing)}"
	else:
		assert missing, f"NVDA {version} now has every {engine} name: move FIRST_COMPLETE[{engine!r}]"


# What NVDA lacks before 2025.3 for SAPI5, exactly (phase 51 spec §10). Both halves count: a class
# name includes the overrides (_onEndStream, _speakThread, _initWasapiAudio) as well as the privates.
SAPI5_MODULE_MISSING_2025 = {"ISpVoice", "_SPEventEnum", "_SapiEvent"}
SAPI5_MODULE_MISSING_2024 = SAPI5_MODULE_MISSING_2025 | {
	"ISpEventSource",
	"ISpNotifySource",
	"SonicStream",
	"SynthDriverAudioStream",
	"hresult",
	"sonicInitialize",
}
SAPI5_CLASS_MISSING_2025_2 = {
	"_bookmarkLists",
	"_isCancelling",
	"_isCompleted",
	"_isSpeaking",
	"_isStoppingThread",
	"_onEndStream",
	"_requestCompleted",
	"_requestsAvailable",
	"_speakRequests",
	"_speakThread",
	"_thread",
	"_threadCond",
}
SAPI5_CLASS_MISSING_2025_1 = SAPI5_CLASS_MISSING_2025_2 | {"_initWasapiAudio"}


@pytest.mark.parametrize(
	("version", "module_names", "class_names", "count"),
	[
		("2024.1", SAPI5_MODULE_MISSING_2024, SAPI5_CLASS_MISSING_2025_1, 22),
		("2024.4", SAPI5_MODULE_MISSING_2024, SAPI5_CLASS_MISSING_2025_1, 22),
		("2025.1", SAPI5_MODULE_MISSING_2025, SAPI5_CLASS_MISSING_2025_1, 16),
		("2025.2", SAPI5_MODULE_MISSING_2025, SAPI5_CLASS_MISSING_2025_2, 15),
	],
	ids=["2024.1", "2024.4", "2025.1", "2025.2"],
)
def test_sapi5_names_missing_before_2025_3_are_exact(version, module_names, class_names, count):
	expected = sorted(
		[f"synthDrivers.sapi5.{name}" for name in module_names]
		+ [f"synthDrivers.sapi5.SynthDriver.{name}" for name in class_names],
	)
	assert len(expected) == count
	assert release_missing("SAPI5", version) == tuple(expected)


def test_missing_release_tag_fails_with_fetch_hint():
	with pytest.raises(pytest.fail.Exception) as failure:
		release_source("1999.1", "sapi5.py")
	assert "release-1999.1" in str(failure.value)
	assert "git -C ref/nvda fetch --tags" in str(failure.value)


def test_release_table_covers_the_supported_range():
	minimum = re.search(
		r'addon_minimumNVDAVersion="([^"]+)"',
		(ROOT / "buildVars.py").read_text(encoding="utf-8"),
	)
	assert RELEASES[0] == minimum.group(1)
	years_and_releases = [
		tuple(int(part) for part in re.match(r"(\d+)\.(\d+)", v).groups()) for v in RELEASES
	]
	assert years_and_releases == sorted(set(years_and_releases))
	assert set(FIRST_COMPLETE.values()) <= set(RELEASES)


def _feature_release(version):
	return tuple(int(part) for part in re.match(r"(\d+)\.(\d+)", version).groups())


def test_release_table_includes_the_newest_ref_nvda_release():
	# RELEASES is kept by hand (spec §5); this only reminds whoever updates ref/nvda to extend it.
	tags = subprocess.run(
		["git", "-C", str(NVDA), "tag", "-l", "release-*"],
		capture_output=True,
		text=True,
		check=False,
	).stdout.split()
	features = {
		_feature_release(tag.removeprefix("release-"))
		for tag in tags
		if re.fullmatch(r"release-\d+\.\d+(\.\d+)*((beta|rc)\d+)?", tag)
	}
	if not features:
		pytest.fail("ref/nvda has no release-* tags: fetch them with `git -C ref/nvda fetch --tags`.")
	newest = max(features)
	assert newest in {_feature_release(version) for version in RELEASES}, (
		f"ref/nvda has NVDA {newest[0]}.{newest[1]} (release-{newest[0]}.{newest[1]}…): add its newest "
		"tag to RELEASES in tests/nvda_releases.py"
	)
