import base64
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest
from meshtastic.protobuf import mesh_pb2
from meshdesk.radio import Radio,decode_channel_url,encode_channel_url
from meshdesk.schema import sections,fields,new_message,set_field,safe_data
from meshdesk.simulator import RadioState,PEER


@pytest.mark.parametrize('section',[s['key'] for s in sections()])
def test_settings_roundtrip(radio,section):
    client,sim,events=radio
    before=client.read_section(section)
    assert client.write_section(section,before)==before
    assert any(a in sim.server.radio.actions for a in ('set_owner','set_channel','set_config','set_module_config','store_ui_config'))


def test_messages_and_reply_ack(radio):
    client,_,events=radio
    for destination in (0xffffffff,PEER):
        sent=client.send_text('Hello, mesh 👋',destination,reply=123)
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and not any(k=='packet' and v.get('decoded',{}).get('replyId')==sent['packet_id'] for k,v in events):time.sleep(.01)
        assert any(k=='packet' and v.get('decoded',{}).get('replyId')==sent['packet_id'] for k,v in events)
        assert any(k=='packet' and v.get('decoded',{}).get('requestId')==sent['packet_id'] and v['decoded']['portnum']=='ROUTING_APP' for k,v in events)
    with pytest.raises(ValueError):client.send_text('🙂'*59)


def test_telemetry_request_gets_correlated_device_metrics(radio):
    client, _, events = radio
    result = client.command('telemetry', {'node': PEER})
    deadline = time.monotonic() + 3
    def response():
        return next((p for kind, p in events if kind == 'packet' and p.get('from') == PEER
                     and p.get('decoded', {}).get('requestId') == result['packet_id']
                     and p['decoded'].get('portnum') == 'TELEMETRY_APP'), None)
    while time.monotonic() < deadline and response() is None:
        time.sleep(.01)
    assert response() is not None
    assert response()['decoded']['telemetry']['deviceMetrics']['batteryLevel'] == 77


def test_channel_link(radio):
    client,_,_=radio
    channels=[client.read_section('channel.'+str(i)) for i in range(8)]
    obj=decode_channel_url(encode_channel_url(channels,client.read_section('config.lora')))
    assert len(obj.settings)==2
    assert obj.settings[1].name=='Friends'
    assert obj.lora_config.hop_limit==3
    with pytest.raises(Exception):decode_channel_url('https://meshtastic.org/e/#not-protobuf')


@pytest.mark.parametrize('name,args',[
    ('favorite',{'value':PEER}),('unfavorite',{'value':PEER}),('ignore',{'value':PEER}),('unignore',{'value':PEER}),
    ('position',{'node':PEER}),('traceroute',{'node':PEER}),('telemetry',{'node':PEER}),
    ('fixed_position',{'latitude':52,'longitude':21}),('remove_position',{}),
    ('canned_set',{'value':'One|Two'}),('canned_get',{}),('ringtone_set',{'value':'test:d=4,o=5,b=100:c'}),('ringtone_get',{}),
    ('verify_key',{'node':PEER}),('set_time',{}),('reboot',{'value':10}),('reboot',{'value':-1}),('reboot_ota',{'value':10}),('reboot_ota',{'value':-1}),('shutdown',{'value':10}),
    ('dfu',{}),('reset_nodes',{}),('reset_config',{}),('reset_device',{}),('remove_node',{'value':PEER}),
    ('waypoint',{'waypoint':{'id':123,'name':'Meeting','latitude_i':520000000,'longitude_i':210000000}})
])
def test_commands(radio,name,args):
    client,_,_=radio
    result=client.command(name,args)
    assert 'message' in result or 'text' in result


def test_rejected_and_missing_ack(radio):
    client,sim,_=radio
    client.read_section('config.lora')
    original=sim.server.radio.handle
    def reject(message):
        if message.HasField('packet'):
            return [sim.server.radio.response(message.packet,mesh_pb2.Routing(error_reason=mesh_pb2.Routing.NOT_AUTHORIZED),5)]
        return original(message)
    sim.server.radio.handle=reject
    with pytest.raises(RuntimeError,match='NOT_AUTHORIZED'):client.command('reboot',{'value':1})
    sim.server.radio.handle=lambda message:[]
    client.timeout=.1
    with pytest.raises(TimeoutError,match='unknown'):client.command('reboot',{'value':1})


def test_http_transport():
    state=RadioState();outbound=queue.Queue()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_PUT(self):
            assert self.path=='/api/v1/toradio'
            message=mesh_pb2.ToRadio.FromString(self.rfile.read(int(self.headers['Content-Length'])))
            for reply in state.handle(message):outbound.put(reply.SerializeToString())
            self.send_response(200);self.end_headers()
        def do_GET(self):
            assert self.path=='/api/v1/fromradio?all=false'
            try:body=outbound.get_nowait()
            except queue.Empty:body=b''
            self.send_response(200);self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    client=Radio(lambda *args:None,timeout=4)
    try:
        client.connect({'transport':'http','address':'http://127.0.0.1:'+str(server.server_port)})
        assert client.snapshot()['my_num']==0xa1000001
        assert client.read_section('config.lora')['hop_limit']==3
        assert client.send_text('HTTP')['packet_id']
    finally:
        client.close();server.shutdown();server.server_close()


def test_schema_types_and_secrets():
    security=new_message('config.security')
    set_field(security,'private_key',base64.b64encode(b'x'*32).decode())
    assert len(security.private_key)==32
    with pytest.raises(Exception):set_field(security,'private_key','invalid')
    assert safe_data({'adminSessionPassKey':b'secret','raw':'raw','ok':1})=={'ok':1}
    for section in sections():
        obj=new_message(section['key'])
        for field in fields(obj):
            set_field(obj,field['path'],field['value'])
