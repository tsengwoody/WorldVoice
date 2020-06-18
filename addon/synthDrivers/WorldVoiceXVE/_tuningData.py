#vocalizer/_tuningData.py
#A part of the vocalizer driver for NVDA (Non Visual Desktop Access)
#Copyright (C) 2012 Rui Batista <ruiandrebatista@gmail.com>
#Copyright (C) 2012 Tiflotecnia, lda. <www.tiflotecnia.com>
#This file is covered by the GNU General Public License.
#See the file GPL.txt for more details.
import os.path
from . import _vocalizer
from logHandler import log

BIN_DICT_CONTENT_TYPE = "application/edct-bin-dictionary"
TEXT_RULESET_CONTENT_TYPE = "application/x-vocalizer-rettt+text"

_tuningDataDir = os.path.join(os.path.dirname(__file__), "tuningData")

_voiceDicts = {}

def onVoiceLoad(instance, voiceName):
	# Ruleset
	rulesetPath = os.path.join(_tuningDataDir, "%s.rules" % voiceName.lower())
	if os.path.exists(rulesetPath):
		with open(rulesetPath, "rb") as f:
			content = f.read()
		log.debug("Loading ruleset from %s", rulesetPath)
		try:
			_vocalizer.resourceLoad(TEXT_RULESET_CONTENT_TYPE, content, instance)
		except _vocalizer.VeError:
			log.warning("Error Loading vocalizer rules from %s", rulesetPath, exc_info=True)
	# Load custom dictionary if one exists
	if voiceName not in _voiceDicts:
		dictPath = os.path.join(_tuningDataDir, "%s.dcb" % voiceName.lower())
		if os.path.exists(dictPath):
			with open(dictPath, "rb") as f:
				_voiceDicts[voiceName] = f.read()
				log.debug("Loading vocalizer dictionary from %s", dictPath)
	if voiceName in _voiceDicts:
		try:
			_vocalizer.resourceLoad(BIN_DICT_CONTENT_TYPE, _voiceDicts[voiceName], instance)
		except _vocalizer.VeError:
			log.warning("Error loading Vocalizer dictionary.", exc_info=True)
