"""Packaging must reject host binaries and missing older-Python dependencies."""
import importlib.util
from pathlib import Path
import zipfile
import pytest

spec = importlib.util.spec_from_file_location('build_deb', Path(__file__).parents[1]/'tools/build_deb.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.mark.parametrize('name,data', [
    ('package/native.so', b'native'),
    ('package/disguised', b'\x7fELFbinary'),
    ('../escape.py', b'pass'),
    ('anything.pth', b'import untrusted'),
    ('pkg.data/scripts/command', b'executable'),
])
def test_reject_nonportable_or_unsafe_wheels(tmp_path, name, data):
    wheel = tmp_path/'fixture.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr(name, data)
    with pytest.raises(ValueError):
        list(builder.pure_members(wheel))


def test_dependency_check_includes_python310_on_newer_build_hosts(tmp_path):
    metadata = tmp_path/'example-1.0.dist-info'
    metadata.mkdir()
    (metadata/'METADATA').write_text('Name: example\nVersion: 1.0\nRequires-Dist: async-timeout>=5; python_version < "3.11"\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Python 3.10.*async-timeout'):
        builder.validate_dependencies(tmp_path)
    compatibility = tmp_path/'async_timeout-5.0.1.dist-info'
    compatibility.mkdir()
    (compatibility/'METADATA').write_text('Name: async-timeout\nVersion: 5.0.1\n', encoding='utf-8')
    builder.validate_dependencies(tmp_path)
