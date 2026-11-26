"""Host a separately installed official Beatrice v2 VST3 for local CPU audio."""

import os
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from paths import DATA, RESOURCES

ALPHABET = ".ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+"
MODELS = {
    "pop-smoke": ("Pop Smoke · Beatrice trial", "beatrice_paraphernalia_train_00000060.toml"),
    "opie": ("Opie / Elanip · Beatrice trial", "beatrice_paraphernalia_train_00000080.toml"),
}


def plugin_path():
    roots = [DATA / "plugins", Path(os.environ.get("COMMONPROGRAMFILES", "C:/Program Files/Common Files")) / "VST3"]
    override = os.environ.get("VOICEFX_BEATRICE_VST")
    if override:
        candidate = Path(override)
        if candidate.is_file():
            return candidate
        roots.insert(0, candidate)
    for root in roots:
        if root.is_dir():
            matches = sorted(root.rglob("beatrice*.vst3/Contents/x86_64-win/*.vst3"))
            if matches:
                return matches[-1]
    return None


def model_path(key):
    if key not in MODELS:
        raise ValueError("Unknown Beatrice voice")
    folder = RESOURCES / "models" / "beatrice" / key
    model = folder / MODELS[key][1]
    try:
        provenance = json.loads((folder / "provenance.json").read_text())
        files = provenance["files"]
        if provenance["voice"] != key or MODELS[key][1] not in files:
            raise ValueError("Voice manifest does not match the selected model")
        for name, expected in files.items():
            if Path(name).name != name or not isinstance(expected, str) or len(expected) != 64:
                raise ValueError("Invalid model manifest")
            if hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected:
                raise ValueError("Model bundle checksum mismatch")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"Beatrice voice bundle missing or changed: {key}") from exc
    return model


def installed_models():
    if plugin_path() is None:
        return {}
    result = {}
    for key, (label, _) in MODELS.items():
        try:
            model_path(key)
        except RuntimeError:
            continue
        result[key] = label
    return result


def _decode(value):
    size_text, encoded = value.split(".", 1)
    result = bytearray(int(size_text))
    for index, char in enumerate(encoded):
        number = ALPHABET.index(char)
        for bit in range(6):
            position = index * 6 + bit
            if position < len(result) * 8 and number & (1 << bit):
                result[position // 8] |= 1 << (position % 8)
    return bytes(result)


def _encode(data):
    chars = []
    for index in range((len(data) * 8 + 5) // 6):
        number = 0
        for bit in range(6):
            position = index * 6 + bit
            if position < len(data) * 8 and data[position // 8] & (1 << (position % 8)):
                number |= 1 << bit
        chars.append(ALPHABET[number])
    return str(len(data)) + "." + "".join(chars)


def _with_model(raw, model):
    if raw[:4] != b"VC2!":
        raise RuntimeError("Unsupported Beatrice plug-in state")
    xml_length = struct.unpack_from("<I", raw, 4)[0]
    xml_bytes = raw[8:8 + xml_length]
    root = ET.fromstring(xml_bytes)
    node = root.find("IComponent")
    if node is None or not node.text:
        raise RuntimeError("Beatrice component state missing")
    component = _decode(node.text)
    state_length = struct.unpack_from("<I", component, 0)[0]
    state = component[4:4 + state_length]
    if len(state) != state_length:
        raise RuntimeError("Truncated Beatrice component state")
    offset = 0
    output = bytearray()
    found = False
    while offset < len(state):
        begin = offset
        param_id, kind = struct.unpack_from("<hi", state, offset)
        offset += 6
        if kind == 0:
            offset += 4
        elif kind == 1:
            offset += 8
        elif kind == 2:
            size = struct.unpack_from("<i", state, offset)[0]
            if size < 0:
                raise RuntimeError("Invalid Beatrice state string")
            offset += 4 + size
        else:
            raise RuntimeError("Unsupported Beatrice state parameter")
        if offset > len(state):
            raise RuntimeError("Truncated Beatrice state parameter")
        if param_id == 1:
            if kind != 2 or found:
                raise RuntimeError("Unexpected Beatrice model parameter")
            value = str(model.resolve()).encode("utf-8")
            output += struct.pack("<hii", 1, 2, len(value)) + value
            found = True
        else:
            output += state[begin:offset]
    if not found:
        raise RuntimeError("Beatrice model parameter missing")
    encoded = _encode(struct.pack("<I", len(output)) + output)
    new_xml = xml_bytes.replace(node.text.encode("ascii"), encoded.encode("ascii"), 1)
    return raw[:4] + struct.pack("<I", len(new_xml)) + new_xml + raw[8 + xml_length:]


class Beatrice:
    frames = 2400
    ms = 50

    def __init__(self, key):
        vst = plugin_path()
        if vst is None:
            raise RuntimeError("Install the official Beatrice v2 VST3 in VoiceFX/plugins or the Windows VST3 folder.")
        model = model_path(key)
        from pedalboard import load_plugin

        self.plugin = load_plugin(str(vst))
        self.plugin.raw_state = _with_model(self.plugin.raw_state, model)
        self._pitch = None
        self._formant = None

    def reset(self):
        self.plugin.reset()

    def convert48(self, x, pitch=0, formant=0):
        if len(x) != self.frames:
            raise ValueError("Beatrice requires its selected audio block size")
        if pitch != self._pitch:
            self.plugin.pitch_shift_st = float(pitch)
            self._pitch = pitch
        if formant != self._formant:
            self.plugin.formant_shift_st = float(np.clip(formant, -2, 2))
            self._formant = formant
        result = self.plugin.process(np.asarray(x, dtype=np.float32)[None, :], sample_rate=48000, buffer_size=self.frames, reset=False)
        y = np.asarray(result, dtype=np.float32).reshape(-1)
        if len(y) != self.frames or not np.isfinite(y).all():
            raise RuntimeError("Beatrice returned invalid audio")
        return y
