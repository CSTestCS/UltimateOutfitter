"""Daily outfit planning from a character's dresser, with approve / reject feedback."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from .categories import ACCESSORY_SLOTS, CATEGORY_BY_NAME, MULTI_SLOTS, SLOTS, WEATHER_WARMTH
from .character import Character
from .storage import unique_path
from .traits import cosine

MOODS = {
    "Happy": "cheerful playful cute",
    "Calm": "laid_back minimalist elegant",
    "Sad": "cozy reserved",
    "Energetic": "sporty bold playful",
    "Romantic": "romantic flirty elegant",
    "Confident": "confident bold glamorous",
    "Cozy / tired": "cozy laid_back",
    "Grumpy / dark": "gothic edgy reserved",
    "Mysterious": "mysterious gothic",
    "Focused": "professional intellectual practical",
    "Adventurous": "adventurous practical sporty",
    "Playful": "playful cute cheerful",
    "Fancy": "glamorous elegant regal",
}

ACTIVITY_FORMALITY = {
    "Lounging at home": 0, "Casual / errands": 1, "Work / office": 2.5,
    "School / studying": 1.5, "Formal event": 3.5, "Date": 2, "Party / night out": 2,
    "Workout / sports": 0.5, "Swimming / beach": 0, "Outdoors / adventure": 1,
    "Combat / battle": 1, "Sleeping": 0, "Manual work / crafting": 1,
    "Ceremony / festival": 3,
}

ACTIVITY_TRAITS = {
    "Workout / sports": "sporty:2 practical",
    "Outdoors / adventure": "adventurous practical",
    "Combat / battle": "tough:2 practical",
    "Formal event": "elegant regal glamorous",
    "Work / office": "professional",
    "Date": "romantic flirty",
    "Party / night out": "bold glamorous playful",
    "Manual work / crafting": "practical",
    "Lounging at home": "cozy laid_back",
    "Sleeping": "cozy",
}

REJECT_REASONS = {
    "clash": "Clashing colours",
    "unnecessary": "Not necessary (e.g. a skirt over a dress)",
    "overlap": "Overlaps with another piece",
    "weather": "Not suitable for the weather",
    "activity": "Not suitable for the activity",
    "formality": "Too formal / too casual",
    "style": "Doesn't fit the character's style",
    "other": "Just try something else",
}


def _parse(traits: str) -> dict[str, float]:
    out = {}
    for tok in traits.split():
        k, _, w = tok.partition(":")
        out[k] = float(w) if w else 1.0
    return out


@dataclass
class DayContext:
    activity: str
    mood: str
    weather: str
    formality: float | None = None   # None -> derived from activity
    notes: str = ""

    def target_formality(self) -> float:
        return self.formality if self.formality is not None else ACTIVITY_FORMALITY.get(self.activity, 1)

    def needed_warmth(self) -> int:
        return WEATHER_WARMTH.get(self.weather, 2)

    def to_dict(self) -> dict[str, Any]:
        return {"activity": self.activity, "mood": self.mood, "weather": self.weather,
                "formality": self.formality, "notes": self.notes}


class NoOutfitPossible(Exception):
    """Raised when required pieces are all in the hamper (laundry needed)."""

    def __init__(self, missing: list[str], laundry_helps: bool):
        self.missing = missing
        self.laundry_helps = laundry_helps
        super().__init__(", ".join(missing))


@dataclass
class OutfitSession:
    character: Character
    context: DayContext
    proposal: dict[str, list[str]] = field(default_factory=dict)   # slot -> entry ids
    approved: set[str] = field(default_factory=set)                 # entry ids
    excluded_entries: set[str] = field(default_factory=set)
    excluded_items: set[str] = field(default_factory=set)
    skipped_slots: set[str] = field(default_factory=set)
    slot_avoid_palettes: dict[str, set[str]] = field(default_factory=dict)
    slot_excluded_categories: dict[str, set[str]] = field(default_factory=dict)
    slot_weights: dict[str, dict[str, float]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    seed: int = field(default_factory=lambda: random.randrange(1 << 30))

    # ------------------------------------------------------------------ data
    @property
    def wardrobe(self) -> dict[str, dict]:
        return self.character.data["wardrobe"]

    def dresser_entries(self) -> list[dict]:
        return [self.wardrobe[e] for e in self.character.data["dresser"] if e in self.wardrobe]

    def owned_slots(self) -> set[str]:
        return {e["slot"] for e in self.wardrobe.values()}

    def in_use(self) -> set[str]:
        return {e for ids in self.proposal.values() for e in ids}

    def item_attrs(self, entry: dict) -> dict:
        item = self.character.library.items.get(entry["item_id"], {})
        return item.get("attrs", {})

    def item_traits(self, entry: dict) -> dict:
        item = self.character.library.items.get(entry["item_id"], {})
        return item.get("traits", {})

    # --------------------------------------------------------------- scoring
    def score(self, entry: dict, slot: str) -> float:
        ctx = self.context
        attrs = self.item_attrs(entry)
        w = {"activity": 1.0, "weather": 1.0, "formality": 1.0, "clash": 1.0,
             **self.slot_weights.get(slot, {})}
        s = entry.get("rating", 50) * 0.4
        acts = attrs.get("activities", [])
        cat = CATEGORY_BY_NAME.get(entry["category"])
        specialised = cat.activities if cat else []
        if ctx.activity in acts:
            s += 25 * w["activity"]
        elif specialised and ctx.activity not in specialised:
            s -= 30 * w["activity"]
        elif acts:
            s -= 5 * w["activity"]
        act_traits = _parse(ACTIVITY_TRAITS.get(ctx.activity, ""))
        if act_traits:
            s += 15 * cosine(self.item_traits(entry), act_traits) * w["activity"]
        s -= 8 * abs(attrs.get("formality", 1) - ctx.target_formality()) * w["formality"]
        need = ctx.needed_warmth()
        warmth = attrs.get("warmth", 2)
        if slot in ("outer", "mid_layer", "cape"):
            s -= 6 * abs(warmth - need) * w["weather"]
        elif slot not in ACCESSORY_SLOTS or slot in ("hands", "neck", "head", "leg_warmers"):
            if warmth > need + 1:
                s -= 7 * (warmth - need - 1) * w["weather"]
            if warmth < need - 2:
                s -= 7 * (need - 2 - warmth) * w["weather"]
        if ctx.weather == "Rainy" and entry["category"] in ("Sandals",):
            s -= 15 * w["weather"]
        s += 20 * cosine(self.item_traits(entry), _parse(MOODS.get(ctx.mood, "")))
        # colour harmony with pieces already chosen
        chosen_pals = set()
        for sl, ids in self.proposal.items():
            if sl == slot:
                continue
            for eid in ids:
                chosen_pals.update(self.wardrobe[eid]["palettes"])
        shared = len(chosen_pals & set(entry["palettes"]))
        s += 6 * shared * w["clash"]
        avoid = self.slot_avoid_palettes.get(slot, set())
        s -= 40 * len(avoid & set(entry["palettes"])) * w["clash"]
        rng = random.Random(f"{self.seed}-{entry['id']}")
        s += rng.uniform(0, 6)
        return s

    def candidates(self, slot: str, extra_exclude: set[str] | None = None) -> list[tuple[float, dict]]:
        used = self.in_use()
        used_items = {self.wardrobe[e]["item_id"] for e in used}
        bad_cats = self.slot_excluded_categories.get(slot, set())
        out = []
        for e in self.dresser_entries():
            if e["slot"] != slot or e["id"] in used or e["id"] in self.excluded_entries:
                continue
            if e["item_id"] in self.excluded_items or e["item_id"] in used_items:
                continue
            if e["category"] in bad_cats:
                continue
            if extra_exclude and e["id"] in extra_exclude:
                continue
            out.append((self.score(e, slot), e))
        out.sort(key=lambda t: -t[0])
        return out

    # ------------------------------------------------------------- planning
    def _slot_plan(self) -> tuple[list[str], list[str], list[list[str]]]:
        """Return (required slots, optional slots, alternative core groups)."""
        ctx = self.context
        prefs = self.character.data.get("prefs", {})
        need = ctx.needed_warmth()
        required: list[str] = []
        optional: list[str] = []
        if ctx.activity == "Sleeping":
            required = ["underwear_bottom"]
            core = [["sleepwear"], ["base_top", "legs"], ["full_body"]]
            return required, optional, core
        if ctx.activity == "Swimming / beach":
            core = [["swim_full"], ["swim_top", "swim_bottom"]]
            optional = ["footwear", "head", "eyes", "jewelry", "hair", "bag"]
            return required, optional, core
        required.append("underwear_bottom")
        wears_bra = prefs.get("wears_bra", "Yes")
        if wears_bra == "Yes":
            required.append("bra")
        elif wears_bra == "Sometimes":
            optional.append("bra")
        core = [["base_top", "legs"], ["full_body"]]
        if ctx.activity != "Lounging at home":
            required.append("footwear")
            (required if need >= 3 else optional).append("socks")
        else:
            optional += ["socks", "footwear"]
        if need >= 3:
            (required if need >= 4 else optional).append("mid_layer")
        if need >= 4 or ctx.weather in ("Rainy", "Windy"):
            required.append("outer")
        elif ctx.activity in ("Work / office", "Formal event", "School / studying") or need >= 3:
            optional.append("outer")
        if ctx.activity == "Combat / battle":
            optional.insert(0, "armor")
        if ctx.activity == "Manual work / crafting":
            optional.insert(0, "apron")
        optional.append("legwear")
        if need >= 3:
            optional += ["hands", "neck", "leg_warmers"]
        optional += [s for s in ("head", "eyes", "jewelry", "waist", "tie", "wrists", "arms",
                                 "hair", "bag", "corset", "cape", "face", "harness", "extras",
                                 "hands", "neck", "leg_warmers")
                     if s not in optional]
        return required, optional, core

    def _fill_slot(self, slot: str) -> bool:
        cands = self.candidates(slot)
        if not cands:
            return False
        self.proposal[slot] = [cands[0][1]["id"]]
        return True

    def build(self) -> dict[str, list[str]]:
        """Create a full outfit proposal. Raises NoOutfitPossible if laundry is needed."""
        self.proposal = {}
        self.warnings = []
        required, optional, core_groups = self._slot_plan()
        owned = self.owned_slots()
        missing: list[str] = []
        laundry_helps = False

        def available(slot):
            return any(e["slot"] == slot for e in self.dresser_entries())

        # core garments: choose the alternative group with the best average top score
        best_group, best_score = None, -1e9
        for group in core_groups:
            if not all(available(s) for s in group):
                continue
            score = sum(self.candidates(s)[0][0] for s in group if self.candidates(s)) / len(group)
            if score > best_score:
                best_group, best_score = group, score
        if best_group is None:
            owned_group = any(all(s in owned for s in g) for g in core_groups)
            missing.append(" / ".join("+".join(SLOTS[s] for s in g) for g in core_groups))
            laundry_helps = laundry_helps or owned_group
        else:
            for s in best_group:
                self._fill_slot(s)

        for slot in required:
            if slot in self.skipped_slots:
                continue
            if not self._fill_slot(slot):
                if slot in owned:
                    missing.append(SLOTS[slot])
                    laundry_helps = True
                else:
                    self.warnings.append(f"{self.character.name} owns no {SLOTS[slot].lower()} items.")
        if missing and (laundry_helps or best_group is None):
            raise NoOutfitPossible(missing, laundry_helps)

        acc_level = self.character.data.get("prefs", {}).get("accessory_level", 3)
        accessories_added = 0
        for slot in optional:
            if slot in self.skipped_slots or slot in self.proposal:
                continue
            is_acc = slot in ACCESSORY_SLOTS
            if is_acc and accessories_added >= acc_level:
                continue
            cands = self.candidates(slot)
            if not cands:
                continue
            threshold = 30 if not is_acc else 35 + 4 * (3 - acc_level)
            if cands[0][0] < threshold:
                continue
            picks = [cands[0][1]["id"]]
            extra = MULTI_SLOTS.get(slot, 1) - 1
            for sc, e in cands[1:]:
                if extra <= 0 or accessories_added + len(picks) >= acc_level:
                    break
                if sc >= threshold and e["category"] not in {self.wardrobe[p]["category"] for p in picks}:
                    picks.append(e["id"])
                    extra -= 1
            self.proposal[slot] = picks
            if is_acc:
                accessories_added += len(picks)
        return self.proposal

    # --------------------------------------------------------- feedback loop
    def slot_of(self, entry_id: str) -> str | None:
        for slot, ids in self.proposal.items():
            if entry_id in ids:
                return slot
        return None

    def approve(self, entry_id: str) -> None:
        self.approved.add(entry_id)

    def reject(self, entry_id: str, reason: str) -> dict | None:
        """Reject a piece. Returns the replacement entry or None.

        For "unnecessary" the piece is simply removed and the slot left empty.
        """
        slot = self.slot_of(entry_id)
        if slot is None:
            return None
        entry = self.wardrobe[entry_id]
        self.proposal[slot].remove(entry_id)
        self.approved.discard(entry_id)
        self.excluded_entries.add(entry_id)
        if reason == "unnecessary":
            if not self.proposal[slot]:
                del self.proposal[slot]
                self.skipped_slots.add(slot)
            return None
        weights = self.slot_weights.setdefault(slot, {})
        if reason == "clash":
            self.slot_avoid_palettes.setdefault(slot, set()).update(entry["palettes"])
            weights["clash"] = weights.get("clash", 1.0) * 2
        elif reason == "overlap":
            self.slot_excluded_categories.setdefault(slot, set()).add(entry["category"])
        elif reason in ("weather", "activity", "formality"):
            weights[reason] = weights.get(reason, 1.0) * 3
            self.excluded_items.add(entry["item_id"])
        elif reason == "style":
            self.excluded_items.add(entry["item_id"])
        cands = self.candidates(slot)
        if reason == "overlap" and not cands:
            # nothing of a different category - fall back to any other piece
            self.slot_excluded_categories[slot].discard(entry["category"])
            self.excluded_items.add(entry["item_id"])
            cands = self.candidates(slot)
        if not cands:
            if not self.proposal.get(slot):
                self.proposal.pop(slot, None)
            return None
        new = cands[0][1]
        self.proposal.setdefault(slot, []).append(new["id"])
        return new

    def pending(self) -> list[str]:
        return [e for e in self.in_use() if e not in self.approved]

    def all_approved(self) -> bool:
        return bool(self.in_use()) and not self.pending()

    def finalize(self) -> dict:
        """Save the approved outfit, move its pieces from dresser to hamper."""
        data = self.character.data
        ids = [e for slot in SLOTS for e in self.proposal.get(slot, [])]
        for e in ids:
            if e in data["dresser"]:
                data["dresser"].remove(e)
            if e not in data["hamper"]:
                data["hamper"].append(e)
        outfit = {
            "date": time.strftime("%Y-%m-%d %H:%M"), "context": self.context.to_dict(),
            "pieces": [{"slot": self.slot_of(e), "entry_id": e,
                        "name": self.wardrobe[e]["item_name"],
                        "palettes": self.wardrobe[e]["palette_names"],
                        "file": self.wardrobe[e]["file"]} for e in ids],
        }
        preview = self.render_preview(ids)
        if preview:
            outfit["preview"] = preview
        data["current_outfit"] = outfit
        data["outfit_history"].append(outfit)
        self.character.save()
        return outfit

    def render_preview(self, ids: list[str]) -> str | None:
        """Write a contact sheet of the outfit into the character's Outfits folder."""
        if not ids:
            return None
        cell = 220
        cols = min(4, len(ids))
        rows = (len(ids) + cols - 1) // cols
        sheet = Image.new("RGBA", (cols * cell, rows * cell), (255, 255, 255, 255))
        for i, eid in enumerate(ids):
            try:
                with Image.open(self.character.entry_path(self.wardrobe[eid])) as im:
                    im = im.convert("RGBA")
                    im.thumbnail((cell - 10, cell - 10))
                    x = (i % cols) * cell + (cell - im.width) // 2
                    y = (i // cols) * cell + (cell - im.height) // 2
                    sheet.alpha_composite(im, (x, y))
            except OSError:
                continue
        folder = self.character.dir / "Outfits"
        folder.mkdir(exist_ok=True)
        path = unique_path(folder / f"Outfit-{time.strftime('%Y-%m-%d')}.png")
        sheet.save(path)
        return path.relative_to(self.character.dir).as_posix()


def do_laundry(character: Character) -> int:
    """Return every item from the hamper to the dresser. Returns how many moved."""
    data = character.data
    moved = 0
    for e in list(data["hamper"]):
        if e not in data["dresser"]:
            data["dresser"].append(e)
        moved += 1
    data["hamper"] = []
    character.save()
    return moved


def outfit_path(character: Character, rel: str) -> Path:
    return character.dir / rel
