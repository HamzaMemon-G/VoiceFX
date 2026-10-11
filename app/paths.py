"""Private settings and model cache live outside the source tree."""

import os
import sys
from pathlib import Path

DATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "VoiceFX"
DATA.mkdir(parents=True, exist_ok=True)
SETTINGS = DATA / "settings.json"
RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
