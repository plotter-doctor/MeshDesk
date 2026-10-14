#!/usr/bin/env python3
"""Snapshot the Python protocol schema and map official web form fields.

The form audit proves field availability, not complete product or hardware
parity. Feature workflow status is recorded separately in docs/FEATURES.md.
"""
import argparse
import importlib.metadata
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from meshdesk.schema import sections,fields,new_message
from meshdesk.i18n import camel


def schema():
    result={}
    for section in sections():
        message=new_message(section['key'])
        result[section['key']]=[{k:f[k] for k in ('path','kind','choices')} for f in fields(message)]
    return result


def web_forms(source):
    base=source/'apps/web/src/components/PageComponents'
    groups={camel(s['key'].split('.')[-1]):s['key'] for s in sections() if not s['key'].startswith('channel.')}
    aliases={'LoRa':'lora','MQTT':'mqtt','StatusMessage':'statusmessage'}
    special={('position','latitude'):'command:fixed_position',('position','longitude'):'command:fixed_position',
             ('position','altitude'):'command:fixed_position',('user','nodeId'):'id',
             ('user','hardwareModel'):'hw_model',('user','isUnmessageable'):'is_unmessagable'}
    out=[]
    for path in sorted(base.rglob('*.tsx')):
        if not any(part in ('Settings','ModuleConfig','Channels') for part in path.parts) or '.test.' in path.name:continue
        component=path.parent.name if path.stem=='index' else path.stem
        group=aliases.get(component,component[0].lower()+component[1:])
        section='channel.0' if component=='Channel' else groups.get(group)
        paths={camel(f['path']):f['path'] for f in fields(new_message(section))} if section else {}
        for name in re.findall(r'\bname:\s*"([^"]+)"',path.read_text()):
            native=special.get((group,name),paths.get(re.sub(r'\.\d+$','',name)))
            out.append({'source':str(path.relative_to(source)),'web_field':name,'section':section,'native':native})
    if not out:raise ValueError('No form fields found in upstream source')
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web-source',type=Path)
    parser.add_argument('--accept',action='store_true')
    args=parser.parse_args()
    current=schema();baseline=ROOT/'upstream/python-schema.json'
    if args.accept:baseline.write_text(json.dumps(current,indent=2,sort_keys=True)+'\n')
    elif not baseline.exists() or json.loads(baseline.read_text())!=current:
        print('Python schema changed. Review the schema diff and adapter mappings.');return 1
    forms=web_forms(args.web_source) if args.web_source else json.loads((ROOT/'upstream/web-form-fields.json').read_text())
    missing=[f for f in forms if not f['native']]
    for row in forms:
        if row['native'] and not row['native'].startswith('command:'):
            available={f['path'] for f in current.get(row['section'],[])}
            if row['native'] not in available:missing.append(row)
    if args.accept and args.web_source:
        (ROOT/'upstream/web-form-fields.json').write_text(json.dumps(forms,indent=2)+'\n')
    print(f'Official Python {importlib.metadata.version("meshtastic")}: {len(current)} settings sections')
    print(f'Web form fields: {len(forms)-len(missing)}/{len(forms)} mapped; hardware/workflow parity requires separate validation.')
    if missing:print(json.dumps(missing,indent=2))
    return int(bool(missing))


if __name__=='__main__':raise SystemExit(main())
