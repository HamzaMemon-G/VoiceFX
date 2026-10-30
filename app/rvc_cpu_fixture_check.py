"""Compare a local public fixture through the actual child process; no devices."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

import numpy as np

from rvc_cpu_check import load_source
from rvc_process import RvcProcessStream
from windows_resource_guard import active_games


def checked_path(root, relative):
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Fixture path leaves its directory')
    return path


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('python','fixture','snapshot','rvc-root','ort-packages','report'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--disable-execution-throttling',action='store_true')
    args=parser.parse_args(argv)
    if args.report.exists():
        parser.error('Choose a new report filename')
    args.report.parent.mkdir(parents=True,exist_ok=True)
    games=active_games()
    if games:
        args.report.write_text(json.dumps(dict(resource_blocked=True,known_games=games,
            public_waveform_parity_passed=False,worker_started=False,cases=[]),indent=2)+'\n')
        return 2
    manifest=json.loads((args.fixture/'manifest.json').read_text())
    if manifest['preparation']!='PCM16 mono to48k resample_poly3_1, then zero-pad to9600; no gain/denoise':
        raise ValueError('Unsupported fixture preprocessing')
    if not isinstance(manifest['cases'],list) or not 1 <= len(manifest['cases']) <= 10:
        raise ValueError('Expected between one and ten public fixture cases')
    results=[]
    for entry in manifest['cases']:
        if not isinstance(entry['name'],str) or not re.fullmatch(r'[a-z0-9-]{1,64}',entry['name']):
            raise ValueError('Invalid fixture case name')
        source=checked_path(args.fixture,entry['source'])
        expected_file=checked_path(args.fixture,entry['reference'])
        for path,key in ((source,'source_sha256'),(expected_file,'reference_sha256')):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=entry[key]:
                raise RuntimeError('Public fixture checksum mismatch')
        audio=load_source(source)
        audio=np.pad(audio,(0,(-len(audio))%9600))
        expected=np.load(expected_file,allow_pickle=False)
        if expected.dtype!=np.float32 or expected.shape!=audio.shape:
            raise ValueError('Invalid fixture reference shape or dtype')
        stream=RvcProcessStream(args.python,args.snapshot,args.rvc_root,args.ort_packages,
            args.report.with_name(args.report.stem+'-'+entry['name']+'.worker.log'),
            startup_packets=1,max_packets=3,pitch=entry['pitch'],
            disable_execution_throttling=args.disable_execution_throttling)
        actual=[]
        row=dict(name=entry['name'],source_sha256=entry['source_sha256'])
        try:
            deadline=time.monotonic()+610
            while not stream.status()['ready']:
                if stream.status()['state']=='fault' or time.monotonic()>deadline:
                    raise RuntimeError('Fixture worker failed to become ready')
                time.sleep(.05)
            for offset in range(0,len(audio),9600):
                if not stream.submit(audio[offset:offset+9600]):
                    raise RuntimeError('Fixture packet rejected')
                deadline=time.monotonic()+10
                while stream.status()['buffered_frames']<9600:
                    if stream.status()['state']=='fault' or time.monotonic()>deadline:
                        raise RuntimeError('Fixture conversion failed or timed out')
                    time.sleep(.002)
                actual.append(stream.read(9600))
            error=float(np.max(np.abs(np.concatenate(actual)-expected)))
            row.update(waveform_max_abs=error,passed=error<1e-4)
        except Exception as exc:
            row.update(passed=False,error=str(exc))
        finally:
            row['worker_execution_speed']=stream.status().get('worker_execution_speed')
            try:
                stream.close()
                row['worker_shutdown_verified']=not stream._thread.is_alive()
            except Exception as exc:
                row.update(passed=False,worker_shutdown_verified=False,shutdown_error=str(exc))
        results.append(row)
    passed=bool(results) and all(row['passed'] and row['worker_shutdown_verified'] for row in results)
    args.report.write_text(json.dumps(dict(public_waveform_parity_passed=passed,cases=results,
        warning='Unpaced public waveform/transport check only. No CPU live timing, new human sound approval, microphone, routing, gaming or XPS readiness.'),indent=2)+'\n')
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
