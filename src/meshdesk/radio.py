"""Only this module depends on Meshtastic interface internals.

Transport callbacks never touch Qt or SQLite. All radio writes are explicit user
operations. Admin writes wait for routing acknowledgement and settings readback.
"""
import base64
import contextlib
import socket
import threading
import time
from urllib.parse import urlsplit
import requests
from google.protobuf import json_format
from meshtastic.mesh_interface import MeshInterface
from meshtastic.protobuf import admin_pb2, apponly_pb2, channel_pb2, mesh_pb2, portnums_pb2, telemetry_pb2
from pubsub import pub
from .schema import new_message, safe_data, to_dict, validate_section


class HTTPInterface(MeshInterface):
    """Official HTTP wire endpoints, with decoding delegated to the Python SDK."""
    def __init__(self, url, timeout=15):
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Use an http:// or https:// device URL without credentials')
        self.url = url.rstrip('/')
        self.stop = threading.Event()
        self.session = requests.Session()
        self.session.trust_env = False
        self.write_lock = threading.Lock()
        super().__init__(timeout=timeout)
        self.reader = threading.Thread(target=self._poll, daemon=True, name='mesh-http')
        try:
            self._startConfig()
            self.reader.start()
            self._waitConnected(timeout)
        except Exception:
            self.close()
            raise

    def _poll(self):
        failures = 0
        while not self.stop.is_set():
            try:
                # Separate session from writers; requests.Session is not thread-safe.
                with requests.Session() as reader:
                    reader.trust_env = False
                    for _ in range(256):
                        if self.stop.is_set():
                            return
                        r = reader.get(self.url+'/api/v1/fromradio?all=false', headers={'Accept':'application/x-protobuf'}, timeout=(3,7))
                        r.raise_for_status()
                        if not r.content:
                            break
                        if len(r.content) > 65536:
                            raise ValueError('Oversized radio response')
                        self._handleFromRadio(r.content)
                failures = 0
            except Exception as error:
                failures += 1
                if failures >= 3:
                    self.failure = error
                    self._disconnected()
                    return
            self.stop.wait(0.4 if not self.isConnected.is_set() else 1.0)

    def _sendToRadioImpl(self, message):
        with self.write_lock:
            response = self.session.put(self.url+'/api/v1/toradio', data=message.SerializeToString(),
                                        headers={'Content-Type':'application/x-protobuf'}, timeout=(3,5))
            response.raise_for_status()

    def close(self):
        with contextlib.suppress(Exception):
            super().close()
        self.stop.set()
        if hasattr(self, 'reader') and self.reader.is_alive() and threading.current_thread() is not self.reader:
            self.reader.join(8)
        self.session.close()


class Radio:
    def __init__(self, emit, timeout=15):
        self.emit = emit
        self.timeout = timeout
        self.interface = None
        self._subscriptions = []
        self._closed = False
        self.lock = threading.RLock()

    def connect(self, profile):
        if self._closed:raise RuntimeError('Connection cancelled')
        transport, address = profile['transport'], profile['address']
        try:
            if transport == 'serial':
                from meshtastic.serial_interface import SerialInterface
                self.interface = SerialInterface(devPath=address, connectNow=False, timeout=self.timeout)
                self._subscribe()
                self.interface.connect()
            elif transport in ('tcp','simulator'):
                from meshtastic.tcp_interface import TCPInterface
                parsed = urlsplit('tcp://'+address)
                if not parsed.hostname:
                    raise ValueError('Enter a hostname and optional port')
                self.interface = TCPInterface(parsed.hostname, portNumber=parsed.port or 4403, connectNow=False, timeout=self.timeout)
                self._subscribe()
                # Upstream myConnect has no socket timeout: bound connection setup here.
                self.interface.socket = socket.create_connection((parsed.hostname, parsed.port or 4403), timeout=8)
                self.interface.socket.settimeout(None)
                from meshtastic.stream_interface import StreamInterface
                StreamInterface.connect(self.interface)
            elif transport == 'http':
                self.interface = HTTPInterface(address, self.timeout)
                self._subscribe()
            elif transport == 'ble':
                from .ble import NativeBLEInterface
                if address.startswith('simble:'):
                    from .virtualble import PERIPHERALS
                    self.interface=PERIPHERALS[address].interface(self.timeout)
                else:self.interface = NativeBLEInterface(address=address or None, timeout=self.timeout)
                self._subscribe()
            else:
                raise ValueError('Unknown connection type')
            if self._closed:raise RuntimeError('Connection cancelled')
            self.emit('snapshot', self.snapshot())
            self.emit('connected', {})
        except BaseException:
            self.close()
            raise

    def _subscribe(self):
        if self._closed:return
        callbacks = [(self._packet, 'meshtastic.receive'), (self._node, 'meshtastic.node.updated'),
                     (self._lost, 'meshtastic.connection.lost'), (self._log, 'meshtastic.log.line'),
                     (self._notification, 'meshtastic.clientNotification')]
        for callback, topic in callbacks:
            pub.subscribe(callback, topic)
            self._subscriptions.append((callback, topic))

    def _packet(self, packet, interface):
        if interface is self.interface and not self._closed:
            self.emit('packet', safe_data(packet))
            num = packet.get('from')
            node = (interface.nodesByNum or {}).get(num)
            if node:
                decoded=packet.get('decoded',{})
                if 'neighborinfo' in decoded:node['neighborinfo']=safe_data(decoded['neighborinfo'])
                self.emit('node', safe_data(node))

    def _node(self, node, interface):
        if interface is self.interface and not self._closed:
            self.emit('node', safe_data(node))

    def _lost(self, interface):
        if interface is self.interface and not self._closed:
            self.emit('disconnected', {})

    def _log(self, line, interface):
        if interface is self.interface and not self._closed:
            self.emit('log', {'message':line})

    def _notification(self, notification, interface):
        if interface is self.interface and not self._closed:
            self.emit('notification', safe_data(notification))

    def snapshot(self):
        iface = self.interface
        local = iface.localNode
        return {'my_num': iface.myInfo.my_node_num, 'metadata': to_dict(iface.metadata) if iface.metadata else {},
                'nodes':safe_data(list((iface.nodesByNum or {}).values())),
                'config':to_dict(local.localConfig, True),'module':to_dict(local.moduleConfig, True),
                'channels':[to_dict(c, True) for c in (local.channels or [])]}

    def send_text(self, text, destination=4294967295, channel=0, reply=0):
        if not text.strip() or len(text.encode('utf-8')) > 233:
            raise ValueError('A message must contain 1–233 UTF-8 bytes')
        timestamp=time.time()
        packet = self.interface.sendText(text, destinationId=int(destination), channelIndex=int(channel),
                                         wantAck=True, replyId=int(reply) or None)
        return {'packet_id':packet.id, 'sender':self.interface.myInfo.my_node_num, 'destination':int(destination),
                'channel':int(channel), 'text':text, 'reply_id':int(reply),'timestamp':timestamp}

    def _admin(self, message, response=False, session=True):
        iface = self.interface
        if session:
            node = (iface.nodesByNum or {}).get(iface.localNode.nodeNum, {})
            if not node.get('adminSessionPassKey'):
                self._admin(admin_pb2.AdminMessage(get_config_request=admin_pb2.AdminMessage.SESSIONKEY_CONFIG),
                            response=True, session=False)
        result = []
        done = threading.Event()
        def onAckNak(packet):
            decoded = packet.get('decoded', {})
            if decoded.get('portnum') == 'ROUTING_APP':
                error = decoded.get('routing', {}).get('errorReason', 'NONE')
                if error not in ('NONE', 0):
                    result.append(RuntimeError('Radio rejected request: '+str(error)))
                    done.set()
                elif not response:
                    result.append(None)
                    done.set()
            elif decoded.get('portnum') == 'ADMIN_APP':
                answer = admin_pb2.AdminMessage()
                answer.ParseFromString(decoded['payload'])
                result.append(answer)
                done.set()
        # The SDK removes an ACK-accepting callback after the ACK. Reads must
        # retain their callback until the actual ADMIN response (or a NAK).
        if response:onAckNak.__name__='onAdminResponse'
        packet = iface.localNode._sendAdmin(message, wantResponse=response, onResponse=onAckNak)
        if not done.wait(self.timeout):
            if packet:
                iface.responseHandlers.pop(packet.id, None)
            raise TimeoutError('Radio did not acknowledge the request; its outcome is unknown. Refresh before retrying.')
        if isinstance(result[0], Exception):
            raise result[0]
        return result[0]

    def read_section(self, section):
        request = admin_pb2.AdminMessage()
        if section == 'user':
            request.get_owner_request = True
            attr = 'get_owner_response'
        elif section == 'config.device_ui':
            request.get_ui_config_request = True
            attr = 'get_ui_config_response'
        elif section.startswith('channel.'):
            request.get_channel_request = int(section.split('.')[1]) + 1
            attr = 'get_channel_response'
        else:
            group, name = section.split('.')
            if group == 'config':
                request.get_config_request = admin_pb2.AdminMessage.ConfigType.Value(name.upper()+'_CONFIG')
                attr = 'get_config_response'
            else:
                aliases = {'external_notification':'EXTNOTIF','store_forward':'STOREFORWARD','range_test':'RANGETEST','canned_message':'CANNEDMSG'}
                enum = aliases.get(name, name.replace('_','').upper())+'_CONFIG'
                request.get_module_config_request = admin_pb2.AdminMessage.ModuleConfigType.Value(enum)
                attr = 'get_module_config_response'
        answer = self._admin(request, response=True, session=False)
        if not answer or not answer.HasField(attr):
            raise RuntimeError('Device returned no settings for '+section)
        value = getattr(answer, attr)
        if section.startswith(('config.','module.')) and section != 'config.device_ui':
            name = section.split('.')[1]
            if not value.HasField(name):
                raise RuntimeError('This firmware does not expose '+section)
            value = getattr(value, name)
        return to_dict(value, True)

    def write_section(self, section, data):
        message = new_message(section)
        json_format.ParseDict(data, message)
        validate_section(section, message)
        request = admin_pb2.AdminMessage()
        if section == 'user':
            request.set_owner.CopyFrom(message)
        elif section == 'config.device_ui':
            request.store_ui_config.CopyFrom(message)
        elif section.startswith('channel.'):
            request.set_channel.CopyFrom(message)
        else:
            group, name = section.split('.')
            getattr(getattr(request, 'set_config' if group == 'config' else 'set_module_config'), name).CopyFrom(message)
        self._admin(request)
        actual = self.read_section(section)
        # Compare normalized protobuf values, including defaults and bytes.
        readback = new_message(section)
        json_format.ParseDict(actual, readback)
        if message != readback:
            raise RuntimeError('Radio acknowledged the write but readback differs. Reload settings to inspect the device values.')
        return actual

    def write_sections(self,values):
        # Firmware defers settings-triggered reboots until commit. Validate all
        # drafts first; retain them in the UI if any write or commit fails.
        for section,data in values.items():
            message=new_message(section);json_format.ParseDict(data,message);validate_section(section,message)
        with self.lock:
            self._admin(admin_pb2.AdminMessage(begin_edit_settings=True))
            try:
                actual={section:self.write_section(section,data) for section,data in values.items()}
            finally:
                self._admin(admin_pb2.AdminMessage(commit_edit_settings=True))
            return actual

    def command(self, name, args):
        request = admin_pb2.AdminMessage()
        simple = {'reboot':'reboot_seconds','reboot_ota':'reboot_ota_seconds','shutdown':'shutdown_seconds','dfu':'enter_dfu_mode_request',
                  'reset_nodes':'nodedb_reset','reset_config':'factory_reset_config','reset_device':'factory_reset_device',
                  'favorite':'set_favorite_node','unfavorite':'remove_favorite_node','ignore':'set_ignored_node',
                  'unignore':'remove_ignored_node','remove_node':'remove_by_nodenum','remove_position':'remove_fixed_position',
                  'set_time':'set_time_only','canned_set':'set_canned_message_module_messages','ringtone_set':'set_ringtone_message'}
        if name in simple:
            value = args.get('value', 1)
            if name in ('dfu','remove_position'):
                value = True
            if name == 'set_time':
                value = int(time.time())
            if name in ('reboot','reboot_ota','shutdown') and not -1 <= int(value) <= 86400:
                raise ValueError('Delay must be 0–86400 seconds, or -1 to cancel')
            setattr(request, simple[name], value)
            self._admin(request)
            result={'message':'Radio acknowledged '+name.replace('_',' ')}
            if name in ('favorite','unfavorite','ignore','unignore','remove_node'):
                result['node_change']={'num':int(value),'remove':name=='remove_node','patch':
                    {'isFavorite':name=='favorite'} if 'favorite' in name else {'isIgnored':name=='ignore'}}
            return result
        if name in ('position','traceroute','telemetry'):
            dest = int(args['node'])
            obj, port = {'position':(mesh_pb2.Position(),portnums_pb2.POSITION_APP),
                         'traceroute':(mesh_pb2.RouteDiscovery(),portnums_pb2.TRACEROUTE_APP),
                         'telemetry':(telemetry_pb2.Telemetry(),portnums_pb2.TELEMETRY_APP)}[name]
            if name == 'telemetry':
                # Firmware selects the reply by the telemetry oneof. An empty
                # Telemetry envelope has no type and gets no metrics response.
                obj.device_metrics.SetInParent()
            packet = self.interface.sendData(obj, destinationId=dest, portNum=port, wantAck=True, wantResponse=True)
            return {'message':'Request sent; the response will appear in activity and node details',
                    'packet_id':packet.id}
        if name == 'fixed_position':
            lat, lon = float(args['latitude']), float(args['longitude'])
            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError('Invalid latitude or longitude')
            request.set_fixed_position.latitude_i = round(lat*1e7)
            request.set_fixed_position.longitude_i = round(lon*1e7)
            request.set_fixed_position.altitude = int(args.get('altitude',0))
            self._admin(request)
        elif name in ('canned_get','ringtone_get'):
            attr = 'get_canned_message_module_messages' if name == 'canned_get' else 'get_ringtone'
            setattr(request, attr+'_request', True)
            answer = self._admin(request, response=True)
            return {'text':getattr(answer, attr+'_response')}
        elif name == 'verify_key':
            request.key_verification.message_type = int(args.get('type',0))
            request.key_verification.remote_nodenum = int(args.get('node',0))
            request.key_verification.nonce = int(args.get('nonce',0))
            request.key_verification.security_number = int(args.get('number',0))
            self._admin(request)
        elif name == 'waypoint':
            wp = mesh_pb2.Waypoint()
            json_format.ParseDict(args['waypoint'], wp)
            self.interface.sendData(wp, portNum=portnums_pb2.WAYPOINT_APP, channelIndex=int(args.get('channel',0)), wantAck=True)
        else:
            raise ValueError('Unknown action: '+name)
        return {'message':'Request acknowledged' if name != 'waypoint' else 'Waypoint sent'}

    def close(self):
        self._closed = True
        for callback, topic in self._subscriptions:
            pub.unsubscribe(callback, topic)
        self._subscriptions.clear()
        if self.interface:
            with contextlib.suppress(Exception):
                self.interface.close()
            self.interface = None


def decode_channel_url(url):
    raw = url.strip().split('#')[-1]
    if len(raw) > 8192:
        raise ValueError('Channel URL is too long')
    channel_set = apponly_pb2.ChannelSet()
    channel_set.ParseFromString(base64.b64decode(raw+'='*((-len(raw))%4), altchars=b'-_', validate=True))
    if not 1 <= len(channel_set.settings) <= 8:
        raise ValueError('Channel URL must contain 1–8 channels')
    return channel_set


def encode_channel_url(channels, lora, add=False):
    from meshtastic.protobuf import config_pb2
    obj = apponly_pb2.ChannelSet()
    for channel in channels:
        ch=channel_pb2.Channel()
        json_format.ParseDict(channel,ch)
        if ch.role in (channel_pb2.Channel.PRIMARY,channel_pb2.Channel.SECONDARY):
            obj.settings.add().CopyFrom(ch.settings)
    json_format.ParseDict(lora,obj.lora_config)
    if not obj.settings:raise ValueError('Selected channels are disabled')
    return ('https://meshtastic.org/e/?add=true#' if add else 'https://meshtastic.org/e/#')+base64.urlsafe_b64encode(obj.SerializeToString()).decode().rstrip('=')


def plan_channel_import(channel_set,targets,replace=False,update_lora=True):
    """Validate the entire proposed import before writing any radio settings."""
    if len(targets)!=len(channel_set.settings):raise ValueError('Choose a target for every channel')
    selected=[int(i) for i in targets if i!=-1]
    if not selected or any(i<0 or i>7 for i in selected):raise ValueError('Select at least one target channel, from 0 to 7')
    if len(selected)!=len(set(selected)):raise ValueError('Two imported channels cannot use the same target slot')
    if replace and 0 not in selected:raise ValueError('A replacement must include the primary channel')
    plan=[]
    for settings,index in zip(channel_set.settings,targets):
        if index==-1:continue
        channel=channel_pb2.Channel(index=index,role=channel_pb2.Channel.PRIMARY if index==0 else channel_pb2.Channel.SECONDARY)
        channel.settings.CopyFrom(settings);plan.append((f'channel.{index}',channel))
    if replace:
        plan.extend((f'channel.{i}',channel_pb2.Channel(index=i,role=channel_pb2.Channel.DISABLED)) for i in range(1,8) if i not in selected)
    if update_lora and channel_set.HasField('lora_config'):plan.append(('config.lora',channel_set.lora_config))
    for section,payload in plan:validate_section(section,payload)
    return plan
