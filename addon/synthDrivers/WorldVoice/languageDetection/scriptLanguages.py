"""The candidate languages of each Unicode script, and the scripts whose assumed language the user picks.

Standard library only, so the tables load without NVDA: the settings, the settings panel and the
detector all read them from here.
"""

from dataclasses import dataclass

BASIC_LATIN = (
	"en",
	"ha",
	"so",
	"id",
	"la",
	"sw",
	"eu",
	"nr",
	"zu",
	"xh",
	"ss",
	"st",
	"tn",
	"ts",
)
EXTENDED_LATIN = (
	"cs",
	"af",
	"pl",
	"hr",
	"ro",
	"sk",
	"sl",
	"tr",
	"hu",
	"az",
	"et",
	"sq",
	"ca",
	"es",
	"gl",
	"fr",
	"de",
	"nl",
	"it",
	"da",
	"is",
	"nb",
	"sv",
	"fi",
	"lv",
	"pt",
	"ve",
	"lt",
	"tl",
	"cy",
	"vi",
	"no",
	"uz",
)
ALL_LATIN = BASIC_LATIN + EXTENDED_LATIN

CYRILLIC = ("ru", "uk", "be", "kk", "tt", "uz", "mn", "sr", "mk", "bg", "ky")
ARABIC = ("ar", "fa", "ps", "ur")
DEVANAGARI = ("hi", "sa", "mr", "ne")
CJK = ("zh", "ja", "ko")

SCRIPT_LANGUAGES = {
	"Latin": ALL_LATIN,
	"Cyrillic": CYRILLIC,
	"Arabic": ARABIC,
	"Devanagari": DEVANAGARI,
	"Han": CJK,
	"Hiragana": ("ja",),
	"Katakana": ("ja",),
	"Hangul": ("ko",),
	"Bopomofo": ("zh",),
	"Armenian": ("hy",),
	"Hebrew": ("he",),
	"Bengali": ("bn",),
	"Gurmukhi": ("pa",),
	"Greek": ("el",),
	"Gujarati": ("gu",),
	"Oriya": ("or",),
	"Tamil": ("ta",),
	"Telugu": ("te",),
	"Kannada": ("kn",),
	"Malayalam": ("ml",),
	"Sinhala": ("si",),
	"Thai": ("th",),
	"Lao": ("lo",),
	"Tibetan": ("bo",),
	"Myanmar": ("my",),
	"Georgian": ("ka",),
	"Mongolian": ("mn",),
	"Khmer": ("km",),
}


@dataclass(frozen=True)
class DetectionScript:
	"""A script whose assumed language the user chooses."""

	# The Unicode script name, as unicodeScripts.lookup.get_script returns it; a key of SCRIPT_LANGUAGES.
	script: str
	# Where config["WorldVoice"]["autoLanguageSwitching"] stores the choice.
	config_key: str
	# The language assumed until the user chooses one.
	default_language: str


# The one list of these scripts, in the Unicode Detection panel's order: the config keys, their
# defaults and the panel's choices are all derived from it.
DETECTION_SCRIPTS: tuple[DetectionScript, ...] = (
	DetectionScript("Latin", "latinCharactersLanguage", "en"),
	DetectionScript("Han", "cjkCharactersLanguage", "ja"),
	DetectionScript("Arabic", "arabicCharactersLanguage", "ar"),
	# The first candidates of their scripts, which detection took before these choices existed.
	DetectionScript("Cyrillic", "cyrillicCharactersLanguage", "ru"),
	DetectionScript("Devanagari", "devanagariCharactersLanguage", "hi"),
)
