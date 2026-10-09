# Ultimate Outfitter

A Windows desktop app (`UltimateOutfitter.exe`) for building character wardrobes from your own clothing, palette and pattern images.

| Tab | What it does |
|---|---|
| **A. Collection** | Inventory of clothing items, colour palettes and patterns. |
| **B. Image Editor** | Select by colour, hue or connected region and recolour with palettes or apply masked patterns. |
| **C. Wardrobe Creator** | Character profiles, palette scan and automatic recoloured wardrobe generation. |
| **D. Outfit Manager** | Dresser / hamper, daily outfit picking with approve / reject feedback and laundry. |
| **E. Upscaler** | Upscale pixelated textures without visible pixel steps. |

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
  * **Copy from an existing item:** select an item and click *Copy selected as new item…*. You can also use the
    *copy answers from an existing item* drop-down in the dialog. All answers are pre-filled, so you only change what differs.
* **Palettes:** *Upload palette image(s)…* extracts colours from the image and lets you edit them before saving.
  * **Exact pixel colours (precise)**, the default, keeps the true HEX values found in the image. Nothing is averaged.
    *Merge ΔE* folds near-identical colours into the more common one. At 0, every distinct colour is kept, up to 256.
  * **Dominant colours** averages similar pixels into clusters instead.
  * *Ignore background* skips the image's background colour. Transparent pixels are always skipped, and *Re-extract*
    re-runs the extraction with new settings. *New from colour wheel…* opens an HSV wheel with H/S/V, R/G/B and HEX inputs. Palettes can be
  *varied hues* or *shades of one colour*, and *Generate shades* builds a shade ramp whose hue drifts slightly.
* **Patterns:** upload any image to use as a pattern in the editor.

## B. Image editor

* **Selection tools:** magic wand (connected colour), select colour (whole image), select hue (whole image or
  connected), rectangle, and brush (right-drag erases). Modes are replace, add (Shift), subtract (Alt) and intersect.
  You can also use *All*, *None*, *Invert*, *Subject* (auto foreground), *Grow* and *Shrink*.
* **Recolour:** apply a palette to the selection, either by region matching (keeps shading, optional second palette)
  or as a gradient map. Click a single swatch to tint the selection with that colour.
* **Patterns:** patterns are masked to the selection. You can tile them, scale them with antialiasing on or off, offset them,
  recolour them with a palette, choose a blend mode (keep shading, replace or multiply) and set the opacity.
* **Erase texture** restores the original pixels inside the selection. Undo, redo and *Revert all* are available.
* **Save (overwrite)** replaces the original file. **Save as new…** writes a new file.

## C. Character wardrobe creator

1. Click *New character…*, choose the character image, answer the personality questions and set preferences
   (whether they wear bras, whether underwear and bras also count as swimwear, which categories they wear, and the
   maximum number of accessories).
2. **Palette scan:** the app samples the character's colours and finds every saved palette whose colours appear in
   the character. *Precision* ranges from loose (similar colours) to exact: at 100 a palette colour must match a
   real pixel colour within ΔE 0.5. The scan checks both the character's averaged colours and its exact pixel colours. *Min. palette coverage*
   sets how many of a palette's colours must be found. You can untick a matched palette to leave it out.
3. **Build wardrobe:** every item is rated against the character's personality, and items are ranked best to worst
   within each category. The best items get the most recolours:
   * top 20% of a category: every matched palette, plus 2-palette and 3-palette combinations
   * next 30%: up to 6 single palettes and 2 two-palette combinations
   * next 30%: 3 palettes; the rest get 1
   * items scoring 80 or more move up a tier.

   Files are saved as `Characters/<Name>/Wardrobe/<Name>-<Item>-<Palette>.png` and added to the dresser.
4. **Scan for new clothing items** processes only the items added since the last build. *Build / update* skips
   any item and palette combination that already exists.

Profiles are saved automatically and reopen with the app. *Open profile file…* reopens a `profile.json`.

## D. Outfit manager

* Click *Plan today's outfit…* and answer the questions: activity, mood, weather, setting (public, private / at
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
* If no suitable outfit can be made because the needed pieces are in the hamper, the app asks you to request
  **laundry**, which moves everything back to the dresser. There is also a *Do laundry* button.

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
