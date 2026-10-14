#!/usr/bin/env python3
"""Build an offline-installable, architecture-independent Debian package.

Only pure-Python wheels are bundled; native Qt/cryptography come from apt.
Run with --offline to rebuild from an already prepared wheelhouse.
"""
import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import zipfile

from packaging.requirements import Requirement
from packaging.markers import default_environment
from packaging.utils import canonicalize_name, parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]


def version():
    tree = ast.parse((ROOT / 'src/meshdesk/__init__.py').read_text(encoding='utf-8'))
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets))


def requirements():
    # Include Python 3.10-only dependencies even when building on Python 3.12.
    return [Requirement(line.split(';')[0].strip()) for line in
            (ROOT / 'requirements-linux.lock').read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.startswith('#')]


def run(*args, **kwargs):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True, **kwargs)


def pure_members(wheel):
    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError(f'Unsafe wheel path: {info.filename}')
            if info.is_dir():
                continue
            data = archive.read(info)
            if path.suffix.lower() in ('.so', '.pyd', '.dll', '.dylib') or data.startswith(b'\x7fELF'):
                raise ValueError(f'Native code cannot enter Architecture: all: {wheel}: {path}')
            if any(part.endswith('.data') for part in path.parts):
                raise ValueError(f'Wheel needs unsupported data relocation: {wheel}: {path}')
            if path.suffix in ('.pyc', '.pth') or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f'Unexpected executable path or symlink: {wheel}: {path}')
            yield path, data


def prepare(wheelhouse):
    wheelhouse.mkdir(parents=True, exist_ok=True)
    reqs = requirements()
    pure = [str(r) for r in reqs if canonicalize_name(r.name) not in ('dbus-fast', 'pyyaml')]
    pip = [sys.executable, '-m', 'pip']
    env = dict(os.environ, PYTHONNOUSERSITE='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
    run(*pip, 'download', '--no-deps', '--only-binary=:all:', '--platform', 'any',
        '--implementation', 'py', '--abi', 'none', '--python-version', '3.10',
        '--dest', wheelhouse, *pure, env=env)
    for name, variables in [('dbus-fast', {'SKIP_CYTHON': '1'}),
                            ('pyyaml', {'PYYAML_FORCE_LIBYAML': '0'})]:
        req = next(r for r in reqs if canonicalize_name(r.name) == name)
        run(*pip, 'wheel', '--no-deps', '--no-cache-dir', f'--no-binary={name}',
            str(req), '-w', wheelhouse, env=dict(env, **variables))
        # dbus-fast labels even its pure build with host ABI/platform tags.
        # Normalize only after verifying every file contains no native code.
        for path in wheelhouse.glob('*.whl'):
            if canonicalize_name(parse_wheel_filename(path.name)[0]) == name:
                list(pure_members(path))
                run(sys.executable, '-m', 'wheel', 'tags', '--python-tag', 'py3',
                    '--abi-tag', 'none', '--platform-tag', 'any', '--remove', path)
    run(*pip, 'wheel', '--no-deps', '--no-build-isolation', '.', '-w', wheelhouse, env=env)


def select_wheels(wheelhouse):
    selected = []
    for requirement in requirements() + [Requirement('meshdesk==' + version())]:
        found = []
        for wheel in wheelhouse.glob('*.whl'):
            name, ver, _, tags = parse_wheel_filename(wheel.name)
            if canonicalize_name(name) == canonicalize_name(requirement.name) and ver in requirement.specifier:
                if not all(t.abi == 'none' and t.platform == 'any' for t in tags):
                    raise ValueError(f'Non-portable wheel: {wheel}')
                found.append(wheel)
        if len(found) != 1:
            raise ValueError(f'Expected one portable wheel for {requirement}, found {len(found)}')
        selected.append(found[0])
    return selected


def validate_dependencies(libraries):
    distributions = list(importlib.metadata.distributions(path=[str(libraries)]))
    versions = {canonicalize_name(d.metadata['Name']): d.version for d in distributions}
    # Minimum supported distribution dependency; all other Python requirements
    # must be in the bundle, including older-interpreter compatibility modules.
    versions['cryptography'] = '3.4.8'
    for python in ('3.10', '3.11', '3.12', '3.13', '3.14'):
        environment = dict(default_environment(), python_version=python,
                           python_full_version=python + '.0', sys_platform='linux',
                           platform_system='Linux', extra='')
        for distribution in distributions:
            for text in distribution.requires or []:
                req = Requirement(text)
                if req.marker and not req.marker.evaluate(environment):
                    continue
                found = versions.get(canonicalize_name(req.name))
                if found is None or found not in req.specifier:
                    raise ValueError(f'Python {python}: {distribution.metadata["Name"]} needs {req}; found {found}')


def build(wheelhouse, output, revision):
    if not re.fullmatch(r'[1-9][0-9]*', revision):
        raise ValueError('Debian revision must be a positive integer')
    upstream = version()
    if not re.fullmatch(r'\d+\.\d+\.\d+', upstream):
        raise ValueError('Use a stable three-part version for this release workflow')
    deb_version = upstream + '-' + revision
    stage = ROOT / 'build/debian' / ('meshdesk_' + deb_version)
    if stage.exists():
        shutil.rmtree(stage)
    libraries = stage / 'usr/share/meshdesk/python'
    libraries.mkdir(parents=True)
    manifest = []
    for wheel in select_wheels(wheelhouse):
        for path, data in pure_members(wheel):
            target = libraries / str(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise ValueError(f'Wheel file collision: {path}')
            target.write_bytes(data)
        manifest.append({'wheel': wheel.name, 'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()})
    validate_dependencies(libraries)
    for command in ('meshdesk', 'meshdesk-simulator'):
        target = stage / 'usr/bin' / command
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'packaging/debian/meshdesk', target)
        target.chmod(0o755)
    for source, destination in [
        ('packaging/debian/meshdesk.desktop', 'usr/share/applications/meshdesk.desktop'),
        ('src/meshdesk/resources/icon.svg', 'usr/share/icons/hicolor/scalable/apps/meshdesk.svg'),
        ('LICENSE', 'usr/share/doc/meshdesk/copyright'),
        ('THIRD_PARTY.md', 'usr/share/doc/meshdesk/THIRD_PARTY.md'),
        ('docs/DEBIAN.md', 'usr/share/doc/meshdesk/README.md')]:
        target = stage / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, target)
    shutil.copytree(ROOT / 'packaging/licenses', stage / 'usr/share/meshdesk/licenses')
    (stage / 'usr/share/meshdesk/dependencies.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    control = stage / 'DEBIAN'
    control.mkdir()
    size = sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())
    template = (ROOT / 'packaging/debian/control.in').read_text(encoding='utf-8')
    (control / 'control').write_text(template.replace('@VERSION@', deb_version).replace('@SIZE@', str((size + 1023) // 1024)), encoding='utf-8')
    sums = []
    for path in sorted((stage / 'usr').rglob('*')):
        if path.is_file():
            path.chmod(0o755 if path.parent == stage / 'usr/bin' else 0o644)
            sums.append(hashlib.md5(path.read_bytes()).hexdigest() + '  ' + str(path.relative_to(stage)))
    (control / 'md5sums').write_text('\n'.join(sums) + '\n', encoding='utf-8')
    # Match timestamps across rebuilds when CI supplies the commit timestamp.
    epoch = int(os.environ.get('SOURCE_DATE_EPOCH', '0'))
    for path in [*stage.rglob('*'), stage]:
        if path.is_dir():
            path.chmod(0o755)
        os.utime(path, (epoch, epoch))
    output.mkdir(parents=True, exist_ok=True)
    deb = output / f'meshdesk_{deb_version}_all.deb'
    run('dpkg-deb', '--root-owner-group', '-Zxz', '-z6', '--build', stage, deb,
        env=dict(os.environ, SOURCE_DATE_EPOCH=str(epoch)))
    (output / (deb.name + '.sha256')).write_text(hashlib.sha256(deb.read_bytes()).hexdigest() + '  ' + deb.name + '\n', encoding='utf-8')
    print(deb)
    return deb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--wheelhouse', type=Path, default=ROOT / 'build/deb-wheels')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--revision', default='1')
    args = parser.parse_args()
    if not args.offline:
        prepare(args.wheelhouse.resolve())
    build(args.wheelhouse.resolve(), args.output.resolve(), args.revision)


if __name__ == '__main__':
    main()
