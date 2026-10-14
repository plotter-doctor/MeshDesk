#!/usr/bin/env python3
"""Collect exact dependency sources alongside the tagged application's source."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def download(url, target, expected=None):
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=120) as response, target.open('wb') as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
    result = digest.hexdigest()
    if expected and result != expected:
        target.unlink()
        raise RuntimeError('Source checksum mismatch: ' + url)
    return {'file': target.name, 'url': url, 'sha256': result}


def checksum(path):
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    path.with_name(path.name + '.sha256').write_text(digest + '  ' + path.name + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--debian', type=Path, required=True)
    parser.add_argument('--windows', type=Path, required=True)
    args = parser.parse_args()
    windows = json.loads(args.windows.read_text(encoding='utf-8'))
    version = windows['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid application version')
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    sources = ROOT / 'build/corresponding-source'
    if sources.exists():
        shutil.rmtree(sources)
    sources.mkdir(parents=True)
    required = {(d['name'].lower().replace('_', '-'), d['version']) for d in windows['distributions']}
    for entry in json.loads(args.debian.read_text(encoding='utf-8')):
        name, release, *_ = entry['wheel'].split('-')
        required.add((name.lower().replace('_', '-'), release))
    manifest = []
    for name, release in sorted(required):
        if name in ('meshdesk', 'pyqt5-qt5'):
            continue
        url = f'https://pypi.org/pypi/{name}/{release}/json'
        with urllib.request.urlopen(url, timeout=60) as response:
            metadata = json.load(response)
        candidates = [item for item in metadata['urls'] if item['packagetype'] == 'sdist']
        if not candidates:
            raise RuntimeError(f'No corresponding source available for {name} {release}')
        item = sorted(candidates, key=lambda item: item['filename'])[0]
        record = download(item['url'], sources / item['filename'], item['digests']['sha256'])
        record.update(name=name, version=release)
        manifest.append(record)
        print(name, release, flush=True)
    python_version = windows['python']
    if not re.fullmatch(r'3\.12\.\d+', python_version):
        raise ValueError('Review source packaging for this Python version')
    manifest.append(download(f'https://www.python.org/ftp/python/{python_version}/Python-{python_version}.tar.xz',
                             sources / f'Python-{python_version}.tar.xz'))
    manifest.append(download('https://codeload.github.com/openssl/openssl/tar.gz/refs/tags/OpenSSL_1_1_1b',
                             sources / 'openssl-1.1.1b-source.tar.gz'))
    # PyQt5-Qt5 is a binary-only PyPI package. Bundle the matching complete Qt
    # source separately so its size does not obscure the small application kit.
    qt = next(release for name, release in required if name == 'pyqt5-qt5')
    if qt != '5.15.2':
        raise ValueError('Review matching Qt source before updating the Windows runtime')
    qt_name = f'qt-everywhere-src-{qt}.tar.xz'
    manifest.append(download(f'https://download.qt.io/archive/qt/5.15/{qt}/single/{qt_name}', output / qt_name))
    for file in [args.debian, args.windows]:
        shutil.copyfile(file, sources / file.name)
    manifest_file = output / f'meshdesk-{version}-sources.json'
    manifest_file.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    shutil.copyfile(manifest_file, sources / 'sources.json')
    archive = output / f'meshdesk-{version}-dependency-sources.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(sources, arcname='dependency-sources')
    app = output / f'meshdesk-{version}-source.tar.gz'
    subprocess.run(['git', 'archive', '--format=tar.gz', f'--prefix=meshdesk-{version}/',
                    '-o', str(app), 'HEAD'], cwd=ROOT, check=True)
    for file in (app, archive, output / qt_name, manifest_file):
        checksum(file)


if __name__ == '__main__':
    main()
