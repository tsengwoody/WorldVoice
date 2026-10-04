"""Legacy engine metadata and lifecycle backed by the runtime voice facade."""

import languageHandler

from ..compat.voiceFacade import VoiceFacade
from ..runtime.settings import VOICE_PARAMETERS, boolean


def getVoiceKey(engine, voiceId):
	return "%s:%s" % (engine, voiceId)


class Voice(VoiceFacade):
	core = None
	session = None
	engine = ""
	synth_driver_class = None
	extra_capabilities = frozenset()
	drain_profile = None

	def applyEngineSettings(self, core, snapshot):
		return None

	@property
	def variants(self):
		return []

	@classmethod
	def voiceInfoToMetadata(cls, voice):
		localeName = voice.language or "unknown"
		langDescription = languageHandler.getLanguageDescription(localeName)
		if not langDescription:
			if " - " in voice.displayName:
				langDescription = voice.displayName.split(" - ", 1)[1]
			else:
				langDescription = localeName
		return {
			"id": voice.id,
			"name": getVoiceKey(cls.engine, voice.id),
			"locale": localeName,
			"language": localeName,
			"langDescription": langDescription,
			"description": "%s - %s [%s]" % (voice.displayName, langDescription, cls.engine),
			"engine": cls.engine,
		}

	@classmethod
	def voices(cls):
		result = []
		if not cls.ready() or not cls.core:
			return result

		try:
			voices = cls.core.availableVoices.values()
		except Exception:
			return result

		for voice in voices:
			result.append(cls.voiceInfoToMetadata(voice))

		return result

	@classmethod
	def supportedSettings(cls):
		if cls.synth_driver_class:
			try:
				return [i.id for i in cls.synth_driver_class.supportedSettings]
			except TypeError:
				return []
		else:
			return []

	@classmethod
	def ready(cls):
		return True

	@classmethod
	def engineOn(cls):
		if not cls.core:
			cls.core = cls.synth_driver_class()
			cls.core.wv = cls.engine

	@classmethod
	def engineOff(cls):
		try:
			if cls.core:
				cls.core.terminate()
		finally:
			cls.session = None
			cls.core = None
			cls._runtime_binding = None
