"""Read-only release check, never a silent dependency update."""
import json
import urllib.request
from pathlib import Path


def latest_releases():
    result=[]
    pins=json.loads((Path(__file__).parent/'resources/upstream.json').read_text(encoding='utf-8'))
    for repo in ('web','python'):
        pinned=pins[repo]['tag']
        url='https://api.github.com/repos/meshtastic/'+repo+'/releases/latest'
        req=urllib.request.Request(url,headers={'User-Agent':'MeshDesk/0.1 release-check','Accept':'application/vnd.github+json'})
        with urllib.request.urlopen(req,timeout=10) as response:
            data=json.load(response)
        result.append({'project':repo,'pinned':pinned,'latest':data['tag_name'],
                       'url':data['html_url'],'update_available':data['tag_name']!=pinned})
    return result
