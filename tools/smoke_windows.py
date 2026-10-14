#!/usr/bin/env python3
"""Run the shipped Windows executable without Python imports from the checkout."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable',type=Path)
    parser.add_argument('--output',type=Path,default=Path('artifacts/windows'))
    args=parser.parse_args()
    exe=args.executable.resolve()
    args.output.mkdir(parents=True,exist_ok=True)
    report={'executable':exe.name,'transports':{}}
    for transport in ('offline','tcp','ble'):
        with tempfile.TemporaryDirectory(prefix='meshdesk-frozen-') as data:
            ready=Path(data)/'ready.json'
            screenshot=args.output.resolve()/(transport+'.png')
            command=[str(exe),'--keyboard','off','--data-dir',data,'--ready-file',str(ready),
                     '--screenshot',str(screenshot),'--quit-after','20']
            if transport!='offline':command+=['--demo','--demo-transport',transport]
            env=dict(os.environ,QT_QUICK_BACKEND='software',QT_QUICK_CONTROLS_STYLE='Material')
            env.pop('PYTHONPATH',None)
            result=subprocess.run(command,cwd=data,env=env,capture_output=True,text=True,timeout=90)
            assert result.returncode==0,(transport,result.returncode,result.stdout,result.stderr)
            assert ready.is_file(),transport+': did not become ready'
            assert screenshot.is_file() and screenshot.stat().st_size>10000,transport+': screenshot missing'
            report['transports'][transport]=json.loads(ready.read_text())
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
