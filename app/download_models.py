"""Opt-in pinned model download, verified before atomically installing."""

import hashlib
import urllib.request
from paths import DATA

REV = "ebfe8c0fdeb974a7eeb463b3abbc8ce42a0e3851"
MODELS = [
    (
        "llvc.pth",
        "llvc",
        "cceb7ab9621f84d62d283725ae3281cacb04f762d6a088fe3e97c1a29d4b8c0e",
    ),
    (
        "llvc-hfg.pth",
        "llvc_hfg",
        "ca046f9a77b36ebfe473923503c5a69260af67f8a1dac317483f2e00ae28e4ed",
    ),
]


def download(progress=print):
    folder = DATA / "models"
    folder.mkdir(exist_ok=True)
    for name, experiment, digest in MODELS:
        path = folder / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            continue
        temporary = path.with_suffix(".download")
        progress("Downloading " + name + "…")
        try:
            url = f"https://huggingface.co/KoeAI/llvc/resolve/{REV}/models/checkpoints/{experiment}/G_500000.pth"
            with (
                urllib.request.urlopen(url, timeout=60) as response,
                temporary.open("wb") as out,
            ):
                while block := response.read(1048576):
                    out.write(block)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
                raise RuntimeError("Model checksum mismatch")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    progress("AI models ready. Audio processing stays offline.")


if __name__ == "__main__":
    download()
