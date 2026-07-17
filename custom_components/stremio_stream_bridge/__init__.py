"""Stremio Stream Bridge integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .aggregator import StremioAddonManager, stream_key
from .api import (
    StremioAddonClient,
    StremioBridgeError,
    StremioStreamServerClient,
    guess_mime_type,
    parse_manifest_urls,
)
from .const import (
    ATTR_ENTRY_ID,
    ATTR_MEDIA_ID,
    ATTR_MEDIA_PLAYER,
    ATTR_MEDIA_TYPE,
    ATTR_QUERY,
    ATTR_STREAM_INDEX,
    ATTR_URL,
    CONF_ADDON_MANIFEST_URL,
    CONF_CATALOG_MANIFEST_URLS,
    CONF_DEFAULT_MEDIA_PLAYER,
    CONF_DEFAULT_STREAM_INDEX,
    CONF_EXCLUDE_KEYWORDS,
    CONF_MAX_SIZE_GB,
    CONF_PREFERRED_QUALITY,
    CONF_STREAM_MANIFEST_URLS,
    CONF_STREAMING_SERVER_URL,
    DEFAULT_CINEMETA_MANIFEST,
    DEFAULT_EXCLUDE_KEYWORDS,
    DEFAULT_MAX_SIZE_GB,
    DEFAULT_PREFERRED_QUALITY,
    DEFAULT_TORRENTIO_MANIFEST,
    DOMAIN,
    PLATFORMS,
    SERVICE_PLAY,
    SERVICE_PLAY_URL,
    SERVICE_REFRESH,
    SERVICE_SEARCH,
)
from .coordinator import StremioBridgeCoordinator
from .stream_selector import choose_best_stream


@dataclass(slots=True)
class StremioBridgeRuntime:
    """Runtime data attached to a config entry."""

    manager: StremioAddonManager
    server: StremioStreamServerClient
    coordinator: StremioBridgeCoordinator
    last_search_query: str | None = None
    last_search_results: list[dict[str, Any]] = field(default_factory=list)


PLAY_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_MEDIA_TYPE): cv.string,
        vol.Required(ATTR_MEDIA_ID): cv.string,
        vol.Optional(ATTR_MEDIA_PLAYER): cv.entity_id,
        vol.Optional(ATTR_STREAM_INDEX): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)

PLAY_URL_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_URL): cv.string,
        vol.Optional(ATTR_MEDIA_PLAYER): cv.entity_id,
    }
)

REFRESH_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTRY_ID): cv.string})

SEARCH_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_QUERY): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_MEDIA_TYPE, default="all"): vol.In(["all", "movie", "series"]),
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register integration services."""

    async def handle_play(call: ServiceCall) -> None:
        entry = _resolve_entry(hass, call.data.get(ATTR_ENTRY_ID))
        runtime: StremioBridgeRuntime = entry.runtime_data
        streams = await runtime.manager.get_streams(
            call.data[ATTR_MEDIA_TYPE], call.data[ATTR_MEDIA_ID]
        )
        if not streams:
            raise HomeAssistantError("No stream provider returned a playable source")
        try:
            stream = _select_stream(entry, streams, call.data.get(ATTR_STREAM_INDEX))
            url = runtime.server.resolve_stream(stream)
        except (StremioBridgeError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        player = _resolve_player(entry, call.data.get(ATTR_MEDIA_PLAYER))
        await _async_play_url(hass, call, player, url)

    async def handle_play_url(call: ServiceCall) -> None:
        entry = _resolve_entry(hass, call.data.get(ATTR_ENTRY_ID))
        runtime: StremioBridgeRuntime = entry.runtime_data
        raw_url = call.data[ATTR_URL].strip()
        try:
            url = (
                runtime.server.resolve_magnet(raw_url) if raw_url.startswith("magnet:") else raw_url
            )
        except StremioBridgeError as err:
            raise HomeAssistantError(str(err)) from err
        if not url.startswith(("http://", "https://")):
            raise HomeAssistantError("play_url accepts HTTP(S) URLs or magnet URIs")
        player = _resolve_player(entry, call.data.get(ATTR_MEDIA_PLAYER))
        await _async_play_url(hass, call, player, url)

    async def handle_refresh(call: ServiceCall) -> None:
        if entry_id := call.data.get(ATTR_ENTRY_ID):
            await _resolve_entry(hass, entry_id).runtime_data.coordinator.async_request_refresh()
            return
        for entry in _loaded_entries(hass):
            await entry.runtime_data.coordinator.async_request_refresh()

    async def handle_search(call: ServiceCall) -> None:
        entry = _resolve_entry(hass, call.data.get(ATTR_ENTRY_ID))
        runtime: StremioBridgeRuntime = entry.runtime_data
        media_type = call.data[ATTR_MEDIA_TYPE]
        media_types = ("movie", "series") if media_type == "all" else (media_type,)
        runtime.last_search_query = call.data[ATTR_QUERY].strip()
        runtime.last_search_results = await runtime.manager.search(
            runtime.last_search_query, media_types
        )

    hass.services.async_register(DOMAIN, SERVICE_PLAY, handle_play, schema=PLAY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_PLAY_URL, handle_play_url, schema=PLAY_URL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh, schema=REFRESH_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SEARCH, handle_search, schema=SEARCH_SCHEMA)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate v0.1 single-add-on entries to the aggregator format."""
    if entry.version >= 2:
        return True
    data = dict(entry.data)
    legacy_url = data.get(CONF_ADDON_MANIFEST_URL)
    catalog_urls = [DEFAULT_CINEMETA_MANIFEST]
    stream_urls = [DEFAULT_TORRENTIO_MANIFEST]
    if isinstance(legacy_url, str) and legacy_url:
        catalog_urls.insert(0, legacy_url)
        stream_urls = [legacy_url]
    data[CONF_CATALOG_MANIFEST_URLS] = parse_manifest_urls(catalog_urls)
    data[CONF_STREAM_MANIFEST_URLS] = parse_manifest_urls(stream_urls)
    hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one aggregate Stremio environment."""
    session = async_get_clientsession(hass)
    current = {**entry.data, **entry.options}
    catalog_urls = parse_manifest_urls(
        current.get(CONF_CATALOG_MANIFEST_URLS, [DEFAULT_CINEMETA_MANIFEST])
    )
    stream_urls = parse_manifest_urls(
        current.get(CONF_STREAM_MANIFEST_URLS, [DEFAULT_TORRENTIO_MANIFEST])
    )
    manager = StremioAddonManager(
        [StremioAddonClient(session, url) for url in catalog_urls],
        [StremioAddonClient(session, url) for url in stream_urls],
    )
    server = StremioStreamServerClient(session, entry.data[CONF_STREAMING_SERVER_URL])
    coordinator = StremioBridgeCoordinator(hass, manager, server)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = StremioBridgeRuntime(manager, server, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry.runtime_data = None
    return unload_ok


def _select_stream(
    entry: ConfigEntry,
    streams: list[dict[str, Any]],
    requested_index: int | None,
) -> dict[str, Any]:
    if requested_index is not None:
        if requested_index >= len(streams):
            raise HomeAssistantError(
                f"Stream index {requested_index} is unavailable; providers returned "
                f"{len(streams)} stream(s)"
            )
        return streams[requested_index]
    # Retain the old v0.1 default-index behavior until the user saves v0.2 options.
    if CONF_DEFAULT_STREAM_INDEX in entry.options:
        legacy_index = int(entry.options[CONF_DEFAULT_STREAM_INDEX])
        if legacy_index < len(streams):
            return streams[legacy_index]
    return choose_best_stream(
        streams,
        str(entry.options.get(CONF_PREFERRED_QUALITY, DEFAULT_PREFERRED_QUALITY)),
        float(entry.options.get(CONF_MAX_SIZE_GB, DEFAULT_MAX_SIZE_GB)),
        str(entry.options.get(CONF_EXCLUDE_KEYWORDS, DEFAULT_EXCLUDE_KEYWORDS)),
    )


def find_stream_by_key(streams: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    """Find a selected stream after re-querying providers."""
    return next((stream for stream in streams if stream_key(stream) == key), None)


def _loaded_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and getattr(entry, "runtime_data", None) is not None
    ]


def _resolve_entry(hass: HomeAssistant, entry_id: str | None) -> ConfigEntry:
    entries = _loaded_entries(hass)
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry not in entries:
            raise HomeAssistantError(f"Stremio Stream Bridge entry {entry_id} is not loaded")
        return entry
    if len(entries) == 1:
        return entries[0]
    if not entries:
        raise HomeAssistantError("No loaded Stremio Stream Bridge entries")
    raise HomeAssistantError("More than one entry exists; specify entry_id")


def _resolve_player(entry: ConfigEntry, requested: str | None) -> str:
    player = requested or entry.options.get(
        CONF_DEFAULT_MEDIA_PLAYER,
        entry.data.get(CONF_DEFAULT_MEDIA_PLAYER),
    )
    if not player:
        raise HomeAssistantError("No target media_player was provided or configured")
    return player


async def _async_play_url(
    hass: HomeAssistant,
    call: ServiceCall,
    player: str,
    url: str,
) -> None:
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            ATTR_ENTITY_ID: player,
            "media_content_id": url,
            "media_content_type": guess_mime_type(url),
        },
        blocking=True,
        context=call.context,
    )
