"""Geometry audit of rendered controls, plus reviewable screenshots/inventory.

Clipped scroll content is expected. Intersecting visible, unrelated controls
and horizontal overflow inside a vertical scroll surface are not.
"""
import json
import os
from pathlib import Path
from PyQt5.QtCore import QObject,QUrl,QPointF,QRectF,QMetaObject,qInstallMessageHandler
from PyQt5.QtQml import QQmlApplicationEngine,qmlRegisterType
from PyQt5.QtQuick import QQuickItem
from PyQt5.QtTest import QTest
from meshdesk.controller import Controller
from meshdesk.store import Store
from meshdesk.mapview import MeshMap,QRProvider
from conftest import wait_for

INTERACTIVE=('QQuickLabel','QQuickSlider','QQuickMenuItem','QQuickButton','QQuickToolButton','QQuickComboBox','QQuickSwitch','QQuickCheckBox','QQuickTextField','QQuickTextArea','QQuickSpinBox','QQuickItemDelegate','QQuickTabButton')
KINDS={}


def ancestors(item):
    parent=item.parentItem()
    while parent:
        yield parent
        parent=parent.parentItem()


def control_kind(item):
    meta=item.metaObject()
    name=meta.className()
    if name in KINDS:return KINDS[name]
    while meta:
        if meta.className() in INTERACTIVE:
            KINDS[name]=meta.className();return KINDS[name]
        meta=meta.superClass()
    KINDS[name]=None
    return None


def controls(root):
    def walk(item):
        yield item
        for child in item.childItems():yield from walk(child)
    result=[]
    for item in walk(root.contentItem()):
        if not item.isVisible() or item.opacity()==0:continue
        kind=control_kind(item)
        if not kind or item.width()<=0 or item.height()<=0:continue
        parents=list(ancestors(item))
        if any(control_kind(p) for p in parents):continue
        rect=QRectF(item.mapToScene(QPointF(0,0)),item.mapToScene(QPointF(item.width(),item.height())))
        clip=QRectF(0,0,root.width(),root.height())
        for parent in parents:
            if parent.clip():clip=clip.intersected(QRectF(parent.mapToScene(QPointF(0,0)),parent.mapToScene(QPointF(parent.width(),parent.height()))))
        visible=rect.intersected(clip)
        if visible.width()<2 or visible.height()<2:continue
        result.append((item,kind,rect,clip,visible))
    return result


def audit(root,within=None):
    found=[v for v in controls(root) if within is None or v[0] is within or within in ancestors(v[0])];issues=[];inventory=[]
    for item,kind,rect,clip,visible in found:
        label=item.objectName() or str(item.property('text') or item.property('placeholderText') or kind)
        inventory.append({'control':kind,'label':label,'bounds':[round(v,1) for v in (rect.x(),rect.y(),rect.width(),rect.height())]})
        if rect.left()<clip.left()-2 or rect.right()>clip.right()+2:
            issues.append('Horizontal clipping: '+label)
    for i,(a,_,ar,ac,av) in enumerate(found):
        for b,_,br,bc,bv in found[i+1:]:
            # controls() already excludes descendants of another control.
            # Avoid rewalking the Qt object tree for every pair on ARM32.
            overlap=av.intersected(bv)
            if overlap.width()>3 and overlap.height()>3:
                issues.append('Overlap: '+str(a.property('text') or a.objectName())+' / '+str(b.property('text') or b.objectName()))
    return inventory,issues


def test_all_pages_and_settings_geometry(qtapp,tmp_path):
    output=Path(os.environ.get('MESHDESK_ARTIFACTS',str(tmp_path/'screenshots')))/'layout'
    output.mkdir(parents=True,exist_ok=True)
    messages=[];previous=qInstallMessageHandler(lambda k,c,t:messages.append(t))
    c=Controller(Store(tmp_path/'data.sqlite'),demo=True)
    engine=QQmlApplicationEngine();qmlRegisterType(MeshMap,'MeshDesk',1,0,'MeshMap')
    engine.rootContext().setContextProperty('bridge',c);engine.addImageProvider('qr',QRProvider(c))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parents[1]/'src/meshdesk/qml/Main.qml')))
    reports=[];failures=[]
    try:
        root=engine.rootObjects()[0]
        wait_for(qtapp,lambda:json.loads(c.stateJson).get('connected'))
        def capture(name):
            root.setProperty('toastText','');QTest.qWait(80)
            snapshot=root.grabWindow()  # Flush polish/layout before inspecting newly created delegates.
            inventory,issues=audit(root)
            reports.append({'view':name,'controls':inventory,'issues':issues})
            if issues:failures.append(name+': '+', '.join(issues))
            assert snapshot.save(str(output/(name+'.png')))
        for width,height in ((1024,600),(600,1024),(480,600)):
            root.setWidth(width);root.setHeight(height)
            for language,theme in (('en','dark'),('pl-PL','light')):
                c._dispatch('preference',{'key':'language','value':language});c._dispatch('preference',{'key':'theme','value':theme});c._publish()
                for page in ('Chat','Nodes','Map','Settings','Connections','Activity','Preferences'):
                    root.setProperty('page',page);QTest.qWait(100)
                    capture(f'{width}-{height}-{language}-{page}')
                    # Scroll each page to expose bottom controls as well.
                    loader=root.findChild(QObject,'pageLoader');item=loader.property('item')
                    flicks=[o for o in item.findChildren(QQuickItem) if o.property('contentHeight') is not None and o.property('contentY') is not None]
                    for f in flicks:
                        if f.property('contentHeight')>f.height():f.setProperty('contentY',f.property('contentHeight')-f.height())
                    capture(f'{width}-{height}-{language}-{page}-bottom')
                    if page=='Nodes':
                        c._dispatch('node',{'num':0xa1000002});c._publish()
                        capture(f'{width}-{height}-{language}-{page}-selected')
                        c._dispatch('node',{'num':0});c._publish()
        c._dispatch('preference',{'key':'language','value':'en'});c._dispatch('preference',{'key':'theme','value':'dark'})
        root.setWidth(1024);root.setHeight(600);root.setProperty('page','Settings');QTest.qWait(80)
        from meshdesk.schema import sections
        for width in (1024,480):
            root.setWidth(width)
            for section in sections():
                c._dispatch('setting_load',{'section':section['key']})
                wait_for(qtapp,lambda:not c.settings_loading);c._publish()
                item=root.findChild(QObject,'pageLoader').property('item')
                scroll=root.findChild(QObject,'settingsFieldScroll').property('contentItem')
                scroll.setProperty('contentY',0)
                capture(str(width)+'-settings-'+section['key'])
                maximum=scroll.property('contentHeight')-scroll.height()
                offset=scroll.height()*.8;step=1
                while 0<offset<maximum:
                    scroll.setProperty('contentY',offset)
                    capture(str(width)+'-settings-'+section['key']+'-scroll'+str(step))
                    offset+=scroll.height()*.8;step+=1
                item=root.findChild(QObject,'pageLoader').property('item')
                for f in item.findChildren(QQuickItem):
                    if f.property('contentHeight') is not None and f.property('contentY') is not None and f.property('contentHeight')>f.height():
                        f.setProperty('contentY',f.property('contentHeight')-f.height())
                capture(str(width)+'-settings-'+section['key']+'-bottom')
        root.setWidth(1024)
        c._dispatch('export_channels',{});wait_for(qtapp,lambda:not c.busy)
        c._dispatch('import_preview',{'url':c.qr_url});c._publish()
        for tab in (1,2):
            root.findChild(QObject,'settingsTabs').setProperty('currentIndex',tab)
            capture('settings-tab-'+str(tab))
        for page,name in (('Chat','commandDialog'),('Chat','confirmDialog'),('Chat','backupDialog'),('Nodes','nodeFiltersDialog'),('Nodes','rolesFilterDialog'),('Nodes','hardwareFilterDialog'),('Map','waypointDialog'),('Map','mapLayersMenu'),('Map','mapLocateMenu'),('Map','mapViewPopup'),('Connections','portPicker'),('Activity','verifyDialog')):
            root.setProperty('page',page);QTest.qWait(80)
            dialog=root.findChild(QObject,name);QMetaObject.invokeMethod(dialog,'open');QTest.qWait(150)
            assert 0<dialog.property('height')<=root.height()
            # Audit only popup controls: the obscured page intentionally overlaps.
            snapshot=root.grabWindow()
            content=dialog.property('contentItem')
            inv,issues=audit(root,content)
            reports.append({'view':name,'controls':inv,'issues':issues})
            if issues:failures.append(name+': '+', '.join(issues))
            snapshot.save(str(output/(name+'.png')))
            QMetaObject.invokeMethod(dialog,'close');QTest.qWait(100)
        for width in (1024,480):
            root.setWidth(width);root.setProperty('page','Activity');QTest.qWait(100)
            for suffix,data in [('number_inform',{'security_number':123456}),('number_request',{'nonce':1,'remote_longname':'A very long node name in the mountains'}),('final',{'nonce':1,'verification_characters':'ABCD'})]:
                c.notification={'key_verification_'+suffix:data};c._publish()
                capture(str(width)+'-verification-'+suffix)
        errors=[t for t in messages if any(s in t for s in ('Error','Binding loop','Cannot','Unable','is not defined'))]
        (output/'inventory.json').write_text(json.dumps({'views':reports,'qml_errors':errors},indent=2), encoding='utf-8')
        from html import escape
        gallery='<!doctype html><meta charset="utf-8"><title>MeshDesk GUI review</title><style>body{font:16px sans-serif;background:#14212b;color:white}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}img{width:100%}a{color:#8cdbbb}</style><h1>MeshDesk GUI review</h1><p>Rendered states and geometry findings. Open any image at full size. <a href="../variants/index.html">Populated chat, connection forms and advanced views</a>.</p><main>'
        for report in reports:
            name=report['view'];gallery+='<article><h2>'+escape(name)+'</h2><p>'+str(len(report['controls']))+' controls · '+str(len(report['issues']))+' geometry issues</p><a href="'+name+'.png"><img loading="lazy" src="'+name+'.png"></a></article>'
        (output/'index.html').write_text(gallery+'</main>', encoding='utf-8')
        assert not errors,'\n'.join(set(errors))
        assert not failures,'\n'.join(failures)
    finally:
        for root in engine.rootObjects():root.close()
        del engine;c.close();qInstallMessageHandler(previous)
