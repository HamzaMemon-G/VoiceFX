"""Explicit host lifecycle with injected driver; no device discovery or defaults."""
import time
from threading import Event, Lock

from rvc_host_callback import RvcHostCallback
from rvc_host_session import RvcHostSession


class RvcHostController:
    def __init__(self, session_factory=RvcHostSession):
        self.stop = Event()
        self.session_factory = session_factory
        self.callback = None
        self.error = ''
        self._start_lock = Lock()
        self._started = False

    def run(self, profile, driver_factory, callback_stop, *, startup_timeout=610):
        """Call off the UI/callback thread; driver_factory gets callback only.

        The caller must supply explicitly selected devices in its factory.
        No driver is constructed before worker readiness. Driver resources close
        before the worker, including when driver initialization raises.
        """
        with self._start_lock:
            if self._started:
                raise RuntimeError('Construct a new controller for each explicit session')
            self._started = True
        try:
            with self.session_factory() as session:
                if self.stop.is_set():
                    return
                profile.start(session)
                deadline = time.monotonic() + startup_timeout
                while not self.stop.is_set():
                    state = session.status()
                    if state['state'] in ('fault', 'stopped'):
                        raise RuntimeError('Voice worker failed during initialization')
                    if state['ready']:
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Voice worker initialization timed out')
                    self.stop.wait(.02)
                if self.stop.is_set():
                    return
                self.callback = RvcHostCallback(session, self.stop, callback_stop)
                with driver_factory(self.callback):
                    while not self.stop.wait(.02):
                        if session.status()['state'] in ('fault', 'stopped'):
                            raise RuntimeError('Voice worker stopped')
                if self.callback.error:
                    self.error = self.callback.error
        except Exception as exc:
            self.error = str(exc)
            self.stop.set()
