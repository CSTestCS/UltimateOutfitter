"""Clothing categories, outfit slots and category-specific questionnaires.

Every category owns a list of questions. Each answer option carries trait weights
(which personalities favour an item with that property) and optional attributes
(warmth, formality, activities, coverage...) used by the outfit manager.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Small DSL
# ---------------------------------------------------------------------------


@dataclass
class Option:
    label: str
    traits: dict[str, float]
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Question:
    id: str
    text: str
    options: list[Option]
    multi: bool = False


def O(label: str, traits: str = "", **attrs: Any) -> Option:
    """Option shorthand. ``traits`` is e.g. "bold:2 elegant" (weight defaults to 1)."""
    parsed: dict[str, float] = {}
    for token in traits.split():
        name, _, weight = token.partition(":")
        parsed[name] = float(weight) if weight else 1.0
    return Option(label, parsed, attrs)


def Q(qid: str, text: str, options: list[Option], multi: bool = False) -> Question:
    return Question(qid, text, options, multi)


# ---------------------------------------------------------------------------
# Activities / weather vocabulary (shared with the outfit manager)
# ---------------------------------------------------------------------------

ACTIVITIES = [
    "Lounging at home", "Casual / errands", "Work / office", "School / studying",
    "Formal event", "Date", "Party / night out", "Workout / sports",
    "Swimming / beach", "Outdoors / adventure", "Combat / battle", "Sleeping",
    "Manual work / crafting", "Ceremony / festival",
]

WEATHER = ["Scorching hot", "Warm", "Mild", "Cool", "Cold", "Freezing / snowy", "Rainy", "Windy"]

# warmth level an outfit should have for each weather (0 = minimal clothing)
WEATHER_WARMTH = {
    "Scorching hot": 0, "Warm": 1, "Mild": 2, "Cool": 3, "Cold": 4,
    "Freezing / snowy": 5, "Rainy": 2, "Windy": 2,
}

# ---------------------------------------------------------------------------
# Outfit slots
# ---------------------------------------------------------------------------

# slot id -> human label
SLOTS: dict[str, str] = {
    "underwear_bottom": "Underwear (bottom)",
    "bra": "Bra",
    "swim_bottom": "Swimsuit bottom",
    "swim_top": "Swimsuit top",
    "swim_full": "One-piece swimsuit",
    "sleepwear": "Sleepwear",
    "base_top": "Top",
    "full_body": "Full-body garment",
    "legs": "Bottoms",
    "legwear": "Leggings / tights",
    "socks": "Socks",
    "mid_layer": "Mid layer",
    "corset": "Corset",
    "outer": "Outerwear",
    "cape": "Cape / cloak",
    "armor": "Armor",
    "apron": "Apron",
    "footwear": "Footwear",
    "head": "Headwear",
    "eyes": "Eyewear",
    "neck": "Neckwear",
    "tie": "Tie",
    "hands": "Gloves",
    "wrists": "Cuffs",
    "arms": "Arm warmers / sleeves",
    "leg_warmers": "Leg warmers",
    "waist": "Belt",
    "jewelry": "Jewelry",
    "bag": "Bag",
    "hair": "Hair accessory",
    "face": "Mask / face accessory",
    "harness": "Harness / garter",
    "extras": "Costume extra",
}

ACCESSORY_SLOTS = {"head", "eyes", "neck", "tie", "hands", "wrists", "arms", "leg_warmers",
                   "waist", "jewelry", "bag", "hair", "face", "harness", "extras", "cape",
                   "apron", "armor", "corset"}

# slots which may hold more than one item at a time
MULTI_SLOTS = {"jewelry": 3}

# ---------------------------------------------------------------------------
# Re-usable question blocks
# ---------------------------------------------------------------------------

FIT = Q("fit", "How does it fit the body?", [
    O("Skin-tight", "flirty:2 confident bold"),
    O("Fitted / tailored", "elegant professional confident"),
    O("Relaxed", "laid_back practical cozy"),
    O("Oversized / baggy", "laid_back:2 cozy edgy reserved"),
])

NECKLINE = Q("neckline", "What is the neckline like?", [
    O("Crew / high round neck", "modest practical minimalist"),
    O("V-neck", "confident flirty"),
    O("Scoop / sweetheart", "romantic cute flirty"),
    O("Off-shoulder / boat neck", "romantic flirty elegant"),
    O("Collared", "professional intellectual traditional"),
    O("Turtleneck / mock neck", "intellectual mysterious elegant modest", dwarmth=1),
    O("Halter", "flirty bold glamorous"),
    O("Square neck", "elegant romantic traditional"),
    O("Plunging", "flirty:2 bold glamorous confident"),
])

SLEEVES = Q("sleeves", "What kind of sleeves does it have?", [
    O("Sleeveless / strappy", "flirty laid_back sporty", dwarmth=-1),
    O("Short sleeves", "practical laid_back cheerful"),
    O("Three-quarter sleeves", "elegant professional"),
    O("Long sleeves", "modest practical", dwarmth=1),
    O("Puffed sleeves", "cute:2 romantic playful"),
    O("Bell / flared sleeves", "romantic magical artistic"),
    O("Cap sleeves", "cute elegant"),
])

LENGTH_BOTTOM = Q("length", "How long is it?", [
    O("Micro / mini", "flirty:2 bold playful", dwarmth=-1),
    O("Above the knee", "cute playful cheerful"),
    O("Knee length", "professional elegant cute"),
    O("Midi (mid-calf)", "elegant romantic modest"),
    O("Maxi / floor length", "elegant regal romantic modest", dwarmth=1),
])

COVERAGE = Q("coverage", "How much skin does it show?", [
    O("Very revealing", "flirty:3 bold:2 confident", coverage=0),
    O("Somewhat revealing", "flirty confident playful", coverage=1),
    O("Balanced", "practical laid_back", coverage=2),
    O("Full coverage / modest", "modest:2 reserved traditional", coverage=3),
])

EMBELLISH = Q("embellish", "What decoration or embellishment does it have?", [
    O("None - plain and clean", "minimalist:2 practical reserved"),
    O("Subtle details (stitching, small buttons)", "elegant professional minimalist"),
    O("Ruffles, bows or frills", "cute:2 romantic playful"),
    O("Lace trim", "romantic elegant flirty"),
    O("Studs, spikes, chains or buckles", "edgy:2 rebellious gothic tough"),
    O("Sequins, rhinestones or metallic", "glamorous:2 bold confident"),
    O("Embroidery or cultural motifs", "traditional:2 artistic elegant"),
    O("Cut-outs or straps", "flirty edgy bold"),
    O("Patches, pins or graphics", "rebellious artistic playful"),
    O("Fringe or tassels", "artistic nature_loving playful"),
])

SURFACE = Q("surface", "What pattern or print does the original show?", [
    O("Solid colour", "minimalist practical"),
    O("Stripes", "playful traditional"),
    O("Plaid / tartan", "traditional intellectual rebellious"),
    O("Florals", "romantic nature_loving cute"),
    O("Polka dots", "cute playful cheerful"),
    O("Animal print", "bold glamorous edgy"),
    O("Geometric / abstract", "artistic edgy"),
    O("Graphic / logo / text", "rebellious playful laid_back"),
    O("Camouflage", "tough adventurous practical"),
    O("Damask / brocade", "regal elegant gothic traditional"),
    O("Hearts, stars or cute motifs", "cute:2 playful"),
    O("Skulls, bats or dark motifs", "gothic:2 edgy rebellious"),
])

COLOR_MOOD = Q("color_mood", "What colour impression does the original give?", [
    O("Dark / black", "gothic mysterious edgy reserved"),
    O("Pastel / soft", "cute romantic cheerful"),
    O("Bright / saturated", "bold cheerful playful"),
    O("Neutral / earthy", "nature_loving practical minimalist"),
    O("Jewel tones", "regal elegant glamorous"),
    O("Metallic / shiny", "glamorous bold"),
    O("Muted / dusty", "intellectual reserved artistic"),
    O("Neon", "bold:2 rebellious playful"),
])

FORMALITY = Q("formality", "How formal is it?", [
    O("Very casual / loungewear", "laid_back:2 cozy", formality=0),
    O("Casual", "laid_back practical", formality=1),
    O("Smart casual", "professional confident", formality=2),
    O("Formal", "elegant:2 professional", formality=3),
    O("Ceremonial / gala", "regal:2 glamorous elegant", formality=4),
])

SETTING = Q("setting", "What setting or genre does it fit best?", [
    O("Modern everyday", "practical laid_back"),
    O("Streetwear / urban", "edgy rebellious confident"),
    O("Fantasy / medieval", "magical:2 traditional adventurous"),
    O("Sci-fi / futuristic", "edgy bold mysterious"),
    O("Historical / vintage", "traditional:2 elegant romantic"),
    O("Gothic / dark", "gothic:2 mysterious"),
    O("Kawaii / fairy-kei", "cute:2 playful cheerful"),
    O("Punk / rock", "rebellious:2 edgy"),
    O("Cottagecore / rustic", "nature_loving:2 cozy romantic"),
    O("Athletic", "sporty:2 practical"),
    O("Business / corporate", "professional:2 intellectual"),
    O("Cultural / traditional dress", "traditional:2 elegant"),
])

WEATHER_Q = Q("weather_fit", "What weather is it suited for?", [
    O("Hot weather only", "", warmth=0),
    O("Warm weather", "", warmth=1),
    O("Mild / any season", "", warmth=2),
    O("Cool weather", "", warmth=3),
    O("Cold weather", "cozy", warmth=4),
    O("Freezing / heavy winter", "cozy practical", warmth=5),
])

PRINT_Q = Q("print", "Can this item be made with a print / pattern?", [
    O("No - always keep it plain", "minimalist", print="none"),
    O("Yes - on the main fabric", "", print="primary"),
    O("Yes - over the whole item", "artistic", print="whole"),
])

NO_PRINT_SLOTS = {"jewelry", "eyes", "armor", "wrists"}

THICKNESS_Q = Q("thickness", "How thick is the fabric?", [
    O("Thin / sheer / lightweight", "flirty romantic", thickness="thin"),
    O("Medium", "practical", thickness="medium"),
    O("Thick / heavy", "cozy modest", thickness="thick", dwarmth=1),
])

# slots without a fabric thickness (hard goods, accessories)
NO_FABRIC_SLOTS = {"jewelry", "eyes", "armor", "wrists", "waist", "bag", "face", "extras", "hair", "footwear"}

ACTIVITY_Q = Q("activities", "Which activities is it suitable for? (choose any)",
               [O(a, "", activities=[a]) for a in ACTIVITIES], multi=True)


def material(*names: str) -> Question:
    table = {
        "cotton": O("Cotton / jersey", "practical laid_back"),
        "denim": O("Denim", "laid_back rebellious practical"),
        "leather": O("Leather / faux leather", "edgy:2 bold rebellious tough"),
        "latex": O("Latex / vinyl / PVC", "edgy bold:2 flirty gothic"),
        "silk": O("Silk / satin", "elegant glamorous:2 romantic"),
        "lace": O("Lace / sheer mesh", "romantic flirty:2 elegant"),
        "knit": O("Knit / wool", "cozy:2 traditional", dwarmth=1),
        "tech": O("Technical / performance fabric", "sporty:2 practical"),
        "velvet": O("Velvet", "regal gothic glamorous", dwarmth=1),
        "linen": O("Linen", "nature_loving laid_back elegant"),
        "metal": O("Metal / chainmail", "tough:2 traditional"),
        "fur": O("Fur / faux fur", "glamorous cozy regal", dwarmth=2),
        "fleece": O("Fleece / sweatshirt fabric", "cozy laid_back sporty", dwarmth=1),
        "tweed": O("Tweed / wool suiting", "intellectual traditional professional", dwarmth=1),
        "nylon": O("Nylon / spandex", "sporty flirty practical"),
        "chiffon": O("Chiffon / tulle", "romantic cute elegant magical"),
        "canvas": O("Canvas / heavy duty", "practical tough adventurous"),
        "plastic": O("Plastic / acrylic", "playful edgy"),
        "gold": O("Gold-tone metal", "glamorous regal"),
        "silver": O("Silver-tone metal", "elegant minimalist mysterious"),
        "black_metal": O("Black / gunmetal", "gothic edgy"),
        "gems": O("Gemstones / crystals", "glamorous magical regal"),
        "pearls": O("Pearls", "elegant traditional romantic"),
        "natural": O("Wood, beads or natural materials", "nature_loving artistic"),
        "rubber": O("Rubber", "practical"),
        "straw": O("Straw / woven", "nature_loving laid_back cheerful"),
        "suede": O("Suede", "nature_loving traditional adventurous"),
    }
    return Q("material", "What is it mainly made of?", [table[n] for n in names])


def kind(text: str, options: list[Option]) -> Question:
    return Q("kind", text, options)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@dataclass
class Category:
    name: str
    slot: str
    questions: list[Question]
    warmth: int = 2           # default warmth contribution (0-5)
    activities: list[str] = field(default_factory=list)
    general: bool = True      # append the general question block
    weather_q: bool = True    # ask the weather question


GENERAL_BLOCK = [COLOR_MOOD, FORMALITY, SETTING]

CATEGORIES: list[Category] = [
    # ---------------- underwear & swim ----------------
    Category("Underwear Bottoms", "underwear_bottom", [
        kind("What cut is it?", [
            O("Briefs", "practical modest"), O("Boyshorts", "sporty laid_back cute"),
            O("Bikini cut", "laid_back playful"), O("Thong", "flirty:3 bold"),
            O("High-waisted", "cute traditional modest"), O("Boxers / boxer briefs", "laid_back practical"),
            O("Cheeky", "flirty:2 playful"), O("Bloomers", "cute:2 traditional romantic"),
        ]),
        material("cotton", "lace", "silk", "nylon", "tech"),
        EMBELLISH,
    ], warmth=0, weather_q=False),
    Category("Bras", "bra", [
        kind("What type of bra is it?", [
            O("Sports bra", "sporty:2 practical"), O("Bralette", "laid_back romantic cute"),
            O("Push-up", "flirty:2 confident glamorous"), O("Balconette / plunge", "flirty elegant"),
            O("Full coverage", "modest:2 practical"), O("Strapless", "elegant glamorous"),
            O("Bandeau / tube", "playful laid_back"), O("Longline", "elegant romantic"),
        ]),
        Q("padding", "How is it padded or structured?", [
            O("Unlined / soft", "laid_back nature_loving minimalist"),
            O("Lightly lined", "practical modest"),
            O("Padded / moulded", "confident practical"),
            O("Underwire with sheer cups", "flirty romantic"),
        ]),
        material("cotton", "lace", "silk", "nylon", "tech"),
        EMBELLISH,
    ], warmth=0, weather_q=False),
    Category("Swimsuit Bottoms", "swim_bottom", [
        kind("What style of swim bottom is it?", [
            O("Classic bikini", "playful cheerful"), O("High-waisted / retro", "cute traditional romantic"),
            O("String / tie-side", "flirty:2 playful"), O("Cheeky / thong", "flirty:3 bold confident"),
            O("Skirted", "modest cute"), O("Board shorts", "sporty laid_back adventurous"),
            O("Swim boyshorts", "sporty practical modest"),
        ]),
        EMBELLISH, SURFACE,
    ], warmth=0, activities=["Swimming / beach"], weather_q=False),
    Category("Swimsuit Tops", "swim_top", [
        kind("What style of swim top is it?", [
            O("Triangle", "flirty playful"), O("Bandeau", "cute playful"),
            O("Halter", "flirty confident"), O("Underwire / balconette", "glamorous elegant"),
            O("Sporty / racerback", "sporty:2 practical"), O("Tankini", "modest:2 practical"),
            O("Rash guard", "sporty modest adventurous"), O("Off-shoulder ruffle", "cute romantic"),
        ]),
        EMBELLISH, SURFACE,
    ], warmth=0, activities=["Swimming / beach"], weather_q=False),
    Category("One-Piece Swimsuits", "swim_full", [
        kind("What style of one-piece is it?", [
            O("Classic scoop", "practical elegant"), O("Plunging", "flirty:2 glamorous confident"),
            O("Cut-out / monokini", "edgy bold flirty"), O("Athletic racerback", "sporty:2 practical"),
            O("Skirted / retro", "cute modest traditional"), O("Long-sleeve / wetsuit", "sporty adventurous modest"),
            O("High-leg", "bold flirty confident"), O("Belted / structured", "elegant glamorous"),
        ]),
        COVERAGE, EMBELLISH, SURFACE,
    ], warmth=0, activities=["Swimming / beach"], weather_q=False),
    # ---------------- tops ----------------
    Category("Shirts", "base_top", [
        kind("What type of shirt is it?", [
            O("T-shirt", "laid_back practical"), O("Button-up", "professional intellectual"),
            O("Blouse", "elegant romantic"), O("Polo", "sporty professional"),
            O("Crop top", "flirty playful bold"), O("Peasant / tunic", "nature_loving traditional artistic"),
            O("Graphic tee", "playful rebellious artistic"), O("Henley", "laid_back nature_loving"),
            O("Flannel", "laid_back nature_loving practical"), O("Corset-laced top", "romantic flirty"),
        ]),
        NECKLINE, SLEEVES, FIT,
        material("cotton", "silk", "linen", "lace", "denim", "knit", "chiffon"),
        EMBELLISH, SURFACE,
    ]),
    Category("Tanktops", "base_top", [
        kind("What type of tank top is it?", [
            O("Basic tank", "laid_back practical minimalist"), O("Camisole / spaghetti strap", "romantic flirty"),
            O("Racerback", "sporty"), O("Muscle tee", "tough laid_back rebellious"),
            O("Cropped tank", "flirty playful"), O("Ribbed tank", "minimalist laid_back"),
            O("Tube top", "flirty bold playful"), O("Lace-trimmed cami", "romantic elegant"),
        ]),
        FIT, NECKLINE, material("cotton", "silk", "lace", "nylon", "knit"), EMBELLISH, SURFACE,
    ], warmth=1),
    Category("Activewear Tops", "base_top", [
        kind("What type of athletic top is it?", [
            O("Compression shirt", "sporty:2 confident"), O("Running tank", "sporty practical"),
            O("Yoga top", "sporty nature_loving laid_back"), O("Cropped athletic top", "sporty flirty"),
            O("Team jersey", "sporty cheerful bold"), O("Long-sleeve training top", "sporty practical"),
            O("Mesh / vented top", "sporty edgy"),
        ]),
        FIT, SLEEVES, material("tech", "nylon", "cotton"), SURFACE,
    ], activities=["Workout / sports"]),
    Category("Bodysuits", "base_top", [
        kind("What type of bodysuit is it?", [
            O("Long-sleeve bodysuit", "elegant minimalist"), O("Leotard", "sporty artistic"),
            O("Catsuit", "bold:2 confident mysterious"), O("Lace bodysuit", "flirty romantic"),
            O("Thong-back bodysuit", "flirty:2 bold"), O("Tank bodysuit", "laid_back minimalist"),
            O("Superhero suit", "bold confident adventurous"),
        ]),
        NECKLINE, SLEEVES, material("nylon", "lace", "cotton", "latex", "velvet", "tech"), EMBELLISH,
    ]),
    Category("Corsets", "corset", [
        kind("What type of corset is it?", [
            O("Overbust", "elegant romantic flirty"), O("Underbust", "confident edgy"),
            O("Waist cincher", "practical confident"), O("Corset top / bustier", "flirty glamorous"),
            O("Corset vest", "traditional intellectual"),
        ]),
        Q("corset_style", "What style is it?", [
            O("Victorian", "traditional:2 elegant gothic"), O("Steampunk", "artistic adventurous edgy"),
            O("Lingerie", "flirty:2 romantic"), O("Fantasy / armour-like", "tough magical"),
            O("Modern fashion", "confident bold"), O("Folk / dirndl", "traditional nature_loving cute"),
        ]),
        Q("lacing", "How does it close?", [
            O("Back lacing", "traditional romantic"), O("Front lacing", "flirty bold"),
            O("Busk / hooks", "elegant practical"), O("Buckles / straps", "edgy tough"),
            O("Zipper", "practical"),
        ]),
        material("silk", "leather", "velvet", "lace", "cotton", "latex", "tweed"), EMBELLISH,
    ], warmth=1, weather_q=False),
    # ---------------- layers ----------------
    Category("Hoodies", "mid_layer", [
        kind("What type of hoodie is it?", [
            O("Pullover", "laid_back cozy"), O("Zip-up", "practical sporty"),
            O("Cropped hoodie", "flirty playful"), O("Animal-ear / character hood", "cute:2 playful"),
            O("Tech / athletic hoodie", "sporty practical"), O("Long tunic hoodie", "mysterious edgy"),
        ]),
        FIT, Q("print", "Does it have a print?", [
            O("Plain", "minimalist reserved"), O("Small logo", "laid_back sporty"),
            O("Big graphic", "playful rebellious bold"), O("Band / fandom print", "rebellious artistic"),
        ]),
        material("fleece", "cotton", "tech", "knit"), EMBELLISH,
    ], warmth=3),
    Category("Sweaters/Cardigans", "mid_layer", [
        kind("What type of knitwear is it?", [
            O("Pullover sweater", "cozy practical"), O("Cardigan", "intellectual cozy cute"),
            O("Turtleneck sweater", "intellectual mysterious elegant"), O("Cable knit", "cozy traditional nature_loving"),
            O("Cropped sweater", "playful flirty"), O("Off-shoulder sweater", "romantic flirty"),
            O("Oversized chunky knit", "cozy:2 laid_back"), O("Sweater vest", "intellectual cute"),
        ]),
        Q("knit_weight", "How thick is the knit?", [
            O("Fine / thin", "elegant professional", dwarmth=-1), O("Medium", "practical"),
            O("Chunky / heavy", "cozy:2", dwarmth=1),
        ]),
        FIT, material("knit", "cotton", "fur"), EMBELLISH, SURFACE,
    ], warmth=3),
    Category("Vests", "mid_layer", [
        kind("What type of vest is it?", [
            O("Suit waistcoat", "professional elegant traditional intellectual"),
            O("Puffer vest", "practical adventurous sporty"),
            O("Denim / leather biker vest", "rebellious:2 edgy tough"),
            O("Sweater vest", "intellectual cute cozy"),
            O("Utility / tactical vest", "practical tough adventurous"),
            O("Fantasy / tunic vest", "magical traditional adventurous"),
            O("Fur / shearling vest", "glamorous cozy nature_loving"),
        ]),
        FIT, material("tweed", "leather", "denim", "knit", "canvas", "silk", "fur"), EMBELLISH,
    ], warmth=2),
    Category("Blazers", "outer", [
        kind("What cut of blazer is it?", [
            O("Tailored single-breasted", "professional:2 elegant"), O("Double-breasted", "confident professional regal"),
            O("Oversized", "laid_back edgy confident"), O("Cropped", "playful flirty"),
            O("Tuxedo / smoking jacket", "elegant:2 glamorous"), O("Academic / school blazer", "intellectual cute traditional"),
        ]),
        Q("lapel", "What lapels does it have?", [
            O("Notch", "professional practical"), O("Peak", "confident bold"),
            O("Shawl", "elegant glamorous"), O("Collarless", "minimalist edgy"),
        ]),
        material("tweed", "cotton", "velvet", "linen", "silk", "leather"), SURFACE,
    ], warmth=2, activities=["Work / office", "Formal event", "School / studying"]),
    Category("Jackets", "outer", [
        kind("What type of jacket is it?", [
            O("Denim jacket", "laid_back rebellious"), O("Leather biker jacket", "edgy:2 rebellious:2 tough"),
            O("Bomber", "edgy confident laid_back"), O("Windbreaker / track jacket", "sporty practical"),
            O("Puffer", "practical cozy adventurous"), O("Cropped jacket", "playful flirty"),
            O("Military / field jacket", "tough practical adventurous"), O("Varsity jacket", "sporty cheerful playful"),
            O("Fantasy doublet / jerkin", "magical traditional adventurous"), O("Utility / workwear jacket", "practical tough"),
        ]),
        Q("closure", "How does it close?", [
            O("Zipper", "practical sporty"), O("Buttons", "traditional"), O("Snaps", "laid_back"),
            O("Open / no closure", "laid_back confident"), O("Toggles / clasps", "traditional magical"),
        ]),
        FIT, material("denim", "leather", "nylon", "cotton", "canvas", "suede", "velvet"), EMBELLISH,
    ], warmth=3),
    Category("Coats", "outer", [
        kind("What type of coat is it?", [
            O("Trench coat", "mysterious intellectual elegant"), O("Peacoat", "traditional professional"),
            O("Parka", "practical adventurous cozy"), O("Fur coat", "glamorous:2 regal"),
            O("Duster / long coat", "mysterious adventurous edgy"), O("Military greatcoat", "tough traditional regal"),
            O("Wool overcoat", "professional elegant"), O("Raincoat", "practical cheerful"),
            O("Frock / tailcoat", "regal traditional elegant"),
        ]),
        LENGTH_BOTTOM, material("knit", "tweed", "leather", "nylon", "fur", "canvas", "velvet"), EMBELLISH,
    ], warmth=4),
    Category("Capes/Cloaks", "cape", [
        kind("What type of cape or cloak is it?", [
            O("Travelling cloak", "adventurous:2 practical mysterious"),
            O("Regal mantle", "regal:2 glamorous"), O("Superhero cape", "bold confident"),
            O("Capelet", "elegant cute"), O("Poncho", "laid_back nature_loving"),
            O("Mage / ritual cloak", "magical:2 mysterious"),
        ]),
        Q("hood", "Does it have a hood?", [
            O("Deep hood", "mysterious:2 reserved"), O("Small hood", "practical"),
            O("No hood", "confident bold"), O("Fur-trimmed hood", "regal cozy"),
        ]),
        LENGTH_BOTTOM,
        Q("clasp", "What does the clasp look like?", [
            O("Simple tie", "practical minimalist"), O("Ornate brooch", "regal elegant magical"),
            O("Chain", "gothic edgy"), O("No clasp / draped", "laid_back"),
        ]),
        material("velvet", "canvas", "silk", "knit", "fur", "leather"),
    ], warmth=3),
    Category("Robes/Yukatas/Kimonos", "full_body", [
        kind("What type of robe is it?", [
            O("Bathrobe / house robe", "cozy:2 laid_back"), O("Yukata", "traditional cheerful laid_back"),
            O("Formal kimono", "traditional:2 elegant regal"), O("Hanfu", "traditional:2 elegant romantic"),
            O("Wizard / mage robe", "magical:2 intellectual mysterious"), O("Kaftan", "artistic laid_back glamorous"),
            O("Monk / priest robe", "reserved modest traditional"), O("Silk dressing gown", "glamorous elegant flirty"),
            O("Hakama set", "traditional practical tough"),
        ]),
        SLEEVES, LENGTH_BOTTOM, material("silk", "cotton", "linen", "velvet", "fleece", "knit"),
        EMBELLISH, SURFACE,
    ], warmth=2),
    # ---------------- full body ----------------
    Category("Dresses", "full_body", [
        kind("What silhouette is the dress?", [
            O("A-line", "elegant cute"), O("Bodycon", "flirty:2 confident bold"),
            O("Ballgown", "regal:2 glamorous romantic"), O("Sundress", "cheerful nature_loving laid_back"),
            O("Slip dress", "elegant flirty minimalist"), O("Wrap dress", "elegant professional"),
            O("Shirt dress", "practical professional"), O("Babydoll", "cute:2 playful"),
            O("Mermaid", "glamorous flirty"), O("Lolita / petticoat dress", "cute:2 romantic traditional"),
            O("Sweater dress", "cozy laid_back"),
        ]),
        LENGTH_BOTTOM, NECKLINE, SLEEVES,
        material("cotton", "silk", "lace", "velvet", "linen", "chiffon", "knit", "latex"),
        EMBELLISH, SURFACE,
    ], warmth=1),
    Category("Jumpsuits/Rompers/Overalls", "full_body", [
        kind("What type is it?", [
            O("Jumpsuit", "confident elegant"), O("Romper / playsuit", "playful cheerful flirty"),
            O("Overalls / dungarees", "practical cute nature_loving"), O("Boiler suit / coveralls", "practical:2 tough"),
            O("Flight / pilot suit", "adventurous bold"), O("Shortalls", "cute playful"),
        ]),
        FIT, SLEEVES, material("denim", "cotton", "silk", "canvas", "linen"), SURFACE,
    ], warmth=2),
    Category("Pajamas/Sleepwear", "sleepwear", [
        kind("What type of sleepwear is it?", [
            O("Button pajama set", "cozy traditional"), O("Nightgown", "romantic modest"),
            O("Onesie / kigurumi", "cute:2 playful cozy"), O("Babydoll / chemise", "flirty romantic"),
            O("Sleep shirt", "laid_back practical"), O("Shorts & tee set", "laid_back cheerful"),
        ]),
        material("cotton", "silk", "fleece", "lace", "knit"), SURFACE,
    ], warmth=2, activities=["Sleeping", "Lounging at home"]),
    # ---------------- bottoms ----------------
    Category("Pants", "legs", [
        kind("What style of pants are they?", [
            O("Skinny jeans", "confident edgy"), O("Straight jeans", "laid_back practical"),
            O("Wide-leg / palazzo", "elegant artistic"), O("Cargo pants", "practical adventurous tough"),
            O("Dress trousers", "professional:2 elegant"), O("Sweatpants / joggers", "laid_back:2 cozy sporty"),
            O("Leather pants", "edgy:2 bold rebellious"), O("Flares / bell-bottoms", "artistic playful"),
            O("Harem / baggy pants", "laid_back artistic"), O("Ripped jeans", "rebellious laid_back"),
            O("Breeches / riding pants", "traditional adventurous"),
        ]),
        Q("rise", "Where does the waist sit?", [
            O("Low rise", "flirty rebellious"), O("Mid rise", "practical"),
            O("High waisted", "elegant cute traditional"),
        ]),
        FIT, material("denim", "cotton", "leather", "linen", "fleece", "tweed", "canvas", "tech"), EMBELLISH,
    ], warmth=3),
    Category("Shorts", "legs", [
        kind("What style of shorts are they?", [
            O("Denim cutoffs", "laid_back rebellious playful"), O("Bike shorts", "sporty confident"),
            O("Athletic shorts", "sporty practical"), O("Tailored shorts", "professional elegant"),
            O("Cargo shorts", "practical adventurous"), O("High-waisted shorts", "cute playful"),
            O("Hot pants", "flirty:2 bold"), O("Bermuda shorts", "laid_back modest"),
        ]),
        LENGTH_BOTTOM, material("denim", "cotton", "linen", "tech", "leather", "canvas"), SURFACE,
    ], warmth=1),
    Category("Skirts", "legs", [
        kind("What style of skirt is it?", [
            O("Mini skirt", "flirty playful bold"), O("Pencil skirt", "professional elegant"),
            O("Pleated skirt", "cute intellectual"), O("A-line skirt", "elegant cute"),
            O("Tulle / tutu", "cute:2 magical playful"), O("Maxi skirt", "nature_loving romantic modest"),
            O("Wrap skirt", "elegant artistic"), O("Plaid school skirt", "cute rebellious intellectual"),
            O("Ruffled / tiered", "romantic cute"), O("Leather skirt", "edgy bold"),
        ]),
        LENGTH_BOTTOM, material("denim", "cotton", "leather", "silk", "chiffon", "tweed", "linen", "knit"),
        EMBELLISH, SURFACE,
    ], warmth=1),
    Category("Leggings/Tights", "legwear", [
        kind("What type is it?", [
            O("Opaque tights", "practical modest elegant"), O("Sheer pantyhose", "elegant professional flirty"),
            O("Fishnets", "edgy:2 flirty rebellious"), O("Athletic leggings", "sporty:2 practical"),
            O("Fleece-lined leggings", "cozy practical"), O("Patterned tights", "playful artistic cute"),
            O("Ripped tights", "rebellious:2 edgy"),
        ]),
        material("nylon", "cotton", "knit", "tech", "lace"),
    ], warmth=1),
    # ---------------- accessories / wearables ----------------
    Category("Aprons", "apron", [
        kind("What style of apron is it?", [
            O("Kitchen bib apron", "practical cozy"), O("Waist apron", "practical professional"),
            O("Frilly maid apron", "cute:2 romantic"), O("Leather work apron", "practical tough artistic"),
            O("Pinafore", "cute traditional nature_loving"), O("Artist smock", "artistic laid_back"),
        ]),
        material("cotton", "linen", "leather", "lace", "canvas"), EMBELLISH,
    ], activities=["Manual work / crafting"], weather_q=False),
    Category("Armor", "armor", [
        Q("armor_weight", "How heavy is the armour?", [
            O("Light (leather / padded)", "adventurous practical"),
            O("Medium (chain / scale)", "tough practical"),
            O("Heavy plate", "tough:2 regal confident"),
            O("Sci-fi / power armour", "tough bold edgy"),
            O("Ceremonial / decorative", "regal:2 glamorous"),
        ]),
        Q("armor_piece", "What part does it cover?", [
            O("Full set", "tough confident"), O("Chest piece / cuirass", "tough practical"),
            O("Pauldrons / shoulders", "bold confident"), O("Bracers / greaves", "practical adventurous"),
            O("Bikini / fantasy armour", "flirty:2 bold"),
        ]),
        Q("armor_style", "What style is it?", [
            O("Knightly", "traditional regal"), O("Samurai", "traditional tough"),
            O("Barbarian / tribal", "tough nature_loving rebellious"), O("Elven / elegant", "elegant magical"),
            O("Dark / spiked", "gothic edgy tough"), O("Futuristic", "edgy bold"),
        ]),
        EMBELLISH,
    ], warmth=2, activities=["Combat / battle"]),
    Category("Belts", "waist", [
        kind("What type of belt is it?", [
            O("Simple leather belt", "practical minimalist"), O("Statement buckle", "bold confident"),
            O("Studded belt", "edgy:2 rebellious"), O("Chain belt", "glamorous edgy"),
            O("Obi / sash", "traditional elegant"), O("Corset belt", "elegant flirty"),
            O("Utility belt with pouches", "practical adventurous tough"), O("Bow / ribbon belt", "cute romantic"),
        ]),
        Q("width", "How wide is it?", [
            O("Skinny", "elegant minimalist"), O("Standard", "practical"), O("Wide", "bold confident"),
        ]),
        material("leather", "silk", "gold", "silver", "canvas", "suede"),
    ], weather_q=False),
    Category("Jewelry", "jewelry", [
        kind("What type of jewellery is it?", [
            O("Necklace / pendant", "elegant romantic"), O("Earrings", "elegant playful"),
            O("Rings", "confident elegant"), O("Bracelet / bangle", "artistic playful"),
            O("Choker", "edgy gothic flirty"), O("Tiara / circlet", "regal:2 magical"),
            O("Piercing jewellery", "edgy rebellious"), O("Anklet", "laid_back nature_loving flirty"),
            O("Brooch / pin", "traditional intellectual"), O("Amulet / talisman", "magical:2 mysterious"),
        ]),
        Q("size", "How big is it?", [
            O("Dainty / minimal", "minimalist elegant reserved"), O("Medium", "practical"),
            O("Statement / chunky", "bold:2 glamorous confident"),
        ]),
        material("gold", "silver", "black_metal", "gems", "pearls", "natural", "plastic", "leather"),
    ], weather_q=False),
    Category("Scarves/Shawls", "neck", [
        kind("What type is it?", [
            O("Knit scarf", "cozy:2 practical"), O("Silk scarf", "elegant glamorous"),
            O("Infinity scarf", "laid_back practical"), O("Shawl / wrap", "elegant romantic traditional"),
            O("Bandana", "rebellious laid_back adventurous"), O("Pashmina", "elegant professional"),
            O("Fur stole", "glamorous regal"), O("Long flowing scarf", "artistic magical"),
        ]),
        Q("scarf_length", "How long is it?", [
            O("Short", "practical"), O("Medium", "laid_back"), O("Extra long", "artistic bold"),
        ]),
        material("knit", "silk", "cotton", "chiffon", "fur", "lace"), SURFACE,
    ], warmth=3),
    Category("Ties", "tie", [
        kind("What type of tie is it?", [
            O("Necktie", "professional:2"), O("Bow tie", "elegant intellectual playful"),
            O("Bolo tie", "adventurous traditional"), O("Cravat / ascot", "regal traditional elegant"),
            O("Ribbon tie", "cute romantic"), O("Skinny tie", "edgy rebellious"),
            O("School tie", "intellectual cute"),
        ]),
        material("silk", "cotton", "knit", "leather"), SURFACE,
    ], activities=["Work / office", "Formal event", "School / studying"], weather_q=False),
    Category("Gloves", "hands", [
        kind("What type of gloves are they?", [
            O("Fingerless", "edgy rebellious laid_back"), O("Opera / long gloves", "elegant:2 glamorous regal"),
            O("Leather driving gloves", "confident mysterious"), O("Mittens", "cute cozy"),
            O("Lace gloves", "romantic gothic elegant"), O("Combat / tactical", "tough practical"),
            O("Winter knit gloves", "cozy practical"), O("Gauntlets", "tough regal"),
            O("Sport / grip gloves", "sporty practical"),
        ]),
        material("leather", "knit", "lace", "silk", "tech", "metal"),
    ], warmth=2),
    Category("Cuffs", "wrists", [
        kind("What type of cuffs are they?", [
            O("Detached shirt cuffs", "professional cute"), O("Spiked cuffs", "edgy:2 rebellious gothic"),
            O("Leather bracers", "adventurous tough"), O("Ornate metal cuffs", "regal glamorous"),
            O("Lace / frill cuffs", "romantic cute"), O("Wrist wraps", "sporty tough"),
        ]),
        material("leather", "lace", "gold", "silver", "cotton", "black_metal"),
    ], weather_q=False),
    Category("Arm Warmers/Detached Sleeves", "arms", [
        kind("What type are they?", [
            O("Knit arm warmers", "cozy cute"), O("Sheer / lace sleeves", "romantic elegant gothic"),
            O("Striped arm warmers", "playful rebellious"), O("Flowing bell sleeves", "magical:2 romantic"),
            O("Ribbed / tight sleeves", "edgy minimalist"), O("Mesh sleeves", "edgy bold"),
        ]),
        material("knit", "lace", "chiffon", "nylon", "latex"),
    ], warmth=1),
    Category("Leg Warmers", "leg_warmers", [
        kind("What type are they?", [
            O("Knit leg warmers", "cozy cute"), O("Slouchy", "laid_back playful"),
            O("Fluffy / furry", "playful bold"), O("Dance leg warmers", "sporty artistic"),
        ]),
        material("knit", "fur", "cotton"),
    ], warmth=2),
    Category("Socks", "socks", [
        kind("What type of socks are they?", [
            O("Ankle / no-show", "sporty practical minimalist"), O("Crew", "practical laid_back"),
            O("Knee-high", "cute traditional"), O("Thigh-high", "flirty cute bold"),
            O("Fishnet socks", "edgy rebellious"), O("Frilly socks", "cute:2 romantic"),
            O("Toe socks", "playful artistic"), O("Wool hiking socks", "practical adventurous cozy"),
        ]),
        SURFACE, material("cotton", "knit", "nylon", "lace"),
    ], warmth=1, weather_q=False),
    Category("Shoes", "footwear", [
        kind("What type of shoes are they?", [
            O("Sneakers", "laid_back sporty"), O("High heels / pumps", "elegant glamorous confident"),
            O("Flats", "practical cute"), O("Loafers", "intellectual professional"),
            O("Oxfords / brogues", "professional traditional"), O("Platforms", "bold edgy playful"),
            O("Mary Janes", "cute:2 traditional"), O("Slippers", "cozy:2 laid_back"),
            O("Running shoes", "sporty:2 practical"), O("Ballet shoes", "elegant artistic romantic"),
        ]),
        Q("heel", "How high is the heel?", [
            O("Flat", "practical laid_back"), O("Low", "professional"),
            O("Mid", "elegant confident"), O("High / stiletto", "glamorous:2 bold flirty"),
        ]),
        material("leather", "canvas", "suede", "plastic", "silk", "rubber"), EMBELLISH,
    ], warmth=1),
    Category("Boots", "footwear", [
        kind("What type of boots are they?", [
            O("Ankle boots", "practical elegant"), O("Combat boots", "edgy:2 tough rebellious"),
            O("Knee-high boots", "confident elegant"), O("Thigh-high boots", "bold:2 flirty"),
            O("Cowboy boots", "adventurous traditional"), O("Rain boots", "practical cheerful"),
            O("Hiking boots", "adventurous:2 practical nature_loving"), O("Platform boots", "bold gothic rebellious"),
            O("Riding boots", "traditional elegant regal"), O("Fur-lined winter boots", "cozy practical"),
        ]),
        Q("heel", "How high is the heel?", [
            O("Flat", "practical"), O("Chunky", "edgy confident"),
            O("Stiletto", "glamorous flirty bold"), O("Platform", "bold rebellious"),
        ]),
        material("leather", "suede", "rubber", "canvas", "latex", "fur"), EMBELLISH,
    ], warmth=3),
    Category("Sandals", "footwear", [
        kind("What type of sandals are they?", [
            O("Flip-flops", "laid_back:2 cheerful"), O("Gladiator", "bold traditional adventurous"),
            O("Strappy heels", "glamorous flirty elegant"), O("Slides", "laid_back sporty"),
            O("Sport sandals", "practical adventurous"), O("Geta / zori", "traditional:2"),
            O("Wedges", "cheerful elegant"), O("Espadrilles", "nature_loving laid_back"),
        ]),
        material("leather", "rubber", "straw", "plastic", "natural"), EMBELLISH,
    ], warmth=0),
    Category("Glasses", "eyes", [
        kind("What style of glasses are they?", [
            O("Round", "intellectual artistic"), O("Cat-eye", "glamorous playful"),
            O("Aviators", "confident adventurous"), O("Rectangular", "professional intellectual"),
            O("Oversized sunglasses", "glamorous mysterious"), O("Goggles", "adventurous artistic"),
            O("Rimless", "minimalist professional"), O("Monocle", "regal intellectual traditional"),
            O("Heart / novelty", "playful cute"), O("Visor / sci-fi", "edgy bold"),
        ]),
        Q("lens", "What are the lenses like?", [
            O("Clear", "intellectual practical"), O("Dark tinted", "mysterious confident"),
            O("Coloured tint", "playful artistic"), O("Mirrored", "bold edgy"),
        ]),
        material("plastic", "gold", "silver", "black_metal"),
    ], weather_q=False),
    Category("Hats", "head", [
        kind("What type of hat is it?", [
            O("Beanie", "laid_back cozy"), O("Baseball cap", "sporty laid_back"),
            O("Sun hat", "cheerful nature_loving romantic"), O("Fedora", "mysterious confident"),
            O("Beret", "artistic intellectual"), O("Top hat", "regal traditional elegant"),
            O("Witch / wizard hat", "magical:2 mysterious"), O("Bucket hat", "laid_back playful"),
            O("Cowboy hat", "adventurous traditional"), O("Fascinator", "glamorous elegant"),
            O("Newsboy cap", "traditional intellectual"), O("Animal-ear hat", "cute:2 playful"),
        ]),
        material("knit", "cotton", "straw", "velvet", "leather", "canvas", "fur"), EMBELLISH,
    ], warmth=1),
    Category("Helmets", "head", [
        kind("What type of helmet is it?", [
            O("Full knight helm", "tough:2 regal"), O("Open-face helm", "tough adventurous"),
            O("Sci-fi helmet", "edgy bold mysterious"), O("Motorcycle helmet", "rebellious adventurous"),
            O("Horned / viking", "tough rebellious"), O("Plumed / ceremonial", "regal glamorous"),
            O("Sport / bike helmet", "sporty practical"), O("Samurai kabuto", "traditional tough"),
        ]),
        Q("visor", "How much of the face does it cover?", [
            O("Fully covered", "mysterious:2 reserved"), O("Partial", "tough"), O("Open", "confident bold"),
        ]),
        EMBELLISH,
    ], warmth=1, activities=["Combat / battle"], weather_q=False),
    Category("Hair Accessories", "hair", [
        kind("What type of hair accessory is it?", [
            O("Hair bow / ribbon", "cute:2 romantic"), O("Headband", "cute practical"),
            O("Hair clips / pins", "playful cute"), O("Flower crown", "nature_loving romantic magical"),
            O("Kanzashi / hair sticks", "traditional elegant"), O("Scrunchie", "laid_back playful"),
            O("Jewelled comb", "glamorous elegant"), O("Bandana / headscarf", "laid_back rebellious"),
            O("Veil", "romantic mysterious elegant"),
        ]),
        material("silk", "plastic", "gold", "silver", "natural", "lace", "gems"),
    ], weather_q=False),
    Category("Masks/Face Accessories", "face", [
        kind("What type is it?", [
            O("Masquerade mask", "mysterious glamorous romantic"), O("Face veil", "mysterious elegant"),
            O("Gas / respirator mask", "edgy tough"), O("Cloth face mask", "practical reserved"),
            O("Eye patch", "rebellious tough mysterious"), O("Animal / kitsune mask", "magical playful traditional"),
            O("Bandit mask", "rebellious mysterious"),
        ]),
        EMBELLISH,
    ], weather_q=False),
    Category("Bags/Purses", "bag", [
        kind("What type of bag is it?", [
            O("Handbag", "elegant professional"), O("Backpack", "practical adventurous"),
            O("Clutch", "glamorous elegant"), O("Crossbody / satchel", "practical intellectual"),
            O("Tote", "laid_back practical"), O("Fanny pack / belt bag", "sporty laid_back"),
            O("Novelty / character bag", "cute playful"), O("Pouch / adventurer's bag", "adventurous traditional"),
        ]),
        material("leather", "canvas", "cotton", "straw", "plastic", "velvet", "latex"), EMBELLISH,
    ], weather_q=False),
    Category("Harnesses/Garters", "harness", [
        kind("What type is it?", [
            O("Body harness", "edgy:2 bold flirty"), O("Leg garter", "flirty romantic"),
            O("Garter belt", "flirty glamorous traditional"), O("Suspenders", "intellectual traditional playful"),
            O("Utility harness", "practical tough"),
        ]),
        material("leather", "lace", "silk", "canvas"),
    ], weather_q=False),
    Category("Costume Extras (Ears/Tails/Wings)", "extras", [
        kind("What is it?", [
            O("Animal ears", "cute:2 playful"), O("Tail", "playful cute"), O("Wings (feathered)", "magical romantic"),
            O("Wings (bat / demon)", "gothic:2 mysterious"), O("Horns", "edgy bold"),
            O("Halo", "romantic magical"), O("Fairy wings", "magical:2 cute"),
        ]),
        EMBELLISH,
    ], weather_q=False),
]

CATEGORY_BY_NAME: dict[str, Category] = {c.name: c for c in CATEGORIES}
CATEGORY_NAMES = [c.name for c in CATEGORIES]


def questions_for(category: str) -> list[Question]:
    cat = CATEGORY_BY_NAME[category]
    qs = list(cat.questions)
    if cat.general:
        qs += GENERAL_BLOCK
    if cat.weather_q:
        qs.append(WEATHER_Q)
    if cat.slot not in NO_FABRIC_SLOTS:
        qs.append(THICKNESS_Q)
    qs.append(PRINT_Q)
    qs.append(ACTIVITY_Q)
    # de-duplicate ids while preserving order (blocks may be reused)
    seen: set[str] = set()
    out = []
    for q in qs:
        if q.id not in seen:
            seen.add(q.id)
            out.append(q)
    return out


def evaluate_answers(category: str, answers: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    """Turn questionnaire answers into (trait vector, attributes).

    ``answers`` maps question id -> option label (or list of labels for multi questions).
    """
    from .traits import add_into, normalize

    cat = CATEGORY_BY_NAME[category]
    traits: dict[str, float] = {}
    attrs: dict[str, Any] = {
        "warmth": cat.warmth, "formality": 1, "coverage": 2,
        "activities": list(cat.activities),
        "print": "none" if cat.slot in NO_PRINT_SLOTS else "primary",
        "thickness": "medium",
    }
    explicit_warmth = None
    dwarmth = 0
    for q in questions_for(category):
        answer = answers.get(q.id)
        if answer is None:
            continue
        chosen = answer if isinstance(answer, list) else [answer]
        for opt in q.options:
            if opt.label not in chosen:
                continue
            add_into(traits, opt.traits)
            for key, value in opt.attrs.items():
                if key == "activities":
                    for a in value:
                        if a not in attrs["activities"]:
                            attrs["activities"].append(a)
                elif key == "dwarmth":
                    dwarmth += value
                elif key == "warmth":
                    explicit_warmth = value
                else:
                    attrs[key] = value
    warmth = explicit_warmth if explicit_warmth is not None else cat.warmth + dwarmth
    attrs["warmth"] = max(0, min(5, warmth))
    attrs["slot"] = cat.slot
    return normalize(traits), attrs
