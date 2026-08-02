"""Playback cache cleanup lifecycle tests without importing Home Assistant."""

from __future__ import annotations

import asyncio
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1] / "custom_components" / "stremio_stream_bridge"
PACKAGE = "stremio_stream_bridge_cache_cleanup_test"

pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg


def install_stub_modules() -> None:
    aiohttp = types.ModuleType("aiohttp")

    class ClientError(Exception):
        pass

    class ClientSession:
        pass

    class ClientTimeout:
        def __init__(self, *, total: float) -> None:
            self.total = total

    aiohttp.ClientError = ClientError
    aiohttp.ClientSession = ClientSession
    aiohttp.ClientTimeout = ClientTimeout
    sys.modules["aiohttp"] = aiohttp

    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []
    sys.modules["homeassistant"] = homeassistant

    const = types.ModuleType("homeassistant.const")
    const.EVENT_CALL_SERVICE = "call_service"
    sys.modules["homeassistant.const"] = const

    core = types.ModuleType("homeassistant.core")

    class Event:
        def __init__(self, data: dict) -> None:
            self.data = data

    class HomeAssistant:
        pass

    core.Event = Event
    core.HomeAssistant = HomeAssistant
    core.callback = lambda function: function
    sys.modules["homeassistant.core"] = core

    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    sys.modules["homeassistant.helpers"] = helpers

    event = types.ModuleType("homeassistant.helpers.event")

    def async_track_state_change_event(hass, entities, callback):
        hass.state_listener = (entities, callback)
        return lambda: setattr(hass, "state_listener", None)

    event.async_track_state_change_event = async_track_state_change_event
    sys.modules["homeassistant.helpers.event"] = event


install_stub_modules()

const_spec = spec_from_file_location(f"{PACKAGE}.const", ROOT / "const.py")
assert const_spec is not None and const_spec.loader is not None
CONST = module_from_spec(const_spec)
sys.modules[const_spec.name] = CONST
const_spec.loader.exec_module(CONST)

cleanup_spec = spec_from_file_location(
    f"{PACKAGE}.cache_cleanup", ROOT / "cache_cleanup.py"
)
assert cleanup_spec is not None and cleanup_spec.loader is not None
CLEANUP = module_from_spec(cleanup_spec)
sys.modules[cleanup_spec.name] = CLEANUP
cleanup_spec.loader.exec_module(CLEANUP)


class FakeBus:
    def __init__(self) -> None:
        self.listener = None

    def async_listen(self, event_type, callback):
        assert event_type == "call_service"
        self.listener = callback
        return lambda: setattr(self, "listener", None)


class FakeStates:
    def __init__(self) -> None:
        self.values = {}

    def get(self, entity_id):
        return self.values.get(entity_id)


class FakeHass:
    def __init__(self) -> None:
        self.bus = FakeBus()
        self.states = FakeStates()
        self.state_listener = None
        self.tasks = []

    def async_create_task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task


class FakeEntry:
    entry_id = "entry-1"
    data = {
        CONST.CONF_STREAMING_SERVER_URL: "http://192.168.1.50:11470",
        CONST.CONF_DEFAULT_MEDIA_PLAYER: "media_player.living_room",
    }
    options = {}


class FakeState:
    def __init__(self, state: str) -> None:
        self.state = state


class FakeResponse:
    status = 202

    async def text(self) -> str:
        return '{"ok":true}'


class FakeRequestContext:
    async def __aenter__(self):
        return FakeResponse()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    def __init__(self) -> None:
        self.urls = []

    def post(self, url, **kwargs):
        self.urls.append((url, kwargs))
        return FakeRequestContext()


def event(data: dict):
    return sys.modules["homeassistant.core"].Event(data)


def test_pause_keeps_cache_and_idle_clears_it() -> None:
    async def scenario() -> None:
        CLEANUP._CLEANUP_DELAY_SECONDS = 0
        hass = FakeHass()
        session = FakeSession()
        tracker = CLEANUP.StreamServerCacheCleanupTracker(hass, FakeEntry(), session)

        tracker._handle_service_call(
            event(
                {
                    "domain": CONST.DOMAIN,
                    "service": CONST.SERVICE_PLAY,
                    "service_data": {},
                }
            )
        )
        assert tracker._player == "media_player.living_room"

        tracker._handle_player_state(
            event(
                {
                    "entity_id": "media_player.living_room",
                    "new_state": FakeState("paused"),
                }
            )
        )
        assert session.urls == []
        assert hass.tasks == []

        hass.states.values["media_player.living_room"] = FakeState("idle")
        tracker._handle_player_state(
            event(
                {
                    "entity_id": "media_player.living_room",
                    "new_state": FakeState("idle"),
                }
            )
        )
        await hass.tasks[-1]

        assert session.urls[0][0] == "http://192.168.1.50:11471/cleanup"
        await tracker.async_stop()

    asyncio.run(scenario())


def test_new_playback_cancels_pending_cleanup() -> None:
    async def scenario() -> None:
        CLEANUP._CLEANUP_DELAY_SECONDS = 60
        hass = FakeHass()
        session = FakeSession()
        tracker = CLEANUP.StreamServerCacheCleanupTracker(hass, FakeEntry(), session)
        tracker.prepare("media_player.living_room")

        hass.states.values["media_player.living_room"] = FakeState("idle")
        tracker._handle_player_state(
            event(
                {
                    "entity_id": "media_player.living_room",
                    "new_state": FakeState("idle"),
                }
            )
        )
        pending = hass.tasks[-1]
        assert not pending.done()

        tracker._handle_player_state(
            event(
                {
                    "entity_id": "media_player.living_room",
                    "new_state": FakeState("playing"),
                }
            )
        )
        await asyncio.sleep(0)
        assert pending.cancelled()
        assert session.urls == []
        await tracker.async_stop()

    asyncio.run(scenario())
