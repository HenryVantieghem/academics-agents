# Changelog


## [Unreleased]
- chore: save uncommitted work (save-all-work 2026-09-30) (2026-09-30)
- Add readable notebook preset and HTML layout guidance (2026-09-29)
- feat(handwrite): port saurabhdaware/text-to-handwriting: page effects, paper image, uploads, a stable seed (2026-09-28)
- feat(handwrite): port saurabhdaware/text-to-handwriting: page effects, paper image, uploads, a stable seed (2026-09-28)
- feat(handwrite): handtextai parity: gap table, contact sheet, readable defaults (2026-09-24)
- feat(handwrite): Markdown documents, maths, tables, 45 hands, paper catalog, photo scenes (2026-09-24)
- fix(handwrite): stop lines crashing into each other on tightly ruled paper (2026-09-21)
- feat(handwrite): cursive joins, any ink colour, a correction pen, and five human marks (2026-09-21)

Dates are when the work was measured, not when it was planned. Every entry that says a number
was measured has a script in `scripts/` that re-measures it.

## 0.5.0 — 2026-09-28 — saurabhdaware/text-to-handwriting

Upstream (MIT, `0f07785`) was read in full and run locally; the gap table, 26 rows with a
verdict each, is `references/text-to-handwriting-parity.md`. The before/after sheet is
`evals/parity/upstream-t2h/before-after.jpg` (`sheet.py` rebuilds it). Credit and the MIT notice
are in `THIRD_PARTY.md`.

### Added
- **Page effects** from upstream: `--effect shadows` (a gradient shadow across the page, 53% at
  its dark edge, at a seeded angle) and `--effect scanner` (that shadow held to 50-120 degrees,
  then upstream's 0.55 contrast: a phone scanner app's look). `--shadow` and `--contrast` set
  the strength directly. Effects draw from their own random stream, so they never move a
  letter (`hw_effects.py`).
- **`--paper-image`**: a photo or scan of a sheet as the paper, scaled to cover the page;
  upstream tiles it at its own size instead. A phone photo's EXIF turn is applied and
  transparent areas are paper white.
- **`liujian`**, Liu Jian Mao Cao (OFL), the one upstream hand the catalog lacked.
- **Site**: upload your own `.ttf`/`.otf` and a paper image (stored by hash and opened in full
  once, so a bad or truncated file is a 400), page effect, letter and word spacing, top margin,
  a PNG download under every page and a ZIP of all pages (`POST /api/zip`). A body over 25 MB
  is a 413, a paper image given as a server path is refused, and a render stops after 900 s.
- The site's render cache is keyed on the engine's own source, so a page drawn by older code
  is never served after an upgrade.
- T16 (effects, paper image, seed) and T17 (site uploads, ZIP).

### Fixed
- **The same `--seed` drew a different hand in every process.** `GlyphBank` and `MintedBank`
  seeded each letter's warp from `hash(ch)`, and Python salts string hashes per process. One
  page at one seed came out with `collision_rate` 0.0159, 0.0032 and 0.0095 on three runs. The
  warp is now seeded with `zlib.crc32`, and T16 renders one seed under two `PYTHONHASHSEED`
  values and requires identical pixels. Pages rendered before this fix cannot be reproduced
  exactly from their seed.

### Not taken, and why
- Kruti Dev Hindi (no licence, legacy encoding), the drawing pad (an image file does the same
  anywhere in the text), page reordering, jsPDF's inset PDF, analytics and CDN calls. Upstream
  has no spacing or baseline jitter to port; this engine already varies both.

## 0.4.0 — 2026-09-24 — handtextai parity

The site was read feature by feature from the live editor and its bundle; the gap table is
`references/handtextai-parity.md` and the side-by-side is `evals/parity/contact-sheet.jpg`.

### Added
- **Documents.** The text is Markdown: headings, bullet and numbered lists, bold, strike,
  highlight, underline, pipe tables ruled by hand, images, horizontal rules (`hw_doc.py`).
- **Maths.** `$...$` and `$$...$$` LaTeX laid out as handwriting: fractions, roots, sums,
  integrals, limits, scripts, Greek, operators. Bars, radicals, integral and sigma signs are pen
  strokes at the face's measured pen width (`hw_math.py`).
- **45 hands** from Google Fonts, fetched on first use, with per-character fallback by script
  from each font's cmap; Arabic and Hebrew shaped and right to left; CJK sized by its own
  glyphs and broken anywhere (`hw_fonts.py`).
- **Paper catalog** matching handtextai's to the tenth of a millimetre (college, wide, feint,
  Lineatur 25/27/28, CIS, India, 5/10 mm squared, plain), 12 page formats, margins in mm, paper
  and rule colour, three-hole punch, mirrored margins (`hw_paper.py`).
- **Realism presets** `--realism off subtle natural realistic lifelike`, and `--ink-flow`,
  `--texture`, `--shading`, `--blur`, `--letter-spacing`, `--line-height`, `--align`,
  `--hyphenate`.
- **Photo mode** `--mode photo --scene --view`: eight desk plates generated with
  `gemini-3-pro-image` for $1.11 in total, sheet corners detected (four set by hand), the page
  warped onto the sheet and lit by the plate's own light (`hw_scene.py`).
- **Export** to `.zip` and `.jpg` beside `.pdf` and `.png`.
- `parity.py`: the five-input contact sheet against handtextai, with a vision-model A/B.
- T15: every output mode renders at the size and page count it claims.

### Changed
- Default hand is Reenie Beanie, not Caveat: a vision judge rated it 9 against 6 for natural at
  the same legibility. T3 pins Caveat, the face its forensic anchors were measured on.
- Default `--wobble` 0.85, not 1.1: at 1.1 the eye of the `e` closed and "heads" read "hoads".
- Word gaps take Caveat's proportions in every face; a line's fit is measured with the word gap
  actually drawn on it, which let wide-gap lines run off the page before.
- On ruled paper the baseline wander is capped at 0.12 of the rule pitch.
- The collision count (the legibility gate) now runs for print hands too, not only cursive.
- `hyperwrite.py` split: the pen is `hw_ink.py`, the command line `hw_options.py`.

### Known gaps
- Tables look ruled by hand but the judge still calls them a digital grid (natural 3-5/10).
- No PDF/DOCX import, no per-word colour, no notebook-spread scenes.

## 0.3.1 — 2026-09-21 — lines that crash into each other

A page shipped where the writing was unreadable: a 4.6 mm x-height on a 5 mm Moleskine dot
grid, so every line's ascenders landed inside the line above's descenders. It was rendered,
opened in a browser and handed over **without being looked at**. Three demos went out; one
had been inspected.

### Fixed

- **`write_every` separates the printed pitch from the writing pitch.** Nobody writes on
  every row of a 5 mm dot grid — they write across two squares. Treating the printed pitch as
  the line spacing made every 5 mm paper physically unwritable. `dotted` `graph` `moleskine`
  `grid` `engineer` now write every second row.
- **A fit guard.** Writing that still does not fit its ruling is scaled down, with a line
  saying so. `--no-fit` renders it anyway and warns loudly. Printing a note and rendering it
  regardless — which is what the previous version did — is not a guard.
- **The judge's minimum blob size was a constant**, so once the engine began fitting writing
  to the ruling, a full page of 250 letters measured as **13 merged blobs** and scored as
  highly unique. It now scales with the measured text height. Every published anchor moved:
  a pure font page is **31**, handtextai.com is **74**, a real pen page is **100**.
- **The font control was not controlling for the new effects.** `--smudge` and `--restart`
  default on, so the "pure font page" anchor drifted from 24 to 44 the moment human cues were
  added. `test.sh`, `proof.sh` and `calibrate.sh` now zero every effect in the control.

### Tests

**T14** renders 12 lines on five papers and asserts 12 separate text bands come back. It also
asserts the fit guard fires, and that `--no-fit` still renders but warns.

> The first version of T14 checked the override on `moleskine` at 4.6 mm, which stopped being
> an over-size case the moment `write_every` gave it a 10 mm writing pitch — the assertion was
> then testing an unreachable state and failed for the right reason.

---

## 0.3.0 — 2026-09-21 — cursive, colour, and a second pen

### Cursive, by drawing the join

Cursive is not a font property here. The engine finds where a pen would leave one letter and
enter the next — the ink nearest the baseline on each side of the glyph — and lays a stroke
between them. So **joining works with any glyph set**, including one minted from a photo, and
it does not depend on a joined typeface whose advances never match its join points.

```bash
--cursive 1.0     # normal
--cursive 1.6     # a loopier hand
```

The join is a quadratic curve that **sags below the straight line**, because a hand travelling
right drops into the baseline and comes back up. A straight connector reads as a typographic
underscore. The pen also lightens mid-travel and presses again on the next letter.

A joined hand sets its letters closer, so `--cursive` tightens the advance by 7% — tried at
13% first and glyph collision hit the 0.06 legibility cap.

### Any colour

`--ink` now takes **any hex colour** (`--ink "#4B2E83"`) as well as 18 named inks: ballpoint
blues and blacks, fountain-pen `royal` `teal` `turquoise` `purple` `plum` `burgundy` `sepia`
`forest`, plus `orange` `pink` `grey` and two pencil grades.

### A second pen for corrections

The page this engine was measured against literally says *"First attempt in Black /
Corrections in Blue"*. That is now a feature: corrections render on their own ink layer.

```bash
--corrections 0.05 --correct-ink red
```

### Five more human marks

| | what it models |
|---|---|
| **restart blob** | the nib sits still for an instant at the start of a word, so the first letter is heavier |
| **word pressure** | a word written slower is a shade darker; nobody holds one speed |
| **heel smudge** | the heel of the writing hand drags through ink that has not dried — one of the few marks nothing but a hand leaves |
| **highlighter** | `--highlight yellow` runs a wide wet felt tip UNDER the ink, overshooting the ends and wandering above and below the line |
| **strike-through** | struck words are drawn as a real pen stroke with a wobble, not a rule |

### Four more papers

`dotted` · `graph` (5 mm) · `moleskine` (cream dot grid) · `engineer` (green 6.35 mm grid),
joining `college` `ruled` `wide` `grid` `legal` `cream` `blank`.

### Fixed

- The render report never carried `glyphset`, `ink`, `paper` or `cursive`. Two earlier edits
  anchored on text that did not exist and failed silently, so a run could not be reproduced
  from its own output.

### Tests

**T13** asserts joins merge at least 20% of ink blobs without pushing collision over the cap,
and that a hex ink reaches the page. Mutation-verified.

> The first version of T13 counted ink RUNS per image row and moved only **3%** — a join lives
> in a thin band at the baseline, and every row above it is unaffected, so the whole-image
> count drowned the signal. Counting connected components instead sees it immediately.

---

## 0.2.0 — 2026-09-21 — measure a real page, and readability over score

`scripts/measure.py` reads a phone photo of a handwritten page (HEIC via `sips`), deskews and
crops it, and prints the flags that reproduce it: ink colour, slant, x-height **against the
ruling** — the only absolute scale a photo has — baseline wander, paper texture and verso
show-through. `judge.py --reference` and `tune.py --reference` re-point both loops at that
page instead of the generic anchors.

### The headline

Tuning the `henry` preset purely for the reference match reached **81/100** and produced a
page its own author called terrible. The shipped preset is the readable one and scores
**10/100** on that same match.

**Readability is the constraint; the score is what gets maximised inside it.**

### Fixed

- **The ruling scaled with the font size**, so the writing floated between the lines instead
  of sitting on them. College rule is 7.1 mm whatever size you write. (T11)
- **Verso show-through blurred at `dpi/150`**, about one pixel, so page one arrived on the
  back of page two mirrored and *readable*. The spread scales with the writing now. (T12)
- **Digits were minted beside the punctuation rows**, which fail segmentation; their stray
  marks contaminated the digit rows and `3410` rendered as `3470`. Digits get their own sheet.
- **The minted warp at 0.16** measurably raised the realism score and visibly ate the letters:
  `product` read as `produLt`.

> T12 took three attempts. Pixel-differencing two renders **cannot** isolate the bleed —
> page two's own glyphs land a sub-pixel apart between runs, so the diff is dominated by glyph
> outlines and reads the same whether the bleed is soft or sharp.

---

## 0.1.0 — 2026-09-21 — raster engine, judge, minting, site

Replaced a font-with-jitter renderer with a measured one.

- **`hyperwrite.py`** — warped glyph variants, ink pressure / pooling / bleed / skip, paper
  grain visible *through* the stroke, scan and phone-photo capture.
- **`judge.py`** — forensic realism score. Anchors measured, not guessed: pure font page
  **31** · handtextai.com **74** · this engine **68 ± 5** · a real pen page **100**.
- **`glyphmint.py`** — mint a whole hand from an image model for about **$0.20**, cached
  forever.
- **`tune.py`**, **`serve.py`** (a local clone of handtextai.com, stdlib only), **`test.sh`**,
  **`proof.sh`**, and an agent eval suite.

`references/handtextai-teardown.md` records their stack and request schema, read from their
own shipped bundles: their entire realism model is `letter_rotation_range: 2` degrees, and
there is no handwriting model in it anywhere.

### Two findings worth keeping

- **A quality score can be won by breaking the artefact.** A tuning loop scored **82.8/100**
  on an illegible page in 47 renders. Four legibility detectors were tried and all four
  failed — tesseract cannot read handwriting at all, a vision model read the mush at 0.88
  because it guesses words from context, glyph width/height moved the *wrong way*, and
  adjacent-ink overlap could not separate legible from illegible. The search grid is capped
  instead: make the bad state unreachable, not detectable.
- **A cheap image model writes its alphabet like a font** — 0.94 intra-letter correlation.
  Minting buys *style*, the warp still buys *variety*.
