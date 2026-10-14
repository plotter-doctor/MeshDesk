import os,sys,time,threading,tempfile,json,gc,faulthandler
faulthandler.enable()
os.environ['QT_QUICK_BACKEND']='software';os.environ['QT_QUICK_CONTROLS_STYLE']='Material'
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from PyQt5.QtCore import QUrl,QByteArray,QBuffer,QIODevice
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication
from PyQt5.QtQml import QQmlApplicationEngine,qmlRegisterType
from PyQt5.QtTest import QTest
from meshdesk.controller import Controller
from meshdesk.store import Store
from meshdesk.mapview import MeshMap,QRProvider
app=QApplication([])
image=QImage(256,256,QImage.Format_RGB32);image.fill(0xff123456)
raw=QByteArray();buf=QBuffer(raw);buf.open(QIODevice.WriteOnly);image.save(buf,'PNG');buf.close()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        time.sleep(.15)
        self.send_response(200);self.send_header('Content-Type','image/png');self.end_headers()
        try:self.wfile.write(bytes(raw))
        except (BrokenPipeError,ConnectionResetError):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory() as directory:
    c=Controller(Store(Path(directory)/'data.sqlite'),demo=True)
    c.store.put('online_maps',True);c.store.put('tile_url',f'http://127.0.0.1:{server.server_port}/{{z}}/{{x}}/{{y}}.png');c._publish()
    engine=QQmlApplicationEngine();qmlRegisterType(MeshMap,'MeshDesk',1,0,'MeshMap')
    engine.rootContext().setContextProperty('bridge',c);engine.addImageProvider('qr',QRProvider(c))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[2]/'src/meshdesk/qml/Main.qml')))
    root=engine.rootObjects()[0];QTest.qWait(500)
    for i in range(10):
        root.setProperty('page','Map');QTest.qWait(70);root.grabWindow();gc.collect();QTest.qWait(300)
        root.setProperty('page','Chat');gc.collect();QTest.qWait(160)
        print('cycle',i,flush=True)
    root.close();del engine;c.close()
server.shutdown();server.server_close()
