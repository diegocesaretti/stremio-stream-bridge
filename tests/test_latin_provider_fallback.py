"""Primary-first and secondary-fallback behavior for Audio Latino."""

import asyncio
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1] / "custom_components" / "stremio_stream_bridge"
PACKAGE = "bridge_latin_fallback_test"

pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg

aggregator = types.ModuleType(f"{PACKAGE}.aggregator")
aggregator.stream_key = lambda stream: str(stream.get("url") or stream.get("title"))
aggregator.supports_resource = lambda manifest, resource, media_type, media_id: True
sys.modules[aggregator.__name__] = aggregator

api = types.ModuleType(f"{PACKAGE}.api")


class StremioProtocolError(Exception):
    pass


api.StremioProtocolError = StremioProtocolError
sys.modules[api.__name__] = api

const = types.ModuleType(f"{PACKAGE}.const")
const.PROFILE_DEFAULT = "default"
const.PROFILE_LATIN = "latin"
sys.modules[const.__name__] = const

source_preferences = types.ModuleType(f"{PACKAGE}.source_preferences")


class SpanishAudioSourceNotFound(StremioProtocolError):
    pass


def stream_has_spanish_audio(stream, keywords):
    text = " ".join(str(value) for value in stream.values()).casefold()
    return any(keyword.casefold() in text for keyword in keywords)


source_preferences.SpanishAudioSourceNotFound = SpanishAudioSourceNotFound
source_preferences.stream_has_spanish_audio = stream_has_spanish_audio
sys.modules[source_preferences.__name__] = source_preferences

spec = spec_from_file_location(f"{PACKAGE}.latin_fallback", ROOT / "latin_fallback.py")
assert spec is not None and spec.loader is not None
FALLBACK = module_from_spec(spec)
sys.modules[spec.name] = FALLBACK
spec.loader.exec_module(FALLBACK)


class FakeClient:
    def __init__(self, url, streams=None, error=None):
        self.manifest_url = url
        self.streams = streams or []
        self.error = error
        self.calls = 0

    async def get_streams(self, media_type, media_id):
        self.calls += 1
        if self.error:
            raise self.error
        return list(self.streams)


class FakeAddon:
    def __init__(self, name, client):
        self.name = name
        self.client = client
        self.roles = frozenset({"stream"})
        self.manifest = {"resources": ["stream"]}


class FakePreferences:
    def __init__(self):
        self.keywords = ("audio latino",)
        self.prefer_h264 = False
        self.prefer_smaller_size = True
        self.force_transcode = True

    async def get_streams(self, media_type, media_id, profile="default"):
        return [{"url": "https://default"}]


class FakeManager:
    def __init__(self, primary, secondary):
        self.addons = [FakeAddon("Primary", primary), FakeAddon("Secondary", secondary)]
        self._bridge_secondary_stream_provider_url = secondary.manifest_url
        self._bridge_source_preferences = FakePreferences()
        self.get_streams = self._bridge_source_preferences.get_streams


def test_primary_match_avoids_secondary_request() -> None:
    primary = FakeClient(
        "https://primary/manifest.json",
        [{"title": "Movie Audio Latino", "url": "https://primary/latino"}],
    )
    secondary = FakeClient(
        "https://secondary/manifest.json",
        [{"title": "Movie Audio Latino", "url": "https://secondary/latino"}],
    )
    manager = FakeManager(primary, secondary)
    assert FALLBACK.install_latin_stream_fallback(manager)

    result = asyncio.run(manager.get_streams("movie", "tt1", "latin"))

    assert [item["url"] for item in result] == ["https://primary/latino"]
    assert primary.calls == 1
    assert secondary.calls == 0
    assert result[0]["_bridge_force_transcode"] is True


def test_secondary_is_queried_only_after_primary_has_no_match() -> None:
    primary = FakeClient(
        "https://primary/manifest.json",
        [{"title": "Movie English", "url": "https://primary/en"}],
    )
    secondary = FakeClient(
        "https://secondary/manifest.json",
        [{"title": "Movie Audio Latino", "url": "https://secondary/latino"}],
    )
    manager = FakeManager(primary, secondary)
    FALLBACK.install_latin_stream_fallback(manager)

    result = asyncio.run(manager.get_streams("movie", "tt1", "latin"))

    assert [item["url"] for item in result] == ["https://secondary/latino"]
    assert primary.calls == 1
    assert secondary.calls == 1


def test_confirmed_no_match_raises_specific_error() -> None:
    primary = FakeClient(
        "https://primary/manifest.json",
        [{"title": "Movie English", "url": "https://primary/en"}],
    )
    secondary = FakeClient(
        "https://secondary/manifest.json",
        [{"title": "Movie French", "url": "https://secondary/fr"}],
    )
    manager = FakeManager(primary, secondary)
    FALLBACK.install_latin_stream_fallback(manager)

    with pytest.raises(SpanishAudioSourceNotFound):
        asyncio.run(manager.get_streams("movie", "tt1", "latin"))


def test_secondary_failure_is_uncertain_not_confirmed_missing() -> None:
    primary = FakeClient(
        "https://primary/manifest.json",
        [{"title": "Movie English", "url": "https://primary/en"}],
    )
    secondary = FakeClient(
        "https://secondary/manifest.json",
        error=RuntimeError("offline"),
    )
    manager = FakeManager(primary, secondary)
    FALLBACK.install_latin_stream_fallback(manager)

    with pytest.raises(StremioProtocolError) as error:
        asyncio.run(manager.get_streams("movie", "tt1", "latin"))

    assert not isinstance(error.value, SpanishAudioSourceNotFound)
