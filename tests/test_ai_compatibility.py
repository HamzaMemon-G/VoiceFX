"""Exercise optional CPU LLVC in its own process; no downloads or audio devices."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


def check_ai():
    import torch,json,tempfile,hashlib
    import numpy as np
    from unittest.mock import patch
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
    import engine,paths
    from model import Net
    config=json.loads((paths.RESOURCES/'vendor/LLVC/experiments/llvc/config.json').read_text())
    assert not torch.cuda.is_available(),'App test requires CPU-only Torch'
    torch.set_num_threads(2)
    torch.manual_seed(1234)
    with tempfile.TemporaryDirectory() as temp:
        data=Path(temp);(data/'models').mkdir();checkpoint=data/'models/test.pth'
        torch.save({'model':Net(**config['model_params']).eval().state_dict()},checkpoint)
        checksum=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        with patch.object(paths,'DATA',data),patch.dict(engine.MODELS,{'test':('test.pth','llvc',checksum)}):
            converter=engine.Converter(threads=2,model_name='test')
            for _ in range(3):
                y=converter.convert48(np.zeros(converter.frames,dtype=np.float32))
                assert y.shape==(converter.frames,)
                assert np.isfinite(y).all()
                assert float(np.max(np.abs(y)))<=.95


@unittest.skipUnless(importlib.util.find_spec('torch'), 'Optional AI dependencies are not installed')
class AICompatibility(unittest.TestCase):
    def test_cpu_checkpoint_and_streaming(self):
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--cpu-check'],capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':
    if '--cpu-check' in sys.argv:check_ai()
    else:unittest.main()
