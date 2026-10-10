"""Character profiles, palette scanning and automatic wardrobe generation."""
from __future__ import annotations

import itertools
import json
import math
import random
import shutil
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image

from .categories import CATEGORY_BY_NAME, CATEGORY_NAMES, O, Q, Question
from .colors import extract_colors, extract_exact_colors, hex_to_rgb, palette_match, precision_to_threshold, rgb_to_hex, rgb_to_lab
from .imaging import MIN_AUTO_ALPHA, apply_pattern, apply_shine, auto_mask, shine_kind, foreground_mask, load_rgba, recolor_regions_multi, save_rgba
from .patterns import load_pattern, pattern_score
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

# How many pieces an average person owns per outfit slot. Multiplied by the
# "wardrobe size" setting; spread across the categories that share the slot.
SLOT_TARGETS = {
    "underwear_bottom": 7, "bra": 5, "swim_bottom": 2, "swim_top": 2, "swim_full": 1, "sleepwear": 3,
    "base_top": 10, "full_body": 4, "legs": 7, "legwear": 3, "socks": 6, "mid_layer": 4, "corset": 1,
    "outer": 3, "cape": 1, "armor": 1, "apron": 1, "footwear": 4, "head": 2, "eyes": 1, "neck": 2,
    "tie": 1, "hands": 1, "wrists": 1, "arms": 1, "leg_warmers": 1, "waist": 2, "jewelry": 4,
    "bag": 2, "hair": 2, "face": 1, "harness": 1, "extras": 1,
}

DEFAULT_GEN_SETTINGS = {
    "min_score": 35,               # minimum personality match (0-100) for an item to be used
    "wardrobe_size": 1.0,          # 0.3 = minimalist ... 1 = average ... 3 = fashionista
    "max_items_per_category": 6,   # how many different base items per category may be owned
    "max_colourways": 3,           # most versions of one item (only for great matches)
    "multi_palette_chance": 0.2,   # chance a piece mixes two palettes
    "triple_palette_chance": 0.05, # chance a piece mixes three palettes
    "pattern_chance": 0.2,         # chance a piece gets a print (if a suitable pattern exists)
    "favourite_bias": 0.6,         # 0 = all matched palettes equally likely, 1 = mostly the best ones
    "rating_bias": 0.6,            # 0 = all suitable items equally likely, 1 = mostly the best ones
    "exhaustive": False,           # make every item in every palette (old behaviour)
    "seed": 1,
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
        self.data.setdefault("images", [self.data["image"]] if self.data.get("image") else [])
        gs = self.data.setdefault("gen_settings", {})
        for k, v in DEFAULT_GEN_SETTINGS.items():
            gs.setdefault(k, v)
        self.data.setdefault("palette_scan", {"precision": 60, "min_coverage": 0.5,
                                              "image_colors": [], "matches": []})

    # -- creation / persistence ----------------------------------------------
    @classmethod
    def create(cls, library: Library, name: str, image_src: Path | str | list, answers: dict,
               prefs: dict) -> "Character":
        """Create a profile. ``image_src`` may be one image or a list of reference images."""
        folder = unique_path(library.characters_dir() / safe_name(name))
        folder.mkdir(parents=True)
        (folder / "Wardrobe").mkdir()
        (folder / "Outfits").mkdir()
        sources = image_src if isinstance(image_src, (list, tuple)) else [image_src]
        images = []
        for i, src in enumerate(sources):
            src = Path(src)
            dest = unique_path(folder / f"{safe_name(name)}{'' if i == 0 else f'-{i + 1}'}{src.suffix.lower() or '.png'}")
            shutil.copy2(src, dest)
            images.append(dest.name)
        traits, extra = evaluate_character(answers)
        prefs = dict(prefs)
        prefs.setdefault("accessory_level", extra.get("accessory_level", 3))
        data = {
            "id": new_id(), "name": name, "image": images[0], "images": images, "answers": answers,
            "traits": traits, "prefs": prefs, "created": time.time(),
            "gen_settings": dict(DEFAULT_GEN_SETTINGS, seed=random.randrange(1, 1 << 30)),
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
    def image_paths(self) -> list[Path]:
        return [self.dir / i for i in self.data.get("images") or [self.data["image"]]]

    def add_image(self, src: Path | str) -> Path:
        """Add another reference image (used by the palette scan)."""
        src = Path(src)
        n = len(self.data["images"]) + 1
        dest = unique_path(self.dir / f"{safe_name(self.name)}-{n}{src.suffix.lower() or '.png'}")
        shutil.copy2(src, dest)
        self.data["images"].append(dest.name)
        self.data["palette_scan"].pop("image_colors", None)  # force a fresh colour sample
        self.save()
        return dest

    def remove_image(self, name: str) -> None:
        imgs = self.data["images"]
        if name in imgs and len(imgs) > 1:
            imgs.remove(name)
            self.data["image"] = imgs[0]
            self.data["palette_scan"].pop("image_colors", None)
            self.save()

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
        """Match library palettes against the colours of all of the character's images."""
        scan = self.data["palette_scan"]
        if precision is not None:
            scan["precision"] = int(precision)
        if min_coverage is not None:
            scan["min_coverage"] = float(min_coverage)
        if (not scan.get("image_colors") or scan.get("n_colors") != n_colors
                or "exact_colors" not in scan or scan.get("n_images") != len(self.image_paths)):
            colors_all: list = []
            exact_all: list[str] = []
            for path in self.image_paths:
                try:
                    img = load_rgba(path)
                except OSError:
                    continue
                mask = foreground_mask(img)
                colors = extract_colors(img[..., :3], n_colors, mask, min_share=0.004)
                colors_all += [[rgb_to_hex(c), sh / len(self.image_paths)] for c, sh in colors]
                # the true pixel colours too, so exact palettes can match at the highest precision
                exact = extract_exact_colors(img[..., :3], 256, mask, merge_tolerance=0.5, min_share=0.0005)
                exact_all += [rgb_to_hex(c) for c, _ in exact]
            colors_all.sort(key=lambda t: -t[1])
            scan["image_colors"] = colors_all
            scan["exact_colors"] = sorted(set(exact_all))
            scan["n_colors"] = n_colors
            scan["n_images"] = len(self.image_paths)
        hexes = [h for h, _ in scan["image_colors"]] + scan.get("exact_colors", [])
        if not hexes:
            scan["matches"] = []
            self.save()
            return []
        lab = rgb_to_lab(np.array([hex_to_rgb(h) for h in hexes], dtype=float))
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
        excluded = set(self.data["palette_scan"].get("excluded", []))
        for m in self.data["palette_scan"].get("matches", []):
            pal = self.library.palettes.get(m["palette_id"])
            if pal and pal["id"] not in excluded:
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
    @staticmethod
    def _key(item_id: str, palette_ids, pattern_id) -> tuple:
        return (item_id, tuple(palette_ids), pattern_id or None)

    def existing_combos(self) -> set[tuple]:
        return {self._key(e["item_id"], e["palettes"], e.get("pattern")) for e in self.data["wardrobe"].values()}

    def _usable_patterns(self) -> list[dict]:
        excluded = set(self.data.get("gen_settings", {}).get("excluded_patterns", []))
        return [p for p in self.library.patterns.values() if p["id"] not in excluded]

    def plan_wardrobe(self, item_ids: list[str] | None = None) -> list[dict]:
        """Decide which pieces to make.

        Returns a list of {"item", "score", "palettes", "pattern"} dicts. By default the
        choice is realistic and random: each outfit slot gets roughly the number of pieces
        a real person owns (scaled by the wardrobe size), items are drawn with a preference
        for good personality matches, most pieces use a single favourite palette, a few mix
        palettes and some get a print. ``item_ids`` restricts planning to those items
        (used when scanning for new items: each new suitable item gets one or two versions).
        """
        gs = {**DEFAULT_GEN_SETTINGS, **self.data.get("gen_settings", {})}
        palettes = self.matched_palettes()
        if not palettes:
            return []
        ranked = self.rank_items(item_ids)
        existing = self.existing_combos()
        patterns = self._usable_patterns()
        if gs["exhaustive"]:
            return self._plan_exhaustive(ranked, palettes, existing, gs)
        rng = random.Random(f"{gs['seed']}-{len(self.data['wardrobe'])}-{item_ids is None}")

        # candidate items per slot, limited per category
        by_slot: dict[str, list[tuple[dict, float]]] = {}
        for cat in CATEGORY_NAMES:
            good = [(it, sc) for it, sc in ranked.get(cat, []) if sc >= gs["min_score"]]
            for it, sc in good[: gs["max_items_per_category"]]:
                by_slot.setdefault(CATEGORY_BY_NAME[cat].slot, []).append((it, sc))

        owned_per_item: dict[str, int] = {}
        owned_per_slot: dict[str, int] = {}
        for e in self.data["wardrobe"].values():
            owned_per_item[e["item_id"]] = owned_per_item.get(e["item_id"], 0) + 1
            owned_per_slot[e["slot"]] = owned_per_slot.get(e["slot"], 0) + 1

        pal_weights = [(1 - gs["favourite_bias"]) + gs["favourite_bias"] * math.exp(-i / 1.5)
                       for i in range(len(palettes))]

        def cap(score: float) -> int:
            c = 1 + (score >= 60) + (score >= 80)
            return max(1, min(c, gs["max_colourways"]))

        def pick_palettes() -> list[dict]:
            roll = rng.random()
            n = 3 if roll < gs["triple_palette_chance"] else 2 if roll < gs["triple_palette_chance"] + gs["multi_palette_chance"] else 1
            n = min(n, len(palettes))
            chosen: list[dict] = []
            pool = list(range(len(palettes)))
            for _ in range(n):
                w = [pal_weights[i] for i in pool]
                i = rng.choices(pool, weights=w)[0]
                pool.remove(i)
                chosen.append(palettes[i])
            return chosen

        def pick_pattern(item: dict) -> dict | None:
            if not patterns or rng.random() >= gs["pattern_chance"]:
                return None
            scored = [(pattern_score(p, item, self.traits), p) for p in patterns]
            scored = [(sc, p) for sc, p in scored if sc > 0.1]
            if not scored:
                return None
            return rng.choices([p for _, p in scored], weights=[sc * sc for sc, _ in scored])[0]

        plan: list[dict] = []
        planned: set[tuple] = set()
        planned_per_item: dict[str, int] = {}
        for slot, cands in by_slot.items():
            if item_ids is None:
                target = max(1, round(SLOT_TARGETS.get(slot, 1) * gs["wardrobe_size"]))
                need = target - owned_per_slot.get(slot, 0)
            else:
                # new items: each gets one version, great matches sometimes a second
                need = sum(1 + (sc >= 75 and rng.random() < 0.4) for _, sc in cands)
            weights = {it["id"]: max(0.01, (sc / 100.0)) ** (1 + 4 * gs["rating_bias"]) for it, sc in cands}
            attempts = 0
            while need > 0 and attempts < need * 30 + 30:
                attempts += 1
                avail = [(it, sc) for it, sc in cands
                         if owned_per_item.get(it["id"], 0) + planned_per_item.get(it["id"], 0) < cap(sc)]
                if not avail:
                    break
                item, score = rng.choices(avail, weights=[weights[it["id"]] for it, _ in avail])[0]
                pals = pick_palettes()
                pattern = pick_pattern(item)
                key = self._key(item["id"], [p["id"] for p in pals], pattern["id"] if pattern else None)
                if key in existing or key in planned:
                    continue
                planned.add(key)
                planned_per_item[item["id"]] = planned_per_item.get(item["id"], 0) + 1
                plan.append({"item": item, "score": score, "palettes": pals, "pattern": pattern})
                need -= 1
        plan.sort(key=lambda p: (p["item"]["category"], p["item"]["name"]))
        return plan

    def _plan_exhaustive(self, ranked, palettes, existing, gs) -> list[dict]:
        plan = []
        for cat in CATEGORY_NAMES:
            entries = [(it, sc) for it, sc in ranked.get(cat, []) if sc >= gs["min_score"]]
            for item, score in entries[: gs["max_items_per_category"]]:
                combos = [(p,) for p in palettes]
                combos += list(itertools.combinations(palettes, 2))[:3]
                for combo in combos:
                    if self._key(item["id"], [p["id"] for p in combo], None) not in existing:
                        plan.append({"item": item, "score": score, "palettes": list(combo), "pattern": None})
        return plan

    def plan_summary(self, plan: list[dict]) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in plan:
            out[p["item"]["category"]] = out.get(p["item"]["category"], 0) + 1
        return out

    def render_piece(self, item: dict, palettes: list[dict], pattern: dict | None,
                     cache: dict | None = None, shine_out: list | None = None) -> list[np.ndarray]:
        """Recolour (and optionally print) every image of an item the same way.

        Palettes whose name contains "metallic" or "silk" (also chrome / metal / satin) get a
        shine on exactly the pixels they coloured; if no palette asks for it but the item's
        own name does, the item's main palette shines. ``shine_out`` receives, per image,
        the (mask, kind) pairs that were applied.
        """
        cache = cache if cache is not None else {}
        if item["id"] not in cache:
            imgs = [load_rgba(self.library.abspath(rel)) for rel in Library.item_images(item)]
            cache.clear()
            cache[item["id"]] = (imgs, [auto_mask(im) for im in imgs])
        imgs, masks = cache[item["id"]]
        pal_masks: list = []
        outs, primaries = recolor_regions_multi(imgs, masks, [p["colors"] for p in palettes],
                                                [p.get("kind", "varied") for p in palettes],
                                                palette_masks_out=pal_masks)
        if pattern:
            pat, cut = load_pattern(self.library, pattern)
            pat_palette = palettes[1]["colors"] if len(palettes) > 1 else palettes[0]["colors"]
            whole = (item.get("attrs", {}).get("print") == "whole"
                     or pattern.get("attrs", {}).get("placement") == "whole")
            repeats = pattern.get("attrs", {}).get("repeats", 6)
            for i, (out, mask, prim) in enumerate(zip(outs, masks, primaries)):
                region = mask if whole or not prim.any() else prim & mask
                if not region.any():
                    continue
                xs = np.flatnonzero(region.any(axis=0))
                width = xs[-1] - xs[0] + 1
                scale = max(0.05, width / max(repeats, 1) / pat.shape[1])
                outs[i] = apply_pattern(out, region, pat, scale=scale, antialias=True,
                                        palette=pat_palette, blend="shaded", cutaway=cut,
                                        offset=(int(xs[0]), 0))
        # metallic / silk shine, limited to the pixels of the palette that asks for it
        shiny = [(g, shine_kind(p["name"])) for g, p in enumerate(palettes) if shine_kind(p["name"])]
        if not shiny and shine_kind(item["name"]):
            shiny = [(0, shine_kind(item["name"]))]
        for i in range(len(outs)):
            applied = []
            for g, kind in shiny:
                m = pal_masks[i][g] & (outs[i][..., 3] >= MIN_AUTO_ALPHA) if pal_masks else None
                if m is not None and m.any():
                    outs[i] = apply_shine(outs[i], m, kind)
                    applied.append((m, kind))
            if shine_out is not None:
                shine_out.append(applied)
        return outs

    def build_wardrobe(self, item_ids: list[str] | None = None,
                       progress: Callable[[int, int, str], bool] | None = None,
                       plan: list[dict] | None = None) -> list[dict]:
        """Generate wardrobe images.

        ``item_ids`` limits the scan to those items (None = whole library). ``plan`` may be
        a plan from :meth:`plan_wardrobe` (so a previewed plan is built exactly).
        ``progress`` is called with (done, total, message) and may return False to cancel.
        New files never overwrite existing ones.
        """
        plan = plan if plan is not None else self.plan_wardrobe(item_ids)
        created = []
        cache: dict = {}
        total = len(plan)
        unfinished: set[str] = set()
        for i, piece in enumerate(plan):
            item, score, combo, pattern = piece["item"], piece["score"], piece["palettes"], piece["pattern"]
            pal_names = "+".join(p["name"] for p in combo)
            label = f"{item['name']} - {pal_names}" + (f" - {pattern['name']}" if pattern else "")
            if progress and progress(i, total, label) is False:
                unfinished = {p["item"]["id"] for p in plan[i:]}
                break
            shine: list = []
            try:
                outs = self.render_piece(item, combo, pattern, cache, shine_out=shine)
            except OSError:
                continue
            base = safe_name(f"{self.name}-{item['name']}-{pal_names}" + (f"-{pattern['name']}" if pattern else ""))
            files = []
            first = unique_path(self.wardrobe_dir / f"{base}.png")
            for n, out in enumerate(outs):
                dest = first if n == 0 else unique_path(first.with_name(f"{first.stem}-{n + 1}.png"))
                save_rgba(out, dest)
                files.append(dest.relative_to(self.dir).as_posix())
            # save each shine mask (white = shiny) so the effect can be traced / reused
            shine_files = []
            for n, applied in enumerate(shine):
                if not applied:
                    continue
                combined = np.zeros(applied[0][0].shape, dtype=bool)
                for m, _kind in applied:
                    combined |= m
                mask_dir = self.wardrobe_dir / "Masks"
                mask_dir.mkdir(exist_ok=True)
                mpath = unique_path(mask_dir / f"{Path(files[n]).stem}-shine.png")
                Image.fromarray((combined * 255).astype(np.uint8), "L").save(mpath)
                shine_files.append(mpath.relative_to(self.dir).as_posix())
            shine_kinds = sorted({k for applied in shine for _m, k in applied})
            cat = CATEGORY_BY_NAME.get(item["category"])
            entry = {
                "id": new_id(), "item_id": item["id"], "item_name": item["name"],
                "category": item["category"], "slot": cat.slot if cat else "extras",
                "palettes": [p["id"] for p in combo], "palette_names": [p["name"] for p in combo],
                "pattern": pattern["id"] if pattern else None,
                "pattern_name": pattern["name"] if pattern else None,
                "file": files[0], "files": files, "rating": score, "created": time.time(),
                "shine": shine_kinds, "shine_masks": shine_files,
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
            for rel in (entry.get("files") or [entry["file"]]) + entry.get("shine_masks", []):
                try:
                    (self.dir / rel).unlink()
                except OSError:
                    pass
        self.save()

    def ensure_shine_masks(self, entry: dict) -> bool:
        """Create the shine masks of an older piece whose palettes ask for a shine.

        Re-renders the piece in memory (files are not touched) to find exactly which pixels
        each "Metallic" / "Silk" palette coloured. Returns True if masks were added.
        """
        if entry.get("shine_masks"):
            return False
        palettes = [self.library.palettes.get(pid) for pid in entry.get("palettes", [])]
        item = self.library.items.get(entry.get("item_id"))
        if not item or not all(palettes):
            return False
        if not any(shine_kind(p["name"]) for p in palettes) and not shine_kind(item["name"]):
            return False
        pattern = self.library.patterns.get(entry.get("pattern")) if entry.get("pattern") else None
        shine: list = []
        try:
            self.render_piece(item, palettes, pattern, {}, shine_out=shine)
        except OSError:
            return False
        files, kinds = [], set()
        for n, applied in enumerate(shine):
            if not applied:
                continue
            combined = np.zeros(applied[0][0].shape, dtype=bool)
            for m, kind in applied:
                combined |= m
                kinds.add(kind)
            mask_dir = self.wardrobe_dir / "Masks"
            mask_dir.mkdir(exist_ok=True)
            src = (entry.get("files") or [entry["file"]])[min(n, len(entry.get("files") or [1]) - 1)]
            mpath = unique_path(mask_dir / f"{Path(src).stem}-shine.png")
            Image.fromarray((combined * 255).astype(np.uint8), "L").save(mpath)
            files.append(mpath.relative_to(self.dir).as_posix())
        if not files:
            return False
        entry["shine"] = sorted(kinds)
        entry["shine_masks"] = files
        self.save()
        return True

    def entry_path(self, entry: dict) -> Path:
        return self.dir / entry["file"]

    def entry_paths(self, entry: dict) -> list[Path]:
        return [self.dir / f for f in entry.get("files") or [entry["file"]]]


def list_characters(library: Library) -> list[Character]:
    out = []
    for path in library.list_characters():
        try:
            out.append(Character(library, path))
        except (OSError, ValueError):
            continue
    return out
