# handtextai.com parity: theirs vs ours

Read 2026-09-24 from the live editor (logged in, free tier, 5 credits, none spent: previews are
free, credits are charged on download) and from the editor bundle, which ships the whole paper
catalog as JSON (`paper_formats`, `paper_families`, `paper_styles`, `page_templates`) and the
realism presets as `REALISM_PRESETS`. The earlier teardown of the request contract is in
`handtextai-teardown.md`; this file is the feature-by-feature gap table.

## Side by side

![contact sheet](../evals/parity/contact-sheet.jpg)

`evals/parity/contact-sheet.jpg`, rebuilt by `python3 scripts/parity.py --judge`. Left column:
handtextai's own preview of the same text (A4, College Ruled, default font, realism Off, which is
all the free tier offers), stored in `evals/parity/theirs/`. Middle: ours, Print mode, defaults.
Right: ours, Photo mode on a generated desk plate. Inputs are `evals/parity/inputs/*.md`.

Vision-model A/B (`google/gemini-3-flash-preview`, one call per input, 2026-09-24, same text,
scores out of 10; `contact-sheet.judge.json`):

| input | theirs legible | ours legible | theirs natural | ours natural |
|---|---|---|---|---|
| letter | 7 | **9** | 9 | 8 |
| class notes | 8 | **9** | 10 | 8 |
| maths page | **9** | 7 | 8 | **10** |
| table | 8 | **9** | **9** | 3 |
| Russian letter | 6 | **9** | 9 | 8 |
| **mean** | 7.6 | **8.6** | **9.0** | 7.4 |

Read it with care: one call per cell, and the same pair re-asked moves by 1-2 points. The
stable pattern across five runs is that ours is easier to read on every input except the maths,
and theirs looks more natural on the table. Their default face is a quick joined hand, which the
judge reads as "authentic cursive"; ours is a legible print hand. Turning on `--cursive 1.0`
with our default face raised "natural" to 8.5 and dropped "legible" to 7.5 (4 calls each), so
cursive stays an option rather than the default: legibility is the constraint.

## Gap table

Legend: **=** parity, **+** ours does more, **~** partial, **-** missing.

### Output

| Theirs | Ours | |
|---|---|---|
| Print mode: clean page | default, `--capture print` for a clean file, `scan` adds a scanner's look | + |
| Photo mode: the page in a notebook scene (8 scenes, all PRO) | `--mode photo --scene <name\|random>`: 8 generated desk plates, perspective, the plate's own light and shadow on the page | = |
| scene framing Wide / Closer / Closest | `--view wide\|closer\|closest` | = |
| randomize scenes | `--scene random`, seeded, a different plate per page | = |
| scene start side, opening-page spread | single-sheet plates only | - |

### Paper

| Theirs | Ours | |
|---|---|---|
| 16 styles: Plain, College, Wide, Feint, Lineatur 25/27/28, CIS grid and line, India single line / college / 12 mm square, 5 mm and 10 mm squared, 3-hole and exercise-book variants | `--paper`: all of those as `plain college wide feint lineatur25 lineatur27 lineatur28 cis-grid cis-ruled india india-college india-square squared5 squared10`, with their exact pitch, rule colour and weight, first-rule offset, margin guides and default margins; plus our `ruled grid legal dotted graph moleskine engineer cream blank` | + |
| 3-hole variant | `--holes` on any paper | = |
| 11 formats: A3-A6, US Letter/Legal/Tabloid, 4x6, 5x7, JIS B5, India 24x18 | `--pagesize a3 a4 a5 a6 letter legal tabloid 4x6 5x7 b5 india postcard`, `--landscape` | = |
| margins in mm, linked or per edge | `--margin-top/right/bottom/left` (mm) | = |
| different margins on even pages, mirror | `--mirror` swaps margins and margin lines on even pages | ~ |
| paper colour (implicit in style) | `--paper-color white ivory cream yellow pink blue green grey kraft aged` or `#hex`, `--rule-color #hex`, `--no-margin-line` | + |

### Typography

| Theirs | Ours | |
|---|---|---|
| 95 numbered fonts, filtered by script | 45 named open-licence hands (`hw_fonts.py list`), fetched on first use, plus macOS faces | ~ |
| script filter: Latin, Cyrillic, Arabic, Greek, Devanagari, Hangul, Hiragana, Katakana, CJK | automatic per-character fallback to a hand that has the glyph, from the font's own cmap; Arabic and Hebrew shaped and set right to left; also Thai | + |
| custom font upload (.ttf, 10 MB, Premium) | `--font path/to/hand.ttf` | = |
| a separate maths font | maths is written with the same hand, symbols from Klee One | ~ |
| font size, line height, letter spacing, word spacing, paragraph spacing | `--size` (x-height mm), `--line-height` (unruled), `--letter-spacing`, `--word-space`; paragraph spacing is a blank line in the text | ~ |
| hyphenation | `--hyphenate` | = |
| alignment left / centre / right | `--align` for the whole document | ~ |

### Realism

| Theirs | Ours | |
|---|---|---|
| presets Off, Subtle, Natural, Realistic, Lifelike | `--realism off subtle natural realistic lifelike` | = |
| word placement, natural line starts, natural line spacing | `--drift`, `--linestart`, `--messiness` | = |
| ink amount (text fade) | `--ink-flow`, plus pressure, pooling, bleed, ballpoint skip, paper grain through the ink | + |
| handwriting variation | `--variants`, `--wobble`: every letter a differently warped form, not one outline rotated | + |
| letter tilt, up to 20 degrees | `--slant` (habitual) plus per-letter rotation from `--messiness` | = |
| paper texture, shading, soft focus | `--texture`, `--shading`, `--blur` | = |
| — | show-through from the previous page, heel smudge, restart blobs, strike-through corrections in a second pen, highlighter | + |

### Document editor

| Theirs (TipTap) | Ours (Markdown in the text) | |
|---|---|---|
| headings | `#`, `##`, `###` | = |
| bold, underline, strikethrough | `**bold**`, `<u>under</u>`, `~~struck~~` | = |
| text colour per span | one ink per page, `==highlight==`, a correction pen | ~ |
| bullet and numbered lists | `- item`, `1. item`, nested by indent | = |
| tables | pipe tables, hand-ruled | = |
| LaTeX maths | `$inline$` and `$$display$$`: fractions, roots, sums, integrals, limits, scripts, Greek, operators, drawn as pen strokes | = |
| images (PRO) | `![alt](path)` | = |
| block text size | headings only | ~ |
| import PDF / DOCX | not built; convert to Markdown first (`pandoc x.docx -t gfm`) | - |
| AI Writer | not built: the assistant calling this skill writes the text | - |

### Export

| Theirs | Ours | |
|---|---|---|
| PDF up to 500 pages (PRO), ZIP (free), JPG, PNG | `.pdf` (multi-page), `.png`, `.jpg`, `.zip` by the `--out` extension; `--max-pages` 60 by default | = |
| quality Standard / HD / 4K | `--dpi 150 / 300 / 600`, `--quality` for JPEG | = |
| business API | the CLI and `serve.py`'s `/api/generate` | ~ |

## Photo mode, how ours is made

`hw_scene.py plates` asks `google/gemini-3-pro-image` (priced before use: $0.1375 a 2K image)
for a desk photo with ONE BLANK UNRULED sheet on it, finds the sheet's corners, and stores both
in `assets/scenes/manifest.json` with the model, prompt, date and cost. At render time the page,
ruling included, is warped onto the sheet and multiplied by the plate's own light divided by
its white, so the window gradient, the lamp pool and the window-frame shadow fall across the
writing. Theirs photographs real blank notebooks and writes into them; ours generates the
photograph, so every plate is ours to ship.

Eight plates, **$1.1066** in total (8 x ~$0.138, from OpenRouter's `usage.cost`). Four sheets
(lamp-angle, window-shadow, marble, study-desk) merged with a bright surface in the automatic
detector and have hand-measured corners; `quad_source` in the manifest says which.
`hw_scene.py overlay --out check.jpg` draws every outline for checking by eye.

## Not copied, on purpose

- their fonts and scene photos: we use open-licence faces and plates we generated
- anything about passing a page off as a specific person's own handwriting
