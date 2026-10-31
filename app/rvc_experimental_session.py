"""Explicit, session-only Pop CPU hardware trial; main app defaults stay unchanged."""
import argparse
from pathlib import Path
from threading import Timer

from rvc_host_controller import RvcHostController
from rvc_host_driver import explicit_driver
from rvc_host_profile import RvcHostProfile
from voice_session_lock import VoiceSessionLock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog=
        'Experimental: simulated first output was 540-560 ms; physical latency and XPS are unvalidated.')
    parser.add_argument('--start', action='store_true', help='Explicitly start a temporary microphone session')
    for name in ('python', 'snapshot', 'rvc-root', 'ort-packages', 'openvino-packages', 'log-file'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--input-name', required=True)
    parser.add_argument('--output-name', required=True)
    parser.add_argument('--monitor-name', default='')
    parser.add_argument('--hear-myself', action='store_true')
    parser.add_argument('--pitch', type=float, default=-9)
    parser.add_argument('--seconds', type=int, default=60,
                        help='Total trial time budget including model initialization')
    args = parser.parse_args(argv)
    if not args.start:
        parser.error('No devices opened. Supply --start for an explicit temporary trial.')
    if not 1 <= args.seconds <= 3600:
        parser.error('Trial duration must be between 1 and 3600 seconds')
    if args.hear_myself and not args.monitor_name:
        parser.error('Choose separate headphones before enabling Hear Myself')
    profile = RvcHostProfile(args.python, args.snapshot, args.rvc_root,
        args.ort_packages, args.openvino_packages, args.log_file, args.pitch)
    profile.worker_options()
    from windows_resource_guard import active_games
    if active_games():
        print('Trial deferred while a known game is running. No game was closed.')
        return 2
    import sounddevice as sd
    controller = RvcHostController()
    def driver(callback):
        callback.session.monitor.enabled = args.hear_myself
        return explicit_driver(sd, callback, input_name=args.input_name,
            output_name=args.output_name, monitor_name=args.monitor_name)
    timer = Timer(args.seconds, controller.stop.set)
    timer.daemon = True
    timer.start()
    try:
        with VoiceSessionLock():
            controller.run(profile, driver, sd.CallbackStop)
    except KeyboardInterrupt:
        controller.stop.set()
    except RuntimeError as exc:
        print('Trial not started: ' + str(exc))
        return 2
    finally:
        timer.cancel()
    if controller.error:
        print('Trial stopped: ' + controller.error)
        return 1
    if not controller.driver_started:
        print('Trial ended before audio devices started; no hardware result was measured.')
        return 2
    print('Temporary trial stopped. Saved devices and routing were not modified.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
