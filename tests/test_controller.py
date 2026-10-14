import json
import time
import pytest
from conftest import wait_for
from meshdesk.controller import Controller
from meshdesk.store import Store
from meshdesk.simulator import RadioSimulator,PEER


def test_draft_is_not_written_until_save_and_stale_callbacks_ignored(qtapp,tmp_path):
    c=Controller(Store(tmp_path/'test.sqlite'),demo=True)
    try:
        wait_for(qtapp,lambda:c.sessions['simulator']['status']=='Connected')
        cached=c.store.get('snapshot:simulator')
        assert cached['channels'][1]['settings']=={'name':'Friends'}
        assert 'psk' not in json.dumps(cached) and 'security' not in cached
        c.dispatch('setting_load',json.dumps({'section':'config.lora'}))
        wait_for(qtapp,lambda:c.settings_message is not None)
        c.dispatch('setting_edit',json.dumps({'path':'hop_limit','value':'6'}))
        assert c.simulator.server.radio.config['lora'].hop_limit==3
        c.dispatch('setting_discard','{}')
        assert c.settings_message.hop_limit==3
        generation=c.sessions['simulator']['generation']
        c.dispatch('forget',json.dumps({'id':'simulator'}))
        c._receive('simulator',generation,'snapshot',{'nodes':[]})
        c._receive('simulator',generation,'result',{'operation':'read:config.lora','value':{}})
        assert not c.sessions
    finally:c.close()


def test_multiple_connections_scoped_messages_and_reconnect(qtapp,tmp_path):
    sim=RadioSimulator();c=Controller(Store(tmp_path/'test.sqlite'),demo=True)
    try:
        wait_for(qtapp,lambda:c.sessions['simulator']['status']=='Connected')
        c.dispatch('add_profile',json.dumps({'transport':'tcp','address':sim.address,'name':'Second'}))
        pid=c.active
        wait_for(qtapp,lambda:c.sessions[pid]['status']=='Connected')
        c.dispatch('send',json.dumps({'text':'Second connection'}))
        wait_for(qtapp,lambda:len(c.store.messages(pid))==2)
        assert not c.store.messages('simulator')
        oldgen=c.sessions[pid]['generation']
        c._receive(pid,oldgen,'disconnected',{})
        c.sessions[pid]['next_retry']=0;c._tick()
        wait_for(qtapp,lambda:c.sessions[pid]['status']=='Connected')
        assert c.sessions[pid]['generation']>oldgen
        c._receive(pid,oldgen,'disconnected',{})
        assert c.sessions[pid]['status']=='Connected'
    finally:c.close();sim.close()


def test_import_keeps_results_with_original_connection(qtapp,tmp_path):
    c=Controller(Store(tmp_path/'test.sqlite'),demo=True)
    try:
        wait_for(qtapp,lambda:c.sessions['simulator']['status']=='Connected')
        c.dispatch('export_channels','{}')
        wait_for(qtapp,lambda:bool(c.qr_url))
        c.dispatch('import_preview',json.dumps({'url':c.qr_url}))
        c.dispatch('import_apply','{}')
        c._register({'id':'offline','name':'Offline','transport':'tcp','address':'127.0.0.1:1'})
        c.dispatch('select_profile',json.dumps({'id':'offline'}))
        wait_for(qtapp,lambda:c.busy==0)
        assert c.sessions['offline']['snapshot']=={}
        assert c.sessions['simulator']['snapshot']['channels'][0]['settings']['name']=='LongFast'
    finally:c.close()
