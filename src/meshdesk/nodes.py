"""Node presentation and filters, independent of Qt and transport."""
import math
import time
from .mapview import coordinate

RANGES={
    'hops':('Hops','hopsAway'), 'snr':('SNR (dB)','snr'),
    'age':('Last heard (hours ago)','lastHeard'),
    'battery':('Battery (%)','deviceMetrics.batteryLevel'),
    'voltage':('Voltage (V)','deviceMetrics.voltage'),
    'channel':('Channel utilization (%)','deviceMetrics.channelUtilization'),
    'air':('Transmit airtime (%)','deviceMetrics.airUtilTx')}


def at(node,path):
    for part in path.split('.'):
        if not isinstance(node,dict):return None
        node=node.get(part)
    return node


def matches(node,filters):
    user=node.get('user',{})
    name=filters.get('name','').lower().strip().lstrip('!')
    if name and not any(name in str(v).lower() for v in (user.get('longName',''),user.get('shortName',''),node['num'],f"{node['num']:08x}")):return False
    for key,path in (('favorite','isFavorite'),('mqtt','viaMqtt'),('ignored','isIgnored')):
        if filters.get(key) is not None and bool(node.get(path))!=filters[key]:return False
    if filters.get('unheard') is not None and (not bool(node.get('lastHeard')))!=filters['unheard']:return False
    if filters.get('unknown_hops') is not None and ('hopsAway' not in node)!=filters['unknown_hops']:return False
    for key,(_,path) in RANGES.items():
        low=filters.get(key+'_min');high=filters.get(key+'_max')
        if low in ('',None) and high in ('',None):continue
        value=at(node,path)
        if value is None:return False
        if key=='age':value=max(0,time.time()-value)/3600
        if key=='voltage':value=abs(value)
        if low not in ('',None) and value<float(low):return False
        if high not in ('',None) and value>float(high):return False
    for key,path in (('roles','role'),('hardware','hwModel')):
        allowed=[v.strip().upper() for v in filters.get(key,'').split(',') if v.strip()]
        if allowed and str(user.get(path,'CLIENT' if key=='roles' else 'UNSET')).upper() not in allowed:return False
    return True


def distance_bearing(start,end):
    lat1,lon1=map(math.radians,start);lat2,lon2=map(math.radians,end)
    a=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    distance=6371000*2*math.asin(min(1,math.sqrt(a)))
    bearing=math.degrees(math.atan2(math.sin(lon2-lon1)*math.cos(lat2),math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(lon2-lon1)))%360
    return distance,bearing


def details(node,local=None):
    rows=[]
    values=[('MAC address','user.macaddr'),('Messageable','user.isUnmessagable'),('Role','user.role'),('Hardware','user.hwModel'),('SNR (dB)','snr'),('Hops','hopsAway'),
            ('Battery (%)','deviceMetrics.batteryLevel'),('Voltage (V)','deviceMetrics.voltage'),
            ('Channel utilization (%)','deviceMetrics.channelUtilization'),('Transmit airtime (%)','deviceMetrics.airUtilTx'),
            ('Public key','user.publicKey'),('Identity verified','isKeyManuallyVerified')]
    for name,path in values:
        value=at(node,path)
        if name=='Messageable':value=not bool(value)
        if value is not None:rows.append({'name':name,'value':str(round(value,2) if isinstance(value,float) else value)})
    coord=coordinate(node)
    if coord:
        rows.append({'name':'Position','value':f'{coord[0]:.6f}, {coord[1]:.6f}'})
        if local and coordinate(local):
            distance,bearing=distance_bearing(coordinate(local),coord)
            rows.append({'name':'Distance / bearing','value':f'{distance/1000:.2f} km / {bearing:.0f}°'})
    return rows


def enum_choices():
    from meshtastic.protobuf import config_pb2, mesh_pb2
    return {'roles':[v.name for v in config_pb2.Config.DeviceConfig.Role.DESCRIPTOR.values],
            'hardware':[v.name for v in mesh_pb2.HardwareModel.DESCRIPTOR.values]}


SORT_FIELDS={'name':'name','hops':'hopsAway','heard':'lastHeard','snr':'snr','hardware':'user.hwModel','mac':'user.macaddr'}


def sorted_nodes(nodes,key='name',descending=False):
    path=SORT_FIELDS.get(key,'name')
    def value(n):
        v=at(n,path)
        if v is None:return (1,0)
        return (0,v.casefold() if isinstance(v,str) else v)
    return sorted(nodes,key=value,reverse=descending)
