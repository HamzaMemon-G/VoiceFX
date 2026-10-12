"""Local custom LLVC checkpoints; built-in models are registered separately."""
import json
import re
from paths import DATA

CUSTOM = {
    "pop_smoke": ("Pop Smoke", "pop-smoke-llvc.pth"),
    "opie": ("Opie / Elanip", "opie-llvc.pth"),
}


def custom_models():
    """Return only installed targets with a recorded checksum."""
    try:
        manifest = json.loads((DATA / "models/custom-models.json").read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(manifest, dict):
        return {}
    result = {}
    for key, (label, filename) in CUSTOM.items():
        checksum = manifest.get(key)
        if (isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]{64}", checksum)
                and (DATA / "models" / filename).is_file()):
            result[key] = (label, filename, checksum)
    return result
