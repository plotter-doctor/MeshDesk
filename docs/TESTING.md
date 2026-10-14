# Testing and GUI review

The Linux CI job enforces **at least 95% statement coverage and 95% branch coverage**
across the entire `src/meshdesk` Python package. No application module is omitted.
Startup and crash regression subprocesses contribute coverage. `pytest-cov` also
enforces a 95% combined score; `tools/check_coverage.py` checks each metric separately. QML is not Python;
its visual and interaction checks are reported separately, not added to this percentage.

```sh
.venv/bin/python -m pip install -e '.[test]'
PYTHONNOUSERSITE=1 MESHDESK_ARTIFACTS=artifacts/screenshots \
  xvfb-run -a .venv/bin/python -m pytest -q --cov \
  --cov-report=html --cov-report=json:artifacts/coverage.json \
  --cov-report=xml:artifacts/coverage.xml --junitxml=artifacts/results.xml
.venv/bin/python tools/check_coverage.py artifacts/coverage.json
```

Open `artifacts/coverage/index.html` for uncovered statements and branches, and
`artifacts/screenshots/layout/index.html` for the rendered GUI gallery and
`artifacts/screenshots/variants/index.html` for populated/alternate states. The same
artifacts are uploaded by CI, including failed runs. Windows runs portable
protocol and GUI tests; the enforced coverage baseline is Linux, including BlueZ
contract tests and POSIX serial ports. CI configuration is not evidence that a
remote platform run has passed.

## Simulators

All simulators use the same protobuf radio state. Settings are read back through
the official SDK; messaging receives correlated acknowledgements and synthetic
replies. They never transmit LoRa packets or alter a physical radio.

```sh
./run.sh --demo --demo-transport tcp --data-dir /tmp/meshdesk-tcp-demo
./run.sh --demo --demo-transport serial --data-dir /tmp/meshdesk-serial-demo
./run.sh --demo --demo-transport ble --data-dir /tmp/meshdesk-ble-demo
```

- **TCP:** loopback Meshtastic framing; also available as a separate process via
  `.venv/bin/python -m meshdesk.simulator --port 4403`.
- **Serial:** a real POSIX pseudo-terminal, usable by any serial client including
  the Meshtastic CLI. Run `.venv/bin/python -m meshdesk.simulator --transport serial`
  and use its printed `/dev/pts/...` address. Add `--fragment-size 1 --delay .001`
  to exercise partial reads. Reconnecting preserves simulated settings.
- **BLE:** an in-process GATT peripheral through Bleak's backend interface. The
  official SDK's receiver, ToRadio/FromRadio characteristics, notifications,
  timeout handling and disconnect cleanup run normally. No adapter is needed.
  This is **not an OS-advertised Bluetooth device**. It does not test BlueZ,
  CoreBluetooth, WinRT, real pairing, RF interference or firmware timing.

`VirtualBLESimulator` exposes response dropping, read-only or all-operation delays and rejected writes
for failure tests. BlueZ object lookup, PIN-agent scoping and cleanup have separate
D-Bus contract tests. These tests substitute the external D-Bus service and do not
pair with the host's real adapter. Physical BLE acceptance remains separate.

## GUI acceptance

The automated layout audit covers all seven pages at 1024×600, 600×1024 and
480×600, English/dark and Polish/light, with top/bottom scroll positions. It also
renders every settings section at tablet and narrow widths, including intermediate
scroll positions, populated node details, channel sharing/import, dialogs, map
menus and identity-verification notices. A second sweep covers populated
conversations with long names, every connection transport including BLE pairing,
JSON editing and the bottom of channel/radio-action tabs. It records visible control bounds and
rejects horizontal clipping, overlaps between unrelated controls, QML errors and
binding loops. Intentional overlap behind modal popups is excluded from the
popup-content check.

`tests/test_window_fit.py` additionally runs the real UI under Openbox in isolated
Xvfb displays at 1024×600, 600×1024 and 1280×1024, with a reserved 32-pixel desktop
panel. It checks the entire decorated window against the usable desktop area at
startup, restored and maximized, including bottom chat controls and all seven
pages. Openbox may hide its cosmetic border at the screen edge on restore; only
that border thickness is permitted outside the work area, while every client
pixel must fit. Install `openbox`, `xvfb` and `x11-utils` to run these Linux-only cases. Whole-desktop
screenshots include title bars and panels; content-only screenshots cannot detect
a window extending below the screen. To check an installed package on its actual
desktop, run `python3 tools/check_window_fit.py --output artifacts/window-fit`
in that desktop session. Use `--source --start-wm` only inside an isolated Xvfb
display when testing the checkout.

Interaction tests operate the real composer, buttons, discovery picker, protocol
popup, map hit targets, channel/settings workflows and reconnection controls. The
map lifecycle regression repeatedly collects Python garbage during pending local
HTTP tile downloads and page destruction. Invalid and oversized tile responses
are tested against a loopback server. No private radio positions are sent to an
external tile provider by this suite.

Screenshots are inspected by a person or visual review in addition to geometry
checks. Geometry passing cannot prove that wording, contrast or every gesture is
ideal. The checked language/size matrix does not establish every translation,
font, display scale or operating-system style. Tablet keyboard behavior is an
additional opt-in test when Qt Virtual Keyboard is installed:

```sh
QT_IM_MODULE=qtvirtualkeyboard QT_VIRTUALKEYBOARD_DESKTOP_DISABLE=1 \
  PYTHONNOUSERSITE=1 xvfb-run -a .venv/bin/python -m pytest -q tests/test_touch_keyboard.py
```

## Updating dependencies

Keep the coverage gate and simulator/GUI tests enabled when changing SDK,
protobuf, Bleak or Qt versions. Run `tools/audit_compatibility.py` as well; the
210-control web-form audit is configuration parity, not code coverage. After
passing automated tests, verify USB and BLE hardware independently. Simulator
success cannot certify firmware resets, encryption, pairing or LoRa delivery.
