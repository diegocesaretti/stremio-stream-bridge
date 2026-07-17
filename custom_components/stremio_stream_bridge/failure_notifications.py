"""Notify the user when all ranked playback candidates fail."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from homeassistant.core import HomeAssistant

from .const import (
    CONF_FAILURE_NOTIFY_HA,
    CONF_TVOVERLAY_DURATION,
    CONF_TVOVERLAY_ENABLED,
    CONF_TVOVERLAY_SERVICE,
    CONF_TVOVERLAY_TARGET,
    DEFAULT_FAILURE_NOTIFY_HA,
    DEFAULT_TVOVERLAY_DURATION,
    DEFAULT_TVOVERLAY_ENABLED,
    DEFAULT_TVOVERLAY_SERVICE,
    DEFAULT_TVOVERLAY_TARGET,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _service_target(value: str, domain: str) -> dict[str, str] | None:
    """Interpret an optional TvOverlay target for the selected service."""
    target = value.strip()
    if not target:
        return None
    for prefix, key in (
        ("device:", "device_id"),
        ("entity:", "entity_id"),
        ("area:", "area_id"),
        ("target:", "target"),
        ("host:", "host"),
    ):
        if target.lower().startswith(prefix):
            return {key: target[len(prefix) :].strip()}
    if domain == "tvoverlay_ui":
        # The HACS integration recommends its stable Device Identifier field.
        return {"target": target}
    return {"target": target}


def failure_message(title: str, attempts: int, reasons: Sequence[str]) -> str:
    """Build a compact failure message for Home Assistant and TvOverlay."""
    text = f"No se pudo reproducir «{title}». Se probaron {attempts} fuente(s)."
    useful = [reason.strip() for reason in reasons if reason and reason.strip()]
    if useful:
        text += " Último error: " + useful[-1][:240]
    return text


async def async_notify_playback_failure(
    hass: HomeAssistant,
    options: Mapping[str, Any],
    *,
    title: str,
    poster: str | None,
    attempts: int,
    reasons: Sequence[str],
    context: Any | None = None,
) -> None:
    """Send a persistent HA notification and an optional TvOverlay message."""
    message = failure_message(title, attempts, reasons)

    if bool(options.get(CONF_FAILURE_NOTIFY_HA, DEFAULT_FAILURE_NOTIFY_HA)):
        persistent_message = message
        if poster:
            persistent_message += f"\n\n![Portada]({poster})"
        try:
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Stremio Stream Bridge",
                    "message": persistent_message,
                    "notification_id": f"{DOMAIN}_playback_failure",
                },
                blocking=False,
                context=context,
            )
        except Exception as err:  # noqa: BLE001 - notification cannot break playback.
            _LOGGER.warning("Could not create Home Assistant failure notification: %s", err)

    if not bool(options.get(CONF_TVOVERLAY_ENABLED, DEFAULT_TVOVERLAY_ENABLED)):
        return

    service_name = str(
        options.get(CONF_TVOVERLAY_SERVICE, DEFAULT_TVOVERLAY_SERVICE) or ""
    ).strip()
    if "." not in service_name:
        _LOGGER.warning(
            "TvOverlay failure notification is enabled but service '%s' is invalid",
            service_name,
        )
        return

    domain, service = service_name.split(".", 1)
    duration = int(
        options.get(CONF_TVOVERLAY_DURATION, DEFAULT_TVOVERLAY_DURATION)
        or DEFAULT_TVOVERLAY_DURATION
    )
    target = _service_target(
        str(options.get(CONF_TVOVERLAY_TARGET, DEFAULT_TVOVERLAY_TARGET) or ""),
        domain,
    )

    if domain == "notify":
        # REST notify configuration commonly used by the original TvOverlay app.
        data: dict[str, Any] = {
            "title": "Stremio Stream Bridge",
            "message": message,
            "data": {
                "seconds": duration,
                "corner": "top_end",
            },
        }
        if poster:
            data["data"].update(
                {
                    "image": poster,
                    "largeIcon": poster,
                }
            )
    elif domain == "tvoverlay_ui":
        # HACS TvOverlay UI integration (snake_case service fields).
        data = {
            "title": "Stremio Stream Bridge",
            "message": message,
            "source": "Home Assistant",
            "corner": "top_end",
            "duration": duration,
        }
        if poster:
            data.update(
                {
                    "large_icon": poster,
                    "media_type": "image",
                    "media_url": poster,
                }
            )
    else:
        # Best-effort generic service contract.
        data = {
            "title": "Stremio Stream Bridge",
            "message": message,
            "duration": duration,
        }
        if poster:
            data["image"] = poster

    if target:
        data.update(target)
    try:
        await hass.services.async_call(
            domain,
            service,
            data,
            blocking=False,
            context=context,
        )
    except Exception as err:  # noqa: BLE001 - overlay failure must remain non-fatal.
        _LOGGER.warning("Could not send TvOverlay failure notification: %s", err)
