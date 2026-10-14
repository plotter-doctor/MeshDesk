import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from PyQt5.QtCore import QBuffer,QByteArray,QIODevice
from PyQt5.QtGui import QImage,QPainter,QColor
from meshdesk.mapview import MeshMap,project,unproject
from conftest import wait_for


def test_rotation_and_projection(qtapp):
    item=MeshMap();item.setWidth(1024);item.setHeight(600)
    item.setView(73,42)
    for x,y in [(100,200),(800,500),(512,300)]:
        px,py=item.transform_point(x,y)
        actual=item.transform_point(px,py,True)
        assert abs(actual[0]-x)<1e-7 and abs(actual[1]-y)<1e-7
    lat,lon=unproject(*project(52.2,21,12),12)
    assert abs(lat-52.2)<1e-6 and abs(lon-21)<1e-6


def test_tile_download_then_offline_cache(qtapp,tmp_path):
    image=QImage(256,256,QImage.Format_RGB32);image.fill(QColor('#173846'))
    raw=QByteArray();buf=QBuffer(raw);buf.open(QIODevice.WriteOnly);image.save(buf,'PNG');buf.close()
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('Cache-Control','max-age=3600');self.end_headers();self.wfile.write(bytes(raw))
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    item=MeshMap();item.cache.setCacheDirectory(str(tmp_path/'tiles'))
    item.tileUrl=f'http://127.0.0.1:{server.server_port}/{{z}}/{{x}}/{{y}}.png';item.online=True
    try:
        assert item._tile(2,1,1) is None
        wait_for(qtapp,lambda:bool(item._images))
        assert len(requests)==1
        item.online=False;item._images.clear()
        cached=item._tile(2,1,1)
        assert cached and cached.pixelColor(10,10)==QColor('#173846')
        assert len(requests)==1
    finally:server.shutdown();server.server_close()


def test_same_position_nodes_expand_and_heat_is_interactive(qtapp,tmp_path):
    item=MeshMap();item.setWidth(600);item.setHeight(400);item.center(52,21)
    item.cache.setCacheDirectory(str(tmp_path/'tiles'))
    item.nodes=[{'num':i,'name':str(i),'snr':5,'position':{'latitude':52,'longitude':21}} for i in range(1,5)]
    def render():
        image=QImage(600,400,QImage.Format_ARGB32);image.fill(0)
        painter=QPainter(image);item.paint(painter);painter.end()
        return image
    render()
    assert len(item._clusters)==1 and not item._markers
    x,y,key=item._clusters[0];item.click(x,y);render()
    assert len(item._markers)==4 and not item._clusters
    seen=[];item.nodeClicked.connect(seen.append)
    for x,y,num in item._markers:item.click(x,y)
    assert seen==['1','2','3','4']
    item.layers=['snr'];render()
    assert item.infoAt(300,200).endswith('5 dB')
    assert item._heat_image and not item._heat_image.isNull()
    assert item._heat_image.pixelColor(100,66).alpha()>0


def test_qml_double_ids_are_safe_in_hover_clicks_and_neighbor_links(qtapp,tmp_path):
    item=MeshMap();item.setWidth(600);item.setHeight(400);item.center(52,21)
    item.cache.setCacheDirectory(str(tmp_path/'tiles'))
    item.nodes=[{'num':2410106456.0,'snr':2.5,'position':{'latitude':52,'longitude':21}},
                {'num':1226017548.0,'hopsAway':0.0,'snr':5.5,'position':{'latitude':52.001,'longitude':21.001}}]
    item.myNode='2410106456';item.layers=['nodes','direct']
    image=QImage(600,400,QImage.Format_ARGB32);image.fill(0)
    painter=QPainter(image)
    try:item.paint(painter)
    finally:painter.end()
    assert item.infoAt(300,200).startswith('!8fa74e58')
    seen=[];item.nodeClicked.connect(seen.append);item.click(300,200)
    assert seen==['2410106456']
    assert item._links


def test_qml_map_download_callbacks_survive_garbage_collection_and_page_changes(qtapp):
    # Keep Python references out of the QML-owned map's lifetime. This reproduced
    # the user's segmentation fault in the former reply.finished closure.
    import os,subprocess,sys
    from pathlib import Path
    root=Path(__file__).parents[1]
    result=subprocess.run([sys.executable,str(root/'tests/helpers/map_lifecycle.py')],
        cwd=root,env=dict(os.environ,PYTHONPATH=str(root/'src')),text=True,capture_output=True,timeout=35)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    assert 'cycle 9' in result.stdout


def test_map_navigation_overlays_and_waypoint_hit_testing(qtapp,tmp_path):
    import time
    item=MeshMap();item.setWidth(600);item.setHeight(400)
    item.cache.setCacheDirectory(str(tmp_path/'tiles'))
    item.fit();item.center(52,21)
    item.nodes=[{'num':1,'name':'A','position':{'latitude':52,'longitude':21,'precisionBits':16},'neighborinfo':{'neighbors':[{'nodeId':2,'snr':-10}]}},
        {'num':2,'name':'B','snr':-20,'position':{'latitude':52.003,'longitude':21.008},'neighborinfo':{'neighbors':[{'nodeId':1,'snr':-20},{'nodeId':999,'snr':0}]}},
        {'num':3,'position':{'latitude':10,'longitude':10}},{'num':4}]
    item.layers=['nodes','remote','precision','waypoints']
    item.waypoints=[{'id':1,'latitude_i':520010000,'longitude_i':210020000,'icon':0x1f3e0,'name':'Home'},
        {'id':2,'latitude_i':520020000,'longitude_i':210030000,'name':'Cross'},
        {'id':3,'expire':time.time()-1}]
    assert item.waypoints and item.layers and item.myNode=='0' and not item.online
    item.attribution='Local tiles';assert item.attribution=='Local tiles'
    def render():
        image=QImage(600,400,QImage.Format_ARGB32);p=QPainter(image)
        try:item.paint(p)
        finally:p.end()
    render();assert len(item._links)==2 and len(item._waypoint_markers)==2
    seen=[];item.waypointClicked.connect(seen.append)
    for x,y,num in item._waypoint_markers:item.click(x,y)
    assert seen==['1','2']
    points,text=item._links[0];x,y=points[16]
    item._markers=[];assert item.infoAt(x,y)==text and item.infoAt(-100,-100)==''
    coordinates=[];item.coordinateClicked.connect(lambda lat,lon:coordinates.append((lat,lon)))
    item.click(10,10);assert coordinates
    item._expanded_cluster='test';item.click(10,10);assert item._expanded_cluster is None
    item.pan(10,-20);assert item._lat!=52
    item.changeZoom(100);assert item.zoom==19
    item.changeZoom(-100);assert item.zoom==1
    item.fit();assert 1<=item.zoom<=16
    item.layers=['heat'];render();old=item._heat_image;render();assert item._heat_image is old
    item.tileUrl='file:///not-allowed/{z}/{x}/{y}';item.online=True
    assert item._tile(1,1,1) is None and not item._pending
    assert item._tile(1,-1,0) is None


def test_failed_and_oversized_tiles_do_not_crash_or_grow_cache(qtapp,tmp_path):
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            requests.append(self.path)
            body=b'invalid PNG' if self.path.startswith('/invalid') else b'x'*(2*1024*1024)
            self.send_response(503 if self.path.startswith('/error') else 200)
            self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    item=MeshMap();item.cache.setCacheDirectory(str(tmp_path/'tiles'));item.online=True
    try:
        for path in ('invalid','oversized','error'):
            item.tileUrl=f'http://127.0.0.1:{server.server_port}/{path}/{{z}}/{{x}}/{{y}}'
            item._tile(1,1,1);wait_for(qtapp,lambda:not item._pending)
            assert len(item._failed)==1 and not item._images
        item.online=False
        item._failed={str(i) for i in range(513)}
        item._tile(1,0,0);assert len(item._failed)<=512
    finally:server.shutdown();server.server_close()
