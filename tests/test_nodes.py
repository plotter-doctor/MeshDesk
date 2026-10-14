import time
from meshdesk.nodes import matches,distance_bearing
from meshdesk.schema import new_message,set_field,fields


def test_filters_cover_unknowns_ranges_and_metadata():
    node={'num':16,'user':{'longName':'Garden','shortName':'GRDN','role':'CLIENT','hwModel':'HELTEC_V3'},'hopsAway':2,'lastHeard':time.time(),'snr':-3,'deviceMetrics':{'batteryLevel':75},'isFavorite':True}
    assert matches(node,{'name':'!00000010','favorite':True,'hops_max':2,'roles':'ROUTER,CLIENT'})
    assert not matches(node,{'battery_min':80})
    assert not matches(node,{'voltage_min':1})
    assert not matches(node,{'unknown_hops':True})
    assert matches(node,{'snr_min':-4,'snr_max':0,'age_max':1})
    distance,bearing=distance_bearing((0,0),(0,1))
    assert 111000<distance<112000 and bearing==90


def test_ipv4_wire_byte_order():
    obj=new_message('config.network')
    set_field(obj,'ipv4_config.ip','192.0.2.10')
    assert obj.ipv4_config.ip==int.from_bytes(bytes([192,0,2,10]),'little')
    assert next(f for f in fields(obj) if f['path']=='ipv4_config.ip')['value']=='192.0.2.10'
