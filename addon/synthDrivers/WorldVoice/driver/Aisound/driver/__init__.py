#__init__.py
#A part of NVDA AiSound 5 Synthesizer Add-On

from buildVersion import version_year

if version_year >= 2026:
	from .aisoundProxy32 import SynthDriver
else:
	from .aisound import SynthDriver
