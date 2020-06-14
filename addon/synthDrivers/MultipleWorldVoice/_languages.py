#vocalizer/_languages.py
#A part of the vocalizer driver for NVDA (Non Visual Desktop Access)
#Copyright (C) 2012, 2013 Rui Batista <ruiandrebatista@gmail.com>
#Copyright (C) 2012, 2013 Tiflotecnia, lda. <www.tiflotecnia.com>
#This file is covered by the GNU General Public License.
#See the file GPL.txt for more details.


# Conversion from Vocalizer proprietary locale naming to NVDA locales.
_vautoTLWToLocaleNames = {
	"ARW" : "ar", # Arabic
	"ENU" : "en_US", # American English
	"ENA" : "en_AU", # Australian English
	"BAE" : "eu", # Basque
	"DUB" : "nl_BE", # Belgian Dutch
	"PTB" : "pt_BR", # Brazilian Portuguese
	"ENG" : "en_GB", # British English
	"FRC" : "fr_CA", # Canadian French
	"CAE" : "ca", # Catalan
	"MNC" : "zh_CN", # Chinese Mandarin
	"CZC" : "cs_CZ", # Czech
	"DAD" : "da_DK", # Danish
	"DUN" : "nl_NL", # Dutch
	"FIF" : "fi_FI", # Finnish
	"FRF" : "fr_FR", # French
	"GED" : "de_DE", # German
	"GRG" : "el_GR", # Greek
	"HEI" : "he_IL", # Hebrew
	"HII" : "hi_IN", # Hindi
	"CAH" : "zh_HK", # Hong Kong Cantonese
	"HUH" : "hu_HU", # Hungarian
	"ENI" : "en_IN", # Indian English
	"IDI" : "id_ID", # Indonesian
	"ENE" : "en_IE", # Irish English
	"ITI" : "it_IT", # Italian
	"JPJ" : "ja_JP", # Japanese
	"KOK" : "ko_KR", # Korean
	"SPM" : "es_MX", # Mexican Spanish
	"NON" : "no", # Norwegian
	"PLP" : "pl_PL", # Polish
	"PTP" : "pt_PT", # Portuguese
	"ROR" : "ro_RO", # Romanian
	"RUR" : "ru_RU", # Russian
	"ENZ" : "en_ZA", # South African  English
	"ENS" : "en_SC", # Scotish English
	"SPE" : "es_ES", # Spanish (spain)
	"SKS" : "sk", # Slovac
	"SWS" : "sv_SE", # Swedish (Sweden)
	"MNT" : "zh_TW", # Taiwanese Mandarin
	"THT" : "th_TH", # Thai (tahiland)
	"TRT" : "tr_TR", # Turkish
	"GLE" : "gl_ES", # Galician (spain)
	"SPA" : "es_AR", # Spannish (argentina)
	"SPC" : "es_CO", # Spannish (colombia)
}


def getLocaleNameFromTLW(tlw):
	return _vautoTLWToLocaleNames.get(tlw, None)


