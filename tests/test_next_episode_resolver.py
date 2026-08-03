"""Account-aware default episode selection tests."""

import asyncio
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys

ROOT = Path(__file__).parents[1] / "custom_components" / "stremio_stream_bridge"
PACKAGE = "stremio_next_episode_test"

pkg = ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg

const = ModuleType(f"{PACKAGE}.const")
const.DEFAULT_CAST_COMPATIBILITY_FILTER = True
const.DEFAULT_EXCLUDE_KEYWORDS = ""
const.DEFAULT_MAX_SIZE_GB = 12.0
const.DEFAULT_PREFERRED_QUALITY = "1080p"
const.PROFILE_DEFAULT = "default"
const.PROFILE_LATIN = "latin"
const.PROFILE_SPORTS = "sports"
sys.modules[const.__name__] = const

selector = ModuleType(f"{PACKAGE}.stream_selector")
selector.order_ideal_streams = lambda streams, *args, **kwargs: list(streams)
selector.parse_seeders = lambda stream: int(stream.get("seeders", 0))
sys.modules[selector.__name__] = selector

spec = spec_from_file_location(f"{PACKAGE}.resolver", ROOT / "resolver.py")
assert spec is not None and spec.loader is not None
resolver = module_from_spec(spec)
sys.modules[spec.name] = resolver
spec.loader.exec_module(resolver)


class FakeManager:
    def __init__(self, episodes, library):
        self.episodes = episodes
        self._bridge_account_runtime = SimpleNamespace(
            coordinator=SimpleNamespace(data={"library": library})
        )

    async def search(self, query, media_types):
        del query, media_types
        return [{"id": "tt-series", "type": "series", "name": "Demo"}]

    async def get_meta(self, media_type, media_id, profile):
        del media_type, media_id, profile
        return {
            "id": "tt-series",
            "type": "series",
            "name": "Demo",
            "videos": self.episodes,
        }

    async def get_streams(self, media_type, media_id, profile):
        del media_type, profile
        return [{"seeders": 10, "url": f"https://example/{media_id}"}]


def episode(season, number):
    return {
        "id": f"tt-series:{season}:{number}",
        "season": season,
        "episode": number,
        "title": f"S{season}E{number}",
    }


def history(season, number, *, finished=False):
    return {
        "media_id": "tt-series",
        "playback_id": f"tt-series:{season}:{number}",
        "type": "series",
        "season": season,
        "episode": number,
        "finished": finished,
        "position": 100,
        "duration": 1000,
    }


def resolve(manager, **kwargs):
    return asyncio.run(
        resolver.async_resolve_content(
            manager,
            query="Demo",
            media_type="series",
            **kwargs,
        )
    )


def test_incomplete_episode_still_advances_to_next() -> None:
    manager = FakeManager(
        [episode(1, 1), episode(1, 2), episode(1, 3)],
        [history(1, 2, finished=False)],
    )
    result = resolve(manager)
    assert result["selected"]["media_id"] == "tt-series:1:3"
    assert result["selected"]["selection_reason"] == "stremio_next_episode"


def test_last_episode_of_season_advances_to_next_season() -> None:
    manager = FakeManager(
        [episode(1, 1), episode(1, 2), episode(2, 1), episode(2, 2)],
        [history(1, 2, finished=True)],
    )
    result = resolve(manager)
    assert result["selected"]["media_id"] == "tt-series:2:1"


def test_new_series_starts_at_first_regular_episode() -> None:
    manager = FakeManager(
        [episode(0, 1), episode(1, 1), episode(1, 2)],
        [],
    )
    result = resolve(manager)
    assert result["selected"]["media_id"] == "tt-series:1:1"
    assert result["selected"]["selection_reason"] == "stremio_first_episode"


def test_explicit_episode_overrides_account_history() -> None:
    manager = FakeManager(
        [episode(1, 1), episode(1, 2), episode(1, 3)],
        [history(1, 2)],
    )
    result = resolve(manager, season=1, episode=1)
    assert result["selected"]["media_id"] == "tt-series:1:1"
    assert result["selected"]["selection_reason"] == "ideal_stream_seeders"


def test_last_available_episode_returns_up_to_date() -> None:
    manager = FakeManager(
        [episode(1, 1), episode(1, 2)],
        [history(1, 2)],
    )
    result = resolve(manager)
    assert result["status"] == "up_to_date"
    assert result["selected"] is None
