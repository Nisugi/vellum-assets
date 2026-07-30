# Gemini prompt kit for VellumFE skin assets

Feed the **master style block** with every request, attach `Dwarf.png` as the
style reference image, then append one batch prompt. File names/ids come from
`src/config/skins.rs` — keep them exact so assets drop straight into a skin
manifest.

---

## Master style block (prepend to every prompt)

> Art direction: dark-fantasy medieval game asset in the exact style of the
> attached reference image — hand-painted illustration with clean dark ink
> outlines, muted desaturated earth tones (olive greens, worn browns, iron
> greys, dull brass), weathered matte surfaces. Absolutely NO gloss, NO shiny
> highlights, NO glow, NO bloom, NO lens flare, NO neon or saturated colors.
> Lighting is flat and diffuse. Solid PURE BLACK background — no scenery,
> no ground shadow, no vignette, no gradient. No text, no watermark, no
> border.

(Never ask an image model for a transparent background — they cannot emit an
alpha channel and will either ignore you or paint a fake checkerboard. Solid
black is the keying background; `dekey.py` in this folder turns it into real
transparency afterward.)

---

## Batch 1 — Compass (12 images, one shared canvas)

The widget stacks per-direction overlays on top of the rose, so registration
matters more than beauty. Generate the two "master" states first; the 11
overlays are best cut from the all-lit master in an editor (Gemini cannot
guarantee pixel registration across separate generations — don't fight it).

**Prompt A — the rose (base, everything unlit):**

> A square compass rose for a fantasy game UI, viewed flat from directly
> above. An aged dark-iron ring with a worn brass center hub. Eight
> directional pointers (N, NE, E, SE, S, SW, W, NW) as tarnished
> arrowheads radiating from the hub, plus a small UP chevron at the top
> inside the ring and a small DOWN chevron at the bottom inside the ring.
> ALL pointers, both chevrons, and the hub are in a dormant, unlit state:
> dark gunmetal, barely distinguishable from the ring. Square canvas,
> composition perfectly centered and symmetrical.

**Prompt B — all-lit master (same composition):**

> The IDENTICAL compass rose, same canvas, same composition, same camera —
> but every pointer, both chevrons, and the center hub are now in an active
> state: dull ember-copper with a faint warm edge, still matte, like heated
> iron cooling — NOT glowing, NOT shiny.

Then slice: mask each lit pointer out of B onto a transparent canvas →
`n.png`, `ne.png`, `e.png`, `se.png`, `s.png`, `sw.png`, `w.png`, `nw.png`,
`up.png` (top chevron), `down.png` (bottom chevron), `out.png` (the hub).
Rose from A → `rose.png`. If a generation drifts, regenerate B by attaching A
and asking for "the same image with all pointers lit" — image-conditioning
holds registration far better than text alone.

---

## Batch 2 — Status icons (16 glyphs, one sprite sheet)

One sheet keeps the style uniform; slice into individual PNGs after.

> A 4x4 grid sprite sheet of sixteen square fantasy game status icons,
> uniform in style, stroke weight, and visual density, each a single bold
> pictogram readable at 20 pixels. Flat matte colors from the reference
> palette, one restrained accent color where meaning demands it. Cells in
> row-major order:
> 1. an open left hand, palm out
> 2. an open right hand, palm out
> 3. a hand with a subtle rune circle above the palm (spellcasting hand)
> 4. a standing figure
> 5. a kneeling figure
> 6. a sitting cross-legged figure
> 7. a figure lying prone
> 8. a skull (dead)
> 9. stars circling a tilted head (stunned)
> 10. a falling blood drop (bleeding), dull crimson accent
> 11. a hooded figure half-dissolved into shadow (hidden)
> 12. a dotted outline of a figure (invisible)
> 13. a figure wrapped in spiderweb strands (webbed)
> 14. a serpent coiled around a drop (poisoned), dull green accent
> 15. a gaunt face with sunken cheeks (diseased), pale ochre accent
> 16. two linked shackle rings (group-joined)

Slice to: `lefthand.png`, `righthand.png`, `spellhand.png`, `standing.png`,
`kneeling.png`, `sitting.png`, `prone.png`, `dead.png`, `stunned.png`,
`bleeding.png`, `hidden.png`, `invisible.png`, `webbed.png`, `poisoned.png`,
`diseased.png`, `joined.png`.

---

## Batch 3 — Injury dolls (one base image per race/class combo)

The app draws wounds itself as dots at calibrated anchor points, so the art
must expose every anchored body part. Non-negotiables are baked into the
prompt below. Attach `Dwarf.png` and reuse this template, swapping the
{RACE} / {CLASS} slots. GemStone IV races: Human, Giantman, Dwarf, Halfling,
Elf, Dark Elf, Half-Elf, Sylvankind, Forest Gnome, Burghal Gnome,
Half-Krolvin, Erithian, Aelotoi. Classes for outfit flavor: Warrior, Rogue,
Wizard, Cleric, Empath, Sorcerer, Ranger, Bard, Monk, Paladin, Savant.

> A full-body character portrait of a {RACE} {CLASS} from a fantasy world,
> in the exact painted style, palette, framing, and proportional scale of
> the attached reference image. Requirements, all mandatory:
> - standing straight, facing the viewer directly, perfectly front-on
> - arms relaxed and held slightly away from the torso so upper arms,
>   forearms, and both open hands are fully visible and do not overlap
>   the body
> - legs slightly apart, both feet visible
> - head bare or with headwear that leaves the face open: BOTH eyes must
>   be clearly visible, open, and unobstructed by hair, hood, or helmet
> - neck visible between head and collar
> - the full figure fits inside the frame with a small margin — nothing
>   cropped
> - portrait orientation, roughly 3:4
> - muted, weathered, matte clothing appropriate to a {CLASS}; no shiny
>   armor, no glowing effects, no magic auras
> - solid pure black background, no ground shadow

Name files `{Race}.png` or `{Race}_{Class}.png`. After dropping one into a
skin, run Settings > Appearance > Skin > "Calibrate injury doll" and click
through the parts — anchors are stored as fractions of the image, so exact
pixel size never matters, but keep framing consistent across races so
calibrations feel similar.

Practical count: 13 races x 11 classes = 143 images. Generate on demand for
characters that exist rather than the full matrix; the calibrator makes each
new doll a two-minute job.

---

## Batch 4 — Window frames (nine-slice borders)

The renderer slices the image into nine regions from the `slice` insets:
corners draw at fixed size, the four straight runs stretch along one axis,
and the center is never drawn. That dictates the art:

- The frame must run **flush to all four canvas edges**, with a **uniform
  band thickness** on every side (target roughly 1/8 of the canvas width).
- Corner ornament is free — it draws unstretched. The four straight runs
  between corners must be **continuous, uniform material** (riveted iron
  band, wood grain running along the run, plain rope) with no medallions,
  knots, or creatures mid-run: anything distinct there gets stretched.
- Corner caps **thicker than the runs are fine** — real generations come
  back that way and it looks good. Set `slice` to the *cap* size; the
  black between the runs' inner edge and the cap depth becomes
  transparent in post and simply never draws.
- Frames DO need a dekey pass, with a twist: the center is a sealed
  pocket the edge flood can't reach, so seed it explicitly, and use a
  low threshold so near-black seams in the ironwork survive:
  `python skins/dekey.py frame.png --seed 1024,1024 --threshold 12 --no-grey`
- Inspect the inner corners at full zoom before accepting — Gemini likes
  to drop small "glint"/sparkle artifacts there, and anything inside the
  corner squares gets drawn over window content. A clean corner can be
  mirrored over a blemished one (the bands line up by construction).

**Prompt:**

> A square ornamental window frame for a fantasy game UI, viewed flat.
> An aged dark-iron band with worn brass corner caps, riveted along its
> length. The frame runs flush to all four edges of the canvas with a
> uniform thickness on all sides, about one eighth of the canvas wide.
> Corner ornamentation stays within the corner squares; the four straight
> runs between corners are plain, continuous, evenly textured metal with
> no emblems or breaks. The inner edge of the frame is a crisp straight
> line. The center of the frame is empty pure black.

Variants worth a set: `frame_iron.png` (default), `frame_brass.png`
(highlight/main window), `frame_wood.png`, `frame_rope.png`. Manifest:

```toml
[window.default.border]
image = "border/frame_iron.png"
slice = [310.0, 310.0, 310.0, 310.0]  # measure the CAPS in source pixels
scale = 0.045                         # 2048px source -> ~14pt caps on screen
```

`scale` is what brings chunky source art down to a sane on-screen
thickness — measure the caps once in an editor, set `slice` to that, then
tune `scale` by eye. (Numbers above are the accepted first-generation
frame: 2048px canvas, ~307px caps, ~240px runs.)

---

## Batch 5 — Window background textures

Backgrounds sit **behind text**, so restraint is the whole game: low
contrast, no focal points, no vignette (windows get cropped by `cover` at
arbitrary aspect ratios, so nothing about the composition may matter).
The manifest's `scrim` paints a theme-colored wash on top for readability
— author the texture legible-ish and let scrim do the rest.

> A flat, even, borderless surface texture for a game UI background:
> {aged parchment with faint fiber flecks | worn dark leather with fine
> grain | rough hewn dark stone}. Perfectly uniform lighting across the
> whole canvas — no vignette, no hotspot, no directional shadow, no
> focal detail anywhere. Very low contrast, subtle texture only.
> Landscape orientation.

Don't ask for "seamless/tileable" — image models can't actually do it and
the seam will show. Use `fit = "cover"` instead of `tile` and generate
generously sized. Dark variants suit the default theme; a light parchment
works if paired with a heavy scrim. No dekey needed — backgrounds are
opaque by design.

```toml
[window.default.background]
image = "bg/leather.png"
fit = "cover"
opacity = 1.0
scrim = 0.35
```

Per-window flavor is cheap once the set exists: parchment for `thoughts`,
stone for `combat`, vellum for `main`.

---

## Batch 6 — Hotbar icon sheets

Hotbar buttons pull from `[sheets]` sprite sheets: square cells, **no
padding**, indexed 1-based left→right then top→bottom (the barbar
convention, 64px cells by default). Gemini keeps style coherent across
about 16 icons per generation, so build sheets from 4x4 grids — reuse the
Batch 2 sprite-sheet prompt frame with new cell contents, e.g.:

> A 4x4 grid sprite sheet of sixteen square fantasy game ability icons,
> uniform in style, stroke weight, and visual density, each a single bold
> pictogram readable at 32 pixels, each cell filling its square edge to
> edge with a plain dark backing — no borders between cells. Cells in
> row-major order: 1. a longsword mid-swing 2. crossed daggers
> 3. a drawn bow ... 16. a healing herb sprig

After acceptance, resample the image so cells land exactly on the cell
size (a 4x4 sheet → 256x256 for 64px cells) — the loader tiles by pixel
arithmetic and drifted cell boundaries bleed neighbors into buttons.
Register in the skin (or in `~/.vellum-fe/global/icons/icons.toml` to
share across skins):

```toml
[sheets.combat]
path = "icons/combat.png"
cell = 64
```

Buttons reference them from hotbars.toml as
`icon = { sheet = "combat", cell = 3 }` — keep a note of which cell is
which when you slice, the index is the only key.

---

## Optional — Injury doll severity overlays

The generated dots (Batch 3 workflow) cover wounds/scars for free. For a
flagship skin the manifest also accepts hand-authored full-canvas
overlays per part and severity (`[injury_doll.head] injury1 = ...`,
`injury2-3`, `scar1-3`), which take precedence over dots. That's up to
14 parts x 6 severities = 84 registered images **per doll** — only
attempt it by generating the doll base, then image-conditioning "the
same figure with a bleeding gash on the left arm" and slicing the diff
onto a transparent canvas, exactly like the compass overlay workflow.
Not recommended as a starting point; the dots exist for a reason.

---

## Not yet skinnable (don't author art for these)

Progress bars, countdown timers, the command input, title bars, scroll
bars, and the radial wheel have no manifest slots today — the six
sections above are the complete surface. If art gets made for anything
else it has nowhere to go until the manifest grows a slot.

---

## Post-processing (every accepted image except backgrounds)

Backgrounds (Batch 5) skip this — they're opaque by design. Frames
(Batch 4) need the `--seed`/`--threshold` variant described there.
Everything else black-keyed (compass, icons, dolls, sheet slices) goes
through:

```
python skins/dekey.py TheImage.png              # -> _alpha.png + _grey.png
python skins/dekey.py TheImage.png --threshold 40   # if a dark halo remains
```

`_alpha.png` has a REAL alpha channel (flood-filled from the edges, so black
ink lines and dark clothing inside the figure survive). `_grey.png` is the
same image desaturated — derived locally so it matches the color version
pixel-for-pixel; use it as the injury-doll base so colored wound dots pop.
Never generate a greyscale variant separately in Gemini: it will not match.

## Workflow notes

- Always attach the previous batch's accepted output as a reference when
  generating siblings — consistency comes from image conditioning, not from
  repeating adjectives.
- Gemini approximates canvas sizes; aspect ratio is what it honors. The skin
  loader scales everything, and doll anchors are fractional, so exact pixel
  dimensions are irrelevant — internal consistency is everything.
- If a result comes back with scenery or a non-black background, ask it to
  "re-render the same image on a solid pure black background" rather than
  regenerating fresh.
- Reject anything glossy immediately; shine creeps back in with each
  generation unless the NO-gloss lines stay in the prompt.
