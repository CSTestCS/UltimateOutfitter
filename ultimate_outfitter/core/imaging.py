"""Pixel-level operations: selections, recolouring and pattern application.

Images are handled as float/uint8 numpy arrays of shape (H, W, 4) RGBA.
Selections are boolean arrays of shape (H, W).
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image

from .colors import hex_to_rgb, kmeans, lab_to_rgb, rgb_to_lab

# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def load_rgba(path: Path | str) -> np.ndarray:
    with Image.open(path) as im:
        return np.array(im.convert("RGBA"), dtype=np.uint8)


def save_rgba(arr: np.ndarray, path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    if path.suffix.lower() in (".jpg", ".jpeg", ".bmp"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        bg.save(path)
    else:
        img.save(path)


# ---------------------------------------------------------------------------
# Connected components (run-length union-find, no scipy needed)
# ---------------------------------------------------------------------------


def _row_runs(row: np.ndarray) -> list[tuple[int, int]]:
    padded = np.concatenate(([False], row, [False]))
    diff = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(diff == 1)
    ends = np.flatnonzero(diff == -1) - 1
    return list(zip(starts.tolist(), ends.tolist()))


def connected_region(mask: np.ndarray, seed: tuple[int, int], diagonal: bool = False) -> np.ndarray:
    """Return the connected component of ``mask`` containing ``seed`` (x, y)."""
    h, w = mask.shape
    x0, y0 = seed
    out = np.zeros_like(mask, dtype=bool)
    if not (0 <= x0 < w and 0 <= y0 < h) or not mask[y0, x0]:
        return out
    runs = [_row_runs(mask[y]) for y in range(h)]
    visited = [np.zeros(len(r), dtype=bool) for r in runs]
    # find seed run
    stack = []
    for i, (s, e) in enumerate(runs[y0]):
        if s <= x0 <= e:
            stack.append((y0, i))
            visited[y0][i] = True
            break
    slack = 1 if diagonal else 0
    while stack:
        y, i = stack.pop()
        s, e = runs[y][i]
        out[y, s:e + 1] = True
        for ny in (y - 1, y + 1):
            if 0 <= ny < h:
                for j, (s2, e2) in enumerate(runs[ny]):
                    if e2 < s - slack:
                        continue
                    if s2 > e + slack:
                        break
                    if not visited[ny][j]:
                        visited[ny][j] = True
                        stack.append((ny, j))
    return out


# ---------------------------------------------------------------------------
# Selection tools
# ---------------------------------------------------------------------------


def color_distance_map(img: np.ndarray, rgb: Sequence[int]) -> np.ndarray:
    """Perceptual (Lab) distance of every pixel to ``rgb``."""
    lab = rgb_to_lab(img[..., :3].astype(float))
    target = rgb_to_lab(np.array(rgb[:3], dtype=float))
    return np.sqrt(((lab - target) ** 2).sum(axis=-1))


def select_color(img: np.ndarray, point: tuple[int, int], tolerance: float,
                 contiguous: bool, ignore_transparent: bool = True) -> np.ndarray:
    """Select pixels similar to the colour at ``point``; optionally only connected ones."""
    x, y = point
    rgb = img[y, x, :3]
    mask = color_distance_map(img, rgb) <= tolerance
    if ignore_transparent:
        mask &= img[..., 3] > 0
    if contiguous:
        mask = connected_region(mask, (x, y))
    return mask


def hue_map(img: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorised HSV: returns hue (deg), saturation (0-1), value (0-1)."""
    rgb = img[..., :3].astype(float) / 255.0
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    d = mx - mn
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.zeros_like(mx)
    nz = d > 1e-9
    rm = nz & (mx == r)
    gm = nz & (mx == g) & ~rm
    bm = nz & ~rm & ~gm
    h[rm] = ((g - b)[rm] / d[rm]) % 6
    h[gm] = ((b - r)[gm] / d[gm]) + 2
    h[bm] = ((r - g)[bm] / d[bm]) + 4
    h = h * 60.0
    s = np.where(mx > 0, d / np.maximum(mx, 1e-9), 0)
    return h, s, mx


def select_hue(img: np.ndarray, point: tuple[int, int], hue_tolerance: float,
               min_saturation: float = 0.08, contiguous: bool = False) -> np.ndarray:
    """Select all pixels whose hue is within ``hue_tolerance`` degrees of the clicked hue.

    Greys (saturation below ``min_saturation``) are only selected when the clicked pixel is
    itself grey, in which case all greys are selected.
    """
    x, y = point
    h, s, _ = hue_map(img)
    opaque = img[..., 3] > 0
    if s[y, x] < min_saturation:
        mask = (s < min_saturation) & opaque
    else:
        diff = np.abs(h - h[y, x])
        diff = np.minimum(diff, 360 - diff)
        mask = (diff <= hue_tolerance) & (s >= min_saturation) & opaque
    if contiguous:
        mask = connected_region(mask, (x, y))
    return mask


def foreground_mask(img: np.ndarray, tolerance: float = 12.0) -> np.ndarray:
    """Guess which pixels belong to the subject.

    Uses the alpha channel when the image has transparency; otherwise flood-fills the
    background from the image border using the dominant border colour.
    """
    alpha = img[..., 3]
    if (alpha < 250).mean() > 0.01:
        return alpha >= MIN_AUTO_ALPHA
    h, w = alpha.shape
    border = np.concatenate([img[0, :, :3], img[-1, :, :3], img[:, 0, :3], img[:, -1, :3]])
    # dominant border colour
    q = (border // 8).astype(int)
    keys = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    vals, counts = np.unique(keys, return_counts=True)
    top = vals[counts.argmax()]
    bg_rgb = border[keys == top].mean(axis=0)
    if counts.max() < len(border) * 0.3:
        return np.ones((h, w), dtype=bool)  # busy border: no clear background
    similar = color_distance_map(img, bg_rgb) <= tolerance
    bg = np.zeros((h, w), dtype=bool)
    # flood from every border pixel that is similar
    seeds_mask = np.zeros((h, w), dtype=bool)
    seeds_mask[0, :] = seeds_mask[-1, :] = True
    seeds_mask[:, 0] = seeds_mask[:, -1] = True
    seeds = np.argwhere(seeds_mask & similar)
    for y, x in seeds:
        if not bg[y, x]:
            bg |= connected_region(similar, (int(x), int(y)))
    fg = ~bg
    if fg.mean() < 0.01:
        return np.ones((h, w), dtype=bool)
    return fg


# ---------------------------------------------------------------------------
# Recolouring
# ---------------------------------------------------------------------------


def _palette_lab(palette: Sequence[str]) -> np.ndarray:
    lab = rgb_to_lab(np.array([hex_to_rgb(c) for c in palette], dtype=float))
    return lab[np.argsort(lab[:, 0])]


def gradient_map(img: np.ndarray, mask: np.ndarray, palette: Sequence[str]) -> np.ndarray:
    """Map lightness inside the mask onto the palette (sorted dark -> light)."""
    out = img.copy()
    if not mask.any() or not palette:
        return out
    lab = rgb_to_lab(img[..., :3][mask].astype(float))
    L = lab[:, 0]
    lo, hi = np.percentile(L, 1), np.percentile(L, 99)
    t = np.clip((L - lo) / max(hi - lo, 1e-6), 0, 1)
    pal = _palette_lab(palette)
    if len(pal) == 1:
        target = np.repeat(pal, len(t), axis=0)
        target[:, 0] = np.clip(pal[0, 0] + (L - L.mean()), 0, 100)
    else:
        pos = t * (len(pal) - 1)
        i0 = np.floor(pos).astype(int).clip(0, len(pal) - 2)
        f = (pos - i0)[:, None]
        target = pal[i0] * (1 - f) + pal[i0 + 1] * f
    out[..., :3][mask] = lab_to_rgb(target).round().astype(np.uint8)
    return out


def tint(img: np.ndarray, mask: np.ndarray, color: str, keep_shading: bool = True) -> np.ndarray:
    """Recolour the selection to a single colour, preserving relative shading."""
    out = img.copy()
    if not mask.any():
        return out
    lab = rgb_to_lab(img[..., :3][mask].astype(float))
    target = rgb_to_lab(np.array(hex_to_rgb(color), dtype=float))
    new = np.empty_like(lab)
    new[:, 1] = target[1]
    new[:, 2] = target[2]
    if keep_shading:
        new[:, 0] = np.clip(target[0] + (lab[:, 0] - np.median(lab[:, 0])), 0, 100)
    else:
        new[:, 0] = target[0]
    out[..., :3][mask] = lab_to_rgb(new).round().astype(np.uint8)
    return out


MIN_AUTO_ALPHA = 26  # 10% opacity: fainter pixels (cleanup dregs) are never auto-coloured


def auto_mask(img: np.ndarray) -> np.ndarray:
    """Pixels that automatic colouring may touch: the subject, at least 10% opaque."""
    return foreground_mask(img) & (img[..., 3] >= MIN_AUTO_ALPHA)


def color_regions(img: np.ndarray, mask: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cluster the masked pixels into ``k`` colour regions.

    Returns (labels (H,W) with -1 outside mask, centres Lab (k,3), pixel share per region).
    """
    labels, centers, share = color_regions_multi([img], [mask], k)
    return labels[0], centers, share


def color_regions_multi(imgs: Sequence[np.ndarray], masks: Sequence[np.ndarray], k: int
                        ) -> tuple[list[np.ndarray], np.ndarray, np.ndarray]:
    """Cluster the masked pixels of several images into ``k`` shared colour regions.

    All images of one clothing item are clustered together, so the same material gets
    the same region (and therefore the same new colour) in every image.
    Clustering is done on a chromatic-heavy Lab space so shading of a single material
    tends to stay in one region.
    """
    labs = [rgb_to_lab(im[..., :3][m].astype(float)) if m.any() else np.zeros((0, 3))
            for im, m in zip(imgs, masks)]
    labels = [np.full(m.shape, -1, dtype=int) for m in masks]
    pooled = np.concatenate(labs) if labs else np.zeros((0, 3))
    if len(pooled) == 0:
        return labels, np.zeros((0, 3)), np.zeros(0)
    weight = np.array([0.5, 1.0, 1.0])  # de-emphasise lightness
    feats = pooled * weight
    n = len(feats)
    rng = np.random.default_rng(0)
    sample = feats if n <= 15000 else feats[rng.choice(n, 15000, replace=False)]
    centers, _ = kmeans(sample, k)
    assign = np.empty(n, dtype=int)
    for s0 in range(0, n, 200000):
        chunk = feats[s0:s0 + 200000]
        assign[s0:s0 + 200000] = ((chunk[:, None, :] - centers[None]) ** 2).sum(-1).argmin(1)
    pos = 0
    for lab_i, lbl, m in zip(labs, labels, masks):
        lbl[m] = assign[pos:pos + len(lab_i)]
        pos += len(lab_i)
    real_centers = np.array([pooled[assign == i].mean(axis=0) if (assign == i).any() else
                             centers[i] / weight for i in range(len(centers))])
    share = np.bincount(assign, minlength=len(centers)) / n
    return labels, real_centers, share


def _distribute(order: np.ndarray, n_pal: int) -> list[list[int]]:
    """Split regions (sorted by area) between palettes; the first palette gets the most."""
    if n_pal == 1:
        return [list(order)]
    n_regions = len(order)
    weights = {2: [0.6, 0.4], 3: [0.5, 0.3, 0.2]}.get(n_pal, [1 / n_pal] * n_pal)
    groups: list[list[int]] = [[] for _ in range(n_pal)]
    counts = [max(1, int(round(w * n_regions))) for w in weights]
    idx = 0
    for g, c in enumerate(counts):
        take = order[idx:idx + c] if g < n_pal - 1 else order[idx:]
        groups[g].extend(int(t) for t in take)
        idx += c
    for g in range(n_pal):  # make sure every palette gets at least one region
        if not groups[g]:
            donor = max(range(n_pal), key=lambda i: len(groups[i]))
            if len(groups[donor]) > 1:
                groups[g].append(groups[donor].pop())
    return groups


def _assign_targets(region_ids: list[int], centers: np.ndarray, share: np.ndarray, pal: np.ndarray,
                    kind: str) -> dict[int, int]:
    """Map each region to a palette index (palette sorted dark -> light)."""
    out: dict[int, int] = {}
    if kind == "shades":
        # the most neutral (middle) shade is the primary colour of the largest region;
        # lighter regions take lighter shades, darker regions darker shades (shading / details)
        neutral = len(pal) // 2
        by_area = sorted(region_ids, key=lambda r: -share[r])
        main = by_area[0]
        out[main] = neutral
        main_l = centers[main][0]
        lighter = sorted([r for r in by_area[1:] if centers[r][0] >= main_l], key=lambda r: centers[r][0])
        darker = sorted([r for r in by_area[1:] if centers[r][0] < main_l], key=lambda r: -centers[r][0])
        for i, r in enumerate(lighter, 1):
            out[r] = min(len(pal) - 1, neutral + i)
        for i, r in enumerate(darker, 1):
            out[r] = max(0, neutral - i)
        return out
    ordered = sorted(region_ids, key=lambda r: centers[r][0])
    for rank, r in enumerate(ordered):
        if len(ordered) == 1:
            out[r] = len(pal) // 2
        else:
            out[r] = int(round(rank * (len(pal) - 1) / (len(ordered) - 1)))
    return out


def recolor_regions_multi(imgs: Sequence[np.ndarray], masks: Sequence[np.ndarray],
                          palettes: Sequence[Sequence[str]], kinds: Sequence[str] | None = None,
                          regions: int | None = None, strength: float = 1.0
                          ) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Recolour one clothing item (one or more images) with one or more palettes.

    The masked area is split into colour regions shared by all images. Regions are ranked
    by area; the largest regions take colours from the first palette, then the second and
    so on. ``kinds`` gives each palette's type: for "varied" palettes regions are matched
    to colours by lightness; for "shades" palettes the most neutral shade is the primary
    colour and lighter / darker shades are used for highlights, shading and details.
    Each pixel's offset from its region centre is kept, preserving folds and texture.

    Returns (recoloured images, primary masks) - the primary mask marks the largest
    region of the first palette in each image (used for prints / patterns).
    """
    outs = [im.copy() for im in imgs]
    primaries = [np.zeros(m.shape, dtype=bool) for m in masks]
    palettes = [list(p) for p in palettes if p]
    kinds = list(kinds or [])
    kinds += ["varied"] * (len(palettes) - len(kinds))
    if not palettes or not any(m.any() for m in masks):
        return outs, primaries
    total_colors = sum(len(p) for p in palettes)
    k = regions or max(len(palettes), min(8, total_colors))
    labels, centers, share = color_regions_multi(imgs, masks, k)
    order = np.argsort(-share)
    groups = _distribute(order, len(palettes))
    targets: dict[int, tuple[int, int]] = {}   # region -> (palette idx, colour idx)
    pals = [_palette_lab(p) for p in palettes]
    for g, region_ids in enumerate(groups):
        if region_ids:
            for r, ci in _assign_targets(region_ids, centers, share, pals[g], kinds[g]).items():
                targets[r] = (g, ci)
    primary_region = max(groups[0], key=lambda r: share[r]) if groups[0] else int(order[0])
    for img, mask, lbl, out, prim in zip(imgs, masks, labels, outs, primaries):
        if not mask.any():
            continue
        prim |= lbl == primary_region
        lab_all = rgb_to_lab(img[..., :3][mask].astype(float))
        lab_labels = lbl[mask]
        new_lab = lab_all.copy()
        for r, (g, ci) in targets.items():
            sel = lab_labels == r
            if not sel.any():
                continue
            pal = pals[g]
            target = pal[ci]
            src = lab_all[sel]
            centre = centers[r]
            recol = np.empty_like(src)
            recol[:, 0] = np.clip(target[0] + (src[:, 0] - centre[0]), 0, 100)
            if kinds[g] == "shades" and len(pal) > 1:
                # shadows / highlights pick up the hue of the neighbouring shades
                L = recol[:, 0]
                base_a = np.interp(L, pal[:, 0], pal[:, 1])
                base_b = np.interp(L, pal[:, 0], pal[:, 2])
                recol[:, 1] = base_a + (src[:, 1] - centre[1]) * 0.3
                recol[:, 2] = base_b + (src[:, 2] - centre[2]) * 0.3
            else:
                recol[:, 1] = target[1] + (src[:, 1] - centre[1]) * 0.5
                recol[:, 2] = target[2] + (src[:, 2] - centre[2]) * 0.5
            new_lab[sel] = src * (1 - strength) + recol * strength
        out[..., :3][mask] = lab_to_rgb(new_lab).round().astype(np.uint8)
    return outs, primaries


def recolor_regions(img: np.ndarray, mask: np.ndarray, palettes: Sequence[Sequence[str]],
                    regions: int | None = None, strength: float = 1.0,
                    kinds: Sequence[str] | None = None) -> np.ndarray:
    """Single-image convenience wrapper around :func:`recolor_regions_multi`."""
    outs, _ = recolor_regions_multi([img], [mask], palettes, kinds, regions, strength)
    return outs[0]


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------


def scale_pattern(pattern: np.ndarray, scale: float, antialias: bool) -> np.ndarray:
    h, w = pattern.shape[:2]
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    if (nw, nh) == (w, h):
        return pattern
    resample = Image.LANCZOS if antialias else Image.NEAREST
    if antialias and scale > 1:
        resample = Image.BICUBIC
    im = Image.fromarray(pattern.astype(np.uint8), "RGBA").resize((nw, nh), resample)
    return np.array(im)


def tile_pattern(pattern: np.ndarray, width: int, height: int, offset: tuple[int, int] = (0, 0),
                 tiled: bool = True) -> np.ndarray:
    """Cover a (height, width) canvas with the pattern. If not tiled, place it once."""
    ph, pw = pattern.shape[:2]
    ox, oy = offset
    if tiled:
        ys = (np.arange(height) - oy) % ph
        xs = (np.arange(width) - ox) % pw
        return pattern[ys[:, None], xs[None, :]]
    canvas = np.zeros((height, width, 4), dtype=pattern.dtype)
    x0, y0 = max(ox, 0), max(oy, 0)
    x1, y1 = min(ox + pw, width), min(oy + ph, height)
    if x1 > x0 and y1 > y0:
        canvas[y0:y1, x0:x1] = pattern[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    return canvas


def apply_pattern(img: np.ndarray, mask: np.ndarray, pattern: np.ndarray, *, scale: float = 1.0,
                  antialias: bool = True, tiled: bool = True, offset: tuple[int, int] = (0, 0),
                  palette: Sequence[str] | None = None, blend: str = "shaded",
                  opacity: float = 1.0, cutaway: np.ndarray | None = None,
                  cutaway_threshold: int = 128) -> np.ndarray:
    """Apply ``pattern`` only inside ``mask``.

    blend: "replace" - paste pattern colours; "shaded" - keep the underlying lightness
    variation (folds/shadows) on top of the pattern; "multiply" - multiply blend.
    cutaway: optional RGBA/grey mask tiled exactly like the pattern; where it is dark
    (or transparent) the garment is cut away (made transparent), e.g. lace or mesh holes.
    """
    out = img.copy()
    if not mask.any():
        return out
    h, w = img.shape[:2]
    if cutaway is not None:
        cut = cutaway if cutaway.ndim == 3 else np.dstack([cutaway] * 3 + [np.full(cutaway.shape, 255, np.uint8)])
        if cut.shape[2] == 3:
            cut = np.dstack([cut, np.full(cut.shape[:2], 255, np.uint8)])
        if cut.shape[:2] != pattern.shape[:2]:
            cut = np.array(Image.fromarray(cut.astype(np.uint8), "RGBA").resize(
                (pattern.shape[1], pattern.shape[0]), Image.NEAREST))
        cut = scale_pattern(cut, scale, antialias)
        cut_layer = tile_pattern(cut, w, h, offset, tiled)
        keep = (cut_layer[..., :3].astype(float).mean(axis=-1) * (cut_layer[..., 3] / 255.0)) / 255.0
        if antialias:
            new_alpha = out[..., 3].astype(float) * np.clip(keep, 0, 1)
        else:
            new_alpha = np.where(keep * 255 >= cutaway_threshold, out[..., 3], 0)
        out[..., 3] = np.where(mask, new_alpha, out[..., 3]).round().astype(np.uint8)
    pat = scale_pattern(pattern, scale, antialias)
    if palette:
        full = np.ones(pat.shape[:2], dtype=bool)
        pat = gradient_map(pat, full, palette)
    layer = tile_pattern(pat, w, h, offset, tiled).astype(float)
    base = img[..., :3].astype(float)
    p_rgb = layer[..., :3]
    p_alpha = layer[..., 3] / 255.0
    if blend == "multiply":
        result = base * p_rgb / 255.0
    elif blend == "shaded":
        base_lab = rgb_to_lab(base[mask])
        pat_lab = rgb_to_lab(p_rgb[mask])
        ref = np.median(base_lab[:, 0])
        pat_lab[:, 0] = np.clip(pat_lab[:, 0] + (base_lab[:, 0] - ref), 0, 100)
        result = base.copy()
        result[mask] = lab_to_rgb(pat_lab)
    else:
        result = p_rgb
    a = (p_alpha * opacity)[..., None]
    mixed = base * (1 - a) + result * a
    out[..., :3][mask] = np.clip(mixed[mask], 0, 255).round().astype(np.uint8)
    return out

