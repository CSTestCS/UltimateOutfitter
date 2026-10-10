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
    ch.data["gen_settings"]["multi_palette_chance"] = 0.5
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


def _wardrobe_char(lib, tmp_path, cats, prefs=None, build=True):
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
    if build:
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
    s = OutfitSession(ch, DayContext("Swimming / beach", "Happy", "Scorching hot"))
    proposal = s.build()  # no swimwear owned: best effort instead of refusing
    assert not {"swim_top", "swim_bottom", "swim_full"} & set(proposal)
    assert any("Incomplete" in w for w in s.warnings)


def test_best_effort_when_laundry_would_not_help(lib, tmp_path):
    # only underwear owned: no tops, bottoms or shoes at all
    ch = _wardrobe_char(lib, tmp_path, ["Underwear Bottoms", "Bras"])
    s = OutfitSession(ch, DayContext("Work / office", "Focused", "Mild"))
    proposal = s.build()
    assert set(proposal) == {"underwear_bottom", "bra"}
    assert any("Incomplete" in w for w in s.warnings)


def test_incomplete_outfit_allowed_instead_of_laundry(lib, tmp_path):
    ch = _wardrobe_char(lib, tmp_path, ["Underwear Bottoms", "Bras", "Shirts", "Pants", "Shoes"])
    shoes = [e["id"] for e in ch.data["wardrobe"].values() if e["category"] == "Shoes"]
    for e in shoes:  # every pair of shoes is dirty
        ch.data["dresser"].remove(e)
        ch.data["hamper"].append(e)
    ctx = DayContext("Casual / errands", "Happy", "Mild")
    with pytest.raises(NoOutfitPossible) as exc:
        OutfitSession(ch, ctx).build()
    assert exc.value.laundry_helps
    s = OutfitSession(ch, ctx)
    proposal = s.build(allow_incomplete=True)
    assert "footwear" not in proposal and "base_top" in proposal



def test_realistic_wardrobe_is_limited(lib, tmp_path):
    for i in range(6):
        lib.add_palette(f"P{i}", [f"#{i * 40:02X}1020", f"#{i * 40:02X}5060", f"#{i * 40:02X}A0B0"])
    ch = _wardrobe_char(lib, tmp_path, ["Shirts"], build=False)
    for p in lib.palettes.values():  # pretend everything matched
        ch.data["palette_scan"]["matches"].append({"palette_id": p["id"], "coverage": 1, "distance": 0})
    plan = ch.plan_wardrobe()
    assert 0 < len(plan) <= 10  # one shirt design is not made in every palette and combo
    per_item = {}
    for p in plan:
        per_item[p["item"]["id"]] = per_item.get(p["item"]["id"], 0) + 1
    assert max(per_item.values()) <= ch.data["gen_settings"]["max_colourways"]
    ch.data["gen_settings"]["exhaustive"] = True
    assert len(ch.plan_wardrobe()) > len(plan)


def test_low_alpha_dregs_not_coloured():
    img = np.zeros((20, 20, 4), np.uint8)
    img[5:15, 5:15] = (200, 50, 50, 255)
    img[0:3, 0:20] = (10, 200, 10, 20)  # 8% opaque cleanup dregs
    mask = imaging.auto_mask(img)
    assert not mask[0:3].any() and mask[5:15, 5:15].all()
    out = imaging.recolor_regions(img, mask, [["#0000FF", "#00FFFF"]])
    assert (out[0:3] == img[0:3]).all()


def test_shades_palette_uses_neutral_as_primary():
    img = np.full((20, 20, 4), 255, np.uint8)
    img[:, :, :3] = (120, 120, 120)          # big main area
    img[0:3, :, :3] = (40, 40, 40)            # small dark trim
    mask = np.ones((20, 20), bool)
    shades = ["#101040", "#202080", "#4040C0", "#8080E0", "#C0C0F8"]
    out = imaging.recolor_regions(img, mask, [shades], kinds=["shades"])
    main = colors.rgb_to_lab(out[10, 10, :3].astype(float))
    neutral = colors.rgb_to_lab(np.array(colors.hex_to_rgb("#4040C0"), float))
    assert np.abs(main - neutral).max() < 3
    assert colors.rgb_to_lab(out[1, 1, :3].astype(float))[0] < main[0]


def test_multi_image_item_and_pattern(lib, tmp_path):
    src1 = _garment(tmp_path / "front.png")
    src2 = _garment(tmp_path / "back.png", color=(190, 50, 50))
    ans = _first_answers("Shirts")
    ans["print"] = "Yes - on the main fabric"
    t, a = categories.evaluate_answers("Shirts", ans)
    item = lib.add_item([src1, src2], "Tee", "Shirts", ans, t, a)
    assert len(item["images"]) == 2
    pat = np.zeros((4, 4, 4), np.uint8)
    pat[..., 3] = 255
    pat[::2, ::2, :3] = 255
    pat[1::2, 1::2, 3] = 0  # transparent holes -> cutaway
    Image.fromarray(pat, "RGBA").save(tmp_path / "dots.png")
    from ultimate_outfitter.core.patterns import evaluate_pattern
    pans = {"pattern_kind": "Animal print", "pattern_boldness": "Loud / high contrast", "pattern_uses": ["Tops"]}
    pt, pa = evaluate_pattern(pans)
    lib.add_pattern(tmp_path / "dots.png", "Dots", pans, pt, pa, cutaway="alpha")
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    ch.data["gen_settings"].update(min_score=0, pattern_chance=1.0)
    created = ch.build_wardrobe()
    tee = [e for e in created if e["item_id"] == item["id"]]
    assert tee and all(len(e["files"]) == 2 for e in tee)
    assert any(e["pattern_name"] == "Dots" for e in tee)
    e = next(e for e in tee if e["pattern"])
    front = np.array(Image.open(ch.dir / e["files"][0]))
    assert (front[..., 3] < 200).sum() > (np.array(Image.open(src1))[..., 3] < 200).sum()  # holes cut
    assert e["files"][1].endswith("-2.png")


def test_multiple_character_images(lib, tmp_path):
    ch = _wardrobe_char(lib, tmp_path, [])
    lib.add_palette("Teal", ["#008080", "#20B2AA"])
    assert "Teal" not in [p["name"] for p in ch.matched_palettes()]
    img = np.full((30, 30, 4), 255, np.uint8)
    img[5:25, 5:15, :3] = colors.hex_to_rgb("#008080")
    img[5:25, 15:25, :3] = colors.hex_to_rgb("#20B2AA")
    Image.fromarray(img).save(tmp_path / "alt.png")
    ch.add_image(tmp_path / "alt.png")
    ch.scan_palettes(100, 1.0)
    names = [p["name"] for p in ch.matched_palettes()]
    assert "Teal" in names and "Ruby" in names


def test_conversation_engine(lib, tmp_path):
    import random
    from ultimate_outfitter.core.interact import TEMPLATES, Conversation
    ch = _wardrobe_char(lib, tmp_path, ["Underwear Bottoms", "Bras", "Shirts", "Pants", "Shoes"])
    s = OutfitSession(ch, DayContext("Lounging at home", "Calm", "Warm", setting="Private / at home",
                                     underwear_only=True))
    s.build()
    for e in s.in_use():
        s.approve(e)
    s.finalize()
    conv = Conversation(ch, "Sam", random.Random(3))
    assert conv.state["setting"] == "Private / at home"
    for intent in TEMPLATES:
        if intent.startswith(("issue_", "init_", "accept_", "decline_")) or intent in ("outfit_ok", "change_mood"):
            continue
        r = conv.respond(intent)
        assert r.text and "{" not in r.text, (intent, r.text)
    for _ in range(20):
        r = conv.initiative()
        assert r.text and "{" not in r.text
    conv.state["setting"] = "Private / at home"
    assert not any(i == "underdressed" for i, _ in conv.outfit_issues())
    conv.state["setting"] = "Public"
    assert any(i == "underdressed" for i, _ in conv.outfit_issues())
    r = conv.respond("ask_outfit")
    assert "{" not in r.text
    r = conv.respond("suggest_activity", activity="Workout / sports")
    r = conv.respond("set_mood", mood="Happy")
    assert conv.state["mood"] == "Happy" and r.changes["mood"] == "Happy"
    assert Conversation.intent_from_text("I love your outfit!") == "compliment_outfit"
    assert Conversation.intent_from_text("hello there") == "greet"
    assert ch.data["chat_log"]


def test_animation_names_and_choice(tmp_path):
    import random
    from ultimate_outfitter.core.animations import AnimationLibrary, parse_name
    lib = AnimationLibrary(tmp_path / "Animations")
    assert (tmp_path / "Animations" / "README.md").exists()
    for n in ["idle.fbx", "idle_happy.fbx", "idle_beach_happy.fbx", "idle_happy_2.fbx", "pose_sitting.fbx",
              "pose_lounging.fbx", "emote_wave.fbx", "emote_wave_shy.fbx", "emote_shake_head.fbx",
              "emote_unknownthing.fbx", "random.fbx"]:
        (tmp_path / "Animations" / n).write_bytes(b"")
    lib.rescan()
    assert parse_name(tmp_path / "x" / "emote_shake_head (2).fbx").event == "shake_head"
    assert parse_name(tmp_path / "x" / "random.fbx") is None
    rng = random.Random(1)
    beach = {"mood": "Happy", "setting": "Beach / pool", "activity": "Swimming / beach", "weather": "Warm"}
    assert lib.choose_idle(beach, "cheerful", rng).path.name == "idle_beach_happy.fbx"
    home = dict(beach, setting="Private / at home", activity="Lounging at home")
    names = {lib.choose_idle(home, "cheerful", rng).path.name for _ in range(20)}
    assert names <= {"idle_happy.fbx", "idle_happy_2.fbx", "pose_lounging.fbx"}
    sad = dict(home, mood="Sad", activity="Work / office")
    assert lib.choose_idle(sad, "edgy", rng).path.name == "idle.fbx"  # pose_sitting is manual only
    assert lib.choose_emote("wave", home, "shy", rng).path.name == "emote_wave_shy.fbx"
    assert lib.choose_emote("wave", home, "edgy", rng).path.name == "emote_wave.fbx"
    assert lib.choose_emote("laugh", home, "edgy", rng) is None
    assert [a.event for a in lib.poses()] == ["lounging", "sitting"]


def test_expressions_config(lib, tmp_path):
    from ultimate_outfitter.core import expressions
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    cfg = expressions.load(ch)
    assert (ch.dir / "expressions.txt").exists()
    assert expressions.weights_for(cfg, "Happy") == {"happy": 1.0}
    assert expressions.weights_for(cfg, "cozy / tired") == {"relaxed": 0.8, "blink": 0.35}
    (ch.dir / "expressions.txt").write_text("# c\nHappy = Fcl_ALL_Joy:0.7, happy\nSad =\n", encoding="utf-8")
    cfg = expressions.load(ch)
    assert expressions.weights_for(cfg, "Happy") == {"Fcl_ALL_Joy": 0.7, "happy": 1.0}
    assert expressions.weights_for(cfg, "Sad") == {}


def test_viewer_server(tmp_path):
    import urllib.error
    import urllib.request
    from ultimate_outfitter.core.viewer_server import ViewerServer
    (tmp_path / "Characters").mkdir()
    (tmp_path / "Characters" / "a b.vrm").write_bytes(b"glTF")
    (tmp_path.parent / "secret.txt").write_text("no")
    srv = ViewerServer(tmp_path)
    try:
        url = srv.lib_url(tmp_path / "Characters" / "a b.vrm")
        assert urllib.request.urlopen(url).read() == b"glTF"
        assert b"viewer.bundle.js" in urllib.request.urlopen(srv.viewer_url()).read()
        for bad in ("/lib/../secret.txt", "/lib/%2e%2e/secret.txt", "/other/x", "/lib/Characters"):
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(f"http://127.0.0.1:{srv.port}{bad}")
    finally:
        srv.stop()


def test_reply_emotes_and_typed_suggestions(lib, tmp_path):
    import random
    from ultimate_outfitter.core.interact import Conversation
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    conv = Conversation(ch, "Sam", random.Random(2))
    assert conv.respond("greet").emote == "wave"
    assert conv.respond("goodbye").emote == "goodbye"
    assert Conversation.parse_text("It's late, go to bed") == ("suggest_activity", {"activity": "Sleeping"})
    assert Conversation.parse_text("let's go to the beach!")[1] == {"setting": "Beach / pool"}
    r = conv.respond("suggest_activity", activity="Sleeping")
    assert r.emote in ("nod", "shake_head") or r.emote.startswith(("embarrassed", "shrug", "laugh", "frustrated",
                                                                   "proud", "tease", "shiver", "fan"))


def test_metallic_palette_shines_only_its_own_parts(lib, tmp_path):
    from ultimate_outfitter.core.imaging import shine_kind
    assert shine_kind("MetallicGreen") == "metallic" and shine_kind("Silk Scarf") == "silk"
    assert shine_kind("Purple") is None
    green = lib.add_palette("MetallicGreen", ["#0B3D20", "#1E8A4A", "#7FE0A0"])
    purple = lib.add_palette("Purple", ["#3A1060", "#7A3AB0", "#C8A0F0"])
    plain_green = dict(green, name="Green")
    src = _garment(tmp_path / "hat.png", color=(150, 150, 150), accent=(40, 40, 40))
    ans = _first_answers("Hats")
    t, a = categories.evaluate_answers("Hats", ans)
    hat = lib.add_item(src, "Hat", "Hats", ans, t, a)
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    shine: list = []
    shiny = ch.render_piece(hat, [green, purple], None, {}, shine_out=shine)[0]
    plain = ch.render_piece(hat, [plain_green, purple], None, {})[0]
    (mask, kind), = shine[0]
    assert kind == "metallic" and mask.any()
    changed = np.any(shiny != plain, axis=-1)
    assert changed.any()
    assert not (changed & ~mask).any()          # nothing outside the MetallicGreen parts changed
    # building the wardrobe names the piece after the palettes and saves the mask
    ch.data["palette_scan"]["matches"] = [{"palette_id": green["id"], "coverage": 1, "distance": 0},
                                          {"palette_id": purple["id"], "coverage": 1, "distance": 0}]
    plan = [{"item": hat, "score": 90, "palettes": [green, purple], "pattern": None}]
    entry, = ch.build_wardrobe(plan=plan)
    assert "Hat-MetallicGreen+Purple" in entry["file"]
    assert entry["shine"] == ["metallic"] and len(entry["shine_masks"]) == 1
    saved = np.array(Image.open(ch.dir / entry["shine_masks"][0])) > 0
    assert (saved == mask).all()
    # an item called "Silk ..." shines on its main palette when no palette asks for it
    silk = lib.add_item(src, "Silk Hat", "Hats", ans, t, a)
    shine2: list = []
    ch.render_piece(silk, [plain_green, purple], None, {}, shine_out=shine2)
    assert shine2[0] and shine2[0][0][1] == "silk"


def test_thickness_and_material_rules(lib, tmp_path):
    from ultimate_outfitter.core import material_rules
    qids = [q.id for q in categories.questions_for("Bras")]
    assert "thickness" in qids and "thickness" not in [q.id for q in categories.questions_for("Jewelry")]
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    (ch.dir / "materials.txt").write_text(material_rules.HEADER.format(name="x") +
                                          "Bra = metallic\nTops_01 = thin\nHair = none\nBad = sparkly\n",
                                          encoding="utf-8")
    assert material_rules.load_overrides(ch) == {"Bra": "metallic", "Tops_01": "thin", "Hair": "none"}
    # thin pieces of the current outfit -> material keywords
    ans = _first_answers("Bras")
    ans["thickness"] = "Thin / sheer / lightweight"
    t, a = categories.evaluate_answers("Bras", ans)
    assert a["thickness"] == "thin"
    bra = lib.add_item(_garment(tmp_path / "b.png"), "Bikini Bra", "Bras", ans, t, a)
    ans2 = _first_answers("Shirts")
    ans2["thickness"] = "Thick / heavy"
    t2, a2 = categories.evaluate_answers("Shirts", ans2)
    shirt = lib.add_item(_garment(tmp_path / "s.png"), "Tee", "Shirts", ans2, t2, a2)
    ch.data["wardrobe"] = {"e1": {"item_id": bra["id"], "slot": "bra"}, "e2": {"item_id": shirt["id"], "slot": "base_top"}}
    ch.data["current_outfit"] = {"pieces": [{"entry_id": "e1", "slot": "bra", "name": "Bikini Bra"},
                                            {"entry_id": "e2", "slot": "base_top", "name": "Tee"}]}
    kw = material_rules.thin_keywords(ch)
    assert {"bra", "bikini"} <= set(kw)
    assert "tops" not in kw  # a thick top shares VRoid's "Tops" material, so it isn't made see-through
    del ch.data["current_outfit"]["pieces"][1]
    assert "tops" in material_rules.thin_keywords(ch)
    assert material_rules.is_wet({"activity": "Swimming / beach", "weather": "Warm"}) == (True, 1.0)
    assert material_rules.is_wet({"activity": "Date", "weather": "Rainy"})[0]
    assert not material_rules.is_wet({"activity": "Date", "weather": "Mild"})[0]
