from meshdesk.store import Store


def test_history_isolation_paging_and_ack(tmp_path):
    store=Store(tmp_path/'data.sqlite')
    for i in range(620):store.message('a',i+1,1,0xffffffff,0,str(i),timestamp=i+1,outgoing=True)
    store.message('b',1,1,0xffffffff,0,'other profile')
    assert len(store.messages('a',limit=500))==500
    assert store.messages('a',limit=100,offset=600)[0]['text']=='0'
    store.ack('a',620,'Acknowledged')
    assert store.messages('a')[-1]['status']=='Acknowledged'
    store.delete_messages('a')
    assert not store.messages('a') and len(store.messages('b'))==1
    store.close()


def test_waypoint_lock_and_expiry(tmp_path):
    store=Store(tmp_path/'data.sqlite')
    store.waypoint('a',{'id':1,'lockedTo':5,'name':'Locked'},5)
    store.waypoint('a',{'id':1,'name':'Bad overwrite'},6)
    assert store.waypoints('a')[0]['name']=='Locked'
    store.waypoint('a',{'id':1,'expire':1},5)
    assert not store.waypoints('a')
    store.close()
