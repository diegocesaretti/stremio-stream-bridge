"""Enable native Home Assistant search inside the Audio Latino profile."""

from __future__ import annotations

import asyncio
from typing import Any

from .const import PROFILE_DEFAULT, PROFILE_LATIN

_PATCH_ATTR = "_bridge_latin_search_patched"


async def filter_latin_search_results(
    manager: Any,
    metas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep matching and uncertain results while hiding confirmed non-matches."""
    preferences = getattr(manager, "_bridge_source_preferences", None)
    if preferences is None or not bool(getattr(preferences, "hide_non_matching", False)):
        return metas
    statuses = await asyncio.gather(
        *(
            preferences._safe_availability(
                str(meta.get("_bridge_media_type") or meta.get("type") or "movie"),
                meta,
            )
            for meta in metas
        )
    )
    return [
        meta
        for meta, status in zip(metas, statuses, strict=True)
        if status is not False
    ]


def install_latin_media_search_patch() -> None:
    """Patch the existing media-source class without duplicating the full platform."""
    from . import media_source

    cls = media_source.StremioBridgeMediaSource
    if getattr(cls, _PATCH_ATTR, False):
        return

    original_search = cls.async_search_media
    original_browse_profile = cls._browse_profile
    original_type_node = cls._type_node
    original_browse_type = cls._browse_type

    async def async_search_media(self, item, query):
        payload: dict[str, Any] = {}
        if item.identifier:
            payload = media_source._decode(item.identifier)
        profile = str(payload.get("profile") or PROFILE_DEFAULT)
        if profile != PROFILE_LATIN:
            return await original_search(self, item, query)
        if not media_source.MEDIA_SOURCE_SEARCH_SUPPORTED:
            raise media_source.BrowseError(
                "This Home Assistant version does not expose media-source search"
            )

        entry = self._entry_for_item(item)
        runtime = entry.runtime_data
        payload_type = str(payload.get("type") or "")
        media_types = (
            (payload_type,)
            if payload_type in {"movie", "series"}
            else self._search_media_types(query)
        )
        metas = await runtime.manager.search(str(query.search_query), media_types)
        metas = await filter_latin_search_results(runtime.manager, metas)
        results = [
            self._meta_preview(entry.entry_id, meta, profile=PROFILE_LATIN)
            for meta in metas
        ]
        return media_source.SearchMedia(result=results)

    def _browse_profile(self, payload):
        node = original_browse_profile(self, payload)
        if str(payload.get("profile") or "") == PROFILE_LATIN:
            _set_searchable(node, media_source.MEDIA_SOURCE_SEARCH_SUPPORTED)
        return node

    def _type_node(self, entry_id, media_type, profile):
        node = original_type_node(self, entry_id, media_type, profile)
        if str(profile) == PROFILE_LATIN:
            _set_searchable(node, media_source.MEDIA_SOURCE_SEARCH_SUPPORTED)
        return node

    def _browse_type(self, payload):
        node = original_browse_type(self, payload)
        if str(payload.get("profile") or PROFILE_DEFAULT) == PROFILE_LATIN:
            _set_searchable(node, media_source.MEDIA_SOURCE_SEARCH_SUPPORTED)
        return node

    cls.async_search_media = async_search_media
    cls._browse_profile = _browse_profile
    cls._type_node = _type_node
    cls._browse_type = _browse_type
    setattr(cls, _PATCH_ATTR, True)


def _set_searchable(node: Any, value: bool) -> None:
    try:
        setattr(node, "can_search", bool(value))
    except (AttributeError, TypeError):
        object.__setattr__(node, "can_search", bool(value))
