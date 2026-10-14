#!/usr/bin/env bash
set -euo pipefail
meshdesk_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x "$meshdesk_root/.venv/bin/python" ]]; then
    echo "Run scripts/bootstrap.sh first." >&2
    exit 1
fi
export PYTHONNOUSERSITE=1
export QT_QUICK_BACKEND="${QT_QUICK_BACKEND:-software}"
export QT_QUICK_CONTROLS_STYLE=Material
exec "$meshdesk_root/.venv/bin/python" -m meshdesk.app "$@"
