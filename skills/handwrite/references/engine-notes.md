# Engine notes: scoring, tuning, cursive, minted hands, measuring a photo

Moved out of SKILL.md on 2026-09-24 when the front door grew the document, paper, maths and
photo features; the content below is unchanged from the 2026-09-21 version.

## Prove it, do not eyeball it

A PDF that exists is not a PDF that looks right, and file size proves nothing.

```bash
python3 scripts/judge.py notes.pdf-01.png            # forensic score + per-metric breakdown
python3 scripts/judge.py page.png --panel            # plus vision models, ~$0.001
```

`judge.py` measures five things a font page fails and a real pen page passes. Both band
anchors are **measured, not guessed** (`scripts/calibrate.sh` re-derives them):

| | pure font page | handtextai.com | hyperwrite | real pen on paper |
|---|---|---|---|---|
| forensic score | **31** | **74** | **68 ± 5** | **100** |

Scores move about ±5 between seeds, so a 3-point difference is noise. Trust
`glyph_uniqueness` (cv 0.03) and `ink_flatness` (cv 0.07); `line_start_px` moves 80% between
seeds and is weighted near zero for that reason.

`judge.py` works on **any** page image, including a competitor's, which is how the 67 above
was obtained.

## Tune against the score

```bash
python3 scripts/tune.py --file sample.txt --preset neat
```

Coordinate ascent over the knobs, ~50 renders, about two minutes. It prints the winning flags
and the page it produced.

🛑 **Then look at the page.** The score is gameable and the exploit is letter collision — a
tuner found it in 47 renders and scored 82.8/100 on a page nobody can read. `tune.py`'s grid
is now capped at values that have been rendered and inspected; **do not widen it** without
rendering the extremes yourself. Four automatic legibility gates were tried and all four
failed; `references/realism-model.md` records which and why.

## Cursive, colour, and a second pen

```bash
python3 scripts/hyperwrite.py --file notes.txt --out notes.pdf --seed 7 \
  --cursive 1.0 --ink "#1C2C7A" --corrections 0.05 --correct-ink red
```

**Cursive is not a font property here.** The engine finds where a pen would leave one letter
and enter the next — the ink nearest the baseline on each side of the glyph — and draws the
stroke between them. So joining works with **any** glyph set, including one minted from a
photo, and does not depend on a joined typeface whose advances never line up with its joins.
The join sags below the straight line, because a hand travelling right drops into the
baseline and comes back up; a straight connector reads as a typographic underscore.

`--corrections` gives the page a second pen. The page this engine was measured against
literally says *"First attempt in Black / Corrections in Blue"*.

Five smaller human marks are on by default and tunable: the **restart blob** where the nib
sat still before a word, **word pressure** (a word written slower is darker), the **heel
smudge** where the hand dragged through wet ink (`--smudge`), the **highlighter**, and
strike-throughs drawn as a real wobbling pen stroke rather than a rule.

## Copy a real hand from a photo

Someone hands you a photo of a page and says "like this". Measure it; do not eyeball it.

```bash
python3 scripts/measure.py ~/Downloads/page.HEIC --paper college --name my-hand \
  --save-upright upright.png
```

It deskews and crops the page out of a phone photo (HEIC included, via `sips`), then reports
the ink colour, the slant, the x-height **against the ruling** — the only absolute scale a
photo has — the word gap, the baseline wander, how much paper shows through the ink, and how
much of the verso bleeds through. It prints a ready `hyperwrite.py` command and a matching
`glyphmint.py` style prompt.

Then close the loop against that page rather than against the generic anchors:

```bash
python3 scripts/judge.py render.png --reference upright.png     # how close to THAT page
python3 scripts/tune.py --file s.txt --preset henry --reference upright.png
```

`--reference` changes the question from "does this read as handwritten" to "how near is this
to this specific page", scoring each metric by how many band-widths it is off. Without it the
tuner will happily walk away from the hand you are copying toward a generically better one.

🛑 **The match score cannot see letterforms.** It measures behaviour — ink, baseline, scale,
paper, capture. A render can match at 100 and still obviously be a different hand. Say so.

### The `henry` preset

Measured from a phone photo of a real page on 2026-09-21: college rule, black ballpoint,
slant −2°, show-through from a well-used notebook. Uses the `henry-notes` glyph set.

🛑 **Tuning it purely for the match score made it unreadable.** The tuner reached 81/100 and
produced a page whose own author called it terrible: at a 3.4 mm x-height, `--grain 0.5` with
`--pressure 1.3` and the warp at 0.16 bit holes in the strokes, so `product` read as
`produLt`, and the digits — which fell back to the font — came out as `3470` for `3410`. The
shipped numbers are the readable ones, chosen by looking, and they score **10/100 on the
match**. Readability is the constraint; the score is what gets maximised inside it.

```bash
python3 scripts/hyperwrite.py --file notes.txt --out notes.pdf --preset henry --seed 7
```

It reproduces the page's *character* — same ink, paper, scale, show-through, capture. It does
**not** reproduce the joined cursive in the photo: this engine draws separated letters, and
the minted alphabet came back as a tidy print hand. Matching joins needs a personal font or
stroke synthesis (`references/realism-model.md`).

## A new hand for 10 cents

A font gives you the hands somebody already drew. `glyphmint.py` gives you any hand you can
describe, by having a cheap image model write out a specimen sheet and segmenting it.

```bash
python3 scripts/glyphmint.py mint --name doctor-scrawl --repeats 3 \
  --style "loose, strongly right-slanted everyday handwriting" --ink "black fountain pen"
python3 scripts/glyphmint.py list
python3 scripts/glyphmint.py show --name doctor-scrawl      # contact sheet — LOOK at it
python3 scripts/hyperwrite.py --file x.txt --out x.pdf --glyphset doctor-scrawl --seed 9
```

`google/gemini-3.1-flash-lite-image` — the cheapest image model on OpenRouter — writes a
usable specimen sheet for **$0.034**, so a complete hand costs about **$0.10–$0.20, paid once**
and cached forever. `--good` switches to `gemini-3-pro-image` at $0.1375 a sheet, worth it only
if the cheap one keeps failing validation on a style you want.

🔑 **Be honest about what minting buys.** Measured 2026-09-21: the model writes its alphabet at
**0.94 intra-letter correlation** — it is, in effect, a font it drew on the spot. Minting gives
a *style* no font library has; it does **not** by itself raise letterform variety, and the
engine's warp is still what supplies that. With the warp matched, a minted hand scores 73.6
against 69.8 for the font path — a real gain, but from the combination, not the mint.

It mints **letters only**. The punctuation rows fail segmentation most of the time and their
stray marks used to contaminate the digit rows — "March 8, 2025" once rendered as
"March 8,, O, .". Digits and punctuation fall back to the font, where nobody can tell.

A set whose stored forms do not resemble each other is **rejected at mint time**, not saved: a
prompt pushed toward variability once produced a beautiful-looking 0.077 correlation that was
simply mislabelled letters. Always open the contact sheet.


## Tests and evals

```bash
bash scripts/test.sh          # 10 deterministic regressions, no network, ~30s
bash scripts/proof.sh         # the ship gate: CLI -> PDF -> score -> site round trip
claude plugin eval .          # 5 agent cases: render, score, mint, match a photo, and the line
```

`test.sh` is not decoration — **every test in it is a bug that actually happened on
2026-09-21**, including the one where the page came back transposed, the one where minted
capitals rendered as small caps, and the one where the tuner found it could win by making the
page illegible. Two of them were mutation-checked: reintroduce the bug and the test fails.

🔑 The first version of the transpose test was **vacuous** — it asserted the page was still
A4 portrait, but `Image.QUAD` always writes a W×H output whatever order its corners are in, so
it passed with the bug fully reintroduced. It now measures the text bands instead. If you add
a test here, reintroduce the bug and watch it fail before you believe it.

## Writing as a specific person

`--preset henry` (in the v1 engine) matches the *measurable* properties of Henry's hand, not
his letterforms — those belong to the font. Anyone who knows his writing sees it immediately.

For real letterforms: fill a Calligraphr template by hand, export a `.ttf`, then
`--font yourhand.ttf --wobble 0.8`. That fixes the letterforms instead of faking them, and it
is the single biggest remaining win — see `references/realism-model.md` for the measured gap
(`glyph_uniqueness` 0.62 for us against 0.31 for a real hand) and the stroke-synthesis route.

## Honest limits

- Font-based with per-glyph warping, not stroke synthesis. Letters do not truly join, because
  a warped outline cannot open a closed loop.
- It will not survive forensic examination and is not built to.
- Do not imitate a named person's hand, and do not produce anything meant to pass as a
  genuine signed or executed record.

## Known trap

`handwrite.py` (v1) silently dropped every page after the first on short-line documents —
equations, matrix rows, truth tables — until 2026-09-03. Check page count against input
length: `pdfinfo file.pdf | grep Pages`. `hyperwrite.py` does not share the bug and reports
its own page count in JSON.
