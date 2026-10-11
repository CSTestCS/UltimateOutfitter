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
from .storage import new_id, unique_path
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

SETTINGS = ["Public", "Private / at home", "Beach / pool"]

# Slots that may be filled by pieces from another slot: underwear and bras can be worn as swimwear.
SLOT_SUBSTITUTES = {"swim_bottom": ["underwear_bottom"], "swim_top": ["bra"]}

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
    setting: str = "Public"
    underwear_only: bool = False     # only honoured in private or beach / pool settings

    def is_underwear_only(self) -> bool:
        return self.underwear_only and self.setting != "Public"

    def target_formality(self) -> float:
        return self.formality if self.formality is not None else ACTIVITY_FORMALITY.get(self.activity, 1)

    def needed_warmth(self) -> int:
        return WEATHER_WARMTH.get(self.weather, 2)

    @classmethod
    def from_dict(cls, d: dict) -> "DayContext":
        return cls(d.get("activity") or "Casual / errands", d.get("mood") or "Calm", d.get("weather") or "Mild",
                   d.get("formality"), d.get("notes", ""), d.get("setting") or "Public",
                   bool(d.get("underwear_only")))

    def to_dict(self) -> dict[str, Any]:
        return {"activity": self.activity, "mood": self.mood, "weather": self.weather,
                "formality": self.formality, "notes": self.notes, "setting": self.setting,
                "underwear_only": self.is_underwear_only()}


class NoOutfitPossible(Exception):
    """``missing`` are readable names; ``shop_slots`` the slots the character owns nothing for."""
    """Raised when required pieces are all in the hamper (laundry needed)."""

    def __init__(self, missing: list[str], laundry_helps: bool, shop_slots: list[str] | None = None):
        self.missing = missing
        self.laundry_helps = laundry_helps
        self.shop_slots = shop_slots or []
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
    shop_slots: list[str] = field(default_factory=list)   # essential slots the wardrobe has nothing for
    core_groups: list[list[str]] = field(default_factory=list)   # alternatives: dress OR top + bottoms...
    seed: int = field(default_factory=lambda: random.randrange(1 << 30))

    # ------------------------------------------------------------------ data
    @property
    def wardrobe(self) -> dict[str, dict]:
        return self.character.data["wardrobe"]

    def dresser_entries(self) -> list[dict]:
        return [self.wardrobe[e] for e in self.character.data["dresser"] if e in self.wardrobe]

    def owned_slots(self) -> set[str]:
        owned = {e["slot"] for e in self.wardrobe.values()}
        return owned | {s for s in SLOT_SUBSTITUTES if any(self.slot_accepts(s, o) for o in owned)}

    def slot_accepts(self, slot: str, entry_slot: str) -> bool:
        """Whether a piece made for ``entry_slot`` may be worn in ``slot``."""
        if entry_slot == slot:
            return True
        if entry_slot in SLOT_SUBSTITUTES.get(slot, []):
            return self.character.data.get("prefs", {}).get("underwear_as_swimwear", True)
        return False

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
        if entry["slot"] != slot:
            s -= 8  # real swimwear is preferred over underwear standing in for it
        rng = random.Random(f"{self.seed}-{entry['id']}")
        s += rng.uniform(0, 6)
        return s

    def candidates(self, slot: str, extra_exclude: set[str] | None = None) -> list[tuple[float, dict]]:
        used = self.in_use()
        used_items = {self.wardrobe[e]["item_id"] for e in used}
        bad_cats = self.slot_excluded_categories.get(slot, set())
        out = []
        for e in self.dresser_entries():
            if not self.slot_accepts(slot, e["slot"]) or e["id"] in used or e["id"] in self.excluded_entries:
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
        wears_bra = prefs.get("wears_bra", "Yes")
        if ctx.is_underwear_only():
            required = ["underwear_bottom"]
            if wears_bra == "Yes":
                required.append("bra")
            elif wears_bra == "Sometimes":
                optional.append("bra")
            if ctx.setting == "Beach / pool":
                optional += ["footwear", "head", "eyes", "jewelry", "hair"]
            else:
                optional += ["socks", "jewelry", "hair"]
            return required, optional, []
        if ctx.activity == "Sleeping":
            required = ["underwear_bottom"]
            core = [["sleepwear"], ["base_top", "legs"], ["full_body"]]
            return required, optional, core
        if ctx.activity == "Swimming / beach":
            core = [["swim_full"], ["swim_top", "swim_bottom"]]
            optional = ["footwear", "head", "eyes", "jewelry", "hair", "bag"]
            return required, optional, core
        required.append("underwear_bottom")
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

    def build(self, allow_incomplete: bool = False) -> dict[str, list[str]]:
        """Create an outfit proposal.

        Pieces that are missing because they are in the hamper raise NoOutfitPossible
        (laundry would help) unless ``allow_incomplete`` is set. Pieces the character
        simply doesn't own are skipped: the outfit is put together from whatever is
        available and the gaps are listed in ``warnings``. NoOutfitPossible is also raised
        when nothing at all can be worn.
        """
        self.proposal = {}
        self.warnings = []
        required, optional, core_groups = self._slot_plan()
        self.core_groups = core_groups
        owned = self.owned_slots()
        in_hamper: list[str] = []      # missing, but laundry would bring it back
        not_owned: list[str] = []      # missing, and laundry would not help

        def available(slot):
            return any(self.slot_accepts(slot, e["slot"]) for e in self.dresser_entries())

        self.shop_slots = []

        def note_missing(slot):
            (in_hamper if slot in owned else not_owned).append(SLOTS[slot])
            if slot not in owned:
                self.shop_slots.append(slot)

        # core garments: prefer a complete alternative with the best average top score;
        # otherwise fall back to the alternative that can be filled the most
        best_group, best_key = None, None
        for group in core_groups:
            avail = [s for s in group if available(s)]
            if not avail:
                continue
            score = sum(self.candidates(s)[0][0] for s in avail if self.candidates(s)) / len(avail)
            key = (len(avail) == len(group), len(avail) / len(group), score)
            if best_key is None or key > best_key:
                best_group, best_key = group, key
        if core_groups and best_group is None:
            # nothing from any alternative is in the dresser
            fixable = any(all(s in owned for s in g) for g in core_groups)
            label = " / ".join("+".join(SLOTS[s] for s in g) for g in core_groups)
            (in_hamper if fixable else not_owned).append(label)
            if not fixable:   # shop for the alternative that needs the fewest new pieces
                group = min(core_groups, key=lambda g: sum(s not in owned for s in g))
                self.shop_slots += [s for s in group if s not in owned]
        elif best_group:
            for slot in best_group:
                if not self._fill_slot(slot):
                    note_missing(slot)

        for slot in required:
            if slot in self.skipped_slots:
                continue
            if not self._fill_slot(slot):
                note_missing(slot)
        if in_hamper and not allow_incomplete:
            raise NoOutfitPossible(in_hamper + not_owned, True, self.shop_slots)
        missing = in_hamper + not_owned
        self._missing = (in_hamper, not_owned)
        self._update_warnings()

        acc_level = self.character.data.get("prefs", {}).get("accessory_level", 3)
        self._fill_optional(optional, acc_level, relaxed=False)
        if not self.proposal:
            # nothing essential could be found: take the best of whatever optional pieces exist
            self._fill_optional(optional, acc_level, relaxed=True)
        if not self.proposal:
            raise NoOutfitPossible(missing or ["everything"], bool(in_hamper), self.shop_slots)
        return self.proposal

    # ---------------------------------------------------------- core alternatives
    def core_group_of(self, slot: str) -> list[str] | None:
        return next((g for g in self.core_groups if slot in g), None)

    def _drop_group(self, group: list[str], keep: str | None = None) -> None:
        for sl in group:
            if sl == keep:
                continue
            for e in self.proposal.pop(sl, []):
                self.approved.discard(e)

    def _consider_legwear(self) -> None:
        """After switching between a dress and a top + bottoms, tights / stockings are worth a look."""
        if "legwear" in self.proposal or "legwear" in self.skipped_slots or self.context.is_underwear_only():
            return
        cands = self.candidates("legwear")
        if cands and cands[0][0] >= 15:
            self.proposal["legwear"] = [cands[0][1]["id"]]

    def switch_core(self, slot: str) -> dict | None:
        """Nothing is left for ``slot``: wear another core alternative (top + bottoms instead of a dress,
        a dress instead of a top + bottoms...). Returns the first new piece, or None if none can be made."""
        current = self.core_group_of(slot)
        if not current:
            return None
        for group in self.core_groups:
            if group is current or not all(self.candidates(sl) for sl in group):
                continue
            self._drop_group(current)
            for sl in group:
                self._fill_slot(sl)
            self._consider_legwear()
            names = "+".join(SLOTS[sl] for sl in group)
            self.warnings.append(f"Nothing else suitable for {SLOTS[slot]} - trying {names} instead.")
            return self.wardrobe[self.proposal[group[0]][0]]
        return None

    def shop_targets(self, slot: str) -> list[str]:
        """Slots a shop visit for ``slot`` may fill: the slot and the other core alternatives' slots."""
        targets = [slot]
        current = self.core_group_of(slot)
        if current:
            for group in self.core_groups:
                if group is not current:
                    targets += [sl for sl in group if sl not in targets and not self.proposal.get(sl)]
        return targets

    def _update_warnings(self) -> None:
        in_hamper, not_owned = getattr(self, "_missing", ([], []))
        missing = in_hamper + not_owned
        self.warnings = [w for w in self.warnings if not w.startswith("Incomplete outfit")]
        if missing:
            self.warnings.append("Incomplete outfit - nothing suitable for: " + ", ".join(missing) + ".")

    def add_bought(self, slot: str, entry_id: str) -> None:
        """Wear a piece just bought in the shop for ``slot`` (it may belong to another core alternative:
        a top bought instead of a dress replaces the dress pieces and fills the rest from the dresser)."""
        entry = self.wardrobe.get(entry_id, {})
        real = next((t for t in self.shop_targets(slot) if self.slot_accepts(t, entry.get("slot", slot))), slot)
        old_group, new_group = self.core_group_of(slot), self.core_group_of(real)
        if real != slot and old_group and new_group and new_group is not old_group:
            self._drop_group(old_group)
            if slot in self.shop_slots:
                self.shop_slots.remove(slot)
            for sl in new_group:
                if sl != real and not self.proposal.get(sl) and not self._fill_slot(sl) and sl not in self.shop_slots:
                    self.shop_slots.append(sl)
            self._consider_legwear()
            slot = real
        self.proposal.setdefault(slot, []).append(entry_id)
        self.skipped_slots.discard(slot)
        if slot in self.shop_slots:
            self.shop_slots.remove(slot)
        in_hamper, not_owned = getattr(self, "_missing", ([], []))
        not_owned = [m for m in not_owned if m != SLOTS.get(slot)]
        if not self.shop_slots:
            not_owned = []
        self._missing = (in_hamper, not_owned)
        self._update_warnings()

    def _fill_optional(self, optional: list[str], acc_level: int, relaxed: bool) -> None:
        accessories_added = sum(len(ids) for sl, ids in self.proposal.items() if sl in ACCESSORY_SLOTS)
        for slot in optional:
            if slot in self.skipped_slots or slot in self.proposal:
                continue
            is_acc = slot in ACCESSORY_SLOTS
            if is_acc and accessories_added >= acc_level:
                continue
            cands = self.candidates(slot)
            if not cands:
                continue
            threshold = -1e9 if relaxed else 30 if not is_acc else 35 + 4 * (3 - acc_level)
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
            # e.g. every dress was rejected: try a top + bottoms instead (and the other way round)
            return self.switch_core(slot)
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
            "id": new_id(), "date": time.strftime("%Y-%m-%d %H:%M"), "context": self.context.to_dict(),
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
        data.pop("shown_outfit", None)     # the Interact tab follows the new day
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


# ---------------------------------------------------------------------------
# Shop: random new pieces for a slot the wardrobe can't fill
# ---------------------------------------------------------------------------

def shop_offer(session: "OutfitSession", slot: str, rng: random.Random | None = None) -> dict | None:
    """A random new piece for ``slot`` that suits the day (not the character's wardrobe rules).

    Returns a build-plan piece {"item", "palettes", "pattern", "score", "slot"} for
    :meth:`Character.build_wardrobe`, or None if the library has no item for the slot.
    Any library palette may be used (except ones rejected for clashing in this slot), and
    sometimes a fitting pattern.
    """
    from .patterns import pattern_fits
    rng = rng or random.Random()
    lib = session.character.library
    avoid = session.slot_avoid_palettes.get(slot, set())
    targets = session.shop_targets(slot)    # a dress may be replaced by a top (+ bottoms) and vice versa

    def target_of(cat):
        return next((t for t in targets if session.slot_accepts(t, cat.slot)), None)

    items = []
    for item in lib.items.values():
        cat = CATEGORY_BY_NAME.get(item["category"])
        target = target_of(cat) if cat else None
        if not target:
            continue
        if item["id"] in session.excluded_items or item["category"] in session.slot_excluded_categories.get(target, set()):
            continue
        items.append((item, cat))
    if not items:   # rejected everything - ignore the rejections rather than offer nothing
        items = [(i, CATEGORY_BY_NAME[i["category"]]) for i in lib.items.values()
                 if i["category"] in CATEGORY_BY_NAME and target_of(CATEGORY_BY_NAME[i["category"]])]
    palettes = [p for p in lib.palettes.values() if p["id"] not in avoid] or list(lib.palettes.values())
    if not items or not palettes:
        return None
    # how well each item suits the day: activity, warmth, formality (no personality involved)
    scored = []
    for item, cat in items:
        fake = {"id": f"shop-{item['id']}", "item_id": item["id"], "category": item["category"],
                "palettes": [], "slot": cat.slot, "rating": 50}
        scored.append((session.score(fake, target_of(cat)), item, cat))
    best = max(sc for sc, _, _ in scored)
    suitable = [(item, cat) for sc, item, cat in scored if sc >= best - 20]
    item, cat = rng.choice(suitable)
    n = 1 + (rng.random() < 0.3) + (rng.random() < 0.08)
    combo = rng.sample(palettes, min(n, len(palettes)))
    pattern = None
    fitting = [p for p in lib.patterns.values() if pattern_fits(p, item)]
    if fitting and rng.random() < 0.3:
        pattern = rng.choice(fitting)
    return {"item": item, "palettes": combo, "pattern": pattern, "score": 50, "slot": target_of(cat)}


def buy(character: Character, offer: dict) -> dict | None:
    """Create the offered piece and put it in the dresser. Returns the new wardrobe entry."""
    created = character.build_wardrobe(item_ids=[], plan=[offer])
    if not created:
        return None
    entry = created[0]
    entry["bought"] = time.strftime("%Y-%m-%d %H:%M")
    character.save()
    return entry


def outfit_piece(entry: dict) -> dict:
    return {"slot": entry["slot"], "entry_id": entry["id"], "name": entry["item_name"],
            "palettes": entry["palette_names"], "file": entry["file"]}


def edit_outfit(character: Character, outfit: dict, remove: list[str] = (), add: list[str] = (),
                reason: str = "edited") -> dict:
    """Change the pieces of a saved outfit.

    Removed pieces stay where they are (a worn piece stays in the hamper - editing never returns
    anything to the dresser). Added pieces must be clean: they move from the dresser to the hamper.
    ``remove`` + ``add`` together replace a piece. Removed pieces are listed in ``outfit["removed"]``
    (so the 3D preview can hide them on the model).
    """
    data = character.data
    wardrobe = data["wardrobe"]
    gone = set(remove)
    removed = [r for r in outfit.get("removed", []) if r.get("entry_id") not in set(add)]
    for p in outfit.get("pieces", []):
        if p.get("entry_id") in gone and all(r.get("entry_id") != p.get("entry_id") for r in removed):
            removed.append(dict(p, reason=reason, time=time.strftime("%Y-%m-%d %H:%M")))
    outfit["removed"] = removed
    pieces = [p for p in outfit.get("pieces", []) if p.get("entry_id") not in gone]
    have = {p.get("entry_id") for p in pieces}
    for eid in add:
        e = wardrobe.get(eid)
        if not e or eid in have:
            continue
        if eid in data["dresser"]:
            data["dresser"].remove(eid)
        if eid not in data["hamper"]:
            data["hamper"].append(eid)
        pieces.append(outfit_piece(e))
        have.add(eid)
    order = {s: i for i, s in enumerate(SLOTS)}
    pieces.sort(key=lambda p: order.get(p.get("slot"), len(order)))
    outfit["pieces"] = pieces
    outfit["edited"] = time.strftime("%Y-%m-%d %H:%M")
    session = OutfitSession(character, DayContext.from_dict(outfit.get("context", {})))
    preview = session.render_preview([p["entry_id"] for p in pieces if p["entry_id"] in wardrobe])
    if preview:
        outfit["preview"] = preview
    else:
        outfit.pop("preview", None)
    character.save()
    return outfit


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
