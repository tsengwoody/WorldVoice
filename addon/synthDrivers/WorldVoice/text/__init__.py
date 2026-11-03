"""Text helpers shared by the speech synthesis drivers and the speech pipeline.

text.arabic is wrapper-facing: engine wrappers import it by absolute path
(synthDrivers.WorldVoice.text.arabic), so that path is public API and the package stays here.
text.chunker holds the segment cut rule the pipeline uses; its path stays public too, as a wrapper
copied from an older built-in one may still name it.
"""
