"""Secondary provider marker tests."""

import asyncio
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1] / "custom_components" / "stremio_stream_bridge"
PACKAGE = "bridge_secondary_marker_test"

pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg

api = types.ModuleType(f"{PACKAGE}.api")


class StremioProtocolError(Exception):
    pass


class FakeAddonClient:
    def __init__(self, session, manifest_url):
        self.manifest_url = self._normalize_manifest_url(manifest_url)

    @staticmethod
    def _normalize_manifest_url(value):
        value = str(value).strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise StremioProtocolError("invalid")
        if value.endswith("/manifest.json"):
            return value
        return f"{value}/manifest.json"


api.StremioAddonClient = FakeAddonClient
api.StremioProtocolError = StremioProtocolError
sys.modules[api.__name__] = api

spec = spec_from_file_location(f"{PACKAGE}.secondary_provider", ROOT / "secondary_provider.py")
assert spec is not None and spec.loader is not None
SECONDARY = module_from_spec(spec)
sys.modules[spec.name] = SECONDARY
spec.loader.exec_module(SECONDARY)


class FakeManager:
    def __init__(self):
        self._roles = {}
        self._clients = {}
        self.refreshes = 0

    async def async_refresh(self):
        self.refreshes += 1
        return []


def test_installer_records_normalized_secondary_url() -> None:
    manager = FakeManager()
    result = asyncio.run(
        SECONDARY.install_secondary_stream_provider(
            manager, object(), "https://secondary.example/addon"
        )
    )

    assert result == "https://secondary.example/addon/manifest.json"
    assert manager._bridge_secondary_stream_provider_url == result
    assert manager._roles[result] == {"stream"}
    assert manager.refreshes == 1
