"""The WorldVoice-workspace directory: external engines and imported core files."""

import os

import globalVars

WORKSPACE_DIRNAME = "WorldVoice-workspace"


def workspace_path() -> str:
	"""Where external engines and imported core files live: NVDA's config directory."""
	return os.path.join(globalVars.appArgs.configPath, WORKSPACE_DIRNAME)
