# Architecture and upgrade procedure

`radio.py` is the boundary around the official library. It contains transport
construction, session-passkey handling, requests, acknowledgements and settings
readback. The HTTP adapter uses official `/api/v1/toradio` and
`/api/v1/fromradio?all=false` endpoints with SDK decoding. It has bounded timeouts
and checks TLS certificates. SDK private APIs used here are intentionally covered
by protocol integration tests; they must be reviewed when the dependency changes.

`schema.py` derives all field types, enums and nested/repeated values from official
protobuf descriptors. New fields become editable when the pinned library updates.
Special operations such as key verification, channel imports and fixed position
remain explicit code and need review. Generated fields do not automatically prove
that new web workflows have been implemented.

`controller.py` owns Qt state; workers serialize operations per radio and signal
results back to the Qt thread. Session generations reject stale callbacks after
disconnect/switch/removal. `FieldModel` updates individual settings rows so incoming
packets do not destroy the focused editor. `store.py` owns persistence. The current
schema is version 1; future incompatible changes require an explicit migration and
backup/restore test. Message views page 100 rows; diagnostics retain 2,000 events.

`mapview.py` paints raster tiles and overlays directly with QPainter. There is no
WebView, WebGL or idle animation loop. Tile memory holds 48 decoded images, disk
cache is limited to 50 MB and at most eight requests are in flight. The map cache
uses Qt's standard cache directory even when `--data-dir` is overridden.

## Accepting an official release

1. Use Preferences → Check official releases (or inspect the official release
   pages). The runtime never installs an update itself. Canonical tags are in
   `src/meshdesk/resources/upstream.json`; the web commit is pinned as well.
2. Check out the candidate **official stable release** in a separate directory.
   Do not replace the baseline yet. Run
   `python tools/vendor_upstream.py /path/to/candidate` to list added, removed and
   changed UI/protocol source files. This check exits nonzero for a changed source.
3. Create an isolated candidate Python environment. Update the SDK/protobuf pins
   in `pyproject.toml` and Linux constraints together. Resolve and review dependency
   changes. Do not overwrite the working runtime before the candidate passes.
4. Run `python tools/audit_compatibility.py --web-source /path/to/candidate`.
   Inspect differences in `upstream/python-schema.json` and all changed web UI
   workflows, not only field names. Extend `docs/FEATURES.md` and protocol/UI tests.
5. After review, use `tools/vendor_upstream.py SOURCE --write` to refresh official
   translations/source hashes, `tools/vendor_forms.py SOURCE --write` to refresh
   grouping/conditional fields and scalar validation, and `tools/audit_compatibility.py --web-source SOURCE
   --accept` to record the new field/schema baseline. Review the resulting diff.
6. Run the whole suite and inspect screenshots. Exercise TCP, serial and Bluetooth
   with supported firmware, key verification with a second radio, and persistence
   using a copy of an existing database. Verify Linux ARM32 memory and responsiveness.
7. Update canonical release tags/commit and the evidence in `docs/VALIDATION.md`,
   then build a wheel and source kit with `python tools/build_release.py`. The wheel includes QML
   and localization resources. Keep the previous wheel and database backup for
   rollback. Never downgrade an incompatible database in place.

For tablet distribution, build `python tools/build_deb.py` and install the result
with `apt install ./dist/meshdesk_VERSION-REVISION_all.deb`. Run the installed
package checks in [DEBIAN.md](DEBIAN.md), including a clean Ubuntu installation
and the actual ARM tablet. The package workflow validates version tags, runs the
test/coverage gates, and publishes tagged releases after package verification.
Keep Python 3.10 compatibility dependencies in the Linux lock file even if the
build host uses a newer interpreter.

The source inventory is deliberately sensitive: a text-only web change can flag
a review even if it adds no features. The form audit currently maps 210 controls;
it cannot detect all new buttons, routes or behavior by itself. CI checks pins,
schema and the recorded form mapping on each push/PR. It does not assert that an
unreviewed future upstream release has already been adopted.


`forms.py` applies the reviewed web ordering, labels, groups, dependencies and
validation to generated protobuf fields. `tools/vendor_forms.py SOURCE` checks
that this metadata still matches a candidate source checkout. Changes to complex
validators or operational workflows require manual review and regression tests.
`ble.py` owns bounded SDK BLE operations and the ephemeral Linux pairing agent;
its cached BlueZ device adaptation must be reviewed with Bleak/SDK upgrades.
Native translations live separately from upstream catalogs to preserve clean
updates. Do not edit generated official catalogs to translate new native strings.

The CI matrix covers Linux Python 3.10/3.12 and Windows x86-64.
Its configuration is checked in; a local Linux pass is not evidence that those
external runners have executed successfully. Run the opt-in keyboard test on a
Qt Virtual Keyboard runtime with `QT_IM_MODULE=qtvirtualkeyboard` and
`QT_VIRTUALKEYBOARD_DESKTOP_DISABLE=1` before creating QApplication.

## Regression gates

Run the coverage command in [TESTING.md](TESTING.md) after every SDK, protobuf,
Bleak or Qt update. Both statement and branch coverage must stay at or above 95%.
The serial pseudo-terminal and virtual GATT peripheral run the official SDK, so
transport API changes must pass these tests as well as the configuration audit.
Review the GUI gallery for changed fields, long labels, dialogs and narrow layouts.
Keep the real USB/BLE acceptance checks separate from simulator results.
