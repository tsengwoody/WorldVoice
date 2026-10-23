"""The two stored number-language values that are not locales.

This module imports nothing, so the language detector can read the values without the pipeline
package or any NVDA module.
"""

# Digits are read in the language of the text around them; the stored default.
FOLLOW = "default"
# Digits are read in the main language: the language the document marks, or the synth's.
MAIN = "main"
