"""Explicit experimental device adapter; importing it opens no devices."""
from contextlib import ExitStack, contextmanager


def resolve_mme(sd, name, direction):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('Select an explicit ' + direction + ' device')
    devices = sd.query_devices()
    matches = [(i, device) for i, device in enumerate(devices)
               if device['name'] == name
               and device['max_' + direction + '_channels'] >= 1
               and sd.query_hostapis(device['hostapi'])['name'] == 'MME']
    if len(matches) != 1:
        raise ValueError('Select one unambiguous MME ' + direction + ' device')
    index, device = matches[0]
    return index, min(2, device['max_' + direction + '_channels'])


@contextmanager
def explicit_driver(sd, callback, *, input_name, output_name, monitor_name=''):
    """Called only after worker readiness by an explicitly started controller.

    No default-device assignment, saved preferences, route setup or fallback.
    All names resolve before opening any stream. Host/controller owns cleanup.
    """
    inp, ins = resolve_mme(sd, input_name, 'input')
    out, outs = resolve_mme(sd, output_name, 'output')
    monitor = resolve_mme(sd, monitor_name, 'output') if monitor_name else None
    if monitor is not None and monitor[0] == out:
        raise ValueError('Headphones must be separate from the voice destination')
    with ExitStack() as stack:
        if monitor is not None:
            stack.enter_context(sd.OutputStream(device=monitor[0], channels=monitor[1],
                samplerate=48000, blocksize=960, dtype='float32',
                callback=callback.session.monitor.callback))
        driver = stack.enter_context(sd.Stream(device=(inp, out), channels=(ins, outs),
            samplerate=48000, blocksize=960, dtype='float32', callback=callback))
        yield driver
