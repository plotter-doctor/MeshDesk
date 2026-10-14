"""In-process Meshtastic GATT peripheral through Bleak's backend API.

Exercises the official SDK's BLE receiver, notifications and writes without an
adapter. This does not emulate an OS Bluetooth controller, pairing or RF.
"""
import asyncio
from collections import deque
import struct
import uuid
from bleak.backends.client import BaseBleakClient
from bleak.backends.device import BLEDevice
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.service import BleakGATTService, BleakGATTServiceCollection
from bleak.exc import BleakError
from meshtastic.ble_interface import SERVICE_UUID,TORADIO_UUID,FROMRADIO_UUID,FROMNUM_UUID
from meshtastic.protobuf import mesh_pb2
from .ble import BoundedBLEClient,NativeBLEInterface
from .simulator import RadioState

PERIPHERALS={}


class VirtualBLESimulator:
    def __init__(self,state=None):
        self.state=state or RadioState()
        self.address='simble:'+uuid.uuid4().hex
        self.device=BLEDevice(self.address,'MeshDesk virtual BLE',self)
        self.clients=[];self.delay=0;self.read_delay=0;self.drop_responses=False;self.write_error=False
        PERIPHERALS[self.address]=self

    def interface(self,timeout=3):
        def client(device,**kwargs):
            return BoundedBLEClient(device,backend=VirtualGattBackend,**kwargs)
        return NativeBLEInterface(self.address,timeout,device=self.device,client_factory=client)

    def close(self):
        PERIPHERALS.pop(self.address,None)
        for client in self.clients:
            if client.is_connected:client.loop.call_soon_threadsafe(client.drop)


class VirtualGattBackend(BaseBleakClient):
    def __init__(self,device,**kwargs):
        super().__init__(device,**kwargs)
        self.peripheral=device.details
        self.peripheral.clients.append(self)
        self.connected=False;self.paired=False;self.queue=deque();self.callbacks={};self.number=0
        self.services=BleakGATTServiceCollection()
        service=BleakGATTService(None,1,SERVICE_UUID);self.services.add_service(service)
        for handle,uid,props in ((2,TORADIO_UUID,['write']),(3,FROMRADIO_UUID,['read']),(4,FROMNUM_UUID,['notify','read'])):
            self.services.add_characteristic(BleakGATTCharacteristic(None,handle,uid,props,lambda:512,service))

    @property
    def name(self):return self.peripheral.device.name
    @property
    def mtu_size(self):return 512
    @property
    def is_connected(self):return self.connected

    async def connect(self,pair=False,**kwargs):
        self.loop=asyncio.get_running_loop();self.connected=True
        if pair:await self.pair()

    async def disconnect(self):
        self.connected=False;self.queue.clear();self.callbacks.clear()

    def drop(self):
        self.connected=False
        if self._disconnected_callback:self._disconnected_callback()

    async def pair(self,*args,**kwargs):self.paired=True
    async def unpair(self):self.paired=False;await self.disconnect()

    async def _ready(self):
        if self.peripheral.delay:await asyncio.sleep(self.peripheral.delay)
        if not self.connected:raise BleakError('Not connected')

    async def read_gatt_char(self,characteristic,**kwargs):
        await self._ready()
        if self.peripheral.read_delay:await asyncio.sleep(self.peripheral.read_delay)
        if characteristic.uuid==FROMNUM_UUID:return bytearray(struct.pack('<I',self.number))
        if characteristic.uuid!=FROMRADIO_UUID:raise BleakError('Characteristic is not readable')
        return bytearray(self.queue.popleft() if self.queue else b'')

    async def write_gatt_char(self,characteristic,data,response):
        await self._ready()
        if characteristic.uuid!=TORADIO_UUID or self.peripheral.write_error:raise BleakError('GATT write rejected')
        replies=self.peripheral.state.handle(mesh_pb2.ToRadio.FromString(bytes(data)))
        if self.peripheral.drop_responses:return
        self.queue.extend(item.SerializeToString() for item in replies)
        self.number+=len(replies)
        if replies and FROMNUM_UUID in self.callbacks:
            self.callbacks[FROMNUM_UUID](bytearray(struct.pack('<I',self.number)))

    async def start_notify(self,characteristic,callback,**kwargs):
        await self._ready();self.callbacks[characteristic.uuid]=callback

    async def stop_notify(self,characteristic):self.callbacks.pop(characteristic.uuid,None)
    async def read_gatt_descriptor(self,descriptor,**kwargs):raise BleakError('No descriptors')
    async def write_gatt_descriptor(self,descriptor,data):raise BleakError('No descriptors')
