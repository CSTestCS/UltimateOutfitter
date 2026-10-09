"""Upscaling for low-resolution / pixelated textures.

Methods
-------
shape      Smooths the *shape* of every colour area and keeps hard edges with no new
           colours (no antialiasing). Each colour is upscaled as a soft mask and every
           output pixel takes the colour with the strongest mask.
shape_aa   Same contour smoothing, but rendered supersampled and downsampled, giving
           antialiased edges.
blend      Smoothed shapes plus in-between colours: every colour transition is blended
           into a short gradient.
scale2x    Classic pixel-art edge-directed scaling (EPX / Scale2x), hard edges.
nearest / bicubic   plain resizes for comparison.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
from PIL import Image

METHODS = {
    "shape": "Smooth shapes - no antialiasing (no new colours)",
    "shape_aa": "Smooth shapes - antialiased",
    "blend": "Smooth shapes + in-between colour gradients",
    "scale2x": "Pixel-art Scale2x / EPX (hard edges)",
    "bicubic": "Plain bicubic resize (reference)",
    "nearest": "Plain nearest-neighbour resize (reference)",
}

Progress = Callable[[float], None] | None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _box_blur_axis(a: np.ndarray, r: int, axis: int) -> np.ndarray:
    if r <= 0:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    p = np.pad(a, pad, mode="edge")
    c = np.cumsum(p, axis=axis, dtype=np.float64)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(a.dtype)


def gaussian_blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Approximate gaussian blur (3 box passes) over the first two axes."""
    if sigma <= 0.3:
        return a
    # box radius for 3 passes approximating sigma
    r = max(1, int(round((np.sqrt(12 * sigma * sigma / 3 + 1) - 1) / 2)))
    out = a.astype(np.float32)
    for _ in range(3):
        out = _box_blur_axis(out, r, 0)
        out = _box_blur_axis(out, r, 1)
    return out


def _quantize(img: np.ndarray, max_colors: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (label image, colour table RGBA) with at most ``max_colors`` colours."""
    flat = img.reshape(-1, 4)
    colors, inverse = np.unique(flat, axis=0, return_inverse=True)
    if len(colors) <= max_colors:
        return inverse.reshape(img.shape[:2]), colors
    pil = Image.fromarray(img, "RGBA")
    q = pil.quantize(colors=max_colors, method=Image.Quantize.FASTOCTREE)
    labels = np.array(q)
    pal = np.array(q.getpalette(rawmode="RGBA")[: 4 * max_colors], dtype=np.uint8).reshape(-1, 4)
    # PIL may not return alpha correctly for every version; recompute colours from data
    table = np.zeros((labels.max() + 1, 4), dtype=np.uint8)
    for i in range(labels.max() + 1):
        sel = labels == i
        table[i] = img[sel].mean(axis=0).round() if sel.any() else pal[min(i, len(pal) - 1)]
    return labels, table


def _resize_f(a: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    return np.array(Image.fromarray(a.astype(np.float32), "F").resize(size, Image.BICUBIC))


# ---------------------------------------------------------------------------
# core algorithms
# ---------------------------------------------------------------------------


def shape_labels(img: np.ndarray, scale: float, smoothness: float = 1.0, max_colors: int = 64,
                 progress: Progress = None) -> tuple[np.ndarray, np.ndarray]:
    """Upscale the label field of ``img`` with smoothed contours.

    Returns (labels at the new size, colour table).
    """
    labels, table = _quantize(img, max_colors)
    h, w = labels.shape
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    best = np.full((nh, nw), -1e9, dtype=np.float32)
    out = np.zeros((nh, nw), dtype=np.int32)
    sigma = smoothness * scale * 0.5
    pad = 2 + int(np.ceil(smoothness))
    n = len(table)
    for i in range(n):
        sel = labels == i
        if not sel.any():
            continue
        ys, xs = np.nonzero(sel)
        y0, y1 = max(0, ys.min() - pad), min(h, ys.max() + pad + 1)
        x0, x1 = max(0, xs.min() - pad), min(w, xs.max() + pad + 1)
        crop = sel[y0:y1, x0:x1].astype(np.float32)
        # target coordinates of this crop in the output
        ty0, ty1 = int(round(y0 * nh / h)), int(round(y1 * nh / h))
        tx0, tx1 = int(round(x0 * nw / w)), int(round(x1 * nw / w))
        if ty1 <= ty0 or tx1 <= tx0:
            continue
        # nearest-upscale then blur gives smooth contours that are rotation-friendly
        up = np.array(Image.fromarray(crop, "F").resize((tx1 - tx0, ty1 - ty0), Image.NEAREST))
        up = gaussian_blur(up, sigma)
        region = best[ty0:ty1, tx0:tx1]
        better = up > region
        region[better] = up[better]
        out[ty0:ty1, tx0:tx1][better] = i
        if progress:
            progress((i + 1) / n)
    return out, table


def upscale_shape(img: np.ndarray, scale: float, smoothness: float = 1.0, max_colors: int = 64,
                  progress: Progress = None) -> np.ndarray:
    labels, table = shape_labels(img, scale, smoothness, max_colors, progress)
    return table[labels]


def upscale_shape_aa(img: np.ndarray, scale: float, smoothness: float = 1.0, max_colors: int = 64,
                     supersample: int = 4, progress: Progress = None) -> np.ndarray:
    h, w = img.shape[:2]
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    # cap supersampled size to keep memory reasonable (~24 MP)
    while supersample > 1 and nw * nh * supersample * supersample > 24_000_000:
        supersample -= 1
    big = upscale_shape(img, scale * supersample, smoothness, max_colors, progress)
    return _downsample_premultiplied(big, (nw, nh))


def _downsample_premultiplied(img: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    f = img.astype(np.float32)
    a = f[..., 3:4] / 255.0
    pre = np.concatenate([f[..., :3] * a, f[..., 3:4]], axis=-1)
    chans = [np.array(Image.fromarray(pre[..., c], "F").resize(size, Image.BOX)) for c in range(4)]
    out = np.stack(chans, axis=-1)
    alpha = out[..., 3:4] / 255.0
    rgb = np.where(alpha > 1e-6, out[..., :3] / np.maximum(alpha, 1e-6), 0)
    return np.clip(np.concatenate([rgb, out[..., 3:4]], axis=-1), 0, 255).round().astype(np.uint8)


def upscale_blend(img: np.ndarray, scale: float, smoothness: float = 1.0, blend_width: float = 1.0,
                  max_colors: int = 64, progress: Progress = None) -> np.ndarray:
    """Smoothed shapes with gradient transitions (in-between colours) at every colour change."""
    sharp = upscale_shape(img, scale, smoothness, max_colors, progress).astype(np.float32)
    sigma = max(0.5, blend_width * scale * 0.45)
    a = sharp[..., 3:4] / 255.0
    pre = np.concatenate([sharp[..., :3] * a, sharp[..., 3:4]], axis=-1)
    blurred = gaussian_blur(pre, sigma)
    alpha = blurred[..., 3:4] / 255.0
    rgb = np.where(alpha > 1e-6, blurred[..., :3] / np.maximum(alpha, 1e-6), 0)
    return np.clip(np.concatenate([rgb, blurred[..., 3:4]], axis=-1), 0, 255).round().astype(np.uint8)


def scale2x(img: np.ndarray) -> np.ndarray:
    """One pass of the Scale2x / EPX algorithm (exact colours, hard edges)."""
    p = np.pad(img, ((1, 1), (1, 1), (0, 0)), mode="edge")
    E = p[1:-1, 1:-1]
    B = p[:-2, 1:-1]
    D = p[1:-1, :-2]
    F = p[1:-1, 2:]
    H = p[2:, 1:-1]

    def eq(x, y):
        return np.all(x == y, axis=-1)

    cond = ~eq(B, H) & ~eq(D, F)
    e0 = np.where((cond & eq(D, B))[..., None], D, E)
    e1 = np.where((cond & eq(B, F))[..., None], F, E)
    e2 = np.where((cond & eq(D, H))[..., None], D, E)
    e3 = np.where((cond & eq(H, F))[..., None], F, E)
    h, w = img.shape[:2]
    out = np.empty((h * 2, w * 2, img.shape[2]), dtype=img.dtype)
    out[0::2, 0::2] = e0
    out[0::2, 1::2] = e1
    out[1::2, 0::2] = e2
    out[1::2, 1::2] = e3
    return out


def upscale_scale2x(img: np.ndarray, scale: float) -> np.ndarray:
    h, w = img.shape[:2]
    target = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    out = img
    s = 1
    while s * 2 <= scale + 1e-6:
        out = scale2x(out)
        s *= 2
    if out.shape[1] != target[0] or out.shape[0] != target[1]:
        out = np.array(Image.fromarray(out, "RGBA").resize(target, Image.NEAREST))
    return out


def upscale(img: np.ndarray, method: str, scale: float, smoothness: float = 1.0,
            blend_width: float = 1.0, max_colors: int = 64, progress: Progress = None) -> np.ndarray:
    img = np.ascontiguousarray(img[..., :4] if img.shape[2] == 4 else
                               np.dstack([img, np.full(img.shape[:2], 255, np.uint8)]))
    h, w = img.shape[:2]
    size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    if method == "shape":
        return upscale_shape(img, scale, smoothness, max_colors, progress)
    if method == "shape_aa":
        return upscale_shape_aa(img, scale, smoothness, max_colors, progress=progress)
    if method == "blend":
        return upscale_blend(img, scale, smoothness, blend_width, max_colors, progress)
    if method == "scale2x":
        return upscale_scale2x(img, scale)
    if method == "bicubic":
        return np.array(Image.fromarray(img, "RGBA").resize(size, Image.BICUBIC))
    if method == "nearest":
        return np.array(Image.fromarray(img, "RGBA").resize(size, Image.NEAREST))
    raise ValueError(f"Unknown method {method}")
