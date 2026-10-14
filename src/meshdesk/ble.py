"""Bounded official BLE transport and Linux PIN pairing.

The SDK 2.7.11 disconnect callback calls synchronous close on Bleak's event
loop. That can deadlock a GATT write. Keep protocol decoding in the SDK, but
move disconnect cleanup off that loop and bound every asynchronous operation.
"""
import asyncio
import atexit
import contextlib
import concurrent.futures
import threading
import sys
from meshtastic.ble_interface import BLEInterface, BLEClient, SERVICE_UUID
from meshtastic.mesh_interface import MeshInterface


class BoundedBLEClient(BLEClient):
    def __init__(self,*args,operation_timeout=15,**kwargs):
        self.operation_timeout=operation_timeout
        super().__init__(*args,**kwargs)

    def async_await(self,coro,timeout=None):
        future=self.async_run(coro)
        try:return future.result(timeout or self.operation_timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise TimeoutError('Bluetooth operation timed out; check pairing and radio availability') from None

    def close(self):
        if not self._eventLoop.is_running():return
        async def drain():
            pending=[t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in pending:task.cancel()
            if pending:await asyncio.gather(*pending,return_exceptions=True)
        with contextlib.suppress(Exception):self.async_await(drain(),timeout=2)
        self._eventLoop.call_soon_threadsafe(self._eventLoop.stop)
        if threading.current_thread() is not self._eventThread:self._eventThread.join(2)


class NativeBLEInterface(BLEInterface):
    @staticmethod
    def scan():
        with BoundedBLEClient(operation_timeout=15) as client:
            found=client.discover(timeout=10,return_adv=True,service_uuids=[SERVICE_UUID])
            return [device for device,advertisement in found.values() if SERVICE_UUID in advertisement.service_uuids]

    def find_device(self,address):
        # Paired BlueZ devices may already be connected and no longer advertise.
        # Bleak accepts a BLEDevice carrying the known BlueZ object path.
        if address and sys.platform=='linux':
            with BoundedBLEClient(operation_timeout=10) as client:
                cached=client.async_await(bluez_device(address))
            if cached:return cached
        devices=self.scan()
        if address:
            normal=lambda s:s.lower().replace(':','').replace('-','')
            devices=[d for d in devices if normal(d.address)==normal(address) or (d.name and d.name.lower()==address.lower())]
        if len(devices)!=1:raise ValueError('Select one available Meshtastic Bluetooth radio')
        return devices[0]

    def __init__(self,address,timeout=15,*,device=None,client_factory=BoundedBLEClient):
        self.operation_timeout=timeout
        self._device=device
        self._client_factory=client_factory
        self._close_lock=threading.Lock()
        self._exit_handler=None
        try:super().__init__(address=address,timeout=timeout)
        except BaseException:
            self.close()
            raise

    def connect(self,address=None):
        device=self._device or self.find_device(address)
        def disconnected(_):
            threading.Thread(target=self.close,name='mesh-ble-close',daemon=True).start()
        client=self._client_factory(device,operation_timeout=self.operation_timeout,disconnected_callback=disconnected,timeout=self.operation_timeout)
        self.client=client
        client.connect()
        return client

    def _waitConnected(self,timeout=30):
        return super()._waitConnected(min(timeout,self.operation_timeout))

    def _receiveFromRadioImpl(self):
        try:super()._receiveFromRadioImpl()
        except Exception as error:
            # A failed/expired GATT read must leave Connected state. The SDK
            # receiver otherwise exits without notifying the application.
            self.receive_failure=error
            self.close()

    def close(self):
        if not self._close_lock.acquire(blocking=False):return
        try:
            client=getattr(self,'client',None)
            if self._exit_handler:atexit.unregister(self._exit_handler)
            if getattr(self,'heartbeatTimer',None):self.heartbeatTimer.cancel()
            self._want_receive=False
            if client and client.bleak_client.is_connected:
                with contextlib.suppress(Exception):MeshInterface.close(self)
            self.client=None
            receiver=getattr(self,'_receiveThread',None)
            if receiver and receiver is not threading.current_thread():receiver.join(2)
            self._receiveThread=None
            if client:
                with contextlib.suppress(Exception):client.disconnect()
                client.close()
            self._disconnected()
        finally:self._close_lock.release()


async def bluez_device(address):
    from dbus_fast.aio import MessageBus
    from dbus_fast import BusType
    from bleak.backends.device import BLEDevice
    bus=await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        intro=await bus.introspect('org.bluez','/')
        manager=bus.get_proxy_object('org.bluez','/',intro).get_interface('org.freedesktop.DBus.ObjectManager')
        found=await manager.call_get_managed_objects()
        matches=[]
        for path,interfaces in found.items():
            props={key:value.value for key,value in interfaces.get('org.bluez.Device1',{}).items()}
            if address.lower() in (str(props.get('Address','')).lower(),str(props.get('Name','')).lower()):
                matches.append(BLEDevice(props['Address'],props.get('Name'),{'path':path,'props':props}))
        return matches[0] if len(matches)==1 else None
    finally:bus.disconnect()


def pair_bluez(address,pin):
    """Pair just this device using an ephemeral agent; never store its PIN."""
    if not pin.isdigit() or len(pin)!=6:raise ValueError('Enter the six-digit PIN shown by the radio')
    NativeBLEInterface.scan()  # Populate BlueZ's device objects before looking up the target.
    async def pair():
        from dbus_fast.aio import MessageBus
        from dbus_fast import BusType,DBusError
        from dbus_fast.service import ServiceInterface,method
        bus=await MessageBus(bus_type=BusType.SYSTEM).connect()
        agent_path='/org/meshdesk/pairing'
        manager=None
        try:
            intro=await bus.introspect('org.bluez','/')
            objects=bus.get_proxy_object('org.bluez','/',intro).get_interface('org.freedesktop.DBus.ObjectManager')
            found=await objects.call_get_managed_objects()
            path=next((p for p,v in found.items() if v.get('org.bluez.Device1',{}).get('Address') and v['org.bluez.Device1']['Address'].value.lower()==address.lower()),None)
            if not path:raise ValueError('Radio not found during Bluetooth discovery')
            if found[path]['org.bluez.Device1']['Paired'].value:return
            class Agent(ServiceInterface):
                def __init__(self):super().__init__('org.bluez.Agent1')
                def check(self,device):
                    if device!=path:raise DBusError('org.bluez.Error.Rejected','Different device')
                @method()
                def Release(self):pass
                @method()
                def Cancel(self):pass
                @method()
                def RequestPasskey(self,device:'o')->'u':
                    self.check(device);return int(pin)
                @method()
                def RequestPinCode(self,device:'o')->'s':
                    self.check(device);return pin
                @method()
                def RequestConfirmation(self,device:'o',passkey:'u'):
                    self.check(device)
                    if passkey!=int(pin):raise DBusError('org.bluez.Error.Rejected','PIN mismatch')
            agent=Agent();bus.export(agent_path,agent)
            intro=await bus.introspect('org.bluez','/org/bluez')
            manager=bus.get_proxy_object('org.bluez','/org/bluez',intro).get_interface('org.bluez.AgentManager1')
            await manager.call_register_agent(agent_path,'KeyboardOnly')
            intro=await bus.introspect('org.bluez',path)
            device=bus.get_proxy_object('org.bluez',path,intro).get_interface('org.bluez.Device1')
            await asyncio.wait_for(device.call_pair(),25)
        finally:
            if manager:
                with contextlib.suppress(Exception):await manager.call_unregister_agent(agent_path)
            bus.unexport(agent_path);bus.disconnect()
    return asyncio.run(asyncio.wait_for(pair(),35))
