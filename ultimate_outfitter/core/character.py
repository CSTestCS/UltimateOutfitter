"""Character profiles, palette scanning and automatic wardrobe generation."""
from __future__ import annotations

import itertools
import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .categories import CATEGORY_BY_NAME, CATEGORY_NAMES, O, Q, Question
from .colors import extract_colors, hex_to_rgb, palette_match, precision_to_threshold, rgb_to_hex, rgb_to_lab
from .imaging import foreground_mask, load_rgba, recolor_regions, save_rgba
from .storage import Library, new_id, safe_name, unique_path, write_json_atomic
from .traits import add_into, cosine, normalize

# ---------------------------------------------------------------------------
# Character questionnaire
# ---------------------------------------------------------------------------

CHARACTER_QUESTIONS: list[Question] = [
    Q("crowd", "How do they act in a crowd?", [
        O("Centre of attention", "bold:2 confident playful"),
        O("Friendly and easygoing", "cheerful laid_back"),
        O("Quiet observer", "reserved mysterious intellectual"),
        O("Avoids crowds altogether", "reserved:2 cozy"),
        O("Takes charge", "confident:2 regal professional"),
    ]),
    Q("weekend", "What is their ideal free day?", [
        O("Partying or socialising", "playful bold flirty"),
        O("Reading or studying", "intellectual:2 cozy reserved"),
        O("Hiking or exploring", "adventurous:2 nature_loving sporty"),
        O("Training or sports", "sporty:2 tough"),
        O("Making art or music", "artistic:2"),
        O("Shopping or pampering", "glamorous:2 elegant"),
        O("Gaming or lounging at home", "laid_back:2 cozy"),
        O("Studying magic or the occult", "magical:2 mysterious gothic"),
        O("Gardening or caring for animals", "nature_loving:2 cute cozy"),
    ]),
    Q("perceived", "How do they want to be perceived?", [
        O("Powerful", "confident regal tough"),
        O("Approachable", "cheerful cute laid_back"),
        O("Attractive", "flirty:2 glamorous"),
        O("Respected", "professional elegant intellectual"),
        O("Feared", "edgy gothic tough"),
        O("Unnoticed", "reserved:2 modest"),
        O("Unique", "artistic edgy bold"),
    ]),
    Q("rules", "What is their attitude towards rules?", [
        O("Follows them strictly", "traditional professional modest"),
        O("Follows them mostly", "practical"),
        O("Bends them for fun", "playful"),
        O("Breaks them on purpose", "rebellious:2 edgy"),
    ]),
    Q("comfort", "Comfort or style?", [
        O("Comfort always", "cozy laid_back practical"),
        O("A balance of both", "practical"),
        O("Style first", "glamorous bold elegant"),
        O("Function first", "practical:2 tough"),
    ]),
    Q("modesty", "How much skin are they comfortable showing?", [
        O("Very little", "modest:2 reserved"),
        O("Some", "laid_back"),
        O("Quite a lot", "flirty confident"),
        O("Whatever they like - very daring", "flirty:2 bold:2"),
    ]),
    Q("role", "What is their role or occupation?", [
        O("Office / business", "professional:2 intellectual"),
        O("Student", "intellectual cute playful"),
        O("Adventurer / explorer", "adventurous:2 practical"),
        O("Warrior / soldier / guard", "tough:2 practical"),
        O("Mage / witch / mystic", "magical:2 mysterious"),
        O("Noble / royalty", "regal:2 elegant"),
        O("Artist / musician", "artistic:2"),
        O("Athlete", "sporty:2"),
        O("Labourer / craftsperson", "practical:2 tough"),
        O("Entertainer / idol", "glamorous bold cheerful"),
        O("Scholar / scientist", "intellectual:2"),
        O("Rogue / outlaw / thief", "rebellious mysterious edgy"),
        O("Healer / caretaker", "nature_loving cute modest"),
        O("Homebody / homemaker", "cozy traditional"),
    ]),
    Q("temperament", "What is their temperament?", [
        O("Sunny and optimistic", "cheerful:2 playful"),
        O("Calm and serene", "laid_back elegant minimalist"),
        O("Brooding", "mysterious gothic reserved"),
        O("Fiery", "bold rebellious confident"),
        O("Sweet and gentle", "cute romantic"),
        O("Stoic", "reserved tough practical"),
        O("Mischievous", "playful rebellious"),
    ]),
    Q("aesthetic", "Which aesthetics suit them? (choose any)", [
        O("Minimal / clean", "minimalist:2"),
        O("Cute / kawaii", "cute:2"),
        O("Gothic / dark", "gothic:2"),
        O("Punk / grunge", "rebellious:2 edgy"),
        O("Romantic / soft", "romantic:2"),
        O("Glam / luxury", "glamorous:2"),
        O("Sporty", "sporty:2"),
        O("Preppy / academic", "intellectual professional"),
        O("Boho / earthy", "nature_loving artistic"),
        O("Fantasy", "magical adventurous"),
        O("Vintage / historical", "traditional:2"),
        O("Streetwear", "edgy laid_back confident"),
        O("Cottagecore", "nature_loving cozy cute"),
        O("Military / utility", "tough practical"),
        O("Regal / aristocratic", "regal:2 elegant"),
    ], multi=True),
    Q("love", "How are they in romance?", [
        O("Hopeless romantic", "romantic:2"),
        O("Shameless flirt", "flirty:2 playful"),
        O("Shy", "reserved cute"),
        O("Not interested", "practical reserved"),
        O("Mysterious and aloof", "mysterious:2"),
    ]),
    Q("accessories", "How much do they accessorise?", [
        O("Barely at all", "minimalist:2 practical", accessory_level=1),
        O("A few pieces", "elegant", accessory_level=2),
        O("A good amount", "artistic", accessory_level=3),
        O("As much as possible", "glamorous bold artistic", accessory_level=5),
    ]),
    Q("colors", "What colours do they gravitate to?", [
        O("Dark colours", "gothic mysterious"),
        O("Pastels", "cute romantic"),
        O("Brights", "cheerful bold"),
        O("Neutrals / earth tones", "nature_loving minimalist practical"),
        O("Rich jewel tones", "regal elegant"),
        O("Anything goes", "playful artistic"),
    ]),
]

BRA_CHOICES = ["Yes", "Sometimes", "No"]


def evaluate_character(answers: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    traits: dict[str, float] = {}
    extra: dict[str, Any] = {}
    for q in CHARACTER_QUESTIONS:
        ans = answers.get(q.id)
        if ans is None:
            continue
        chosen = ans if isinstance(ans, list) else [ans]
        for opt in q.options:
            if opt.label in chosen:
                add_into(traits, opt.traits)
                extra.update(opt.attrs)
    return normalize(traits), extra


# ---------------------------------------------------------------------------
# Character profile
# ---------------------------------------------------------------------------

DEFAULT_GEN_SETTINGS = {
    "min_score": 35,               # minimum match (0-100) for an item to be used
    "max_items_per_category": 12,  # best N items per category
    # per tier (top 20%, next 30%, next 30%, rest): number of recolours
    "singles": [99, 6, 3, 1],
    "pairs": [6, 2, 0, 0],
    "triples": [3, 0, 0, 0],
}


class Character:
    def __init__(self, library: Library, profile_path: Path):
        self.library = library
        self.path = Path(profile_path)
        self.dir = self.path.parent
        self.data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        self.data.setdefault("wardrobe", {})
        self.data.setdefault("dresser", [])
        self.data.setdefault("hamper", [])
        self.data.setdefault("processed_items", [])
        self.data.setdefault("item_ratings", {})
        self.data.setdefault("outfit_history", [])
        self.data.setdefault("gen_settings", dict(DEFAULT_GEN_SETTINGS))
        self.data.setdefault("palette_scan", {"precision": 60, "min_coverage": 0.5,
                                              "image_colors": [], "matches": []})

    # -- creation / persistence ----------------------------------------------
    @classmethod
    def create(cls, library: Library, name: str, image_src: Path | str, answers: dict,
               prefs: dict) -> "Character":
        folder = unique_path(library.characters_dir() / safe_name(name))
        folder.mkdir(parents=True)
        (folder / "Wardrobe").mkdir()
        (folder / "Outfits").mkdir()
        image_src = Path(image_src)
        img_name = f"{safe_name(name)}{image_src.suffix.lower() or '.png'}"
        shutil.copy2(image_src, folder / img_name)
        traits, extra = evaluate_character(answers)
        prefs = dict(prefs)
        prefs.setdefault("accessory_level", extra.get("accessory_level", 3))
        data = {
            "id": new_id(), "name": name, "image": img_name, "answers": answers,
            "traits": traits, "prefs": prefs, "created": time.time(),
        }
        path = folder / "profile.json"
        write_json_atomic(path, data)
        return cls(library, path)

    def save(self) -> None:
        write_json_atomic(self.path, self.data)

    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def traits(self) -> dict[str, float]:
        return self.data.get("traits", {})

    @property
    def image_path(self) -> Path:
        return self.dir / self.data["image"]

    @property
    def wardrobe_dir(self) -> Path:
        d = self.dir / "Wardrobe"
        d.mkdir(exist_ok=True)
        return d

    def update_answers(self, answers: dict, prefs: dict) -> None:
        traits, extra = evaluate_character(answers)
        self.data["answers"] = answers
        self.data["traits"] = traits
        prefs = dict(prefs)
        prefs.setdefault("accessory_level", extra.get("accessory_level", 3))
        self.data["prefs"] = prefs
        self.save()

    # -- palette scan ----------------------------------------------------------
    def scan_palettes(self, precision: int | None = None, min_coverage: float | None = None,
                      n_colors: int = 16) -> list[dict]:
        scan = self.data["palette_scan"]
        if precision is not None:
            scan["precision"] = int(precision)
        if min_coverage is not None:
            scan["min_coverage"] = float(min_coverage)
        if not scan.get("image_colors") or scan.get("n_colors") != n_colors:
            img = load_rgba(self.image_path)
            mask = foreground_mask(img)
            colors = extract_colors(img[..., :3], n_colors, mask, min_share=0.004)
            scan["image_colors"] = [[rgb_to_hex(c), s] for c, s in colors]
            scan["n_colors"] = n_colors
        lab = rgb_to_lab(np.array([hex_to_rgb(h) for h, _ in scan["image_colors"]], dtype=float))
        threshold = precision_to_threshold(scan["precision"])
        matches = []
        for pal in self.library.palettes.values():
            coverage, dist = palette_match(pal["colors"], lab, threshold)
            if coverage >= scan["min_coverage"] and coverage > 0:
                matches.append({"palette_id": pal["id"], "coverage": round(coverage, 3),
                                "distance": round(dist, 2)})
        matches.sort(key=lambda m: (-m["coverage"], m["distance"]))
        scan["matches"] = matches
        scan["threshold"] = threshold
        self.save()
        return matches

    def matched_palettes(self) -> list[dict]:
        out = []
        for m in self.data["palette_scan"].get("matches", []):
            pal = self.library.palettes.get(m["palette_id"])
            if pal:
                out.append(pal)
        return out

    # -- item rating -----------------------------------------------------------
    def rate_item(self, item: dict) -> float:
        prefs = self.data.get("prefs", {})
        if item["category"] in prefs.get("excluded_categories", []):
            return 0.0
        if item["category"] == "Bras" and prefs.get("wears_bra") == "No":
            return 0.0
        return round(100 * cosine(self.traits, item.get("traits", {})), 1)

    def rank_items(self, item_ids: list[str] | None = None) -> dict[str, list[tuple[dict, float]]]:
        """Rate items and group them by category, best first."""
        items = (self.library.items.values() if item_ids is None
                 else [self.library.items[i] for i in item_ids if i in self.library.items])
        by_cat: dict[str, list[tuple[dict, float]]] = {}
        for item in items:
            score = self.rate_item(item)
            self.data["item_ratings"][item["id"]] = score
            by_cat.setdefault(item["category"], []).append((item, score))
        for lst in by_cat.values():
            lst.sort(key=lambda t: -t[1])
        return by_cat

    # -- wardrobe generation ---------------------------------------------------
    def existing_combos(self) -> set[tuple[str, tuple[str, ...]]]:
        return {(e["item_id"], tuple(e["palettes"])) for e in self.data["wardrobe"].values()}

    def plan_wardrobe(self, item_ids: list[str] | None = None) -> list[tuple[dict, float, list[dict]]]:
        """Decide which recolours to make. Returns [(item, score, [palettes...])]."""
        settings = {**DEFAULT_GEN_SETTINGS, **self.data.get("gen_settings", {})}
        palettes = self.matched_palettes()
        if not palettes:
            return []
        ranked = self.rank_items(item_ids)
        existing = self.existing_combos()
        plan = []
        for cat in CATEGORY_NAMES:
            entries = [(it, s) for it, s in ranked.get(cat, []) if s >= settings["min_score"]]
            entries = entries[: settings["max_items_per_category"]]
            n = len(entries)
            for rank, (item, score) in enumerate(entries):
                frac = rank / max(n, 1)
                tier = 0 if frac < 0.2 else 1 if frac < 0.5 else 2 if frac < 0.8 else 3
                if score >= 80 and tier > 0:
                    tier -= 1  # excellent matches always get extra variety
                combos: list[tuple[dict, ...]] = []
                combos += [(p,) for p in palettes[: settings["singles"][tier]]]
                if len(palettes) >= 2 and settings["pairs"][tier]:
                    combos += list(itertools.combinations(palettes, 2))[: settings["pairs"][tier]]
                if len(palettes) >= 3 and settings["triples"][tier]:
                    combos += list(itertools.combinations(palettes, 3))[: settings["triples"][tier]]
                for combo in combos:
                    key = (item["id"], tuple(p["id"] for p in combo))
                    if key in existing:
                        continue
                    plan.append((item, score, list(combo)))
        return plan

    def build_wardrobe(self, item_ids: list[str] | None = None,
                       progress: Callable[[int, int, str], bool] | None = None) -> list[dict]:
        """Generate recoloured wardrobe images.

        ``item_ids`` limits the scan to those items (None = whole library). ``progress``
        is called with (done, total, message) and may return False to cancel.
        New files never overwrite existing ones.
        """
        plan = self.plan_wardrobe(item_ids)
        created = []
        cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        total = len(plan)
        unfinished: set[str] = set()
        for i, (item, score, combo) in enumerate(plan):
            pal_names = "+".join(p["name"] for p in combo)
            if progress and progress(i, total, f"{item['name']} - {pal_names}") is False:
                unfinished = {it["id"] for it, _, _ in plan[i:]}
                break
            if item["id"] not in cache:
                try:
                    img = load_rgba(self.library.abspath(item["image"]))
                except OSError:
                    continue
                cache = {item["id"]: (img, foreground_mask(img))}
            img, mask = cache[item["id"]]
            out = recolor_regions(img, mask, [p["colors"] for p in combo])
            fname = safe_name(f"{self.name}-{item['name']}-{pal_names}") + ".png"
            dest = unique_path(self.wardrobe_dir / fname)
            save_rgba(out, dest)
            cat = CATEGORY_BY_NAME.get(item["category"])
            entry = {
                "id": new_id(), "item_id": item["id"], "item_name": item["name"],
                "category": item["category"], "slot": cat.slot if cat else "extras",
                "palettes": [p["id"] for p in combo], "palette_names": [p["name"] for p in combo],
                "file": dest.relative_to(self.dir).as_posix(), "rating": score,
                "created": time.time(),
            }
            self.data["wardrobe"][entry["id"]] = entry
            self.data["dresser"].append(entry["id"])
            created.append(entry)
            if i % 10 == 0:
                self.save()
        processed = set(self.data["processed_items"])
        ids = item_ids if item_ids is not None else list(self.library.items)
        processed.update(i for i in ids if i not in unfinished)
        self.data["processed_items"] = sorted(processed)
        self.data["last_build"] = time.time()
        self.save()
        if progress and not unfinished:
            progress(total, total, "Done")
        return created

    def new_item_ids(self) -> list[str]:
        done = set(self.data["processed_items"])
        return [i for i in self.library.items if i not in done]

    def remove_entry(self, entry_id: str, delete_file: bool = False) -> None:
        entry = self.data["wardrobe"].pop(entry_id, None)
        for key in ("dresser", "hamper"):
            if entry_id in self.data[key]:
                self.data[key].remove(entry_id)
        if entry and delete_file:
            try:
                (self.dir / entry["file"]).unlink()
            except OSError:
                pass
        self.save()

    def entry_path(self, entry: dict) -> Path:
        return self.dir / entry["file"]


def list_characters(library: Library) -> list[Character]:
    out = []
    for path in library.list_characters():
        try:
            out.append(Character(library, path))
        except (OSError, ValueError):
            continue
    return out
