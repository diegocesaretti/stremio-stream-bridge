"""Prepare the target player and streaming session before starting new media."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

from .const import CONF_STOP_BEFORE_PLAY, DEFAULT_STOP_BEFORE_PLAY

_LOGGER = logging.getLogger(__name__)
_STOP_SETTLE_SECONDS = 0.8


async def async_prepare_player_session(
    hass: HomeAssistant,
    player: str | None,
    options: dict[str, Any],
    *,
    context: Any | None = None,
) -> bool:
    """Stop current playback so the old reader releases the stream-server URL.

    The official Stremio server does not expose a documented cross-version
    endpoint that safely resets every torrent/session. Stopping the target
    media player closes the active HTTP reader; the following prebuffer request
    then starts a clean stream session for the newly selected source.
    """
    if not player or not bool(
        options.get(CONF_STOP_BEFORE_PLAY, DEFAULT_STOP_BEFORE_PLAY)
    ):
        return False

    state = hass.states.get(player)
    if state is not None and state.state in {"off", "idle", "unavailable", "unknown"}:
        return False

    try:
        await hass.services.async_call(
            "media_player",
            "media_stop",
            {ATTR_ENTITY_ID: player},
            blocking=True,
            context=context,
        )
    except Exception as err:  # noqa: BLE001 - playback must continue after a stop failure.
        _LOGGER.warning("Could not stop current media on %s before playback: %s", player, err)
        return False

    await asyncio.sleep(_STOP_SETTLE_SECONDS)
    return True
