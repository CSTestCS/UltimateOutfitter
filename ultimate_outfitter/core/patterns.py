"""Pattern (print) metadata: questionnaire, suitability and loading for auto generation."""
from __future__ import annotations

from typing import Any

import numpy as np

from .categories import FORMALITY, O, Q, SETTING, Question
from .imaging import load_rgba
from .traits import add_into, cosine, normalize

# garment groups a pattern can be used on, keyed by outfit slot
SLOT_GROUPS = {
    "base_top": "Tops", "mid_layer": "Tops", "corset": "Tops",
    "legs": "Bottoms", "legwear": "Legwear & socks", "socks": "Legwear & socks", "leg_warmers": "Legwear & socks",
    "full_body": "Dresses & full-body", "sleepwear": "Sleepwear",
    "outer": "Outerwear", "cape": "Outerwear",
    "underwear_bottom": "Underwear & swimwear", "bra": "Underwear & swimwear",
    "swim_bottom": "Underwear & swimwear", "swim_top": "Underwear & swimwear",
    "swim_full": "Underwear & swimwear",
    "neck": "Accessories", "tie": "Accessories", "head": "Accessories", "bag": "Accessories",
    "hands": "Accessories", "arms": "Accessories", "hair": "Accessories", "waist": "Accessories",
    "apron": "Accessories", "harness": "Accessories", "face": "Accessories", "extras": "Accessories",
    "footwear": "Footwear",
    "wrists": "Jewellery & hard goods", "jewelry": "Jewellery & hard goods",
    "eyes": "Jewellery & hard goods", "armor": "Jewellery & hard goods",
}
GROUPS = ["Tops", "Bottoms", "Dresses & full-body", "Outerwear", "Underwear & swimwear", "Sleepwear",
          "Legwear & socks", "Accessories", "Footwear", "Jewellery & hard goods"]

# how many times the pattern repeats across the width of an item
REPEATS = {"Small / fine": 12, "Medium": 6, "Large / bold motifs": 3, "Single placement print": 1}

PATTERN_QUESTIONS: list[Question] = [
    Q("pattern_kind", "What kind of pattern is it?", [
        O("Florals", "romantic nature_loving cute"),
        O("Stripes", "playful traditional minimalist"),
        O("Plaid / tartan / check", "traditional intellectual rebellious"),
        O("Polka dots", "cute playful cheerful"),
        O("Animal print", "bold glamorous edgy"),
        O("Geometric", "artistic edgy minimalist"),
        O("Abstract / painterly", "artistic:2"),
        O("Camouflage", "tough adventurous practical"),
        O("Damask / brocade / baroque", "regal elegant gothic traditional"),
        O("Paisley / folk / ethnic motifs", "traditional artistic nature_loving"),
        O("Hearts, stars or cute motifs", "cute:2 playful"),
        O("Skulls, bats or dark motifs", "gothic:2 edgy rebellious"),
        O("Lace / mesh / fishnet texture", "romantic flirty gothic"),
        O("Text / logos / graphics", "rebellious playful laid_back"),
        O("Magical / celestial", "magical:2 mysterious"),
        O("Sporty / racing stripes", "sporty:2"),
    ]),
    Q("pattern_boldness", "How bold or loud is it?", [
        O("Subtle / tonal", "minimalist elegant reserved"),
        O("Moderate", "practical"),
        O("Loud / high contrast", "bold:2 playful confident"),
    ]),
    Q("pattern_scale", "How large should it appear on clothing?",
      [O(label, "") for label in REPEATS]),
    FORMALITY,
    SETTING,
    Q("pattern_uses", "Which kinds of items suit this pattern? (choose any)",
      [O(g, "", uses=[g]) for g in GROUPS], multi=True),
    Q("pattern_where", "Where on an item should it go?", [
        O("Main fabric only", "", placement="primary"),
        O("The whole item", "", placement="whole"),
    ]),
]

DEFAULT_USES = ["Tops", "Bottoms", "Dresses & full-body", "Outerwear", "Sleepwear", "Underwear & swimwear",
                "Legwear & socks", "Accessories"]


def evaluate_pattern(answers: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    traits: dict[str, float] = {}
    attrs: dict[str, Any] = {"repeats": 6, "uses": [], "placement": "primary", "formality": 1}
    for q in PATTERN_QUESTIONS:
        ans = answers.get(q.id)
        if ans is None:
            continue
        chosen = ans if isinstance(ans, list) else [ans]
        for opt in q.options:
            if opt.label not in chosen:
                continue
            add_into(traits, opt.traits)
            for k, v in opt.attrs.items():
                if k == "uses":
                    attrs["uses"] += v
                else:
                    attrs[k] = v
            if q.id == "pattern_scale":
                attrs["repeats"] = REPEATS[opt.label]
    if not attrs["uses"]:
        attrs["uses"] = list(DEFAULT_USES)
    return normalize(traits), attrs


def pattern_fits(pattern: dict, item: dict) -> bool:
    """Whether a pattern may be printed on an item at all."""
    item_attrs = item.get("attrs", {})
    if item_attrs.get("print", "primary") == "none":
        return False
    group = SLOT_GROUPS.get(item_attrs.get("slot", ""), "Accessories")
    uses = pattern.get("attrs", {}).get("uses") or DEFAULT_USES
    return group in uses


def pattern_score(pattern: dict, item: dict, character_traits: dict[str, float]) -> float:
    """0-1 suitability of a pattern for an item worn by a character."""
    if not pattern_fits(pattern, item):
        return 0.0
    p_traits = pattern.get("traits", {})
    if not p_traits:
        return 0.35  # unanswered pattern: neutral
    char = cosine(p_traits, character_traits)
    style = cosine(p_traits, item.get("traits", {}))
    formality_gap = abs(pattern.get("attrs", {}).get("formality", 1) - item.get("attrs", {}).get("formality", 1))
    return max(0.0, 0.65 * char + 0.35 * style - 0.08 * formality_gap)


def load_pattern(library, pattern: dict) -> tuple[np.ndarray, np.ndarray | None]:
    """Return (pattern RGBA, cutaway mask RGBA or None) honouring the pattern's cutaway setting."""
    pat = load_rgba(library.abspath(pattern["image"]))
    mode = pattern.get("cutaway", "none")
    cut = None
    if mode == "alpha":
        a = pat[..., 3]
        cut = np.dstack([a, a, a, np.full(a.shape, 255, np.uint8)])
        pat = pat.copy()
        pat[..., 3] = 255
    elif mode == "mask" and pattern.get("cutaway_mask"):
        try:
            cut = load_rgba(library.abspath(pattern["cutaway_mask"]))
        except OSError:
            cut = None
    return pat, cut
