import numpy as np
import pytest
from PIL import Image

from ultimate_outfitter.core import categories, colors, imaging, upscale
from ultimate_outfitter.core.character import CHARACTER_QUESTIONS, Character
from ultimate_outfitter.core.outfit import DayContext, NoOutfitPossible, OutfitSession, do_laundry
from ultimate_outfitter.core.storage import Library, unique_path


def _garment(path, color=(200, 40, 40), accent=(30, 30, 160)):
    img = np.full((64, 64, 4), 255, np.uint8)
    img[12:52, 16:48, :3] = color
    img[12:20, 16:48, :3] = accent
    img[30:34, 20:30, :3] = (np.array(color) * 0.6).astype(np.uint8)
    Image.fromarray(img, "RGBA").save(path)
    return path


def _first_answers(category):
    ans = {}
    for q in categories.questions_for(category):
        ans[q.id] = [q.options[0].label] if q.multi else q.options[0].label
    return ans


@pytest.fixture
def lib(tmp_path):
    return Library(tmp_path / "data")


def test_color_roundtrip():
    rgb = np.array([[12, 200, 99], [255, 255, 255], [0, 0, 0]], float)
    back = colors.lab_to_rgb(colors.rgb_to_lab(rgb))
    assert np.abs(back - rgb).max() < 1.0
    assert colors.rgb_to_hex(colors.hex_to_rgb("#a1B2c3")) == "#A1B2C3"
    assert colors.hsv_to_rgb(*colors.rgb_to_hsv((10, 20, 30))) == (10, 20, 30)


def test_every_category_has_specific_questions():
    names = set(categories.CATEGORY_NAMES)
    for required in ["Underwear Bottoms", "Bras", "Swimsuit Bottoms", "Swimsuit Tops", "One-Piece Swimsuits",
                     "Shirts", "Tanktops", "Hoodies", "Vests", "Jackets", "Dresses", "Coats", "Corsets",
                     "Activewear Tops", "Capes/Cloaks", "Sweaters/Cardigans", "Blazers", "Scarves/Shawls",
                     "Bodysuits", "Armor", "Belts", "Jewelry", "Robes/Yukatas/Kimonos", "Pants", "Shorts",
                     "Skirts", "Aprons", "Ties", "Gloves", "Cuffs", "Arm Warmers/Detached Sleeves", "Socks",
                     "Shoes", "Boots", "Sandals", "Glasses", "Hats", "Helmets"]:
        assert required in names
    for cat in categories.CATEGORIES:
        assert cat.questions, cat.name
        traits, attrs = categories.evaluate_answers(cat.name, _first_answers(cat.name))
        assert traits and max(traits.values()) == 1.0
        assert attrs["slot"] == cat.slot


def test_unique_path_never_overwrites(tmp_path):
    p = tmp_path / "a.png"
    p.write_text("x")
    q = unique_path(p)
    assert q.name == "a (2).png" and not q.exists()


def test_selection_and_recolor():
    img = np.zeros((20, 20, 4), np.uint8)
    img[..., 3] = 255
    img[2:8, 2:8, :3] = (255, 0, 0)
    img[12:18, 12:18, :3] = (250, 5, 5)
    sel = imaging.select_color(img, (3, 3), 10, contiguous=True)
    assert sel.sum() == 36
    sel_all = imaging.select_color(img, (3, 3), 10, contiguous=False)
    assert sel_all.sum() == 72
    hue = imaging.select_hue(img, (3, 3), 15)
    assert hue.sum() == 72
    out = imaging.recolor_regions(img, sel, [["#00FF00"]])
    assert out[4, 4, 1] > 150 and out[4, 4, 0] < 100
    assert (out[~sel] == img[~sel]).all()


def test_pattern_masked():
    img = np.full((16, 16, 4), 128, np.uint8)
    img[..., 3] = 255
    mask = np.zeros((16, 16), bool)
    mask[4:12, 4:12] = True
    pat = np.zeros((2, 2, 4), np.uint8)
    pat[..., 3] = 255
    pat[0, 0, :3] = 255
    out = imaging.apply_pattern(img, mask, pat, scale=2, antialias=False, blend="replace")
    assert (out[~mask] == img[~mask]).all()
    assert not (out[mask] == img[mask]).all()


def test_upscale_methods():
    img = np.zeros((10, 10, 4), np.uint8)
    img[..., 3] = 255
    img[3:7, 3:7, :3] = 255
    for m in upscale.METHODS:
        out = upscale.upscale(img, m, 4)
        assert out.shape == (40, 40, 4)
    no_new = upscale.upscale(img, "shape", 4)
    assert len(np.unique(no_new.reshape(-1, 4), axis=0)) == 2


def test_full_flow(lib, tmp_path):
    pal_a = lib.add_palette("Ruby", ["#7A0010", "#C8102E", "#F28B9B"])
    pal_b = lib.add_palette("Navy", ["#0B1A40", "#1F3A93", "#7FA3E6"])
    lib.add_palette("Lime", ["#3CFF00", "#B6FF7A"])
    for cat in ["Underwear Bottoms", "Bras", "Shirts", "Pants", "Shoes", "Socks", "Dresses", "Jewelry"]:
        for n in range(2):
            src = _garment(tmp_path / f"{cat.replace('/', '_')}{n}.png")
            ans = _first_answers(cat)
            traits, attrs = categories.evaluate_answers(cat, ans)
            lib.add_item(src, f"{cat.split('/')[0]} {n}", cat, ans, traits, attrs)
    char_img = np.full((80, 80, 4), 255, np.uint8)
    char_img[10:70, 20:40, :3] = colors.hex_to_rgb("#C8102E")
    char_img[10:70, 40:60, :3] = colors.hex_to_rgb("#1F3A93")
    char_img[30:40, 25:35, :3] = colors.hex_to_rgb("#F28B9B")
    char_img[30:40, 45:55, :3] = colors.hex_to_rgb("#7FA3E6")
    char_img[50:60, 25:35, :3] = colors.hex_to_rgb("#7A0010")
    char_img[50:60, 45:55, :3] = colors.hex_to_rgb("#0B1A40")
    Image.fromarray(char_img, "RGBA").save(tmp_path / "hero.png")
    answers = {q.id: ([q.options[0].label] if q.multi else q.options[0].label) for q in CHARACTER_QUESTIONS}
    ch = Character.create(lib, "Hero", tmp_path / "hero.png", answers, {"wears_bra": "Yes"})
    matches = ch.scan_palettes(precision=70, min_coverage=0.6)
    ids = [m["palette_id"] for m in matches]
    assert pal_a["id"] in ids and pal_b["id"] in ids
    assert len(ids) == 2
    ch.data["gen_settings"]["min_score"] = 0
    created = ch.build_wardrobe()
    assert created
    files = [ch.entry_path(e) for e in created]
    assert all(f.exists() for f in files)
    assert len(set(files)) == len(files)
    assert any("+" in e["file"] for e in created)  # multi-palette versions exist
    assert all(e["file"].startswith("Wardrobe/Hero-") for e in created)
    # no new items -> rescan creates nothing
    assert ch.new_item_ids() == []
    src = _garment(tmp_path / "newshirt.png")
    ans = _first_answers("Shirts")
    t, a = categories.evaluate_answers("Shirts", ans)
    new = lib.add_item(src, "New Shirt", "Shirts", ans, t, a)
    assert ch.new_item_ids() == [new["id"]]
    more = ch.build_wardrobe(ch.new_item_ids())
    assert more and all(e["item_id"] == new["id"] for e in more)

    ctx = DayContext("Casual / errands", "Happy", "Mild")
    session = OutfitSession(ch, ctx)
    proposal = session.build()
    assert "underwear_bottom" in proposal and "footwear" in proposal
    assert ("full_body" in proposal) != ("base_top" in proposal and "legs" in proposal)
    some = proposal["footwear"][0]
    repl = session.reject(some, "clash")
    assert repl is None or repl["id"] != some
    if "socks" in session.proposal:
        sock = session.proposal["socks"][0]
        assert session.reject(sock, "unnecessary") is None
        assert "socks" not in session.proposal
    for e in session.in_use():
        session.approve(e)
    assert session.all_approved()
    outfit = session.finalize()
    assert outfit["pieces"]
    for p in outfit["pieces"]:
        assert p["entry_id"] in ch.data["hamper"] and p["entry_id"] not in ch.data["dresser"]
    # exhaust the dresser until laundry is needed
    with pytest.raises(NoOutfitPossible) as exc:
        for _ in range(200):
            s = OutfitSession(ch, ctx)
            s.build()
            for e in s.in_use():
                s.approve(e)
            s.finalize()
    assert exc.value.laundry_helps
    moved = do_laundry(ch)
    assert moved > 0 and not ch.data["hamper"]
    OutfitSession(ch, ctx).build()
    # profile reloads from disk
    again = Character(lib, ch.path)
    assert again.data["wardrobe"].keys() == ch.data["wardrobe"].keys()


def test_upscale_keeps_thin_diagonal_lines():
    img = np.zeros((16, 16, 4), np.uint8)
    img[..., 3] = 255
    for i in range(16):
        img[i, i, :3] = 255
    for m in ("shape", "shape_aa"):
        out = upscale.upscale(img, m, 4)
        # every point along the diagonal stays light
        diag = np.array([out[4 * i + 2, 4 * i + 2, 0] for i in range(1, 15)])
        assert (diag > 128).all(), m


def _wardrobe_char(lib, tmp_path, cats, prefs=None):
    lib.add_palette("Ruby", ["#7A0010", "#C8102E", "#F28B9B"])
    for cat in cats:
        src = _garment(tmp_path / f"{cat.replace('/', '_')}.png")
        ans = _first_answers(cat)
        t, a = categories.evaluate_answers(cat, ans)
        lib.add_item(src, cat, cat, ans, t, a)
    img = np.full((40, 40, 4), 255, np.uint8)
    img[5:35, 5:35, :3] = colors.hex_to_rgb("#C8102E")
    img[10:20, 10:20, :3] = colors.hex_to_rgb("#7A0010")
    img[22:30, 10:20, :3] = colors.hex_to_rgb("#F28B9B")
    Image.fromarray(img, "RGBA").save(tmp_path / "c.png")
    answers = {q.id: ([q.options[0].label] if q.multi else q.options[0].label) for q in CHARACTER_QUESTIONS}
    ch = Character.create(lib, "Mia", tmp_path / "c.png", answers, prefs or {"wears_bra": "Yes"})
    assert ch.scan_palettes(100, 1.0)  # exact colours match at maximum precision
    ch.data["gen_settings"]["min_score"] = 0
    ch.build_wardrobe()
    return ch


def test_exact_color_extraction():
    img = np.zeros((10, 10, 3), np.uint8)
    img[:5] = (200, 16, 46)
    img[5:8] = (201, 16, 46)
    img[8:] = (11, 26, 64)
    exact = colors.extract_exact_colors(img, 8)
    assert [colors.rgb_to_hex(c) for c, _ in exact] == ["#C8102E", "#C9102E", "#0B1A40"]
    merged = colors.extract_exact_colors(img, 8, merge_tolerance=2)
    assert [colors.rgb_to_hex(c) for c, _ in merged] == ["#C8102E", "#0B1A40"]
    assert merged[0][1] == pytest.approx(0.8)
    assert colors.precision_to_threshold(100) <= 0.5


def test_underwear_only_outfit(lib, tmp_path):
    ch = _wardrobe_char(lib, tmp_path, ["Underwear Bottoms", "Bras", "Shirts", "Pants", "Shoes", "Jewelry"])
    for setting in ("Private / at home", "Beach / pool"):
        s = OutfitSession(ch, DayContext("Lounging at home", "Calm", "Warm", setting=setting, underwear_only=True))
        proposal = s.build()
        assert {"underwear_bottom", "bra"} <= set(proposal)
        assert not {"base_top", "legs", "full_body"} & set(proposal)
    # ignored in public
    s = OutfitSession(ch, DayContext("Casual / errands", "Calm", "Warm", setting="Public", underwear_only=True))
    assert "base_top" in s.build() or "full_body" in s.proposal


def test_underwear_counts_as_swimwear(lib, tmp_path):
    ch = _wardrobe_char(lib, tmp_path, ["Underwear Bottoms", "Bras", "Sandals"])
    s = OutfitSession(ch, DayContext("Swimming / beach", "Happy", "Scorching hot"))
    proposal = s.build()
    slots = {ch.data["wardrobe"][e]["category"]: sl for sl, ids in proposal.items() for e in ids}
    assert slots["Underwear Bottoms"] == "swim_bottom" and slots["Bras"] == "swim_top"
    ch.data["prefs"]["underwear_as_swimwear"] = False
    with pytest.raises(NoOutfitPossible):
        OutfitSession(ch, DayContext("Swimming / beach", "Happy", "Scorching hot")).build()
