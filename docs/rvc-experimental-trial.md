# Experimental Pop CPU microphone trial

Prepared locally, not a live release. The existing VoiceFX UI and saved device
choices remain unchanged. Do not run this while someone else uses audio or a
game. This entrypoint shares the original application's named admission lock
and refuses simultaneous sessions before starting its worker or audio devices.

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


## Separate larger-delay experiment, 2 November

The user explicitly authorized testing roughly one second or more of delay.
Only the optional session CLI now accepts `--startup-ms 1000`; the default remains
400, capacity becomes1200ms only with that explicit option, and strict underflow
handling remains enabled. This option is experimental, not deployment approval.
No microphone or devices were opened while preparing it.

Both300s public file-driven simulations completed without cutoffs or lost samples,
first simulated output1140.39/1140.58ms. Modelp95157.10/163.77ms means the second
FAILED the unchanged160ms headroom criterion; overall validation did not pass.
Longer endurance was therefore not started. These are not physical latency,
gaming-load or XPS measurements.

The actual five-packet startup/six-packet-capacity worker also retained all129
private held-out Recording5 packets, including its full buffered tail. Waveform
error3.714e-5 passed the unchanged1e-4 gate; shutdown verified. No private audio
was saved, uploaded or used for training. This proves local waveform/sample
retention only, not sustained performance. Main application settings and routes
are unchanged. An attended trial still requires an awake user and explicit
device selections; the new delay option does not authorize enabling it silently.
