# Third-party notices

MeshDesk is distributed under GPL-3.0-only; see LICENSE.

- **Meshtastic web contributors:** official localization catalogs in
  `src/meshdesk/resources/locales/` are derived from meshtastic/web v2.7.2,
  GPL-3.0-only, https://github.com/meshtastic/web/tree/v2.7.2 . Source hashes and
  provenance are retained under `upstream/` and in the canonical release manifest.
  Catalogs are flattened for native lookup; missing native strings use English.
- **Meshtastic Python contributors:** protocol/client dependency,
  GPL-3.0-only, https://github.com/meshtastic/python .
- **Riverbank Computing:** PyQt5, GPL v3/commercial dual license,
  https://www.riverbankcomputing.com/software/pyqt/ .
- Qt, protobuf, qrcode, cryptography, Bleak and other dependencies retain their
  own licenses. Their license texts remain in the bundled distribution metadata.
  The Linux package uses Ubuntu's Qt and cryptography packages and bundles the
  pinned pure-Python SDK dependencies. The Windows ZIP also bundles CPython,
  PyQt5, Qt and cryptography. `PYTHON-LICENSE.txt` includes CPython's notices.
- PyInstaller's bootloader uses GPL with its distribution exception; building
  this program does not remove the original licenses. See
  https://pyinstaller.org/en/stable/license.html .
- Release assets include MeshDesk's complete source and build scripts, matching
  dependency source distributions, and Qt 5.15.2 source for the Windows runtime.
  `dependencies.json` (Windows) and `/usr/share/meshdesk/dependencies.json`
  (Linux) identify bundled inputs. The release's source manifest records source
  URLs and SHA-256 hashes. Ubuntu supplies sources for its system packages.
- Map data attribution defaults to © OpenStreetMap contributors. The selected
  tile provider's attribution remains visible on the map.

MeshDesk is an independent client, not an official Meshtastic product.
