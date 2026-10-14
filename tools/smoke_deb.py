#!/usr/bin/env python3
"""Verify the installed Debian runtime, using synthetic radios and temporary data."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import fnmatch

LIBRARIES = Path('/usr/share/meshdesk/python')


def verify_package():
    # Minimal Ubuntu installations deliberately exclude documentation. Only
    # accept missing optional docs when an actual dpkg exclusion covers them.
    rules = []
    for config in [Path('/etc/dpkg/dpkg.cfg'), *sorted(Path('/etc/dpkg/dpkg.cfg.d').glob('*'))]:
        if config.is_file():
            for line in config.read_text(encoding='utf-8').splitlines():
                if line.startswith(('path-exclude=', 'path-include=')):
                    key, pattern = line.split('=', 1)
                    rules.append((key, pattern))
    omitted = []
    for line in subprocess.check_output(['dpkg', '--verify', 'meshdesk'], text=True).splitlines():
        parts = line.split(maxsplit=1)
        path = parts[-1]
        excluded = False
        for key, pattern in rules:
            if fnmatch.fnmatchcase(path, pattern):
                excluded = key == 'path-exclude'
        if len(parts) == 2 and parts[0] == 'missing' and path.startswith('/usr/share/doc/meshdesk/') and excluded:
            omitted.append(path)
        else:
            raise AssertionError('Installed package integrity failure: ' + line)
    assert (LIBRARIES.parent / 'dependencies.json').is_file()
    return omitted


def keyboard_probe(output):
    sys.path.insert(0, str(LIBRARIES))
    from PyQt5.QtCore import QObject, QPointF, Qt, QUrl, qInstallMessageHandler
    from PyQt5.QtQml import QQmlApplicationEngine, qmlRegisterType
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication
    import meshdesk
    from meshdesk.controller import Controller
    from meshdesk.mapview import MeshMap, QRProvider
    from meshdesk.store import Store

    app = QApplication([])
    errors = []
    previous = qInstallMessageHandler(lambda _, context, text: errors.append(text))
    with tempfile.TemporaryDirectory(prefix='meshdesk-keyboard-') as data:
        controller = Controller(Store(Path(data) / 'data.sqlite'), demo=True)
        engine = QQmlApplicationEngine()
        qmlRegisterType(MeshMap, 'MeshDesk', 1, 0, 'MeshMap')
        engine.rootContext().setContextProperty('bridge', controller)
        engine.addImageProvider('qr', QRProvider(controller))

        def wait(condition):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                app.processEvents()
                if condition():
                    return
                QTest.qWait(10)
            raise AssertionError('Timed out waiting for keyboard UI: ' + '\n'.join(errors))

        try:
            engine.load(QUrl.fromLocalFile(str(Path(meshdesk.__file__).parent / 'qml/Main.qml')))
            assert engine.rootObjects(), errors
            root = engine.rootObjects()[0]
            wait(lambda: json.loads(controller.stateJson).get('connected'))
            root.requestActivate()
            wait(root.isActive)
            composer = root.findChild(QObject, 'composer')
            composer.forceActiveFocus()
            app.inputMethod().show()
            panel = root.findChild(QObject, 'touchKeyboard')
            wait(lambda: panel is not None and panel.property('active') and panel.height() > 100)
            QTest.qWait(500)
            assert composer.mapToScene(QPointF(0, composer.height())).y() <= panel.mapToScene(QPointF()).y() + 1
            assert not root.findChild(QObject, 'emptyChatHint').isVisible()
            exit_button = root.findChild(QObject, 'exitButton')
            assert exit_button.isVisible() and exit_button.height() >= 44
            assert exit_button.mapToScene(QPointF(0, exit_button.height())).y() <= panel.mapToScene(QPointF()).y()

            def items(item):
                yield item
                for child in item.childItems():
                    yield from items(child)

            keys = [item for item in items(panel) if item.isVisible() and item.property('key') == Qt.Key_Q and item.width() > 0]
            assert len(keys) == 1
            key = keys[0]
            QTest.mouseClick(root, Qt.LeftButton, pos=key.mapToScene(QPointF(key.width()/2, key.height()/2)).toPoint(), delay=50)
            wait(lambda: composer.property('text').lower() == 'q')
            assert root.grabWindow().save(str(output / 'keyboard.png'))
            assert root.screen().grabWindow(0).save(str(output / 'keyboard-desktop.png'))
            app.inputMethod().hide()
            wait(lambda: not panel.property('active'))
            assert root.findChild(QObject, 'emptyChatHint').isVisible()
            QTest.mouseClick(root, Qt.LeftButton,
                pos=exit_button.mapToScene(QPointF(exit_button.width()/2, exit_button.height()/2)).toPoint())
            wait(lambda: not root.isVisible())
            assert not [e for e in errors if any(word in e for word in ('Error', 'Cannot', 'Binding loop', 'not installed'))], errors
        finally:
            for root in engine.rootObjects():
                root.close()
            del engine
            controller.close()
            qInstallMessageHandler(previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/package'))
    parser.add_argument('--keyboard-probe', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.keyboard_probe:
        keyboard_probe(output)
        return
    report = {'package': subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', 'meshdesk'], text=True),
              'architecture': subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip(),
              'transports': {}, 'keyboard': False}
    # -I ignores PYTHONPATH and user-site packages. Every SDK module must resolve
    # from the package; Qt/cryptography must resolve from the distribution.
    probe = '''import sys,json,importlib
from pathlib import Path
root=Path('/usr/share/meshdesk/python')
sys.path.insert(0,str(root))
names=['meshdesk','meshtastic','bleak','dbus_fast','google.protobuf','yaml','requests','serial','async_timeout','typing_extensions']
origins={name:str(Path(importlib.import_module(name).__file__).resolve()) for name in names}
assert all(Path(p).is_relative_to(root) for p in origins.values()),origins
from PyQt5 import QtCore,QtQuick,QtQml,QtWidgets,QtPrintSupport
import cryptography
assert str(cryptography.__file__).startswith('/usr/lib/python3/dist-packages/')
print(json.dumps({'python':sys.version.split()[0],'qt':QtCore.QT_VERSION_STR,'libraries':origins}))
'''
    report['runtime'] = json.loads(subprocess.check_output(['/usr/bin/python3', '-I', '-c', probe], text=True))
    env = dict(os.environ, QT_QUICK_BACKEND='software', QT_QUICK_CONTROLS_STYLE='Material')
    env.pop('QT_IM_MODULE', None)
    for transport in ('tcp', 'serial', 'ble'):
        with tempfile.TemporaryDirectory(prefix='meshdesk-deb-') as data:
            ready = Path(data) / 'ready.json'
            screenshot = output / (transport + '.png')
            result = subprocess.run(['/usr/bin/meshdesk', '--demo', '--demo-transport', transport,
                '--data-dir', data, '--keyboard', 'off', '--ready-file', str(ready),
                '--screenshot', str(screenshot), '--quit-after', '15'], env=env,
                capture_output=True, text=True, timeout=60)
            (output / (transport + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
            assert result.returncode == 0, result.stderr
            assert ready.exists(), f'{transport}: simulator did not connect before screenshot'
            assert screenshot.stat().st_size > 10000
            assert not any(word in result.stderr for word in ('Error:', 'Binding loop', 'Cannot load', 'is not defined')), result.stderr
            report['transports'][transport] = json.loads(ready.read_text(encoding='utf-8'))
    keyboard_env = dict(env, QT_IM_MODULE='qtvirtualkeyboard', QT_VIRTUALKEYBOARD_DESKTOP_DISABLE='1')
    result = subprocess.run(['/usr/bin/python3', '-I', str(Path(__file__).resolve()), '--keyboard-probe',
        '--output', str(output)], env=keyboard_env, capture_output=True, text=True, timeout=60)
    (output / 'keyboard.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
    report['keyboard'] = True
    report['documentation_omitted_by_dpkg'] = verify_package()
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
