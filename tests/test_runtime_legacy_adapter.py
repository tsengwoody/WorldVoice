import ast
import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

from runtime_harness import MemoryRepository, RUNTIME, make_spec, rt
from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs


@pytest.fixture
def compat(monkeypatch, rt):
    name = "worldvoice_compat_test"
    package = ModuleType(name)
    package.__path__ = [str(RUNTIME.parent)]
    monkeypatch.setitem(sys.modules, name, package)
    for suffix, module in (("", rt.package), (".models", rt.models),
                           (".settings", rt.settings), (".session", rt.session)):
        monkeypatch.setitem(sys.modules, name + ".runtime" + suffix, module)
    # Remove cached compatibility imports between isolated runtime fixtures.
    for suffix in ("compat", "compat.engineAdapter", "compat.voiceFacade"):
        monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
    return SimpleNamespace(
        adapter=importlib.import_module(name + ".compat.engineAdapter"),
        facade=importlib.import_module(name + ".compat.voiceFacade"),
    )


class Core:
    def __init__(self):
        object.__setattr__(self, "writes", [])
        self.spoken = []
        self.paused = []
        self.cancelled = 0
        self.writes.clear()

    def __setattr__(self, name, value):
        self.writes.append((name, value))
        object.__setattr__(self, name, value)

    def speak(self, commands, **kwargs):
        self.spoken.append((commands, kwargs))

    def cancel(self):
        self.cancelled += 1

    def pause(self, switch):
        self.paused.append(switch)


def legacy_class(core):
    class Legacy:
        opens = closes = 0
        session = None

        @classmethod
        def engineOn(cls):
            cls.opens += 1
            cls.core = core

        @classmethod
        def engineOff(cls):
            cls.closes += 1
            cls.core = cls.session = None

        @classmethod
        def supportedSettings(cls):
            return ["voice", "rateBoost", "rate", "pitch", "volume", "inflection"]

        @classmethod
        def voices(cls):
            return [dict(id="a", name="Fake:a", description="A", language="en",
                         engine="Fake", locale="en", langDescription="English")]

        def active(self):
            raise AssertionError("Adapter must not call legacy active")

        def speak(self, *args):
            raise AssertionError("Adapter must not call legacy speak")

        def applyEngineSettings(self, core, snapshot):
            core.hook = snapshot.variant

        @property
        def variants(self):
            return [{"id": "bright", "name": "Bright"}]

    Legacy.core = None
    return Legacy


def test_lifecycle_metadata_and_apply_order(compat, rt):
    core = Core()
    cls = legacy_class(core)
    adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
    adapter.open()
    adapter.open()
    assert cls.opens == 1
    assert adapter.notification_source is core
    spec = adapter.list_voices()[0]
    assert spec == rt.models.VoiceSpec("a", "Fake:a", "A", "en", "Fake", "en")
    assert adapter.variants(spec.name) == ({"id": "bright", "name": "Bright"},)
    assert core.writes == []
    snapshot = rt.settings.VoiceState(spec, {"rate": 72, "rateBoost": True}).snapshot()
    adapter.apply(spec, snapshot)
    assert core.writes == [("voice", "a"), ("rateBoost", True), ("rate", 72),
                           ("pitch", 50), ("volume", 50), ("inflection", 50),
                           ("hook", "default")]
    adapter.cancel()
    adapter.pause(True)
    adapter.pause(False)
    assert core.cancelled == 1
    assert core.paused == [True, False]
    adapter.close()
    adapter.close()
    assert cls.closes == 1
    assert cls.core is None
    adapter.open()
    adapter.close()
    assert (cls.opens, cls.closes) == (2, 2)


@pytest.mark.parametrize("support", [True, False, None])
def test_token_support_comes_from_actual_core(compat, support):
    core = Core()
    if support is not None:
        core.supportsCancellationToken = support
    cls = legacy_class(core)
    cls.supportsCancellationToken = True  # Class claims are not authoritative.
    adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
    adapter.open()
    token = SimpleNamespace(is_cancelled=lambda: False)
    adapter.speak(("hello",), token)
    assert core.spoken == [(("hello",), {"cancellationToken": token} if support else {})]
    assert adapter.capabilities.supports_cancellation_token is bool(support)
    assert adapter.capabilities.supports_variants is False
    assert adapter.capabilities.supports_waitfactor is False


def test_unsupported_generic_settings_are_not_written(compat, rt):
    core = Core()
    cls = legacy_class(core)
    cls.supportedSettings = classmethod(lambda cls: ["rate"])
    adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
    adapter.open()
    state = rt.settings.VoiceState(make_spec(), {})
    adapter.apply(state.spec, state.snapshot())
    assert core.writes == [("voice", "a"), ("rate", 50), ("hook", "default")]
    assert adapter.capabilities.settings == frozenset({"rate"})


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_partial_engine_open_is_cleaned_once(compat, rt, cleanup_fails):
    core = Core()
    cls = legacy_class(core)

    def fail_open(cls):
        cls.core = core
        raise ValueError("open failed")

    def cleanup(cls):
        cls.closes += 1
        cls.core = None
        if cleanup_fails:
            raise OSError("cleanup failed")

    cls.engineOn = classmethod(fail_open)
    cls.engineOff = classmethod(cleanup)
    adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
    session = rt.session.EngineSession(adapter, rt.settings.VoiceSettingsStore(MemoryRepository()))
    with pytest.raises(ValueError, match="open failed") as caught:
        session.open()
    session.close()
    adapter.close()
    assert cls.closes == 1
    assert cls.core is None
    if cleanup_fails:
        assert isinstance(caught.value.__cause__, OSError)


def test_alias_detach_preserves_shared_resource_owner(compat):
    core = Core()
    owner_cls, alias_cls = legacy_class(core), legacy_class(core)
    owner = compat.adapter.LegacyEngineAdapter(owner_cls, lambda key: owner_cls())
    alias = compat.adapter.LegacyEngineAdapter(alias_cls, lambda key: alias_cls())
    owner.open()
    alias.open()
    alias_cls.session = object()
    alias_cls._runtime_binding = object()
    alias.detach_alias()
    alias.close()
    assert (alias_cls.core, alias_cls.session, alias_cls._runtime_binding) == (None, None, None)
    assert owner_cls.core is core
    assert (owner_cls.closes, alias_cls.closes) == (0, 0)
    owner.close()
    assert (owner_cls.closes, alias_cls.closes) == (1, 0)


def test_onecore_cached_a_b_a_restores_language(compat, rt):
    path = RUNTIME.parent / "driver/OneCore/__init__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Voice")
    core = Core()
    env = {"Voice": legacy_class(core), "SynthDriver": object}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), env)
    cls = env["Voice"]
    store = rt.settings.VoiceSettingsStore(MemoryRepository())
    store.ensure(make_spec("OneCore:a", "en")).update(rate=72)
    store.ensure(make_spec("OneCore:b", "zh_TW")).update(rate=31)
    adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
    session = rt.session.EngineSession(adapter, store)
    session.open()
    for key in ("OneCore:a", "OneCore:b", "OneCore:a"):
        assert session.activate(key) is True
    assert (core.voice, core.language, core.rate) == ("a", "en", 72)
    assert session.activate("OneCore:a") is False


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_real_variant_and_waitfactor_hooks(compat, rt, monkeypatch, engine):
    harness = load_real_driver_with_native_stubs(monkeypatch, engine)
    class LegacyVoice(harness.module.Voice):
        extra_capabilities = frozenset({"variant", "waitfactor"})

    cls = LegacyVoice
    core = Core()
    core.getVoiceInstance = lambda key: "native:" + key
    core.getParameter = lambda *args, **kwargs: "plain"
    core.availableVariants = {"plain": object(), "bright": object()}
    writes = []
    monkeypatch.setattr(harness.module, "TtsSetParamList",
                        lambda instance, pair: lambda: writes.append((instance, pair[1])))
    monkeypatch.setattr(harness.module.ve2 if engine == "VE" else harness.module.ttsapi,
                        "getSpeechDBList", lambda language, key: ["plain", "bright"])
    monkeypatch.setattr(cls, "engineOn", classmethod(lambda cls: setattr(cls, "core", core)), raising=False)
    monkeypatch.setattr(cls, "supportedSettings", classmethod(lambda cls: ["rate"]), raising=False)
    voice = object.__new__(cls)
    voice.id = "a"
    adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: voice)
    adapter.open()
    core.writes.clear()
    assert adapter.capabilities.supports_variants is True
    assert adapter.capabilities.supports_waitfactor is True
    assert adapter.variants(engine + ":a") == ({"id": "plain", "name": "plain"},
                                                {"id": "bright", "name": "bright"})
    assert core.writes == []
    state = rt.settings.VoiceState(make_spec(engine + ":a"), {"variant": "bright", "waitfactor": 4})
    adapter.apply(state.spec, state.snapshot())
    assert (core.voice, core.rate, core.waitfactor) == ("a", 50, 4)
    assert writes == [("native:a", "bright")]
