"""BlueZ D-Bus contract tests; no host pairing or hardware changes."""
import asyncio
import sys
from types import SimpleNamespace
import pytest
from bleak.backends.device import BLEDevice
from meshtastic.ble_interface import SERVICE_UUID
from meshdesk import ble

pytestmark=pytest.mark.skipif(sys.platform!='linux',reason='BlueZ D-Bus contract is Linux-specific')


@pytest.mark.parametrize('found,query,expected',[
    ([('AA:BB','Radio')],'aa-bb','AA:BB'),([('AA:BB','Radio')],'radio','AA:BB'),
    ([('AA:BB','Radio')],None,'AA:BB'),([],None,None),([('A','One'),('B','Two')],None,None),([('A',None)],'missing',None)])
def test_ble_discovery_selection(monkeypatch,found,query,expected):
    monkeypatch.setattr(ble.sys,'platform','test')
    monkeypatch.setattr(ble.NativeBLEInterface,'scan',lambda self:[BLEDevice(a,n,{}) for a,n in found])
    interface=object.__new__(ble.NativeBLEInterface)
    if expected:assert interface.find_device(query).address==expected
    else:
        with pytest.raises(ValueError):interface.find_device(query)


def test_scan_filters_other_services(monkeypatch):
    dev=BLEDevice('A','Radio',{})
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def discover(self,**kw):
            assert kw['service_uuids']==[SERVICE_UUID]
            return {'yes':(dev,SimpleNamespace(service_uuids=[SERVICE_UUID])),'no':(dev,SimpleNamespace(service_uuids=[]))}
    monkeypatch.setattr(ble,'BoundedBLEClient',Client)
    assert ble.NativeBLEInterface.scan()==[dev]


@pytest.fixture
def bus(monkeypatch):
    from dbus_fast import Variant
    path='/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF'
    class Bus:
        def __init__(self,**kwargs):
            self.found={path:{'org.bluez.Device1':{'Address':Variant('s','AA:BB:CC:DD:EE:FF'),'Name':Variant('s','Radio'),'Paired':Variant('b',False)}}}
            self.exported=None;self.disconnected=False;self.registered=False;self.unregistered=False;self.pair_calls=0
        async def connect(self):return self
        async def introspect(self,*a):return None
        def get_proxy_object(self,*a):return self
        def get_interface(self,*a):return self
        async def call_get_managed_objects(self):return self.found
        def export(self,path,agent):self.exported=agent
        def unexport(self,path):self.exported=None
        def disconnect(self):self.disconnected=True
        async def call_register_agent(self,*a):self.registered=True
        async def call_unregister_agent(self,*a):self.unregistered=True
        async def call_pair(self):
            from dbus_fast import DBusError
            self.pair_calls+=1
            agent=self.exported
            assert agent.RequestPasskey.__wrapped__(agent,path)==123456
            assert agent.RequestPinCode.__wrapped__(agent,path)=='123456'
            agent.RequestConfirmation.__wrapped__(agent,path,123456)
            with pytest.raises(DBusError):agent.RequestConfirmation.__wrapped__(agent,path,111111)
            with pytest.raises(DBusError):agent.check('/different')
            agent.Release();agent.Cancel()
    instance=Bus()
    monkeypatch.setattr('dbus_fast.aio.MessageBus',lambda **kw:instance)
    monkeypatch.setattr(ble.NativeBLEInterface,'scan',lambda:[])
    return instance,path


def test_bluez_cached_lookup_and_cleanup(bus):
    instance,path=bus
    result=asyncio.run(ble.bluez_device('Radio'))
    assert result.address=='AA:BB:CC:DD:EE:FF' and result.details['path']==path
    assert instance.disconnected
    assert asyncio.run(ble.bluez_device('missing')) is None


@pytest.mark.parametrize('state',['new','paired','missing','failure'])
def test_pairing_contract_and_cleanup(bus,state):
    from dbus_fast import Variant
    instance,path=bus
    if state=='paired':instance.found[path]['org.bluez.Device1']['Paired']=Variant('b',True)
    if state=='missing':instance.found={}
    if state=='failure':
        async def fail():raise RuntimeError('Pair rejected')
        instance.call_pair=fail
    if state in ('failure','missing'):
        with pytest.raises((ValueError,RuntimeError)):ble.pair_bluez('AA:BB:CC:DD:EE:FF','123456')
    else:ble.pair_bluez('AA:BB:CC:DD:EE:FF','123456')
    assert instance.disconnected and instance.exported is None
    assert instance.registered==instance.unregistered
    assert instance.pair_calls==(1 if state=='new' else 0)
