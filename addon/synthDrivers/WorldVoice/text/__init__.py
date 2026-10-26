"""Engine-side text preprocessing shared by speech synthesis drivers.

Wrapper-facing: engine wrappers import text.arabic and text.chunker by absolute path
(synthDrivers.WorldVoice.text...), so this import path is public API and the package stays here.
"""
