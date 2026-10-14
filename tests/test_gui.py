import json
import os
from pathlib import Path
from PyQt5.QtCore import QUrl,QObject,Qt,QPointF,QMetaObject,qInstallMessageHandler
from PyQt5.QtQml import QQmlApplicationEngine,qmlRegisterType
from PyQt5.QtTest import QTest
from meshdesk.controller import Controller
from meshdesk.mapview import MeshMap,QRProvider
from meshdesk.store import Store
from meshdesk.simulator import PEER
from conftest import wait_for


def test_native_ui_workflows(qtapp,tmp_path,monkeypatch):
    messages=[]
    previous=qInstallMessageHandler(lambda kind,ctx,text:messages.append(text))
    store=Store(tmp_path/'data.sqlite')
    controller=Controller(store,demo=True)
    engine=QQmlApplicationEngine()
    qmlRegisterType(MeshMap,'MeshDesk',1,0,'MeshMap')
    engine.rootContext().setContextProperty('bridge',controller)
    engine.addImageProvider('qr',QRProvider(controller))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/meshdesk/qml/Main.qml')))
    try:
        assert engine.rootObjects(),messages
        root=engine.rootObjects()[0]
        wait_for(qtapp,lambda:json.loads(controller.stateJson).get('connected'))
        def act(action,**args):
            controller.dispatch(action,json.dumps(args))
            qtapp.processEvents()
        # Exercise the actual composer and send button, not just controller calls.
        composer=root.findChild(QObject,'composer');assert composer
        composer.setProperty('text','Hello from the native client')
        qtapp.processEvents()
        send=root.findChild(QObject,'sendMessage')
        point=send.mapToScene(QPointF(send.width()/2,send.height()/2)).toPoint()
        QTest.mouseClick(root,Qt.LeftButton,pos=point)
        wait_for(qtapp,lambda:len(store.messages('simulator'))==2)
        assert any(m['status']=='Acknowledged' for m in store.messages('simulator'))
        act('node',num=PEER)
        artifacts=Path(os.environ.get('MESHDESK_ARTIFACTS',str(tmp_path/'screenshots')))
        artifacts.mkdir(parents=True,exist_ok=True)
        for page in ('Chat','Nodes','Map','Settings','Connections','Activity','Preferences'):
            root.setProperty('page',page)
            QTest.qWait(180)
            if page=='Settings':
                act('setting_load',section='config.lora')
                wait_for(qtapp,lambda:controller.settings_message is not None)
                act('setting_edit',path='hop_limit',value='4')
                act('setting_save')
                wait_for(qtapp,lambda:not controller.settings_loading and not controller.busy)
                assert controller.simulator.server.radio.config['lora'].hop_limit==4
            if page=='Map':
                from meshdesk.mapview import coordinate
                item=root.findChild(QObject,'meshMap')
                # Initial auto-fit is asynchronous. Wait for it before choosing
                # a pixel target; a fixed sleep races the slower ARM renderer.
                wait_for(qtapp,lambda:not root.findChild(QObject,'mapInitialFit').property('running'))
                node=next(n for n in item.nodes if coordinate(n))
                item.center(*coordinate(node));QTest.qWait(80);root.grabWindow()
                x,y,num=next(m for m in item._markers if m[2]==int(node['num']))
                assert isinstance(num,int)
                point=item.mapToScene(QPointF(x,y)).toPoint()
                QTest.mouseMove(root,point);QTest.qWait(80)
                assert item.infoAt(x,y)
                QTest.mouseClick(root,Qt.LeftButton,pos=point)
                assert controller.selected_node==num
                # QML signal parameters must reach the position dialog.
                item.coordinateClicked.emit(51.2345678,20.1234567);QTest.qWait(50)
                dialog=root.findChild(QObject,'waypointDialog')
                assert dialog.property('visible')
                QMetaObject.invokeMethod(dialog,'close')
            if page=='Connections':
                from types import SimpleNamespace
                monkeypatch.setattr('serial.tools.list_ports.comports',lambda:[SimpleNamespace(description='Test USB '+str(i),device='/dev/test'+str(i),vid=0x303a) for i in range(25)])
                combo=root.findChild(QObject,'transportBox')
                point=combo.mapToScene(QPointF(combo.width()/2,combo.height()/2)).toPoint()
                QTest.mouseClick(root,Qt.LeftButton,pos=point);QTest.qWait(80)
                popup=root.findChild(QObject,'transportBoxPopup');assert popup
                root.grabWindow().save(str(artifacts/'protocol-picker.png'))
                assert popup.property('height')<=300
                QMetaObject.invokeMethod(popup,'close')
                discover=root.findChild(QObject,'discoverRadios')
                point=discover.mapToScene(QPointF(discover.width()/2,discover.height()/2)).toPoint()
                background=discover.property('background');normal=background.property('color')
                QTest.mousePress(root,Qt.LeftButton,pos=point);qtapp.processEvents()
                assert background.property('color')!=normal
                QTest.mouseRelease(root,Qt.LeftButton,pos=point)
                wait_for(qtapp,lambda:not controller.busy)
                picker=root.findChild(QObject,'portPicker');assert picker.property('visible')
                listing=root.findChild(QObject,'discoveredRadioList')
                wait_for(qtapp,lambda:listing.property('count')==25)
                assert listing.property('contentHeight')>listing.height()
                QTest.qWait(80);root.grabWindow().save(str(artifacts/'port-picker.png'))
                point=listing.mapToScene(QPointF(listing.width()/2,30)).toPoint()
                QTest.mouseClick(root,Qt.LeftButton,pos=point);QTest.qWait(80)
                wait_for(qtapp,lambda:not picker.property('visible'))
                assert root.findChild(QObject,'connectionAddress').property('text')=='/dev/test0'
                combo.setProperty('currentIndex',1)
                root.findChild(QObject,'connectionAddress').setProperty('text',controller.simulator.address)
                button=root.findChild(QObject,'connectRadio')
                QTest.qWait(80)
                point=button.mapToScene(QPointF(button.width()/2,button.height()/2)).toPoint()
                QTest.mouseClick(root,Qt.LeftButton,pos=point)
                wait_for(qtapp,lambda:button.property('text')=='Disconnect')
                assert not button.property('highlighted')
                new_profile=controller.active
                assert controller.sessions[new_profile]['status']=='Connected'
                count=len(controller.sessions)
                act('add_profile',transport='tcp',address=controller.simulator.address)
                assert len(controller.sessions)==count
                QTest.mouseClick(root,Qt.LeftButton,pos=point)
                wait_for(qtapp,lambda:button.property('text')=='Connect radio')
                assert controller.sessions[new_profile]['status']=='Offline'
                act('select_profile',id='simulator')
            QTest.qWait(120)
            root.setProperty('toastText','')
            root.grabWindow().save(str(artifacts/(page.lower()+'.png')))
        act('command',name='favorite',args={'value':PEER})
        wait_for(qtapp,lambda:any(n['num']==PEER and n.get('isFavorite') for n in store.nodes('simulator')))
        act('export_channels')
        wait_for(qtapp,lambda:bool(controller.qr_url))
        root.setProperty('page','Settings');QTest.qWait(120)
        tabs=root.findChild(QObject,'settingsTabs');assert tabs,messages
        tabs.setProperty('currentIndex',1);QTest.qWait(150)
        root.grabWindow().save(str(artifacts/'channels.png'))
        tabs.setProperty('currentIndex',2);QTest.qWait(150)
        root.grabWindow().save(str(artifacts/'radio-actions.png'))
        act('import_preview',url=controller.qr_url)
        act('import_apply')
        wait_for(qtapp,lambda:not controller.busy and not controller.import_preview,timeout=15)
        assert controller.busy==0
        act('command',name='verify_key',args={'node':PEER})
        wait_for(qtapp,lambda:'key_verification_number_inform' in controller.notification)
        act('preference',key='language',value='pl-PL')
        act('preference',key='theme',value='light');QTest.qWait(100)
        root.grabWindow().save(str(artifacts/'light-polish.png'))
        act('preference',key='language',value='en')
        act('preference',key='theme',value='dark')
        root.setProperty('width',600);root.setProperty('height',1024)
        root.setProperty('page','Chat');QTest.qWait(100)
        root.grabWindow().save(str(artifacts/'portrait.png'))
        # Reopening a populated direct conversation used to trigger a height
        # binding loop, especially when wrapped replies changed the layout.
        local=controller.sessions['simulator']['snapshot']['my_num']
        controller.store.message('simulator',4278636133,local,PEER,0,
            'MeshDesk USB test: private message to the second node. Testing the native Linux client.',
            outgoing=True,status='Acknowledged')
        controller.store.message('simulator',736099816,local,PEER,0,
            'Unicode reply — Zażółć gęślą jaźń 👋. Test complete; no reply needed.',
            outgoing=True,status='Acknowledged',metadata={'reply_id':4278636133})
        act('chat',peer=PEER)
        for width in (1024,480,600,1024):
            root.setProperty('page','Nodes');QTest.qWait(50)
            root.setProperty('width',width)
            root.setProperty('page','Chat');QTest.qWait(150)
        root.setProperty('height',600);QTest.qWait(150)
        root.grabWindow().save(str(artifacts/'unicode-reply.png'))
        for page,dialog_name in (('Nodes','nodeFiltersDialog'),('Map','waypointDialog')):
            root.setProperty('page',page);QTest.qWait(100)
            dialog=root.findChild(QObject,dialog_name);assert dialog
            QMetaObject.invokeMethod(dialog,'open');QTest.qWait(200)
            assert 0 < dialog.property('height') <= root.height()-68
            root.grabWindow().save(str(artifacts/(dialog_name+'.png')))
            QMetaObject.invokeMethod(dialog,'close');QTest.qWait(100)
        root.setProperty('page','Chat');QTest.qWait(100)
        dialog=root.findChild(QObject,'commandDialog');assert dialog
        QMetaObject.invokeMethod(dialog,'open');QTest.qWait(150)
        command_list=root.findChild(QObject,'commandList');assert command_list.property('count')>=19
        root.grabWindow().save(str(artifacts/'commands.png'))
        QMetaObject.invokeMethod(dialog,'close')
        wait_for(qtapp,lambda:not dialog.property('visible'))
        # QML errors indicate missing controls, broken bindings, or failed pages.
        failures=[m for m in messages if any(t in m for t in ('Error','is not','Cannot','Unable','not found','Unexpected','Invalid','Binding loop'))]
        assert not failures,'\n'.join(dict.fromkeys(failures))
        exit_button=root.findChild(QObject,'exitButton')
        assert exit_button.isVisible() and exit_button.height()>=44
        point=exit_button.mapToScene(QPointF(exit_button.width()/2,exit_button.height()/2)).toPoint()
        background=exit_button.property('background');normal=background.property('color')
        QTest.mousePress(root,Qt.LeftButton,pos=point);qtapp.processEvents()
        assert background.property('color')!=normal
        QTest.mouseRelease(root,Qt.LeftButton,pos=point)
        wait_for(qtapp,lambda:not root.isVisible())
    finally:
        for root in engine.rootObjects():root.close()
        del engine
        controller.close()
        qInstallMessageHandler(previous)
