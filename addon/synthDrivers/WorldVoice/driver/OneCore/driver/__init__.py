from synthDrivers.oneCore import SynthDriver


class OneCoreSynthDriver(SynthDriver):
	def _get_voice(self):
		return self._language

	def _set_language(self, value):
		self._language = value
