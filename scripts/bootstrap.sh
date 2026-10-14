#!/usr/bin/env bash
# Installs only into this project's virtual environment.
set -euo pipefail
meshdesk_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONNOUSERSITE=1
case "$(uname -m)" in
    armv6l|armv7l|armv8l) export SKIP_CYTHON=1 ;;
esac
python3 -c 'from PyQt5 import QtCore, QtQml, QtQuick, QtWidgets, QtPrintSupport' || {
    echo "Install the Qt prerequisites listed in README.md, then retry." >&2
    exit 1
}
python3 -m venv --system-site-packages "$meshdesk_root/.venv"
"$meshdesk_root/.venv/bin/python" -m pip install --only-binary=protobuf --find-links "$meshdesk_root/dist" -c "$meshdesk_root/requirements-linux.lock" -e "$meshdesk_root"
"$meshdesk_root/.venv/bin/python" "$meshdesk_root/tools/audit_compatibility.py"
echo "Ready. Run $meshdesk_root/run.sh --demo"
