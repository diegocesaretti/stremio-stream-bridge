"""Prepare a player-compatible media URL and MIME type."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .api import StremioStreamServerClient, guess_stream_mime_type
from .const import (
    CONF_AUDIO_MODE,
    DEFAULT_AUDIO_MODE,
    PROFILE_SPORTS,
)

_HLS_MIME = "application/vnd.apple.mpegurl"
_INCOMPATIBLE_AUDIO_MARKERS = (
    "dts",
    "truehd",
    "eac3",
    "e-ac-3",
    "ddp",
    "dolby digital plus",
    "ac3",
    "ac-3",
    "7.1",
)


def _stream_text(stream: Mapping[str, Any]) -> str:
    hints = stream.get("behaviorHints")
    filename = hints.get("filename") if isinstance(hints, Mapping) else None
    return " ".join(
        str(value).lower()
        for value in (
            stream.get("name"),
            stream.get("title"),
            stream.get("description"),
            filename,
        )
        if value
    )


def needs_compatible_hls(stream: Mapping[str, Any], resolved_url: str) -> bool:
    """Return whether the stream is likely to need AAC/HLS compatibility."""
    lowered_url = resolved_url.lower().split("?", 1)[0]
    if lowered_url.endswith((".m3u8", ".mpd")):
        return False
    if stream.get("infoHash"):
        return True
    text = _stream_text(stream)
    if text.endswith((".mkv", ".avi")) or ".mkv" in text or ".avi" in text:
        return True
    return any(marker in text for marker in _INCOMPATIBLE_AUDIO_MARKERS)


def prepare_playback(
    server: StremioStreamServerClient,
    stream: Mapping[str, Any],
    options: Mapping[str, Any],
    *,
    profile: str,
) -> tuple[str, str]:
    """Resolve a stream and optionally route it through hlsv2 for AAC audio."""
    resolved_url = server.resolve_stream(stream)
    mode = str(options.get(CONF_AUDIO_MODE, DEFAULT_AUDIO_MODE))
    if mode == "direct":
        return resolved_url, guess_stream_mime_type(stream, resolved_url)

    # Sports add-ons commonly return an already prepared live HLS feed. Do not
    # wrap it again unless the user explicitly asks for forced transcoding.
    force = mode == "force_transcode"
    should_wrap = force or (
        profile != PROFILE_SPORTS and needs_compatible_hls(stream, resolved_url)
    )
    if should_wrap:
        return (
            server.build_compatible_hls_url(
                resolved_url,
                force_transcoding=force,
                max_audio_channels=2,
            ),
            _HLS_MIME,
        )
    return resolved_url, guess_stream_mime_type(stream, resolved_url)
