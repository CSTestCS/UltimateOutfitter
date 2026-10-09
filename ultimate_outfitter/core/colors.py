"""Color math: conversions, k-means color extraction, palette matching."""
from __future__ import annotations

import colorsys
from typing import Iterable, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Hex / RGB / HSV helpers
# ---------------------------------------------------------------------------

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) != 6:
        raise ValueError(f"Invalid hex color: {value!r}")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: Sequence[float]) -> str:
    r, g, b = (int(round(max(0, min(255, c)))) for c in rgb[:3])
    return f"#{r:02X}{g:02X}{b:02X}"


def is_valid_hex(value: str) -> bool:
    try:
        hex_to_rgb(value)
        return True
    except ValueError:
        return False


def rgb_to_hsv(rgb: Sequence[int]) -> tuple[float, float, float]:
    """Returns hue in degrees (0-360), saturation and value in 0-100."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb[:3]))
    return h * 360.0, s * 100.0, v * 100.0


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, s / 100.0, v / 100.0)
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


# ---------------------------------------------------------------------------
# Lab conversions (vectorised)
# ---------------------------------------------------------------------------

_M_RGB2XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                       [0.2126729, 0.7151522, 0.0721750],
                       [0.0193339, 0.1191920, 0.9503041]])
_M_XYZ2RGB = np.linalg.inv(_M_RGB2XYZ)
_WHITE = np.array([0.95047, 1.0, 1.08883])


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """rgb: (..., 3) array in 0-255. Returns (..., 3) Lab."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ _M_RGB2XYZ.T / _WHITE
    eps = 216 / 24389
    kappa = 24389 / 27
    f = np.where(xyz > eps, np.cbrt(xyz), (kappa * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    """lab: (..., 3). Returns float (..., 3) RGB in 0-255 (clipped)."""
    lab = np.asarray(lab, dtype=np.float64)
    fy = (lab[..., 0] + 16) / 116
    fx = fy + lab[..., 1] / 500
    fz = fy - lab[..., 2] / 200
    eps = 216 / 24389
    kappa = 24389 / 27
    f = np.stack([fx, fy, fz], axis=-1)
    f3 = f ** 3
    xyz = np.where(f3 > eps, f3, (116 * f - 16) / kappa)
    # L channel uses a slightly different rule
    xyz[..., 1] = np.where(lab[..., 0] > kappa * eps, f3[..., 1], lab[..., 0] / kappa)
    xyz = xyz * _WHITE
    lin = xyz @ _M_XYZ2RGB.T
    lin = np.clip(lin, 0, 1)
    c = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
    return np.clip(c * 255.0, 0, 255)


def delta_e(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIE76 distance; broadcasts."""
    return np.sqrt(((np.asarray(lab1) - np.asarray(lab2)) ** 2).sum(axis=-1))


def luminance(rgb: Sequence[int]) -> float:
    return float(rgb_to_lab(np.array(rgb[:3], dtype=float))[0])


# ---------------------------------------------------------------------------
# K-means colour extraction
# ---------------------------------------------------------------------------

def kmeans(data: np.ndarray, k: int, iterations: int = 20, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Simple k-means with k-means++ init. data: (N, D). Returns (centers, labels)."""
    data = np.asarray(data, dtype=np.float64)
    n = len(data)
    if n == 0:
        return np.zeros((0, data.shape[1] if data.ndim == 2 else 3)), np.zeros(0, dtype=int)
    k = max(1, min(k, n))
    rng = np.random.default_rng(seed)
    centers = [data[rng.integers(n)]]
    d2 = ((data - centers[0]) ** 2).sum(axis=1)
    for _ in range(1, k):
        total = d2.sum()
        if total <= 0:
            break
        idx = rng.choice(n, p=d2 / total)
        centers.append(data[idx])
        d2 = np.minimum(d2, ((data - data[idx]) ** 2).sum(axis=1))
    centers = np.array(centers)
    labels = np.zeros(n, dtype=int)
    for _ in range(iterations):
        dists = ((data[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = dists.argmin(axis=1)
        new_centers = centers.copy()
        for i in range(len(centers)):
            members = data[new_labels == i]
            if len(members):
                new_centers[i] = members.mean(axis=0)
        converged = np.array_equal(new_labels, labels) and np.allclose(new_centers, centers)
        labels, centers = new_labels, new_centers
        if converged:
            break
    return centers, labels


def sample_pixels(rgb: np.ndarray, mask: np.ndarray | None = None, max_samples: int = 20000,
                  seed: int = 0) -> np.ndarray:
    """Return an (N, 3) sample of RGB pixels, optionally restricted to a mask."""
    flat = rgb.reshape(-1, 3)
    if mask is not None:
        flat = flat[mask.reshape(-1)]
    if len(flat) > max_samples:
        rng = np.random.default_rng(seed)
        flat = flat[rng.choice(len(flat), max_samples, replace=False)]
    return flat.astype(np.float64)


def extract_colors(rgb: np.ndarray, k: int, mask: np.ndarray | None = None,
                   min_share: float = 0.0) -> list[tuple[tuple[int, int, int], float]]:
    """Extract up to k dominant colours. Returns [(rgb, share)] sorted by share desc."""
    pixels = sample_pixels(rgb, mask)
    if len(pixels) == 0:
        return []
    lab = rgb_to_lab(pixels)
    centers, labels = kmeans(lab, k)
    counts = np.bincount(labels, minlength=len(centers)).astype(float)
    shares = counts / counts.sum()
    out = []
    for c, s in zip(centers, shares):
        if s <= 0 or s < min_share:
            continue
        r = lab_to_rgb(c)
        out.append((tuple(int(round(v)) for v in r), float(s)))
    out.sort(key=lambda t: -t[1])
    return out


def extract_exact_colors(rgb: np.ndarray, max_colors: int, mask: np.ndarray | None = None,
                         merge_tolerance: float = 0.0, min_share: float = 0.0
                         ) -> list[tuple[tuple[int, int, int], float]]:
    """Extract the actual pixel colours of an image (no averaging).

    Every distinct colour is counted over *all* pixels. Colours closer than
    ``merge_tolerance`` (Delta E) to a more frequent colour are folded into it, so 0 keeps
    every distinct colour exactly. Returns up to ``max_colors`` [(rgb, share)], most
    frequent first. The returned values are always colours that really occur in the image.
    """
    flat = rgb.reshape(-1, 3)
    if mask is not None:
        flat = flat[mask.reshape(-1)]
    if len(flat) == 0:
        return []
    packed = (flat[:, 0].astype(np.int64) << 16) | (flat[:, 1].astype(np.int64) << 8) | flat[:, 2]
    values, counts = np.unique(packed, return_counts=True)
    order = np.argsort(-counts, kind="stable")
    values, counts = values[order], counts[order].astype(float)
    total = counts.sum()
    cols = np.stack([(values >> 16) & 255, (values >> 8) & 255, values & 255], axis=1)
    kept: list[int] = []
    kept_counts: list[float] = []
    if merge_tolerance <= 0:
        kept = list(range(min(len(cols), max_colors)))
        kept_counts = counts[:len(kept)].tolist()
    else:
        # limit the work on photos with huge numbers of colours
        limit = min(len(cols), 20000)
        lab = rgb_to_lab(cols[:limit].astype(float))
        kept_lab = np.zeros((0, 3))
        for i in range(limit):
            if len(kept_lab):
                d = np.sqrt(((kept_lab - lab[i]) ** 2).sum(axis=1))
                j = int(d.argmin())
                if d[j] <= merge_tolerance:
                    kept_counts[j] += counts[i]
                    continue
            if len(kept) >= max_colors:
                continue
            kept.append(i)
            kept_counts.append(counts[i])
            kept_lab = np.vstack([kept_lab, lab[i]])
    out = []
    for i, c in zip(kept, kept_counts):
        share = c / total
        if share >= min_share:
            out.append((tuple(int(v) for v in cols[i]), float(share)))
    out.sort(key=lambda t: -t[1])
    return out


def sort_by_lightness(colors: Iterable[str]) -> list[str]:
    return sorted(colors, key=lambda h: luminance(hex_to_rgb(h)))


# ---------------------------------------------------------------------------
# Palette matching
# ---------------------------------------------------------------------------

def palette_match(palette_hex: Sequence[str], image_colors_lab: np.ndarray,
                  threshold: float) -> tuple[float, float]:
    """How well a palette is represented by image colours.

    Returns (coverage, mean_distance): coverage is the fraction of palette colours whose
    nearest image colour is within ``threshold`` (Delta E); mean_distance is the mean
    nearest distance.
    """
    if not palette_hex or len(image_colors_lab) == 0:
        return 0.0, float("inf")
    pal_lab = rgb_to_lab(np.array([hex_to_rgb(h) for h in palette_hex], dtype=float))
    d = delta_e(pal_lab[:, None, :], image_colors_lab[None, :, :]).min(axis=1)
    return float((d <= threshold).mean()), float(d.mean())


def precision_to_threshold(precision: int) -> float:
    """Map a 0-100 precision slider (100 = exact) to a Delta-E threshold."""
    precision = max(0, min(100, precision))
    # 100 -> 0.5 (exact match), 0 -> 45 (very loose)
    return 0.5 + (45.0 - 0.5) * (1 - precision / 100.0) ** 1.5
