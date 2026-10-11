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


def thin_keywords(character) -> list[str]:
    """Material-name keywords for the thin pieces of the current outfit."""
    outfit = character.shown_outfit() or {}
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


def removed_keywords(character, removed: list[dict]) -> list[str]:
    """Material-name words for pieces taken off the outfit (used when no model texture matched them).

    Words that also describe a piece still being worn are left out, so nothing worn gets hidden.
    """
    outfit = character.shown_outfit() or {}
    wardrobe = character.data.get("wardrobe", {})
    keep = set()
    for p in outfit.get("pieces", []):
        slot = p.get("slot") or wardrobe.get(p.get("entry_id"), {}).get("slot", "")
        keep.update(SLOT_MATERIAL_WORDS.get(slot, []))
        if slot in GENERIC:
            keep.add(GENERIC[slot])
    words = set()
    for r in removed:
        slot = r.get("slot") or wardrobe.get(r.get("entry_id"), {}).get("slot", "")
        words.update(SLOT_MATERIAL_WORDS.get(slot, []))
        words.update(w for w in re.split(r"[^a-zA-Z]+", r.get("name", "").lower()) if len(w) > 2 and w not in STOP_WORDS)
        if slot in GENERIC:
            words.add(GENERIC[slot])
    return sorted(words - keep)


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
