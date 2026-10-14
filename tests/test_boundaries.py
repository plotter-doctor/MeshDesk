import base64
import io
import json
import math
from types import SimpleNamespace
import pytest
from PyQt5.QtCore import QModelIndex,Qt
from meshtastic.protobuf import admin_pb2,channel_pb2,mesh_pb2
from meshdesk.schema import new_message,set_field,validate_section,safe_data
from meshdesk.radio import Radio,HTTPInterface,decode_channel_url,encode_channel_url,plan_channel_import
from meshdesk.mapmath import signal_color,segment_distance,heat_weight
from meshdesk.mapview import coordinate
from meshdesk import nodes,forms,notifications,upstream
from meshdesk.models import FieldModel


@pytest.mark.parametrize('section,data',[
    ('user',{'long_name':'','short_name':'X'}),('user',{'long_name':'🙂'*10,'short_name':'X'}),
    ('channel.1',{'index':2}),('channel.0',{'role':0}),('channel.1',{'role':1}),
    ('channel.1',{'settings':{'name':'🙂'*3}}),('channel.1',{'settings':{'psk':base64.b64encode(b'xx').decode()}}),
    ('config.lora',{'hop_limit':8}),('config.lora',{'override_frequency':100}),
    ('config.security',{'private_key':'eA=='}),('config.security',{'admin_key':['eA==']}),
    ('config.security',{'admin_key':['']*4}),('config.security',{'is_managed':True})])
def test_validation_rejects_invalid_device_values(section,data):
    from google.protobuf.json_format import ParseDict
    message=new_message(section);ParseDict(data,message)
    with pytest.raises(ValueError):validate_section(section,message)


def test_field_validation_and_safe_diagnostics():
    with pytest.raises(ValueError):new_message('channel.8')
    security=new_message('config.security')
    for path,value in [('admin_key.3',''),('admin_key.0','eA==')]:
        with pytest.raises(ValueError):set_field(security,path,value)
    message=new_message('config.lora')
    set_field(message,'use_preset','true');assert message.use_preset
    set_field(message,'use_preset','false');assert not message.use_preset
    for path,value in [('use_preset','yes'),('region',9999),('override_frequency','nan')]:
        with pytest.raises(ValueError):set_field(message,path,value)
    assert safe_data(float('inf')) is None
    assert safe_data(mesh_pb2.User(long_name='Radio'))['long_name']=='Radio'
    assert coordinate({'position':{}}) is None
    for lat,lon in [(0,0),(91,0),(0,181),(math.nan,1),(1,math.inf)]:
        assert coordinate({'position':{'latitude':lat,'longitude':lon}}) is None


def test_presentation_boundaries():
    assert signal_color(-10)=='#ffe600' and signal_color(-20)=='#f7931a'
    assert signal_color(0,-127)=='#f7931a'
    assert segment_distance(1,1,0,0,0,0)==pytest.approx(math.sqrt(2))
    assert segment_distance(5,2,0,0,10,0)==2
    assert heat_weight(None,'snr')==0 and heat_weight(100,'snr')==1
    assert nodes.at({'a':1},'a.b') is None
    n={'num':1,'user':{},'hopsAway':0,'lastHeard':1,'snr':0}
    for filters in ({'name':'missing'},{'favorite':True},{'unheard':True},{'unknown_hops':True},{'battery_min':1},{'snr_max':-1},{'roles':'ROUTER'},{'hardware':'HELTEC_V3'}):
        assert not nodes.matches(n,filters)
    assert nodes.details(n) and nodes.details({'position':{'latitude':52,'longitude':21}}, {'num':2})
    assert nodes.sorted_nodes([{'num':1},{'num':2,'name':'A'}])[0]['num']==2
    model=FieldModel();model.sync([{'path':'x','value':1}])
    assert model.rowCount(model.index(0))==0
    assert model.data(QModelIndex(),model.ROLE) is None
    assert model.data(model.index(0),Qt.DisplayRole) is None
    assert not forms.disabled(SimpleNamespace(x='a'),{'conditions':[{'path':'x'}]})
    for x,invert,selector,disabled in [(True,True,0,True),(False,True,0,False),(1,False,0,False),(0,True,0,False),(1,True,0,True)]:
        assert forms.disabled(SimpleNamespace(x=x),{'conditions':[{'path':'x','invert':invert,'selector':selector}]})==disabled
    notice=notifications.present({'waypoint':{'id':1,'name':'Meeting','latitude_i':520000000,'longitude_i':210000000,'created':1,'updated':2,'expire':3,'locked_to':1,'sender':2,'distance_m':50,'bearing_degrees':90}})
    assert notice['title']=='Meeting' and len(notice['rows'])==9


def test_release_check_uses_pinned_tags(monkeypatch):
    calls=[]
    def open_url(request,timeout):
        calls.append(request.full_url);assert timeout==10
        return io.StringIO(json.dumps({'tag_name':'v999','html_url':'https://example.invalid/release'}))
    monkeypatch.setattr('urllib.request.urlopen',open_url)
    result=upstream.latest_releases()
    assert len(calls)==2 and all(r['update_available'] for r in result)


@pytest.mark.parametrize('url',['ftp://node','http://user:pass@node','http://'])
def test_http_rejects_invalid_or_credential_urls(url):
    with pytest.raises(ValueError):HTTPInterface(url)


@pytest.mark.parametrize('profile',[{'transport':'unknown','address':'x'},{'transport':'tcp','address':''}])
def test_invalid_connection_closes_resources(profile):
    radio=Radio(lambda *a:None)
    with pytest.raises(ValueError):radio.connect(profile)
    assert radio._closed and radio.interface is None
    radio._subscribe()
    with pytest.raises(RuntimeError):radio.connect(profile)


def test_radio_callback_routing_and_readback_failures(radio,monkeypatch):
    client,sim,events=radio;iface=client.interface
    for interface in (object(),iface):
        client._log('test',interface);client._notification({'message':'notice'},interface)
        client._node({'num':1},interface);client._lost(interface)
        client._packet({'from':0xa1000001,'decoded':{'neighborinfo':{'neighbors':[]}}},interface)
    assert any(k=='log' for k,v in events)
    assert iface.nodesByNum[0xa1000001]['neighborinfo']=={'neighbors':[]}
    with pytest.raises(ValueError):client.command('reboot',{'value':999999})
    with pytest.raises(ValueError):client.command('fixed_position',{'latitude':91,'longitude':1})
    with pytest.raises(ValueError):client.command('invalid',{})
    monkeypatch.setattr(client,'_admin',lambda *a,**k:admin_pb2.AdminMessage())
    with pytest.raises(RuntimeError,match='no settings'):client.read_section('user')
    answer=admin_pb2.AdminMessage();answer.get_config_response.device.SetInParent()
    monkeypatch.setattr(client,'_admin',lambda *a,**k:answer)
    with pytest.raises(RuntimeError,match='does not expose'):client.read_section('config.lora')
    monkeypatch.setattr(client,'read_section',lambda section:{'hop_limit':2})
    with pytest.raises(RuntimeError,match='readback differs'):client.write_section('config.lora',{'hop_limit':3})


def test_channel_url_and_import_rejections():
    for url in ('x'*8193,''):
        with pytest.raises(ValueError):decode_channel_url(url)
    with pytest.raises(ValueError):encode_channel_url([{'index':0,'role':'DISABLED'}],{})
    obj=decode_channel_url(encode_channel_url([{'index':0,'role':'PRIMARY','settings':{'name':'A'}},{'index':1,'role':'SECONDARY','settings':{'name':'B'}}],{}))
    for targets,replace in [([],False),([-1,-1],False),([0,0],False),([1,2],True),([0,8],False)]:
        with pytest.raises(ValueError):plan_channel_import(obj,targets,replace)
    assert len(plan_channel_import(obj,[0,-1],False,False))==1


@pytest.mark.parametrize('failure',['oversized','network'])
def test_http_stops_after_three_poll_failures(monkeypatch,failure):
    import threading
    from meshdesk import radio
    class Response:
        content=b'x'*65537
        def raise_for_status(self):
            if failure=='network':raise OSError('Unavailable')
    class Session:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def get(self,*a,**kw):return Response()
    instance=object.__new__(HTTPInterface)
    instance.stop=threading.Event();instance.url='http://fixture';instance.isConnected=threading.Event()
    disconnected=[];instance._disconnected=lambda:disconnected.append(True)
    monkeypatch.setattr(radio.requests,'Session',Session)
    monkeypatch.setattr(instance.stop,'wait',lambda delay:None)
    instance._poll()
    assert disconnected and isinstance(instance.failure,(OSError,ValueError))
