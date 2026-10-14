import os
import time
import pytest

os.environ.setdefault('QT_QUICK_BACKEND','software')
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE','Material')


@pytest.fixture(scope='session')
def qtapp():
    from PyQt5.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    app.setApplicationName('MeshDesk-tests')
    yield app


def wait_for(app, condition, timeout=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        app.processEvents()
        if condition():return
        time.sleep(0.01)
    raise AssertionError('Timed out waiting for condition')


@pytest.fixture
def radio():
    from meshdesk.simulator import RadioSimulator
    from meshdesk.radio import Radio
    simulator=RadioSimulator()
    events=[]
    client=Radio(lambda kind,data:events.append((kind,data)),timeout=2)
    client.connect({'transport':'tcp','address':simulator.address})
    yield client,simulator,events
    client.close()
    simulator.close()
