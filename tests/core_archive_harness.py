"""Load the core archive and install task modules with a recording logHandler."""

import types

from addon_loader import ADDON, load_source
from nvda_stubs import StubModules

INSTALL = ADDON / "installTasks.py"


def load(path, name, monkeypatch, logged):
	"""Load path as name, with log calls appended to logged as (level, *args)."""
	StubModules(monkeypatch).module(
		"logHandler",
		log=types.SimpleNamespace(
			info=lambda *a: logged.append(("info",) + a),
			warning=lambda *a: logged.append(("warning",) + a),
			error=lambda *a: logged.append(("error",) + a),
			exception=lambda *a: logged.append(("exception",) + a),
		),
	)
	return load_source(monkeypatch, name, path)
