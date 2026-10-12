"""Headless interface smoke test with empty devices and temporary settings."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import main
from PySide6.QtWidgets import QApplication

app = QApplication([])
with (
    tempfile.TemporaryDirectory() as tmp,
    patch.object(main, "SETTINGS", Path(tmp) / "settings.json"),
    patch.object(main, "devices", lambda: ([], [])),
):
    w = main.Window()
    assert w.input.currentText() == w.output.currentText() == ""
    assert not w.monitor_button.isChecked()
    assert not w.monitor_button.isEnabled()
    w.toggle()
    assert w.worker is None
    for mode in main.MODES:
        w.choose(mode)
        app.processEvents()
        assert w.heading.text() == mode
    w.choose("Local AI")
    w.controls["pitch"].setValue(-87)
    assert w.character.currentText() == "Custom"
    w.character.setCurrentText("Balanced masculine")
    assert w.values()["pitch"] == -5 and w.values()["formant"] == -3
    w.controls["pitch"].setValue(-70)
    w.save()
    w.close()
    restored = main.Window()
    assert not restored.monitor_button.isChecked()
    assert restored.values()["pitch"] == -7
    restored.close()
print("PASS: no capture defaults, all modes, character sync and preset persistence")
