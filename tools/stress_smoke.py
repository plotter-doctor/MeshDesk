#!/usr/bin/env python3
"""Bounded large-mesh UI exercise; local simulator, no RF transmissions."""
import argparse,json,os,platform,random,sys,time,tempfile
from pathlib import Path
os.environ.setdefault('QT_QUICK_BACKEND','software')
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE','Material')
from PyQt5.QtCore import QUrl,QObject,Qt,QMetaObject,qInstallMessageHandler
from PyQt5.QtQml import QQmlApplicationEngine,qmlRegisterType
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication
from meshdesk.controller import Controller
from meshdesk.store import Store
from meshdesk.mapview import MeshMap,QRProvider


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--nodes',type=int,default=500);parser.add_argument('--messages',type=int,default=5000)
    args=parser.parse_args();app=QApplication([]);app.setApplicationName('MeshDesk-stress')
    errors=[];previous=qInstallMessageHandler(lambda kind,ctx,text:errors.append(text))
    result={'architecture':platform.machine(),'nodes':args.nodes,'stored_messages':args.messages,'page_ms':{}}
    with tempfile.TemporaryDirectory() as directory:
        c=Controller(Store(Path(directory)/'stress.sqlite'),demo=True)
        engine=QQmlApplicationEngine();qmlRegisterType(MeshMap,'MeshDesk',1,0,'MeshMap')
        engine.rootContext().setContextProperty('bridge',c);engine.addImageProvider('qr',QRProvider(c))
        engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/meshdesk/qml/Main.qml')))
        try:
            if not engine.rootObjects():raise RuntimeError(str(errors))
            root=engine.rootObjects()[0]
            deadline=time.monotonic()+15
            while not json.loads(c.stateJson).get('connected') and time.monotonic()<deadline:QTest.qWait(20)
            rng=random.Random(15)
            for i in range(args.nodes):
                c.store.node('simulator',{'num':0xa2000000+i,'user':{'longName':f'Node {i:04}','shortName':str(i)},
                    'position':{'latitude':52+rng.uniform(-.2,.2),'longitude':21+rng.uniform(-.2,.2)},'snr':rng.uniform(-20,10)})
            rows=[('simulator',i+1,0xa2000000,0xffffffff,0,'Large mesh history '+str(i),time.time()-args.messages+i,'received',0,1,'{}') for i in range(args.messages)]
            with c.store.db:
                c.store.db.executemany('INSERT INTO messages(profile,packet_id,sender,destination,channel,text,timestamp,status,outgoing,read,metadata) VALUES (?,?,?,?,?,?,?,?,?,?,?)',rows)
            c._publish();QTest.qWait(100)
            for page in ('Nodes','Map','Chat'):
                started=time.perf_counter();root.setProperty('page',page);app.processEvents();root.grabWindow()
                result['page_ms'][page]=round((time.perf_counter()-started)*1000,2)
                QTest.qWait(250)
                if page=='Map':
                    item=root.findChild(QObject,'meshMap');item.layers=['snr']
                    started=time.perf_counter();app.processEvents();root.grabWindow()
                    result['heatmap_ms']=round((time.perf_counter()-started)*1000,2)
                    args.output.parent.mkdir(parents=True,exist_ok=True)
                    root.grabWindow().save(str(args.output.with_suffix('.png')))
            composer=root.findChild(QObject,'composer');composer.forceActiveFocus()
            times=[]
            for key in 'MeshDesk':
                started=time.perf_counter();QTest.keyClick(root,ord(key.upper()));app.processEvents()
                times.append(round((time.perf_counter()-started)*1000,2));QTest.qWait(80)
            result['key_event_ms']=times
            result['visible_messages']=len(json.loads(c.stateJson)['messages'])
            if sys.platform=='linux':
                status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines())
                result['rss_mib']=round(int(status['VmRSS'].split()[0])/1024,2)
            result['qml_errors']=[e for e in errors if any(t in e for t in ('Error','Cannot','Binding loop','is not defined','not installed'))]
            result['passed']=not result['qml_errors'] and result['visible_messages']==100
            args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
            return 0 if result['passed'] else 1
        finally:
            for root in engine.rootObjects():root.close()
            del engine;c.close();qInstallMessageHandler(previous)


if __name__=='__main__':raise SystemExit(main())
