"""Read-only training preflight; run with the separate training Python."""
import argparse
import csv
import io
import json
import platform
import subprocess


def check():
    report = {"python": platform.python_version(), "gpu": [],
              "cuda_training_ready": False, "errors": []}
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=20)
        for row in csv.reader(io.StringIO(result.stdout)):
            name, total, free, driver = [value.strip() for value in row]
            report["gpu"].append(dict(name=name, total_mib=int(total),
                                      free_mib=int(free), driver=driver))
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        report["errors"].append("NVIDIA query failed: " + str(error))
    try:
        import torch
        report["torch"] = torch.__version__
        report["torch_cuda"] = torch.version.cuda
        if not torch.cuda.is_available():
            report["errors"].append("This Python has no usable CUDA PyTorch backend.")
        else:
            report["torch_device"] = torch.cuda.get_device_name(0)
            report["compute_capability"] = list(torch.cuda.get_device_capability(0))
            # Exercise allocation, execution and backward without opening any audio device.
            x = torch.ones((256, 256), device="cuda", requires_grad=True)
            (x @ x).square().mean().backward()
            torch.cuda.synchronize()
            report["cuda_training_ready"] = True
            report["note"] = "CUDA backward passed; full model VRAM fit is still untested."
    except Exception as error:
        report["errors"].append("CUDA smoke test failed: " + str(error))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-cuda", action="store_true")
    args = parser.parse_args()
    report = check()
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if args.require_cuda and not report["cuda_training_ready"] else 0)
