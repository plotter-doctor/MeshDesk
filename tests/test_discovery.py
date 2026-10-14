from types import SimpleNamespace
from meshdesk.discovery import serial_devices


def test_discovery_hides_system_ports_and_marks_usb_as_unverified():
    def port(device,vid=None,name='Serial port'):
        return SimpleNamespace(device=device,vid=vid,description=name)
    devices=serial_devices([port('/dev/ttyS0'),port('/dev/ttyACM0',0x303a,'USB JTAG/serial'),
                            port('/dev/ttyUSB0',0x10c4,'CP2102 USB bridge'),port('/dev/ttyACM1',0x1234,'Custom device')],known=['/dev/ttyACM1'])
    assert devices[0]['verified'] and devices[0]['address']=='/dev/ttyACM1'
    by_address={d['address']:d for d in devices}
    assert not by_address['/dev/ttyS0']['likely']
    assert by_address['/dev/ttyACM0']['likely'] and not by_address['/dev/ttyACM0']['verified']
    assert by_address['/dev/ttyUSB0']['likely']
