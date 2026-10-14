import asyncio
import pytest
from bleak import BleakClient
from bleak.exc import BleakError
from meshtastic.ble_interface import FROMNUM_UUID,TORADIO_UUID,FROMRADIO_UUID
from meshdesk.virtualble import VirtualBLESimulator,VirtualGattBackend,PERIPHERALS
from meshdesk.radio import Radio
from conftest import wait_for


def test_sdk_ble_handshake_write_notification_disconnect_reconnect(qtapp):
    sim=VirtualBLESimulator();events=[]
    try:
        for expected in (3,4):
            radio=Radio(lambda k,v:events.append((k,v)),timeout=2)
            radio.connect({'transport':'ble','address':sim.address})
            try:
                data=radio.read_section('config.lora');assert data['hop_limit']==expected
                data['hop_limit']=4;assert radio.write_section('config.lora',data)['hop_limit']==4
                result=radio.send_text('Virtual BLE 👋')
                wait_for(qtapp,lambda:any(k=='packet' and v['decoded'].get('replyId')==result['packet_id'] for k,v in events))
                client=radio.interface.client;backend=sim.clients[-1]
                assert backend.mtu_size==512 and backend.name=='MeshDesk virtual BLE'
                client._eventLoop.call_soon_threadsafe(backend.drop)
                wait_for(qtapp,lambda:radio.interface.client is None)
                wait_for(qtapp,lambda:not client._eventThread.is_alive())
                assert any(k=='disconnected' for k,v in events)
            finally:radio.close()
    finally:sim.close()
    assert sim.address not in PERIPHERALS


@pytest.mark.parametrize('failure',['write_error','drop_responses'])
def test_ble_failed_handshake_cleans_receiver_and_loop(failure):
    import threading
    before={t.ident for t in threading.enumerate()}
    sim=VirtualBLESimulator();setattr(sim,failure,True)
    radio=Radio(lambda *args:None,timeout=.2)
    try:
        with pytest.raises(Exception):radio.connect({'transport':'ble','address':sim.address})
        assert radio.interface is None
        assert not any(t.name in ('BLEReceive','BLEClient') and t.ident not in before for t in threading.enumerate())
    finally:radio.close();sim.close()


def test_virtual_gatt_contract_and_faults():
    sim=VirtualBLESimulator()
    async def exercise():
        client=BleakClient(sim.device,backend=VirtualGattBackend)
        await client.connect();await client.pair()
        backend=client._backend;assert backend.paired
        assert bytes(await client.read_gatt_char(FROMNUM_UUID))==b'\0'*4
        assert not await client.read_gatt_char(FROMRADIO_UUID)
        with pytest.raises(BleakError):await client.read_gatt_char(TORADIO_UUID)
        with pytest.raises(BleakError):await client.write_gatt_char(FROMRADIO_UUID,b'',response=True)
        with pytest.raises(BleakError):await backend.read_gatt_descriptor(None)
        with pytest.raises(BleakError):await backend.write_gatt_descriptor(None,b'')
        await client.start_notify(FROMNUM_UUID,lambda *args:None)
        await client.stop_notify(FROMNUM_UUID);assert not backend.callbacks
        sim.delay=.05
        with pytest.raises(asyncio.TimeoutError):await asyncio.wait_for(client.read_gatt_char(FROMRADIO_UUID),.01)
        sim.delay=0
        await client.unpair();assert not backend.paired and not client.is_connected
        with pytest.raises(BleakError):await backend._ready()
        await backend.connect(pair=True);assert backend.paired
        sim.close();await asyncio.sleep(.01);assert not backend.is_connected
    try:asyncio.run(exercise())
    finally:sim.close()


def test_ble_read_timeout_reports_disconnect_and_stops_thread(qtapp):
    sim=VirtualBLESimulator();radio=Radio(lambda *args:None,timeout=1)
    try:
        radio.connect({'transport':'ble','address':sim.address})
        interface=radio.interface;client=interface.client
        # Delay reads only: configuration completion can still trigger SDK
        # writes after connect() returns. A shared delay races that activity.
        client.operation_timeout=.05;sim.read_delay=.2
        interface.should_read=True
        wait_for(qtapp,lambda:hasattr(interface,'receive_failure'))
        assert isinstance(interface.receive_failure,TimeoutError)
        wait_for(qtapp,lambda:not client._eventThread.is_alive())
        assert interface.client is None
    finally:radio.close();sim.close()
