"""Personality traits and helpers for trait vectors.

Both clothing items and characters are described by a ``{trait: weight}`` mapping.
Item traits say which personalities would favour the item; character traits describe
the character. Matching compares the two vectors.
"""
from __future__ import annotations

import math
from typing import Mapping

TRAITS: dict[str, str] = {
    "bold": "Likes to stand out and be noticed",
    "reserved": "Quiet, shy or private; prefers to blend in",
    "elegant": "Refined, graceful, sophisticated",
    "playful": "Fun-loving, whimsical, lighthearted",
    "cute": "Sweet, adorable, soft aesthetic",
    "edgy": "Sharp, alternative, unconventional",
    "rebellious": "Defies rules and expectations",
    "gothic": "Drawn to dark, dramatic and macabre aesthetics",
    "romantic": "Dreamy, affectionate, delicate",
    "flirty": "Alluring, enjoys showing some skin",
    "modest": "Prefers coverage and understatement",
    "sporty": "Athletic, active, energetic",
    "practical": "Values function, comfort and durability",
    "laid_back": "Relaxed, casual, easygoing",
    "cozy": "Loves comfort, warmth and softness",
    "professional": "Polished, businesslike, organised",
    "intellectual": "Studious, thoughtful, bookish",
    "confident": "Self-assured, commanding presence",
    "glamorous": "Luxurious, showy, loves sparkle",
    "regal": "Noble, dignified, aristocratic",
    "mysterious": "Enigmatic, secretive, hard to read",
    "adventurous": "Seeks exploration and the outdoors",
    "tough": "Rugged, fierce, battle-ready",
    "traditional": "Values heritage, classic and cultural styles",
    "artistic": "Creative, expressive, eclectic",
    "minimalist": "Clean lines, simple, uncluttered",
    "nature_loving": "Earthy, organic, connected to nature",
    "cheerful": "Bright, sunny, optimistic",
    "magical": "Fantastical, mystical, otherworldly",
}

TRAIT_LABELS = {k: k.replace("_", " ").title() for k in TRAITS}


def normalize(vec: Mapping[str, float]) -> dict[str, float]:
    """Scale a trait vector so its largest value is 1.0 (drops non-positive values)."""
    positive = {k: float(v) for k, v in vec.items() if v > 0 and k in TRAITS}
    if not positive:
        return {}
    top = max(positive.values())
    return {k: round(v / top, 4) for k, v in positive.items()}


def add_into(target: dict[str, float], source: Mapping[str, float], scale: float = 1.0) -> None:
    for k, v in source.items():
        target[k] = target.get(k, 0.0) + v * scale


def cosine(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def top_traits(vec: Mapping[str, float], n: int = 8) -> list[tuple[str, float]]:
    return sorted(((k, v) for k, v in vec.items() if v > 0), key=lambda t: -t[1])[:n]


def describe(vec: Mapping[str, float], n: int = 8) -> str:
    return ", ".join(f"{TRAIT_LABELS.get(k, k)} ({v:.0%})" for k, v in top_traits(vec, n))
