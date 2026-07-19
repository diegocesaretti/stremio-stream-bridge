"""Prioritized primary-to-secondary stream lookup for the Latin profile."""

from __future__ import annotations

import asyncio
from types import MethodType
from typing import Any

from .aggregator import stream_key, supports_resource
from .api import StremioProtocolError
from .const import PROFILE_DEFAULT, PROFILE_LATIN
from .source_preferences import SpanishAudioSourceNotFound, stream_has_spanish_audio

_SECONDARY_PROVIDER_ATTR = "_bridge_secondary_stream_provider_url"
_PATCH_STATE_ATTR = "_bridge_latin_fallback_state"


def install_latin_stream_fallback(manager: Any) -> bool:
    """Make Latin lookup use primary providers first and secondary only as fallback."""
    preferences = getattr(manager, "_bridge_source_preferences", None)
    if preferences is None or not hasattr(preferences, "get_streams"):
        return False

    state = getattr(manager, _PATCH_STATE_ATTR, None)
    if isinstance(state, dict):
        state["secondary_url"] = getattr(manager, _SECONDARY_PROVIDER_ATTR, None)
        manager.get_streams = preferences.get_streams
        return True

    original_get_streams = preferences.get_streams
    state = {
        "secondary_url": getattr(manager, _SECONDARY_PROVIDER_ATTR, None),
        "original_get_streams": original_get_streams,
    }

    async def get_streams(
        self,
        media_type: str,
        media_id: str,
        profile: str = PROFILE_DEFAULT,
    ) -> list[dict[str, Any]]:
        if profile != PROFILE_LATIN:
            return await state["original_get_streams"](media_type, media_id, profile)
        return await _get_latin_streams(
            manager,
            self,
            media_type,
            media_id,
            state.get("secondary_url"),
        )

    bound = MethodType(get_streams, preferences)
    preferences.get_streams = bound
    manager.get_streams = bound
    manager._bridge_latin_fallback_state = state
    return True


async def _get_latin_streams(
    manager: Any,
    preferences: Any,
    media_type: str,
    media_id: str,
    secondary_url: str | None,
) -> list[dict[str, Any]]:
    primary = _compatible_providers(
        manager,
        media_type,
        media_id,
        secondary_url=secondary_url,
        secondary=False,
    )
    secondary = _compatible_providers(
        manager,
        media_type,
        media_id,
        secondary_url=secondary_url,
        secondary=True,
    )
    if not primary and not secondary:
        raise StremioProtocolError("No compatible Latin stream provider")

    primary_streams, primary_errors, primary_responded = await _fetch_provider_group(
        primary,
        media_type,
        media_id,
    )
    primary_matches = _matching_streams(preferences, primary_streams)
    if primary_matches:
        return _decorate(preferences, primary_matches)

    secondary_streams: list[dict[str, Any]] = []
    secondary_errors: list[str] = []
    secondary_responded = False
    if secondary:
        secondary_streams, secondary_errors, secondary_responded = (
            await _fetch_provider_group(secondary, media_type, media_id)
        )
        secondary_matches = _matching_streams(preferences, secondary_streams)
        if secondary_matches:
            return _decorate(preferences, secondary_matches)

    errors = [*primary_errors, *secondary_errors]
    if errors:
        # A failed provider may still contain a Latin source. Keep catalog availability
        # uncertain rather than incorrectly caching the title as a confirmed non-match.
        raise StremioProtocolError("; ".join(errors))

    all_streams = [*primary_streams, *secondary_streams]
    if all_streams:
        phrases = ", ".join(tuple(preferences.keywords)[:12])
        raise SpanishAudioSourceNotFound(
            "No source from the primary or secondary provider matched the configured "
            f"Spanish/Latin audio keywords ({phrases})"
        )

    if primary_responded or secondary_responded:
        return []
    raise StremioProtocolError("No Latin stream provider returned a response")


def _compatible_providers(
    manager: Any,
    media_type: str,
    media_id: str,
    *,
    secondary_url: str | None,
    secondary: bool,
) -> list[Any]:
    result: list[Any] = []
    for addon in getattr(manager, "addons", []):
        if "stream" not in addon.roles:
            continue
        addon_url = str(addon.client.manifest_url)
        is_secondary = bool(secondary_url and addon_url == secondary_url)
        if is_secondary != secondary:
            continue
        if not supports_resource(addon.manifest, "stream", media_type, media_id):
            continue
        result.append(addon)
    return result


async def _fetch_provider_group(
    providers: list[Any],
    media_type: str,
    media_id: str,
) -> tuple[list[dict[str, Any]], list[str], bool]:
    if not providers:
        return [], [], False
    results = await asyncio.gather(
        *(addon.client.get_streams(media_type, media_id) for addon in providers),
        return_exceptions=True,
    )
    merged: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    responded = False
    for addon, result in zip(providers, results, strict=True):
        if isinstance(result, BaseException):
            errors.append(f"{addon.name}: {result}")
            continue
        responded = True
        for provider_index, stream in enumerate(result):
            if not isinstance(stream, dict):
                continue
            enriched = dict(stream)
            enriched["_bridge_addon_name"] = addon.name
            enriched["_bridge_addon_url"] = addon.client.manifest_url
            enriched["_bridge_provider_index"] = provider_index
            enriched["_bridge_profile"] = PROFILE_LATIN
            key = stream_key(enriched)
            if key in seen:
                continue
            seen.add(key)
            merged.append(enriched)
    return merged, errors, responded


def _matching_streams(preferences: Any, streams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        stream
        for stream in streams
        if stream_has_spanish_audio(stream, tuple(preferences.keywords))
    ]


def _decorate(preferences: Any, streams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for stream in streams:
        item = dict(stream)
        item["_bridge_profile"] = PROFILE_LATIN
        item["_bridge_prefer_h264"] = bool(preferences.prefer_h264)
        item["_bridge_prefer_smaller_size"] = bool(preferences.prefer_smaller_size)
        item["_bridge_force_transcode"] = bool(preferences.force_transcode)
        result.append(item)
    return result
