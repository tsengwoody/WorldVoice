#aisound.py
#A part of NVDA AiSound 5 Synthesizer Add-On

from collections import OrderedDict
from . import _aisound
import config
import speech
import weakref
from logHandler import log
from synthDriverHandler import SynthDriver,VoiceInfo,synthIndexReached,synthDoneSpeaking


class SynthDriver(SynthDriver):

	name="aisound"
	description="AiSound 5"

	supportedCommands={
		speech.commands.IndexCommand,
		speech.commands.CharacterModeCommand,
	}

	supportedNotifications={
		synthIndexReached,
		synthDoneSpeaking
	}

	supportedSettings=(
		SynthDriver.VoiceSetting(),
		SynthDriver.RateSetting(),
		SynthDriver.PitchSetting(),
		SynthDriver.InflectionSetting(),
		SynthDriver.VolumeSetting()
	)

	_voiceDict=OrderedDict([
		("BabyXu",VoiceInfo("BabyXu",_("Baby Xu, Mandarin"),"zh_CN")),
		("DaLong",VoiceInfo("DaLong",_("Da Long, Cantonese"),"zh_HK")),
		("DonaldDuck",VoiceInfo("DonaldDuck",_("Donald Duck, Mandarin"),"zh_CN")),
		("DuoXu",VoiceInfo("DuoXu",_("Duo Xu, Mandarin"),"zh_CN")),
		("JiuXu",VoiceInfo("JiuXu",_("Jiu Xu, Mandarin"),"zh_CN")),
		("XiaoFeng",VoiceInfo("XiaoFeng",_("Xiao Feng, Mandarin"),"zh_CN")),
		("XiaoMei",VoiceInfo("XiaoMei",_("Xiao Mei, Cantonese"),"zh_HK")),
		("XiaoPing",VoiceInfo("XiaoPing",_("Xiao Ping, Mandarin"),"zh_CN")),
		("YanPing",VoiceInfo("YanPing",_("Yan Ping, Mandarin"),"zh_CN")),
	])

	# Setup default parameters
	_voice="YanPing"
	_rate=50
	_pitch=50
	_inflection=50
	_volume=100

	@classmethod
	def check(cls):
		# This synthesizer is always available
		return True

	def __init__(self):
		_aisound.Initialize(weakref.ref(self))

		# Setup output device with backward compatibility
		try:
			# Try the new path first (NVDA 2025.1+)
			device = config.conf["audio"]["outputDevice"]
		except KeyError:
			# Fallback to the old path for older NVDA versions
			device = config.conf["speech"]["outputDevice"]
		_aisound.Configure("device", device)

		# Apply default parameters
		self.voice=self._voice
		self.rate=self._rate
		self.pitch=self._pitch
		self.inflection=self._inflection
		self.volume=self._volume

	def terminate(self):
		_aisound.Terminate()

	def speak(self,speechSequence):
		charMode=False
		for item in speechSequence:
			if isinstance(item,str):
				if charMode:
					text=' '.join([x for x in item])
				else:
					text=item
				_aisound.Speak(text,None)
			elif isinstance(item,speech.commands.IndexCommand):
				_aisound.Speak("",item.index)
			elif isinstance(item,speech.commands.CharacterModeCommand):
				charMode=item.state
			elif isinstance(item,speech.commands.SpeechCommand):
				log.debugWarning("Unsupported speech command: %s"%item)
			else:
				log.error("Unknown speech: %s"%item)

	def _get_lastIndex(self):
		return _aisound.lastIndex

	def cancel(self):
		_aisound.Cancel()

	def _getAvailableVoices(self):
		return self._voiceDict

	def _get_voice(self):
		return self._voice

	def _set_voice(self,voice):
		self._voice=voice
		_aisound.Configure("voice",voice)

	def _get_rate(self):
		return self._rate

	def _set_rate(self,rate):
		self._rate=rate
		value=self._percentToParam(rate,-32768,32767)
		_aisound.Configure("speed","%d"%value)

	def _get_pitch(self):
		return self._pitch

	def _set_pitch(self,pitch):
		self._pitch=pitch
		value=self._percentToParam(pitch,-32768,32767)
		_aisound.Configure("pitch","%d"%value)

	def _get_inflection(self):
		return self._inflection

	def _set_inflection(self,inflection):
		self._inflection=inflection
		value=self._percentToParam(inflection,0,2)
		_aisound.Configure("style","%d"%value)

	def _get_volume(self):
		return self._volume

	def _set_volume(self,volume):
		self._volume=volume
		value=self._percentToParam(volume,-32768,32767)
		_aisound.Configure("volume","%d"%value)

	def pause(self,switch):
		if switch:
			_aisound.Pause()
		else:
			_aisound.Resume()

	def _get_isSpeaking(self):
		return _aisound.isPlaying


# vim: set tabstop=4 shiftwidth=4 wm=0:
