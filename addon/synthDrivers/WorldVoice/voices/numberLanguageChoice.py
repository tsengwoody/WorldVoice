"""The number language a user stored, and the one speech uses.

Portable core: it reads the voice manager's locales and imports only the number-language values.
"""

from ..numberLanguage import FOLLOW, MAIN


class NumberLanguageChoice:
	"""The number language the user stored, and the one speech uses.

	manager gives the locales of the voices offered now (languages) and of every installed voice
	(all_languages); both are read on each call, as voices come and go with the settings.
	"""

	def __init__(self, manager):
		self._manager = manager
		self._value = FOLLOW

	def is_storable(self, value):
		# Any installed voice's locale, also one the voice settings hide for now.
		return value in (FOLLOW, MAIN) or value in self._manager.all_languages

	@property
	def stored(self):
		"""The stored choice, which NVDA saves back: a locale hidden by a voice or engine change is
		kept, so it comes back when its voices are offered again."""
		return self._value if self.is_storable(self._value) else FOLLOW

	def store(self, value):
		"""Keep value; False when it is not a choice and FOLLOW is kept instead.

		NVDA stores any string; one that is not a choice would leave the Voice panel without a
		selection and break the settings ring, so it reads as the default (no migration).
		"""
		accepted = self.is_storable(value)
		self._value = value if accepted else FOLLOW
		return accepted

	@property
	def spoken(self):
		"""The number language speech uses: a stored locale that no offered voice speaks is FOLLOW."""
		value = self.stored
		return value if value in (FOLLOW, MAIN) or value in self._manager.languages else FOLLOW

	def listed_locales(self):
		"""Each offered locale, then the stored one when no offered voice speaks it.

		A stored locale that "Keep main locale engine consistent" hides stays listed, so the Voice
		panel and the settings ring find the current value.
		"""
		locales = list(self._manager.languages)
		stored = self.stored
		if stored not in (FOLLOW, MAIN) and stored not in locales:
			locales.append(stored)
		return locales
