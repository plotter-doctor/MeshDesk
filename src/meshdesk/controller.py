"""Qt presentation controller. Threaded I/O, bounded views and explicit writes."""
import base64
import concurrent.futures
import contextlib
import csv
import hashlib
import io
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot, pyqtProperty
from PyQt5.QtWidgets import QApplication, QFileDialog
from PyQt5.QtGui import QFont,QPalette
from google.protobuf import json_format
from . import __version__
from .schema import fields, label, new_message, safe_data, sections, set_field, to_dict, validate_section
from .radio import Radio, decode_channel_url, encode_channel_url
from .models import FieldModel
from . import i18n
from . import forms, commands, notifications
from . import nodes as node_tools


class Controller(QObject):
    changed = pyqtSignal()
    toast = pyqtSignal(str)
    navigate = pyqtSignal(str)
    delivered = pyqtSignal(str, int, str, object)

    def __init__(self, store, demo=False, demo_transport='tcp'):
        super().__init__()
        self.store=store
        self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=4,thread_name_prefix='mesh-io')
        self.sessions={}
        self.active=''
        self.peer=0
        self.channel=0
        self.search=''
        self.message_limit=100
        self.message_offset=0
        self.page='Chat'
        self.form_model=FieldModel(self)
        self.selected_node=0
        self.drafts=self.store.get('drafts',{})
        self.settings_section='config.lora'
        self.settings_message=None
        self.settings_original=None
        self.settings_drafts={}
        self.settings_loading=False
        self.settings_error=''
        self.invalid_fields={}
        self.busy=0
        self.qr_url=''
        self.import_preview=[]
        self.import_url=''
        self.import_lora=False
        self.notification={}
        self.simulator=None
        self.demo_transport=demo_transport
        self._closing=False
        self._pending_acks={}
        self._json='{}'
        self.delivered.connect(self._receive)
        self.publish_timer=QTimer(self)
        self.publish_timer.setSingleShot(True)
        self.publish_timer.timeout.connect(self._publish)
        self.maintenance=QTimer(self)
        self.maintenance.timeout.connect(self._tick)
        self.maintenance.start(5000)
        for profile in self.store.profiles():
            if profile['id']!='simulator':
                self._register(profile)
        self.active=self.store.get('active','')
        if self.active not in self.sessions:
            self.active=next(iter(self.sessions),'')
        if demo:
            self.start_demo()
        elif self.store.get('default_profile','') in self.sessions:
            self.active=self.store.get('default_profile');self._connect(self.active)
        QApplication.instance().paletteChanged.connect(self.dirty)
        self._publish()

    @pyqtProperty(str,notify=changed)
    def stateJson(self):
        return self._json

    @pyqtProperty(QObject,constant=True)
    def fieldsModel(self):
        return self.form_model

    @pyqtProperty(QFont,constant=True)
    def interfaceFont(self):
        font=QFont()
        font.setFamilies(['DejaVu Sans','Noto Color Emoji','Apple Color Emoji','Segoe UI Emoji'])
        font.setPixelSize(14)
        return font

    @pyqtProperty(bool,constant=True)
    def keyboardAvailable(self):return os.environ.get('QT_IM_MODULE')=='qtvirtualkeyboard'

    @pyqtSlot(str,result=int)
    def messageBytes(self,text):return len(text.encode('utf-8'))

    @pyqtSlot(str,str,result=str)
    def translate(self,text,language):
        return i18n.translate(text,language)

    @pyqtSlot(str,str,result=str)
    def translateKey(self,key,language):return i18n.catalog(language).get(key,i18n.catalog().get(key,key))

    def _register(self,profile):
        self.sessions[profile['id']]={'profile':profile,'radio':None,'status':'Offline','generation':0,
                                     'snapshot':self.store.get('snapshot:'+profile['id'],{}),'retry':0,'next_retry':0,'manual':True}

    def _cache_snapshot(self,pid,snapshot):
        self.store.put('snapshot:'+pid,{'my_num':snapshot.get('my_num',0),'metadata':snapshot.get('metadata',{}),
            'channels':[{'index':c.get('index',i),'role':c.get('role','DISABLED'),'settings':{'name':c.get('settings',{}).get('name','')}}
                        for i,c in enumerate(snapshot.get('channels',[]))]})

    def dirty(self):
        if not self.publish_timer.isActive():
            self.publish_timer.start(60)

    def _publish(self):
        session=self.sessions.get(self.active,{})
        snapshot=session.get('snapshot',{})
        nodes=self.store.nodes(self.active) if self.active else []
        for n in nodes:
            user=n.get('user',{})
            n['name']=user.get('longName',user.get('long_name',f"!{n['num']:08x}"))
            n['short']=user.get('shortName',user.get('short_name','?'))
            n['favorite']=bool(n.get('isFavorite',n.get('is_favorite',False)))
            n['ignored']=bool(n.get('isIgnored',n.get('is_ignored',False)))
            n['lastHeard']=n.get('lastHeard',n.get('last_heard',0))
        nodes.sort(key=lambda n:(not n['favorite'],n['name'].lower()))
        names={n['num']:n['name'] for n in nodes}
        messages=self.store.messages(self.active,self.peer,self.channel,self.search,self.message_limit,self.message_offset) if self.active else []
        clock='%I:%M %p' if self.store.get('clock12',False) else '%H:%M'
        for m in messages:
            m['sender_name']=names.get(m['sender'],f"!{m['sender']:08x}")
            m['time']=time.strftime(clock,time.localtime(m['timestamp']))
        channels=snapshot.get('channels',[])
        conversations=[{'peer':0,'channel':int(ch.get('index',i)),'name':ch.get('settings',{}).get('name') or f'Channel {i}'}
                       for i,ch in enumerate(channels) if ch.get('role') not in ('DISABLED',0)]
        if not conversations:
            conversations=[{'peer':0,'channel':0,'name':'Primary channel'}]
        conversations += [{'peer':n['num'],'channel':0,'name':n['name']} for n in nodes if n['num']!=snapshot.get('my_num')]
        unread=self.store.unread(self.active) if self.active else []
        for c in conversations:
            c['unread']=sum(u['count'] for u in unread if (not c['peer'] and u['destination']==4294967295 and u['channel']==c['channel']) or (c['peer'] and u['destination']!=4294967295 and u['sender']==c['peer']))
        selected=next((n for n in nodes if n['num']==self.selected_node),{})
        local=next((n for n in nodes if n['num']==snapshot.get('my_num')),None)
        filters=self.store.get('node_filters',{})
        filtered=node_tools.sorted_nodes([n for n in nodes if node_tools.matches(n,filters)],self.store.get('node_sort','name'),self.store.get('node_sort_desc',False))
        units=snapshot.get('config',{}).get('display',{}).get('units',0)
        cfg_fields=forms.present(self.settings_section,self.settings_message,self.store.get('language','en'),units) if self.settings_message is not None else []
        self.form_model.sync(cfg_fields)
        cfg_dirty=bool(self.settings_message is not None and self.settings_original is not None and self.settings_message.SerializeToString()!=self.settings_original)
        events=self.store.events(self.active,120) if self.active else []
        for e in events:
            e['time']=time.strftime('%H:%M:%S',time.localtime(e['timestamp']))
            e['summary']=self._event_summary(e['kind'],e['data'],names)
        view={'version':__version__,'active':self.active,'status':session.get('status','Offline'),
              'backup_due':bool(session.get('status')=='Connected' and snapshot.get('config',{}).get('security',{}).get('private_key') and time.time()-session.get('profile',{}).get('last_connected',time.time())>=10 and self.store.get('backup_reminder:'+self.active,0)<time.time()),
              'connected':session.get('status')=='Connected','busy':self.busy>0,
              'profiles':[dict(s['profile'],status=s['status'],is_default=s['profile']['id']==self.store.get('default_profile')) for s in self.sessions.values()],
              'nodes':nodes,'filtered_nodes':filtered,'node_filters':filters,
              'filter_ranges':[{'key':key,'name':value[0]} for key,value in node_tools.RANGES.items()],
              'selected_node':selected,'node_details':node_tools.details(selected,local) if selected else [],
              'messages':messages,'conversations':conversations,
              'peer':self.peer,'channel':self.channel,'chat_name':next((c['name'] for c in conversations if c['peer']==self.peer and (self.peer or c['channel']==self.channel)),'Messages'),
              'draft':self.drafts.get(self._chat_key(),''),'my_num':snapshot.get('my_num',0),'metadata':snapshot.get('metadata',{}),
              'pending_settings':self._pending_settings(),
              'sections':sections(),'settings_section':self.settings_section,'fields':cfg_fields,'settings_dirty':cfg_dirty,
              'settings_loading':self.settings_loading,'settings_error':self.settings_error,
              'settings_json':json.dumps(to_dict(self.settings_message,True),indent=2) if self.settings_message is not None else '{}',
              'events':events,'qr_url':self.qr_url,'import_preview':self.import_preview,'import_lora':self.import_lora,'notification':self.notification,'notification_view':notifications.present(self.notification,self.store.get('language','en')),
              'history_offset':self.message_offset,'waypoints':self.store.waypoints(self.active),
              'theme_preference':self.store.get('theme','dark'),'theme':self._theme(),'clock12':self.store.get('clock12',False),
              'language':self.store.get('language','en'),'languages':i18n.locales(),'online_maps':self.store.get('online_maps',False),
              'tile_url':self.store.get('tile_url','https://tile.openstreetmap.org/{z}/{x}/{y}.png'),
              'tile_attribution':self.store.get('tile_attribution','© OpenStreetMap contributors'),
              'pinned_commands':self.store.get('pinned_commands',[]),
              'pinned_command_groups':self.store.get('pinned_command_groups',[]),
              'commands':commands.entries([s['profile'] for s in self.sessions.values()],self.store.get('language','en'),self.store.get('pinned_command_groups',[])),
              'filter_enums':node_tools.enum_choices(),'node_sort':self.store.get('node_sort','name'),'node_sort_desc':self.store.get('node_sort_desc',False)}
        serialized=json.dumps(safe_data(view),ensure_ascii=False)
        if serialized!=self._json:
            self._json=serialized
            self.changed.emit()

    def _theme(self):
        preference=self.store.get('theme','dark')
        if preference!='system':return preference
        return 'dark' if QApplication.palette().color(QPalette.Window).lightness()<128 else 'light'

    def _stash_settings(self):
        if self.settings_message is not None:
            self.settings_drafts[(self.active,self.settings_section)]={
                'value':self.settings_message.SerializeToString(),'original':self.settings_original,
                'errors':dict(self.invalid_fields)}

    def _pending_settings(self):
        self._stash_settings()
        return [section for (pid,section),draft in self.settings_drafts.items()
                if pid==self.active and (draft['value']!=draft['original'] or draft['errors'])]

    def _restore_settings(self,section):
        draft=self.settings_drafts.get((self.active,section))
        if draft is None:return False
        self.settings_message=new_message(section);self.settings_message.ParseFromString(draft['value'])
        self.settings_original=draft['original'];self.invalid_fields=dict(draft['errors'])
        self.settings_error='\n'.join(self.invalid_fields.values());self.settings_loading=False
        return True

    def _chat_key(self):
        return f'{self.active}:{self.peer}:{self.channel}'

    @staticmethod
    def _event_summary(kind,data,names):
        decoded=data.get('decoded',{})
        sender=names.get(data.get('from'),str(data.get('from','')))
        if kind=='TRACEROUTE_APP':
            route=decoded.get('traceroute',{})
            to_name=lambda num:names.get(num,f'!{num:08x}')
            forward=[data.get('to',0)]+route.get('route',[])+[data.get('from',0)]
            reverse=[data.get('from',0)]+route.get('routeBack',[])+[data.get('to',0)]
            return 'Route: '+' → '.join(map(to_name,forward))+'\nReturn: '+' → '.join(map(to_name,reverse))+'\nSNR towards: '+', '.join(str(n/4)+' dB' for n in route.get('snrTowards',[]))+'\nSNR back: '+', '.join(str(n/4)+' dB' for n in route.get('snrBack',[]))
        if kind=='TELEMETRY_APP':
            telemetry=decoded.get('telemetry',{})
            return sender+' · '+json.dumps(telemetry,ensure_ascii=False)
        if kind=='POSITION_APP':
            p=decoded.get('position',{})
            return sender+f" · {p.get('latitudeI',0)*1e-7:.6f}, {p.get('longitudeI',0)*1e-7:.6f} · altitude {p.get('altitude','—')} m"
        if kind=='WAYPOINT_APP':
            p=decoded.get('waypoint',{})
            return sender+' · '+p.get('name','Waypoint')+'\n'+p.get('description','')
        return json.dumps(data,ensure_ascii=False)[:1800]

    def _submit(self,operation,fn,pid=None):
        pid=pid or self.active
        generation=self.sessions.get(pid,{}).get('generation',0)
        radio=self.sessions.get(pid,{}).get('radio')
        self.busy+=1
        self.dirty()
        def task():
            try:
                lock=radio.lock if radio else contextlib.nullcontext()
                with lock:
                    result=fn()
                self.delivered.emit(pid,generation,'result',{'operation':operation,'value':result})
            except (Exception,SystemExit) as error:
                self.delivered.emit(pid,generation,'error',{'operation':operation,'message':str(error) or type(error).__name__})
        self.pool.submit(task)

    def _connect(self,pid):
        s=self.sessions[pid]
        if s['status'] in ('Connecting','Connected'):
            return
        s['generation']+=1
        gen=s['generation']
        old=s['radio']
        closing=s.get('closing')
        s['radio']=Radio(lambda kind,data:self.delivered.emit(pid,gen,kind,data))
        radio=s['radio'];profile=dict(s['profile'])
        s['status']='Connecting'
        s['manual']=False
        def work():
            if closing:closing.result(timeout=30)
            if old:
                old.close()
            radio.connect(profile)
        self._submit('connect',work,pid)

    def _tick(self):
        if self._closing:
            return
        now=time.time()
        for pid,s in self.sessions.items():
            if not s['manual'] and s['status']=='Reconnecting' and s['next_retry']<=now:
                self._connect(pid)
        self.store.execute("UPDATE messages SET status='No acknowledgement' WHERE outgoing=1 AND status='Awaiting acknowledgement' AND timestamp<?",(now-90,))
        self.dirty()

    @pyqtSlot(str,int,str,object)
    def _receive(self,pid,generation,kind,data):
        if kind in ('result','error'):
            self.busy=max(0,self.busy-1)
        s=self.sessions.get(pid)
        if self._closing or (s and generation!=s['generation']):
            return
        if not s and (kind not in ('result','error') or data.get('operation') not in ('scan','upstream','ble_pair','probe')):
            return
        if kind=='snapshot':
            s['snapshot']=data
            self._cache_snapshot(pid,data)
            for n in data['nodes']:
                self.store.node(pid,n)
        elif kind=='connected':
            s['status']='Connected'
            s['retry']=0
            s['profile']['last_connected']=time.time()
            s['profile'].pop('error',None)
            if pid!='simulator':self.store.save_profile(s['profile'])
        elif kind=='disconnected':
            if not s['manual']:
                self._retry(s)
        elif kind=='node':
            self.store.node(pid,data)
        elif kind=='section':
            self._update_snapshot_section(s,data['section'],data['value'])
            self._cache_snapshot(pid,s['snapshot'])
        elif kind=='packet':
            decoded=data.get('decoded',{})
            port=decoded.get('portnum','')
            if port=='TEXT_MESSAGE_APP':
                text=decoded.get('text')
                if text is None:
                    text=base64.b64decode(decoded.get('payload','')).decode('utf-8',errors='replace')
                now=time.time();rx=data.get('rxTime') or now
                timestamp=now if abs(now-rx)<2 else rx
                self.store.message(pid,data.get('id',0),data.get('from',0),data.get('to',0),data.get('channel',0),text,
                                   timestamp,metadata={'snr':data.get('rxSnr'),'rssi':data.get('rxRssi'),
                                   'hop_start':data.get('hopStart'),'hop_limit':data.get('hopLimit'),'reply_id':decoded.get('replyId',0),'pki':data.get('pkiEncrypted',False)})
                if pid==self.active and self.page=='Chat':
                    self.store.mark_read(pid,self.peer,self.channel)
            elif port=='ROUTING_APP':
                error=decoded.get('routing',{}).get('errorReason','NONE')
                status='Acknowledged' if error in ('NONE',0) else 'Failed: '+str(error)
                request=int(decoded.get('requestId',0))
                self._pending_acks[(pid,request)]=status
                if len(self._pending_acks)>500:
                    self._pending_acks.pop(next(iter(self._pending_acks)))
                self.store.ack(pid,request,status)
            elif port!='ADMIN_APP':
                self.store.event(pid,port,data)
                if port in ('TRACEROUTE_APP','POSITION_APP'):
                    names={n['num']:n.get('user',{}).get('longName',str(n['num'])) for n in self.store.nodes(pid)}
                    self.notification={'message':'Traceroute response' if port=='TRACEROUTE_APP' else 'Position response',
                                       'details':self._event_summary(port,data,names),'packet':data}
                    self.toast.emit(self.notification['message']+' received · open Activity for details')
                if port=='WAYPOINT_APP':
                    waypoint=decoded.get('waypoint')
                    if waypoint:
                        self.store.waypoint(pid,waypoint,data.get('from',0))
        elif kind=='notification':
            self.notification=data
            self.store.event(pid,'notification',data)
            self.toast.emit(data.get('message') or 'Radio notification received')
        elif kind=='log':
            self.store.event(pid,'log',data)
        elif kind=='error':
            operation=data['operation']
            if operation=='connect':
                s['profile']['error']=data['message']
                self._retry(s)
            if operation.startswith(('read:','write:')) or operation=='write_all':
                self.settings_loading=False
                self.settings_error=data['message']
            self.toast.emit(data['message'])
        elif kind=='result':
            op=data['operation'];value=data['value']
            if op=='send':
                self.store.message(pid,value['packet_id'],value['sender'],value['destination'],value['channel'],value['text'],
                    timestamp=value['timestamp'],
                    status=self._pending_acks.pop((pid,value['packet_id']),'Awaiting acknowledgement'),outgoing=True,metadata={'reply_id':value['reply_id']})
                key=f"{pid}:{0 if value['destination']==4294967295 else value['destination']}:{value['channel']}"
                if self.drafts.get(key)==value['text']:
                    self.drafts[key]=''
                    self.store.put('drafts',self.drafts)
            elif op.startswith(('read:','write:')):
                section=op.split(':',1)[1]
                self._update_snapshot_section(s,section,value)
                self._cache_snapshot(pid,s['snapshot'])
                if pid==self.active and section==self.settings_section:
                    self.settings_message=new_message(section)
                    json_format.ParseDict(value,self.settings_message)
                    self.settings_original=self.settings_message.SerializeToString()
                    self.settings_loading=False
                    self.settings_error=''
                    self.invalid_fields={}
                if pid==self.active:self._stash_settings()
                if op.startswith('write:'):
                    self.toast.emit('Settings saved and verified on the radio')
            elif op=='write_all':
                for section,result in value.items():
                    self._update_snapshot_section(s,section,result)
                    message=new_message(section);json_format.ParseDict(result,message)
                    raw=message.SerializeToString()
                    self.settings_drafts[(pid,section)]={'value':raw,'original':raw,'errors':{}}
                if pid==self.active:
                    self.settings_loading=False;self._restore_settings(self.settings_section)
                self.toast.emit('All staged settings saved and verified on the radio')
            elif op=='scan':
                self.notification={'message':'Available devices','devices':value}
            elif op=='probe':
                self.toast.emit('Connection test successful: '+value)
            elif op=='ble_pair':
                self.toast.emit('Bluetooth pairing completed. You can connect the radio now.')
            elif op=='export_channels':
                self.qr_url=value
            elif op.startswith('command:'):
                self.toast.emit(value.get('message','Completed'))
                if 'text' in value:
                    self.notification={'message':op.split(':')[1],'text':value['text']}
                if value.get('node_change'):
                    change=value['node_change'];num=int(change['num'])
                    node=next((n for n in self.store.nodes(pid) if n['num']==num),None)
                    if change.get('remove'):
                        self.store.execute('DELETE FROM nodes WHERE profile=? AND num=?',(pid,num))
                    elif node:
                        node.update(change['patch']);self.store.node(pid,node)
            elif op=='upstream':
                self.notification={'message':'Official release check','releases':value}
            elif op=='import':
                self.toast.emit('Channels imported and verified')
                self.import_preview=[]
        self.dirty()

    def _retry(self,s):
        s['retry']+=1
        s['status']='Reconnecting'
        s['next_retry']=time.time()+min(60,2**min(s['retry'],6))

    def _update_snapshot_section(self,s,section,value):
        snap=s['snapshot']
        if section.startswith('channel.'):
            index=int(section.split('.')[1])
            channels=snap.setdefault('channels',[])
            while len(channels)<=index:
                channels.append({})
            channels[index]=value
        elif section!='user':
            group,name=section.split('.')
            snap.setdefault(group,{})[name]=value
        elif snap.get('my_num'):
            nodes=self.store.nodes(s['profile']['id'])
            node=next((n for n in nodes if n['num']==snap['my_num']),{'num':snap['my_num']})
            node['user']=value
            self.store.node(s['profile']['id'],node)

    def _radio(self):
        s=self.sessions.get(self.active)
        if not s or s['status']!='Connected':
            raise ValueError('Connect a radio first')
        return s['radio']

    def start_demo(self):
        from .simulator import RadioSimulator,SerialSimulator
        if not self.simulator:
            if self.demo_transport=='ble':
                from .virtualble import VirtualBLESimulator
                self.simulator=VirtualBLESimulator()
            else:self.simulator=SerialSimulator() if self.demo_transport=='serial' else RadioSimulator()
        pid='simulator'
        if pid not in self.sessions:
            self._register({'id':pid,'name':'Local simulator','transport':'simulator' if self.demo_transport=='tcp' else self.demo_transport,'address':self.simulator.address})
        self._stash_settings()
        self.active=pid
        self.settings_message=None;self.settings_original=None;self.settings_loading=False
        self._restore_settings(self.settings_section)
        self._connect(pid)

    @pyqtSlot(str,str)
    def dispatch(self,action,payload='{}'):
        try:
            a=json.loads(payload or '{}')
            self._dispatch(action,a)
        except (Exception,SystemExit) as error:
            self.toast.emit(str(error) or type(error).__name__)
        self.dirty()

    def _dispatch(self,action,a):
        if action=='demo':
            self.start_demo()
        elif action=='page':
            self.page=a['name']
            if self.page=='Chat':self.store.mark_read(self.active,self.peer,self.channel)
        elif action=='add_profile':
            self._stash_settings()
            transport=a['transport']; address=a['address'].strip()
            if transport not in ('serial','tcp','http','ble') or not address:
                raise ValueError('Select a connection type and enter its address')
            existing=next((p['profile'] for p in self.sessions.values() if p['profile']['transport']==transport and p['profile']['address']==address),None)
            if existing:
                self._dispatch('select_profile',{'id':existing['id']})
                self._connect(existing['id'])
                return
            profile={'id':uuid.uuid4().hex[:12],'name':a.get('name','').strip() or address,'transport':transport,'address':address}
            self.store.save_profile(profile)
            self._register(profile)
            self.active=profile['id']
            self.settings_message=None;self.settings_original=None;self.settings_loading=False
            self.store.put('active',self.active)
            self._connect(self.active)
        elif action=='edit_profile':
            pid=a['id'];session=self.sessions[pid]
            transport=a.get('transport',session['profile']['transport']);address=a.get('address',session['profile']['address']).strip()
            if transport not in ('serial','tcp','http','ble') or not address:raise ValueError('Select a connection type and enter its address')
            self._dispatch('disconnect',{'id':pid})
            changed=(transport,address)!=(session['profile']['transport'],session['profile']['address'])
            session['profile'].update(name=a.get('name','').strip() or address,transport=transport,address=address)
            self.store.save_profile(session['profile'])
            if changed:
                session['snapshot']={}
                self.settings_drafts={key:value for key,value in self.settings_drafts.items() if key[0]!=pid}
            if pid==self.active:self.settings_message=None;self.settings_original=None;self.settings_loading=False
            self._connect(pid)
        elif action=='default_profile':
            pid=a['id']
            if pid and pid not in self.sessions:raise ValueError('Unknown connection')
            self.store.put('default_profile',pid)
        elif action=='probe':
            profile={'transport':a['transport'],'address':a['address'].strip()}
            def probe():
                radio=Radio(lambda *event:None,timeout=10)
                try:
                    radio.connect(profile)
                    return f"!{radio.snapshot()['my_num']:08x}"
                finally:radio.close()
            self._submit('probe',probe)
        elif action=='select_profile':
            self._stash_settings()
            self.active=a['id']
            self.store.put('active',self.active)
            self.peer=0;self.channel=0
            self.settings_message=None;self.settings_original=None;self.settings_loading=False
            self._restore_settings(self.settings_section)
        elif action=='connect':
            self._connect(a.get('id',self.active))
        elif action in ('disconnect','forget'):
            pid=a.get('id',self.active)
            s=self.sessions[pid]
            s['manual']=True;s['generation']+=1;s['status']='Offline'
            radio=s['radio'];s['radio']=None
            if radio:
                s['closing']=self.pool.submit(radio.close)
            if action=='forget':
                self.store.execute('DELETE FROM profiles WHERE id=?',(pid,))
                self.store.clear_profile(pid)
                self.settings_drafts={key:value for key,value in self.settings_drafts.items() if key[0]!=pid}
                self.drafts={key:value for key,value in self.drafts.items() if not key.startswith(pid+':')}
                self.store.put('drafts',self.drafts)
                self.settings_message=None;self.settings_original=None
                del self.sessions[pid]
                self.active=next(iter(self.sessions),'')
        elif action=='scan':
            kind=a.get('transport','serial')
            self.notification={'devices':[]}
            known=[s['profile']['address'] for s in self.sessions.values() if s['profile']['transport']=='serial' and s['profile'].get('last_connected')]
            def scan():
                if kind=='serial':
                    from serial.tools.list_ports import comports
                    from .discovery import serial_devices
                    return serial_devices(comports(),known)
                from .ble import NativeBLEInterface
                return [{'name':d.name or d.address,'address':d.address,'likely':True,'hint':'Meshtastic Bluetooth service'} for d in NativeBLEInterface.scan()]
            self._submit('scan',scan)
        elif action=='ble_pair':
            from .ble import pair_bluez
            address=a['address'];pin=a['pin']
            self._submit('ble_pair',lambda:pair_bluez(address,pin))
        elif action=='chat':
            self.peer=int(a.get('peer',0));self.channel=int(a.get('channel',0));self.message_offset=0
            self.store.mark_read(self.active,self.peer,self.channel)
        elif action=='draft':
            self.drafts[self._chat_key()]=a['text']
            self.store.put('drafts',self.drafts)
        elif action=='send':
            radio=self._radio();text=a['text'];dest=self.peer or 4294967295;channel=self.channel;reply=int(a.get('reply',0))
            self.drafts[self._chat_key()]=text
            self.store.put('drafts',self.drafts)
            self._submit('send',lambda:radio.send_text(text,dest,channel,reply))
        elif action=='search':
            self.search=a.get('text','')
            self.message_offset=0
        elif action=='older':
            self.message_offset+=100
        elif action=='newer':
            self.message_offset=max(0,self.message_offset-100)
        elif action=='delete_messages':
            self.store.delete_messages(self.active,self.peer,self.channel)
        elif action=='delete_message':
            self.store.execute('DELETE FROM messages WHERE profile=? AND rowid=?',(self.active,int(a['id'])))
        elif action=='clear_data':
            self.store.clear_profile(self.active)
        elif action=='clear_all_data':
            for pid in list(self.sessions):self._dispatch('disconnect',{'id':pid})
            self.sessions={};self.active='';self.peer=0;self.channel=0;self.drafts={};self.settings_drafts={}
            self.settings_message=None;self.settings_original=None;self.settings_error='';self.settings_loading=False
            self.qr_url='';self.import_url='';self.import_preview=[];self.notification={};self._pending_acks={}
            self.store.clear_all()
            self.navigate.emit('Connections')
        elif action=='clear_messages':
            self.store.execute('DELETE FROM messages WHERE profile=?',(self.active,))
        elif action=='reconfigure':
            pid=self.active
            self._dispatch('disconnect',{'id':pid})
            self._connect(pid)
        elif action=='node':
            self.selected_node=int(a['num'])
        elif action=='node_filters':
            current={} if a.get('reset') else self.store.get('node_filters',{})
            if 'key' in a:
                key=a['key'];value=a['value']
                if key.endswith(('_min','_max')) and value not in ('',None):
                    value=float(value)
                    if not __import__('math').isfinite(value):raise ValueError('Filter must be a finite number')
                if value is None or value=='':current.pop(key,None)
                else:current[key]=value
            self.store.put('node_filters',current)
        elif action=='waypoint_details':
            waypoint=next((w for w in self.store.waypoints(self.active) if int(w['id'])==int(a['id'])),{})
            snap=self.sessions.get(self.active,{}).get('snapshot',{})
            local=next((n for n in self.store.nodes(self.active) if n['num']==snap.get('my_num')),None)
            coords=node_tools.coordinate({'position':waypoint})
            local_coords=node_tools.coordinate(local) if local else None
            if coords and local_coords:
                distance,bearing=node_tools.distance_bearing(local_coords,coords)
                waypoint=dict(waypoint,distance_m=round(distance),bearing_degrees=round(bearing))
            self.notification={'message':'Waypoint','waypoint':waypoint}
            self.navigate.emit('Activity')
        elif action=='locate_host':
            try:from PyQt5.QtPositioning import QGeoPositionInfoSource
            except ImportError:
                raise ValueError('Computer location requires the optional Qt Positioning package') from None
            source=QGeoPositionInfoSource.createDefaultSource(self)
            if source is None:raise ValueError('This computer has no available location provider')
            self.location_source=source
            def located(info):
                coordinate=info.coordinate()
                self.notification={'message':'Computer location','latitude':coordinate.latitude(),'longitude':coordinate.longitude()}
                self.dirty();source.deleteLater();self.location_source=None
            source.positionUpdated.connect(located)
            source.updateTimeout.connect(lambda:self.toast.emit('No location fix received'))
            source.requestUpdate(15000)
        elif action=='setting_load':
            section=a['section'];radio=self._radio()
            self._stash_settings()
            self.settings_section=section
            if a.get('discard'):self.settings_drafts.pop((self.active,section),None)
            if not a.get('discard') and self._restore_settings(section):return
            self.settings_loading=True;self.settings_error='';self.invalid_fields={}
            self.settings_message=None;self.settings_original=None
            self._submit('read:'+section,lambda:radio.read_section(section))
        elif action=='setting_edit':
            if self.settings_message is None:
                raise ValueError('Load settings first')
            try:
                set_field(self.settings_message,a['path'],a['value'])
                if self.settings_section=='config.security' and a['path']=='private_key' and self.settings_message.private_key:
                    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
                    from cryptography.hazmat.primitives import serialization
                    key=X25519PrivateKey.from_private_bytes(self.settings_message.private_key)
                    self.settings_message.public_key=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
                self.invalid_fields.pop(a['path'],None)
                self.settings_error='\n'.join(self.invalid_fields.values())
            except Exception as error:
                self.invalid_fields[a['path']]='Invalid '+a['path']+': '+str(error)
                self.settings_error='\n'.join(self.invalid_fields.values())
                raise ValueError(self.settings_error) from error
        elif action=='setting_json':
            message=new_message(self.settings_section)
            json_format.ParseDict(json.loads(a['text']),message)
            self.settings_message=message
            self.settings_error='';self.invalid_fields={}
        elif action=='setting_discard':
            if self.settings_original is not None:
                self.settings_message.ParseFromString(self.settings_original)
                self.settings_error=''
                self.invalid_fields={}
        elif action=='setting_discard_all':
            self._stash_settings()
            for (pid,section),draft in self.settings_drafts.items():
                if pid==self.active:draft.update(value=draft['original'],errors={})
            self._restore_settings(self.settings_section)
        elif action=='setting_save_all':
            radio=self._radio();pending=self._pending_settings();values={}
            for section in pending:
                draft=self.settings_drafts[(self.active,section)]
                if draft['errors']:raise ValueError('Fix invalid fields in '+section)
                message=new_message(section);message.ParseFromString(draft['value'])
                validate_section(section,message);values[section]=to_dict(message,True)
            if not values:raise ValueError('No staged settings to save')
            self.settings_loading=True
            self._submit('write_all',lambda:radio.write_sections(values))
        elif action=='setting_save':
            radio=self._radio();section=self.settings_section
            if self.settings_error:raise ValueError('Fix the invalid setting before saving')
            if self.settings_message is None:
                raise ValueError('Load settings first')
            validate_section(section,self.settings_message)
            value=to_dict(self.settings_message,True)
            self.settings_loading=True
            self._submit('write:'+section,lambda:radio.write_section(section,value))
        elif action=='generate_channel_key':
            if not self.settings_section.startswith('channel.') or self.settings_message is None:
                raise ValueError('Open a channel first')
            bits=int(a.get('bits',256))
            if bits not in (0,8,128,256):raise ValueError('Choose 0, 8, 128 or 256 bits')
            self.settings_message.settings.psk=secrets.token_bytes(bits//8) if bits>=128 else b'\x01' if bits==8 else b''
        elif action=='generate_identity':
            if self.settings_section!='config.security' or self.settings_message is None:
                raise ValueError('Open Security settings first')
            from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
            from cryptography.hazmat.primitives import serialization
            key=X25519PrivateKey.generate()
            self.settings_message.private_key=key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
            self.settings_message.public_key=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
            self.toast.emit('New identity staged. Back it up, then save to apply.')
        elif action=='export_channels':
            radio=self._radio()
            indices=a.get('indices',[0] if a.get('primary') else list(range(8)))
            indices=sorted(set(int(i) for i in indices));add=bool(a.get('add'))
            if not indices or any(i<0 or i>7 for i in indices):raise ValueError('Select at least one channel, from 0 to 7')
            def share():
                chans=[radio.read_section('channel.'+str(i)) for i in indices]
                return encode_channel_url(chans,radio.read_section('config.lora'),add=add)
            self._submit('export_channels',share)
        elif action=='import_preview':
            from urllib.parse import urlsplit,parse_qs
            obj=decode_channel_url(a['url'])
            self.import_url=a['url'].strip()
            add=parse_qs(urlsplit(self.import_url).query).get('add')==['true']
            used={int(c.get('index',i)) for i,c in enumerate(self.sessions.get(self.active,{}).get('snapshot',{}).get('channels',[])) if c.get('role') not in ('DISABLED',0)}
            slots=[i for i in range(1,8) if i not in used] if add else list(range(8))
            self.import_preview=[{'index':i,'target':slots[i] if i<len(slots) else -1,'name':ch.name,'key_bytes':len(ch.psk)} for i,ch in enumerate(obj.settings)]
            self.import_lora=obj.HasField('lora_config') and not add
        elif action=='import_target':
            index=int(a['index']);target=int(a['target'])
            if not 0<=index<len(self.import_preview) or not -1<=target<8:raise ValueError('Invalid import channel')
            self.import_preview[index]['target']=target
        elif action=='import_lora':
            self.import_lora=bool(a['value'])
        elif action=='import_apply':
            from .radio import plan_channel_import
            radio=self._radio();obj=decode_channel_url(self.import_url)
            plan=plan_channel_import(obj,[c['target'] for c in self.import_preview],bool(a.get('replace',False)),self.import_lora)
            pid=self.active;generation=self.sessions[pid]['generation']
            def import_channels():
                values=radio.write_sections({section:to_dict(payload,True) for section,payload in plan})
                for section,value in values.items():
                    self.delivered.emit(pid,generation,'section',{'section':section,'value':value})
            self._submit('import',import_channels)
        elif action=='command':
            radio=self._radio();name=a['name'];args=a.get('args',{})
            self._submit('command:'+name,lambda:radio.command(name,args))
        elif action=='verify_reply':
            from meshtastic.protobuf import admin_pb2
            types=admin_pb2.KeyVerificationAdmin
            request=self.notification.get('key_verification_number_request',{})
            final=self.notification.get('key_verification_final',{})
            nonce=(request or final).get('nonce')
            if nonce is None:raise ValueError('No pending verification request')
            if request:
                number=int(a['number'])
                if not 0<=number<=999999:raise ValueError('Enter a six-digit security number')
                msgtype=types.PROVIDE_SECURITY_NUMBER
            else:
                number=0;msgtype=types.DO_VERIFY if a.get('accept') else types.DO_NOT_VERIFY
            self._dispatch('command',{'name':'verify_key','args':{'type':msgtype,'nonce':nonce,'number':number}})
            self.notification={}
        elif action=='copy':
            QApplication.clipboard().setText(a['text'])
            self.toast.emit('Copied')
        elif action=='preference':
            key=a['key']
            if key not in ('theme','clock12','online_maps','tile_url','tile_attribution','language','pinned_commands','pinned_command_groups','node_sort','node_sort_desc'):
                raise ValueError('Unknown preference')
            if key=='language' and a['value'] not in [v['code'] for v in i18n.locales()]:
                raise ValueError('Unknown language')
            self.store.put(key,a['value'])
        elif action=='export':
            self._export(a['kind'])
        elif action=='backup_reminder':
            days=int(a.get('days',7))
            self.store.put('backup_reminder:'+self.active,time.time()+max(1,days)*86400)
            if a.get('open'):
                self._dispatch('setting_load',{'section':'config.security'})
                self.navigate.emit('Settings')
        elif action=='print_identity':
            if self.settings_section!='config.security' or self.settings_message is None:
                raise ValueError('Read Security settings before printing an identity backup')
            from PyQt5.QtPrintSupport import QPrinter,QPrintDialog
            from PyQt5.QtGui import QTextDocument
            from html import escape
            value=to_dict(self.settings_message)
            doc=QTextDocument()
            doc.setHtml('<h1>MeshDesk identity backup</h1><p>Keep this backup private.</p><h2>Public key</h2><p>'+escape(value.get('public_key',''))+'</p><h2>Private key</h2><p>'+escape(value.get('private_key',''))+'</p>')
            printer=QPrinter()
            if QPrintDialog(printer).exec_():doc.print_(printer)
        elif action=='import_settings_file':
            path,_=QFileDialog.getOpenFileName(None,'Import settings','','JSON files (*.json)')
            if path:
                data=json.loads(Path(path).read_text())
                section=data['section']
                self._stash_settings()
                self.invalid_fields={};self.settings_error=''
                self.settings_section=section
                self.settings_message=new_message(section)
                json_format.ParseDict(data['value'],self.settings_message)
                self.settings_original=b'pending-import'
                self.toast.emit('Imported into draft. Review the fields, then save to the radio.')
        elif action=='check_updates':
            from .upstream import latest_releases
            self._submit('upstream',latest_releases)
        elif action=='dismiss_notification':
            self.notification={}
        else:
            raise ValueError('Unknown operation: '+action)

    def _export(self,kind):
        path,_=QFileDialog.getSaveFileName(None,'Export '+kind,'meshdesk-'+kind+('.svg' if kind=='qr' else '.json'))
        if not path:
            return
        if kind=='qr':
            if not self.qr_url:raise ValueError('Generate a channel link first')
            import qrcode
            from qrcode.image.svg import SvgPathImage
            content=qrcode.make(self.qr_url,image_factory=SvgPathImage).to_string()
        elif kind in ('settings','identity'):
            if self.settings_message is None:raise ValueError('Load settings first')
            content=json.dumps({'section':self.settings_section,'value':to_dict(self.settings_message,True)},indent=2).encode()
        else:
            content=json.dumps(self.store.nodes(self.active) if kind=='nodes' else self.store.events(self.active,2000) if kind=='activity' else [dict(r) for r in self.store.execute('SELECT * FROM messages WHERE profile=? ORDER BY timestamp',(self.active,))],indent=2).encode()
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(content)
        os.chmod(path,0o600)
        if kind=='identity':self.store.put('backup_reminder:'+self.active,time.time()+365*86400)
        self.toast.emit('Exported to '+path)

    def close(self):
        with contextlib.suppress(TypeError):QApplication.instance().paletteChanged.disconnect(self.dirty)
        self._closing=True
        self.maintenance.stop()
        self.publish_timer.stop()
        for s in self.sessions.values():
            s['manual']=True
            if s['radio']:
                self.pool.submit(s['radio'].close)
        self.pool.shutdown(wait=True,cancel_futures=True)
        if self.simulator:self.simulator.close()
        self.store.close()
