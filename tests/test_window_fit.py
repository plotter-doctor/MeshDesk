"""Exercise real window-manager decorations and panel reservations, not just QML pixels."""
from pathlib import Path
import shutil
import subprocess
import sys
import pytest


@pytest.mark.skipif(sys.platform != 'linux' or not all(shutil.which(tool) for tool in ('openbox','Xvfb','xwininfo','xprop')),
                    reason='Needs Xvfb, Openbox and x11-utils for decorated-window acceptance')
@pytest.mark.parametrize('size', ['1024x600', '600x1024', '1280x1024'])
def test_window_fits_decorated_desktop(size, tmp_path):
    # Run in a separate X display: never rearrange the user's desktop.
    result = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 '+size+'x24',
        sys.executable, str(Path(__file__).parents[1]/'tools/check_window_fit.py'),
        '--source', '--start-wm', '--output', str(tmp_path/size)],
        capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
