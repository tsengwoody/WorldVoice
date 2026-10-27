"""Base class every engine wrapper (built-in or WorldVoice-workspace plugin) subclasses.

Voice gives a wrapper its engine metadata and lifecycle, backed by the runtime voice facade.
Plugins import this module as synthDrivers.WorldVoice.driver (Voice, getVoiceKey), so that
import path is public API: the rest of the add-on may move, this module may not.
"""

import languageHandler

from ..bridge.voiceFacade import VoiceFacade


def getVoiceKey(engine, voiceId):
	return f"{engine}:{voiceId}"


class Voice(VoiceFacade):
	"""One engine's metadata and core factory; instances are bound voices.

	The engine adapter owns the core: create_core either returns a working core
	or raises without leaving one behind, and destroy_core releases it.
	"""

	engine = ""
	synthDriverClass = None
	extraCapabilities = frozenset()
	drainProfile = None

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
			"description": f"{voice.displayName} - {langDescription} [{cls.engine}]",
			"engine": cls.engine,
		}

	@classmethod
	def voices(cls, core):
		# Engine discovery loads only classes whose ready() is true.
		result = []
		if not core:
			return result

		try:
			voices = core.availableVoices.values()
		except Exception:  # noqa: BLE001 - an engine without voice metadata contributes no voices
			return result

		for voice in voices:
			result.append(cls.voiceInfoToMetadata(voice))

		return result

	@classmethod
	def supportedSettings(cls):
		if cls.synthDriverClass:
			try:
				return [i.id for i in cls.synthDriverClass.supportedSettings]
			except TypeError:
				return []
		else:
			return []

	@classmethod
	def ready(cls):
		return True

	@classmethod
	def create_core(cls):
		return cls.synthDriverClass()

	@classmethod
	def destroy_core(cls, core):
		core.terminate()
