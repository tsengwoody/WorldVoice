"""The running NVDA's name and version, for the engine wrappers' ready() log lines."""


def nvdaLabel():
	# Imported here: the NVDA version is read only to name it in a log line.
	import versionInfo

	return f"NVDA {versionInfo.version}"
