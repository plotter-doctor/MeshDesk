#!/usr/bin/env python3
"""Check window frames, desktop work area and bottom controls with a real WM.

Use --source for the checkout, otherwise the installed Debian package.
--start-wm is for an isolated Xvfb display only, and reserves a 32px desktop panel.
"""
import argparse
import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='store_true')
    parser.add_argument('--start-wm', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src') if args.source else '/usr/share/meshdesk/python')
    os.environ.setdefault('QT_QUICK_BACKEND', 'software')
    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Material')
    from PyQt5.QtCore import QObject, QPointF, QRect, Qt, QUrl, qInstallMessageHandler
    from PyQt5.QtQml import QQmlApplicationEngine, qmlRegisterType
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QWindow
    import meshdesk
    from meshdesk.controller import Controller
    from meshdesk.mapview import MeshMap, QRProvider
    from meshdesk.store import Store
    app = QApplication([])
    args.output.mkdir(parents=True, exist_ok=True)
    wm = None
    panel = None
    errors = []
    reports = []
    previous = qInstallMessageHandler(lambda _, context, text: errors.append(text))

    def wait(condition):
        deadline = time.monotonic()+15
        while time.monotonic()<deadline:
            app.processEvents()
            if condition():
                return
            QTest.qWait(20)
        raise AssertionError('Window did not settle: '+repr(errors))

    def native_geometry(window):
        # Qt 5.15 can retain a stale (-1,-1) frame origin after Openbox changes
        # its border widths on maximize. Query the server's actual coordinates
        # and published decorations, rather than relaxing the clipping check.
        window_id = hex(int(window.winId()))
        info = subprocess.check_output(['xwininfo','-id',window_id],text=True)
        def number(label):
            return int(re.search(r'^\s*'+label+r':\s*(-?\d+)',info,re.MULTILINE).group(1))
        client = QRect(number('Absolute upper-left X'),number('Absolute upper-left Y'),
                       number('Width'),number('Height'))
        extents = subprocess.check_output(['xprop','-id',window_id,'_NET_FRAME_EXTENTS'],text=True)
        left,right,top,bottom = map(int,extents.split('=',1)[1].strip().split(','))
        return client.adjusted(-left,-top,right,bottom),client,min(left,right,bottom)

    def fits(window, available):
        frame,client,border = native_geometry(window)
        # Openbox may restore at (-1,-1), hiding its one-pixel cosmetic border.
        # Permit only the WM's border thickness; all client pixels must fit.
        return available.contains(client) and available.adjusted(-border,-border,border,border).contains(frame)

    try:
        if args.start_wm:
            wm = subprocess.Popen(['openbox'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # A real dock reservation makes this fail if code uses screen size
            # instead of available desktop area. No Python-Xlib dependency.
            panel = QWindow()
            panel.setFlags(Qt.Tool | Qt.FramelessWindowHint)
            area = app.primaryScreen().geometry()
            panel.setGeometry(area.x(), area.bottom()-31, area.width(), 32)
            panel.create()
            x = ctypes.CDLL(ctypes.util.find_library('X11'))
            x.XOpenDisplay.restype = ctypes.c_void_p
            x.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x.XInternAtom.restype = ctypes.c_ulong
            x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            x.XChangeProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
            x.XCloseDisplay.argtypes = [ctypes.c_void_p]
            display = x.XOpenDisplay(None)
            assert display
            def prop(name, kind, values):
                data = (ctypes.c_ulong*len(values))(*values)
                x.XChangeProperty(display, int(panel.winId()), x.XInternAtom(display,name.encode(),False),
                    x.XInternAtom(display,kind.encode(),False),32,0,data,len(values))
            prop('_NET_WM_WINDOW_TYPE','ATOM',[x.XInternAtom(display,b'_NET_WM_WINDOW_TYPE_DOCK',False)])
            prop('_NET_WM_STRUT_PARTIAL','CARDINAL',[0,0,0,32,0,0,0,0,0,0,area.x(),area.right()])
            prop('_NET_WM_STRUT','CARDINAL',[0,0,0,32])
            x.XCloseDisplay(display)
            panel.show()
            wait(lambda: app.primaryScreen().availableGeometry().height()==area.height()-32)
        with tempfile.TemporaryDirectory(prefix='meshdesk-window-') as data:
            controller = Controller(Store(Path(data)/'state.sqlite'))
            engine = QQmlApplicationEngine()
            qmlRegisterType(MeshMap,'MeshDesk',1,0,'MeshMap')
            engine.rootContext().setContextProperty('bridge',controller)
            engine.addImageProvider('qr',QRProvider(controller))
            try:
                engine.load(QUrl.fromLocalFile(str(Path(meshdesk.__file__).parent/'qml/Main.qml')))
                assert engine.rootObjects(), errors
                root = engine.rootObjects()[0]
                wait(lambda: root.isExposed() and root.frameMargins().top()>0)
                available = root.screen().availableGeometry()
                small = available.width()<1056 or available.height()<664
                wait(lambda: root.visibility()==(QWindow.Maximized if small else QWindow.Windowed))

                def capture(name):
                    # Allow WM configure/layout events to finish; assert both the
                    # full decorated frame and the actual footer are on-screen.
                    try:
                        wait(lambda: fits(root,available))
                    except AssertionError:
                        root.screen().grabWindow(0).save(str(args.output/(name+'-failed.png')))
                        print('Window geometry failure:',name,root.frameGeometry(),'expected work area:',
                              available,'current work area:',root.screen().availableGeometry(),flush=True)
                        subprocess.run(['xprop','-id',hex(int(root.winId())),'_NET_FRAME_EXTENTS','_NET_WM_STATE'])
                        subprocess.run(['xwininfo','-id',hex(int(root.winId()))])
                        raise
                    QTest.qWait(100)
                    frame,client,border = native_geometry(root)
                    assert fits(root,available), (frame,available)
                    root.grabWindow()
                    exit_button = root.findChild(QObject,'exitButton')
                    assert exit_button.isVisible() and exit_button.height()>=44
                    for point in (QPointF(),QPointF(exit_button.width(),exit_button.height())):
                        assert available.contains(client.topLeft()+exit_button.mapToScene(point).toPoint())
                    if root.property('page')=='Chat':
                        for name_ in ('composer','sendMessage','byteCounter'):
                            control = root.findChild(QObject,name_)
                            assert control.isVisible()
                            bottom = control.mapToScene(QPointF(control.width(),control.height()))
                            assert 0<=bottom.y()<=root.height(), (name_,bottom.y(),root.height())
                            assert available.contains(client.topLeft()+bottom.toPoint())
                    reports.append({'state':name,'frame':[frame.x(),frame.y(),frame.width(),frame.height()],
                        'client':[client.x(),client.y(),client.width(),client.height()],'border_tolerance_px':border,
                        'work_area':[available.x(),available.y(),available.width(),available.height()]})
                    assert root.screen().grabWindow(0).save(str(args.output/(name+'.png')))

                capture('startup')
                root.showNormal()
                wait(lambda: root.visibility()==QWindow.Windowed)
                capture('restored')
                root.showMaximized()
                wait(lambda: root.visibility()==QWindow.Maximized)
                for page in ('Chat','Nodes','Map','Settings','Connections','Activity','Preferences'):
                    root.setProperty('page',page)
                    QTest.qWait(100)
                    capture('maximized-'+page)
                assert not [e for e in errors if any(t in e for t in ('Error','Binding loop','Cannot','is not defined','Conflicting properties'))], errors
            finally:
                for root in engine.rootObjects():
                    root.close()
                del engine
                controller.close()
        (args.output/'geometry.json').write_text(json.dumps(reports,indent=2)+'\n')
        print(json.dumps(reports))
    finally:
        qInstallMessageHandler(previous)
        if panel:
            panel.close()
        if wm:
            wm.terminate()
            wm.wait(timeout=5)


if __name__=='__main__':
    main()
