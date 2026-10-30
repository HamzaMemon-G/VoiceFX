"""Friendly entry point for the local CPU TEST bundle; opens no audio devices."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

from windows_worker_job import WindowsWorkerJob
from windows_resource_guard import active_games


def main():
    if active_games():
        print('A game is running. Close it before running the CPU check.',flush=True)
        return 2
    root=Path(__file__).resolve().parent.parent
    python=root/'runtime/python.exe'
    if not all(path.exists() for path in (python,root/'packages/ort',root/'packages/openvino',
                                         root/'snapshot',root/'public-fixture/manifest.json')):
        print('CPU test files are missing. Use the complete local CPU Check folder.',flush=True)
        return 2
    report=root/'reports'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ)
    for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'):
        env.pop(key,None)
    system=Path(env.get('SystemRoot',r'C:\Windows'))
    env.update(PYTHONNOUSERSITE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_OFFLINE='1',
               HF_HUB_DISABLE_TELEMETRY='1',
               PATH=os.pathsep.join(map(str,(system/'System32',system,root/'runtime',root/'runtime/DLLs'))))

    def run(script,arguments):
        job=WindowsWorkerJob()
        process=None
        try:
            process=subprocess.Popen([str(python),'-E','-s',str(root/'app'/script),*arguments],
                env=env,cwd=root,creationflags=subprocess.CREATE_NO_WINDOW|job.suspended_creation_flag)
            job.assign_and_resume(process)
            return process.wait()
        finally:
            job.close()
            if process is not None:
                process.wait(timeout=5)

    common=['--python',str(python),'--snapshot',str(root/'snapshot'),
            '--rvc-root',str(root/'RVC'),'--ort-packages',str(root/'packages/ort')]
    print('VoiceFX CPU check. This uses test files and leaves your audio routing alone.',flush=True)
    print('Checking reference audio...',flush=True)
    code=run('rvc_cpu_fixture_check.py',common+['--fixture',str(root/'public-fixture'),
                                              '--report',str(report/'reference.json')])
    if code:
        print('Reference check failed. CPU timing was skipped. Reports:',report,flush=True)
        return 1
    fixtures=json.loads((root/'public-fixture/manifest.json').read_text())
    passed=True
    for index,entry in enumerate(fixtures['cases'],1):
        print(f'Checking CPU timing (sample {index} of {len(fixtures["cases"])})...',flush=True)
        code=run('rvc_cpu_check.py',common+['--source',str(root/'public-fixture'/entry['source']),
            '--pitch',str(entry['pitch']),'--report',str(report/(entry['name']+'.json')),
            '--seconds','300','--dynamic-block-base','4','--synthesis-backend','openvino',
            '--openvino-packages',str(root/'packages/openvino'),'--worker-priority','above_normal'])
        passed=passed and code==0
    print('File-based CPU test passed.' if passed else 'CPU timing still needs work on this computer.',flush=True)
    print('This was a file-based test. Live microphone and delay testing remain.',flush=True)
    print('Reports:',report,flush=True)
    return 0 if passed else 1


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nCPU check stopped. Audio routing was not changed.',flush=True)
        raise SystemExit(130)
    except Exception as exc:
        print('CPU check could not finish:',str(exc),flush=True)
        raise SystemExit(1)
