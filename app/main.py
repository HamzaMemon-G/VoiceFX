"""VoiceFX desktop application."""

import json
import queue
import threading
import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSlider,
    QFrame,
    QProgressBar,
    QScrollArea,
)
from audio import Audio, devices
from paths import SETTINGS

MODES = {
    "Local AI": "hfg",
    "Clean": "clean",
    "Deep": "deep",
    "Police radio": "police",
    "ATC radio": "atc",
    "Robot": "robot",
}
CHARACTERS = {
    "Balanced masculine": (-5, -3),
    "Subtle lower": (-3, -1.5),
    "Deep character": (-8, -4),
    "Original AI target": (0, 0),
}
STYLE = """QWidget{background:#10141e;color:#e7ecf6;font-family:Segoe UI;font-size:13px} QFrame#card{background:#1a2030;border:1px solid #2a3348;border-radius:14px} QLabel{background:transparent} QLabel#title{font-size:28px;font-weight:700} QLabel#sub{color:#9aa9c2} QPushButton{background:#222c40;border:1px solid #34415b;border-radius:8px;padding:12px;text-align:left} QPushButton:checked{background:#284b69;border:1px solid #62c8e8} QPushButton#start{background:#61cce3;color:#0b1721;font-weight:700;text-align:center} QPushButton:disabled{color:#68748c} QComboBox{padding:9px;border:1px solid #34415b;border-radius:7px;background:#222c40} QSlider::groove:horizontal{height:5px;background:#34415b;border-radius:2px} QSlider::handle:horizontal{width:14px;margin:-5px 0;background:#61cce3;border-radius:7px} QProgressBar{border:0;background:#2a3348;border-radius:4px;height:8px} QProgressBar::chunk{background:#61cce3;border-radius:4px}"""


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VoiceFX")
        self.resize(1080, 750)
        try:
            self.saved = json.loads(SETTINGS.read_text())
        except (OSError, ValueError):
            self.saved = {}
        self.mode = "Local AI"
        self.audio = None
        self.worker = None
        self.messages = queue.Queue()
        self.controls = {}
        self.presets = self.saved.get("presets", {})
        root = QWidget()
        self.setCentralWidget(root)
        row = QHBoxLayout(root)
        row.setContentsMargins(24, 24, 24, 24)
        row.setSpacing(20)
        side = QVBoxLayout()
        row.addLayout(side, 1)
        side.addWidget(self.label("VOICEFX", "title"))
        side.addWidget(self.label("Make it your voice.", "sub"))
        side.addSpacing(22)
        self.buttons = {}
        for name in MODES:
            b = QPushButton(name)
            b.setCheckable(True)
            b.clicked.connect(lambda checked=False, n=name: self.choose(n))
            side.addWidget(b)
            self.buttons[name] = b
        side.addStretch()
        side.addWidget(self.label("LOCAL AUDIO · CPU ONLY", "sub"))
        center = QVBoxLayout()
        row.addLayout(center, 3)
        self.heading = self.label("Local AI", "title")
        center.addWidget(self.heading)
        self.description = self.label("A different voice, shaped by you.", "sub")
        self.description.setWordWrap(True)
        center.addWidget(self.description)
        card = QFrame()
        card.setObjectName("card")
        self.editor = QVBoxLayout(card)
        self.editor.setContentsMargins(22, 22, 22, 22)
        center.addWidget(card, 1)
        self.character = QComboBox()
        self.character.addItems([*CHARACTERS, "Custom"])
        self.character.currentTextChanged.connect(self.character_changed)
        self.character_label = self.label("Character")
        self.editor.addWidget(self.character_label)
        self.editor.addWidget(self.character)
        self.sliders = QVBoxLayout()
        self.editor.addLayout(self.sliders)
        self.editor.addStretch()
        actions = QHBoxLayout()
        save = QPushButton("Save this preset")
        save.clicked.connect(self.save)
        reset = QPushButton("Reset controls")
        reset.clicked.connect(lambda: self.choose(self.mode, reset=True))
        actions.addWidget(save)
        actions.addWidget(reset)
        self.editor.addLayout(actions)
        self.status = self.label("Select your input and output to begin.", "sub")
        self.status.setWordWrap(True)
        center.addWidget(self.status)
        self.start = QPushButton("Start voice")
        self.start.setObjectName("start")
        self.start.clicked.connect(self.toggle)
        center.addWidget(self.start)
        right_widget = QWidget()
        right = QVBoxLayout(right_widget)
        right.setContentsMargins(6, 0, 6, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(right_widget)
        scroll.setMinimumWidth(290)
        right_column = QVBoxLayout()
        right_column.addWidget(scroll, 1)
        row.addLayout(right_column, 2)
        right.addWidget(self.label("Audio routing", "title"))
        self.input = QComboBox()
        self.output = QComboBox()
        right.addWidget(self.label("Microphone / incoming stream"))
        right.addWidget(self.input)
        right.addWidget(self.label("Voice destination"))
        right.addWidget(self.output)
        refresh = QPushButton("Refresh devices")
        refresh.clicked.connect(self.refresh)
        right.addWidget(refresh)
        right.addSpacing(12)
        right.addWidget(self.label("AI model"))
        self.ai_model = QComboBox()
        self.ai_model.addItems(["HFG target", "Original target"])
        self.ai_model.setCurrentIndex(int(self.saved.get("ai_model", 0)))
        self.get_models = QPushButton("Get AI models")
        self.get_models.clicked.connect(self.download)
        model_row = QHBoxLayout()
        model_row.addWidget(self.ai_model, 1)
        model_row.addWidget(self.get_models)
        right.addLayout(model_row)
        self.downloading = False
        right.addWidget(self.label("AI response"))
        self.buffer = QComboBox()
        self.buffer.addItems(["Stable · 104 ms", "Experimental · 52 ms"])
        self.buffer.setCurrentIndex(int(self.saved.get("buffer", 0)))
        right.addWidget(self.buffer)
        advanced = QPushButton("Microphone controls")
        advanced.setCheckable(True)
        right.addWidget(advanced)
        advanced_widget = QWidget()
        advanced_layout = QVBoxLayout(advanced_widget)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        right.addWidget(advanced_widget)
        advanced_widget.setVisible(False)
        advanced.toggled.connect(advanced_widget.setVisible)
        for key, title, lo, hi, value in [
            ("gain_db", "Microphone gain", -6, 12, 0),
            ("gate_db", "Noise gate", -80, -35, -70),
            ("volume", "Output level", 0, 100, 80),
        ]:
            self.slider(
                right if key == "volume" else advanced_layout,
                key,
                title,
                lo,
                hi,
                self.saved.get(key, value),
            )
        self.mute = QPushButton("Mute output")
        self.mute.setCheckable(True)
        self.mute.toggled.connect(self.live)
        right.addWidget(self.mute)
        right.addSpacing(12)
        meter_layout = QVBoxLayout()
        right_column.addLayout(meter_layout)
        meter_layout.addWidget(self.label("Input signal"))
        self.inmeter = QProgressBar()
        self.inmeter.setTextVisible(False)
        meter_layout.addWidget(self.inmeter)
        meter_layout.addWidget(self.label("Output signal"))
        self.outmeter = QProgressBar()
        self.outmeter.setTextVisible(False)
        meter_layout.addWidget(self.outmeter)
        self.metrics = self.label("Stopped · no audio sent", "sub")
        self.metrics.setWordWrap(True)
        meter_layout.addWidget(self.metrics)
        right.addStretch()
        self.refresh()
        self.choose(self.saved.get("mode", "Local AI"))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)

    def label(self, text, name=""):
        w = QLabel(text)
        w.setObjectName(name)
        return w

    def slider(self, layout, key, title, lo, hi, value):
        label = self.label("")
        layout.addWidget(label)
        s = QSlider(Qt.Horizontal)
        s.setRange(int(lo * 10), int(hi * 10))
        s.setValue(int(value * 10))
        layout.addWidget(s)
        self.controls[key] = s

        def changed(v):
            label.setText(f"{title}   {v / 10:g}")
            if (
                self.mode == "Local AI"
                and "pitch" in self.controls
                and "formant" in self.controls
            ):
                self.sync_character()
            self.live()

        s.valueChanged.connect(changed)
        changed(s.value())

    def refresh(self):
        try:
            ins, outs = devices()
        except Exception as e:
            self.status.setText("Device discovery failed: " + str(e))
            return
        for combo, items, key in (
            (self.input, ins, "input"),
            (self.output, outs, "output"),
        ):
            wanted = combo.currentText() or self.saved.get(key, "")
            combo.clear()
            combo.addItem("")
            combo.addItems(items)
            if wanted in items:
                combo.setCurrentText(wanted)

    def choose(self, name, reset=False):
        if self.worker and self.worker.is_alive():
            return
        if name not in MODES:
            name = "Local AI"
        self.mode = name
        self.audio = None
        self.heading.setText(name)
        for n, b in self.buttons.items():
            b.setChecked(n == name)
        while self.sliders.count():
            item = self.sliders.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for k in list(self.controls):
            if k not in ("gain_db", "gate_db", "volume"):
                del self.controls[k]
        self.character.setVisible(name == "Local AI")
        self.character_label.setVisible(name == "Local AI")
        self.buffer.setEnabled(name == "Local AI")
        self.ai_model.setEnabled(name == "Local AI")
        values = {} if reset else self.presets.get(name, {})
        if name == "Local AI":
            spec = [("pitch", "Pitch", -12, 6, -5), ("formant", "Resonance", -6, 4, -3)]
        elif name == "Deep":
            spec = [("pitch", "Depth", 0, 12, 9)]
        elif name == "Robot":
            spec = [
                ("carrier", "Carrier tone (Hz)", 55, 108, 95),
                ("drive", "Metallic intensity", 0, 100, 70),
                ("noise", "Natural voice blend", 0, 100, 0),
                ("clarity", "Brightness", 0, 100, 35),
            ]
        elif name in ("Police radio", "ATC radio"):
            spec = [
                ("drive", "Radio bite", 0, 100, 70 if name == "Police radio" else 35),
                ("clarity", "Bandwidth", 0, 100, 35 if name == "Police radio" else 65),
                ("noise", "Receiver noise", 0, 100, 0),
                ("squelch", "Squelch threshold", -80, -35, -65),
            ]
        else:
            spec = []
        for k, t, lo, hi, v in spec:
            self.slider(self.sliders, k, t, lo, hi, values.get(k, v))
        if name == "Local AI":
            self.sync_character()
        self.description.setText(
            {
                "Local AI": "Fixed AI target with independent pitch and resonance.",
                "Clean": "Clean mono audio for checking your routing.",
                "Deep": "Lightweight pitch shift for a lower character.",
                "Police radio": "Gritty tactical radio with speech driven squelch.",
                "ATC radio": "Brighter communication radio with less overload.",
                "Robot": "Metallic carrier modulation with adjustable character.",
            }[name]
        )

    def character_changed(self, name):
        if name not in CHARACTERS:
            return
        for k, v in zip(("pitch", "formant"), CHARACTERS[name]):
            if k in self.controls:
                self.controls[k].setValue(int(v * 10))

    def sync_character(self):
        v = self.values()
        name = next(
            (
                n
                for n, pair in CHARACTERS.items()
                if abs(pair[0] - v["pitch"]) < 0.05
                and abs(pair[1] - v["formant"]) < 0.05
            ),
            "Custom",
        )
        self.character.blockSignals(True)
        self.character.setCurrentText(name)
        self.character.blockSignals(False)

    def values(self):
        return {k: s.value() / 10 for k, s in self.controls.items()}

    def live(self, *args):
        if not self.audio:
            return
        v = self.values()
        self.audio.gain_db = v["gain_db"]
        self.audio.gate_db = v["gate_db"]
        self.audio.volume = v["volume"] / 100
        self.audio.mute = self.mute.isChecked()
        if self.mode == "Local AI":
            self.audio.pitch = v["pitch"]
            self.audio.formant = v["formant"]
        else:
            self.audio.effect.update(
                {k: int(x) for k, x in v.items() if k in self.audio.effect}
            )
            if "carrier" in v:
                self.audio.effect["pitch"] = round((v["carrier"] - 55) * 9 / 40)

    def save(self):
        self.presets[self.mode] = {
            k: v
            for k, v in self.values().items()
            if k not in ("gain_db", "gate_db", "volume")
        }
        data = dict(
            self.values(),
            mode=self.mode,
            input=self.input.currentText(),
            output=self.output.currentText(),
            presets=self.presets,
            ai_model=self.ai_model.currentIndex(),
            buffer=self.buffer.currentIndex(),
        )
        SETTINGS.write_text(json.dumps(data, indent=2))
        self.status.setText("Preset saved locally.")

    def toggle(self):
        if self.downloading:
            self.status.setText("Wait for the model download to finish.")
            return
        if self.worker and self.worker.is_alive():
            self.audio.stop.set()
            self.start.setEnabled(False)
            return
        if not self.input.currentText() or not self.output.currentText():
            self.status.setText("Choose an explicit input and output device.")
            return
        model = (
            ("hfg" if self.ai_model.currentIndex() == 0 else "original")
            if self.mode == "Local AI"
            else MODES[self.mode]
        )
        self.audio = Audio(
            self.input.currentText(),
            self.output.currentText(),
            self.messages.put,
            model,
            8 if self.buffer.currentIndex() == 0 else 4,
        )
        self.live()
        self.worker = threading.Thread(target=self.audio.run, daemon=True)
        self.worker.start()
        self.start.setText("Stop voice")
        for w in (
            *self.buttons.values(),
            self.input,
            self.output,
            self.buffer,
            self.ai_model,
            self.get_models,
        ):
            w.setEnabled(False)

    def download(self):
        if self.downloading:
            return
        self.downloading = True
        self.get_models.setEnabled(False)

        def run():
            try:
                from download_models import download

                download(self.messages.put)
            except Exception as e:
                self.messages.put("Download failed: " + str(e))
            finally:
                self.downloading = False

        threading.Thread(target=run, daemon=True).start()

    def tick(self):
        if not self.downloading and not (self.worker and self.worker.is_alive()):
            self.get_models.setEnabled(True)
        while not self.messages.empty():
            self.status.setText(self.messages.get_nowait())
        if self.audio:
            s = self.audio.stats
            self.inmeter.setValue(int(max(0, min(100, (s["peak_db"] + 60) / 60 * 100))))
            self.outmeter.setValue(int(min(100, s["output_peak"] * 100)))
            self.metrics.setText(
                f"{s['blocks']} blocks · {s['misses']} late\nCompute {s['mean_ms']:.1f} ms · peak {s['max_ms']:.1f} ms"
            )
        if self.worker and not self.worker.is_alive():
            self.worker = None
            self.start.setText("Start voice")
            self.start.setEnabled(True)
            for w in (*self.buttons.values(), self.input, self.output):
                w.setEnabled(True)
            self.buffer.setEnabled(self.mode == "Local AI")
            self.ai_model.setEnabled(self.mode == "Local AI")
            self.inmeter.setValue(0)
            self.outmeter.setValue(0)

    def closeEvent(self, event):
        if self.worker and self.worker.is_alive():
            self.audio.stop.set()
            self.status.setText("Stopping audio safely…")
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    w = Window()
    w.show()
    sys.exit(app.exec())
