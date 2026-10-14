import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).parents[1]


def test_pinned_library_and_schema():
    pins=json.loads((ROOT/'src/meshdesk/resources/upstream.json').read_text(encoding='utf-8'))
    assert importlib.metadata.version('meshtastic')==pins['python']['tag']
    result=subprocess.run([sys.executable,str(ROOT/'tools/audit_compatibility.py')],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


def test_official_translations_have_english_fallback():
    from meshdesk.i18n import translate,enrich
    from meshdesk.schema import fields,new_message
    assert translate('Settings','pl-PL')!='Settings'
    form=enrich('config.lora',fields(new_message('config.lora')),'en')
    region=next(f for f in form if f['path']=='region')
    assert region['description']


def test_native_locales_cover_the_same_controls():
    from meshdesk.i18n import ROOT as LOCALES,native_catalog,translate,native_labels,catalog
    expected=set(native_catalog('en'))
    assert len(expected)>=50
    for file in LOCALES.glob('*.json'):
        assert set(native_catalog(file.stem))==expected,file.stem
    assert all(key in catalog() for key in native_labels().values())
    assert translate('Preferences','pl-PL')=='Preferencje'
    assert translate('Bluetooth operation timed out','en')=='Bluetooth operation timed out'
