import base64
import json
import pytest
from meshdesk import forms,commands
from meshdesk.schema import new_message,set_field,validate_section
from meshdesk.radio import encode_channel_url,decode_channel_url,plan_channel_import
from meshdesk.mapmath import precision_meters,heat_weight,heat_color,fan_offsets,nice_scale
from meshdesk.controller import Controller
from meshdesk.store import Store


def test_official_form_conditions_groups_and_admin_keys():
    message=new_message('config.network')
    rows={f['path']:f for f in forms.present('config.network',message,'en')}
    assert rows['wifi_ssid']['disabled']
    message.wifi_enabled=True
    rows={f['path']:f for f in forms.present('config.network',message,'pl-PL')}
    assert not rows['wifi_ssid']['disabled'] and rows['wifi_ssid']['description']
    security=new_message('config.security')
    key=base64.b64encode(b'a'*32).decode()
    set_field(security,'admin_key.2',key)
    assert list(security.admin_key)==[b'',b'',b'a'*32]
    rows={f['path']:f for f in forms.present('config.security',security,'en')}
    assert rows['admin_key.2']['value']==key
    assert rows['public_key']['disabled']
    with pytest.raises(ValueError):set_field(security,'admin_key.1','YQ==')
    set_field(security,'admin_key.2','')
    assert list(security.admin_key)==[]
    security.is_managed=True
    with pytest.raises(ValueError,match='Managed'):validate_section('config.security',security)


@pytest.mark.parametrize('section,path,value',[
    ('config.lora','override_frequency',100),('config.power','adc_multiplier_override',5),
    ('module.ambient_lighting','red',256),('module.traffic_management','position_precision_bits',33),
    ('config.network','wifi_ssid','x'*34),('module.statusmessage','node_status','x'*201)])
def test_web_constraints_reject_bad_settings(section,path,value):
    message=new_message(section)
    if section=='config.network':message.wifi_enabled=True
    if section=='module.ambient_lighting':message.led_state=True
    if section=='module.traffic_management':message.enabled=True;message.position_dedup_enabled=True
    set_field(message,path,value)
    with pytest.raises(ValueError):validate_section(section,message)


def test_command_groups_pins_switch_connections_and_qr_destination():
    result=commands.entries([{'id':'r','name':'My radio'}],pinned=['debugGroup'])
    assert result[0]['group']=='debugGroup'
    assert next(c for c in result if c['id']=='switch:r')['args']=={'id':'r'}
    qr=next(c for c in result if c['id']=='contextualGroup:qrGenerator')
    assert qr['page']=='Settings' and qr['tab']==1
    assert all(not c['title'].startswith('commandPalette.') for c in result)


def test_channel_selection_add_link_import_mapping_and_no_duplicate_writes():
    channels=[{'index':1,'role':'SECONDARY','settings':{'name':'Friends','psk':'AQ=='}}]
    url=encode_channel_url(channels,{'hop_limit':3},add=True)
    assert '?add=true#' in url
    parsed=decode_channel_url(url)
    plan=plan_channel_import(parsed,[5],update_lora=False)
    assert len(plan)==1 and plan[0][0]=='channel.5'
    assert plan[0][1].settings.name=='Friends'
    parsed.settings.add().CopyFrom(parsed.settings[0])
    with pytest.raises(ValueError,match='same target'):plan_channel_import(parsed,[5,5])
    assert len(plan_channel_import(parsed,[5,-1],update_lora=False))==1
    with pytest.raises(ValueError,match='primary'):plan_channel_import(parsed,[5,-1],replace=True)
    assert len(plan_channel_import(parsed,[0,2],replace=True,update_lora=True))==9


def test_drafts_persist_per_conversation_and_count_utf8(qtapp,tmp_path):
    path=tmp_path/'drafts.sqlite';c=Controller(Store(path))
    try:
        c._register({'id':'r','name':'Saved','transport':'tcp','address':'127.0.0.1:1'})
        c.store.save_profile(c.sessions['r']['profile']);c.active='r';c.store.put('active','r')
        c.dispatch('draft',json.dumps({'text':'Zażółć 👋'}))
        c.dispatch('chat',json.dumps({'peer':42}))
        c.dispatch('draft',json.dumps({'text':'Private draft'}))
        assert c.messageBytes('👋')==4
    finally:c.close()
    c=Controller(Store(path))
    try:
        assert c.drafts['r:0:0']=='Zażółć 👋' and c.drafts['r:42:0']=='Private draft'
    finally:c.close()


def test_map_scale_precision_heat_and_deterministic_fan():
    assert precision_meters(24)==1
    assert precision_meters(16)>300
    assert heat_weight(-20,'snr')==0 and heat_weight(10,'snr')==1
    assert heat_color(0)[3]==0 and heat_color(1)[3]>0
    assert fan_offsets(4,'same')==fan_offsets(4,'same')
    assert len(set(fan_offsets(4,'same')))==4
    width,label=nice_scale(52,12)
    assert 0<width<=100 and label.endswith(('m','km'))


def test_staged_settings_survive_navigation_and_batch_commit(qtapp,tmp_path):
    from conftest import wait_for
    c=Controller(Store(tmp_path/'batch.sqlite'),demo=True)
    try:
        wait_for(qtapp,lambda:c.sessions['simulator']['status']=='Connected')
        c._dispatch('setting_load',{'section':'config.lora'})
        wait_for(qtapp,lambda:c.settings_message is not None)
        c._dispatch('setting_edit',{'path':'hop_limit','value':6})
        c._dispatch('setting_load',{'section':'module.telemetry'})
        wait_for(qtapp,lambda:c.settings_message is not None)
        c._dispatch('setting_edit',{'path':'device_update_interval','value':1800})
        c._dispatch('setting_load',{'section':'config.lora'})
        assert c.settings_message.hop_limit==6
        assert set(c._pending_settings())=={'config.lora','module.telemetry'}
        assert c.simulator.server.radio.config['lora'].hop_limit==3
        c._dispatch('setting_save_all',{})
        wait_for(qtapp,lambda:c.busy==0)
        assert not c._pending_settings()
        state=c.simulator.server.radio
        assert state.config['lora'].hop_limit==6 and state.module['telemetry'].device_update_interval==1800
        assert 'begin_edit_settings' in state.actions and 'commit_edit_settings' in state.actions
        c._dispatch('clear_all_data',{})
        assert not c.sessions and not c.store.nodes('simulator') and not c.store.get('drafts')
    finally:c.close()


def test_channel_precision_uses_radio_units_and_localized_timestamp_prefix():
    from meshdesk import i18n
    channel=new_message('channel.0')
    def choices(units):
        return next(f['choices'] for f in forms.present('channel.0',channel,'en',units) if f['path']=='settings.module_settings.position_precision')
    assert 'kilometers' in choices(0)[1]['label']
    assert 'miles' in choices('IMPERIAL')[1]['label']
    assert '{{date}}' not in i18n.translate('Last connected','pl-PL')
