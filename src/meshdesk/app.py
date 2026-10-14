import argparse
import os
import sys
import time
import json
from pathlib import Path


def main():
    import faulthandler
    faulthandler.enable()
    started=time.monotonic()
    parser=argparse.ArgumentParser(description='MeshDesk native Meshtastic client')
    parser.add_argument('--demo',action='store_true',help='Connect to a local protocol simulator; never transmits over radio')
    parser.add_argument('--demo-transport',choices=['tcp','serial','ble'],default='tcp',help='Transport used with --demo; BLE uses an in-process GATT peripheral')
    parser.add_argument('--data-dir',type=Path,help='Override the local data directory')
    parser.add_argument('--renderer',choices=['software','opengl'],default='software')
    parser.add_argument('--screenshot',type=Path,help='Capture the window after initialization, then exit')
    parser.add_argument('--quit-after',type=int,help='Exit after this many seconds (smoke testing)')
    parser.add_argument('--ready-file',type=Path,help='Write readiness timing for resource measurements')
    parser.add_argument('--keyboard',choices=['auto','on','off'],default='auto',help='Embedded touch keyboard (requires Qt Virtual Keyboard)')
    args=parser.parse_args()
    os.environ.setdefault('QT_QUICK_BACKEND',args.renderer)
    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE','Material')
    from PyQt5.QtCore import QCoreApplication,QUrl,QStandardPaths,QTimer,Qt,QLibraryInfo
    import platform
    keyboard=(Path(QLibraryInfo.location(QLibraryInfo.Qml2ImportsPath))/'QtQuick/VirtualKeyboard/qmldir').is_file()
    if args.keyboard=='on' or (args.keyboard=='auto' and keyboard and platform.machine().lower().startswith(('arm','aarch'))):
        os.environ['QT_IM_MODULE']='qtvirtualkeyboard'
        os.environ['QT_VIRTUALKEYBOARD_DESKTOP_DISABLE']='1'
    elif args.keyboard=='off':os.environ.pop('QT_IM_MODULE',None)
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtQml import QQmlApplicationEngine,qmlRegisterType
    from .store import Store
    from .controller import Controller
    from .mapview import MeshMap,QRProvider
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app=QApplication(sys.argv[:1])
    app.setOrganizationName('MeshDesk');app.setApplicationName('MeshDesk')
    directory=args.data_dir or Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(directory,0o700)
    store=Store(directory/'meshdesk.sqlite3')
    controller=Controller(store,demo=args.demo,demo_transport=args.demo_transport)
    qmlRegisterType(MeshMap,'MeshDesk',1,0,'MeshMap')
    engine=QQmlApplicationEngine()
    engine.rootContext().setContextProperty('bridge',controller)
    engine.addImageProvider('qr',QRProvider(controller))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent/'qml'/'Main.qml')))
    if not engine.rootObjects():
        controller.close();return 1
    if args.ready_file:
        ready=QTimer()
        def record_ready():
            if not args.demo or json.loads(controller.stateJson).get('connected'):
                args.ready_file.write_text(json.dumps({'ready_seconds':time.monotonic()-started,'monotonic':time.monotonic()}), encoding='utf-8')
                ready.stop()
        ready.timeout.connect(record_ready);ready.start(100)
    if args.screenshot:
        def capture():
            args.screenshot.parent.mkdir(parents=True,exist_ok=True)
            engine.rootObjects()[0].grabWindow().save(str(args.screenshot))
            app.quit()
        QTimer.singleShot(2500,capture)
    if args.quit_after:QTimer.singleShot(args.quit_after*1000,app.quit)
    code=app.exec_()
    # Destroy QML bindings while their context objects are still alive.
    del engine
    controller.close()
    return code


if __name__=='__main__':
    sys.exit(main())
