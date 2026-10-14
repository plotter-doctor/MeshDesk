"""Populated and alternate-control states complement the page/form sweep."""
import json
import os
from pathlib import Path
from PyQt5.QtCore import QObject,QUrl,QMetaObject,qInstallMessageHandler
from PyQt5.QtQml import QQmlApplicationEngine,qmlRegisterType
from PyQt5.QtQuick import QQuickItem
from PyQt5.QtTest import QTest
from meshdesk.controller import Controller
from meshdesk.mapview import MeshMap,QRProvider
from meshdesk.store import Store
from meshdesk.simulator import LOCAL,PEER
from test_gui_layout import audit
from conftest import wait_for,prepare_layout_window


def test_populated_chat_transport_forms_and_advanced_settings(qtapp,tmp_path):
    output=Path(os.environ.get('MESHDESK_ARTIFACTS',str(tmp_path)))/'variants';output.mkdir(parents=True,exist_ok=True)
    errors=[];previous=qInstallMessageHandler(lambda k,c,t:errors.append(t))
    c=Controller(Store(tmp_path/'data.sqlite'),demo=True)
    engine=QQmlApplicationEngine();qmlRegisterType(MeshMap,'MeshDesk',1,0,'MeshMap')
    engine.rootContext().setContextProperty('bridge',c);engine.addImageProvider('qr',QRProvider(c))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/meshdesk/qml/Main.qml')))
    reports=[];problems=[]
    try:
        root=engine.rootObjects()[0];wait_for(qtapp,lambda:json.loads(c.stateJson).get('connected'))
        prepare_layout_window(root)
        peer=next(n for n in c.store.nodes(c.active) if n['num']==PEER)
        peer['user']['longName']='Long radio name beside the river 123456';c.store.node(c.active,peer)
        for i in range(3):
            c.store.message(c.active,100+i,LOCAL if i%2 else PEER,PEER if i%2 else LOCAL,0,
                ('Unicode 👋 Zażółć gęślą jaźń. '*5) if i<2 else 'x'*233,outgoing=bool(i%2),metadata={'reply_id':100 if i else 0})
        def capture(name):
            c._publish();root.setProperty('toastText','');QTest.qWait(120)
            snapshot=root.grabWindow()
            if root.property('page')=='Chat':
                # Rendering can change delegate heights and schedule the
                # follow-to-end update. Capture the resulting settled frame.
                listing=root.findChild(QObject,'messageList')
                wait_for(qtapp,lambda:listing.property('atYEnd'))
                QTest.qWait(30);snapshot=root.grabWindow()
            inv,issues=audit(root);reports.append({'view':name,'controls':inv,'issues':issues})
            problems.extend(name+': '+issue for issue in issues)
            assert snapshot.save(str(output/(name+'.png')))
        for width in (1024,480):
            root.setWidth(width);root.setHeight(600)
            for language,theme in (('en','dark'),('pl-PL','light')):
                c._dispatch('preference',{'key':'language','value':language});c._dispatch('preference',{'key':'theme','value':theme})
                c._dispatch('chat',{'peer':PEER});root.setProperty('page','Chat');QTest.qWait(120)
                capture(f'{width}-{language}-chat-long-name')
                listing=root.findChild(QObject,'messageList')
                wait_for(qtapp,lambda:listing.property('atYEnd'))
                assert listing.property('count')==3
                root.setProperty('page','Connections');QTest.qWait(100)
                combo=root.findChild(QObject,'transportBox')
                for index in range(4):
                    combo.setProperty('currentIndex',index)
                    capture(f'{width}-{language}-transport-{index}')
                root.setProperty('page','Settings');QTest.qWait(100)
                c._dispatch('setting_load',{'section':'config.lora'});wait_for(qtapp,lambda:not c.settings_loading)
                item=root.findChild(QObject,'pageLoader').property('item');item.setProperty('advanced',True)
                capture(f'{width}-{language}-settings-json');item.setProperty('advanced',False)
                c._dispatch('export_channels',{});wait_for(qtapp,lambda:not c.busy)
                c._dispatch('import_preview',{'url':c.qr_url})
                for tab in (1,2):
                    root.findChild(QObject,'settingsTabs').setProperty('currentIndex',tab)
                    capture(f'{width}-{language}-settings-tab-{tab}')
                    for f in item.findChildren(QQuickItem):
                        if f.isVisible() and f.property('contentY') is not None and f.property('contentHeight') is not None and f.property('contentHeight')>f.height():
                            f.setProperty('contentY',f.property('contentHeight')-f.height())
                    capture(f'{width}-{language}-settings-tab-{tab}-bottom')
                root.findChild(QObject,'settingsTabs').setProperty('currentIndex',0)
        (output/'inventory.json').write_text(json.dumps(reports,indent=2), encoding='utf-8')
        from html import escape
        (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>MeshDesk alternate states</title><style>body{background:#14212b;color:white;font:16px sans-serif}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}img{width:100%}a{color:#8cdbbb}</style><h1>Alternate and populated states</h1><main>'+''.join('<article><h2>'+escape(r['view'])+'</h2><a href="'+r['view']+'.png"><img loading="lazy" src="'+r['view']+'.png"></a></article>' for r in reports)+'</main>', encoding='utf-8')
        assert not problems,'\n'.join(problems)
        assert not [e for e in errors if any(w in e for w in ('Error','Binding loop','Cannot','Unable','is not defined'))],errors
    finally:
        for root in engine.rootObjects():root.close()
        del engine;c.close();qInstallMessageHandler(previous)
