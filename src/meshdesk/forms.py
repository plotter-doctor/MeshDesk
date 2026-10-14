"""Official form order/labels/conditions layered over the live protobuf schema."""
import base64
import json
from functools import lru_cache
from pathlib import Path
from meshtastic.protobuf import config_pb2
from .schema import fields,label
from . import i18n


@lru_cache(maxsize=1)
def metadata():
    return json.loads((Path(__file__).parent/'resources/web-forms.json').read_text())


def value_at(message,path):
    for part in path.split('.'):
        message=message[int(part)] if part.isdigit() else getattr(message,part)
    return message


def disabled(message,info):
    if info.get('disabled'):return True
    for rule in info.get('conditions',[]):
        value=value_at(message,rule['path']);invert=rule.get('invert',False)
        if isinstance(value,bool):
            if value if invert else not value:return True
        elif isinstance(value,int):
            if (value!=rule.get('selector')) if invert else (value==rule.get('selector')):return True
    return False


def present(section,message,language,units=0):
    raw={f['path']:f for f in i18n.enrich(section,fields(message),language)}
    result=[];used=set();previous_group=None
    english=i18n.catalog();localized=i18n.catalog(language)
    def translated(key):return localized.get(key,english.get(key,key))
    for info in metadata().get('channel.0' if section.startswith('channel.') else section,[]):
        path=info['path'];base=path.rsplit('.',1)[0] if path.rsplit('.',1)[-1].isdigit() else path
        if base not in raw:continue
        field=dict(raw[base],path=path,disabled=disabled(message,info))
        used.add(base)
        if path!=base:
            values=value_at(message,base);index=int(path.rsplit('.',1)[-1])
            field.update(kind='bytes',value=base64.b64encode(values[index]).decode() if index<len(values) else '',secret=True)
        if 'label' in info:field['title']=translated(info['label'])
        if 'description' in info:field['description']=translated(info['description'])
        if info.get('choices'):field.update(kind='enum',choices=info['choices'],value=int(field['value']))
        if section=='config.position' and path=='position_flags':
            field.update(kind='bitmask',value=int(field['value']),choices=[
                {'label':translated('config.position.flags.'+i18n.camel(v.name.removeprefix('POS_').lower())),'value':v.number}
                for v in config_pb2.Config.PositionConfig.PositionFlags.DESCRIPTOR.values if v.number])
        if section.startswith('channel.'):
            if path=='role':
                field['disabled']=message.index==0
                field['choices']=[c for c in field['choices'] if c['value'] in ((1,) if message.index==0 else (0,2))]
            if path=='settings.module_settings.position_precision':
                names=['none','metric_km23','metric_km12','metric_km5_8','metric_km2_9','metric_km1_5',
                       'metric_m700','metric_m350','metric_m200','metric_m90','metric_m50','precise']
                if units in (1,'IMPERIAL'):
                    names=['none','imperial_mi15','imperial_mi7_3','imperial_mi3_6','imperial_mi1_8','imperial_mi0_9',
                           'imperial_mi0_5','imperial_mi0_2','imperial_ft600','imperial_ft300','imperial_ft150','precise']
                field.update(kind='enum',value=int(field['value']),choices=[
                    {'label':translated('channels.positionPrecision.options.'+name),'value':value}
                    for name,value in zip(names,[0,*range(10,20),32])])
        group=info.get('group','')
        field['group']=translated(group) if group and group!=previous_group else ''
        previous_group=group
        result.append(field)
    extras=[dict(f,disabled=False,group='') for p,f in raw.items() if p not in used]
    if section.startswith('channel.'):
        for f in extras:
            if f['path']=='index':f['disabled']=True
    if extras:extras[0]['group']=i18n.translate('Advanced',language)
    result.extend(extras)
    return result
