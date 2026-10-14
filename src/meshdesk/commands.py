"""The official command groups, with native page and connection destinations."""
from . import i18n


def entries(profiles,language='en',pinned=()):
    en=i18n.catalog();local=i18n.catalog(language)
    def t(key):
        key='commandPalette.'+key
        return local.get(key,en.get(key,key))
    groups=[('gotoGroup','goto',[
        ('messages',{'page':'Chat'}),('map',{'page':'Map'}),
        ('config',{'page':'Settings','tab':0}),('nodes',{'page':'Nodes'})]),
        ('manageGroup','manage',[
        ('switchNode',{'page':'Connections'}),('connectNewNode',{'page':'Connections'})]),
        ('contextualGroup','contextual',[
        ('qrGenerator',{'page':'Settings','tab':1}),('qrImport',{'page':'Settings','tab':1}),
        ('scheduleShutdown',{'page':'Settings','tab':2}),('scheduleReboot',{'page':'Settings','tab':2}),
        ('dfuMode',{'command':'dfu'}),('resetNodeDb',{'command':'reset_nodes'}),
        ('disconnect',{'action':'disconnect'}),('factoryResetDevice',{'command':'reset_device'}),
        ('factoryResetConfig',{'command':'reset_config'})]),
        ('debugGroup','debug',[
        ('reconfigure',{'action':'reconfigure'}),('clearAllStoredMessages',{'action':'clear_messages','confirm':True}),
        ('clearAllStores',{'action':'clear_all_data','confirm':True})])]
    result=[]
    for gid,prefix,actions in sorted(groups,key=lambda g:g[0] not in pinned):
        label=t(prefix+'.label')
        for key,data in actions:
            result.append(dict(id=gid+':'+key,group=gid,group_label=label,title=t(prefix+'.command.'+key),**data))
            if key=='switchNode':
                for p in profiles:
                    result.append(dict(id='switch:'+p['id'],group=gid,group_label=label,
                                       title='↳ '+p['name'],action='select_profile',args={'id':p['id']}))
    return result
