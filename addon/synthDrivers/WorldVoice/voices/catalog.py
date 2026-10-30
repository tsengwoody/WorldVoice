"""Immutable view of the voices that opened engines published."""

from collections import OrderedDict, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from operator import attrgetter
from types import MappingProxyType

import languageHandler
from synthDriverHandler import VoiceInfo

from ..locales import primary_language
from ..runtime.models import VoiceSpec


def group_by_primary_locale(specs: Iterable[VoiceSpec]) -> dict[str, list[str]]:
	groups: dict[str, list[str]] = defaultdict(list)
	for spec in specs:
		groups[primary_language(spec.locale)].append(spec.name)
	return dict(groups)


@dataclass(frozen=True)
class VoiceCatalog:
	table: tuple[VoiceSpec, ...]
	by_name: Mapping[str, VoiceSpec]
	# Mutable on purpose: NVDA's SynthDriver.availableVoices is an OrderedDict.
	voice_infos: "OrderedDict[str, VoiceInfo]"
	all_languages: tuple[str, ...]
	# The engines in table order, and each engine's entries of voice_infos (the same objects).
	engines: tuple[str, ...]
	engine_voice_infos: "Mapping[str, OrderedDict[str, VoiceInfo]]"

	@classmethod
	def from_specs(cls, specs: Iterable[VoiceSpec]) -> "VoiceCatalog":
		by_name = {}
		for spec in specs:
			by_name[spec.name] = spec
		table = tuple(sorted(by_name.values(), key=attrgetter("engine", "language", "name")))
		voice_infos = OrderedDict((v.name, VoiceInfo(v.name, v.description, v.language)) for v in table)
		engine_voice_infos: dict[str, OrderedDict[str, VoiceInfo]] = {}
		for spec in table:
			engine_voice_infos.setdefault(spec.engine, OrderedDict())[spec.name] = voice_infos[spec.name]
		return cls(
			table=table,
			by_name=MappingProxyType(by_name),
			voice_infos=voice_infos,
			all_languages=tuple(sorted(group_by_primary_locale(table))),
			engines=tuple(engine_voice_infos),
			engine_voice_infos=MappingProxyType(engine_voice_infos),
		)

	def readable_name(self, locale: str) -> str:
		description = languageHandler.getLanguageDescription(locale)
		return f"{description} - {locale}" if description else locale


EMPTY_CATALOG = VoiceCatalog.from_specs(())
