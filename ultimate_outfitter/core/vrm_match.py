"""Match the textures inside a VRoid .vrm file to the character's wardrobe images.

A VRoid model's clothing textures are usually images made by the wardrobe creator. When a
model texture is (a resized / re-encoded copy of) a wardrobe piece, the 3D preview can apply
that piece's intended effects automatically:

* metallic / silk shine - only where the piece's saved shine mask is white
* thin fabric          - see-through while wet
"""
from __future__ import annotations

import io
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image

SIG_SIZE = 48
MATCH_THRESHOLD = 14.0     # mean colour difference (0-255) allowed for a match


# ---------------------------------------------------------------------------
# GLB / VRM reading
# ---------------------------------------------------------------------------

def read_glb(path: Path | str) -> tuple[dict, bytes]:
    data = Path(path).read_bytes()
    magic, _version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError("Not a binary glTF / VRM file")
    offset = 12
    js, binary = None, b""
    while offset < min(length, len(data)):
        chunk_len, chunk_type = struct.unpack_from("<I4s", data, offset)
        chunk = data[offset + 8: offset + 8 + chunk_len]
        if chunk_type == b"JSON":
            js = json.loads(chunk.decode("utf-8"))
        elif chunk_type == b"BIN\x00":
            binary = chunk
        offset += 8 + chunk_len
    if js is None:
        raise ValueError("VRM file has no JSON chunk")
    return js, binary


def _image_bytes(js: dict, binary: bytes, image_index: int) -> bytes | None:
    images = js.get("images") or []
    if not 0 <= image_index < len(images):
        return None
    img = images[image_index]
    if "bufferView" in img:
        bv = js["bufferViews"][img["bufferView"]]
        start = bv.get("byteOffset", 0)
        return binary[start:start + bv["byteLength"]]
    return None


def material_textures(path: Path | str) -> list[dict]:
    """[{material, image_index, image (PIL RGBA)}] for every material's main (colour) texture."""
    js, binary = read_glb(path)
    textures = js.get("textures") or []
    materials = js.get("materials") or []

    def tex_to_image(tex_index):
        if tex_index is None or not 0 <= tex_index < len(textures):
            return None
        return textures[tex_index].get("source")

    # VRM 0.x keeps MToon textures in extensions.VRM.materialProperties
    vrm0_main = {}
    for mp in (js.get("extensions", {}).get("VRM", {}).get("materialProperties") or []):
        tp = mp.get("textureProperties") or {}
        if "_MainTex" in tp:
            vrm0_main[mp.get("name")] = tp["_MainTex"]

    out, cache = [], {}
    for mat in materials:
        name = mat.get("name", "")
        tex_index = (mat.get("pbrMetallicRoughness") or {}).get("baseColorTexture", {}).get("index")
        if tex_index is None and name in vrm0_main:
            tex_index = vrm0_main[name]
        image_index = tex_to_image(tex_index)
        if image_index is None:
            continue
        if image_index not in cache:
            raw = _image_bytes(js, binary, image_index)
            try:
                cache[image_index] = Image.open(io.BytesIO(raw)).convert("RGBA") if raw else None
            except OSError:
                cache[image_index] = None
        if cache[image_index] is not None:
            out.append({"material": name, "image_index": image_index, "image": cache[image_index]})
    return out


# ---------------------------------------------------------------------------
# image comparison
# ---------------------------------------------------------------------------

def signature(img: Image.Image) -> np.ndarray:
    """Small premultiplied RGBA thumbnail used for comparing images of any size."""
    small = img.convert("RGBA").resize((SIG_SIZE, SIG_SIZE), Image.BILINEAR)
    a = np.asarray(small, dtype=np.float32)
    alpha = a[..., 3:4] / 255.0
    return np.concatenate([a[..., :3] * alpha, a[..., 3:4]], axis=-1)


def difference(sig_a: np.ndarray, sig_b: np.ndarray) -> float:
    """Mean colour difference (0-255) where either image has content."""
    content = (sig_a[..., 3] > 8) | (sig_b[..., 3] > 8)
    if not content.any():
        return 255.0
    return float(np.abs(sig_a[content] - sig_b[content]).mean())


_sig_cache: dict[str, tuple[float, np.ndarray]] = {}


def file_signature(path: Path) -> np.ndarray | None:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    key = str(path)
    hit = _sig_cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        with Image.open(path) as im:
            sig = signature(im)
    except OSError:
        return None
    _sig_cache[key] = (mtime, sig)
    return sig


def match_wardrobe(character, vrm_path: Path | str, threshold: float = MATCH_THRESHOLD) -> list[dict]:
    """Find wardrobe pieces whose images are used as textures in the VRM.

    Returns one dict per matched material:
    {material, entry_id, item_name, file, file_index, difference, shine: [{kind, mask}], thin}
    where ``mask`` is a path (relative to the character folder) to the piece's shine mask.
    """
    mats = material_textures(vrm_path)
    if not mats:
        return []
    wardrobe = character.data.get("wardrobe", {})
    current = {p.get("entry_id") for p in (character.data.get("current_outfit") or {}).get("pieces", [])}
    candidates = []
    for eid, e in wardrobe.items():
        for i, rel in enumerate(e.get("files") or [e.get("file")]):
            if rel:
                candidates.append((eid, i, rel))
    if not candidates:
        return []
    sigs = {}
    for eid, i, rel in candidates:
        sig = file_signature(character.dir / rel)
        if sig is not None:
            sigs[(eid, i)] = sig
    results = []
    tex_sigs: dict[int, np.ndarray] = {}
    for m in mats:
        if m["image_index"] not in tex_sigs:
            tex_sigs[m["image_index"]] = signature(m["image"])
        tsig = tex_sigs[m["image_index"]]
        best = None
        for (eid, i), sig in sigs.items():
            d = difference(tsig, sig)
            # pieces of the current outfit win ties
            key = (d - (2.0 if eid in current else 0.0), d)
            if d <= threshold and (best is None or key < best[0]):
                best = (key, eid, i, d)
        if best is None:
            continue
        _, eid, i, d = best
        e = wardrobe[eid]
        if not e.get("shine_masks") and hasattr(character, "ensure_shine_masks"):
            character.ensure_shine_masks(e)
        item = character.library.items.get(e.get("item_id"), {})
        masks = e.get("shine_masks") or []
        shine = []
        kinds = e.get("shine") or []
        if kinds:
            stem = Path((e.get("files") or [e["file"]])[i]).stem
            mask = next((mk for mk in masks if Path(mk).stem.startswith(stem)), masks[i] if i < len(masks) else None)
            for kind in kinds:
                shine.append({"kind": kind, "mask": mask})
        results.append({
            "material": m["material"], "entry_id": eid, "item_name": e.get("item_name", ""),
            "file": (e.get("files") or [e["file"]])[i], "file_index": i, "difference": round(d, 2),
            "shine": shine, "thin": item.get("attrs", {}).get("thickness") == "thin",
        })
    return results
