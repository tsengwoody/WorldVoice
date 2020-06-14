# CJKEnhancedUI

Version 1.2.1

Customizations and enhancements by Michael M Chen <nvda.conceptsphere@gmail.com>

Tested by 蔡宗豪 Victor Cai <surfer0627@gmail.com>

A global plug-in intended for the CJK locales

Utilizing the character processing framework, several enhancements are implemented for a more user friendly experience.

Speech review mode and Braille review mode can be toggled independently with NVDA+0 and NVDA+=(equals) respectively.

## Summary of the speech review mode

Moving the system or review cursor automatically speaks the first character description for non English characters.

Pressing numpad2 [or NVDA+.(dot) for laptop] speaks the next character description.

Pressing Shift+numPad2 or NVDA+Shift+,(comma) for laptop speaks the previous character description.

Typing into the input composition window automatically speaks the first character description for single characters.

## Summary of the Braille review mode

There are three modes: "Off", "On", and "Auto".

*	Braille review mode off: performs default Braille display behavior.
*	Braille review mode on: pressing numpad2 [or nvda+.(dot)] displays the character descriptions.
*	Braille review mode auto: moving the system or review cursor within a region  of text automatically displays the character descriptions.

For "On" and "Auto" mode, typing into the input composition window automatically displays character descriptions for single characters.

## update log

v1.2.1: Fix bug(Pressing numPad2 can't speak current character) by Tseng Woody.

v1.3: Upgrading to compatible with NVDA 2019.3 and Python 3 by Tseng Woody.
