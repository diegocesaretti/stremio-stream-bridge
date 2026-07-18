"""Optional codec/size ranking and hard maximum-size tests."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1] / "custom_components" / "stremio_stream_bridge"
PACKAGE = "stremio_stream_bridge_optional_ranking_test"

pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg

aggregator = types.ModuleType(f"{PACKAGE}.aggregator")
aggregator.stream_key = lambda stream: str(stream.get("url") or stream.get("name") or "")
sys.modules[aggregator.__name__] = aggregator

spec = spec_from_file_location(f"{PACKAGE}.stream_selector", ROOT / "stream_selector.py")
assert spec is not None and spec.loader is not None
SELECTOR = module_from_spec(spec)
sys.modules[spec.name] = SELECTOR
spec.loader.exec_module(SELECTOR)


def stream(name: str, *, seeds: int, url_id: str) -> dict:
    return {
        "name": name,
        "description": f"{seeds} seeders",
        "url": f"https://video.example/{url_id}",
    }


def test_h264_preference_can_be_disabled() -> None:
    h264 = stream("Movie 1080p x264 4 GB", seeds=10, url_id="h264")
    hevc = stream("Movie 1080p x265 4 GB", seeds=500, url_id="hevc")

    ordered = SELECTOR.order_ideal_streams(
        [h264, hevc],
        12,
        "",
        prefer_h264=False,
    )

    assert ordered[0] is hevc


def test_h264_preference_can_be_enabled() -> None:
    h264 = stream("Movie 1080p x264 4 GB", seeds=10, url_id="h264")
    hevc = stream("Movie 1080p x265 4 GB", seeds=500, url_id="hevc")

    ordered = SELECTOR.order_ideal_streams(
        [hevc, h264],
        12,
        "",
        prefer_h264=True,
    )

    assert ordered[0] is h264


def test_smaller_file_preference_is_only_a_tie_breaker() -> None:
    small = stream("Movie 1080p 2 GB", seeds=100, url_id="small")
    large = stream("Movie 1080p 8 GB", seeds=100, url_id="large")

    without_preference = SELECTOR.order_ideal_streams(
        [large, small],
        12,
        "",
        prefer_h264=False,
        prefer_smaller_size=False,
    )
    with_preference = SELECTOR.order_ideal_streams(
        [large, small],
        12,
        "",
        prefer_h264=False,
        prefer_smaller_size=True,
    )

    assert without_preference[0] is large
    assert with_preference[0] is small


def test_maximum_size_is_never_bypassed() -> None:
    allowed = stream("Movie 1080p 10 GB", seeds=2, url_id="allowed")
    too_large = stream("Movie 1080p 15 GB", seeds=500, url_id="too-large")

    ordered = SELECTOR.order_ideal_streams(
        [too_large, allowed],
        12,
        "",
        prefer_h264=False,
        prefer_smaller_size=False,
    )

    assert ordered == [allowed]


def test_selection_fails_when_all_known_sizes_exceed_limit() -> None:
    streams = [
        stream("Movie 1080p 15 GB", seeds=100, url_id="a"),
        stream("Movie 1080p 20 GB", seeds=200, url_id="b"),
    ]

    assert SELECTOR.order_ideal_streams(streams, 12, "") == []
    with pytest.raises(ValueError, match="maximum size"):
        SELECTOR.choose_best_stream(streams, "1080p", 12, "")


def test_force_transcode_neutralizes_direct_play_codec_penalty() -> None:
    stream_item = stream("Movie 1080p x265 MKV DTS", seeds=10, url_id="hevc")
    assert SELECTOR.cast_compatibility_tier(stream_item) == 2

    stream_item["_bridge_force_transcode"] = True
    assert SELECTOR.cast_compatibility_tier(stream_item) == 0
    assert SELECTOR.direct_play_compatibility_rank(stream_item) == (0, 0, 0, 0)
