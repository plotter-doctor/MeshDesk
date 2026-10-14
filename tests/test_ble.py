import asyncio
import threading
import time
import pytest
from meshdesk.ble import BoundedBLEClient,pair_bluez


def test_ble_operation_timeout_cancels_future_and_closes_loop():
    client=BoundedBLEClient(operation_timeout=.05)
    finished=threading.Event()
    async def never_finishes():
        try:await asyncio.sleep(100)
        finally:finished.set()
    started=time.monotonic()
    try:
        with pytest.raises(TimeoutError):client.async_await(never_finishes())
        assert time.monotonic()-started<1
        assert finished.wait(1)
    finally:client.close()
    assert not client._eventThread.is_alive()


def test_pairing_rejects_invalid_pin_without_discovery(monkeypatch):
    monkeypatch.setattr('meshdesk.ble.BLEInterface.scan',lambda:pytest.fail('must not scan'))
    with pytest.raises(ValueError):pair_bluez('00:00:00:00:00:00','123')


def test_paired_bluez_device_connects_without_advertising(monkeypatch):
    from meshdesk import ble
    from bleak.backends.device import BLEDevice
    device=BLEDevice('AA:BB:CC:DD:EE:FF','Known radio',{'path':'/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF'})
    async def lookup(address):
        assert address==device.address
        return device
    monkeypatch.setattr(ble.sys,'platform','linux')
    monkeypatch.setattr(ble,'bluez_device',lookup)
    monkeypatch.setattr(ble.NativeBLEInterface,'scan',staticmethod(lambda:pytest.fail('Paired device need not advertise')))
    interface=object.__new__(ble.NativeBLEInterface)
    assert interface.find_device(device.address) is device
