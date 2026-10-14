# MeshDesk 0.3.0 — first public release

A native, touch-friendly Meshtastic client using Qt Quick, the official Python
SDK and a software renderer suitable for the 1 GB ARM32 tablet.

## Downloads

- **Ubuntu ARM32 tablet / x86-64 desktops:** `meshdesk_0.3.0-1_all.deb`.
  Install with `sudo apt install ./meshdesk_0.3.0-1_all.deb`.
  The architecture-independent package uses Ubuntu's native Qt/Python packages.
- **Windows x86-64:** `MeshDesk-0.3.0-windows-x86_64.zip`.
  Extract the complete archive and run `MeshDesk/MeshDesk.exe`.
  It includes Python and Qt; keep the `_internal` directory beside the executable.
- **Sources:** the application source archive, dependency source archive and Qt
  source archive accompany the binaries. SHA-256 checksum files are included.

## Included

USB/serial, TCP, HTTP and BLE connections; chat and direct messages; node lists;
cached maps and waypoints; radio/module/channel settings; QR sharing; diagnostics;
dark/light themes; 22 locale catalogs; a tablet keyboard and an always-accessible
Exit button. Port/protocol pickers scroll and close on selection. Connection
buttons reflect the selected connection's actual state. Small-screen startup
respects desktop work areas, and map download lifetime regressions are covered.

The configuration audit maps all 210 controls in official web v2.7.2. SDK and
resource versions are pinned, with upgrade audit tools and repeatable packaging.
GitHub Actions gates releases on tests, separate 95% statement/branch coverage,
Ubuntu installed-package checks and Windows executable smoke tests.

## Compatibility and validation limits

The ARMv7 Ubuntu 22.04 tablet is tested directly. Ubuntu x86-64 checks cover
22.04, 24.04, 25.04 and 25.10. Both 25.x releases are end of life; use an LTS
release for ongoing Ubuntu security support.

Windows targets 10/11 x86-64, with automated tests on Windows Server 2025.
The ZIP is unsigned. Its official PyQt5 Windows runtime uses Qt 5.15.2.
Physical Windows USB/Bluetooth, full physical BLE synchronization, two-radio
identity verification and destructive firmware actions are not certified by
simulator success. See `docs/FEATURES.md` for the detailed acceptance matrix.

Licensed **GPL-3.0-only**, with upstream notices retained. MeshDesk is an
independent client and is not an official Meshtastic product.
