#!/usr/bin/env bash
set -euo pipefail

OPTIONS_FILE=/data/options.json
LOG_LEVEL=info

if [[ -f "${OPTIONS_FILE}" ]]; then
  LOG_LEVEL="$(jq -r '.log_level // "info"' "${OPTIONS_FILE}")"
fi

case "${LOG_LEVEL}" in
  trace|debug|info|warn|error) ;;
  *) LOG_LEVEL=info ;;
esac

export HOME=/data
export XDG_CONFIG_HOME=/data/config
export XDG_CACHE_HOME=/data/cache
export RUST_LOG="server=${LOG_LEVEL},stream_server=${LOG_LEVEL},enginefs=${LOG_LEVEL}"

mkdir -p "${XDG_CONFIG_HOME}" "${XDG_CACHE_HOME}"

echo "Starting Stremio Stream Engine on port 11470 (log level: ${LOG_LEVEL})"
exec /usr/local/bin/stream-server --no-tray
