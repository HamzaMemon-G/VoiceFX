"""Build import archives for a Beatrice v2 client without changing audio devices.

The preserved model files remain read-only inputs. This tool deliberately does not
install or launch a client: the live CPU path still requires machine testing.
"""

import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "models" / "beatrice"
OUTPUT = ROOT / "dist" / "beatrice-import"
WEIGHTS = (
    "phone_extractor.bin",
    "pitch_estimator.bin",
    "waveform_generator.bin",
    "embedding_setter.bin",
    "speaker_embeddings.bin",
)


def package(voice: str) -> Path:
    folder = SOURCE / voice
    provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    tomls = list(folder.glob("beatrice_paraphernalia_*.toml"))
    if len(tomls) != 1:
        raise RuntimeError(f"Expected exactly one Beatrice TOML for {voice}")
    files = [folder / name for name in WEIGHTS] + [folder / "noimage.png", tomls[0]]
    for file in files:
        expected = provenance["files"].get(file.name)
        if expected is None or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Missing or modified approved file: {file}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    dest = OUTPUT / f"{voice}-beatrice-v2.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, f"beatrice_paraphernalia_{voice.replace('-', '_')}/{file.name}")
    return dest


if __name__ == "__main__":
    for name in ("pop-smoke", "opie"):
        print(package(name))
