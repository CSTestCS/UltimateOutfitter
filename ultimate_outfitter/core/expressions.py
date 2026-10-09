"""Per-character mood -> facial expression config (``expressions.txt``).

Each character folder gets an editable text file. Every line maps a mood (or a
short-lived reaction) to one or more blend shapes with weights 0-1::

    Happy = happy:1.0
    Cozy / tired = relaxed:0.7, blink:0.4
    Embarrassed = Fcl_MTH_Small:0.6, Fcl_EYE_Close:0.3

Names are first looked up as VRM expressions (happy, angry, sad, relaxed, surprised,
aa, ih, ou, ee, oh, blink, blinkLeft, blinkRight, lookUp... or custom expressions from the
model); anything else is used as a raw blend shape / morph target name such as
VRoid's ``Fcl_ALL_Joy``.
"""
from __future__ import annotations

from pathlib import Path

from .outfit import MOODS

REACTIONS = ["Laughing", "Embarrassed", "Frustrated", "Surprised", "Blushing", "Annoyed", "Flirty", "Thinking"]

DEFAULTS = {
    "Happy": "happy:1.0",
    "Calm": "relaxed:0.6",
    "Sad": "sad:0.9",
    "Energetic": "happy:0.7, surprised:0.25",
    "Romantic": "relaxed:0.5, happy:0.4",
    "Confident": "happy:0.45, relaxed:0.3",
    "Cozy / tired": "relaxed:0.8, blink:0.35",
    "Grumpy / dark": "angry:0.8",
    "Mysterious": "relaxed:0.45",
    "Focused": "angry:0.2, relaxed:0.2",
    "Adventurous": "happy:0.55",
    "Playful": "happy:0.75, surprised:0.15",
    "Fancy": "relaxed:0.55, happy:0.3",
    # short reactions shown for a few seconds after something happens in the chat
    "Laughing": "happy:1.0, aa:0.4",
    "Embarrassed": "sad:0.4, happy:0.25, blink:0.2",
    "Frustrated": "angry:0.7, sad:0.2",
    "Surprised": "surprised:1.0",
    "Blushing": "happy:0.5, relaxed:0.3",
    "Annoyed": "angry:0.5",
    "Flirty": "happy:0.5, blinkLeft:0.9",
    "Thinking": "relaxed:0.3, lookUp:0.4",
}

HEADER = """# Facial expressions for {name}
# One line per mood or reaction:   Mood = blendshape:weight, blendshape:weight
# Weights go from 0 to 1. Lines starting with # are comments.
# Names are VRM expressions (happy, angry, sad, relaxed, surprised, aa, ih, ou, ee, oh,
# blink, blinkLeft, blinkRight, lookUp, lookDown, lookLeft, lookRight, neutral, or a custom
# expression from the model) or raw blend shape names, e.g. VRoid's Fcl_ALL_Joy,
# Fcl_EYE_Close, Fcl_MTH_A, Fcl_BRW_Angry. Use "List model blend shapes" in the Interact
# tab to see what your model has.
# Leave a mood empty ("Calm =") for a neutral face.
#
# Moods: {moods}
# Reactions (played briefly during chat): {reactions}

"""


def config_path(character) -> Path:
    return character.dir / "expressions.txt"


def ensure_config(character) -> Path:
    path = config_path(character)
    if not path.exists():
        lines = [HEADER.format(name=character.name, moods=", ".join(MOODS), reactions=", ".join(REACTIONS))]
        lines += [f"{k} = {v}" for k, v in DEFAULTS.items()]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def parse(text: str) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        weights: dict[str, float] = {}
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            name, _, w = part.partition(":")
            try:
                weights[name.strip()] = max(0.0, min(1.0, float(w))) if w.strip() else 1.0
            except ValueError:
                continue
        out[key.strip().lower()] = weights
    return out


def load(character) -> dict[str, dict[str, float]]:
    path = ensure_config(character)
    try:
        return parse(path.read_text(encoding="utf-8"))
    except OSError:
        return {k.lower(): parse(f"x = {v}")["x"] for k, v in DEFAULTS.items()}


def weights_for(config: dict[str, dict[str, float]], name: str) -> dict[str, float]:
    return config.get(name.lower(), {})
