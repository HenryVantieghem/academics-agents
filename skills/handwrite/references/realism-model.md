# What actually makes a page read as handwritten

Written from measurements taken 2026-09-21 while building `scripts/hyperwrite.py`. Every
claim here is one the forensic judge can check; nothing in it is aesthetic opinion.

## The three axes, in order of how much they buy

### 1. Letterform variety — the cue nobody can name

A font draws every `a` from one outline. People spot this in under a second and cannot say
why. Rotating the outline does not help: a rotated `a` is still the same `a`.

The fix is to render each letter several times through a **different low-frequency
displacement field**, so the third `e` on a line is a genuinely different shape from the
first. `GlyphBank` keeps N such variants per character and picks one at random per instance.

Measured, `glyph_uniqueness` = mean correlation between each glyph blob and its nearest
same-proportion twin on the page:

| | |
|---|---|
| pure font page | **0.945** — near-identical twins everywhere |
| handtextai.com | 0.617 |
| hyperwrite | 0.616 |
| real pen on paper | **0.312** |

We match the best commercial tool and we are still a long way from a real hand. That gap is
structural and worth being honest about: a human varies a letter's *topology* (an `a` with an
open loop, then a closed one). Warping an outline cannot open a closed loop. Closing the rest
of that gap needs stroke synthesis or a personal font, not more warp — see the last section.

### 2. Ink physics — the cue that survives zooming in

Flat fill is the giveaway at 100% zoom. Real ink:

- **varies in darkness along a stroke** as the pen pressure swings on a slow wave
- **pools** where the nib slowed — stroke ends, tight turns, crossings
- **bleeds** a soft low-opacity halo into the paper's fibres
- **skips**, in rare thin slivers, if it is a ballpoint
- lets the **paper grain show through**; ink sits in the tooth, it does not cover it

`ink_flatness` = std/mean of ink density inside eroded stroke cores.
Font page **0.025** · hyperwrite **0.096** · real hand **0.087**. We are at the real number.

The last point is the one most renderers miss. Covering the paper with an opaque fill is what
makes a scan look composited. `composite()` tints the paper toward the ink colour instead.

### 3. Correlated error — why jitter alone produces a ransom note

Realism is not the *size* of the error, it is its **correlation**. A hand's baseline wanders
on a slow curve; its wrist angle changes between words, not between letters; the writing
degrades down the page as the hand tires; the last word of a line gets crammed in rather
than hyphenated.

Sprinkle independent random jitter on each glyph and you get every letter wrong in an
unrelated direction — which reads as a ransom note, not as handwriting. `Drift` is value
noise (smoothstep between random anchors) for exactly this reason.

`baseline_wander` = per-line detrended residual amplitude **times** its lag-1 autocorrelation.
A font scores ~0 (no wander). Uniform jitter also scores ~0 (wander, but each sample
disagrees with the last). Only a hand scores high.

> A spectral low/high energy ratio was tried for this first and **does not discriminate** —
> on a straight baseline the residual is rounding noise and the ratio of two tiny numbers is
> meaningless. It ranked a font page *above* a real hand. Amplitude × autocorrelation is the
> honest version.

### 4. Capture — the artefact is a photo of the page, not the page

A clean render of a perfect page is still obviously a render. `--capture scan` adds a fraction
of a degree of rotation, a lighting gradient, sensor noise and dust; `--capture photo` adds
keystone, a light falloff from one corner, and focus softening. `--capture print` is for when
the output is genuinely going to a printer.

## The trap: the score is gameable, and here is how

Measured 2026-09-21. A tuning loop searching `--wobble` up to 2.0 found in 47 renders that
**letter collision raises `glyph_uniqueness` and `ink_flatness` at the same time** — merged
blobs have no twins and their overlapping ink is not flat. It scored **82.8/100 on a page
nobody can read.**

Four legibility gates were tried against it and all four failed:

| gate | result |
|---|---|
| tesseract OCR agreement | 0.77 on a clean font page, **0.01 on both a legible handwritten page and an illegible one** — it is trained on print and fails them equally |
| vision-model read-back | **0.88 on the illegible page** — the model guesses the words from context |
| glyph width ÷ height | mush **0.92**, real hand 1.14 — the merged blobs were tall as well as wide, so the ratio moved the wrong way |
| adjacent-ink x-overlap, measured in the renderer | separates a font (0.006) from handwriting (0.032) but **not** legible handwriting from illegible (0.042) |

So the bad state is made **unreachable rather than detectable**: `tune.py`'s grid is capped at
values that have been rendered and looked at. `--wobble` above ~1.3 is where it starts to go.

The general lesson, which outlives this skill: *when a quality score can be won by breaking
the artefact, cap the search space — do not add a fifth detector.*

## Minting an alphabet from an image model — what it does and does not buy

Measured 2026-09-21, and the result was not what was expected.

**It works, and it is cheap.** Asked for a specimen sheet — a few rows of separated letters on
plain paper, the set written out three times — `google/gemini-3.1-flash-lite-image`, the
cheapest image model on OpenRouter, returns a clean, correctly-spelled, segmentable page of
genuine handwriting for **$0.034**. A complete hand is about **$0.10–$0.20, paid once**.
`scripts/glyphmint.py` segments it into per-character crops with a measured baseline and
x-height, and `hyperwrite.py --glyphset <name>` renders from them.

**It does not raise letterform variety.** The forms the model stores for one character
correlate at **0.94** with each other — it writes its alphabet like a font. Rendered naively
the minted set scored *worse* than the warped-font path (`glyph_uniqueness` 0.81 vs 0.67),
because a font path with 20 warped variants out-varies three near-identical real ones. Only
once the minted path's warp was raised to match the font path's amplitude did it come out
ahead: **0.62 vs 0.67, score 73.6 vs 69.8.** The gain is from the combination, not the mint.

So the honest framing: **minting buys STYLE, the warp buys VARIETY.** What it gives you that
no font library does is any hand you can describe in a sentence, in ten minutes, for pennies.

Three traps, each of which cost a render:

- **Pushing the prompt toward variability destroys the sheet.** A prompt asking for "the same
  letter noticeably different each time" came back unsegmentable; the resulting set scored a
  spectacular 0.077 intra-letter correlation, which looked like a triumph until the contact
  sheet was opened and a `g` was filed under `h`. `glyphmint.py` now **rejects** any set below
  0.40 rather than saving it. Always open the contact sheet.
- **A row of capitals contains no x-height letter**, so its median glyph height *is* the cap
  height. Storing that as the x-height rendered every capital at lowercase size — the first
  minted page came out in small caps. Rows without an x-height letter now divide by a measured
  cap ratio of 1.42.
- **Punctuation cannot be segmented reliably.** A comma and a speck are the same shape and
  size, so a failed punctuation row donates its stray marks to whatever row validates next —
  "March 8, 2025" rendered as "March 8,, O, .". Letters only; digits and punctuation fall back
  to the font, where nobody can tell.

## Where the remaining gap is

`glyph_uniqueness` 0.62 (us) vs 0.31 (a real hand) is the whole remaining distance, and warp
cannot close it. The three real routes, in increasing order of effort:

1. **A personal font.** Fill a Calligraphr / FontCrafter template by hand, get a `.ttf`, then
   `--font yourhand.ttf --wobble 0.8`. Cheap, and it fixes letterforms rather than faking them.
2. **A font with real alternates.** Some handwriting faces ship 3–4 variants per glyph via
   OpenType `salt`/`calt`. Cycling real alternates beats warping a single outline.
3. **Stroke synthesis.** Graves-style RNN (`handwriting-synthesis`), or the diffusion line —
   DiffusionPen (5-shot, `github.com/koninik/DiffusionPen`), One-DM (one reference sample,
   ECCV 2024), InkSpire (ICLR 2026, FLUX-based masked inpainting of whole pages). These draw
   pen paths, so they get true joins, pen-lifts and topology variation. They need a model
   download and a GPU to be quick, and none of them will lay out a 40-page PDF for you —
   the right shape is to use one for the *glyphs* and keep this engine for the *page*.

## The line

This is for notes, study material, mockups, props and documents that should feel personal.
It will not survive forensic examination and is not built to. Do not use it to imitate a
named person's hand, and do not produce anything meant to pass as a genuine signed or
executed record.
