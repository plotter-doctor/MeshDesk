"""Official web translations with English fallback for new native controls."""
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT=Path(__file__).parent/'resources/locales'


@lru_cache(maxsize=3)
def catalog(language='en'):
    path=ROOT/(language+'.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def locales():
    from PyQt5.QtCore import QLocale
    return [{'code':p.stem,'name':QLocale(p.stem).nativeLanguageName()+' · '+p.stem} for p in sorted(ROOT.glob('*.json'))]


def translate(text,language):
    if language=='en':return text
    native=native_catalog(language)
    if text in native:return native[text]
    key=native_labels().get(text)
    if key:
        value=catalog(language).get(key,catalog().get(key,text))
        if text=='Last connected':value=value.replace('{{date}}','').rstrip(' :')
        return value
    aliases={'Chat':'Messages','Radio settings':'Settings','Preferences':'Settings','Your mesh':'Nodes',
             'Dark appearance':'Dark','Light appearance':'Light','Owner':'User','Lora':'LoRa'}
    # Keep application preferences distinguishable from radio configuration.
    if text=='Preferences':return 'Preferencje' if language=='pl-PL' else text
    lookup=aliases.get(text,text)
    key=english_index().get(lookup)
    return catalog(language).get(key,lookup) if key else text


@lru_cache(maxsize=1)
def native_labels():
    return json.loads((ROOT.parent/'native-labels.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=3)
def native_catalog(language):
    path=ROOT.parent/'native-locales'/(language+'.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


@lru_cache(maxsize=1)
def english_index():
    return {v:k for k,v in catalog().items() if '{{' not in v}


def camel(name):
    return re.sub(r'_([a-z0-9])',lambda m:m[1].upper(),name)


def enrich(section,fields,language):
    prefix='moduleConfig.' if section.startswith('module.') else 'channels.' if section.startswith('channel.') else 'config.'
    group=camel(section.split('.')[-1]) if '.' in section else section
    english=catalog();localized=catalog(language)
    for field in fields:
        path=camel(field['path'])
        candidates=[prefix+group+'.'+path, prefix+path.removeprefix('settings.'),prefix+group+'.'+path.split('.')[-1]]
        for candidate in candidates:
            if candidate+'.label' in english:
                field['title']=localized.get(candidate+'.label',english[candidate+'.label'])
                field['description']=localized.get(candidate+'.description',english.get(candidate+'.description',''))
                break
        field.setdefault('description','')
    return fields
