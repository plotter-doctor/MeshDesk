#!/usr/bin/env python3
"""Linux host RSS / idle CPU sampling; includes the local simulator process."""
import argparse
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='meshdesk-benchmark-') as directory:
        started=time.monotonic()
        ready_file=Path(directory)/'ready.json'
        process=subprocess.Popen([sys.executable,'-m','meshdesk.app','--demo','--data-dir',directory,'--quit-after','16','--ready-file',str(ready_file)],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        samples=[]
        while process.poll() is None:
            time.sleep(1)
            try:
                stat=Path(f'/proc/{process.pid}/stat').read_text().split()
                status=dict(line.split(':',1) for line in Path(f'/proc/{process.pid}/status').read_text().splitlines())
                if 'VmRSS' in status:
                    samples.append({'seconds':round(time.monotonic()-started,2),'rss_mib':round(int(status['VmRSS'].split()[0])/1024,2),
                                    'cpu_seconds':(int(stat[13])+int(stat[14]))/os.sysconf('SC_CLK_TCK')})
            except FileNotFoundError:break
        stdout,stderr=process.communicate(timeout=10)
        if process.returncode:raise RuntimeError(stderr)
        ready=json.loads(ready_file.read_text())
        ready_after=ready['monotonic']-started
        steady=[s for s in samples[:-2] if s['seconds']>=ready_after+3]
        result={'platform':sys.platform,'architecture':platform.machine(),'python':sys.version,'mode':'Qt software, demo simulator, 1024x600, no online tiles',
                'ready_after_seconds':round(ready_after,3),'idle_sample_range_seconds':[steady[0]['seconds'],steady[-1]['seconds']],
                'samples':samples,'peak_sampled_rss_mib':max(s['rss_mib'] for s in samples),
                'idle_cpu_percent':round((steady[-1]['cpu_seconds']-steady[0]['cpu_seconds'])/(steady[-1]['seconds']-steady[0]['seconds'])*100,2),
                'stderr':stderr,'note':'Includes the local simulator. Idle CPU excludes startup, three warmup seconds and shutdown.'}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()
