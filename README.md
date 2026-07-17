# Stremio Stream Bridge v0.3.1 for Home Assistant

Custom Home Assistant integration that combines Stremio-compatible catalog, stream and subtitle add-ons into one browsable media library.

The default setup uses:

- **Cinemeta** for movie/series catalogs, posters, metadata, seasons and episodes;
- **Torrentio** as the stream provider;
- **OpenSubtitles v3** as the subtitle provider;
- a Stremio-compatible **stream-server** running on a PC;
- a Home Assistant `media_player` as the playback target.

Home Assistant does not download or transcode the video. It selects a source, builds the stream-server URL and calls `media_player.play_media` on the selected entity.

## What's new in v0.3.1

- Home Assistant now downloads and converts subtitles itself instead of depending only on the stream-server converter.
- Temporary WebVTT tracks are served from a random, expiring Home Assistant URL with permissive CORS headers.
- Handles plain, gzip and ZIP subtitles in UTF-8, UTF-16, Windows-1252 and Latin-1.
- Retries subtitle providers without filename/hash extras when their deployed route rejects extras.
- Cast playback is explicitly marked as `BUFFERED` instead of `LIVE`.
- Subtitle-provider failures are visible in logs and in the connectivity sensor attributes.
- A configurable **Home Assistant subtitle base URL** lets you force the Raspberry Pi LAN address that the Chromecast can reach.
- Includes the v0.3 ideal-link filter: 1080p, most seeders, then smallest file.

## Installation or update

1. Copy `custom_components/stremio_stream_bridge` to `/config/custom_components/`.
2. Replace the existing folder when updating.
3. Restart Home Assistant.
4. Existing entries are migrated automatically.
5. Open **Settings → Devices & services → Stremio Stream Bridge → Configure**.

The PC address must be reachable from Home Assistant and from the target TV/Chromecast. Do not configure stream-server as `127.0.0.1` or `localhost` unless all components run on the same computer.

## Default providers

```text
stream-server:
http://192.168.1.50:11470

Catalog and metadata manifests:
https://v3-cinemeta.strem.io/manifest.json

Stream manifests:
https://torrentio.strem.fun/manifest.json

Subtitle manifests:
https://opensubtitles-v3.strem.io/manifest.json
```

Multiple manifest URLs can be entered, one per line. Leave the subtitle manifest field empty to disable subtitle providers.

## Ideal link filter

Enable **Ideal-link filter** in the integration options. Automatic playback then ignores the normal preferred-quality selector and applies this order:

```text
1080p first
→ highest seed count
→ smallest file
```

Example candidates:

```text
1080p · 80 seeds · 2.1 GB
1080p · 140 seeds · 5.8 GB
1080p · 140 seeds · 3.4 GB  ← selected
4K    · 500 seeds · 18 GB
```

The 3.4 GB 1080p source wins because 1080p is required when available, 140 is the highest seed count in that group, and 3.4 GB is smaller than the other 140-seed result.

The maximum-size and excluded-keyword settings are still applied first. Common exclusions are `CAM, HDCAM, TS, TELECINE, SCREENER`.

## Subtitles

Subtitle options:

- mode: `automatic` or `disabled`;
- preferred languages, for example `spa, eng`;
- convert subtitles to WebVTT;
- optional **Home Assistant subtitle base URL**.

For Google Cast entities, Home Assistant downloads the selected subtitle, converts it and exposes a temporary URL such as:

```text
http://192.168.1.20:8123/api/stremio_stream_bridge/subtitle/RANDOM_TOKEN.vtt
```

Set **Home Assistant subtitle base URL** to the Raspberry Pi LAN URL when automatic detection produces `localhost`, an unreachable hostname, HTTPS with a certificate the receiver does not trust, or the wrong network interface.

Native external subtitle support is currently limited to Home Assistant entities provided by the **Cast** integration. The connectivity sensor exposes `external_subtitles_supported`; it must be `true` for the configured default player. Other media-player integrations receive the video normally but may rely on subtitles embedded in the MKV or on player-specific support.

### Subtitle troubleshooting

After trying playback, inspect **Settings → System → Logs** for `stremio_stream_bridge`. Also open the integration connectivity sensor attributes:

- `external_subtitles_supported`: must be `true`;
- `subtitle_provider_errors`: should be empty;
- `default_player`: confirms which entity was evaluated.

The Chromecast must be able to open the configured Home Assistant subtitle base URL directly over the LAN.

Run the diagnostic action before playback:

```yaml
action: stremio_stream_bridge.subtitle_diagnostics
data:
  media_type: movie
  media_id: tt0133093
  media_player: media_player.tv_living
```

The response reports `cast_entity`, subtitle count, available languages, provider errors and the exact temporary `delivery_url`. Open that URL from another device on the LAN to verify that Home Assistant is serving valid WebVTT.

## Natural Home Assistant workflow

Open a compatible player and browse media:

```text
Stremio Stream Bridge
└── Stremio Media
    ├── Movies
    └── Series
```

A movie opens its stream list. A series opens seasons, episodes and then streams. At the top you get:

```text
▶ Ideal link · 1080p · most seeds · smallest size
▶ Ideal link · without subtitles
```

Manual source entries remain available below those automatic options.

## Actions

Automatic ideal-link playback with automatic subtitles:

```yaml
action: stremio_stream_bridge.play
data:
  media_type: movie
  media_id: tt0133093
  media_player: media_player.tv_living
```

Automatic playback without subtitles:

```yaml
action: stremio_stream_bridge.play
data:
  media_type: movie
  media_id: tt0133093
  media_player: media_player.tv_living
  disable_subtitles: true
```

Manual stream index:

```yaml
action: stremio_stream_bridge.play
data:
  media_type: series
  media_id: "tt0903747:1:1"
  stream_index: 2
  media_player: media_player.tv_living
```

Search on Home Assistant versions without native media-source search:

```yaml
action: stremio_stream_bridge.search
data:
  query: Interstellar
  media_type: all
```

## Supported Stremio sources

- direct HTTP/HTTPS URLs;
- HLS and DASH URLs;
- `infoHash` with optional `fileIdx`, trackers and filename hint;
- magnet URLs;
- `ytId`;
- proxy request/response headers through stream-server;
- subtitle objects included directly in a stream;
- separate Stremio subtitle add-ons.

## Limitations

- Playback depends on codecs and containers accepted by the target player.
- External subtitles are currently implemented specifically for Google Cast entities.
- Subtitle synchronization depends on the subtitle provider match; filename, hash and size hints improve it when the stream add-on supplies them.
- Provider response formats may change.

Use providers and media only where you have the right to access and reproduce the content.
