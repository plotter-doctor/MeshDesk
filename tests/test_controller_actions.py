"""State transitions and negative paths exposed by native controls."""
import base64
import json
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
from PyQt5.QtWidgets import QApplication
from meshdesk.controller import Controller
from meshdesk.store import Store
from meshdesk.schema import new_message,to_dict
from meshdesk.simulator import LOCAL,PEER,RadioSimulator
from conftest import wait_for


@pytest.fixture
def c(qtapp,tmp_path):
    controller=Controller(Store(tmp_path/'test.sqlite'),demo=True)
    wait_for(qtapp,lambda:controller.sessions['simulator']['status']=='Connected')
    yield controller
    controller.close()


def finish(c,app):wait_for(app,lambda:not c.busy)
def action(c,operation,**args):c._dispatch(operation,args)
def load(c,app,section):
    action(c,'setting_load',section=section);finish(c,app)
    assert c.settings_message is not None,c.settings_error


def test_settings_drafts_save_all_discard_and_validation(c,qtapp):
    load(c,qtapp,'config.lora')
    action(c,'setting_edit',path='hop_limit',value='5')
    load(c,qtapp,'user');action(c,'setting_edit',path='long_name',value='New owner')
    assert set(c._pending_settings())=={'user','config.lora'}
    action(c,'setting_save_all');finish(c,qtapp)
    assert c.simulator.server.radio.config['lora'].hop_limit==5
    assert c.simulator.server.radio.nodes[0].user.long_name=='New owner'
    assert not c._pending_settings()
    with pytest.raises(ValueError,match='No staged'):action(c,'setting_save_all')
    load(c,qtapp,'config.lora')
    with pytest.raises(ValueError,match='Invalid'):action(c,'setting_edit',path='hop_limit',value='invalid')
    with pytest.raises(ValueError,match='invalid'):action(c,'setting_save')
    with pytest.raises(ValueError,match='invalid'):action(c,'setting_save_all')
    action(c,'setting_discard_all');assert not c.settings_error and not c._pending_settings()
    action(c,'setting_json',text='{"hop_limit":4,"region":"EU_868"}')
    assert c.settings_message.hop_limit==4
    action(c,'setting_load',section='config.lora',discard=True);finish(c,qtapp)
    assert c.settings_message.hop_limit==5
    action(c,'setting_save');finish(c,qtapp)
    c.settings_message=None;c.settings_original=None
    for name in ('setting_save','setting_edit'):
        with pytest.raises(ValueError,match='Load settings'):action(c,name,path='hop_limit',value=2)
    action(c,'setting_discard')


def test_identity_and_channel_keys_are_staged_only(c,qtapp):
    for name in ('generate_channel_key','generate_identity','print_identity'):
        with pytest.raises(ValueError):action(c,name)
    load(c,qtapp,'config.security')
    action(c,'generate_identity');first=c.settings_message.public_key
    assert len(first)==32 and not c.simulator.server.radio.config['security'].private_key
    action(c,'setting_edit',path='private_key',value=base64.b64encode(b'x'*32).decode())
    assert c.settings_message.public_key!=first
    action(c,'setting_edit',path='private_key',value='')
    load(c,qtapp,'channel.1')
    for bits,length in ((0,0),(8,1),(128,16),(256,32)):
        action(c,'generate_channel_key',bits=bits);assert len(c.settings_message.settings.psk)==length
    with pytest.raises(ValueError):action(c,'generate_channel_key',bits=64)
    assert c.simulator.server.radio.channels[1].settings.psk==b'\x01'


def test_message_history_filters_clipboard_and_local_clears(c,qtapp):
    action(c,'draft',text='draft');assert c.store.get('drafts')[c._chat_key()]=='draft'
    action(c,'send',text='hello');finish(c,qtapp)
    wait_for(qtapp,lambda:len(c.store.messages(c.active))==2)
    action(c,'search',text='hello');action(c,'older');assert c.message_offset==100
    action(c,'newer');action(c,'newer');assert c.message_offset==0
    action(c,'delete_message',id=c.store.messages(c.active)[0]['rowid']);assert len(c.store.messages(c.active))==1
    action(c,'delete_messages');assert not c.store.messages(c.active)
    c.store.message(c.active,1,PEER,LOCAL,0,'private')
    action(c,'chat',peer=PEER);action(c,'delete_messages');assert not c.store.messages(c.active,PEER)
    action(c,'clear_messages');action(c,'copy',text='Unicode 👋');assert QApplication.clipboard().text()=='Unicode 👋'
    for key,value in (('hops_min','2'),('name','test'),('hops_min','')):
        action(c,'node_filters',key=key,value=value)
    assert c.store.get('node_filters')=={'name':'test'}
    with pytest.raises(ValueError):action(c,'node_filters',key='snr_max',value='nan')
    action(c,'node_filters',reset=True);assert c.store.get('node_filters')=={}
    action(c,'clear_data');assert not c.store.nodes(c.active)
    action(c,'clear_all_data');assert not c.sessions and not c.active and c.store.get('drafts') is None
    with pytest.raises(ValueError):c._radio()


def test_received_packets_notifications_and_ack_expiry(c,qtapp):
    gen=c.sessions[c.active]['generation']
    def receive(kind,data):c._receive(c.active,gen,kind,data)
    action(c,'page',name='Nodes')
    receive('packet',{'id':10,'from':PEER,'to':LOCAL,'rxTime':1,'decoded':{'portnum':'TEXT_MESSAGE_APP','payload':base64.b64encode('received 👋'.encode()).decode()}})
    assert c.store.messages(c.active,PEER)[0]['text']=='received 👋'
    assert c.store.unread(c.active)
    for port,payload in [('POSITION_APP',{'position':{'latitudeI':520000000,'longitudeI':210000000}}),
        ('TRACEROUTE_APP',{'traceroute':{'route':[LOCAL+2],'routeBack':[LOCAL+2],'snrTowards':[24],'snrBack':[28]}}),
        ('TELEMETRY_APP',{'telemetry':{'batteryLevel':70}}),('WAYPOINT_APP',{'waypoint':{'id':42,'name':'Meet','latitudeI':520000000,'longitudeI':210000000}}),('WAYPOINT_APP',{})]:
        receive('packet',{'from':PEER,'to':LOCAL,'decoded':dict(portnum=port,**payload)})
    assert len(c.store.events(c.active))==5
    action(c,'waypoint_details',id=42);assert c.notification['waypoint']['distance_m']>0
    c._publish();assert json.loads(c.stateJson)['notification_view']['rows']
    action(c,'waypoint_details',id=999);assert not c.notification['waypoint']
    receive('log',{'message':'Radio log'});receive('notification',{})
    assert c.store.events(c.active)[0]['kind']=='notification'
    c._pending_acks={(c.active,i):'Acknowledged' for i in range(500)}
    receive('packet',{'decoded':{'portnum':'ROUTING_APP','requestId':501,'routing':{'errorReason':'NO_ROUTE'}}})
    assert len(c._pending_acks)==500 and c._pending_acks[(c.active,501)]=='Failed: NO_ROUTE'
    c.store.message(c.active,40,LOCAL,PEER,0,'lost',timestamp=time.time()-100,outgoing=True,status='Awaiting acknowledgement')
    c._tick();assert c.store.messages(c.active,PEER)[-1]['status']=='No acknowledgement'
    action(c,'page',name='Chat');action(c,'dismiss_notification');assert not c.notification
    for kind in ('POSITION_APP','TRACEROUTE_APP','TELEMETRY_APP','WAYPOINT_APP','other'):
        assert c._event_summary(kind,{'decoded':{}},{})


def test_profile_edit_default_reconfigure_and_probe(c,qtapp):
    sim=RadioSimulator()
    try:
        action(c,'probe',transport='tcp',address=sim.address);finish(c,qtapp)
        action(c,'add_profile',transport='tcp',address=sim.address,name='second');finish(c,qtapp)
        pid=c.active
        action(c,'default_profile',id=pid);assert c.store.get('default_profile')==pid
        with pytest.raises(ValueError):action(c,'default_profile',id='unknown')
        with pytest.raises(ValueError):action(c,'edit_profile',id=pid,address='')
        action(c,'edit_profile',id=pid,name='Renamed');finish(c,qtapp)
        assert c.sessions[pid]['profile']['name']=='Renamed'
        action(c,'edit_profile',id=pid,address=c.simulator.address);finish(c,qtapp)
        action(c,'reconfigure');finish(c,qtapp)
        assert c.sessions[pid]['status']=='Connected'
        action(c,'disconnect');action(c,'connect');finish(c,qtapp)
        action(c,'forget');assert pid not in c.sessions
        action(c,'demo');assert c.active=='simulator'
    finally:sim.close()


def test_async_errors_retry_and_device_scans(c,qtapp,monkeypatch):
    notices=[];c.toast.connect(notices.append)
    c._submit('test',lambda:1/0);finish(c,qtapp);assert 'division' in notices[-1]
    gen=c.sessions[c.active]['generation']
    c._receive(c.active,gen,'error',{'operation':'read:user','message':'Read failed'})
    assert c.settings_error=='Read failed' and not c.settings_loading
    c._receive(c.active,gen,'error',{'operation':'connect','message':'Disconnected'})
    assert c.sessions[c.active]['status']=='Reconnecting'
    c.sessions[c.active]['manual']=True
    c._receive(c.active,gen,'disconnected',{})
    monkeypatch.setattr('meshdesk.ble.NativeBLEInterface.scan',lambda:[SimpleNamespace(name=None,address='virtual')])
    action(c,'scan',transport='ble');finish(c,qtapp)
    assert c.notification['devices'][0]['name']=='virtual'
    monkeypatch.setattr('meshdesk.ble.pair_bluez',lambda address,pin:None)
    action(c,'ble_pair',address='virtual',pin='123456');finish(c,qtapp)
    assert 'pairing completed' in notices[-1]
    monkeypatch.setattr('meshdesk.upstream.latest_releases',lambda:[{'version':'test'}])
    action(c,'check_updates');finish(c,qtapp)
    assert c.notification['releases'][0]['version']=='test'
    c.dispatch('nonsense','{}');assert 'Unknown operation' in notices[-1]
    c.dispatch('send','bad json');assert notices
    with pytest.raises(ValueError):action(c,'add_profile',transport='fake',address='x')
    for key,value in [('unknown',True),('language','fake')]:
        with pytest.raises(ValueError):action(c,'preference',key=key,value=value)
    action(c,'preference',key='theme',value='system');assert c._theme() in ('dark','light')
    c._closing=True;c._tick();c._receive(c.active,gen,'connected',{})


def test_channel_import_targets_and_verification(c,qtapp):
    for indices in ([],[8],[-1]):
        with pytest.raises(ValueError):action(c,'export_channels',indices=indices)
    action(c,'export_channels',add=True);finish(c,qtapp)
    action(c,'import_preview',url=c.qr_url);assert c.import_preview[0]['target']==2 and not c.import_lora
    action(c,'import_target',index=0,target=3);assert c.import_preview[0]['target']==3
    with pytest.raises(ValueError):action(c,'import_target',index=99,target=9)
    action(c,'import_lora',value=True);assert c.import_lora
    with pytest.raises(ValueError):action(c,'verify_reply',number=123456)
    c.notification={'key_verification_number_request':{'nonce':123}}
    with pytest.raises(ValueError):action(c,'verify_reply',number=1000000)
    action(c,'verify_reply',number=123456);finish(c,qtapp)
    for accept in (True,False):
        c.notification={'key_verification_final':{'nonce':123}}
        action(c,'verify_reply',accept=accept);finish(c,qtapp)
    action(c,'command',name='canned_get');finish(c,qtapp);assert 'On my way' in c.notification['text']
    action(c,'command',name='remove_node',args={'value':PEER});finish(c,qtapp)
    assert not any(n['num']==PEER for n in c.store.nodes(c.active))


def test_export_import_files_and_identity_print(c,qtapp,tmp_path,monkeypatch):
    from meshdesk import controller as module
    path=tmp_path/'export.json'
    monkeypatch.setattr(module.QFileDialog,'getSaveFileName',lambda *a:(str(path),''))
    with pytest.raises(ValueError):action(c,'export',kind='settings')
    with pytest.raises(ValueError):action(c,'export',kind='qr')
    load(c,qtapp,'config.security');action(c,'generate_identity')
    for kind in ('settings','identity','nodes','activity','messages'):
        action(c,'export',kind=kind);assert json.loads(path.read_text()) is not None
        if __import__('os').name=='posix':assert path.stat().st_mode&0o777==0o600
    action(c,'export',kind='identity')
    monkeypatch.setattr(module.QFileDialog,'getOpenFileName',lambda *a:(str(path),''))
    action(c,'import_settings_file');assert c.settings_original==b'pending-import'
    action(c,'export_channels');finish(c,qtapp)
    action(c,'export',kind='qr');assert b'<svg' in path.read_bytes()
    monkeypatch.setattr(module.QFileDialog,'getSaveFileName',lambda *a:('',''))
    monkeypatch.setattr(module.QFileDialog,'getOpenFileName',lambda *a:('',''))
    action(c,'export',kind='nodes');action(c,'import_settings_file')
    from PyQt5 import QtPrintSupport,QtGui
    monkeypatch.setattr(QtPrintSupport.QPrintDialog,'exec_',lambda self:0)
    action(c,'print_identity')
    printed=[]
    monkeypatch.setattr(QtPrintSupport.QPrintDialog,'exec_',lambda self:1)
    monkeypatch.setattr(QtGui.QTextDocument,'print_',lambda self,p:printed.append(self.toPlainText()))
    action(c,'print_identity');assert 'Private key' in printed[0]
    action(c,'backup_reminder',days=0,open=True);finish(c,qtapp)
    assert c.store.get('backup_reminder:'+c.active)>time.time()


def test_default_connection_restored_on_start(qtapp,tmp_path):
    sim=RadioSimulator();store=Store(tmp_path/'default.sqlite')
    store.save_profile({'id':'saved','name':'Saved','transport':'tcp','address':sim.address})
    store.put('default_profile','saved');store.put('active','missing')
    c=Controller(store)
    try:
        wait_for(qtapp,lambda:c.sessions['saved']['status']=='Connected')
        assert c.active=='saved'
        assert c.messageBytes('👋')==4
    finally:c.close();sim.close()


def test_location_provider_success_timeout_and_absence(c,qtapp,monkeypatch):
    from PyQt5.QtCore import QObject,pyqtSignal
    import sys
    try:from PyQt5.QtPositioning import QGeoPositionInfoSource
    except ImportError:
        with pytest.raises(ValueError,match='Qt Positioning'):action(c,'locate_host')
    QGeoPositionInfoSource=SimpleNamespace(createDefaultSource=lambda parent:None)
    monkeypatch.setitem(sys.modules,'PyQt5.QtPositioning',SimpleNamespace(QGeoPositionInfoSource=QGeoPositionInfoSource))
    notices=[];c.toast.connect(notices.append)
    class Source(QObject):
        positionUpdated=pyqtSignal(object)
        updateTimeout=pyqtSignal()
        def requestUpdate(self,timeout):self.timeout=timeout
    monkeypatch.setattr(QGeoPositionInfoSource,'createDefaultSource',lambda parent:None)
    with pytest.raises(ValueError,match='no available'):action(c,'locate_host')
    source=Source();monkeypatch.setattr(QGeoPositionInfoSource,'createDefaultSource',lambda parent:source)
    action(c,'locate_host');assert source.timeout==15000
    source.updateTimeout.emit();assert 'No location fix' in notices[-1]
    source.positionUpdated.emit(SimpleNamespace(coordinate=lambda:SimpleNamespace(latitude=lambda:52.,longitude=lambda:21.)))
    assert c.notification['latitude']==52 and c.location_source is None
