import os
import sys
from collections import OrderedDict
from typing import Any

import addonHandler
import config
import extensionPoints
import gui
import languageHandler
import speech
import versionInfo
from autoSettingsUtils.driverSetting import BooleanDriverSetting, DriverSetting, NumericDriverSetting
from autoSettingsUtils.utils import StringParameterInfo
from logHandler import log as nvdaLog
from speech.commands import (
	BreakCommand,
	CharacterModeCommand,
	IndexCommand,
	LangChangeCommand,
	PitchCommand,
	RateCommand,
	VolumeCommand,
)
from speech.extensions import filter_speechSequence
from synthDriverHandler import SynthDriver, getSynth, synthDoneSpeaking, synthIndexReached

from . import languageDetection
from .assembly import Teardown, patch_attribute, timed
from .compat.commands import normalize_legacy_commands
from .compat.completionPolicies import CompletionPolicy
from .configRepository import VOICE_CONFSPEC, ConfigVoiceSettingsRepository
from .engine import ready_engine_classes
from .indexLedger import IndexLedger
from .languageDetection.settings import DETECTION_CONFSPEC, detection_settings
from .numberLanguage import FOLLOW
from .nvdaEventBridge import NvdaEventBridge
from .pipeline import (
	LOG_SWITCHES,
	deduplicate_language_command,
	detect_with_number_language,
	inject_langchange_reorder,
	lang_cmd_to_voice,
	listable,
	order_move_to_start_register,
)
from .pipeline.context import GENERIC_CONTEXT, SpeechContext
from .pipeline.scope import pipeline_scope
from .pipeline.settings import (
	NUMBER_LANGUAGE_CHOICES,
	NUMBER_MODE_CHOICES,
	PIPELINE_CONFSPEC,
	PIPELINE_SETTINGS,
	pipeline_settings,
)
from .runtime.requestBuilder import queue_speech_sequence
from .runtime.scheduler import TaskManager
from .runtime.settings import VoiceSettingsStore
from .voiceManager import VoiceManager
from .VoiceSettingsDialogs import WorldVoiceVoiceSettingsPanel

_: Any

# The add-on root stays on sys.path although this package imports nothing from it: the
# global plugin imports generics.coreArchive after importing this package.
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base_dir)

addonHandler.initTranslation()

config.conf.spec["WorldVoice"] = {
	"autoLanguageSwitching": {
		**DETECTION_CONFSPEC,
		"KeepMainLocaleVoiceConsistent": "boolean(default=true)",
		"KeepMainLocaleParameterConsistent": "boolean(default=false)",
		"KeepMainLocaleEngineConsistent": "boolean(default=true)",
	},
	"pipeline": dict(PIPELINE_CONFSPEC),
	"role": {},
	"engine": {
		"__many__": "boolean(default=false)",
	},
	"log": {
		"enable": "boolean(default=false)",
		**{key: "boolean(default=false)" for key in LOG_SWITCHES},
	},
	"voices": {"__many__": dict(VOICE_CONFSPEC)},
}

WVStart = extensionPoints.Action()
WVEnd = extensionPoints.Action()


class SynthDriver(SynthDriver):
	name = "WorldVoice"
	description = "WorldVoice"
	supportedCommands = {  # noqa: RUF012
		IndexCommand,
		CharacterModeCommand,
		LangChangeCommand,
		BreakCommand,
		PitchCommand,
		RateCommand,
		VolumeCommand,
	}
	supportedNotifications = {synthIndexReached, synthDoneSpeaking}  # noqa: RUF012

	@classmethod
	def check(cls):
		return True

	@staticmethod
	def _pipeline_driver_setting(spec):
		# An ordering-only entry (number language) is stored by NVDA; the others in the pipeline section.
		options = {
			"availableInSettingsRing": spec.ring,
			"defaultVal": spec.default,
			"useConfig": not spec.pipeline_config,
		}
		if spec.display_name is not None:
			options["displayName"] = spec.display_name
		if spec.kind is bool:
			return BooleanDriverSetting(spec.driver_id, spec.label, **options)
		if spec.kind is int:
			return NumericDriverSetting(
				spec.driver_id,
				spec.label,
				minVal=spec.min_value,
				maxVal=spec.max_value,
				minStep=spec.min_step,
				**options,
			)
		return DriverSetting(spec.driver_id, spec.label, **options)

	def _driver_settings(self, capabilities):
		"""The synth settings; ``capabilities`` None lists every optional voice setting."""
		settings = [SynthDriver.VoiceSetting(), SynthDriver.VariantSetting(), SynthDriver.RateSetting()]
		if capabilities is None or "rateBoost" in capabilities:
			settings.append(SynthDriver.RateBoostSetting())
		settings.append(SynthDriver.PitchSetting())
		if capabilities is None or "inflection" in capabilities:
			settings.append(SynthDriver.InflectionSetting())
		settings.append(SynthDriver.VolumeSetting())
		settings.append(
			BooleanDriverSetting(
				"uwv",
				_("Detect language based on Unicode characters"),
				availableInSettingsRing=True,
				defaultVal=True,
				displayName=_("Detect language based on Unicode characters"),
			),
		)
		for spec in PIPELINE_SETTINGS:
			if spec.driver_id is None:
				continue
			settings.append(self._pipeline_driver_setting(spec))
		return settings

	@property
	def supportedSettings(self):
		capabilities = self._voiceManager.getVoiceCapabilities(self._voiceManager.defaultVoiceName)
		return self._driver_settings(capabilities.settings)

	@property
	def allSupportedSettings(self):
		return self._driver_settings(None)

	_TEARDOWN_ORDER = (
		"task manager shutdown",
		"detection settings unsubscribe",
		"language detection unregister",
		"pipeline cleanup",
		"voice settings panel restore",
		"spelling function restore",
		"event bridge close",
		"pipeline settings unsubscribe",
		"voice manager terminate",
		"index ledger close",
		"end notification",
	)

	def __init__(self):
		self._terminated = False
		self._terminateCommit = True
		self._numlan = FOLLOW
		self._realSpellingFunc = None
		self.taskManager = None
		self._voiceManager = None
		self._eventBridge = None
		self._settingsStore = None
		self._indexLedger = None
		self._teardown = Teardown(self._TEARDOWN_ORDER, nvdaLog)
		try:
			self._initialize()
		except BaseException:
			# Release acquired resources even on KeyboardInterrupt, then re-raise.
			self.terminate(commit=False)
			raise

	def _initialize(self):
		with timed(nvdaLog, "total"):
			with timed(nvdaLog, "WVStart.notify"):
				self._teardown.add("end notification", WVEnd.notify)
				WVStart.notify()

			with timed(nvdaLog, "voice settings panel patch"):
				self._teardown.add(
					"voice settings panel restore",
					patch_attribute(gui.settingsDialogs, "VoiceSettingsPanel", WorldVoiceVoiceSettingsPanel),
				)

			with timed(nvdaLog, "TaskManager"):
				self._settingsStore = VoiceSettingsStore(ConfigVoiceSettingsRepository(config.conf))
				# One ledger spans every binding of a live core in this runtime. A core
				# handed to a new runtime must first close, or retain its original ledger.
				self._indexLedger = IndexLedger()
				self._teardown.add("index ledger close", self._indexLedger.close)
				self._eventBridge = NvdaEventBridge(
					self,
					done_event=synthDoneSpeaking,
					index_event=synthIndexReached,
					get_synth=getSynth,
					index_ledger=self._indexLedger,
				)
				self._teardown.add("event bridge close", self._eventBridge.close)
				tasks = self.taskManager = TaskManager(output=self._eventBridge, logger=nvdaLog)

				def shutdown_tasks():
					# The voice manager comes later, so it may not exist yet.
					manager = self._voiceManager
					tasks.shutdown(manager.playback_ports if manager is not None else ())

				self._teardown.add("task manager shutdown", shutdown_tasks)
				self._eventBridge.start(tasks.on_event, batch_handler=tasks.on_events)

			with timed(nvdaLog, "VoiceManager"):
				self._completionPolicy = CompletionPolicy(nvda_version=versionInfo.version, logger=nvdaLog)
				self._voiceManager = VoiceManager(
					taskManager=self.taskManager,
					settings=self._settingsStore,
					bridge=self._eventBridge,
					index_ledger=self._indexLedger,
					completion_for=self._completionPolicy.select,
					engine_classes=ready_engine_classes(config.conf["WorldVoice"]["engine"]),
					conf_provider=lambda: config.conf,
					get_language=languageHandler.getLanguage,
				)
				manager = self._voiceManager
				self._teardown.add(
					"voice manager terminate",
					lambda: manager.terminate(commit=self._terminateCommit),
				)

			self._apply_pipeline_settings(pipeline_settings.get())
			pipeline_settings.subscribe(self._apply_pipeline_settings)
			self._teardown.add(
				"pipeline settings unsubscribe",
				lambda: pipeline_settings.unsubscribe(self._apply_pipeline_settings),
			)

			with timed(nvdaLog, "speakSpelling patch"):
				self._realSpellingFunc = speech.speech.speakSpelling
				self._teardown.add(
					"spelling function restore",
					patch_attribute(speech.speech, "speakSpelling", self.patchedSpeakSpelling),
				)

			with timed(nvdaLog, "LanguageDetector"):
				self._languageDetector = languageDetection.LanguageDetector(
					list(self._voiceManager.allLanguages),
					settings=detection_settings,
					language=lambda: self.language,
					number_language=lambda: self._numlan,
				)
				self.add_detected_language_commands = listable(self._detect_languages)
				self._teardown.add(
					"language detection unregister",
					lambda: filter_speechSequence.unregister(self.add_detected_language_commands),
				)
				detection_settings.subscribe(self._on_detection_settings)
				self._teardown.add(
					"detection settings unsubscribe",
					lambda: detection_settings.unsubscribe(self._on_detection_settings),
				)

			self._voice = None

			# Stages see a fully built synth: voices and the number language exist.
			with timed(nvdaLog, "pipeline register"):
				self._teardown.add("pipeline cleanup", pipeline_scope.worldvoice_ended)
				pipeline_scope.worldvoice_started()

	def terminate(self, *, commit=True):
		if self._terminated:
			return
		self._terminated = True
		self._terminateCommit = commit
		try:
			self._teardown.run()
		finally:
			self.taskManager = self._eventBridge = self._voiceManager = self._indexLedger = None

	def loadSettings(self, *args, **kwargs):
		super().loadSettings(*args, **kwargs)
		# Pipeline settings are not NVDA driver config; re-read them for this profile.
		self._apply_pipeline_settings(pipeline_settings.get())
		self._voiceManager.reload()

	def _apply_pipeline_settings(self, settings):
		manager = self._voiceManager
		if manager is not None:
			manager.waitfactor = min(settings.global_wait_factor // 10, 9)

	def speak(self, speechSequence):
		if self._terminated:
			return
		if self.uwv and self._detectLanguageTiming() == "after":
			speechSequence = self.add_detected_language_commands(speechSequence)

		ctx = self.speech_context()
		speechSequence = inject_langchange_reorder(speechSequence)
		speechSequence = deduplicate_language_command(speechSequence, ctx)
		speechSequence = lang_cmd_to_voice(speechSequence, ctx)

		queue_speech_sequence(
			self.taskManager,
			normalize_legacy_commands(speechSequence),
			self._voiceManager.defaultVoiceName,
			self._voiceManager.resolve_playback,
		)

	def _detect_languages(self, speechSequence):
		# The number language decides the digits: the pipeline wraps each number for detection,
		# wherever detection runs (before NVDA's processing as a filter, or after it in speak).
		return detect_with_number_language(
			speechSequence,
			self._languageDetector.add_detected_language_commands,
			self.speech_context(),
		)

	def patchedSpeakSpelling(self, text, locale=None, useCharacterDescriptions=False, priority=None):
		if self.uwv and config.conf["speech"]["trustVoiceLanguage"]:
			for part, loc in self._languageDetector.process_for_spelling(text, locale):
				self._realSpellingFunc(part, loc, useCharacterDescriptions, priority=priority)
		else:
			self._realSpellingFunc(text, locale, useCharacterDescriptions, priority=priority)

	def cancel(self):
		if self._terminated:
			return
		self._voiceManager.cancel()

	def pause(self, switch):
		if self._terminated:
			return
		self.taskManager.pause_current(switch)

	@property
	def voice_manager(self):
		"""The voice manager the settings panels read; None after terminate."""
		return self._voiceManager

	def speech_context(self) -> SpeechContext:
		manager = self._voiceManager
		if manager is None:
			return GENERIC_CONTEXT
		voice = manager.defaultVoiceInstance
		return SpeechContext(
			supports_roles=True,
			language=self.language,
			number_language=self._numlan,
			default_voice_name=voice.name,
			default_voice_language=voice.language,
			voice_name_for_language=manager.getVoiceNameForLanguage,
			voice_locale_for_language=manager.getVoiceLocaleForLanguage,
		)

	def _set_voice_parameter(self, name, value):
		instance = self._voiceManager.defaultVoiceInstance
		setattr(instance, name, value)
		instance.commit()
		if self._voiceManager.parameter_consistency.enabled:
			self._voiceManager.onVoiceParameterConsistent(instance)

	def _get_volume(self):
		return self._voiceManager.defaultVoiceInstance.volume

	def _set_volume(self, value):
		self._set_voice_parameter("volume", value)

	def _get_rate(self):
		return self._voiceManager.defaultVoiceInstance.rate

	def _set_rate(self, value):
		self._set_voice_parameter("rate", value)

	def _get_pitch(self):
		return self._voiceManager.defaultVoiceInstance.pitch

	def _set_pitch(self, value):
		self._set_voice_parameter("pitch", value)

	def _get_inflection(self):
		return self._voiceManager.defaultVoiceInstance.inflection

	def _set_inflection(self, value):
		self._set_voice_parameter("inflection", value)

	def _getAvailableVoices(self):
		return self._voiceManager.voiceInfos

	def _get_voice(self):
		if self._voice is None:
			return self._voiceManager.getVoiceNameForLanguage(languageHandler.getLanguage())
		return self._voiceManager.defaultVoiceName

	def _set_voice(self, voiceName):
		if voiceName != self._voiceManager.defaultVoiceName:
			# Stop speech before setting a new voice to avoid voice instances
			# continuing speaking when changing voices for, e.g., say-all
			# See NVDA ticket #3540
			self._voiceManager.defaultVoiceInstance.stop()
			# Raises LookupError for an unavailable voice, before the choice is recorded.
			self._voiceManager.defaultVoiceName = voiceName
		self._voice = voiceName

	def _get_availableVariants(self):
		values = OrderedDict([("default", StringParameterInfo("default", _("default")))])
		for item in self._voiceManager.getVoiceVariants(self._voiceManager.defaultVoiceName):
			values[item["id"]] = StringParameterInfo(item["id"], item["name"])
		return values

	def _get_variant(self):
		return self._voiceManager.defaultVoiceInstance.variant

	def _set_variant(self, value):
		self._set_voice_parameter("variant", value)

	def _get_rateBoost(self):
		return self._voiceManager.defaultVoiceInstance.rateBoost

	def _set_rateBoost(self, enable):
		self._set_voice_parameter("rateBoost", enable)

	def _get_uwv(self):
		return self._uwv

	def _set_uwv(self, value):
		self._uwv = value
		self.refresh_language_detection()

	def _detectLanguageTiming(self):
		return detection_settings.get().timing

	def _on_detection_settings(self, settings, changed):
		# Only the timing decides the filter registration; refreshing also reorders NVDA's filters.
		if "timing" in changed:
			self.refresh_language_detection()

	def refresh_language_detection(self):
		"""Register language detection as an NVDA filter only when it runs before NVDA's processing.

		Called when uwv or the detection timing changes.
		"""
		if self.uwv and self._detectLanguageTiming() == "before":
			filter_speechSequence.register(self.add_detected_language_commands)
			order_move_to_start_register()
		else:
			filter_speechSequence.unregister(self.add_detected_language_commands)

	def _get_availableNumlans(self):
		values = {value: StringParameterInfo(value, label) for value, label in NUMBER_LANGUAGE_CHOICES}
		for locale in self._voiceManager.languages:
			values[locale] = StringParameterInfo(locale, self._numlanDisplayName(locale))
		return values

	def _get_numlan(self):
		return self._numlan

	def _set_numlan(self, value):
		self._numlan = value

	def _get_availableNummods(self):
		return {value: StringParameterInfo(value, label) for value, label in NUMBER_MODE_CHOICES}

	def _numlanDisplayName(self, locale):
		# Settings-ring entries show the language description only.
		description = languageHandler.getLanguageDescription(locale)
		return f"{description}" if description else locale


class _PipelineSetting:
	"""A synth attribute stored only in the pipeline config, never in NVDA's speech config."""

	def __init__(self, key):
		self._key = key

	def __get__(self, synth, owner=None):
		if synth is None:
			return self
		return getattr(pipeline_settings.get(), self._key)

	def __set__(self, synth, value):
		pipeline_settings.update(**{self._key: value})


for _spec in PIPELINE_SETTINGS:
	# An ordering-only entry keeps the driver's own property (numlan).
	if _spec.driver_id is not None and _spec.pipeline_config:
		setattr(SynthDriver, _spec.driver_id, _PipelineSetting(_spec.key))
