"""How the 3D preview treats the materials of a character's VRoid model.

* ``materials.txt`` in the character folder lets you override automatic detection:
  ``<part of a material name> = metallic | silk | thin | thick | none``
* Thin clothing keywords: when the character is wet (rain, swimming) the parts of the model
  that belong to thin clothing items of the current outfit become semi-transparent. The model's
  material names (e.g. VRoid's ``N00_002_01_Tops_01_CLOTH``) are matched against the item's
  name words and keywords for its outfit slot.
"""
from __future__ import annotations

import re
from pathlib import Path

# VRoid / common material-name words per outfit slot
SLOT_MATERIAL_WORDS = {
    "base_top": ["tops", "shirt", "top", "blouse", "tank"],
    "mid_layer": ["tops", "sweater", "hoodie", "vest", "cardigan"],
    "corset": ["corset"],
    "full_body": ["onepiece", "dress", "robe", "kimono", "jumpsuit"],
    "sleepwear": ["onepiece", "pajama", "nightgown", "sleep"],
    "legs": ["bottoms", "pants", "skirt", "shorts", "trousers"],
    "legwear": ["legwear", "tights", "stocking", "leggings"],
    "socks": ["socks", "legwear", "stocking"],
    "outer": ["outer", "jacket", "coat", "blazer"],
    "cape": ["cape", "cloak"],
    "underwear_bottom": ["underwear", "panties", "pantsu", "brief", "inner"],
    "bra": ["bra", "underwear", "inner"],
    "swim_bottom": ["swim", "bikini"],
    "swim_top": ["swim", "bikini"],
    "swim_full": ["swim", "onepiece", "swimsuit"],
    "neck": ["scarf", "shawl"],
    "hands": ["glove"],
    "arms": ["sleeve", "armwarmer"],
    "apron": ["apron"],
    "head": ["hat", "cap"],
}
# generic VRoid part names - only used for a thin piece when no thick piece shares them
GENERIC = {"base_top": "tops", "mid_layer": "tops", "bra": "tops", "swim_top": "tops",
           "legs": "bottoms", "underwear_bottom": "bottoms", "swim_bottom": "bottoms",
           "full_body": "onepiece", "swim_full": "onepiece"}
STOP_WORDS = {"the", "and", "with", "of", "a", "an"}

HEADER = """# Material rules for {name}'s 3D preview (VRoid model)
# One rule per line:   <part of a material name> = metallic | silk | thin | thick | none
#   metallic  render as reflective metal (keeps the model's own colours / textures)
#   silk      soft sheen
#   thin      becomes ~70% opaque while wet (rain / swimming)
#   thick     never becomes see-through
#   none      no metallic / silk effect even if detected automatically
# Matching is case-insensitive and uses the longest matching rule. Use "List model materials"
# in the Interact tab to see the material names and what was detected.
#
# Automatic detection (no rule needed): material or texture names containing metallic, metal,
# chrome, silver, gold, steel, armor (-> metallic) or silk, satin (-> silk), a glTF metallic
# factor of 0.5 or more, or a matcap / sphere-add reflection texture (can be switched off).
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


def thin_keywords(character) -> list[str]:
    """Material-name keywords for the thin pieces of the current outfit."""
    outfit = character.data.get("current_outfit") or {}
    wardrobe = character.data.get("wardrobe", {})
    items = character.library.items
    thin, thick_generic = [], set()
    pieces = []
    for p in outfit.get("pieces", []):
        e = wardrobe.get(p.get("entry_id"), {})
        item = items.get(e.get("item_id"), {})
        thickness = item.get("attrs", {}).get("thickness", "medium")
        slot = p.get("slot") or e.get("slot", "")
        pieces.append((slot, thickness, p.get("name", "")))
        if thickness != "thin" and slot in GENERIC:
            thick_generic.add(GENERIC[slot])
    for slot, thickness, name in pieces:
        if thickness != "thin":
            continue
        thin += SLOT_MATERIAL_WORDS.get(slot, [])
        thin += [w for w in re.split(r"[^a-zA-Z]+", name.lower()) if len(w) > 2 and w not in STOP_WORDS]
        generic = GENERIC.get(slot)
        if generic and generic not in thick_generic:
            thin.append(generic)
    return sorted(set(thin))


def is_wet(state: dict) -> tuple[bool, float]:
    if state.get("activity") == "Swimming / beach":
        return True, 1.0
    if state.get("weather") == "Rainy":
        return True, 0.8
    return False, 0.0
