"""Opt-in file-driven CPU check; never open an audio device or save input audio."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import wave

import numpy as np

from rvc_capture_bridge import RvcCaptureBridge
from rvc_process import RvcProcessStream
from windows_resource_guard import active_games, GameLoadWatch


def evaluate(completed, first_play, fault, missing_samples, compute_ms, callback_ms):
    """Keep uninterrupted playback and compute headroom as separate criteria."""
    uninterrupted = bool(completed and first_play is not None and not fault and missing_samples == 0)
    headroom = bool(compute_ms and float(np.percentile(compute_ms, 95)) <= 160.)
    callback_budget = bool(callback_ms and max(callback_ms) <= 20.)
    return dict(uninterrupted_simulation=uninterrupted,
                model_p95_has_20percent_headroom=headroom,
                callback_work_within_20ms=callback_budget,
                simulated_cpu_gate_passed=uninterrupted and headroom and callback_budget)


def load_source(path):
    with wave.open(str(path), 'rb') as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError('Use a mono 16-bit PCM WAV for this check')
        rate = source.getframerate()
        if rate not in (16000, 48000):
            raise ValueError('Use a 16 kHz or 48 kHz source')
        audio = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(np.float32)/32768.
    if len(audio) < rate:
        raise ValueError('Use at least one second of source audio')
    if rate == 16000:
        from scipy.signal import resample_poly
        audio = resample_poly(audio,3,1).astype(np.float32)
    return audio


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot','rvc-root','ort-packages','source','report'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--python',type=Path,default=Path(sys.executable))
    parser.add_argument('--seconds',type=int,default=600)
    parser.add_argument('--pitch',type=float,default=-9.)
    parser.add_argument('--startup-ms',type=int,choices=(400,600),default=400,
                        help='Explicit queue tradeoff; 600 adds 200 ms startup delay')
    parser.add_argument('--dynamic-block-base',type=int,choices=(0,4),default=0)
    parser.add_argument('--synthesis-backend',choices=('ort','openvino'),default='ort')
    parser.add_argument('--openvino-packages',type=Path)
    parser.add_argument('--worker-priority',choices=('normal','above_normal'),default='normal')
    parser.add_argument('--disable-execution-throttling',action='store_true')
    parser.add_argument('--allow-game-co-load',action='store_true',help='Explicitly allow an intentional game/co-load experiment')
    args=parser.parse_args(argv)
    if not 10 <= args.seconds <= 3600:
        parser.error('Check duration must be between 10 and 3600 seconds')
    if any(path.exists() for path in (args.report,args.report.with_suffix('.worker.log'),
                                      args.report.with_suffix('.packets.json'))):
        parser.error('Choose a new report filename; existing reports are preserved')
    args.report.parent.mkdir(parents=True,exist_ok=True)
    games=active_games()
    if games and not args.allow_game_co_load:
        args.report.write_text(json.dumps(dict(resource_blocked=True,known_games=games,
            simulated_cpu_gate_passed=False,worker_started=False,
            reason='A game is running; no model was loaded. Close it before an idle CPU check.'),indent=2)+'\n')
        return 2
    audio=load_source(args.source)
    source_sha=hashlib.sha256(args.source.read_bytes()).hexdigest()
    stream=RvcProcessStream(args.python,args.snapshot,args.rvc_root,args.ort_packages,
        args.report.with_suffix('.worker.log'),startup_packets=args.startup_ms//200,
        max_packets=args.startup_ms//200+1,
        pitch=args.pitch,dynamic_block_base=args.dynamic_block_base,
        synthesis_backend=args.synthesis_backend,openvino_packages=args.openvino_packages,
        worker_priority=args.worker_priority,disable_execution_throttling=args.disable_execution_throttling)
    timings=[]
    callbacks=[]
    lateness=[]
    fault=None
    first_play=None
    played=0
    capture=0
    sequence=-1
    bridge=RvcCaptureBridge(stream)
    watch=None
    report=dict(scope='File-driven real-worker CPU check, simulated callbacks only',
        source_sha256=source_sha,source_looped=True,requested_seconds=args.seconds,
        processing_packet_ms=200,callback_ms=20,startup_queue_ms=args.startup_ms,
        max_queue_ms=args.startup_ms+200,
        pitch=args.pitch,dynamic_block_base=args.dynamic_block_base,
        synthesis_backend=args.synthesis_backend,worker_priority=args.worker_priority,
        experimental_disable_execution_throttling=args.disable_execution_throttling,
        known_games_at_start=games,intentional_game_co_load=args.allow_game_co_load,
        warning='No microphone, devices, game load, routing, physical latency or XPS readiness is measured. No source audio is saved. Finite check stops without draining the live queue; tail samples are not certified played.')
    try:
        if not args.allow_game_co_load:
            watch=GameLoadWatch(stream.abort)
        while not stream.status()['ready']:
            if stream.status()['state']=='fault':
                raise RuntimeError(stream.status()['fault'])
            time.sleep(.05)
        begin=time.perf_counter()
        for index in range(args.seconds*50):
            # Callback n receives a completed 20ms capture block at (n+1)*20ms.
            target=begin+(index+1)*.02
            time.sleep(max(0,target-time.perf_counter()))
            offset=capture % len(audio)
            packet=audio[offset:offset+960]
            if len(packet)<960:
                packet=np.concatenate((packet,audio[:960-len(packet)]))
            start=time.perf_counter()
            lateness.append(max(0,1000*(start-target)))
            bridge.process(packet)
            callbacks.append(1000*(time.perf_counter()-start))
            capture+=960
            state=stream.status()
            if state['state']=='playing':
                if first_play is None:
                    first_play=time.perf_counter()-begin
                played+=960
            if index%10==0 or state['state']=='fault':
                for row in stream.metrics():
                    if row['sequence']>sequence:
                        timings.append(row)
                        sequence=row['sequence']
            if state['state']=='fault':
                fault=state['fault']
                break
        for row in stream.metrics():
            if row['sequence']>sequence:
                timings.append(row)
                sequence=row['sequence']
        state=stream.status()
        # Strict buffering stops on the first gap; it does not count lost samples.
        missing=state.get('missing_samples',0 if fault is None else None)
        report.update(evaluate(capture==args.seconds*48000,first_play,fault,
            missing,[r['compute_ms'] for r in timings],callbacks))
        report.update(fault=fault,capture_samples=capture,converted_playout_samples=played,
            missing_samples=missing,
            loss_count_scope='Zero only for an uninterrupted strict stream; null after a strict fault because lost samples were not counted',
            first_converted_playout_after_capture_start_ms=None if first_play is None else 1000*first_play,
            elapsed_seconds=time.perf_counter()-begin,observed_completed_packets=len(timings),
            model_p95_ms=float(np.percentile([r['compute_ms'] for r in timings],95)) if timings else None,
            callback_p95_ms=float(np.percentile(callbacks,95)) if callbacks else None,
            callback_schedule_lateness_p99_ms=float(np.percentile(lateness,99)) if lateness else None,
            buffered_tail_frames=state['buffered_frames'],queued_tail_input_packets=state['queued_input_packets'])
    except Exception as exc:
        report.update(error=str(exc),simulated_cpu_gate_passed=False)
    finally:
        if watch is not None:
            try:
                watch.close()
                resource=watch.status()
                report.update(resource_blocked=resource['blocked'],resource_watch=resource)
            except Exception as exc:
                report.update(resource_blocked=True,resource_watch_error=type(exc).__name__)
            if report.get('resource_blocked'):
                report['simulated_cpu_gate_passed']=False
        report['worker_execution_speed']=stream.status().get('worker_execution_speed')
        try:
            stream.close()
            report['worker_shutdown_verified']=not stream._thread.is_alive()
        except Exception as exc:
            report.update(shutdown_error=str(exc),worker_shutdown_verified=False,
                          simulated_cpu_gate_passed=False)
        args.report.write_text(json.dumps(report,indent=2)+'\n')
        args.report.with_suffix('.packets.json').write_text(json.dumps(timings,indent=2)+'\n')
    return 2 if report.get('resource_blocked') else (0 if report.get('simulated_cpu_gate_passed') else 1)


if __name__=='__main__':
    raise SystemExit(main())
