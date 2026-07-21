"""Latin native-search result filtering tests."""

import asyncio
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1] / "custom_components" / "stremio_stream_bridge"
PACKAGE = "bridge_latin_search_test"

pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg

const = types.ModuleType(f"{PACKAGE}.const")
const.PROFILE_DEFAULT = "default"
const.PROFILE_LATIN = "latin"
sys.modules[const.__name__] = const

spec = spec_from_file_location(f"{PACKAGE}.latin_search_patch", ROOT / "latin_search_patch.py")
assert spec is not None and spec.loader is not None
SEARCH = module_from_spec(spec)
sys.modules[spec.name] = SEARCH
spec.loader.exec_module(SEARCH)


class FakePreferences:
    hide_non_matching = True

    async def _safe_availability(self, media_type, meta):
        return {"yes": True, "no": False, "unknown": None}[meta["id"]]


class FakeManager:
    _bridge_source_preferences = FakePreferences()


def test_search_keeps_matches_and_uncertain_results() -> None:
    metas = [
        {"id": "yes", "_bridge_media_type": "movie"},
        {"id": "no", "_bridge_media_type": "movie"},
        {"id": "unknown", "_bridge_media_type": "series"},
    ]

    result = asyncio.run(SEARCH.filter_latin_search_results(FakeManager(), metas))

    assert [meta["id"] for meta in result] == ["yes", "unknown"]
