# Conversion from Vocalizer proprietary locale naming to NVDA locales.
_vautoTLWToLocaleNames = {
	"ARW": "ar", # Arabic
	"ARG": "ar", # Gulf Arabic
	"ENU": "en_US", # American English
	"ENA": "en_AU", # Australian English
	"BAE": "eu", # Basque
	"BGB": "bg", # Bulgarian
	"DUB": "nl_BE", # Belgian Dutch
	"PTB": "pt_BR", # Brazilian Portuguese
	"ENG": "en_GB", # British English
	"FRB": "fr_BE", # Belgian French
	"FRC": "fr_CA", # Canadian French
	"FAI": "fa_IR", # Farsi
	"MSM": "ms_MS", # Malay
	"VIV": "vi_VN", # Vietnamese
	"CAE": "ca", # Catalan
	"SXC": "sx_CN", # Chinese Shanxiese
	"SHC": "sh_CN", # Chinese Shanhaiese
	"DOC": "db_CN", # Chinese Dontbei
	"SIC": "sc_CN", # Chinese Sichuanese
	"MNC": "zh_CN", # Chinese Mandarin
	"MNT": "zh_TW", # Taiwanese Mandarin
	"CAH": "zh_HK", # Hong Kong Cantonese
	"CZC": "cs_CZ", # Czech
	"HRH": "hr_HR", # Croatian
	"BHI": "bh_IN", # bhojpuri
	"BEI": "bn_IN", # bengali
	"KAI": "kn_IN", # kannada
	"MAI": "mr_IN", # marathi
	"SPL": "es_CH", # spanish chile
	"SLS": "SL_SI", # Slovenian
	"TAI": "ta_IN", # tamil
	"TEI": "te_IN", # telugu
	"DAD": "da_DK", # Danish
	"DUN": "nl_NL", # Dutch
	"FIF": "fi_FI", # Finnish
	"FRF": "fr_FR", # French
	"GED": "de_DE", # German
	"GRG": "el_GR", # Greek
	"HEI": "he_IL", # Hebrew
	"HII": "hi_IN", # Hindi
	"HUH": "hu_HU", # Hungarian
	"ENI": "en_IN", # Indian English
	"IDI": "id_ID", # Indonesian
	"ENE": "en_IE", # Irish English
	"ITI": "it_IT", # Italian
	"JPJ": "ja_JP", # Japanese
	"KOK": "ko_KR", # Korean
	"SPM": "es_MX", # Mexican Spanish
	"NON": "no", # Norwegian
	"PLP": "pl_PL", # Polish
	"PTP": "pt_PT", # Portuguese
	"ROR": "ro_RO", # Romanian
	"RUR": "ru_RU", # Russian
	"UKU": "uk_UA", # Ukrainian
	"ENZ": "en_ZA", # South African  English
	"ENS": "en_SC", # Scottish English
	"SPE": "es_ES", # Spanish (spain)
	"SKS": "sk", # Slovac
	"SWS": "sv_SE", # Swedish (Sweden)
	"THT": "th_TH", # Thai (tahiland)
	"TRT": "tr_TR", # Turkish
	"GLE": "gl_ES", # Galician (spain)
	"VAE": "ca", # Catalan (spain)
	"SPA": "es_AR", # Spannish (argentina)
	"SPC": "es_CO", # Spannish (colombia)
}

def getLocaleNameFromTLW(tlw):
	return _vautoTLWToLocaleNames.get(tlw, None)
