"""Global settings for the Interact tab's 3D preview (``preview_settings.txt`` in the library folder).

The file is plain text so it can be edited with any text editor::

    wet thin opacity = 0.7
    metallic shine = 1.0
    ...
    [default expressions]
    Happy = happy:1.0

The ``[default expressions]`` section holds the mood / reaction faces that new characters'
``expressions.txt`` files start with (and that are used for moods missing from those files).
"""
from __future__ import annotations

from pathlib import Path

FILE_NAME = "preview_settings.txt"

# key: (default, minimum, maximum, comment)
NUMBERS = {
    "wet thin opacity": (0.7, 0.0, 1.0, "opacity of thin clothing while wet (1 = not see-through)"),
    "metallic shine": (1.0, 0.0, 3.0, "strength of metallic reflections (0 = off, 0.1 = barely, 1 = polished)"),
    "silk shine": (1.0, 0.0, 3.0, "strength of the silk sheen (0 = off)"),
    "wet shine": (1.0, 0.0, 3.0, "strength of the wet gloss on the whole character (0 = off)"),
    "wet darkening": (0.25, 0.0, 0.9, "how much darker clothing, hair and accessories get while wet "
                                      "(0 = not at all; thin, metallic and silk pieces never darken)"),
    "physics": (1.0, 0.0, 1.0, "1 = hair / clothing physics (spring bones) on, 0 = off"),
    "physics stiffness": (1.0, 0.2, 3.0, "multiplies the model's spring-bone stiffness (higher = less floppy)"),
    "wind strength": (1.0, 0.0, 3.0, "how strongly wind moves hair and clothing in Windy weather"),
}

HEADER = """# Ultimate Outfitter - 3D preview settings (Interact tab)
# Change a value after the "=" and save; the Interact tab reloads this file when you use
# "Reload preview settings" or switch characters. Lines starting with # are comments.
"""

EXPR_HEADER = """
[default expressions]
# Faces that every NEW character's expressions.txt starts with, and that are used for any mood or
# reaction missing from a character's own expressions.txt.
# Mood = blendshape:weight, blendshape:weight   (weights 0-1, VRM expressions or raw blend shapes)
"""


def path_for(library) -> Path:
    return Path(library.root) / FILE_NAME


def default_text() -> str:
    from .expressions import DEFAULTS
    lines = [HEADER]
    for key, (value, lo, hi, comment) in NUMBERS.items():
        lines.append(f"# {comment} ({lo:g} - {hi:g})")
        lines.append(f"{key} = {value:g}")
    lines.append(EXPR_HEADER)
    lines += [f"{k} = {v}" for k, v in DEFAULTS.items()]
    return "\n".join(lines) + "\n"


def ensure(library) -> Path:
    path = path_for(library)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(default_text(), encoding="utf-8")
    return path


def parse(text: str) -> dict:
    """{'numbers': {key: float}, 'expressions': {Mood: 'shape:w, ...'}} with defaults filled in."""
    from .expressions import DEFAULTS
    numbers = {k: v[0] for k, v in NUMBERS.items()}
    exprs: dict[str, str] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if section == "default expressions":
            exprs[key] = value
            continue
        low = " ".join(key.lower().replace("_", " ").split())
        if low in NUMBERS:
            _, lo, hi, _ = NUMBERS[low]
            if value.lower() in ("on", "yes", "true"):
                value = "1"
            elif value.lower() in ("off", "no", "false"):
                value = "0"
            try:
                numbers[low] = max(lo, min(hi, float(value)))
            except ValueError:
                pass
    known = {k.lower() for k in exprs}
    for k, v in DEFAULTS.items():
        if k.lower() not in known:
            exprs[k] = v
    return {"numbers": numbers, "expressions": exprs}


def load(library) -> dict:
    try:
        return parse(ensure(library).read_text(encoding="utf-8"))
    except OSError:
        return parse("")


def default_expressions(library) -> dict[str, str]:
    return load(library)["expressions"] if library is not None else parse("")["expressions"]
