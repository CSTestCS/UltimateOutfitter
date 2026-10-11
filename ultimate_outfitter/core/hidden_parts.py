"""Per-outfit list of hidden 3D-model parts (``Outfits/<outfit>-hidden.txt``).

When a piece is taken off an outfit, the model parts whose texture matched that piece are hidden in
the Interact preview. The list is written to a plain text file next to the outfit's contact sheet so a
wrong guess can be corrected by deleting its line (or a part added by writing its material name).

The file is the authority for what is hidden. When pieces change, only the parts that changed are
added or removed, so lines the user deleted stay deleted.
"""
from __future__ import annotations

from pathlib import Path

from .storage import safe_name

HEADER = """# Hidden 3D-model parts for {name}'s outfit of {date}
# Each line is a material of the VRoid model that is hidden in the Interact preview because its
# texture matched a piece taken off this outfit (the item name follows the #).
# Wrong? Delete the line and save: that part is shown again. You can also add material names
# (see "List model materials" in the Interact tab). Lines starting with # are comments.

"""


def path_for(character, outfit: dict) -> Path:
    stem = safe_name(f"Outfit-{outfit.get('date', '')}-{str(outfit.get('id', ''))[:8]}")
    return character.dir / "Outfits" / f"{stem}-hidden.txt"


def read(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and line not in out:
            out.append(line)
    return out


def write(character, outfit: dict, materials: list[str], notes: dict[str, str]) -> Path:
    path = path_for(character, outfit)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [HEADER.format(name=character.name, date=outfit.get("date", ""))]
    width = max((len(m) for m in materials), default=0)
    for m in materials:
        note = notes.get(m)
        lines.append(f"{m.ljust(width)}    # {note}" if note else m)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def reconcile(character, outfit: dict, matches: list[dict] | None) -> list[str]:
    """Bring the outfit's hidden-parts file up to date and return the materials to hide.

    ``matches`` are the texture matches of the loaded model (``vrm_match.match_wardrobe``), or None
    while they are not known yet - then the file is used as it is.
    """
    path = path_for(character, outfit)
    listed = read(path)
    if matches is None:
        return listed
    removed = {r.get("entry_id") for r in outfit.get("removed", [])}
    computed = {m["material"]: m.get("item_name", "") for m in matches if m.get("entry_id") in removed}
    written = set(outfit.get("hidden_written", []))
    new = [m for m in computed if m not in written]          # parts of pieces taken off since last time
    gone = written - set(computed)                           # pieces put back on
    result = [m for m in listed if m not in gone] + [m for m in new if m not in listed]
    if set(outfit.get("hidden_written", [])) != set(computed):
        outfit["hidden_written"] = sorted(computed)
        character.save()
    if result != listed or (computed and not path.exists()):
        notes = {m: computed.get(m, "") for m in result}
        write(character, outfit, result, notes)
    return result
