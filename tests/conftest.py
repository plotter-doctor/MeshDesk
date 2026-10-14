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


def prepare_layout_window(window):
    """Permit exact audit sizes even on the small Windows runner desktop.

    Windows defaults an unconstrained window's maximum tracking size to its
    monitor. An explicit limit makes Qt supply WM_GETMINMAXINFO for the taller
    portrait capture. Normal application startup retains its work-area sizing.
    """
    from PyQt5.QtCore import QSize
    from PyQt5.QtTest import QTest
    window.setMaximumSize(QSize(2048, 2048))
    window.showNormal()
    QTest.qWait(100)


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
