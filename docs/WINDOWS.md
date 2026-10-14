# Windows portable package

Extract the entire `MeshDesk-VERSION-windows-x86_64.zip`, open the `MeshDesk`
folder and run `MeshDesk.exe`. Keep `_internal` beside the executable. Python
installation and administrator access are not required. Use Exit at the top
right to close the app. This package targets Windows 10/11 x86-64; the automated
executable checks run on the GitHub Windows Server 2025 runner.

The package is unsigned. Windows may show its normal unknown-publisher warning.
Verify the download against the release's SHA-256 checksums before running it.
Application data lives in the user's Qt application-data directory, separate
from the extracted program. Startup diagnostics go to
`%LOCALAPPDATA%\MeshDesk\logs\startup.log`.

Connect USB radios using their COM port. Bluetooth requires a working Windows
adapter and OS permissions. Automated checks use offline, TCP and in-process BLE
simulators; they do not certify physical Windows Bluetooth or USB hardware.
The POSIX virtual-serial simulator is available in the Linux package.

The official Windows PyQt5 wheel uses Qt 5.15.2. Linux uses Qt maintained by the
distribution. The Qt wheel also supplies its own OpenSSL 1.1.1b libraries for
Qt HTTPS; Python and cryptography use their separate OpenSSL 3 runtimes. This is
a legacy Windows Qt runtime. `dependencies.json` records exact bundled versions. Shared Qt DLLs
remain separate in `_internal` and can be replaced by compatible rebuilt copies.
Dependency licenses are retained with their distribution metadata in `_internal`.
The release supplies MeshDesk source, third-party source archives and Qt source.

Build with 64-bit Python 3.12 on Windows:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-windows.txt .
.venv\Scripts\python tools/build_windows.py
.venv\Scripts\python tools/smoke_windows.py dist/windows/MeshDesk/MeshDesk.exe
```

The build uses a directory bundle to avoid unpacking a large one-file executable
on every launch. GitHub Actions builds, tests and publishes the portable archive.
