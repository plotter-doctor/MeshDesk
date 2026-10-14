# Coverage against official web v2.7.2

Reference commit: `ee5243a2059126ecd799927d21e052b5f5745974`.
Official Python: `2.7.11`. The checked-in source inventory has no differences
from this release. The audit maps **210/210 configuration controls**, including
channels: 207 native field editors and three fixed-position actions. The editor
exposes 34 sections, including 16 modules and eight channels.

| Area | Implemented behavior | Evidence and remaining validation |
|---|---|---|
| USB/serial | Discovery, address selection, official SDK framing | Pseudo-terminal tests; physical Heltec V4 handshake, configuration reads, private messages and reconnect |
| TCP | Address/port, simultaneous profiles, automatic reconnect | Real-SDK local protocol tests and isolation tests |
| HTTP(S) | Official endpoints, bounded polling, certificate verification | Local HTTP integration and rejection of a self-signed HTTPS endpoint; physical network-radio acceptance remains |
| Bluetooth LE | Discovery, Linux PIN pairing, cached BlueZ devices, bounded operations and cleanup | Host pairing succeeded; complete physical BLE handshake still under verification; no tablet adapter detected previously |
| Connections | Edit/name/delete/select profiles, default auto-connect, connection probe, last connection/error | Controller/QML coverage, including Connect/Disconnect state, filtered discovery and scrollable picker; explicit PIN entry is not persisted |
| Chat | Channel/direct messages, replies, ACK/NAK/timeout, unread, search, copy/delete, paged history, export, persistent drafts, UTF-8 byte limit | Two physical private messages remotely acknowledged; protocol and QML tests |
| Nodes | Metrics/position, distance, sorting/filtering, favorites, ignore, removal/key refresh | Controller/model tests; enum filter pickers include hardware and role |
| Requests | Position, telemetry, traceroute, correlated responses and diagnostics | Physical telemetry and directed traceroute passed; physical position response remains |
| Map | Raster tiles/cache/custom provider, zoom/pan/pinch, fit/locate, overlapping-node fan, position precision, neighbor link signal/hover, density/SNR heat, scale, node actions | Projection, cache/network, GC/lifetime and interaction tests; real 106-node USB map test with local fixture tiles; 500-node ARM stress exercise |
| Waypoints | Receive/persist/display, sender/timestamps/expiry/lock/distance/bearing/emoji, creation | Protocol/model/map coverage; physical mesh exchange remains |
| Radio settings | Owner and all config sections, staged drafts, grouped/conditional fields, scalar constraints, JSON editing, save/discard, batch commit | Every section roundtripped with simulator; all physical owner/config sections read |
| Modules | MQTT, serial, external notification, store/forward, range test, telemetry, canned, audio, remote hardware, neighbors, ambient, detection, paxcounter, status, traffic, TAK | All 16 simulated roundtrips; physical firmware exposes 14 (traffic management and TAK unavailable) |
| Channels | Eight slots, PSK generation, role/name/uplink/downlink, precision with metric/imperial choices, selected QR/URL sharing, add links, target-slot import/skip, optional LoRa/replacement | Generated field audit, import preflight, duplicate-target rejection and controller roundtrip tests |
| Security | Key generation/derivation, three admin-key editors, managed-mode validation, identity backup/import/print, backup reminders, verification prompts and responses | Protocol and local tests; end-to-end two-radio identity verification remains |
| Radio actions | Time, fixed position, computer location, canned messages/ringtone, reboot/shutdown/cancel, OTA reboot, DFU, node/config/device reset | Encodings tested; physical Bluetooth-settings transaction/readback/restoration passed; destructive actions deliberately not exercised on the user's configured radio |
| Commands | Search, navigation, connection switching, radio/debug actions, group pinning, clear-all local data | Real QML command dialog and controller tests |
| Preferences | Automatic/dark/light theme, clock, 22 official locales plus native catalogs, map source, manual release check | Locale resource completeness and GUI tests; translations have not received native-speaker review |
| Touch/Unicode | Embedded Qt keyboard, composer resize, software rendering, explicit emoji font fallback, CJK font installation | Actual ARM keyboard tapping and geometry passed; desktop GUI tests |
| Packaging/upgrades | Portable wheel/source kit, Linux bootstrap/menu launcher, pinned dependencies, source/schema/form audits, desktop CI matrix | Host/ARM execution tested; release workflow gates Ubuntu and Windows packages on installed-runtime tests; physical Windows radio acceptance remains |

## Scope and evidence

The official map uses a fixed OSM raster style, disables rotation/perspective,
and comments out its traceroute layer and computer-geolocation control. A vector
style picker and perspective projection are therefore not missing features of
this pinned web release. Native heat rendering serves the same function but is
not pixel-identical to the MapLibre shader. Pixel/layout identity is not claimed.
The web reaction action and waypoint editor callback are also inactive in this
baseline. Firmware flashing/XMODEM transfers are not web routes; DFU entry is
provided.

The field audit is **100% for the recorded 210 controls**. It is not a proof of
100% product behavior on every firmware and OS. Remaining acceptance work is
listed explicitly above. Raw protocol names and some dynamic error/confirmation
text remain English; locale resource completeness does not imply every displayed
sentence has been translated. No simulator can establish real RF reliability,
firmware-reset behavior, OS location-provider support or two-radio PKI success.

Batch writes defer firmware reboots using begin/commit-edit commands, but cannot
roll back partially applied settings. A timeout is reported as an unknown outcome
and preserves the draft; reload before retrying. The ARM stress test also exposes
a performance boundary: changing pages with 500 nodes takes about 0.8–1.4 seconds,
although measured individual typing events remain below 27 ms in that run.
