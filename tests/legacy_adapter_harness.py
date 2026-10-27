"""A recording engine core and the legacy Voice class that owns it, for VoiceClassAdapter tests."""


class Core:
	def __init__(self):
		object.__setattr__(self, "writes", [])
		self.spoken = []
		self.paused = []
		self.cancelled = 0
		self.writes.clear()

	def __setattr__(self, name, value):
		self.writes.append((name, value))
		object.__setattr__(self, name, value)

	def speak(self, commands, **kwargs):
		self.spoken.append((commands, kwargs))

	def cancel(self):
		self.cancelled += 1

	def pause(self, switch):
		self.paused.append(switch)


def legacy_class(core):
	class Legacy:
		opens = closes = 0

		@classmethod
		def createCore(cls):
			cls.opens += 1
			return core

		@classmethod
		def destroyCore(cls, target):
			assert target is core
			cls.closes += 1

		@classmethod
		def supportedSettings(cls):
			return ["voice", "rateBoost", "rate", "pitch", "volume", "inflection"]

		@classmethod
		def voices(cls, target):
			assert target is core
			return [
				{
					"id": "a",
					"name": "Fake:a",
					"description": "A",
					"language": "en",
					"engine": "Fake",
					"locale": "en",
					"langDescription": "English",
				},
			]

		def active(self):
			raise AssertionError("Adapter must not call legacy active")

		def speak(self, *args):
			raise AssertionError("Adapter must not call legacy speak")

		def applyEngineSettings(self, core, snapshot):
			core.hook = snapshot.variant

		@property
		def variants(self):
			return [{"id": "bright", "name": "Bright"}]

	return Legacy
