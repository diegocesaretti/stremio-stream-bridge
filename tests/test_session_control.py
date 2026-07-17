"""Tests for the pre-playback player stop/session release helper."""

import asyncio
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1] / "custom_components" / "stremio_stream_bridge"
PACKAGE = "stremio_stream_bridge_session_test"
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg

ha = types.ModuleType("homeassistant")
ha_const = types.ModuleType("homeassistant.const")
ha_const.ATTR_ENTITY_ID = "entity_id"
ha_core = types.ModuleType("homeassistant.core")
ha_core.HomeAssistant = object
sys.modules.setdefault("homeassistant", ha)
sys.modules["homeassistant.const"] = ha_const
sys.modules["homeassistant.core"] = ha_core


def load(name: str):
    spec = spec_from_file_location(f"{PACKAGE}.{name}", ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CONST = load("const")
SESSION = load("session_control")


class FakeStateMachine:
    def get(self, _entity_id):
        return types.SimpleNamespace(state="playing")


class FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, **kwargs):
        self.calls.append((domain, service, data, kwargs))


async def _run_stop_test():
    services = FakeServices()
    hass = types.SimpleNamespace(states=FakeStateMachine(), services=services)
    original_sleep = asyncio.sleep

    async def no_sleep(_delay):
        return None

    SESSION.asyncio.sleep = no_sleep
    try:
        stopped = await SESSION.async_prepare_player_session(
            hass,
            "media_player.tv",
            {CONST.CONF_STOP_BEFORE_PLAY: True},
        )
    finally:
        SESSION.asyncio.sleep = original_sleep
    assert stopped is True
    assert services.calls[0][0:3] == (
        "media_player",
        "media_stop",
        {"entity_id": "media_player.tv"},
    )


def test_current_player_is_stopped_before_new_stream():
    asyncio.run(_run_stop_test())
