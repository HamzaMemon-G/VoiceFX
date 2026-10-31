# Experimental Pop CPU microphone trial

Prepared locally, not a live release. The existing VoiceFX UI and saved device
choices remain unchanged. Do not run this while someone else uses audio or a
game. Close other VoiceFX sessions first; this separate experimental entrypoint
does not share the original application's session lock.

Use the app interpreter (work/VoiceFX/.venv/Scripts/python.exe) for the host:
it already has sounddevice. Pass work/cpu-inference-env/Scripts/python.exe as
--python for the separate CPU-only worker. The worker environment intentionally
has no sounddevice; do not reinstall it or run the host with that interpreter.

Run app/rvc_experimental_session.py --help with the app interpreter to inspect
arguments. A trial requires --start, exact --input-name and --output-name, and
all six path arguments. Set --snapshot to the preserved approved 200 ms runtime,
--rvc-root to work/RVC, --ort-packages to work/cpu-onnx-packages,
--openvino-packages to work/cpu-openvino-packages, and --log-file to a NEW file
outside all preserved snapshots. --seconds is a total time budget including
initialization. The default 60 seconds may end before devices start on a cold
load; that returns exit 2 and provides no hardware result. No session auto-runs.

Use the already selected voice destination; do not change Voicemeeter or VBAN.
Hear Myself is off unless --hear-myself is supplied together with a distinct
--monitor-name. Ctrl+C ends the temporary session and closes its owned worker.
Driver or worker faults stop output; raw microphone fallback is never used.

The next required check is attended: speak several unseen sentences, confirm
word preservation and naturalness, toggle monitoring independently, check for
dropouts, and measure physical microphone-to-output latency. Simulated first
output was 540-560 ms and does not establish physical latency. The XPS and gaming
load remain untested. No need to provide XPS access for this desktop trial.

Evidence: 54 model-free RVC tests passed in the CPU environment; all 23 host
integration tests also passed in the actual app interpreter. Both public host
and callback replays matched exactly, and the earlier two 900-second CPU
simulations and private held-out waveform gate passed. Earlier CPU failures
remain recorded; these passes do not promise reliability on different loads.
