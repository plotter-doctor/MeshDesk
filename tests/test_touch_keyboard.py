"""Opt-in on an installed Qt Virtual Keyboard runtime (including the tablet)."""
import json
import os
from pathlib import Path
import pytest
from PyQt5.QtCore import QUrl,QObject,QMetaObject,Qt,QPointF,qInstallMessageHandler
from PyQt5.QtQml import QQmlApplicationEngine,qmlRegisterType
from PyQt5.QtTest import QTest
from meshdesk.controller import Controller
from meshdesk.mapview import MeshMap,QRProvider
from meshdesk.store import Store
from conftest import wait_for


@pytest.mark.skipif(os.environ.get('QT_IM_MODULE')!='qtvirtualkeyboard',reason='Enable installed Qt Virtual Keyboard explicitly')
def test_touch_keyboard_keeps_composer_visible(qtapp,tmp_path):
    errors=[];previous=qInstallMessageHandler(lambda _,ctx,text:errors.append(text))
    c=Controller(Store(tmp_path/'touch.sqlite'),demo=True)
    engine=QQmlApplicationEngine();qmlRegisterType(MeshMap,'MeshDesk',1,0,'MeshMap')
    engine.rootContext().setContextProperty('bridge',c);engine.addImageProvider('qr',QRProvider(c))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/meshdesk/qml/Main.qml')))
    try:
        assert engine.rootObjects(),errors
        root=engine.rootObjects()[0]
        wait_for(qtapp,lambda:json.loads(c.stateJson).get('connected'))
        root.requestActivate();wait_for(qtapp,root.isActive)
        composer=root.findChild(QObject,'composer');composer.forceActiveFocus()
        qtapp.inputMethod().show();QTest.qWait(800)
        panel=root.findChild(QObject,'touchKeyboard');assert panel,errors
        assert panel.property('active'),errors
        assert panel.height()>100
        assert not root.findChild(QObject,'emptyChatHint').isVisible()
        point=composer.mapToScene(QPointF(0,composer.height()))
        panel_top=panel.mapToScene(QPointF(0,0)).y()
        assert point.y()<=panel_top+1,(point.y(),panel_top)
        # Find the actual Q key: layouts/font scaling can move it, so a fixed
        # pixel offset tests the wrong key on a different display backend.
        def items(item):
            yield item
            for child in item.childItems():yield from items(child)
        keys=[item for item in items(panel) if item.isVisible() and item.property('key')==Qt.Key_Q and item.width()>0]
        assert len(keys)==1
        key=keys[0];center=key.mapToScene(QPointF(key.width()/2,key.height()/2)).toPoint()
        QTest.mouseClick(root,Qt.LeftButton,pos=center,delay=50)
        QTest.qWait(150)
        assert composer.property('text').lower()=='q'
        artifact=Path(os.environ.get('MESHDESK_ARTIFACTS',str(tmp_path)))
        artifact.mkdir(parents=True,exist_ok=True)
        root.grabWindow().save(str(artifact/'keyboard.png'))
        qtapp.inputMethod().hide();QTest.qWait(200)
        assert not panel.property('active')
        assert root.findChild(QObject,'emptyChatHint').isVisible()
        assert not [e for e in errors if any(word in e for word in ('Error','Cannot','Binding loop','not installed'))],errors
    finally:
        for root in engine.rootObjects():root.close()
        del engine;c.close();qInstallMessageHandler(previous)
