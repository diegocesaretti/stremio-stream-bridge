# Stremio Stream Bridge v0.4.3 for Home Assistant

Custom Home Assistant integration that combines Stremio-compatible catalogs, stream providers and subtitles, then sends the selected media through a Stremio stream-server running on a PC.

## v0.4.3 direct-playback restoration

- Fixes the false **cannot connect** error caused by temporary failures in optional subtitle, Latin Audio or Sports add-ons. Only the main PC stream-server and the core catalog/stream providers are mandatory.
- Fixes configured manifest URLs containing commas, such as Torrentio language/provider settings, being split into broken URLs.
- Older v0.4 entries with empty optional profiles are migrated automatically and receive prefilled Latin Audio and Sports manifests.
- The PC stream-server URL is now editable from **Configure** and defaults to the address already used by this installation: `http://192.168.1.145:11470`.
- The subtitle base field recommends the Raspberry Pi/Home Assistant LAN URL detected through the route to the PC.

- Restores the direct stream URL used by versions that played successfully before v0.4.
- Migrates existing `automatic` audio mode entries to `direct`.
- Uses `hlsv2` only when `force_transcode` is selected explicitly.
- Tests a generated `hlsv2` playlist and falls back to the direct URL if conversion fails.

Recommended prefilled optional profiles:

```text
Latin Audio:
https://torrentio.strem.fun/providers=yts,eztv,rarbg,1337x,thepiratebay,kickasstorrents,torrentgalaxy,magnetdl,horriblesubs,nyaasi,rutracker,mejortorrent,cinecalidad|sort=size|language=spanish,latino|qualityfilter=brremux,hdrall,dolbyvision,4k/manifest.json

F1 and Sports:
https://stremverse1.alwaysdata.net/manifest.json
```

## v0.4.1 Cast hotfix

- HLS and DASH URLs now use the MIME type of the resolved playlist, even when an add-on supplies a misleading filename hint.
- Proxied playlists are checked before Cast playback. Dead links are skipped automatically.
- F1/Sports playback tries the next source instead of blindly using a broken first result.

## What is new in v0.4.0

- Borderless Google Cast subtitles: transparent background/window and `edgeType: NONE`.
- Audio compatibility mode enabled by default. Torrent and MKV-like sources can be routed through stream-server `hlsv2` as H.264 video with AAC stereo audio.
- Direct ideal-link playback enabled by default: selecting a movie, episode or event starts playback instead of opening the source list.
- Optional **Latin Audio** provider profile. It uses only the configured Latin stream add-ons and always disables subtitles.
- Optional **F1 and Sports** provider profile. It uses the add-on's own catalogs and streams and does not request subtitles.
- Fixed migration logic from old versions.

## Installation or update

1. Copy `custom_components/stremio_stream_bridge` to `/config/custom_components/`.
2. Replace the existing folder when updating.
3. Restart Home Assistant.
4. Keep the existing config entry; it migrates automatically to version 6.
5. Open **Settings → Devices & services → Stremio Stream Bridge → Configure**.

## Default profile

```text
Catalog and metadata:
https://v3-cinemeta.strem.io/manifest.json

Default streams:
https://torrentio.strem.fun/manifest.json

Subtitles:
https://opensubtitles-v3.strem.io/manifest.json
```

The ideal-link selector prefers:

```text
1080p
→ highest seeder count
→ smallest file when seeders are tied
```

## Direct playback

**Play ideal link when selecting an item** is enabled by default.

- Selecting a movie starts the ideal link directly.
- Selecting a series still opens seasons.
- Selecting an episode starts the ideal link directly.
- Selecting a sports event/channel tries provider sources in order and skips dead proxied playlists.

Disable the setting to restore the manual list of source links.

## Audio compatibility

The **Audio compatibility** option has three modes:

- `direct` — default. Sends the original stream-server URL directly to the player, restoring the route used before v0.4.
- `automatic` — retained for backwards compatibility and currently behaves like `direct`.
- `force_transcode` — explicitly asks stream-server for H.264/AAC HLS. If `hlsv2` fails, playback falls back to the original direct URL.

Direct playback is the safe default because not every stream-server build can generate `hlsv2`. Use `force_transcode` only for files that play video without compatible audio.

## Borderless subtitles

When the target is a Home Assistant Cast entity, the integration modifies the outgoing Cast LOAD message so subtitle style uses:

```text
edgeType: NONE
background: transparent
window: none
```

Subtitles are still downloaded, converted to WebVTT and served temporarily by Home Assistant.

## Latin Audio profile

Put one or more Stremio manifest URLs in **Latin Audio manifests**. A stream-only add-on is enough: when it does not provide catalogs, the integration mirrors the normal Cinemeta movie/series catalogs and queries only the Latin provider for playback.

The browser then shows:

```text
Stremio Media
├── Películas
├── Series
├── Audio Latino
│   ├── Películas
│   └── Series
└── F1 y Deportes
```

The Latin profile always plays without external subtitles.

Action example:

```yaml
action: stremio_stream_bridge.play
data:
  media_type: movie
  media_id: tt0133093
  profile: latin
  media_player: media_player.tv_living
```

## F1 and Sports profile

Put the sports add-on manifest in **F1 and Sports manifests**. For natural navigation, the add-on must expose both `catalog` and `stream` resources.

Its catalog types may be `tv`, `channel`, `movie`, `series` or another valid Stremio type. The integration creates a dedicated **F1 y Deportes** section and uses only that provider group for playback.

Action example:

```yaml
action: stremio_stream_bridge.play
data:
  media_type: tv
  media_id: event-id-from-addon
  profile: sports
  media_player: media_player.tv_living
```

## Notes

- The PC stream-server must be reachable from Home Assistant and from the playback device.
- HLS audio compatibility depends on FFmpeg/transcoding support in the stream-server build.
- External subtitles are applied only to Home Assistant entities belonging to the Cast integration.
- Public add-ons can change or disappear. Optional-provider failures are shown in the connectivity sensor but no longer prevent the core integration from loading.
- Use media and providers only where you have the right to access and reproduce the content.
