# Ultimate Outfitter

A Windows desktop app (`UltimateOutfitter.exe`) for building character wardrobes from your own clothing, palette and pattern images.

| Tab | What it does |
|---|---|
| **A. Collection** | Inventory of clothing items, colour palettes and patterns. |
| **B. Image Editor** | Select by colour, hue or connected region and recolour with palettes or apply masked patterns. |
| **C. Wardrobe Creator** | Character profiles, palette scan and automatic recoloured wardrobe generation. |
| **D. Outfit Manager** | Dresser / hamper, daily outfit picking with approve / reject feedback and laundry. |
| **E. Upscaler** | Upscale pixelated textures without visible pixel steps. |
| **F. Interact** | Chat with a character, who reacts to their mood, activity, setting and outfit. |

## Getting the .exe

* **From GitHub Actions:** every push runs the *Build Windows exe* workflow. Open the run and download the
  `UltimateOutfitter-windows` artifact, which contains `UltimateOutfitter.exe`. Pushing a tag like `v1.0.0` also
  attaches the exe to a GitHub release.
* **Build it yourself on Windows:** install Python 3.10+ and double-click `build_exe.bat`. The exe is written to
  `dist\UltimateOutfitter.exe`.
* **Run from source (any OS):** `pip install -r requirements.txt` then `python run_ultimate_outfitter.py`.

The exe is a single portable file and needs no installation.

## Where data is stored

By default it goes in `Documents\UltimateOutfitterData`. You can change this with *File → Change library folder…*.

```
UltimateOutfitterData/
  library.json           items (answers, traits, attributes), palettes, patterns
  Items/ Palettes/ Patterns/
  Edited/ Upscaled/      default save locations for edited / upscaled images
  Characters/<Name>/
    profile.json         questionnaire, traits, palette scan, wardrobe, dresser, hamper, outfits
    <Name>.png           the character image
    Wardrobe/<Name>-<Item>-<Palette>.png   generated pieces (combos use Palette1+Palette2)
    Outfits/Outfit-<date>.png              contact sheet of each approved outfit
```

The app never overwrites files it creates automatically. If a name is taken, it saves `name (2).png`, `name (3).png` and so on.

## A. Collection inventory

* **Clothing items:** click *Add item(s)…* and pick one or more images. For each one, choose the category and answer
  that category's questions (for example the cut, padding and material of a bra, or the heel height of boots). The
  questions are followed by a short general block covering colour impression, formality, setting, weather and activities. The dialog shows live
  which **personality traits** are most likely to favour the item. It also records the item's warmth, formality and
  activities for the outfit manager.
  * There are 47 categories: all the ones requested plus Jumpsuits/Rompers/Overalls, Pajamas/Sleepwear, Leggings/Tights,
    Leg Warmers, Hair Accessories, Masks/Face Accessories, Bags/Purses, Harnesses/Garters and Costume Extras
    (ears, tails, wings).
  * **Several images per item:** use *Add one item from several images…*, or *Add image…* in the item dialog,
    for front and back views or separate parts. Whenever an item is recoloured or printed automatically, every
    image of it gets exactly the same treatment, and the files are saved as `…-2.png`, `…-3.png` and so on.
  * A question on each item says whether it can carry a print (never, the main fabric, or the whole item).
  * **Copy from an existing item:** select an item and click *Copy selected as new item…*. You can also use the
    *copy answers from an existing item* drop-down in the dialog. All answers are pre-filled, so you only change what differs.
* **Palettes:** *Upload palette image(s)…* extracts colours from the image and lets you edit them before saving.
  * **Exact pixel colours (precise)**, the default, keeps the true HEX values found in the image. Nothing is averaged.
    *Merge ΔE* folds near-identical colours into the more common one. At 0, every distinct colour is kept, up to 256.
  * **Dominant colours** averages similar pixels into clusters instead.
  * *Ignore background* skips the image's background colour. Transparent pixels are always skipped, and *Re-extract*
    re-runs the extraction with new settings. *New from colour wheel…* opens an HSV wheel with H/S/V, R/G/B and HEX inputs. Palettes can be
  *varied hues* or *shades of one colour*, and *Generate shades* builds a shade ramp whose hue drifts slightly.
* **Patterns:** upload any image, then answer a few questions about it: the kind of pattern, how bold it is, its
  scale, formality, setting, which kinds of items it suits, and whether it goes on the main fabric or the whole
  item. The wardrobe creator uses these answers to put suitable prints on suitable pieces.
  * **Cutaway:** a pattern can cut holes in the garment, for lace, mesh or fishnet. Either the pattern's own
    transparency is used, or a separate black/white mask (black = cut away).

## B. Image editor

* **Selection tools:** magic wand (connected colour), select colour (whole image), select hue (whole image or
  connected), rectangle, and brush (right-drag erases). Modes are replace, add (Shift), subtract (Alt) and intersect.
  You can also use *All*, *None*, *Invert*, *Subject* (auto foreground), *Grow* and *Shrink*.
* **Recolour:** apply a palette to the selection, either by region matching (keeps shading, optional second palette)
  or as a gradient map. Click a single swatch to tint the selection with that colour.
* **Patterns:** patterns are masked to the selection. You can tile them, scale them with antialiasing on or off, offset them,
  recolour them with a palette, choose a blend mode (keep shading, replace or multiply) and set the opacity.
* The pattern's **cutaway** can be switched on or off when applying it. *Erase texture* also restores
  cut-away pixels.
* **Erase texture** restores the original pixels inside the selection. Undo, redo and *Revert all* are available.
* **Save (overwrite)** replaces the original file. **Save as new…** writes a new file.

## C. Character wardrobe creator

1. Click *New character…*, choose the character image, answer the personality questions and set preferences
   (whether they wear bras, whether underwear and bras also count as swimwear, which categories they wear, and the
   maximum number of accessories).
2. **Palette scan:** the app samples the colours of **all** the character's reference images (add more with
   *Add reference image…*) and finds every saved palette whose colours appear in
   the character. *Precision* ranges from loose (similar colours) to exact: at 100 a palette colour must match a
   real pixel colour within ΔE 0.5. The scan checks both the character's averaged colours and its exact pixel colours. *Min. palette coverage*
   sets how many of a palette's colours must be found. You can untick a matched palette to leave it out.
3. **Build wardrobe:** every item is rated against the character's personality. The build then picks a realistic,
   random selection, the way a real person's closet looks:
   * each outfit slot gets roughly what an average person owns, about 10 tops, 7 bottoms, 4 pairs of shoes and
     7 pairs of underwear, scaled by **Wardrobe size** (minimalist to hoarder);
   * better-matching items are more likely to be picked (**Best-match item bias**), and only great matches get
     several versions (**Max versions per item**);
   * most pieces use one palette, usually a favourite (**Favourite-palette bias**). A few mix two or three palettes
     (**Two-/Three-palette pieces**), and some get a suitable print (**Printed pieces**, **Allowed patterns**);
   * a stored **Random seed** keeps builds repeatable. Click *New random seed* for a different selection.
     *Exhaustive* restores the old every-item-in-every-palette behaviour;
   * a preview lists what will be made before anything is generated. *Clear wardrobe…* removes everything so you
     can rebuild.

   **Metallic and silk shine:** if a palette's name contains *Metallic* (or *Metal* / *Chrome*) or *Silk* (or
   *Satin*), the parts of each piece coloured with that palette get a shine. Metallic is high-contrast with
   bright, sharp highlights; silk is a soft sheen. The app builds a mask of exactly the pixels that palette
   coloured, so in `Hat-MetallicGreen+Purple` only the MetallicGreen parts shine and the Purple parts stay matte.
   If no palette asks for it but the item's own name does (e.g. "Silk Scarf"), the item's main palette shines.
   The masks are saved in `Wardrobe/Masks/`. The Image Editor applies the same rule when you recolour with such a
   palette, and *Add shine to selection* adds a shine by hand.

   When colouring automatically, the app never touches pixels below 10% opacity, which leaves leftover
   cleanup specks alone. With a **shades of one colour** palette, the most neutral (middle) shade becomes the
   main colour, and the lighter and darker shades are used for highlights, shading and details.

   Files are saved as `Characters/<Name>/Wardrobe/<Name>-<Item>-<Palette>.png` and added to the dresser.
4. **Scan for new clothing items** processes only the items added since the last build. Each suitable new
   item gets one version, and great matches sometimes get two. *Build / update* skips
   any item and palette combination that already exists.

Profiles are saved automatically and reopen with the app. *Open profile file…* reopens a `profile.json`.

## D. Outfit manager

* Click *Plan today's outfit…*. Activity, mood, weather, setting and dress code start on random choices, and you
  can change any of them. The questions are: activity, mood, weather, setting (public, private / at
  home, or beach / pool) and dress code. In a private or beach / pool setting you can tick *Limit the outfit to
  underwear only*. The outfit is then just underwear (plus a bra if the character wears one), with a few optional
  extras such as jewellery, socks at home, or sandals and sunglasses at the beach.
* Underwear can be picked as a swimsuit bottom and a bra as a swimsuit top, unless that is switched off in the
  character profile. Real swimwear is still preferred when it is available. The app picks a complete
  outfit from the **dresser**: underwear, a top with bottoms or a full-body garment, footwear, layers as the weather
  needs, and accessories. It scores each piece on personality match, activity, formality, warmth, mood and colour harmony
  with the other pieces.
* **Approve** or **Reject** each piece. When you reject a piece you give a reason:
  * *Clashing colours:* the next pick avoids that palette and prefers palettes already in the outfit.
  * *Not necessary:* the piece is removed and **not** replaced.
  * *Overlaps:* the next pick comes from a different category.
  * *Weather / activity / formality:* that criterion gets more weight for the next pick.
  * *Style:* that item is excluded in every colourway.
* When every piece is approved, *Wear this outfit* saves it as the current outfit, keeps a history entry and contact sheet, and
  moves the pieces from the dresser to the **hamper**.
* If needed pieces are in the hamper, the app offers to **do laundry**, which moves everything back to the dresser.
  You can also choose *Wear what's available* to go without those pieces. There is also a *Do laundry* button.
* If the character simply doesn't own something (e.g. no tops, shoes or swimwear), laundry wouldn't help. The app
  then does its best with what exists, even if that's only underwear, and lists the missing parts above the outfit.
  Complete outfits are always preferred when possible.

## F. Interact

Pick a character to see them in a large **3D viewport** and chat with them. Planning a new outfit of the day in
the Outfit Manager copies its answers (mood, activity, setting and weather) into the Interact tab and starts a
fresh chat.

### 3D viewport (VRoid)

* **Set VRoid model for this outfit…** loads a `.vrm` exported from VRoid Studio that shows the character in the
  current outfit. The file is copied to `Characters/<Name>/Models/`. Outfits without a model of their own use the
  last model loaded. *Show 2D outfit sheet* switches back to the flat outfit image.
* **Navigation** works like other 3D software: left-drag to orbit, right- or middle-drag to pan, the wheel to zoom,
  and **F** or *Frame* to re-centre the camera on the character.
* **Lighting** follows the weather (sunny, cold, rain with falling rain, snow with snowfall...) and the time of day.
  *Time* can follow the computer's clock or be set to dawn, morning, day, evening or night.
* **Background:** a sky that matches the time and weather, a solid colour, or any image.
* **Expressions** follow the character's mood, and the chat adds short reactions such as laughing, blushing or
  embarrassment. The eyes keep looking at the camera (you can turn this off), and the character blinks on their own.
* **Expressions config:** each character folder has an editable `expressions.txt`, which maps every mood and
  reaction to blend shapes and weights. You can use VRM expressions (`happy`, `sad`, `angry`, `relaxed`,
  `surprised`, `blink`, `aa`...) or raw VRoid blend shapes (`Fcl_ALL_Joy`, `Fcl_EYE_Close`...). Use *Edit
  expressions…* to change it, and *List model blend shapes* to see the names your model supports.

### Animations

Raw **.fbx** animations go in the library's `Animations` folder (button *Animations folder*). Mixamo
animations ("FBX Binary, Without Skin") are retargeted onto the VRoid model automatically. The file name decides
when each one plays:

* `idle_*.fbx` loops depending on the situation, e.g. `idle.fbx`, `idle_happy.fbx`, `idle_beach_hot.fbx`,
  `idle_shy.fbx`.
* `pose_*.fbx` is picked from the *Pose* menu, or used automatically for a matching situation.
* `emote_<event>*.fbx` plays once as a chat reaction, e.g. `emote_wave.fbx`, `emote_laugh_shy.fbx`,
  `emote_embarrassed_public.fbx`.

All valid names (activities, moods, settings, weather, personalities and emote events) are listed in the
`README.md` the app writes into that folder, also available as [docs/ANIMATIONS.md](docs/ANIMATIONS.md).

The 3D view is built with three.js and @pixiv/three-vrm. Its source is in `viewer_src/`; rebuild the bundle with
`npm install && npm run build`.

### Chat There is no AI model involved. Replies are
built "madlibs"-style from a library of sentence templates with placeholders such as `{name}`, `{player}`,
`{mood}`, `{doing}`, `{where}`, `{item}`, `{color}` and `{trait}`. Each personality has its own voice: cheerful,
shy, confident, edgy, elegant, flirty, mysterious or laid-back, chosen from the character's traits and mood.

* **Talk buttons:** greet, ask how they are, what they're doing or wearing, compliment or tease the outfit,
  compliment them, ask their favourite colour, ask about them, tell a joke, flirt, comfort, annoy, say goodbye.
  You can also type simple sentences, which are matched by keywords. Suggestions such as "go to bed" or
  "let's go to the beach" become activity or setting suggestions.
* **Suggest / change:** suggest an activity or a different setting. The character may accept or refuse, depending
  on their personality and how they feel about you. You can also set their mood, or change the weather.
* **Outfit awareness:** the character notices when the outfit doesn't suit what they're doing. That includes
  underwear in public, being too cold or too warm, overdressed or too casual, or wrong for the activity. They react
  in character: shy ones get embarrassed, others get frustrated, shrug it off, joke, or tease you.
* **Let them talk:** the character takes the initiative. They may change their own plans or mood, comment on their
  outfit, share something, or ask you a question.

## E. Upscaler

| Method | Result |
|---|---|
| Smooth shapes – no antialiasing | Outlines of every colour area are rounded and hard edges are kept. No new colours are added. |
| Smooth shapes – antialiased | The same contours with antialiased edges. |
| Smooth shapes + in-between colours | Every colour change becomes a short gradient. *Blend width* sets how wide. |
| Scale2x / EPX | Classic pixel-art scaling, for comparison. |

A Scale2x pre-pass keeps one-pixel diagonal lines connected. *Shape smoothing* sets how round the shapes become.

## Development

```
pip install -r requirements.txt pytest
python -m pytest -q tests
```

The core logic lives in `ultimate_outfitter/core` and doesn't depend on Qt. The PySide6 interface is in `ultimate_outfitter/ui`.
