"""Preferred audio-track query and secondary provider registration tests."""

import asyncio
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).parents[1] / "custom_components" / "stremio_stream_bridge"
PACKAGE = "stremio_stream_bridge_provider_options_test"

pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg

const = types.ModuleType(f"{PACKAGE}.const")
const.DEFAULT_PREFERRED_AUDIO_LANGUAGES = "lat, esp, spa, es"
sys.modules[const.__name__] = const

server_spec = spec_from_file_location(
    f"{PACKAGE}.server_preferences", ROOT / "server_preferences.py"
)
assert server_spec is not None and server_spec.loader is not None
SERVER_PREFS = module_from_spec(server_spec)
sys.modules[server_spec.name] = SERVER_PREFS
server_spec.loader.exec_module(SERVER_PREFS)


class FakeServer:
    def build_compatible_hls_url(
        self,
        media_url: str,
        *,
        force_transcoding: bool = False,
        max_audio_channels: int = 2,
    ) -> str:
        return (
            "http://server/hlsv2/session/master.m3u8?"
            f"mediaURL={media_url}&forceTranscoding={int(force_transcoding)}"
            f"&maxAudioChannels={max_audio_channels}"
        )


def test_preferred_audio_languages_are_ordered_and_added_to_hls_url() -> None:
    server = FakeServer()
    languages = SERVER_PREFS.install_preferred_audio_languages(
        server,
        "lat, esp, spa, es, spa",
    )

    url = server.build_compatible_hls_url(
        "http://server/media",
        force_transcoding=True,
        max_audio_channels=2,
    )
    query = parse_qs(urlsplit(url).query)

    assert languages == ("lat", "esp", "spa", "es")
    assert query["audioLanguages"] == ["lat,esp,spa,es"]


def test_preferred_audio_languages_can_be_reconfigured_without_double_wrapping() -> None:
    server = FakeServer()
    SERVER_PREFS.install_preferred_audio_languages(server, "lat, esp")
    SERVER_PREFS.install_preferred_audio_languages(server, "spa, es")

    query = parse_qs(
        urlsplit(server.build_compatible_hls_url("http://server/media")).query
    )

    assert query["audioLanguages"] == ["spa,es"]


api = types.ModuleType(f"{PACKAGE}.api")


class StremioProtocolError(Exception):
    pass


class FakeAddonClient:
    def __init__(self, session, manifest_url: str) -> None:
        self.session = session
        self.manifest_url = self._normalize_manifest_url(manifest_url)

    @staticmethod
    def _normalize_manifest_url(manifest_url: str) -> str:
        value = manifest_url.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise StremioProtocolError("invalid")
        if value.endswith("/manifest.json"):
            return value
        return f"{value}/manifest.json"


api.StremioAddonClient = FakeAddonClient
api.StremioProtocolError = StremioProtocolError
sys.modules[api.__name__] = api

secondary_spec = spec_from_file_location(
    f"{PACKAGE}.secondary_provider", ROOT / "secondary_provider.py"
)
assert secondary_spec is not None and secondary_spec.loader is not None
SECONDARY = module_from_spec(secondary_spec)
sys.modules[secondary_spec.name] = SECONDARY
secondary_spec.loader.exec_module(SECONDARY)


class FakeManager:
    def __init__(self) -> None:
        self._clients = {}
        self._roles = {}
        self.refresh_count = 0

    async def async_refresh(self):
        self.refresh_count += 1
        return []


def test_secondary_provider_is_registered_as_a_normal_stream_source() -> None:
    manager = FakeManager()

    normalized = asyncio.run(
        SECONDARY.install_secondary_stream_provider(
            manager,
            object(),
            "https://secondary.example/addon",
        )
    )

    assert normalized == "https://secondary.example/addon/manifest.json"
    assert normalized in manager._clients
    assert manager._roles[normalized] == {"stream"}
    assert manager.refresh_count == 1


def test_invalid_secondary_provider_does_not_break_primary_setup() -> None:
    manager = FakeManager()

    normalized = asyncio.run(
        SECONDARY.install_secondary_stream_provider(manager, object(), "not-a-url")
    )

    assert normalized is None
    assert manager._clients == {}
    assert manager.refresh_count == 0
