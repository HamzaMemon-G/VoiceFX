"""Reject changed worker assets before importing a model runtime."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from rvc_cpu_worker import FrozenRvcCpu


class WorkerValidation(unittest.TestCase):
    def test_host_with_existing_torch_must_use_separate_worker(self):
        with patch.dict(sys.modules, {"torch": object()}):
            with self.assertRaisesRegex(RuntimeError, "dedicated worker"):
                FrozenRvcCpu("unused", "unused", "unused")

    def fixture(self, root):
        snapshot = root / "snapshot"
        names = ["models/pop-pitch-refined.pth", "runtime/features.pt",
                 "runtime/synth.onnx", "runtime/rmvpe32.onnx", "settings.json",
                 "reproduction/rvc_worker.py", "reproduction/rtrvc.py"]
        hashes = {}
        for name in names:
            path = snapshot / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"validation fixture, never loaded as a model")
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (snapshot / "provenance.json").write_text(json.dumps({"sha256": hashes}))
        rvc = root / "rvc"
        (rvc / "infer").mkdir(parents=True)
        (rvc / "infer/rtrvc.py").write_bytes((snapshot / "reproduction/rtrvc.py").read_bytes())
        return snapshot, rvc

    def test_changed_graph_is_rejected_before_runtime_import(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot, rvc = self.fixture(Path(directory))
            (snapshot / "runtime/features.pt").write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                FrozenRvcCpu(snapshot, rvc, directory)
            self.assertNotIn("torch", sys.modules)

    def test_changed_external_inference_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot, rvc = self.fixture(Path(directory))
            (rvc / "infer/rtrvc.py").write_bytes(b"changed inference")
            with self.assertRaisesRegex(RuntimeError, "inference implementation has changed"):
                FrozenRvcCpu(snapshot, rvc, directory)
            self.assertNotIn("torch", sys.modules)


if __name__ == "__main__":
    unittest.main()
