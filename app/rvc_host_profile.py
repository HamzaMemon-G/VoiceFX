"""Explicit session-only CPU profile; never reads or writes app preferences."""
from dataclasses import dataclass
import math
from pathlib import Path


@dataclass(frozen=True)
class RvcHostProfile:
    python: Path
    snapshot: Path
    rvc_root: Path
    ort_packages: Path
    openvino_packages: Path
    log_file: Path
    pitch: float = -9.0
    startup_ms: int = 400

    def worker_options(self):
        """Validate dependencies before any device open; worker checks hashes."""
        if not math.isfinite(self.pitch) or not -24 <= self.pitch <= 24:
            raise ValueError('Invalid session pitch')
        if type(self.startup_ms) is not int or self.startup_ms not in (400, 600, 1000):
            raise ValueError('Explicit startup buffering must be 400, 600 or explicitly experimental1000 ms')
        paths = {name: Path(getattr(self, name)).resolve() for name in
                 ('python', 'snapshot', 'rvc_root', 'ort_packages', 'openvino_packages', 'log_file')}
        if not paths['python'].is_file():
            raise ValueError('Explicit CPU Python interpreter is missing')
        for name in ('snapshot', 'rvc_root', 'ort_packages', 'openvino_packages'):
            if not paths[name].is_dir():
                raise ValueError('Missing runtime directory: ' + name)
        if not (paths['snapshot'] / 'provenance.json').is_file():
            raise ValueError('Frozen runtime manifest is missing')
        if not paths['log_file'].parent.is_dir():
            raise ValueError('Diagnostic log directory is missing')
        # Prevent diagnostics accidentally modifying any frozen runtime file.
        if paths['log_file'].is_relative_to(paths['snapshot']):
            raise ValueError('Diagnostic log must be outside frozen runtime')
        return dict(paths, startup_packets=self.startup_ms // 200,
                    max_packets=self.startup_ms // 200 + 1, pitch=self.pitch,
                    dynamic_block_base=4, synthesis_backend='openvino',
                    worker_priority='above_normal', recover_underflow=False,
                    disable_execution_throttling=False)

    def start(self, session):
        # Import only the transport, never Torch or the model in the host.
        from rvc_process import RvcProcessStream
        options = self.worker_options()
        session.start(lambda: RvcProcessStream(**options))
