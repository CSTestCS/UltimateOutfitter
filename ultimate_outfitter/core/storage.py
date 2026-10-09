"""On-disk library: clothing items, palettes, patterns and characters.

Layout (inside the data folder)::

    library.json
    Items/        uploaded clothing item images
    Palettes/     source images palettes were extracted from
    Patterns/     pattern images
    Characters/<Name>/profile.json, character image, Wardrobe/, Outfits/
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

SETTINGS_FILE = Path.home() / ".ultimate_outfitter_settings.json"


def default_data_dir() -> Path:
    docs = Path.home() / "Documents"
    base = docs if docs.is_dir() else Path.home()
    return base / "UltimateOutfitterData"


def load_settings() -> dict[str, Any]:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict[str, Any]) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass


def new_id() -> str:
    return uuid.uuid4().hex[:12]


_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str, fallback: str = "Unnamed") -> str:
    """Make a string safe to use as a file or folder name on Windows."""
    cleaned = _BAD_CHARS.sub("_", name).strip().strip(".")
    return cleaned or fallback


def unique_path(path: Path) -> Path:
    """Return ``path`` or, if it exists, ``stem (2).ext``, ``stem (3).ext``... Never overwrites."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class Library:
    """Clothing items, palettes and patterns shared by every character."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        for sub in ("Items", "Palettes", "Patterns", "Characters", "Edited", "Upscaled"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        self.path = self.root / "library.json"
        self.items: dict[str, dict] = {}
        self.palettes: dict[str, dict] = {}
        self.patterns: dict[str, dict] = {}
        self.load()

    # -- persistence --------------------------------------------------------
    def load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except ValueError:
                data = {}
            self.items = data.get("items", {})
            self.palettes = data.get("palettes", {})
            self.patterns = data.get("patterns", {})

    def save(self) -> None:
        write_json_atomic(self.path, {
            "version": 1, "items": self.items, "palettes": self.palettes, "patterns": self.patterns,
        })

    def abspath(self, rel: str) -> Path:
        return self.root / rel

    def _import_file(self, src: Path | str, folder: str, stem: str) -> str:
        src = Path(src)
        dest = unique_path(self.root / folder / f"{safe_name(stem)}{src.suffix.lower() or '.png'}")
        shutil.copy2(src, dest)
        return dest.relative_to(self.root).as_posix()

    # -- items --------------------------------------------------------------
    def add_item(self, image_src: Path | str | list, name: str, category: str, answers: dict,
                 traits: dict, attrs: dict, notes: str = "", copied_from: str | None = None) -> dict:
        """Add a clothing item. ``image_src`` may be one path or a list (front, back, parts...)."""
        item_id = new_id()
        sources = image_src if isinstance(image_src, (list, tuple)) else [image_src]
        rels = [self.import_item_image(src, name) for src in sources]
        item = {
            "id": item_id, "name": name, "category": category, "image": rels[0], "images": rels,
            "answers": answers, "traits": traits, "attrs": attrs, "notes": notes,
            "copied_from": copied_from, "created": time.time(),
        }
        self.items[item_id] = item
        self.save()
        return item

    def import_item_image(self, src: Path | str, name: str) -> str:
        """Copy an image into the Items folder unless it already lives in the library."""
        src = Path(src)
        try:
            return src.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return self._import_file(src, "Items", name)

    @staticmethod
    def item_images(item: dict) -> list[str]:
        return item.get("images") or [item["image"]]

    def update_item(self, item_id: str, **fields: Any) -> dict:
        item = self.items[item_id]
        item.update(fields)
        item["modified"] = time.time()
        self.save()
        return item

    def remove_item(self, item_id: str, delete_file: bool = False) -> None:
        item = self.items.pop(item_id, None)
        if item and delete_file:
            still_used = {r for it in self.items.values() for r in self.item_images(it)}
            for rel in self.item_images(item):
                if rel in still_used:
                    continue
                try:
                    self.abspath(rel).unlink()
                except OSError:
                    pass
        self.save()

    # -- palettes -----------------------------------------------------------
    def add_palette(self, name: str, colors: list[str], kind: str = "varied",
                    source_image: Path | str | None = None) -> dict:
        pid = new_id()
        rel = self._import_file(source_image, "Palettes", name) if source_image else None
        pal = {"id": pid, "name": name, "colors": colors, "kind": kind, "source": rel,
               "created": time.time()}
        self.palettes[pid] = pal
        self.save()
        return pal

    def update_palette(self, pid: str, **fields: Any) -> dict:
        self.palettes[pid].update(fields)
        self.save()
        return self.palettes[pid]

    def remove_palette(self, pid: str) -> None:
        self.palettes.pop(pid, None)
        self.save()

    # -- patterns -----------------------------------------------------------
    def add_pattern(self, image_src: Path | str, name: str, answers: dict | None = None,
                    traits: dict | None = None, attrs: dict | None = None, cutaway: str = "none",
                    cutaway_mask_src: Path | str | None = None) -> dict:
        """Add a pattern. ``cutaway``: "none", "alpha" (the pattern's transparency cuts
        holes in the garment) or "mask" (a separate black/white mask image does)."""
        pid = new_id()
        rel = self._import_file(image_src, "Patterns", name)
        mask_rel = self._import_file(cutaway_mask_src, "Patterns", f"{name}-cutaway") if cutaway_mask_src else None
        pat = {"id": pid, "name": name, "image": rel, "answers": answers or {}, "traits": traits or {},
               "attrs": attrs or {}, "cutaway": cutaway, "cutaway_mask": mask_rel, "created": time.time()}
        self.patterns[pid] = pat
        self.save()
        return pat

    def update_pattern(self, pid: str, cutaway_mask_src: Path | str | None = None, **fields: Any) -> dict:
        pat = self.patterns[pid]
        if cutaway_mask_src:
            pat["cutaway_mask"] = self._import_file(cutaway_mask_src, "Patterns", f"{pat['name']}-cutaway")
        pat.update(fields)
        self.save()
        return pat

    def remove_pattern(self, pid: str, delete_file: bool = False) -> None:
        pat = self.patterns.pop(pid, None)
        if pat and delete_file:
            try:
                self.abspath(pat["image"]).unlink()
            except OSError:
                pass
        self.save()

    # -- characters ---------------------------------------------------------
    def characters_dir(self) -> Path:
        return self.root / "Characters"

    def list_characters(self) -> list[Path]:
        out = []
        for d in sorted(self.characters_dir().iterdir()) if self.characters_dir().exists() else []:
            if (d / "profile.json").exists():
                out.append(d / "profile.json")
        return out
