"""How the 3D preview treats the materials of a character's VRoid model.

* ``materials.txt`` in the character folder lets you override automatic detection:
  ``<part of a material name> = metallic | silk | thin | thick | none``
* Effects normally come only from wardrobe pieces matched to the model's textures
  (see ``vrm_match``): metallic / silk masks, and thin fabric that turns see-through when wet.
  Nothing is guessed from material names.
"""
from __future__ import annotations

from pathlib import Path


HEADER = """# Material rules for {name}'s 3D preview (VRoid model) - OPTIONAL
# Normally nothing is needed here: when the model is loaded its textures are compared with the
# wardrobe images, and matched parts get their piece's effects (metallic / silk masks, thin fabric).
# Rules below only override that.
# One rule per line:   <part of a material name> = metallic | silk | thin | thick | none
#   metallic  render as reflective metal (keeps the model's own colours / textures)
#   silk      soft sheen
#   thin      becomes ~70% opaque while wet (rain / swimming)
#   thick     never becomes see-through
#   none      no metallic / silk effect even if detected automatically
# Matching is case-insensitive and uses the longest matching rule. Use "List model materials"
# in the Interact tab to see the material names and what was detected.
#
# Without rules, metallic / silk effects come only from wardrobe pieces matched to the model's
# textures (material names are not used).
#
# Examples:
# Bra = metallic
# Tops_01 = thin
# HairBack = none
"""


def config_path(character) -> Path:
    return character.dir / "materials.txt"


def ensure_config(character) -> Path:
    path = config_path(character)
    if not path.exists():
        path.write_text(HEADER.format(name=character.name), encoding="utf-8")
    return path


def load_overrides(character) -> dict[str, str]:
    path = ensure_config(character)
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().lower()
        if key.strip() and value in ("metallic", "silk", "thin", "thick", "none"):
            out[key.strip()] = value
    return out


def wet_reason(state: dict) -> str:
    """Why the character is wet ("" when dry)."""
    if state.get("activity") == "Swimming / beach":
        return "swimming"
    if state.get("weather") == "Rainy":
        return "rain"
    if state.get("weather") == "Scorching hot":
        return "sweat in the scorching heat"
    return ""


def is_wet(state: dict) -> tuple[bool, float]:
    """Wet from swimming, rain, or sweat in scorching heat -> (wet, strength 0-1)."""
    if state.get("activity") == "Swimming / beach":
        return True, 1.0
    if state.get("weather") == "Rainy":
        return True, 0.8
    if state.get("weather") == "Scorching hot":
        return True, 0.6
    return False, 0.0
