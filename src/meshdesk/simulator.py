"""Local-only protocol simulator. Uses the same protobuf framing as a real radio.

This is a deterministic integration fixture, not a firmware emulator. It does
not model LoRa delivery, encryption, power management or actual radio hardware.
"""
import argparse
import contextlib
import random
import os
import select
import socketserver
import threading
import time
from google.protobuf import json_format
from google.protobuf.message import DecodeError
from meshtastic.protobuf import admin_pb2, channel_pb2, config_pb2, module_config_pb2, mesh_pb2, portnums_pb2, telemetry_pb2

LOCAL = 0xA1000001
PEER = 0xA1000002


class RadioState:
    def __init__(self):
        self.lock = threading.RLock()
        self.config = {}
        self.module = {}
        for cls, target in ((config_pb2.Config,self.config),(module_config_pb2.ModuleConfig,self.module)):
            for field in cls.DESCRIPTOR.fields:
                if field.message_type:
                    target[field.name] = getattr(cls(), field.name)
        self.config['lora'].region = config_pb2.Config.LoRaConfig.EU_868
        self.config['lora'].use_preset = True
        self.config['lora'].hop_limit = 3
        self.config['lora'].tx_enabled = True
        self.config['bluetooth'].fixed_pin = 123456
        self.nodes = []
        for i, (name, short, lat, lon) in enumerate([
            ('Desk radio','DESK',52.2297,21.0122),('Riverside','RIVR',52.239,21.040),
            ('North lookout','NTH',52.265,21.004),('Garden relay','GARD',52.207,20.985)]):
            node=mesh_pb2.NodeInfo(num=LOCAL+i,last_heard=int(time.time()),snr=9.5-i*3)
            node.user.id=f'!{LOCAL+i:08x}'
            node.user.long_name=name
            node.user.short_name=short
            node.user.hw_model=mesh_pb2.HardwareModel.HELTEC_V3
            node.position.latitude_i=round(lat*1e7)
            node.position.longitude_i=round(lon*1e7)
            node.position.precision_bits=24
            node.device_metrics.battery_level=90-i*13
            self.nodes.append(node)
        self.channels = []
        for i in range(8):
            ch=channel_pb2.Channel(index=i,role=channel_pb2.Channel.PRIMARY if i==0 else channel_pb2.Channel.SECONDARY if i==1 else channel_pb2.Channel.DISABLED)
            if i<2:
                ch.settings.name=['LongFast','Friends'][i]
                ch.settings.psk=b'\x01'
            self.channels.append(ch)
        self.strings={'canned':'On my way|All clear|Need assistance','ringtone':'Mesh:d=4,o=5,b=100:c,e,g'}
        self.actions=[]

    def initial(self, config_id):
        result=[mesh_pb2.FromRadio(my_info=mesh_pb2.MyNodeInfo(my_node_num=LOCAL)),
                mesh_pb2.FromRadio(metadata=mesh_pb2.DeviceMetadata(firmware_version='2.7.11-simulator'))]
        result.extend(mesh_pb2.FromRadio(node_info=n) for n in self.nodes)
        for name,value in self.config.items():
            cfg=config_pb2.Config()
            getattr(cfg,name).CopyFrom(value)
            result.append(mesh_pb2.FromRadio(config=cfg))
        for name,value in self.module.items():
            cfg=module_config_pb2.ModuleConfig()
            getattr(cfg,name).CopyFrom(value)
            result.append(mesh_pb2.FromRadio(moduleConfig=cfg))
        result.extend(mesh_pb2.FromRadio(channel=c) for c in self.channels)
        result.append(mesh_pb2.FromRadio(config_complete_id=config_id))
        return result

    def response(self, request, payload, port, sender=LOCAL):
        packet=mesh_pb2.MeshPacket(id=random.randrange(1,0xffffffff),to=LOCAL,rx_time=int(time.time()),rx_snr=8.5,rx_rssi=-91,channel=request.channel)
        setattr(packet,'from',sender)
        packet.decoded.portnum=port
        packet.decoded.request_id=request.id
        packet.decoded.payload=payload.SerializeToString() if hasattr(payload,'SerializeToString') else payload
        return mesh_pb2.FromRadio(packet=packet)

    def handle(self, message):
        with self.lock:
            if message.want_config_id:
                return self.initial(message.want_config_id)
            if not message.HasField('packet'):
                return []
            p=message.packet
            port=p.decoded.portnum
            ack=self.response(p,mesh_pb2.Routing(error_reason=mesh_pb2.Routing.NONE),portnums_pb2.ROUTING_APP)
            if port==portnums_pb2.ADMIN_APP:
                req=admin_pb2.AdminMessage.FromString(p.decoded.payload)
                field=req.WhichOneof('payload_variant')
                self.actions.append(field)
                answer=admin_pb2.AdminMessage(session_passkey=b'simulator-session')
                if field=='get_config_request':
                    if req.get_config_request!=admin_pb2.AdminMessage.SESSIONKEY_CONFIG:
                        name=admin_pb2.AdminMessage.ConfigType.Name(req.get_config_request).removesuffix('_CONFIG').lower()
                        if name in self.config:
                            getattr(answer.get_config_response,name).CopyFrom(self.config[name])
                elif field=='get_module_config_request':
                    names=['mqtt','serial','external_notification','store_forward','range_test','telemetry','canned_message','audio','remote_hardware','neighbor_info','ambient_lighting','detection_sensor','paxcounter','statusmessage','traffic_management','tak']
                    name=names[req.get_module_config_request]
                    getattr(answer.get_module_config_response,name).CopyFrom(self.module[name])
                elif field=='get_channel_request':
                    answer.get_channel_response.CopyFrom(self.channels[req.get_channel_request-1])
                elif field=='get_owner_request':
                    answer.get_owner_response.CopyFrom(self.nodes[0].user)
                elif field=='get_ui_config_request':
                    answer.get_ui_config_response.CopyFrom(self.config['device_ui'])
                elif field=='store_ui_config':
                    self.config['device_ui'].CopyFrom(req.store_ui_config)
                elif field in ('set_config','set_module_config'):
                    cfg=getattr(req,field)
                    name=cfg.WhichOneof('payload_variant')
                    (self.config if field=='set_config' else self.module)[name].CopyFrom(getattr(cfg,name))
                elif field=='set_channel':
                    self.channels[req.set_channel.index].CopyFrom(req.set_channel)
                elif field=='set_owner':
                    self.nodes[0].user.CopyFrom(req.set_owner)
                elif field=='get_canned_message_module_messages_request':
                    answer.get_canned_message_module_messages_response=self.strings['canned']
                elif field=='get_ringtone_request':
                    answer.get_ringtone_response=self.strings['ringtone']
                elif field=='set_canned_message_module_messages':
                    self.strings['canned']=req.set_canned_message_module_messages
                elif field=='set_ringtone_message':
                    self.strings['ringtone']=req.set_ringtone_message
                elif field in ('set_favorite_node','remove_favorite_node','set_ignored_node','remove_ignored_node'):
                    for node in self.nodes:
                        if node.num==getattr(req,field):
                            setattr(node,'is_favorite' if 'favorite' in field else 'is_ignored',field.startswith('set_'))
                elif field=='remove_by_nodenum':
                    self.nodes=[n for n in self.nodes if n.num!=req.remove_by_nodenum]
                elif field=='set_fixed_position':
                    self.nodes[0].position.CopyFrom(req.set_fixed_position)
                elif field=='remove_fixed_position':
                    self.nodes[0].ClearField('position')
                elif field=='key_verification':
                    notice=mesh_pb2.ClientNotification(message='Simulator key verification event')
                    notice.key_verification_number_inform.security_number=123456
                    return [ack,mesh_pb2.FromRadio(clientNotification=notice)]
                return [ack,self.response(p,answer,portnums_pb2.ADMIN_APP)] if p.decoded.want_response else [ack]
            if port==portnums_pb2.TEXT_MESSAGE_APP:
                reply=self.response(p,b'Simulator: '+p.decoded.payload,portnums_pb2.TEXT_MESSAGE_APP,sender=PEER)
                reply.packet.to=p.to if p.to==0xffffffff else LOCAL
                reply.packet.decoded.reply_id=p.id
                return [ack,reply]
            if port==portnums_pb2.POSITION_APP:
                return [ack,self.response(p,self.nodes[1].position,port,sender=p.to)]
            if port==portnums_pb2.TRACEROUTE_APP:
                return [ack,self.response(p,mesh_pb2.RouteDiscovery(route=[LOCAL+2],snr_towards=[24,32],route_back=[LOCAL+2],snr_back=[28,36]),port,sender=p.to)]
            if port==portnums_pb2.TELEMETRY_APP:
                request = telemetry_pb2.Telemetry.FromString(p.decoded.payload)
                if not request.HasField('device_metrics'):
                    return [ack]
                t=telemetry_pb2.Telemetry(time=int(time.time()))
                t.device_metrics.battery_level=77
                t.device_metrics.voltage=3.95
                return [ack,self.response(p,t,port,sender=p.to)]
            if port==portnums_pb2.WAYPOINT_APP:
                return [ack,self.response(p,p.decoded.payload,port,sender=PEER)]
            return [ack]


def frame(message):
    raw=message.SerializeToString()
    return b'\x94\xc3'+len(raw).to_bytes(2,'big')+raw


class FrameDecoder:
    """Incremental serial/TCP decoder, including firmware console noise."""
    def __init__(self):
        self.buffer=bytearray()

    def feed(self,chunk):
        self.buffer.extend(chunk)
        result=[]
        while len(self.buffer)>=4:
            index=self.buffer.find(b'\x94\xc3')
            if index<0:
                self.buffer[:]=self.buffer[-1:]
                break
            del self.buffer[:index]
            if len(self.buffer)<4:break
            size=int.from_bytes(self.buffer[2:4],'big')
            if size>4096:
                del self.buffer[:2]
                continue
            if len(self.buffer)<size+4:break
            raw=bytes(self.buffer[4:4+size]);del self.buffer[:4+size]
            try:result.append(mesh_pb2.ToRadio.FromString(raw))
            except DecodeError:continue
        return result


class SerialSimulator:
    """A real POSIX serial endpoint usable by MeshDesk or the official CLI.

    fragment_size/delay exercise partial reads. Keeping the slave open allows
    clients to disconnect and reconnect to the same simulated radio state.
    """
    def __init__(self,state=None,fragment_size=0,delay=0):
        import pty,tty
        self.state=state or RadioState()
        self.fragment_size=fragment_size;self.delay=delay
        self.master,self.slave=pty.openpty();tty.setraw(self.slave)
        self.address=os.ttyname(self.slave)
        self.stop=threading.Event();self.errors=[]
        self.thread=threading.Thread(target=self._serve,daemon=True,name='mesh-serial-simulator')
        self.thread.start()

    def _serve(self):
        decoder=FrameDecoder()
        try:
            while not self.stop.is_set():
                if not select.select([self.master],[],[],.05)[0]:continue
                for message in decoder.feed(os.read(self.master,4096)):
                    for response in self.state.handle(message):
                        raw=frame(response);size=self.fragment_size or len(raw)
                        for offset in range(0,len(raw),size):
                            pending=memoryview(raw[offset:offset+size])
                            while pending:pending=pending[os.write(self.master,pending):]
                            if self.delay:self.stop.wait(self.delay)
        except OSError as error:
            if not self.stop.is_set():self.errors.append(error)

    def close(self):
        if self.stop.is_set():return
        self.stop.set();self.thread.join(2)
        os.close(self.master);os.close(self.slave)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        decoder=FrameDecoder()
        while True:
            try:
                chunk=self.request.recv(4096)
                if not chunk:
                    return
                for msg in decoder.feed(chunk):
                    for response in self.server.radio.handle(msg):
                        self.request.sendall(frame(response))
            except (ConnectionError,OSError):
                return


class RadioSimulator:
    def __init__(self, port=0):
        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address=True
            daemon_threads=True
        self.server=Server(('127.0.0.1',port),Handler)
        self.server.radio=RadioState()
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True,name='mesh-simulator')
        self.thread.start()

    @property
    def address(self):
        return '127.0.0.1:'+str(self.server.server_address[1])

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=4403)
    parser.add_argument('--transport',choices=['tcp','serial'],default='tcp')
    parser.add_argument('--fragment-size',type=int,default=0,help='Serial response chunk size')
    parser.add_argument('--delay',type=float,default=0,help='Delay between serial chunks in seconds')
    parser.add_argument('--duration',type=float,help='Stop after this many seconds')
    args=parser.parse_args()
    if args.fragment_size<0 or args.delay<0:parser.error('Fragment size and delay cannot be negative')
    sim=SerialSimulator(fragment_size=args.fragment_size,delay=args.delay) if args.transport=='serial' else RadioSimulator(args.port)
    print('Meshtastic simulator listening at '+sim.address,flush=True)
    try:
        if args.duration is not None:time.sleep(args.duration)
        else:
            while True:time.sleep(60)
    except KeyboardInterrupt:
        pass
    finally:sim.close()


if __name__=='__main__':
    main()
