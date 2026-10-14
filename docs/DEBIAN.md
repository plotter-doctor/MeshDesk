# Debian package and releases

Install the package on the tablet with:

```sh
sudo apt install ./meshdesk_0.3.0-1_all.deb
```

`apt` installs required Ubuntu packages. If they are already installed, an offline
`sudo dpkg -i meshdesk_0.3.0-1_all.deb` also works. Launch **MeshDesk** from the
application menu or run `meshdesk`. The ARM tablet automatically enables its
embedded keyboard. The package uses software rendering by default.

The `all` architecture is intentional: the package contains Python/QML/resources
only. Ubuntu supplies architecture-specific Python, Qt and cryptography. The same
package can be used on armhf, arm64 and amd64 with Python 3.10–3.14 and Qt 5.15;
installation/runtime acceptance is recorded per tested platform. Ubuntu 22.04
armhf is the tablet baseline. A desktop session is required.

The pinned SDK and its pure-Python dependencies live privately under
`/usr/share/meshdesk/python`. Launchers use `/usr/bin/python3` in isolated mode.
No pip invocation, network download, virtual environment, shell profile or source
checkout is needed during installation or startup. Qt and cryptography continue
receiving distribution security updates. Dependency metadata/licenses are retained
and `/usr/share/meshdesk/dependencies.json` records wheel hashes. Optional
documentation may be omitted by minimal Ubuntu installations; runtime files
and the dependency manifest remain installed and verified.

No radio connection is made automatically. Existing data remains at
`~/.local/share/MeshDesk/MeshDesk/`; `--data-dir` can override this. Upgrading or
removing the package does not remove user data. Quit the app before upgrading.
Serial access uses the user's existing `dialout` membership; Bluetooth additionally
requires BlueZ and a working adapter. The installer does not change user groups,
radio configuration, Bluetooth pairing or system services.

```sh
meshdesk --demo --demo-transport serial
meshdesk --demo --demo-transport ble
meshdesk-simulator --transport serial
sudo apt remove meshdesk
```

## Build locally

Use a Python build environment with `setuptools>=68`, `wheel` and `packaging`,
plus the system `dpkg-deb` command. From the repository root:

```sh
python tools/build_deb.py
# Rebuild without network access from the prepared wheelhouse:
python tools/build_deb.py --offline
```

Output: `dist/meshdesk_VERSION-REVISION_all.deb` and its SHA-256 checksum. SDK
versions come from `requirements-linux.lock`. Python 3.10 compatibility packages
are included even on a newer build host. The builder disables optional native
extensions in PyYAML and dbus-fast, rejects native libraries in every wheel, and
checks the dependency closure for each supported Python version. The package
does not include tests, development tools, caches or user data.

`SOURCE_DATE_EPOCH` controls package timestamps. The dependency manifest records
the exact input wheels; byte reproducibility requires the same wheels, app source,
build-tool versions and compression tools. Use `--revision 2` for packaging-only
updates without changing the app version. Keep previous packages for rollback;
do not downgrade an incompatible database without restoring its backup.

## GitHub Actions

`.github/workflows/packages.yml` builds on pushes to `main`, manual runs and
`vMAJOR.MINOR.PATCH` tags. It runs Linux and Windows tests, with separate 95%
statement and branch coverage gates on Linux. It builds one `.deb` and tests its
installation, three simulators, keyboard and decorated-window sizing in Ubuntu
22.04, 24.04, 25.04 and 25.10 containers. Ubuntu 25.x uses archived repositories
and no longer receives Ubuntu security support. Windows builds and runs the
portable executable independently.

A matching version tag publishes the first-party and dependency source archives,
Qt source, packages and checksums only after all required jobs pass. Main-branch
and manual runs upload artifacts without creating releases. Set the version in
`pyproject.toml` and `src/meshdesk/__init__.py`, update `docs/RELEASE.md`, push and
validate `main`, then push its matching tag (for example `v0.3.0`). Only the release
job requests `contents: write`; no custom publishing secret is needed.

The installed-package check is `tools/smoke_deb.py`. Run it under `xvfb-run -a`
after installing a candidate package. It uses a temporary data directory and
simulators; it never connects to a physical radio. ARM hardware testing remains
separate from the x86-64 Ubuntu container check.

References: [GitHub workflow triggers](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows),
[GitHub CLI releases](https://cli.github.com/manual/gh_release_create),
[PyYAML build configuration](https://github.com/yaml/pyyaml/blob/6.0.3/setup.py).
