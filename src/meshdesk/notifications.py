"""Readable device notifications without losing their diagnostic payload."""
import time
from . import i18n


def present(notification,language='en'):
    def t(key,**values):
        result=i18n.catalog(language).get(key,i18n.catalog().get(key,key))
        for name,value in values.items():result=result.replace('{{'+name+'}}',str(value))
        return result
    for suffix in ('number_inform','number_request','final'):
        data=notification.get('key_verification_'+suffix)
        if data is not None:
            kind={'number_inform':'inform','number_request':'request','final':'final'}[suffix]
            return {'title':t('dialog.keyVerification.'+kind+'.title'),
                    'description':t('dialog.keyVerification.'+kind+'.description',name=data.get('remote_longname','')),
                    'code':str(data.get('security_number',0)).zfill(6) if suffix=='number_inform' else data.get('verification_characters',''),
                    'rows':[]}
    point=notification.get('waypoint')
    if point:
        rows=[]
        def add(key,value):rows.append({'name':t('map.waypointDetail.'+key),'value':str(value)})
        add('latitude',point.get('latitudeI',point.get('latitude_i',0))*1e-7)
        add('longitude',point.get('longitudeI',point.get('longitude_i',0))*1e-7)
        for name,field in (('createdDate','created'),('updated','updated'),('expires','expire')):
            if point.get(field):add(name,time.strftime('%Y-%m-%d %H:%M',time.localtime(point[field])))
        if point.get('distance_m') is not None:add('distance',str(point['distance_m'])+' m')
        if point.get('bearing_degrees') is not None:add('bearing',str(point['bearing_degrees'])+'°')
        locked=point.get('lockedTo',point.get('locked_to',0))
        if locked:add('lockedTo',f'!{locked:08x}')
        if point.get('sender'):add('createdBy',f"!{point['sender']:08x}")
        return {'title':point.get('name','Waypoint'),'description':point.get('description',''),'code':'','rows':rows}
    return {}
