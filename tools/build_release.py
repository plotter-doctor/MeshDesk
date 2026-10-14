#!/usr/bin/env python3
"""Build the client, portable D-Bus wheel and a source-plus-wheels release kit."""
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    env=dict(os.environ,PYTHONNOUSERSITE='1')
    subprocess.run([sys.executable,'-m','pip','wheel','--no-deps','--no-build-isolation','.', '-w','dist'],cwd=ROOT,env=env,check=True)
    subprocess.run([sys.executable,'-m','pip','wheel','--no-deps','--no-binary=dbus-fast','dbus-fast==5.0.26','-w','dist'],cwd=ROOT,env=dict(env,SKIP_CYTHON='1'),check=True)
    for path in (ROOT/'dist').glob('dbus_fast-5.0.26-*.whl'):
        if path.name.endswith('py3-none-any.whl'):continue
        with zipfile.ZipFile(path) as wheel:
            if any(n.endswith(('.so','.pyd','.dll','.dylib')) for n in wheel.namelist()):
                raise RuntimeError('Refusing to mark compiled code as portable: '+str(path))
        # Upstream marks pure builds with the build-host tag; normalize only
        # after checking that the wheel contains no native extensions.
        subprocess.run([sys.executable, '-m', 'wheel', 'tags', '--python-tag', 'py3',
                        '--abi-tag', 'none', '--platform-tag', 'any', '--remove', str(path)], check=True)
    package_kit()


def package_kit():
    sys.path.insert(0,str(ROOT/'src'))
    from meshdesk import __version__
    archive=ROOT/'dist'/f'meshdesk-{__version__}-kit.tar.gz'
    # Only publish version-controlled files; local hardware reports and user
    # data must never enter a source kit merely because they exist in the tree.
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    with tarfile.open(archive,'w:gz') as tar:
        for name in sorted(filter(None, tracked)):
            path = ROOT / name
            if path.is_file():
                tar.add(path,arcname='meshdesk/'+name,recursive=False)
        for path in [ROOT/'dist'/f'meshdesk-{__version__}-py3-none-any.whl', ROOT/'dist'/'dbus_fast-5.0.26-py3-none-any.whl']:
            tar.add(path,arcname='meshdesk/dist/'+path.name)
    print(archive)


if __name__=='__main__':main()
