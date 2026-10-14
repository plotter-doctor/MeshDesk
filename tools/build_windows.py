#!/usr/bin/env python3
"""Build a self-contained Windows x86-64 directory and portable ZIP."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != 'win32' or platform.architecture()[0] != '64bit':
        raise SystemExit('Build this package with 64-bit Python on Windows.')
    from meshdesk import __version__
    from PyQt5.QtCore import qVersion
    from cryptography.hazmat.backends.openssl.backend import backend
    output = ROOT / 'dist/windows'
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
            '--windowed', '--name', 'MeshDesk', '--distpath', str(output),
            '--workpath', str(ROOT/'build/windows'), '--specpath', str(ROOT/'build'),
            '--paths', str(ROOT/'src'), '--collect-data', 'meshdesk',
            '--collect-submodules', 'meshtastic', '--collect-submodules', 'pubsub',
            '--hidden-import', 'bleak.backends.winrt.client',
            '--hidden-import', 'bleak.backends.winrt.scanner',
            '--hidden-import', 'serial.tools.list_ports_windows']
    # Preserve dependency metadata and license files; SDK version lookups also
    # require this metadata inside the frozen program.
    distributions = sorted(metadata.distributions(), key=lambda d: d.metadata['Name'].lower())
    for dist in distributions:
        args += ['--copy-metadata', dist.metadata['Name']]
    args.append(str(ROOT/'packaging/windows/entrypoint.py'))
    subprocess.run(args, cwd=ROOT, check=True)
    folder = output/'MeshDesk'
    shutil.copytree(ROOT/'packaging/licenses', folder/'licenses', dirs_exist_ok=True)
    for source, target in [('LICENSE','LICENSE'), ('THIRD_PARTY.md','THIRD_PARTY.md'),
                           ('docs/WINDOWS.md','README.md')]:
        shutil.copyfile(ROOT/source, folder/target)
    license_file = Path(sys.base_prefix)/'LICENSE.txt'
    if not license_file.is_file():
        raise RuntimeError('Python license not found: '+str(license_file))
    shutil.copyfile(license_file,folder/'PYTHON-LICENSE.txt')
    manifest = {'version':__version__, 'python':platform.python_version(), 'qt':qVersion(),
                'openssl':backend.openssl_version_text(), 'platform':'windows-x86_64', 'license':'GPL-3.0-only',
                'distributions':[{'name':d.metadata['Name'],'version':d.version} for d in distributions]}
    (folder/'dependencies.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    archive = Path(shutil.make_archive(str(ROOT/'dist'/f'MeshDesk-{__version__}-windows-x86_64'),
                                      'zip',root_dir=output,base_dir='MeshDesk'))
    archive.with_suffix(archive.suffix+'.sha256').write_text(
        hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n', encoding='utf-8')
    print(archive)


if __name__ == '__main__':
    main()
