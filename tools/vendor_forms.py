#!/usr/bin/env python3
"""Extract reviewable form presentation metadata from the pinned official UI.

No upstream JavaScript is executed. Unknown conditional expressions fail the
import so an upstream change cannot silently make a control always editable.
"""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from audit_compatibility import web_forms
from meshdesk.schema import fields,new_message
from meshdesk.i18n import camel


def balanced(text,start,opening='{',closing='}'):
    depth=0;quote='';escape=False
    for i in range(start,len(text)):
        char=text[i]
        if quote:
            if escape:escape=False
            elif char=='\\':escape=True
            elif char==quote:quote=''
            continue
        if char in ('"',"'",'`'):quote=char;continue
        if char==opening:depth+=1
        elif char==closing:
            depth-=1
            if depth==0:return text[start:i+1]
    raise ValueError('Unbalanced upstream form expression')


def extract(source):
    inventory=web_forms(source);result={}
    for filename in sorted({r['source'] for r in inventory}):
        text=(source/filename).read_text(encoding='utf-8')
        rows={r['web_field']:r for r in inventory if r['source']==filename}
        namespace=re.search(r'useTranslation\(\[?"([^"]+)"',text)[1]
        section=next(iter(rows.values()))['section']
        native={camel(f['path']):f for f in fields(new_message(section))}
        group_markers=[]
        for group in re.finditer(r'\{\s*label:\s*t\("([^"]+)"\)',text):
            block=balanced(text,group.start())
            if 'fields:' in block:group_markers.append((group.start(),namespace+'.'+group[1]))
        for match in re.finditer(r'\{\s*type:\s*"([^"]+)"',text):
            block=balanced(text,match.start())
            name=re.search(r'\bname:\s*"([^"]+)"',block)
            if not name or name[1] not in rows:continue
            row=rows[name[1]];path=row['native']
            if path.startswith('command:'):continue
            index=re.search(r'\.(\d+)$',name[1])
            if index:path+='.'+index[1]
            item={'path':path,'web_name':name[1],'type':match[1],
                  'group':next((g for pos,g in reversed(group_markers) if pos<match.start()),''),
                  'disabled':bool(re.search(r'\bdisabled:\s*true',block)),'conditions':[]}
            for key in ('label','description'):
                value=re.search(r'\b'+key+r':\s*t\("([^"]+)"',block)
                if value:item[key]=namespace+'.'+value[1]
            condition=re.search(r'disabledBy:\s*\[',block)
            if condition:
                condition_text=balanced(block,condition.end()-1,'[',']')
                for cond in re.finditer(r'\{[^{}]+\}',condition_text):
                    field=re.search(r'fieldName:\s*"([^"]+)"',cond[0])
                    if not field or field[1] not in native:raise ValueError('Unknown condition: '+cond[0])
                    rule={'path':native[field[1]]['path'],'invert':'invert: true' in cond[0]}
                    selector=re.search(r'selector:\s*([\w.]+)',cond[0])
                    if selector:
                        value=selector[1].split('.')[-1]
                        rule['selector']=int(value) if value.isdigit() else next(
                            c['value'] for c in native[field[1]]['choices'] if c['label']==value)
                    item['conditions'].append(rule)
            numeric_options=re.search(r'enumValue:\s*\{([^{}]+)\}',block)
            if numeric_options:
                item['choices']=[{'label':v,'value':int(v)} for _,v in re.findall(r'(\d+):\s*(\d+)',numeric_options[1])]
            result.setdefault(section,[]).append(item)
    return result


def validation(source):
    """Import scalar Zod constraints; custom cross-field rules live in schema.py."""
    from meshdesk.schema import sections
    groups={camel(s['key'].split('.')[-1]):s['key'] for s in sections() if not s['key'].startswith('channel.')}
    result={}
    for file in sorted((source/'apps/web/src/validation').rglob('*.ts')):
        name={'statusMessage':'statusmessage'}.get(file.stem,file.stem)
        if '.test.' in file.name or name not in groups:continue
        section=groups[name];native=fields(new_message(section))
        text=file.read_text(encoding='utf-8')
        rules={}
        for match in re.finditer(r'(\w+):\s*z\.(?:coerce\.)?(number|string)\(\)(.*?)(?=,\s*\n|\n\s*\})',text,re.S):
            name,kind,chain=match.groups()
            candidates=[f['path'] for f in native if camel(f['path'].split('.')[-1])==name]
            if len(candidates)!=1:continue
            rule={'kind':kind}
            for constraint in ('min','max'):
                found=re.search(r'\.'+constraint+r'\((-?[0-9.]+)',chain)
                if found:rule[constraint]=float(found[1])
            if '.int()' in chain:rule['integer']=True
            if len(rule)>1:rules[candidates[0]]=rule
        if rules:result[section]=rules
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args();result=extract(args.source)
    target=ROOT/'src/meshdesk/resources/web-forms.json'
    if args.write:target.write_text(json.dumps(result,indent=2)+'\n', encoding='utf-8')
    elif not target.exists() or json.loads(target.read_text(encoding='utf-8'))!=result:
        raise SystemExit('Official form presentation changed; review and regenerate metadata')
    limits=validation(args.source);limit_target=ROOT/'src/meshdesk/resources/web-validation.json'
    if args.write:limit_target.write_text(json.dumps(limits,indent=2)+'\n', encoding='utf-8')
    elif not limit_target.exists() or json.loads(limit_target.read_text(encoding='utf-8'))!=limits:
        raise SystemExit('Official validation changed; review and regenerate metadata')
    print(f'{sum(map(len,result.values()))} fields with official grouping, labels and enablement rules')


if __name__=='__main__':main()
