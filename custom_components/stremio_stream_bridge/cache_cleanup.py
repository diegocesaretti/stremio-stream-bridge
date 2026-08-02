"""Clear the local stream-server cache after playback ends."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from aiohttp import ClientError, ClientSession, ClientTimeout

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_STREAMING_SERVER_URL, DEFAULT_STREAMING_SERVER_URL

_LOGGER = logging.getLogger(__name__)
_CLEANUP_DELAY_SECONDS = 30
_CONTROL_PORT = 11471
_TERMINAL_STATES = {"idle", "off", "standby", "unavailable"}
_ACTIVE_STATES = {"playing", "buffering"}


class StreamServerCacheCleanupTracker:
    """Ask the packaged stream server to discard playback data after Cast stops."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: Any,
        session: ClientSession,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.session = session
        self._player: str | None = None
        self._state_unsub = None
        self._cleanup_task: asyncio.Task[None] | None = None

    def prepare(self, player: str) -> None:
        """Track the physical player used by the next bridge playback."""
        self._cancel_cleanup()
        if self._state_unsub is not None:
            self._state_unsub()
            self._state_unsub = None
        self._player = player
        self._state_unsub = async_track_state_change_event(
            self.hass,
            [player],
            self._handle_player_state,
        )

    @callback
    def _handle_player_state(self, event: Event) -> None:
        if event.data.get("entity_id") != self._player:
            return
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        state = str(new_state.state).lower()
        if state in _ACTIVE_STATES or state == "paused":
            self._cancel_cleanup()
            return
        if state in _TERMINAL_STATES:
            self._schedule_cleanup()

    @callback
    def _schedule_cleanup(self) -> None:
        self._cancel_cleanup()
        self._cleanup_task = self.hass.async_create_task(self._delayed_cleanup())

    @callback
    def _cancel_cleanup(self) -> None:
        task = self._cleanup_task
        if task is not None and not task.done():
            task.cancel()
        self._cleanup_task = None

    async def _delayed_cleanup(self) -> None:
        try:
            await asyncio.sleep(_CLEANUP_DELAY_SECONDS)
            if not self._player:
                return
            current_state = self.hass.states.get(self._player)
            if current_state is None:
                return
            if str(current_state.state).lower() not in _TERMINAL_STATES:
                return
            await self._request_cleanup()
        except asyncio.CancelledError:
            raise
        finally:
            self._cleanup_task = None

    async def _request_cleanup(self) -> None:
        cleanup_url = self._cleanup_url()
        if cleanup_url is None:
            return
        try:
            async with self.session.post(
                cleanup_url,
                json={},
                timeout=ClientTimeout(total=10),
            ) as response:
                if response.status not in {200, 202}:
                    body = await response.text()
                    _LOGGER.debug(
                        "Stream-server cache cleanup returned HTTP %s: %s",
                        response.status,
                        body[:200],
                    )
                    return
                _LOGGER.info("Stream-server playback cache cleared")
        except (ClientError, TimeoutError, OSError) as err:
            # External Stremio servers do not expose the companion cleanup API.
            _LOGGER.debug("Stream-server cache cleanup is unavailable: %s", err)

    def _cleanup_url(self) -> str | None:
        current = {**self.entry.data, **self.entry.options}
        base_url = str(
            current.get(CONF_STREAMING_SERVER_URL, DEFAULT_STREAMING_SERVER_URL)
            or ""
        ).strip()
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        netloc = f"{host}:{_CONTROL_PORT}"
        return urlunsplit((parsed.scheme, netloc, "/cleanup", "", ""))

    async def async_stop(self) -> None:
        """Remove listeners and cancel a pending cleanup."""
        self._cancel_cleanup()
        if self._state_unsub is not None:
            self._state_unsub()
            self._state_unsub = None
        self._player = None
