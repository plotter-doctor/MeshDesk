#!/usr/bin/env bash
# Register this checkout in the current Linux user's application menu.
set -euo pipefail
meshdesk_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
meshdesk_apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$meshdesk_apps"
python3 - "$meshdesk_root" "$meshdesk_apps/meshdesk.desktop" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
def quoted(value):
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')+'"'
Path(sys.argv[2]).write_text('[Desktop Entry]\nType=Application\nName=MeshDesk\nComment=Meshtastic messages, nodes and radio settings\nExec='+quoted(root/'run.sh')+'\nIcon='+str(root/'src/meshdesk/resources/icon.svg')+'\nTerminal=false\nCategories=Network;HamRadio;\nStartupWMClass=MeshDesk\n')
print('Installed '+sys.argv[2])
PY
