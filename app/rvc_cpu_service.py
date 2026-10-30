"""Local pipe protocol for the optional RVC CPU worker; opens no devices."""

import argparse
import base64
from contextlib import redirect_stdout
import json
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--rvc-root", required=True)
    parser.add_argument("--ort-packages", required=True)
    parser.add_argument("--dynamic-block-base", type=int, choices=(0, 4), default=0)
    parser.add_argument("--synthesis-backend", choices=("ort", "openvino"), default="ort")
    parser.add_argument("--openvino-packages")
    parser.add_argument('--disable-execution-throttling',action='store_true')
    args = parser.parse_args()
    protocol = sys.stdout

    def send(message):
        protocol.write(json.dumps(message) + "\n")
        protocol.flush()

    try:
        # RVC diagnostics belong on stderr, never in the packet protocol.
        with redirect_stdout(sys.stderr):
            qos=None
            if args.disable_execution_throttling:
                from windows_worker_qos import execution_speed_state
                qos=execution_speed_state(True)
            from rvc_cpu_worker import FrozenRvcCpu
            import numpy as np
            with FrozenRvcCpu(args.snapshot, args.rvc_root, args.ort_packages,
                             dynamic_block_base=args.dynamic_block_base,
                             synthesis_backend=args.synthesis_backend,
                             openvino_packages=args.openvino_packages) as converter:
                converter.warmup()
                send(dict(type="ready", frames=converter.frames, sample_rate=48000,
                          dynamic_block_base=args.dynamic_block_base,
                          execution_speed=qos,
                          synthesis_backend=args.synthesis_backend))
                sequence = 0
                while True:
                    line = sys.stdin.readline(65537)
                    if not line:
                        break
                    if len(line) > 65536 or not line.endswith("\n"):
                        raise ValueError("Oversized or incomplete input packet")
                    message = json.loads(line)
                    if message.get("type") == "stop":
                        send(dict(type="stopped"))
                        break
                    if (message.get("type") != "convert"
                            or type(message.get("sequence")) is not int
                            or message["sequence"] != sequence):
                        raise ValueError("Invalid packet order or command")
                    raw = base64.b64decode(message["audio"], validate=True)
                    if len(raw) != converter.frames * 4:
                        raise ValueError("Invalid input packet size")
                    audio = np.frombuffer(raw, dtype="<f4").copy()
                    converted = converter.convert48(audio, pitch=message.get("pitch", -9))
                    send(dict(type="converted", sequence=sequence,
                              audio=base64.b64encode(converted.astype("<f4").tobytes()).decode("ascii"),
                              compute_ms=converter.last_compute_ms))
                    sequence += 1
    except Exception as exc:
        # No packet contents are logged or sent back with an error.
        import traceback
        traceback.print_exc(file=sys.stderr)
        send(dict(type="error", message=f"CPU worker failed: {type(exc).__name__}"))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
