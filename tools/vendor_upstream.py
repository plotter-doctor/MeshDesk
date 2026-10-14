#!/usr/bin/env python3
"""Import official localization data and record a reviewable source inventory.

Never installs dependencies or runs upstream code. Run against a checked-out,
reviewed release with --write to accept it; omit --write to report differences.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
RESOURCES=ROOT/'src/meshdesk/resources'


def flatten(value,prefix=''):
    out={}
    for key,item in value.items():
        path=prefix+key
        if isinstance(item,dict):out.update(flatten(item,path+'.'))
        elif isinstance(item,str):out[path]=item
    return out


def inventory(source):
    paths=[]
    for base in ('apps/web/src/pages','apps/web/src/components','apps/web/src/validation','packages/protobufs/meshtastic'):
        for path in (source/base).rglob('*'):
            if path.is_file() and path.suffix in ('.tsx','.ts','.proto') and '.test.' not in path.name and '__mocks__' not in str(path):paths.append(path)
    return {str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--write',action='store_true',help='Accept this source baseline and import its translations')
    args=parser.parse_args()
    source=args.source.resolve()
    current=inventory(source)
    if not current:parser.error('No web source files found')
    baseline=ROOT/'upstream/web-inventory.json'
    previous=json.loads(baseline.read_text(encoding='utf-8')) if baseline.exists() else {}
    changes={'added':sorted(current.keys()-previous.keys()),'removed':sorted(previous.keys()-current.keys()),
             'changed':sorted(p for p in current.keys() & previous.keys() if current[p]!=previous[p])}
    print(json.dumps(changes,indent=2))
    if not args.write:return int(any(changes.values()))
    RESOURCES.mkdir(parents=True,exist_ok=True)
    target=RESOURCES/'locales';target.mkdir(exist_ok=True)
    for folder in (source/'apps/web/public/i18n/locales').iterdir():
        if not folder.is_dir():continue
        catalog={}
        for path in folder.glob('*.json'):
            catalog.update(flatten(json.loads(path.read_text(encoding='utf-8')),path.stem+'.'))
        (target/(folder.name+'.json')).write_text(json.dumps(catalog,ensure_ascii=False,sort_keys=True,indent=2)+'\n', encoding='utf-8')
    baseline.parent.mkdir(exist_ok=True)
    baseline.write_text(json.dumps(current,sort_keys=True,indent=2)+'\n', encoding='utf-8')
    print('Imported translations and recorded',len(current),'source files. Review the diff before accepting the upgrade.')
    return 0


if __name__=='__main__':raise SystemExit(main())
