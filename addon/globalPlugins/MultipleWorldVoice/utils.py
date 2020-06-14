#vocalizer_globalPlugin/utils.py
#A part of the vocalizer driver for NVDA (Non Visual Desktop Access)
#Copyright (C) 2012 Rui Batista <ruiandrebatista@gmail.com>
#Copyright (C) 2012 Tiflotecnia, lda. <www.tiflotecnia.com>
#This file is covered by the GNU General Public License.
#See the file GPL.txt for more details.
import speech

_reentrancy = 0
_opened = False

class VocalizerOpened(object):
	def __enter__(self):
		global _opened, _reentrancy
		from synthDrivers import MultipleWorldVoice
		from synthDrivers.MultipleWorldVoice import _vocalizer
		if speech.getSynth().name != MultipleWorldVoice.SynthDriver.name and _reentrancy == 0:
			try:
				_vocalizer.initialize()
				_opened = True
			except _vocalizer.VeError as e:
				if e.code not in (_vocalizer.VAUTONVDA_ERROR_EXPIRED, _vocalizer.VAUTONVDA_ERROR_INVALID, _vocalizer.VAUTONVDA_ERROR_NOLICENSE, _vocalizer.VAUTONVDA_ERROR_DEMO_EXPIRED):
					raise
		_reentrancy += 1
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		global _opened, _reentrancy
		from synthDrivers import MultipleWorldVoice
		from synthDrivers.MultipleWorldVoice import _vocalizer
		_reentrancy -= 1
		if speech.getSynth().name != MultipleWorldVoice.SynthDriver.name and _opened and _reentrancy == 0:
			try:
				_vocalizer.terminate()
			except _vocalizer.VeError:
				pass
		return False

