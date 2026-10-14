"""Hardware-test targeting must never guess a recipient or broadcast."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('hardware_smoke', Path(__file__).parents[1] / 'tools/hardware_smoke.py')
hardware = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hardware)
LOCAL = 0x8fa74e58
PEER = {'num': 0x49138b0c, 'user': {'shortName': 'afa0'}}


def test_short_name_can_differ_from_node_id():
    assert hardware.resolve_recipient([PEER], 'afa0', LOCAL) == PEER
    assert hardware.resolve_recipient([PEER], '!49138b0c', LOCAL) == PEER
    assert hardware.resolve_recipient([PEER], '8B0C', LOCAL) == PEER


def test_ambiguous_name_and_id_suffix_is_rejected():
    other = {'num': 0x1234afa0, 'user': {'shortName': 'node'}}
    with pytest.raises(ValueError, match='exactly one'):
        hardware.resolve_recipient([PEER, other], 'afa0', LOCAL)
    assert hardware.resolve_recipient([PEER, other], '!49138b0c', LOCAL) == PEER


@pytest.mark.parametrize('query', ['', 'ffff', '!00008b0c', 'missing'])
def test_unknown_or_partial_explicit_id_is_rejected(query):
    with pytest.raises(ValueError):
        hardware.resolve_recipient([PEER], query, LOCAL)


@pytest.mark.parametrize('num', [0, 0xffffffff, LOCAL])
def test_only_remote_unicast_nodes_are_allowed(num):
    with pytest.raises(ValueError, match='remote, unicast'):
        hardware.resolve_recipient([{'num': num}], f'!{num:08x}', LOCAL)
