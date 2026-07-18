# Changelog

## 0.1.0

- Initial Home Assistant app package.
- Builds `perpetus/stream-server` v0.1.8 for `aarch64` and `amd64`.
- Uses the upstream-supported `libtorrent` torrent backend.
- Exposes the Stremio-compatible API on TCP port 11470.
- Persists configuration and cache under `/data`.
- Adds health monitoring through the `/heartbeat` endpoint.
