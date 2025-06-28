from gui.settingsDialogs import VoiceSettingsPanel

class WorldVoiceVoiceSettingsPanel(VoiceSettingsPanel):
	"""
	A custom voice settings panel for WorldVoice.
	By ensuring the WorldVoice synth driver correctly implements the 'supportedSettings'
	property, this panel can be greatly simplified. It inherits all necessary UI
	creation logic from its parent classes (VoiceSettingsPanel and AutoSettingsMixin),
	which automatically build the settings interface based on 'supportedSettings'.
	No custom methods are needed here anymore.
	"""
	pass
