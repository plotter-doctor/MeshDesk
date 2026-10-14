# MeshDesk

A native Meshtastic desktop client built with Qt Quick 5, the official Python
library and SQLite. The default software renderer suits the ARMv7 / 1 GB Ubuntu
tablet. No browser engine is embedded.

**Status:** tested on the x86-64 host and the ARMv7 Ubuntu 22.04 tablet.
The audit maps **210/210 configuration controls** in official web **v2.7.2**;
207 use generated native form metadata and three use fixed-position actions.
See [feature coverage](docs/FEATURES.md) and [measured results](docs/VALIDATION.md)
for the distinction between implemented features and verified hardware behavior.

## Run on the current host

```sh
./run.sh --demo
```

The default simulator speaks the official TCP/protobuf protocol and echoes messages.
Use `--demo-transport serial` for a real virtual serial port, or
`--demo-transport ble` for an in-process Bleak GATT peripheral.
See [testing and GUI review](docs/TESTING.md) for the 95% coverage gate, simulator
limits, fault tests and screenshot gallery.
It never transmits over LoRa. For a real radio, run `./run.sh`, open Connections,
choose USB/serial, TCP, HTTP(S) or Bluetooth LE, and enter its address. Discover
opens a scrollable picker; compatible USB devices are shown by default, with
Show all serial ports available for other hardware. Selection closes the picker.
The main Connect button becomes Disconnect for the selected active endpoint. Multiple
connections can remain active. Select a connection to change the displayed mesh.
Use **Exit** at the top right to close the app. It remains
available on every page, including while the embedded keyboard is open.

## Linux packages (Ubuntu 22.04, 24.04 and 25.x)

Download the `.deb` from [Releases](https://github.com/plotter-doctor/MeshDesk/releases).
The same package serves the ARM32 tablet and x86-64 Ubuntu desktops and includes
its pinned Python libraries:

```sh
sudo apt install ./meshdesk_0.3.0-1_all.deb
meshdesk
```

It adds a MeshDesk application-menu entry. See [Debian packages and releases](docs/DEBIAN.md)
for package builds, upgrades and the GitHub Actions release workflow.
The source-checkout installation remains available below.

Install the distribution's ARM Qt packages rather than a browser or Flutter
runtime. This installation has been exercised on the target tablet.

```sh
sudo apt install python3-venv python3-pip python3-pyqt5 python3-pyqt5.qtquick \
  python3-cryptography qml-module-qtquick2 \
  qml-module-qtquick-window2 qml-module-qtquick-layouts \
  qml-module-qtquick-controls2 qml-module-qtquick-templates2 \
  qml-module-qtgraphicaleffects qml-module-qtquick-virtualkeyboard qtvirtualkeyboard-plugin \
  qml-module-qt-labs-folderlistmodel \
  fonts-noto-color-emoji fonts-noto-cjk
./scripts/bootstrap.sh
./run.sh --demo
```

QtPrintSupport is included in the PyQt5 distribution. Optional computer-location
support uses `python3-pyqt5.qtpositioning` and an OS location provider. Bluetooth
needs BlueZ and an available adapter; serial access normally needs membership of
the `dialout` group. Re-login after changing group membership. Use an OS on-screen
keyboard on touch devices, or the embedded keyboard enabled automatically on ARM
when Qt Virtual Keyboard is installed (`--keyboard on|off|auto`). The existing tablet graphics driver is not accelerated;
keep the default software renderer until graphics support changes.

The protobuf dependency has a pure-Python wheel for ARM32. That backend was
tested on ARM32: approximately 80 MiB peak sampled idle RSS and 94 MiB for
500 nodes plus 5,000 stored messages. These are short, reproducible samples. Qt and
cryptography receive updates through the distribution; SDK dependencies are
constrained in `requirements-linux.lock`.
The bootstrap script disables optional D-Bus Cython extensions on ARM32 and also
uses any dependency wheels supplied in `dist/`.

## Other desktop platforms

The application code uses portable Qt, pyserial and Bleak interfaces. In a Python
3.10+ virtual environment, install `pip install -e '.[desktop]'` and run `meshdesk`.
A portable Windows x86-64 ZIP is built and tested by GitHub Actions; extract it
and run `MeshDesk.exe`. See [Windows installation](docs/WINDOWS.md).
Release checks cover Ubuntu 22.04, 24.04, 25.04 and 25.10 on x86-64. Ubuntu 25.x
is end of life; prefer an LTS release for ongoing OS security updates.
Physical Windows radio acceptance remains separate from the simulator tests.
No macOS, Android or iOS package is supplied.

## Using the client

- Chat: channels, direct messages, replies, delivery acknowledgements, unread
  counts, search, paged history, copy/delete and export.
- Nodes: names, signal, battery, position, distance, filters, favorites, ignore,
  removal/key refresh, position requests, traceroute and identity verification.
- Map: native raster tiles, cached offline content, node/waypoint markers,
  neighbor links, position precision, density/SNR overlays, pan/pinch/zoom and
  location controls. Internet tile fetching starts disabled.
- Settings: read a section, edit a draft, then explicitly save. Writes wait for
  acknowledgement and readback. JSON import/export handles advanced fields.
  Drafts survive page navigation and can be committed together. Selected channels
  can be shared by URL/QR and imported into chosen slots, with optional LoRa
  settings and explicit replacement controls. Identity keys can
  be generated, backed up or printed. Radio actions include fixed position,
  canned messages, ringtone, time, reboot/shutdown with cancellation, OTA reboot, DFU and resets.
- Activity: diagnostics, telemetry, traceroute responses and key-verification
  prompts. The header indicator opens pending notifications.
- Preferences: automatic/dark/light theme, clock, 22 official translation catalogs
  with native UI translations, map source and
  manual official-release checks. Ctrl+K opens commands; Ctrl+1–4 switches pages.

Settings changes that restart firmware may disconnect the radio before readback;
the application reports an unknown/different outcome instead of claiming a
verified save. Reconnect and reload before retrying. Batch saves and channel imports use firmware begin/commit-edit commands to defer
restarts. This is not an atomic rollback transaction: a failure can leave a subset
of changes applied. Unconfirmed drafts remain available for inspection.

## Data and privacy

Local state lives in Qt's application-data directory (normally
`~/.local/share/MeshDesk/MeshDesk/` on Linux). Override it with `--data-dir PATH`.
Messages and nodes are scoped to a connection; schema version 1 uses SQLite WAL.
The directory is owner-only and database/exports use mode 0600. The database is
not encrypted. Admin session passkeys are excluded from stored packet/node data.
Channel keys and private keys are exported only through explicit user actions.

There is no automatic release check or telemetry. Map fetching and checking
official releases are explicit actions. Tile providers receive tile requests;
nodes are overlaid locally. Never share identity backups publicly.

## Development and tests

```sh
PYTHONNOUSERSITE=1 .venv/bin/python -m pip install -e '.[test]'
PYTHONNOUSERSITE=1 xvfb-run -a .venv/bin/python -m pytest -q --cov --cov-report=html --cov-report=json:artifacts/coverage.json
.venv/bin/python tools/check_coverage.py artifacts/coverage.json
PYTHONNOUSERSITE=1 .venv/bin/python tools/audit_compatibility.py
```

Tests exercise the real official SDK over TCP, HTTP and a POSIX pseudo terminal;
read/write every settings section; test message ACKs/replies, errors, isolation
and reconnection; and operate the actual QML window. Set `MESHDESK_ARTIFACTS` to
save screenshots. They do not emulate RF propagation, encryption or firmware
reboots. [Architecture and upgrades](docs/UPGRADING.md) explain the update process.

For an opt-in physical USB test, close other applications using the serial port:

```sh
PYTHONNOUSERSITE=1 .venv/bin/python tools/hardware_smoke.py \
  --port /dev/ttyACM0 --data-dir /tmp/meshdesk-hardware \
  --output artifacts/hardware.json
```

This reads configuration, opens all seven screens and reconnects without
changing radio settings. Add `--recipient '!FULLNODEID' --message 'Test message'`
to explicitly enable one private message; the tool requires a unique known
remote node and verifies the acknowledgement's sender and request ID. Optional
`--probe telemetry --probe traceroute` enables directed read requests to that
recipient. `--keep-open` leaves the connected GUI open after success. Reports
exclude keys and configuration values. See [hardware results](docs/VALIDATION.md).

To add a Linux application-menu entry for this checkout, run
`./scripts/install-desktop.sh`. Build a wheel and source kit with
`.venv/bin/python tools/build_release.py`.

Copyright 2026 MeshDesk contributors. Licensed under [GPL-3.0-only](LICENSE). Meshtastic and its official web translations remain the
work of their respective contributors; see [THIRD_PARTY.md](THIRD_PARTY.md).
