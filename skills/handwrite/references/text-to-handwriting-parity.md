# saurabhdaware/text-to-handwriting: what we took and what we left

Upstream is https://github.com/saurabhdaware/text-to-handwriting at `0f07785` (2021-07-11, MIT,
archived by its author). Read in full on 2026-09-28: `index.html`, `css/index.css`,
`js/app.mjs`, `js/generate-images.mjs`, `js/utils/{draw,generate-utils,helpers}.mjs`. It is a
static browser page: a `contenteditable` div styled with a handwriting web font and CSS ruling,
turned into a JPEG by html2canvas and into a PDF by jsPDF.

Its output for our letter input, captured by running that commit locally
(`evals/parity/upstream-t2h/capture.py`, Playwright on a local checkout):

| shadows (default) | scanner | no effect | Caveat | Liu Jian Mao Cao |
|---|---|---|---|---|
| ![](../evals/parity/upstream-t2h/shadows-homemadeapple.jpg) | ![](../evals/parity/upstream-t2h/scanner-homemadeapple.jpg) | ![](../evals/parity/upstream-t2h/no-effect-homemadeapple.jpg) | ![](../evals/parity/upstream-t2h/no-effect-caveat.jpg) | ![](../evals/parity/upstream-t2h/no-effect-liujianmaocao.jpg) |

## Two premises in the brief, checked

- **Upstream has no spacing or baseline jitter.** Letter and word spacing are single CSS values
  (`app.mjs` `#letter-spacing`, `#word-spacing` set `pageEl.style.letterSpacing/wordSpacing`),
  and the baseline is the CSS line box. Every `e` is the same outline in the same place. Ours
  already varies each word gap, each letter advance, the baseline, size and rotation (rows 5-7).
- **This engine is font-based, not stroke-based.** `hyperwrite.py` warps glyphs from one of 45
  open-licence handwriting fonts (`GlyphBank`, `hyperwrite.py:71`), or letterforms minted from an
  image model (`MintedBank`, `hyperwrite.py:161`). Maths, table rules and joins are drawn as pen
  strokes, the letters are not. So "font mode" already exists and is the default; there is no
  stroke mode on `main`. An unfinished handwriting-synthesis stroke engine was found uncommitted
  in the working tree and parked on the local branch `wip/stroke-engine-2026-09-24`.

## Gap table

Verdicts: **port** (built here), **ours better** (kept as is), **skip** (with the reason).

### Hands

| # | Feature | Upstream | /handwrite today | Verdict |
|---|---|---|---|---|
| 1 | bundled fonts | Homemade Apple (default), Caveat, Liu Jian Mao Cao from the Google Fonts CDN (`index.html:197`) | 45 faces, including `homemade` (`hw_fonts.py:38`) and `caveat` (`hw_fonts.py:30`); no Liu Jian Mao Cao | **port** Liu Jian Mao Cao as `liujian` (OFL, Latin + Simplified Chinese) |
| 2 | Hindi | Kruti Dev as `fonts/Hindi_Type.ttf` (`css/index.css:38`): a legacy font that maps ASCII keys to Devanagari shapes, with no licence in the repo | Unicode Devanagari in Kalam and Playpen Sans Devanagari (`hw_fonts.py:31`, `:67`), chosen per character (`hw_fonts.py:102`) | **ours better**, and skip: the licence is unknown, and a legacy-encoded font turns real Unicode Hindi into the wrong letters |
| 3 | upload your own font | `.ttf`/`.otf` file input (`index.html:234`) loaded as a `FontFace` (`helpers.mjs:4`) | `--font path/to/hand.ttf` on the CLI (`hw_options.py:67`, `hw_fonts.py:235`); the site has no upload | **port** to the site: upload `.ttf`/`.otf`, render with it |
| 4 | font size | points, 10 by default, capped at 30 (`index.html:247`) | `--size` as x-height in mm, fitted to the ruling so lines cannot collide (`hw_options.py:71`, `geometry` in `hyperwrite.py:558`) | **ours better** |
| 5 | letter spacing | one px value for every letter (`index.html:310`) | `--letter-spacing` in em (`hw_options.py:72`) plus a different advance for each letter (`hw_ink.py:251`); the site maps it (`serve.py:50`) but shows no control | **port** the control to the site; engine **ours better** |
| 6 | word spacing | one px value for every gap (`index.html:300`) | `--word-space` (`hw_options.py:73`), each gap 0.72-1.28x of it (`hw_ink.py:155`); mapped in `serve.py:43`, no control | **port** the control to the site; engine **ours better** |
| 7 | baseline and letter jitter | none (see above) | baseline drift (`hyperwrite.py:241`, `hw_ink.py:215`), per-letter size and rotation (`hw_ink.py:175-176`), 14 warped forms per letter (`hyperwrite.py:133`) | **ours better**, nothing to port |
| 8 | vertical position | top padding in px (`index.html:295`) | `--margin-top` in mm (`hw_options.py:100`); no site control | **port** the control to the site |

### Page and paper

| # | Feature | Upstream | /handwrite today | Verdict |
|---|---|---|---|---|
| 9 | ink colour | blue `#000f55`, black, red `#ba3807` (`index.html:256`) | 21 named inks or any `#hex` (`hyperwrite.py:253`, `:271`) | **ours better** |
| 10 | page size | A4 only (`index.html:264`) | 12 sizes and `--landscape` (`hw_options.py:101`) | **ours better** |
| 11 | margin lines | a pink line 50 px from the top and the left, on or off (`css/index.css:242-250`) | each paper's real margin guides (`hw_paper.py:45`), `--no-margin-line` (`hw_options.py:95`) | **ours better** |
| 12 | ruled lines | grey rules every 1.5 em, so they move with the font size (`css/index.css:225`) | 23 papers at their printed pitch; the writing fits the rules, not the other way round | **ours better** |
| 13 | paper image | upload a JPG/PNG as the page background (`index.html:371`, `helpers.mjs:53`; marked experimental) | procedural paper and `--paper-color` (`hw_options.py:92`), no image | **port** as `--paper-image` on the CLI and an upload on the site |

### Page effects

| # | Feature | Upstream | /handwrite today | Verdict |
|---|---|---|---|---|
| 14 | Shadows (their default) | a linear gradient over the whole page at a random angle, `#0008` (53% black) to clear (`generate-utils.mjs:18`) | `--shading` (`hyperwrite.py:489`): the same idea at most 16% dark | **port** as `--effect shadows` and a `--shadow` strength, seeded |
| 15 | Scanner | that gradient held to 50-120 degrees so the lit side never lands on the margin, then a per-channel contrast of 0.55 (`generate-images.mjs:30`, `:180`): the look of a phone scanner app | `--capture scan` (`hyperwrite.py:369`) is a flatbed scan: noise, dust, a slight tilt, no contrast | **port** as `--effect scanner` and a `--contrast` knob |
| 16 | No effect | clean page | `--capture print` | parity |

### Output

| # | Feature | Upstream | /handwrite today | Verdict |
|---|---|---|---|---|
| 17 | resolution | html2canvas scale 0.8 to 4 (`index.html:278`) | `--dpi`, 150 to 600 (`hw_options.py:103`) | parity |
| 18 | long text | re-fills the div word by word until it overflows (`generate-images.mjs:45`) | pages cut at composed lines (`hw_doc.py:338`), Markdown blocks kept whole | **ours better** |
| 19 | save a page | a JPEG download under each page (`generate-utils.mjs:64`) | the CLI writes `.png`, `.jpg`, `.zip` or `.pdf` (`hw_options.py:33`); the site offers only the PDF (`web/index.html:229`) | **port** to the site: a download per page and a ZIP of all pages |
| 20 | PDF | jsPDF puts each page image inside A4 with 25/50 pt margins (`helpers.mjs:22`) | the page at its true size and dpi (`hw_options.py:35`, `serve.py:158`) | **ours better**: no second margin around the page |
| 21 | reorder or delete pages | move left, move right, remove (`generate-images.mjs:139`) | none | skip: pages follow the text, and a render is repeatable from its seed, so edit the text instead |
| 22 | draw a diagram | a mouse canvas whose drawing is put at the top of the page (`draw.mjs:82`) | `![alt](figure.png)` puts any image where the Markdown says (`hw_doc.py:67`) | skip the pad: this skill is driven by an agent and a CLI with no pointer, and an image file already lands anywhere in the text, not only at the top |
| 23 | paste | strips formatting on paste (`helpers.mjs:45`) | a plain textarea; formatting is Markdown | parity |
| 24 | dark mode | a toggle button | follows the system setting (`web/index.html:11`) | parity |
| 25 | network calls | Google Analytics, the GitHub contributors API, Google Fonts and jsPDF from CDNs (`index.html:5`, `:614`) | nothing leaves the machine (`serve.py` docstring) | skip, on purpose |
| 26 | tests | three Cypress checks of toggles (`tests/generateImage.spec.js`) | 15 regressions in `scripts/test.sh`, each a real bug | **ours better** |

## What was ported, and where

| Row | Flag or control | Code |
|---|---|---|
| 1 | `--font liujian` | `hw_fonts.py` catalog |
| 14, 15 | `--effect none\|shadows\|scanner`, `--shadow`, `--contrast` | `hw_effects.py` |
| 13 | `--paper-image PATH` | `hyperwrite.py` `make_paper` |
| 3, 5, 6, 8, 13, 14, 19 | font upload, paper upload, letter and word spacing, top margin, effect, per-page and ZIP download | `serve.py`, `web/index.html` |

Upstream's constants are kept where they define the look: the 53% shadow, the 50-120 degree
scanner angle and the 0.55 contrast. Credit is in `THIRD_PARTY.md`.
