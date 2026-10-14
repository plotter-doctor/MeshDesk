"""Windowed executable entry point; retain diagnostics when no console exists."""
import multiprocessing
import os
from pathlib import Path
import sys

if __name__ == '__main__':
    multiprocessing.freeze_support()
    if sys.stderr is None or sys.stdout is None:
        directory = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'MeshDesk' / 'logs'
        directory.mkdir(parents=True, exist_ok=True)
        stream = (directory / 'startup.log').open('a', encoding='utf-8', buffering=1)
        if sys.stderr is None:
            sys.stderr = stream
        if sys.stdout is None:
            sys.stdout = stream
    from meshdesk.app import main
    raise SystemExit(main())
