"""Human-readable stream labels and automatic quality selection."""

from __future__ import annotations

import re
from typing import Any

from .aggregator import stream_key

_QUALITY_PATTERNS = (
    (2160, re.compile(r"(?:\b2160p?\b|\b4k\b|uhd)", re.IGNORECASE)),
    (1080, re.compile(r"\b1080[pi]?\b", re.IGNORECASE)),
    (720, re.compile(r"\b720[pi]?\b", re.IGNORECASE)),
    (480, re.compile(r"\b480[pi]?\b", re.IGNORECASE)),
    (360, re.compile(r"\b360[pi]?\b", re.IGNORECASE)),
)
_SIZE_RE = re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(TiB|TB|GiB|GB|MiB|MB)\b", re.IGNORECASE)
_SEED_PATTERNS = (
    re.compile(r"(?:👤|🌱|seeders?|seeds?)\s*[:=]?\s*(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)\s*(?:seeders?|seeds?)\b", re.IGNORECASE),
)


def stream_text(stream: dict[str, Any]) -> str:
    """Join fields commonly used by Stremio stream add-ons."""
    hints = stream.get("behaviorHints")
    filename = hints.get("filename") if isinstance(hints, dict) else None
    return "\n".join(
        str(value)
        for value in (
            stream.get("name"),
            stream.get("title"),
            stream.get("description"),
            filename,
        )
        if value
    )


def parse_quality(stream: dict[str, Any]) -> int:
    text = stream_text(stream)
    for value, pattern in _QUALITY_PATTERNS:
        if pattern.search(text):
            return value
    return 0


def parse_size_gb(stream: dict[str, Any]) -> float | None:
    match = _SIZE_RE.search(stream_text(stream))
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    if unit in {"tib", "tb"}:
        return value * 1024
    if unit in {"mib", "mb"}:
        return value / 1024
    return value


def parse_seeders(stream: dict[str, Any]) -> int:
    text = stream_text(stream)
    for pattern in _SEED_PATTERNS:
        if match := pattern.search(text):
            return int(match.group(1))
    return 0


def stream_label(stream: dict[str, Any], position: int | None = None) -> str:
    """Build a compact label suited to Home Assistant's media browser."""
    quality = parse_quality(stream)
    size = parse_size_gb(stream)
    seeders = parse_seeders(stream)
    provider = stream.get("_bridge_addon_name")
    parts: list[str] = []
    if position is not None:
        parts.append(str(position + 1))
    if quality:
        parts.append("4K" if quality == 2160 else f"{quality}p")
    if size is not None:
        parts.append(f"{size:.1f} GB" if size >= 1 else f"{size * 1024:.0f} MB")
    if seeders:
        parts.append(f"{seeders} semillas")
    if provider:
        parts.append(str(provider))
    if parts:
        return " · ".join(parts)
    text = stream_text(stream).replace("\n", " · ").strip()
    return text[:110] or "Stream"


def choose_best_stream(
    streams: list[dict[str, Any]],
    preferred_quality: str,
    max_size_gb: float,
    exclude_keywords: str,
) -> dict[str, Any]:
    """Select a practical stream using quality, size, release tags and seeds."""
    if not streams:
        raise ValueError("No streams to select")
    excluded = [word.strip().lower() for word in exclude_keywords.split(",") if word.strip()]

    def allowed(stream: dict[str, Any], enforce_size: bool = True) -> bool:
        text = stream_text(stream).lower()
        if any(
            re.search(
                rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])",
                text,
                re.IGNORECASE,
            )
            for keyword in excluded
        ):
            return False
        size = parse_size_gb(stream)
        return not (enforce_size and max_size_gb > 0 and size is not None and size > max_size_gb)

    candidates = [stream for stream in streams if allowed(stream)]
    if not candidates:
        candidates = [stream for stream in streams if allowed(stream, enforce_size=False)]
    if not candidates:
        candidates = streams

    target_map = {"2160p": 2160, "1080p": 1080, "720p": 720, "480p": 480}
    target = target_map.get(preferred_quality)

    def quality_rank(quality: int) -> tuple[int, int]:
        if preferred_quality == "lowest":
            return (0 if quality else 1, quality or 9999)
        if target is not None:
            if quality == target:
                return (0, 0)
            if 0 < quality < target:
                return (1, target - quality)
            if quality > target:
                return (2, quality - target)
            return (3, 9999)
        # auto: highest known quality first.
        return (0 if quality else 1, -quality)

    def rank(stream: dict[str, Any]) -> tuple[Any, ...]:
        quality = parse_quality(stream)
        size = parse_size_gb(stream)
        return (
            *quality_rank(quality),
            -parse_seeders(stream),
            size if size is not None else 9999,
            stream_key(stream),
        )

    return min(candidates, key=rank)
