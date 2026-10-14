"""Small raster map renderer: no browser, WebGL or permanent render loop."""
import math
from collections import OrderedDict
from pathlib import Path
from PyQt5.QtCore import Qt, QPointF, QRectF, QUrl, pyqtProperty, pyqtSignal, pyqtSlot, QTimer
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QRadialGradient
from PyQt5.QtGui import QPainterPath, QFont
from .mapmath import signal_color,precision_meters,fan_offsets,heat_weight,heat_radius,heat_color,segment_distance,nice_scale
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkDiskCache
from PyQt5.QtQuick import QQuickPaintedItem, QQuickImageProvider


def project(lat,lon,zoom):
    lat=max(-85.05112878,min(85.05112878,float(lat)))
    scale=256*2**zoom
    return ((float(lon)+180)/360*scale,(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*scale)


def unproject(x,y,zoom):
    scale=256*2**zoom
    return (math.degrees(math.atan(math.sinh(math.pi*(1-2*y/scale)))),(x/scale*360-180+180)%360-180)


def coordinate(node):
    p=node.get('position',{})
    lat=p.get('latitude',p.get('latitude_i',p.get('latitudeI')))
    lon=p.get('longitude',p.get('longitude_i',p.get('longitudeI')))
    if lat is None or lon is None:
        return None
    if 'latitude' not in p:lat*=1e-7
    if 'longitude' not in p:lon*=1e-7
    lat,lon=float(lat),float(lon)
    if not math.isfinite(lat) or not math.isfinite(lon) or abs(lat)>90 or abs(lon)>180 or (lat==0 and lon==0):return None
    return lat,lon


class MeshMap(QQuickPaintedItem):
    changed=pyqtSignal()
    nodeClicked=pyqtSignal(str,arguments=['num'])
    coordinateClicked=pyqtSignal(float,float,arguments=['lat','lon'])
    waypointClicked=pyqtSignal(str,arguments=['waypointId'])

    def __init__(self,parent=None):
        super().__init__(parent)
        self._nodes=[];self._waypoints=[];self._layers=['nodes','waypoints'];self._online=False
        self._template='https://tile.openstreetmap.org/{z}/{x}/{y}.png'
        self._attribution='© OpenStreetMap contributors'
        self._lat=52.2297;self._lon=21.0122;self._zoom=12
        self._images=OrderedDict();self._pending=set();self._failed=set();self._markers=[]
        self._waypoint_markers=[];self._my_node=0
        self._clusters=[];self._bearing=0;self._pitch=0
        self._expanded_cluster=None;self._links=[];self._heat_key=None;self._heat_image=None
        self.network=QNetworkAccessManager(self)
        self.cache=QNetworkDiskCache(self)
        from PyQt5.QtCore import QStandardPaths
        self.cache.setCacheDirectory(QStandardPaths.writableLocation(QStandardPaths.CacheLocation)+'/tiles')
        self.cache.setMaximumCacheSize(50*1024*1024)
        self.network.setCache(self.cache)
        self.setAntialiasing(True)

    @pyqtProperty('QVariantList',notify=changed)
    def nodes(self):return self._nodes
    @nodes.setter
    def nodes(self,value):
        # QML JSON numbers cross QVariant as doubles, including uint32 node IDs.
        self._nodes=[dict(n,num=int(n['num'])) for n in value]
        self.update()
    @pyqtProperty(str,notify=changed)
    def myNode(self):return str(self._my_node)
    @myNode.setter
    def myNode(self,value):self._my_node=int(value or 0);self.update()
    @pyqtProperty('QVariantList',notify=changed)
    def waypoints(self):return self._waypoints
    @waypoints.setter
    def waypoints(self,value):self._waypoints=value;self.update()
    @pyqtProperty('QStringList',notify=changed)
    def layers(self):return self._layers
    @layers.setter
    def layers(self,value):self._layers=list(value);self.update()
    @pyqtProperty(bool,notify=changed)
    def online(self):return self._online
    @online.setter
    def online(self,value):
        if value!=self._online:self._failed.clear()
        self._online=value;self.update()
    @pyqtProperty(str,notify=changed)
    def tileUrl(self):return self._template
    @tileUrl.setter
    def tileUrl(self,value):
        if value!=self._template:
            self._template=value;self._images.clear();self._failed.clear();self.update()
    @pyqtProperty(str,notify=changed)
    def attribution(self):return self._attribution
    @attribution.setter
    def attribution(self,value):self._attribution=value;self.update()
    @pyqtProperty(int,notify=changed)
    def zoom(self):return self._zoom

    @pyqtSlot(float,float)
    def setView(self,bearing,pitch):
        self._bearing=bearing%360;self._pitch=max(0,min(45,pitch));self.update()

    def transform_point(self,x,y,inverse=False):
        x-=self.width()/2;y-=self.height()/2
        angle=math.radians(self._bearing);c=math.cos(angle);s=math.sin(angle);scale=math.cos(math.radians(self._pitch))
        if inverse:x,y=c*x+s*y,(-s*x+c*y)/scale
        else:x,y=c*x-s*y*scale,s*x+c*y*scale
        return x+self.width()/2,y+self.height()/2

    def _tile(self,z,x,y):
        if not 0<=y<2**z or not 0<=x<2**z:return None
        url=self._template.replace('{z}',str(z)).replace('{x}',str(x)).replace('{y}',str(y))
        if url in self._images:
            self._images.move_to_end(url)
            return self._images[url]
        if not self._online and url not in self._failed:
            cached=self.cache.data(QUrl(url))
            if cached:
                image=QImage.fromData(cached.readAll());cached.deleteLater()
                if not image.isNull():
                    self._images[url]=image
                    while len(self._images)>48:self._images.popitem(last=False)
                    return image
            self._failed.add(url)
            if len(self._failed)>512:self._failed.clear()
        if self._online and url not in self._pending and url not in self._failed and len(self._pending)<8:
            if QUrl(url).scheme() not in ('https','http'):return None
            self._pending.add(url)
            request=QNetworkRequest(QUrl(url))
            request.setRawHeader(b'User-Agent',b'MeshDesk/0.2 native Meshtastic client')
            request.setAttribute(QNetworkRequest.CacheLoadControlAttribute,QNetworkRequest.PreferCache)
            request.setTransferTimeout(10000)
            reply=self.network.get(request)
            reply.setProperty('tile_url',url)
            # A Python closure capturing reply + this QML-owned item forms a
            # cycle that can be collected while Qt still queues its callback.
            # A registered QObject slot has Qt lifetime/disconnection semantics.
            reply.finished.connect(self._tile_finished)
        return None

    @pyqtSlot()
    def _tile_finished(self):
        reply=self.sender()
        url=reply.property('tile_url')
        self._pending.discard(url)
        if reply.error()==reply.NoError:
            raw=bytes(reply.readAll())
            image=QImage.fromData(raw) if len(raw)<2*1024*1024 else QImage()
            if not image.isNull() and image.width()<=1024 and image.height()<=1024:
                self._images[url]=image
                while len(self._images)>48:self._images.popitem(last=False)
            else:self._failed.add(url)
        else:self._failed.add(url)
        if len(self._failed)>512:self._failed.clear()
        reply.deleteLater();self.update()

    @pyqtSlot(float,float)
    def pan(self,dx,dy):
        cx,cy=self.width()/2,self.height()/2
        px,py=self.transform_point(cx+dx,cy+dy,inverse=True)
        dx,dy=px-cx,py-cy
        x,y=project(self._lat,self._lon,self._zoom)
        self._lat,self._lon=unproject(x-dx,max(0,min(256*2**self._zoom,y-dy)),self._zoom)
        self.update()

    @pyqtSlot(int)
    def changeZoom(self,delta):
        self._zoom=max(1,min(19,self._zoom+delta));self.changed.emit();self.update()

    @pyqtSlot(float,float)
    def center(self,lat,lon):
        self._lat=max(-85,min(85,lat));self._lon=lon;self.update()

    @pyqtSlot()
    def fit(self):
        coords=[coordinate(n) for n in self._nodes if coordinate(n)]
        if not coords:return
        self._lat=sum(c[0] for c in coords)/len(coords);self._lon=sum(c[1] for c in coords)/len(coords)
        for zoom in range(16,0,-1):
            pts=[project(*c,zoom) for c in coords]
            if max(p[0] for p in pts)-min(p[0] for p in pts)<max(100,self.width()-100) and max(p[1] for p in pts)-min(p[1] for p in pts)<max(100,self.height()-100):
                self._zoom=zoom;break
        self.changed.emit();self.update()

    @pyqtSlot(float,float)
    def click(self,x,y):
        for px,py,key in self._clusters:
            if (px-x)**2+(py-y)**2<25**2:
                self._expanded_cluster=key;self.update();return
        for px,py,number in sorted(self._waypoint_markers,key=lambda marker:(marker[0]-x)**2+(marker[1]-y)**2):
            if (px-x)**2+(py-y)**2<20**2:
                self.waypointClicked.emit(str(number));return
        for px,py,num in sorted(self._markers,key=lambda marker:(marker[0]-x)**2+(marker[1]-y)**2):
            if (px-x)**2+(py-y)**2<24**2:
                self.nodeClicked.emit(str(num));return
        if self._expanded_cluster is not None:
            self._expanded_cluster=None;self.update();return
        cx,cy=project(self._lat,self._lon,self._zoom)
        x,y=self.transform_point(x,y,inverse=True)
        lat,lon=unproject(cx+x-self.width()/2,cy+y-self.height()/2,self._zoom)
        self.coordinateClicked.emit(lat,lon)

    @pyqtSlot(float,float,result=str)
    def infoAt(self,x,y):
        for px,py,num in self._markers:
            if math.hypot(px-x,py-y)<20:
                node=next((n for n in self._nodes if n['num']==num),{})
                return str(node.get('name') or node.get('user',{}).get('longName') or f'!{int(num):08x}')+'\nSNR: '+str(node.get('snr','—'))+' dB'
        for points,text in self._links:
            if any(segment_distance(x,y,*a,*b)<7 for a,b in zip(points,points[1:])):return text
        return ''

    def _heat(self,points,left,top):
        mode='snr' if 'snr' in self._layers else 'density'
        values=[(x,y,heat_weight(n.get('snr'),mode)) for x,y,n in points.values()]
        key=(int(self.width()),int(self.height()),self._zoom,mode,tuple(values))
        if key==self._heat_key:return self._heat_image
        from array import array
        scale=3;w=max(1,math.ceil(self.width()/scale));h=max(1,math.ceil(self.height()/scale))
        mask=QImage(w,h,QImage.Format_RGB32);mask.fill(Qt.black)
        p=QPainter(mask);p.setCompositionMode(QPainter.CompositionMode_Plus)
        radius=max(1,heat_radius(self._zoom)/scale);intensity=1+2*min(15,self._zoom)/15
        for x,y,weight in values:
            if not weight or x<-radius*scale or y<-radius*scale or x>self.width()+radius*scale or y>self.height()+radius*scale:continue
            point=QPointF(x/scale,y/scale);gradient=QRadialGradient(point,radius)
            value=min(255,round(85*weight*intensity))
            gradient.setColorAt(0,QColor(value,value,value));gradient.setColorAt(1,QColor(0,0,0))
            p.setPen(Qt.NoPen);p.setBrush(gradient);p.drawEllipse(point,radius,radius)
        p.end()
        bits=mask.constBits();bits.setsize(mask.byteCount())
        colors=[]
        for i in range(256):
            r,g,b,a=heat_color(i/255);colors.append((a<<24)|(r<<16)|(g<<8)|b)
        data=array('I',(colors[pixel&255] for pixel in memoryview(bits).cast('I')))
        image=QImage(data.tobytes(),w,h,w*4,QImage.Format_ARGB32).copy()
        self._heat_key=key;self._heat_image=image
        return image

    def paint(self,painter):
        w,h=self.width(),self.height()
        painter.fillRect(QRectF(0,0,w,h),QColor('#182a32'))
        painter.save();painter.translate(w/2,h/2);painter.rotate(self._bearing);painter.scale(1,math.cos(math.radians(self._pitch)));painter.translate(-w/2,-h/2)
        cx,cy=project(self._lat,self._lon,self._zoom);left=cx-w/2;top=cy-h/2
        corners=[self.transform_point(x,y,True) for x,y in ((0,0),(w,0),(w,h),(0,h))]
        xmin,xmax=min(p[0] for p in corners),max(p[0] for p in corners)
        ymin,ymax=min(p[1] for p in corners),max(p[1] for p in corners)
        for tx in range(math.floor((left+xmin)/256),math.floor((left+xmax)/256)+1):
            for ty in range(math.floor((top+ymin)/256),math.floor((top+ymax)/256)+1):
                box=QRectF(tx*256-left,ty*256-top,256,256)
                image=self._tile(self._zoom,tx,ty)
                if image:painter.drawImage(box,image)
                else:
                    painter.setPen(QColor('#25414b'));painter.drawRect(box)
        points={}
        for n in self._nodes:
            coord=coordinate(n)
            if coord:
                x,y=project(*coord,self._zoom);points[int(n['num'])]=(x-left,y-top,n)
        if 'heat' in self._layers or 'snr' in self._layers:
            painter.drawImage(QRectF(0,0,w,h),self._heat(points,left,top))
        links={}
        if 'direct' in self._layers and self._my_node in points:
            local=points[self._my_node]
            for x,y,n in points.values():
                if n.get('hopsAway',n.get('hops_away'))==0 and n['num']!=self._my_node:
                    links[(self._my_node,n['num'])]=n.get('snr',0)
        if 'remote' in self._layers:
            for x,y,n in points.values():
                info=n.get('neighborinfo',n.get('neighbor_info',{}))
                for neighbor in info.get('neighbors',[]):
                    other=points.get(int(neighbor.get('nodeId',neighbor.get('node_id',0))))
                    if other:
                        links[(n['num'],other[2]['num'])]=neighbor.get('snr',0)
        self._links=[]
        for (start,end),snr in links.items():
            ax,ay,a=points[start];bx,by,b=points[end]
            curved=(end,start) in links;dx=bx-ax;dy=by-ay
            coords=[]
            for i in range(33):
                t=i/32;offset=math.sin(t*math.pi)*.01 if curved else 0
                coords.append((ax+t*dx-dy*offset,ay+t*dy+dx*offset))
            path=QPainterPath(QPointF(*coords[0]))
            for point in coords[1:]:path.lineTo(QPointF(*point))
            painter.setPen(QPen(QColor(signal_color(snr)),5));painter.setBrush(Qt.NoBrush);painter.drawPath(path)
            name=lambda n:n.get('name',n.get('user',{}).get('longName',f"!{n['num']:08x}"))
            self._links.append(([self.transform_point(*p) for p in coords],f'{name(a)} → {name(b)}\nSNR: {snr:.2f} dB'))
        self._markers=[]
        self._clusters=[]
        groups={}
        if 'nodes' in self._layers:
            for x,y,n in points.values():
                lat,lon=coordinate(n)
                groups.setdefault(f'{round(lat*1e7)},{round(lon*1e7)}',[]).append((x,y,n))
            for key,group in groups.items():
                if key==self._expanded_cluster and len(group)>1:
                    for (x,y,n),(dx,dy) in zip(group,fan_offsets(len(group),key)):
                        points[n['num']]=(x+dx,y+dy,n)
        expanded={n['num'] for _,_,n in groups.get(self._expanded_cluster,[])}
        clustered={int(n['num']) for group in groups.values() if len(group)>1 for _,_,n in group}
        for x,y,n in points.values():
            if x<xmin-80 or y<ymin-80 or x>xmax+80 or y>ymax+80:continue
            if 'precision' in self._layers:
                p=n.get('position',{});bits=p.get('precisionBits',p.get('precision_bits',32))
                if 0<bits<32:
                    lat,lon=coordinate(n);px,py=project(lat,lon,self._zoom)
                    radius=precision_meters(bits)/(156543.033928*math.cos(math.radians(lat))/2**self._zoom)
                    painter.setPen(QPen(QColor('#5d9bff'),1));painter.setBrush(QColor(70,130,230,35));painter.drawEllipse(QPointF(px-left,py-top),radius,radius)
            if 'nodes' in self._layers and (n['num'] not in clustered or n['num'] in expanded):
                painter.setPen(QPen(QColor('#10212a'),2));painter.setBrush(QColor('#6bdfb5'));painter.drawEllipse(QPointF(x,y),9,9)
                name=n.get('name',n.get('user',{}).get('longName','Node'))
                rect=QRectF(x+13,y-15,min(150,len(name)*8+12),26)
                painter.fillRect(rect,QColor('#11212d'));painter.setPen(QColor('#e4eff4'));painter.drawText(rect.adjusted(5,0,-3,0),Qt.AlignVCenter,name)
                sx,sy=self.transform_point(x,y)
                self._markers.append((sx,sy,n['num']))
            elif 'heat' in self._layers or 'snr' in self._layers:
                self._markers.append((*self.transform_point(x,y),n['num']))
        for key,group in groups.items():
            if len(group)<2 or key==self._expanded_cluster:continue
            x=sum(p[0] for p in group)/len(group);y=sum(p[1] for p in group)/len(group)
            painter.setBrush(QColor('#52ceac'));painter.setPen(QPen(QColor('#0d2926'),2));painter.drawEllipse(QPointF(x,y),18,18)
            painter.setPen(QColor('#10212a'));painter.drawText(QRectF(x-18,y-18,36,36),Qt.AlignCenter,str(len(group)))
            sx,sy=self.transform_point(x,y)
            self._clusters.append((sx,sy,key))
        self._waypoint_markers=[]
        if 'waypoints' in self._layers:
            for waypoint in self._waypoints:
                if waypoint.get('expire',0) and waypoint['expire']<__import__('time').time():continue
                lat=waypoint.get('latitude_i',waypoint.get('latitudeI',0))*1e-7
                lon=waypoint.get('longitude_i',waypoint.get('longitudeI',0))*1e-7
                x,y=project(lat,lon,self._zoom);x-=left;y-=top
                sx,sy=self.transform_point(x,y)
                self._waypoint_markers.append((sx,sy,int(waypoint['id'])))
                icon=int(waypoint.get('icon',0));painter.save()
                if 0<icon<=0x10ffff:
                    font=QFont();font.setFamilies(['DejaVu Sans','Noto Color Emoji','Apple Color Emoji','Segoe UI Emoji']);font.setPixelSize(26)
                    painter.setFont(font);painter.drawText(QRectF(x-18,y-18,36,36),Qt.AlignCenter,chr(icon))
                else:
                    painter.setPen(QPen(QColor('#ffc278'),3));painter.drawLine(QPointF(x-7,y),QPointF(x+7,y));painter.drawLine(QPointF(x,y-7),QPointF(x,y+7))
                painter.restore();painter.setPen(QColor('#ffc278'))
                painter.drawText(QPointF(x+12,y),waypoint.get('name','Waypoint'))
        painter.restore()
        length,text=nice_scale(self._lat,self._zoom)
        painter.fillRect(QRectF(8,h-63,length+12,32),QColor('#11212d'))
        painter.setPen(QPen(Qt.white,2));painter.drawLine(QPointF(14,h-36),QPointF(14+length,h-36))
        painter.drawText(QRectF(14,h-60,length+5,20),Qt.AlignCenter,text)
        painter.fillRect(QRectF(0,h-26,w,26),QColor('#11212d'))
        painter.setPen(QColor('#b4c6cc'))
        painter.drawText(QRectF(10,h-26,w-20,26),Qt.AlignVCenter,
                         (self._attribution if self._online else 'Offline · enable map tiles in Preferences')+f'   |   {self._lat:.4f}, {self._lon:.4f}   z{self._zoom}')


class QRProvider(QQuickImageProvider):
    def __init__(self,controller):
        super().__init__(QQuickImageProvider.Image)
        self.controller=controller

    def requestImage(self,id,size):
        import qrcode
        matrix=qrcode.QRCode(border=4)
        matrix.add_data(self.controller.qr_url or 'MeshDesk')
        matrix.make(fit=True)
        grid=matrix.get_matrix();scale=5;n=len(grid)
        image=QImage(n*scale,n*scale,QImage.Format_RGB32);image.fill(Qt.white)
        p=QPainter(image)
        for y,row in enumerate(grid):
            for x,on in enumerate(row):
                if on:p.fillRect(x*scale,y*scale,scale,scale,Qt.black)
        p.end()
        return image,image.size()
