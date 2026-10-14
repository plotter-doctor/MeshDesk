"""Subprocess checks include startup, shutdown and the actual executable."""
import json
import os
import subprocess
import sys
import pytest


@pytest.mark.parametrize('transport',['tcp','serial','ble'])
def test_demo_executable(transport,tmp_path):
    if transport=='serial' and os.name!='posix':pytest.skip('POSIX pseudo terminal')
    result=subprocess.run([sys.executable,'-m','meshdesk.app','--demo','--demo-transport',transport,
        '--data-dir',str(tmp_path/'data'),'--keyboard','off','--ready-file',str(tmp_path/'ready.json'),
        '--screenshot',str(tmp_path/'window.png'),'--quit-after','8'],capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stderr
    assert (tmp_path/'window.png').stat().st_size>10000
    assert json.loads((tmp_path/'ready.json').read_text())['ready_seconds']>0


def test_offline_startup(tmp_path):
    result=subprocess.run([sys.executable,'-m','meshdesk.app','--data-dir',str(tmp_path),
        '--quit-after','1','--ready-file',str(tmp_path/'ready.json')],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert (tmp_path/'ready.json').exists()


@pytest.mark.parametrize('transport',['tcp','serial'])
def test_standalone_simulator(transport):
    if transport=='serial' and os.name!='posix':pytest.skip('POSIX pseudo terminal')
    result=subprocess.run([sys.executable,'-m','meshdesk.simulator','--transport',transport,'--port','0','--duration','.1'],
        capture_output=True,text=True,timeout=30)  # Includes pure-Python protobuf import on ARM.
    assert result.returncode==0,result.stderr
    assert 'listening at' in result.stdout
