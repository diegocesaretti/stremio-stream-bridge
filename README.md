# Stremio Stream Bridge v0.2.0 for Home Assistant

Custom Home Assistant integration that combines Stremio-compatible add-ons instead of treating each add-on as an isolated library.

The default setup uses:

- **Cinemeta** for movie/series catalogs, posters, metadata, seasons and episodes;
- **Torrentio** as a configurable stream provider;
- a Stremio-compatible **stream-server** running on a PC;
- any Home Assistant `media_player` as the playback target.

Home Assistant does not download or transcode the video. It selects a source, builds the stream-server URL when needed, and calls `media_player.play_media` on the chosen entity.

## What's new in v0.2.0

- Multiple catalog/metadata add-ons and multiple stream add-ons.
- Automatic v0.1 migration: the previous add-on remains available and Cinemeta is added as a catalog provider.
- Native Movies and Series sections in Home Assistant Media Sources.
- Popular, New, Featured, genre and year catalogs based on the add-on manifest.
- Pagination using the Stremio `skip` extra.
- Movie details, seasons and episode navigation.
- A stream-choice screen for each movie or episode.
- Automatic stream selection by preferred quality, maximum size, excluded release tags and seed count.
- Manual selection of up to 40 returned streams.
- Aggregate search:
  - native media-source search on Home Assistant versions that expose it;
  - `stremio_stream_bridge.search` plus a search-results folder on earlier versions.
- Connectivity entity showing all loaded providers and partial provider errors.

## Installation or update

1. Copy `custom_components/stremio_stream_bridge` to `/config/custom_components/`.
2. Replace the existing folder when updating from v0.1.0.
3. Restart Home Assistant.
4. Existing v0.1 entries are migrated automatically.
5. Open **Settings → Devices & services → Stremio Stream Bridge → Configure** to review providers and playback preferences.

The PC address must be reachable from Home Assistant and from the target TV/Chromecast. Do not configure the stream-server as `127.0.0.1` or `localhost` unless Home Assistant and the player run on that same PC.

## Default configuration

```text
stream-server:
http://192.168.1.50:11470

Catalog and metadata manifests:
https://v3-cinemeta.strem.io/manifest.json

Stream manifests:
https://torrentio.strem.fun/manifest.json
```

You can enter multiple manifest URLs, one per line. An add-on can appear in both lists when it exposes both catalogs and streams, as in the included static add-on example.

## Natural Home Assistant workflow

Open a compatible media player and browse media:

```text
Stremio Stream Bridge
└── Stremio Media
    ├── Movies
    │   ├── Popular
    │   ├── New
    │   └── Featured
    └── Series
        ├── Popular
        ├── New
        └── Featured
```

A movie opens its available streams. A series opens seasons, then episodes, then streams. The first option is **Play automatically**.

## Playback preferences

In the integration options you can set:

- preferred quality: Auto, 4K, 1080p, 720p, 480p or Lowest;
- maximum stream size in GB (`0` disables the limit);
- comma-separated excluded terms such as `CAM, HDCAM, TS, TELECINE`;
- default `media_player`;
- catalog and stream provider lists.

The selector parses common Torrentio-style titles for resolution, size and seeds. If every result violates the size limit, it retries without the size limit; if every result contains an excluded release tag, it finally falls back to the provider ordering rather than failing silently.

## Search on Home Assistant 2026.7.x

Home Assistant 2026.7.2 includes the media search data models but does not yet route search requests through `media_source`. Use the action below, then reopen **Media → Stremio Stream Bridge**:

```yaml
action: stremio_stream_bridge.search
data:
  query: Interstellar
  media_type: all
```

A folder named `Search: Interstellar` will appear. On Home Assistant versions with media-source search support, the normal search bar is enabled automatically.

## Other actions

Automatic selection:

```yaml
action: stremio_stream_bridge.play
data:
  media_type: movie
  media_id: tt0133093
  media_player: media_player.tv_living
```

Manual provider-result index:

```yaml
action: stremio_stream_bridge.play
data:
  media_type: series
  media_id: "tt0903747:1:1"
  stream_index: 2
  media_player: media_player.tv_living
```

Direct URL or magnet:

```yaml
action: stremio_stream_bridge.play_url
data:
  url: "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"
  media_player: media_player.tv_living
```

## Static add-on example

`examples/static-addon` contains an editable add-on for your own videos. On Windows run `start-addon-server.bat`; it publishes a catalog, metadata and streams without Node or Docker.

## Supported Stremio sources

- direct HTTP/HTTPS URLs;
- HLS and DASH URLs;
- `infoHash` with optional `fileIdx`, trackers and filename hint;
- magnet URLs;
- `ytId`;
- proxy request/response headers through stream-server.

## Limitations

- Playback still depends on the codecs and containers accepted by the target `media_player`.
- Subtitle selection is not yet passed separately to the player.
- Search support in the Home Assistant browser depends on the installed Home Assistant version.
- Provider responses can change; the integration re-fetches a manually selected stream and matches it by URL or torrent hash before playback.

Use providers and media only where you have the right to access and reproduce the content.
