"""Optional secondary main stream provider support."""

from __future__ import annotations

import logging
from typing import Any

from .api import StremioAddonClient, StremioProtocolError

_LOGGER = logging.getLogger(__name__)


async def install_secondary_stream_provider(
    manager: Any,
    session: Any,
    manifest_url: object,
) -> str | None:
    """Register one optional stream manifest beside the main providers.

    The manager already merges and deduplicates streams across every provider with
    the ``stream`` role. Refresh failures are retained in ``manager.errors`` and do
    not remove successfully loaded primary providers.
    """
    raw = str(manifest_url or "").strip()
    if not raw:
        return None
    try:
        normalized = StremioAddonClient._normalize_manifest_url(raw)
    except StremioProtocolError:
        _LOGGER.warning("Ignoring invalid secondary stream provider URL: %s", raw)
        return None
    roles = manager._roles.setdefault(normalized, set())
    roles.add("stream")
    if normalized not in manager._clients:
        manager._clients[normalized] = StremioAddonClient(session, normalized)
    try:
        await manager.async_refresh()
    except StremioProtocolError:
        # This only occurs when no add-on at all can be loaded. Preserve the
        # original startup behavior instead of making the optional field fatal.
        _LOGGER.warning(
            "Secondary stream provider refresh failed for %s",
            normalized,
            exc_info=True,
        )
    return normalized
