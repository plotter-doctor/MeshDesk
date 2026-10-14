"""Real SDK serial transport over an OS pseudo-terminal, no pyserial mocks."""
import os
import pytest
from meshdesk.radio import Radio
from meshdesk.simulator import SerialSimulator,FrameDecoder,frame
from meshtastic.protobuf import mesh_pb2


@pytest.mark.skipif(os.name!='posix',reason='POSIX pseudo terminal required')
@pytest.mark.parametrize('fragment_size',[0,1,7])
def test_serial_handshake_settings_message_and_reconnect(fragment_size):
    sim=SerialSimulator(fragment_size=fragment_size,delay=.0001)
    try:
        for expected in (3,4):
            client=Radio(lambda *args:None,timeout=3)
            try:
                client.connect({'transport':'serial','address':sim.address})
                data=client.read_section('config.lora');assert data['hop_limit']==expected
                data['hop_limit']=4;assert client.write_section('config.lora',data)['hop_limit']==4
                assert client.send_text('Serial 👋')['packet_id']
            finally:client.close()
        assert not sim.errors
    finally:sim.close();sim.close()
    assert not sim.thread.is_alive()


def test_decoder_recovers_from_console_noise_invalid_size_and_protobuf():
    message=mesh_pb2.ToRadio(want_config_id=123)
    raw=b'booting\n'+b'\x94\xc3\xff\xff'+b'\x94\xc3\x00\x01\xff'+frame(message)
    for chunksize in (1,2,3,7,len(raw)):
        decoder=FrameDecoder();received=[]
        for i in range(0,len(raw),chunksize):received.extend(decoder.feed(raw[i:i+chunksize]))
        assert received==[message]
