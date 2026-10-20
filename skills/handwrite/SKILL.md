---
name: handwrite
description: >-
  Turn text or a Markdown document into pages someone wrote by hand: a PDF, PNG, JPG or ZIP
  with letterforms that differ every time, real ink behaviour, headings, bullet lists, tables,
  LaTeX maths written as pen strokes, and text in any script (Latin, Cyrillic, Greek, Arabic,
  Hebrew, Devanagari, Thai, Korean, Japanese, Chinese). Paper to the millimetre (college,
  wide, feint, Lineatur, squared, dotted, India and CIS school papers, any colour), and a Photo
  mode that places the page on a desk in a lit, perspective-correct photo. Use whenever
  something should LOOK handwritten rather than typed: handwritten notes, a study sheet, a
  maths worksheet, a journal page, a letter or thank-you card, flash cards, notes for a video
  or mockup, a prop document, "text to handwriting", "handwritten PDF", "make this look
  handwritten", or anyone wanting their own handtextai.com. Also scores how convincing a page
  is and mints a new hand from an image model. Trigger on /handwrite.
license: MIT
---

# handwrite

Render a document as pages a person wrote by hand, then check it reads.

Front doors: `/handwrite` in Claude Code and in Codex (`~/.codex/skills/handwrite/`). Both run
the **same scripts** in this directory; there is no second copy to drift.

## Use it

```bash
python3 scripts/hyperwrite.py --file notes.md --out notes.pdf --seed 42
python3 scripts/hyperwrite.py --file notes.md --out photo.jpg --mode photo --scene random
python3 scripts/hyperwrite.py --text "Dear Sam, thank you." --out card.png --pagesize 5x7 --paper cream
```

Text comes from `--file`, `--text`, or stdin. The output format follows the `--out`
extension: `.pdf` (multi-page), `.png` / `.jpg` (one file per page, `-01`, `-02`...), `.zip`
(a PNG per page). The run prints a JSON report and writes it beside the output as
`<name>.hyperwrite.json`: pages, seed, size, scene, and `collision_rate`, the legibility gate.

🔑 **The seed IS the identity of the hand.** Reuse it across runs or page two of a document
looks like a different person wrote it.

## Documents

The text is Markdown. Plain prose with none of it lays out exactly as before; `--plain` turns
the markup off entirely.

| Write | Get |
|---|---|
| `# Title` `## Section` `### Minor` | bigger writing; a `#` heading takes two ruled rows |
| `- item` `* item` `1. item`, indented two spaces per level | a pen dash, a dot, or the number, with the text hanging off it |
| `**bold**` `~~struck~~` `==highlighted==` `<u>underlined</u>` | gone over twice, struck through, highlighter under it, a pen underline |
| `$x^2$` inline, `$$\frac{a}{b}$$` on its own line | maths written by hand: bars, roots, integral and sigma signs are pen strokes |
| a pipe table, header row first | a table ruled by hand, full width, one ruled row of air per row |
| `![alt](figure.png)` | the image stuck onto the page, the writing around it |
| `---` | a pen line across |
| a blank line | a skipped line, as in a notebook |
| `::: correction` then `::: end` on separate lines | write the enclosed blocks with the second pen (`--correct-ink red` for red corrections) |

For self-evaluations, keep the first attempt in the main ink and wrap checked
corrections and final answers in `::: correction` / `::: end`. Use an actual
handwriting sample or the `henry` preset when available; inspect readability
before using a personalized hand. The color markers preserve the same page
layout and pen variation, rather than switching to uniform HTML text.

Maths covers `\frac \sqrt \sqrt[n] ^ _ \sum \prod \int \iint \oint \lim`, `\left( \right)`,
Greek, relations and operators, `\sin \log` and friends, `\text{}`, `\vec \hat \bar`, and
spacing. An unknown command is written out by name, so a typo shows on the page.

## Flags

Anything you pass beats `--preset` and `--realism`.

**Page**

| Flag | Default | Notes |
|---|---|---|
| `--paper` | `college` | `college wide feint plain squared5 squared10 lineatur25 lineatur27 lineatur28 cis-grid cis-ruled india india-college india-square` (handtextai's catalog, exact pitch, colour and margins) and `ruled grid graph dotted moleskine engineer legal cream blank` |
| `--pagesize` | `a4` | `a3 a4 a5 a6 letter legal tabloid 4x6 5x7 b5 india postcard`; `--landscape` |
| `--paper-color` | the paper's | `white ivory cream yellow pink blue green grey kraft aged` or `#hex`; `--rule-color #hex` |
| `--margin-top/-right/-bottom/-left` | the paper's | millimetres |
| `--mirror` | off | margins and margin lines swap sides on even pages |
| `--holes` | off | three-hole punched |
| `--no-margin-line` | | drop the red or grey margin guide |
| `--paper-image` | | a `.png`/`.jpg` of a real sheet as the paper, scaled to cover; the `--paper` ruling is drawn on top, so use `plain` or `blank` to keep only the photo's lines |

**Hand**

| Flag | Default | Notes |
|---|---|---|
| `--font` | `reenie` | any of 47 hands (`python3 scripts/hw_fonts.py list`), a macOS face, or a path to any `.ttf`/`.otf` |
| `--size` | 4.6 | x-height in mm; on ruled paper it is fitted to the ruling (`--no-fit` overrides) |
| `--letter-spacing` `--word-space` | 0, 1.35 | em per letter; word gap multiplier |
| `--line-height` | 1.62 | line pitch in em, unruled paper only; ruled paper writes on its rules |
| `--align` `--hyphenate` | left, off | `left center right` |
| `--slant` `--messiness` `--drift` `--linestart` | 0, 1.0, 0.34, 1.0 | lean in degrees; overall care; baseline wander; margin scatter |
| `--variants` `--wobble` | 14, 0.85 | forms per letter and how different they are. **Above ~1.0 the eye of the `e` closes** |
| `--cursive` | off | joins letters up; 1.0 normal. Reads more natural and less legible |
| `--glyphset` | | a hand minted with `glyphmint.py` (see references/engine-notes.md) |

**Ink and look**

| Flag | Default | Notes |
|---|---|---|
| `--ink` | `blue` | 21 named inks or any `#hex`; `--correct-ink` for the second pen |
| `--realism` | | `off subtle natural realistic lifelike`, handtextai's five steps |
| `--pressure` `--grain` `--bleed` `--pool` `--skip` `--ink-flow` | 1, 0.22, 1, 1, 0.35, 0 | pen weight swing, paper through the ink, capillary halo, pooling, ballpoint skip, the pen running dry |
| `--texture` `--shading` `--blur` | 1, 0, 0 | paper fibre, uneven light across the sheet, soft focus |
| `--corrections` `--highlight` `--smudge` `--showthrough` | 0, off, 0.6, 1 | struck-out words, a highlighter under everything, heel smudge, last page bleeding through |
| `--capture` | `scan` | `print` (clean file), `scan`, `photo` (a phone photo of the bare page) |
| `--effect` | `none` | text-to-handwriting's page effects: `shadows` (a gradient shadow across the page) or `scanner` (a side shadow, then a scanner app's contrast; implies `--capture print`) |
| `--shadow` `--contrast` | 0, 0 | the same two knobs directly: 1 is upstream's shadow, 0.55 its scanner contrast |
| `--dpi` `--quality` | 200, 92 | 150 screen, 300 print, 600 for "4K" |

**Photo mode**

| Flag | Default | Notes |
|---|---|---|
| `--mode photo` | `print` | put each page on a desk (below) |
| `--scene` | `random` | `oak-mug dark-desk marble study-desk lamp-angle window-shadow clipboard concrete`, `random`, or `fallback` (no plate: a plain desk, works offline) |
| `--view` | `closer` | `wide` the whole photo, `closer`, `closest` |

| Preset | What it is |
|---|---|
| `student` | college rule, blue biro, rushed, photographed on a desk |
| `study-notebook` | readable dark-ink ruled notes with restrained variation |
| `neat` | ruled, dark blue, careful, scanned |
| `letter` | cream unruled, blue-black, slight droop to the right |
| `journal` | ruled, black, everyday pace |
| `exam` | very rushed, cramped, photographed |
| `pencil` | grid paper, graphite, soft edges |

## HTML-first study notes

For dense worked notes, draft and review the content in Markdown or HTML first. HTML/CSS is useful
for page layout, line spacing, and keeping math legible. A local Chromium print pass can then make a
PDF. In the STAT 3610 Homework 1 and Quiz 1 trial, this produced smaller, selectable-text PDFs
with clean pagination, but the font repeated identical letterforms and looked more uniform than
the pen renderer. Keep the HTML/PDF as a readable version; use `--preset study-notebook` for a
more natural notebook version. Do not treat an HTML print as proof of handwriting realism.
On the same dense math sample, Caveat with automatic cursive joins collided enough to obscure
digits and words; the study preset uses Patrick Hand without joins after visual review.

For a reproducible example, see
`~/agenticengineeringconsultingllc/Academics-Enterprise-FALL2026/courses/STAT-3610/05-study-guides/handwriting/build_html.py`.
It converts checked Markdown with Pandoc, embeds local open-licence fonts, and prints through
Chrome. Inspect the PDF pages after printing: ruled backgrounds, math glyphs, and page breaks
can differ from browser preview.

```bash
python3 scripts/hyperwrite.py --file notes.md --out notes.pdf --preset study-notebook --pagesize letter --seed 42
```

## Photo mode

```bash
python3 scripts/hyperwrite.py --file notes.md --out desk.jpg --mode photo --scene lamp-angle --view wide
python3 scripts/hw_scene.py list                         # plates, model, cost
python3 scripts/hw_scene.py overlay --out check.jpg      # every plate with its sheet outline
python3 scripts/hw_scene.py plates --budget 1.0          # generate any missing plates
```

The plates in `assets/scenes/` are generated, not photographed: an image model draws a desk with
one blank, unruled sheet on it, and `manifest.json` records model, prompt, date and cost for
each ($1.11 for all eight). The whole page, ruling included, is warped onto that sheet and
multiplied by the plate's own light, so a lamp pool or a window-frame shadow falls across the
writing. The sheet's corners are found automatically; when a sheet sits on a surface as bright
as paper the detector merges them, so **open the `overlay` sheet after generating** and set
the quad by hand in the manifest if an outline is wrong (four of the eight needed that).

## Hands and scripts

`hw_fonts.py` names 47 open-licence handwriting faces from Google Fonts (licences in
`THIRD_PARTY.md`). They download on first
use into `assets/fonts/` (not in git; about 50 MB for all of them, `hw_fonts.py fetch --all` to
warm it). Offline, the engine falls back to Caveat.

A character the chosen hand does not have is written in the first hand that does, per script,
decided from the font's own cmap table: Cyrillic in Neucha, Greek in Playpen, Arabic in Ruqaa,
Hebrew and Thai and Devanagari in Playpen or Kalam or Mali, Korean in Nanum Pen, Japanese in Klee
One, Chinese in Ma Shan Zheng, maths symbols in Klee One. Arabic and Hebrew words are shaped as
whole words and their lines run right to left. Korean, Japanese and Chinese are sized by their
own characters, not by the face's Latin x-height, and a run of CJK breaks anywhere.

```bash
python3 scripts/hw_fonts.py covers reenie "Привет αβγ ∫"    # what a hand lacks
```

**Font hand or minted hand.** Every hand is font-based: letters are glyphs, each one warped into
a different form every time it appears; maths, table rules and joins are drawn as pen strokes.
Use a catalog hand or your own `.ttf`/`.otf` (`--font`) for anything with punctuation, numbers
or other scripts. Use a minted set (`--glyphset`) only for a Latin page written in that one
minted hand (`references/cloning-your-hand.md`); it covers letters, and anything else falls back
to the font.

## Prove it, do not eyeball it

A PDF that exists is not a PDF that reads.

```bash
python3 scripts/parity.py --judge        # 5 inputs vs handtextai, contact sheet + vision A/B
python3 scripts/judge.py page.png        # forensic realism score, per-metric breakdown
```

🛑 **Readability is the constraint; every score is maximised inside it.** Twice a tuner found
it could raise a realism score by making letters collide or holes appear in strokes. The
renderer counts glyph collisions itself (`collision_rate` in the report; above ~0.06 a page
reads as mush), and after any change to the hand, **look at the page**. Details, the scoring
bands, the tuner and why four automatic legibility gates failed: `references/engine-notes.md`.

Against handtextai on the same five inputs (`references/handtextai-parity.md`): ours read more
easily on four of five, theirs looked more natural on the table, where their quick joined
default hand beats our print hand.

## Your own handtextai.com

```bash
python3 scripts/serve.py          # http://127.0.0.1:8787, walks up if the port is taken
```

Editor, Print/Photo switch, scene and framing, realism, page effect, paper, format, hand, ink,
your own font and paper image as uploads, letter and word spacing, top margin, page previews
with a PNG download each, PDF and ZIP download, and the forensic score on every render. Nothing leaves the machine;
standard library only. The HTTP contract mirrors theirs (`/api/generate`, `/api/pdf`,
`/api/fonts`) with the same `paper / font / effects / general` split plus `output`, and
`/api/zip`. An upload is `{"name", "data": base64}` under `font.upload` or `paper.upload`.

## Tests

```bash
bash scripts/test.sh          # 17 deterministic regressions, no network, ~60 s
bash scripts/proof.sh         # the ship gate: CLI -> PDF -> score -> site round trip
claude plugin eval .          # 5 agent cases
```

Every test in `test.sh` is a bug that actually happened, with its date. T15 renders every
output mode (PDF, PNG on five papers, landscape JPG, ZIP, Photo on a plate and offline) and
checks the pixel size and page count each one claims.

## Where the details live

| File | What |
|---|---|
| `references/handtextai-parity.md` | the gap table, feature by feature, and the side-by-side |
| `references/handtextai-teardown.md` | how their site works: request contract, realism ceiling |
| `references/text-to-handwriting-parity.md` | saurabhdaware/text-to-handwriting, row by row: what was ported, what was not, why |
| `references/engine-notes.md` | scoring, tuning, cursive, minted hands, measuring a photo of a page |
| `references/realism-model.md` | what makes a page read as handwritten, measured |
| `scripts/hw_doc.py` `hw_math.py` `hw_paper.py` `hw_fonts.py` `hw_scene.py` `hw_ink.py` `hw_effects.py` | layout, maths, paper, hands, photo mode, the pen, page effects |

## Limits

- Font-based with per-glyph warping, not stroke synthesis. Joined cursive is drawn between
  letters, not inside them.
- Import of PDF or DOCX is not built: convert to Markdown first (`pandoc x.docx -t gfm`).
- One ink colour per page (plus the correction pen and highlighter), not per word.
- It will not survive forensic examination and is not built to. Do not imitate a named
  person's hand, and do not make anything meant to pass as a genuine signed or executed record.
