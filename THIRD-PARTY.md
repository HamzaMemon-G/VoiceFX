# Third-party notices

* LLVC — Koe AI, MIT. https://github.com/KoeAI/LLVC
  Revision `1627c5d358cf9bb2b92b0ccc513d8b36807c923d`.
  Only inference files/configs are included. `model.py` imports the standalone
  positional encoder instead of the full SpeechBrain package. Configuration
  exports retain only inference model parameters; training settings are omitted.
* SpeechBrain positional encoder — Apache 2.0; extracted implementation.
  License: `vendor/LLVC/SPEECHBRAIN-LICENSE`.
  https://github.com/speechbrain/speechbrain , `Transformer.py` positional encoder.
* stftPitchShift — Juri Hock, MIT. https://github.com/jurihock/stftPitchShift
  Revision `1a4f21f6c300a785cce860e374fd63cb5e9ba154`.
  Only cepstral, pitch and resampling primitives are included. Empty package
  initializer avoids importing unrelated offline components.
* LLVC original/HFG pretrained weights — KoeAI/llvc, MIT model card.
  https://huggingface.co/KoeAI/llvc
  Revision `ebfe8c0fdeb974a7eeb463b3abbc8ce42a0e3851`.
  Optional download; checksums are enforced. Not stored in Git.
* PySide6/Qt — LGPLv3, dynamically linked and replaceable in portable releases.
  https://doc.qt.io/qtforpython-6/licenses.html
  Sources for the bundled 6.8.3 libraries:
  https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/
  and https://download.qt.io/archive/qt/6.8/6.8.3/single/ .
  Replacing compatible libraries in `_internal/PySide6` is permitted, including
  debugging or reverse engineering changes to those libraries under LGPLv3.
  Full GPLv3 and LGPLv3 texts are included under `licenses/`.
* NumPy, SciPy, PyTorch, sounddevice and psutil retain their upstream licenses.
  Installed package notices are included in portable builds.
* PyInstaller — GPLv2 with the bootloader exception permitting distribution of
  bundled applications under their own license.
