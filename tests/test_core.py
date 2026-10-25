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
    pat = np.kron(pat, np.ones((8, 8, 1), np.uint8))   # big holes survive any print scale
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
        if intent.startswith(("issue_", "init_", "accept_", "decline_", "propose_", "removal_")) or \
                intent in ("outfit_ok", "change_mood"):
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
    # the shine is a preview effect only - the texture keeps exactly the palette colours
    assert (shiny == plain).all()
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
    ans = _first_answers("Bras")
    ans["thickness"] = "Thin / sheer / lightweight"
    t, a = categories.evaluate_answers("Bras", ans)
    assert a["thickness"] == "thin"
    assert material_rules.is_wet({"activity": "Swimming / beach", "weather": "Warm"}) == (True, 1.0)
    assert material_rules.is_wet({"activity": "Date", "weather": "Rainy"})[0]
    assert not material_rules.is_wet({"activity": "Date", "weather": "Mild"})[0]


def _write_glb(path, materials_textures):
    """Minimal GLB: one material per (name, PIL image) using it as base colour texture."""
    import io
    import json as _json
    import struct
    binary = b""
    js = {"asset": {"version": "2.0"}, "images": [], "textures": [], "materials": [], "bufferViews": [],
          "buffers": []}
    for i, (name, img) in enumerate(materials_textures):
        buf = io.BytesIO()
        img.save(buf, "PNG")
        data = buf.getvalue()
        while len(binary) % 4:
            binary += b"\0"
        js["bufferViews"].append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data)})
        binary += data
        js["images"].append({"bufferView": i, "mimeType": "image/png", "name": name + "_tex"})
        js["textures"].append({"source": i})
        js["materials"].append({"name": name, "pbrMetallicRoughness": {"baseColorTexture": {"index": i},
                                                                        "metallicFactor": 1.0}})
    while len(binary) % 4:
        binary += b"\0"
    js["buffers"].append({"byteLength": len(binary)})
    jbytes = _json.dumps(js).encode()
    while len(jbytes) % 4:
        jbytes += b" "
    total = 12 + 8 + len(jbytes) + 8 + len(binary)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(jbytes), b"JSON") + jbytes)
        f.write(struct.pack("<I4s", len(binary), b"BIN\0") + binary)


def test_vrm_textures_match_wardrobe_pieces(lib, tmp_path):
    from ultimate_outfitter.core import vrm_match
    green = lib.add_palette("MetallicGreen", ["#0B3D20", "#1E8A4A", "#7FE0A0"])
    purple = lib.add_palette("Purple", ["#3A1060", "#7A3AB0", "#C8A0F0"])
    ans = _first_answers("Bras")
    ans["thickness"] = "Thin / sheer / lightweight"
    t, a = categories.evaluate_answers("Bras", ans)
    bra = lib.add_item(_garment(tmp_path / "bra.png", color=(150, 150, 150), accent=(40, 40, 40)), "Bra", "Bras",
                       ans, t, a)
    shirt_ans = _first_answers("Shirts")
    t2, a2 = categories.evaluate_answers("Shirts", shirt_ans)
    shirt = lib.add_item(_garment(tmp_path / "shirt.png", color=(30, 90, 200)), "Shirt", "Shirts", shirt_ans, t2, a2)
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    pieces = ch.build_wardrobe(plan=[
        {"item": bra, "score": 90, "palettes": [green, purple], "pattern": None},
        {"item": shirt, "score": 80, "palettes": [purple], "pattern": None},
    ])
    bra_entry = next(e for e in pieces if e["item_id"] == bra["id"])
    # the VRoid model uses the generated bra image (resized, as VRoid would) as a texture
    tex = Image.open(ch.dir / bra_entry["file"]).resize((256, 256), Image.BILINEAR)
    other = Image.new("RGBA", (128, 128), (230, 190, 170, 255))  # skin, not from the wardrobe
    vrm = tmp_path / "model.vrm"
    # skin / face textures are never wardrobe pieces, even when they look exactly like one; a hair
    # material can be clothing made with VRoid's hair system (a capelet...) and is matched
    _write_glb(vrm, [("N00_010_01_Onepiece_00_CLOTH", tex), ("N00_000_00_Body_00_SKIN", other),
                     ("N00_000_00_Face_00_SKIN (Instance)", tex), ("N00_000_Hair_00_HAIR_01", tex)])
    found = vrm_match.match_wardrobe(ch, vrm)
    assert [m["material"] for m in found] == ["N00_010_01_Onepiece_00_CLOTH", "N00_000_Hair_00_HAIR_01"]
    m = found[0]
    assert m["entry_id"] == bra_entry["id"] and m["thin"]
    assert [s["kind"] for s in m["shine"]] == ["metallic"]
    assert m["shine"][0]["mask"] and (ch.dir / m["shine"][0]["mask"]).exists()
    # an older piece without saved masks gets them generated on demand
    del bra_entry["shine_masks"], bra_entry["shine"]
    found = vrm_match.match_wardrobe(ch, vrm)
    assert found[0]["shine"] and found[0]["shine"][0]["mask"]


def test_palette_lock_uses_exact_shades(lib, tmp_path):
    from ultimate_outfitter.core.imaging import recolor_regions
    shades = ["#202020", "#606060", "#A0A0A0", "#E0E0E0"]
    lib.add_palette("Greys", shades)
    # a gradient garment: many grey levels in one region
    arr = np.zeros((32, 64, 4), np.uint8)
    for x in range(64):
        v = 60 + x * 2
        arr[:, x, :3] = (v, int(v * 0.6), int(v * 0.3))
    arr[..., 3] = 255
    mask = np.ones((32, 64), bool)
    out = np.array(recolor_regions(arr, mask, [shades], kinds=["shades"], lock=True))
    used = {"#%02X%02X%02X" % tuple(px) for px in out[..., :3].reshape(-1, 3)}
    assert used <= set(shades)
    assert "#%02X%02X%02X" % tuple(out[0, 0, :3]) == shades[0]     # darkest -> darkest
    assert "#%02X%02X%02X" % tuple(out[0, -1, :3]) == shades[-1]   # brightest -> brightest
    assert len(used) == len(shades)


def test_extra_palette_on_single_colour_item_adds_pattern(lib, tmp_path):
    a = lib.add_palette("Red", ["#B01010"])
    b = lib.add_palette("Blue", ["#1030C0"])
    arr = np.zeros((40, 40, 4), np.uint8)
    arr[4:36, 4:36] = (150, 150, 150, 255)
    src = tmp_path / "plain.png"
    Image.fromarray(arr, "RGBA").save(src)
    ans = _first_answers("Hats")
    t, at = categories.evaluate_answers("Hats", ans)
    hat = lib.add_item(src, "Plain Hat", "Hats", ans, t, at)
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    info: dict = {}
    out = np.array(ch.render_piece(hat, [a, b], None, {}, info_out=info)[0])
    assert info.get("pattern")
    cols = {tuple(px) for px in out[out[..., 3] > 0][:, :3]}
    assert (0xB0, 0x10, 0x10) in cols and (0x10, 0x30, 0xC0) in cols


def test_shared_character_and_shown_outfit(lib, tmp_path):
    import time as _time
    ch = _wardrobe_char(lib, tmp_path, ["Underwear Bottoms", "Bras", "Shirts", "Pants", "Shoes"])
    assert Character.open(lib, ch.path) is ch          # every tab shares one object
    outfits = []
    for _ in range(2):
        do_laundry(ch)
        s = OutfitSession(ch, DayContext("Casual / errands", "Calm", "Warm"))
        s.build(allow_incomplete=True)
        for e in s.in_use():
            s.approve(e)
        outfits.append(s.finalize())
    first, second = outfits
    assert first["id"] != second["id"] and ch.shown_outfit() is second
    ch.data["shown_outfit"] = first["id"]
    assert ch.shown_outfit() is first
    ch.data["shown_outfit"] = second["id"]
    ch.save()
    # reloaded from disk: current_outfit is the same dict as its history entry
    again = Character(lib, ch.path)
    assert again.data["current_outfit"] is again.data["outfit_history"][-1]
    again.data["current_outfit"]["vrm"] = "Models/x.vrm"
    assert again.data["outfit_history"][-1]["vrm"] == "Models/x.vrm"
    _time.sleep(0.01)
    again.save()
    # a change made elsewhere is picked up instead of being overwritten
    assert Character.open(lib, ch.path) is ch and ch.data["current_outfit"].get("vrm") == "Models/x.vrm"


def test_edit_outfit_keeps_hamper(lib, tmp_path):
    from ultimate_outfitter.core.outfit import edit_outfit
    ch = _wardrobe_char(lib, tmp_path, ["Underwear Bottoms", "Bras", "Shirts", "Shirts", "Pants", "Shoes"])
    s = OutfitSession(ch, DayContext("Casual / errands", "Calm", "Warm"))
    s.build(allow_incomplete=True)
    for e in s.in_use():
        s.approve(e)
    outfit = s.finalize()
    worn = [p["entry_id"] for p in outfit["pieces"]]
    spare = next(e for e in ch.data["dresser"])
    hamper_before = set(ch.data["hamper"])
    edit_outfit(ch, outfit, remove=[worn[0]], add=[spare])
    ids = [p["entry_id"] for p in outfit["pieces"]]
    assert worn[0] not in ids and spare in ids
    assert worn[0] in ch.data["hamper"] and worn[0] not in ch.data["dresser"]   # nothing back to the dresser
    assert spare in ch.data["hamper"] and spare not in ch.data["dresser"]
    assert hamper_before <= set(ch.data["hamper"])
    assert ch.data["outfit_history"][-1] is outfit and outfit.get("preview")


def test_preview_settings_and_wet_rules(lib, tmp_path):
    from ultimate_outfitter.core import expressions, material_rules, preview_settings
    path = preview_settings.ensure(lib)
    data = preview_settings.load(lib)
    assert data["numbers"]["wet thin opacity"] == 0.7 and "Happy" in data["expressions"]
    text = path.read_text(encoding="utf-8")
    text = text.replace("wet darkening = 0.25", "wet darkening = 5").replace("physics = 1", "physics = off")
    text = text.replace("Happy = happy:1.0", "Happy = happy:0.4, Fcl_ALL_Joy:0.5")
    text = text.replace("wet shine = full", "wet shine = Very Low").replace("silk shine = full", "silk shine = 0.4")
    path.write_text(text, encoding="utf-8")
    data = preview_settings.load(lib)
    assert data["numbers"]["wet darkening"] == 0.9 and data["numbers"]["physics"] == 0
    assert data["numbers"]["wet shine"] == 0.15 and data["numbers"]["silk shine"] == 0.4
    # new characters' expressions.txt start from the library defaults
    ch = _wardrobe_char(lib, tmp_path, ["Shirts", "Pants"], build=False)
    assert expressions.load(ch)["happy"] == {"happy": 0.4, "Fcl_ALL_Joy": 0.5}
    assert material_rules.is_wet({"weather": "Scorching hot"})[0]
    assert not material_rules.is_wet({"weather": "Warm"})[0]


def test_outfit_changes_in_conversation(lib, tmp_path):
    import random
    from ultimate_outfitter.core.interact import TEMPLATES, Conversation
    cats = ["Underwear Bottoms", "Bras", "Shirts", "Pants", "Shoes", "Jackets", "Shirts"]
    ch = _wardrobe_char(lib, tmp_path, cats)
    s = OutfitSession(ch, DayContext("Casual / errands", "Calm", "Cold"))
    s.build(allow_incomplete=True)
    for e in s.in_use():
        s.approve(e)
    outfit = s.finalize()
    conv = Conversation(ch, "Sam", random.Random(1))
    w = ch.data["wardrobe"]
    by_slot = {p["slot"]: p["entry_id"] for p in outfit["pieces"]}
    # never takes off underwear, never leaves themselves uncovered in public
    for _ in range(10):
        r = conv.respond_outfit(remove=[by_slot["bra"]])
        assert r.outfit_change is None and "{" not in r.text
    conv.state["setting"] = "Public"
    if "base_top" in by_slot:
        r = conv.respond_outfit(remove=[by_slot["base_top"]] + ([by_slot["outer"]] if "outer" in by_slot else []))
        assert r.outfit_change is None
    # adding / swapping: accepted sometimes, applied to the shown outfit, dresser -> hamper
    spare = next(e for e in ch.data["dresser"] if w[e]["slot"] == "base_top")
    accepted = None
    for _ in range(40):
        r = conv.respond_outfit(add=[spare])
        assert "{" not in r.text
        if r.outfit_change:
            accepted = r
            break
    assert accepted
    conv.apply_change(accepted.outfit_change)
    assert spare in [p["entry_id"] for p in outfit["pieces"]] and spare in ch.data["hamper"]
    # the character asks to take off the jacket in scorching heat; nothing changes until the player agrees
    jacket = by_slot["outer"]
    lib.items[w[jacket]["item_id"]]["attrs"]["warmth"] = 3
    if jacket:
        conv.state["weather"] = "Scorching hot"
        r = conv.propose_removal(allow_regret=False)
        assert r and r.proposal and r.proposal["remove"] == [jacket] and r.proposal["reason"] == "hot"
        assert jacket in [p["entry_id"] for p in outfit["pieces"]]
        no = conv.answer_proposal(False)
        assert no.outfit_change is None and conv.removal_candidate(allow_regret=False) != (jacket, "hot")
        conv.state["kept_on"] = []
        conv.propose_removal(allow_regret=False)
        yes = conv.answer_proposal(True)
        conv.apply_change(yes.outfit_change)
        assert jacket not in [p["entry_id"] for p in outfit["pieces"]]
        assert jacket in ch.data["hamper"] and jacket not in ch.data["dresser"]
        assert [r["entry_id"] for r in outfit["removed"]] == [jacket]
    for key in ("accept_remove", "decline_modest", "propose_remove_regret", "removal_refused"):
        assert TEMPLATES[key]["any"]


def test_shop_offers_and_buys_missing_pieces(lib, tmp_path):
    import random
    from ultimate_outfitter.core.outfit import buy, shop_offer
    ch = _wardrobe_char(lib, tmp_path, ["Underwear Bottoms", "Bras", "Shirts", "Pants"])
    # shoes exist in the library but the character owns none
    ans = _first_answers("Shoes")
    t, a = categories.evaluate_answers("Shoes", ans)
    shoe = lib.add_item(_garment(tmp_path / "shoe.png"), "Runner", "Shoes", ans, t, a)
    for name, col in (("Teal", "#108080"), ("Sun", "#F0C020"), ("Ink", "#202040")):
        lib.add_palette(name, [col])
    s = OutfitSession(ch, DayContext("Casual / errands", "Calm", "Warm"))
    s.build()
    assert "footwear" in s.shop_slots
    rng = random.Random(4)
    offers = [shop_offer(s, "footwear", rng) for _ in range(6)]
    assert all(o and o["item"]["id"] == shoe["id"] for o in offers)
    assert len({tuple(p["id"] for p in o["palettes"]) for o in offers}) > 1   # pressing Shop again re-rolls
    n_before = len(ch.data["wardrobe"])
    processed = list(ch.data["processed_items"])
    entry = buy(ch, offers[0])
    assert entry and entry["slot"] == "footwear" and entry["id"] in ch.data["dresser"] and entry.get("bought")
    assert len(ch.data["wardrobe"]) == n_before + 1
    assert ch.data["processed_items"] == processed      # buying doesn't mark library items as scanned
    s.proposal.setdefault("footwear", []).append(entry["id"])
    assert s.slot_of(entry["id"]) == "footwear"
    # clashing palettes rejected for the slot are not offered
    s.slot_avoid_palettes["footwear"] = {p["id"] for p in list(lib.palettes.values())[:-1]}
    assert all(p["id"] not in s.slot_avoid_palettes["footwear"] for p in shop_offer(s, "footwear", rng)["palettes"])


def test_rejecting_every_dress_switches_to_top_and_bottoms(lib, tmp_path):
    import random
    from ultimate_outfitter.core.outfit import shop_offer
    ch = _wardrobe_char(lib, tmp_path, ["Underwear Bottoms", "Bras", "Shoes", "Dresses", "Shirts", "Skirts",
                                        "Leggings/Tights"])
    s = OutfitSession(ch, DayContext("Casual / errands", "Calm", "Warm"))
    s.build()
    s._drop_group(["base_top", "legs"])          # start from the dress, whatever the build preferred
    s.proposal["full_body"] = [next(e["id"] for e in s.dresser_entries() if e["slot"] == "full_body")]
    s.proposal.pop("legwear", None)
    new = s.reject(s.proposal["full_body"][0], "style")
    assert new and new["slot"] in ("base_top", "legs")
    assert s.proposal.get("base_top") and s.proposal.get("legs") and not s.proposal.get("full_body")
    assert s.proposal.get("legwear")             # tights are considered with the new set
    # rejecting bottoms never switches to a dress, and never touches the (approved) top
    top = s.proposal["base_top"][0]
    s.approve(top)
    assert s.reject(s.proposal["legs"][0], "style") is None
    assert s.proposal["base_top"] == [top] and top in s.approved and not s.proposal.get("full_body")
    assert "full_body" not in s.shop_targets("legs")
    # no dress left after rejecting the top too: nothing to switch back to
    s.approved.discard(top)
    assert s.reject(top, "style") is None
    # shopping for a missing top may offer a dress, and buying it replaces top + bottoms
    rng = random.Random(2)
    slots = {shop_offer(s, "base_top", rng)["slot"] for _ in range(30)}
    assert "full_body" in slots and "base_top" in slots
    from ultimate_outfitter.core.outfit import buy
    offer = next(o for o in (shop_offer(s, "base_top", rng) for _ in range(50)) if o["slot"] == "full_body")
    entry = buy(ch, offer)
    s.add_bought("base_top", entry["id"])
    assert s.proposal["full_body"] == [entry["id"]] and not s.proposal.get("legs") and not s.proposal.get("base_top")


def test_manual_piece_options(lib, tmp_path):
    a = lib.add_palette("Red", ["#B01010"])
    b = lib.add_palette("Silk Blue", ["#1030C0"])
    arr = np.zeros((40, 40, 4), np.uint8)
    arr[4:36, 4:36] = (150, 150, 150, 255)
    Image.fromarray(arr, "RGBA").save(tmp_path / "plain.png")
    ans = _first_answers("Hats")
    t, at = categories.evaluate_answers("Hats", ans)
    hat = lib.add_item(tmp_path / "plain.png", "Plain Hat", "Hats", ans, t, at)
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    info: dict = {}
    out = np.array(ch.render_piece(hat, [a, b], None, {}, info_out=info, auto_pattern=False)[0])
    assert not info.get("pattern") and (0x10, 0x30, 0xC0) not in {tuple(px) for px in out[out[..., 3] > 0][:, :3]}
    shine: list = []
    ch.render_piece(hat, [a, b], None, {}, shine_out=shine, shine="none")
    assert shine == [[]]
    shine = []
    ch.render_piece(hat, [a, b], None, {}, shine_out=shine, shine=("metallic", 0))
    assert shine[0] and shine[0][0][1] == "metallic"
    entry, = ch.build_wardrobe(item_ids=[], plan=[{"item": hat, "palettes": [a], "pattern": None, "score": 70,
                                                   "shine": ("metallic", 0), "custom": True, "lock": True}])
    assert entry["custom"] and entry["shine"] == ["metallic"] and entry["id"] in ch.data["dresser"]


def test_similar_texture_is_not_the_piece(lib, tmp_path):
    """The character's own hair looks like a hair-made capelet, but only the capelet texture matches."""
    from ultimate_outfitter.core import vrm_match
    pal = lib.add_palette("Brown", ["#5A3A20", "#8A6040", "#C09070"])
    ans = _first_answers("Capes/Cloaks") if "Capes/Cloaks" in categories.CATEGORY_BY_NAME else _first_answers("Shirts")
    cat = "Capes/Cloaks" if "Capes/Cloaks" in categories.CATEGORY_BY_NAME else "Shirts"
    t, a = categories.evaluate_answers(cat, ans)
    cape = lib.add_item(_garment(tmp_path / "cape.png", color=(140, 100, 70)), "Capelet", cat, ans, t, a)
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    entry, = ch.build_wardrobe(item_ids=[], plan=[{"item": cape, "score": 80, "palettes": [pal], "pattern": None}])
    exact = Image.open(ch.dir / entry["file"]).convert("RGBA").resize((256, 256), Image.BILINEAR)
    arr = np.array(exact).astype(int)
    arr[..., :3] = np.clip(arr[..., :3] + 9, 0, 255)          # the hair: same layout, slightly different colour
    similar = Image.fromarray(arr.astype(np.uint8), "RGBA")
    vrm = tmp_path / "hair.vrm"
    _write_glb(vrm, [("N00_000_Hair_00_HAIR", similar), ("N00_005_Hair_01_HAIR_Capelet", exact)])
    found = vrm_match.match_wardrobe(ch, vrm)
    assert [m["material"] for m in found] == ["N00_005_Hair_01_HAIR_Capelet"]


def test_switch_never_replaces_approved_pieces(lib, tmp_path):
    ch = _wardrobe_char(lib, tmp_path, ["Underwear Bottoms", "Bras", "Shoes", "Dresses", "Shirts", "Skirts"])
    s = OutfitSession(ch, DayContext("Casual / errands", "Calm", "Warm"))
    s.build()
    s._drop_group(["full_body"])
    s.proposal["base_top"] = [next(e["id"] for e in s.dresser_entries() if e["slot"] == "base_top")]
    s.proposal["legs"] = [next(e["id"] for e in s.dresser_entries() if e["slot"] == "legs")]
    bottoms = s.proposal["legs"][0]
    s.approve(bottoms)
    # the only top is rejected, but the approved bottoms keep the outfit a top + bottoms
    assert s.reject(s.proposal["base_top"][0], "style") is None
    assert s.proposal["legs"] == [bottoms] and not s.proposal.get("full_body")
    # the shop still offers dresses for the missing top - buying one is the user's choice
    assert "full_body" in s.shop_targets("base_top") and "full_body" not in s.shop_targets("legs")


def test_hidden_parts_file(lib, tmp_path):
    from ultimate_outfitter.core import hidden_parts
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    outfit = {"id": "abc123", "date": "2026-10-11 09:00", "pieces": [], "removed": []}
    matches = [{"material": "Tops_01_CLOTH", "entry_id": "shirt", "item_name": "Shirt"},
               {"material": "HairBack_00_HAIR", "entry_id": "cape", "item_name": "Capelet"},
               {"material": "Cape_CLOTH", "entry_id": "cape", "item_name": "Capelet"}]
    assert hidden_parts.reconcile(ch, outfit, matches) == []
    assert not hidden_parts.path_for(ch, outfit).exists()
    # the capelet is taken off: both its parts are hidden and listed in the file
    outfit["removed"] = [{"entry_id": "cape", "name": "Capelet"}]
    assert hidden_parts.reconcile(ch, outfit, matches) == ["HairBack_00_HAIR", "Cape_CLOTH"]
    path = hidden_parts.path_for(ch, outfit)
    assert "Capelet" in path.read_text(encoding="utf-8")
    # the user deletes a wrong line: that part stays shown, even after another update
    text = path.read_text(encoding="utf-8").replace("HairBack_00_HAIR", "# removed by me")
    path.write_text(text, encoding="utf-8")
    assert hidden_parts.reconcile(ch, outfit, matches) == ["Cape_CLOTH"]
    # taking the shirt off too only adds the shirt's part
    outfit["removed"].append({"entry_id": "shirt", "name": "Shirt"})
    assert hidden_parts.reconcile(ch, outfit, matches) == ["Cape_CLOTH", "Tops_01_CLOTH"]
    # putting the capelet back on shows it again; unknown matches (None) just read the file
    outfit["removed"] = [{"entry_id": "shirt", "name": "Shirt"}]
    assert hidden_parts.reconcile(ch, outfit, matches) == ["Tops_01_CLOTH"]
    assert hidden_parts.reconcile(ch, outfit, None) == ["Tops_01_CLOTH"]


def test_overdressed_character_removes_least_suitable_first(lib, tmp_path):
    import random
    from ultimate_outfitter.core.interact import Conversation
    cats = ["Underwear Bottoms", "Bras", "Shirts", "Pants", "Shoes", "Jackets", "Scarves"]
    cats = [c for c in cats if c in categories.CATEGORY_BY_NAME]
    ch = _wardrobe_char(lib, tmp_path, cats)
    s = OutfitSession(ch, DayContext("Casual / errands", "Calm", "Cold"))
    s.build(allow_incomplete=True)
    w = ch.data["wardrobe"]
    jacket = next(e["id"] for e in s.dresser_entries() if e["slot"] == "outer")
    s.proposal["outer"] = [jacket]
    for e in s.in_use():
        s.approve(e)
    outfit = s.finalize()
    by_slot = {p["slot"]: p["entry_id"] for p in outfit["pieces"]}
    attrs = {sl: lib.items[w[eid]["item_id"]]["attrs"] for sl, eid in by_slot.items()}
    for a in attrs.values():
        a["formality"], a["activities"] = 1, ["Lounging at home"]
    attrs["outer"]["formality"] = 4          # a very formal jacket
    attrs["base_top"]["formality"] = 3       # a fairly formal shirt
    conv = Conversation(ch, "Sam", random.Random(5))
    conv.state.update(activity="Lounging at home", weather="Mild", setting="Private / at home")
    assert "formal" in {i for i, _ in conv.outfit_issues()}
    ranked = conv.removal_candidates(allow_regret=False)
    assert ranked[0][1] == by_slot["outer"] and ranked[0][2] == "formal"
    assert all(eid not in (by_slot["bra"], by_slot["underwear_bottom"]) for _, eid, _ in ranked)
    # refused: the next request is about a different part
    r = conv.propose_removal(allow_regret=False)
    assert r.proposal["remove"] == [by_slot["outer"]]
    conv.answer_proposal(False)
    nxt = conv.removal_candidate(allow_regret=False)
    assert nxt and nxt[0] != by_slot["outer"]


def test_print_never_repeats_the_colour_beneath(lib, tmp_path):
    from ultimate_outfitter.core.imaging import avoid_same_colors
    pal = ["#FFFFFF", "#808080", "#000000"]
    before = np.zeros((4, 4, 4), np.uint8)
    before[..., :3] = (128, 128, 128)
    before[2:, :, :3] = (0, 0, 0)            # bottom half is black
    before[..., 3] = 255
    out = before.copy()
    out[:, :2, :3] = (128, 128, 128)        # print says grey everywhere on the left
    coverage = np.zeros((4, 4), bool)
    coverage[:, :2] = True
    res = avoid_same_colors(out, before, coverage, pal)
    # on grey the grey print becomes another palette colour; on black, grey is fine
    assert (res[:2, :2, :3] != (128, 128, 128)).any(axis=-1).all()
    assert tuple(res[:2, 0, :3][0]) in {(255, 255, 255), (0, 0, 0)}
    assert (res[2:, :2, :3] == (128, 128, 128)).all()
    assert (res[:, 2:] == before[:, 2:]).all()      # outside the print nothing changes


def test_print_scale_varies_but_is_stable(lib, tmp_path):
    greys = lib.add_palette("Greys", ["#F0F0F0", "#808080", "#202020"])
    arr = np.zeros((48, 48, 4), np.uint8)
    arr[4:44, 4:44] = (128, 128, 128, 255)
    Image.fromarray(arr, "RGBA").save(tmp_path / "base.png")
    dots = np.zeros((16, 16, 4), np.uint8)
    dots[4:12, 4:12] = (0, 0, 0, 255)
    Image.fromarray(dots, "RGBA").save(tmp_path / "dots.png")
    pat = lib.add_pattern(tmp_path / "dots.png", "Dots", {}, {}, {"repeats": 4}, cutaway="alpha")
    ans = _first_answers("Shirts")
    t, a = categories.evaluate_answers("Shirts", ans)
    shirt = lib.add_item(tmp_path / "base.png", "Tee", "Shirts", ans, t, a)
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    one = ch.render_piece(shirt, [greys], pat, {})[0]
    assert (one == ch.render_piece(shirt, [greys], pat, {})[0]).all()     # same piece -> same print
    small = ch.render_piece(shirt, [greys], pat, {}, print_scale=0.5)[0]
    big = ch.render_piece(shirt, [greys], pat, {}, print_scale=2.0)[0]
    assert (small != big).any()
    # the grey shirt never gets grey dots: printed pixels inside the shirt are not the base grey
    body = arr[..., 3] > 0
    assert ((big[..., :3] != (128, 128, 128)).any(axis=-1) & body).any()


def test_add_to_wardrobe_plans_another_batch(lib, tmp_path):
    for name, col in (("Teal", "#108080"), ("Sun", "#F0C020"), ("Ink", "#202040"), ("Rose", "#E07090")):
        lib.add_palette(name, [col])
    ch = _wardrobe_char(lib, tmp_path, ["Shirts", "Shirts", "Pants", "Shoes"])
    ch.scan_palettes(0, 0.0)                              # accept every palette
    before = set(ch.existing_combos())
    assert ch.plan_wardrobe() == [] or len(ch.plan_wardrobe()) < len(ch.plan_wardrobe(extra=True))
    extra = ch.plan_wardrobe(extra=True)
    assert extra
    keys = {ch._key(p["item"]["id"], [q["id"] for q in p["palettes"]], p["pattern"]["id"] if p["pattern"] else None)
            for p in extra}
    assert not keys & before                               # never an exact duplicate
    n = len(ch.data["wardrobe"])
    ch.build_wardrobe(plan=extra)
    assert len(ch.data["wardrobe"]) == n + len(extra)


def test_pattern_colour_and_material_options(lib, tmp_path):
    greys = lib.add_palette("Greys", ["#F0F0F0", "#808080", "#202020"])
    arr = np.zeros((48, 48, 4), np.uint8)
    arr[4:44, 4:44] = (128, 128, 128, 255)
    Image.fromarray(arr, "RGBA").save(tmp_path / "base.png")
    grad = np.zeros((32, 32, 4), np.uint8)
    grad[..., 3] = 255
    grad[..., 0] = np.linspace(0, 255, 32, dtype=np.uint8)[None, :]     # a red gradient
    Image.fromarray(grad, "RGBA").save(tmp_path / "grad.png")
    ans = _first_answers("Shirts")
    t, a = categories.evaluate_answers("Shirts", ans)
    shirt = lib.add_item(tmp_path / "base.png", "Tee", "Shirts", ans, t, a)
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    body = arr[..., 3] > 0
    exact_cols = {(0xF0, 0xF0, 0xF0), (0x80, 0x80, 0x80), (0x20, 0x20, 0x20)}

    def render(**attrs):
        pat = lib.add_pattern(tmp_path / "grad.png", f"Grad-{len(lib.patterns)}", {}, {},
                              {"repeats": 2, "placement": "whole", **attrs})
        shine: list = []
        out = ch.render_piece(shirt, [greys], pat, {}, shine_out=shine, print_scale=1.0)[0]
        return {tuple(px) for px in out[body][:, :3]}, shine

    exact, _ = render()
    assert exact <= exact_cols                              # locked: only the palette's exact colours
    smooth, _ = render(colors="smooth")
    assert len(smooth - exact_cols) > 3                     # a gradient between the palette colours
    own, _ = render(colors="own")
    assert any(r > g + 40 for r, g, b in own)               # keeps the pattern's own red
    _, shine = render(material="silk")
    assert shine[0] and shine[0][0][1] == "silk" and shine[0][0][0].any()


def test_opaque_textures_are_coloured_everywhere(lib, tmp_path):
    """Full-canvas textures (no transparency): the border colour is part of the garment, not background."""
    from ultimate_outfitter.core.imaging import auto_mask
    pink = np.zeros((64, 128, 4), np.uint8)
    pink[..., :3] = (255, 0, 128)
    pink[56:, :, :3] = (0, 140, 30)          # a green hem along the bottom
    pink[..., 3] = 255
    assert auto_mask(pink).all()
    Image.fromarray(pink, "RGBA").save(tmp_path / "skirt.png")
    a = lib.add_palette("Navy", ["#101840"])
    b = lib.add_palette("Gold", ["#C09030"])
    ans = _first_answers("Skirts")
    t, at = categories.evaluate_answers("Skirts", ans)
    skirt = lib.add_item(tmp_path / "skirt.png", "Skirt", "Skirts", ans, t, at)
    ch = _wardrobe_char(lib, tmp_path, [], build=False)
    out = ch.render_piece(skirt, [a, b], None, {}, auto_pattern=False)[0]
    body, hem = out[:50, :, :3].reshape(-1, 3), out[58:, :, :3].reshape(-1, 3)
    assert not (body == (255, 0, 128)).all(axis=1).any()      # the pink body was recoloured too
    assert {tuple(px) for px in body} | {tuple(px) for px in hem} <= {(0x10, 0x18, 0x40), (0xC0, 0x90, 0x30)}
    assert {tuple(px) for px in body} != {tuple(px) for px in hem}   # body and hem got different palettes


def test_pixel_paint_and_inner_outline():
    from ultimate_outfitter.core import imaging as im
    img = np.zeros((6, 8, 4), np.uint8)
    pts = im.mirror_points(im.line_points(0, 1, 2, 1), 8, 6, "x")
    hit = im.paint_pixels(img, pts, 1, (255, 0, 0, 255))
    assert hit.sum() == 6                                    # 3 pixels + their mirror images, nothing else
    assert (img[1, 0:3, 0] == 255).all() and (img[1, 5:8, 0] == 255).all() and img[1, 3:5, 0].sum() == 0
    assert set(np.unique(img[..., 0])) <= {0, 255}           # no antialiasing
    assert len(im.brush_offsets(1)) == 1 and len(im.brush_offsets(4)) > 9
    # outline on the inside edge, thickness 1 / 2, and omitting the bottom end of each shape
    sel = np.zeros((10, 14), bool)
    sel[1:9, 1:6] = True
    sel[1:9, 8:13] = True                                    # two separate shapes (e.g. two sleeves)
    one = im.inner_outline(sel)
    assert not (one & ~sel).any() and one[1, 1] and not one[4, 3]
    two = im.inner_outline(sel, 2)
    assert two[2, 2] and not two[4, 3]
    open_end = im.inner_outline(sel, 1, {"bottom": 2})
    assert not open_end[7:9].any() and open_end[6, 1] and open_end[6, 8]   # both shapes lose their bottoms
    assert open_end[1].any()
