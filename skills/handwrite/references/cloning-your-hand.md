# Cloning a specific person's handwriting

The `--preset henry` in this skill is an **approximation**, not a clone. It matches measurable
properties of Henry's writing — joined cursive, fine near-black pen, strong rightward lean,
sagging baseline, wide word gaps, unruled card — but the letterforms are Snell Roundhand's,
a formal copperplate. Henry's actual hand is quick and angular. Anyone who knows his writing
will not be fooled, and that is the honest ceiling of font-substitution.

To get his actual letterforms there are exactly two real routes.

---

## Route A — build a personal font (practical, works today)

You fill in a template with every glyph, the tool traces your strokes into outlines, and you
get a real `.ttf`. That file drops straight into this skill: `--font /path/to/HenryHand.ttf`.

| Tool | Cost | Notes |
|---|---|---|
| **[FontCrafter](https://arcade.pirillo.com/fontcrafter.html)** | free | Browser-based, processes locally, no account. Includes ligatures and contextual alternates — which matter a lot for cursive. |
| **[draw-your-font](https://baeseokjae.github.io/posts/draw-your-font-handwriting-to-font-claude-code-2026/)** | free, OSS | Node CLI, runs entirely locally, outputs TTF/WOFF/WOFF2. Released Jul 2026. |
| **[yashlamba/handwrite](https://github.com/yashlamba/handwrite)** | free, OSS | Python; generates a font from a filled sample sheet. |
| **[Calligraphr](https://www.calligraphr.com/en/)** | $8/mo | Mature, but uploads your writing to their servers. |
| **FontForge / BirdFont / Glyphr Studio** | free, OSS | Manual editors — use when you want to hand-correct specific glyphs afterwards. |

**What makes this work or fail for cursive:** a plain font renders each letter in isolation, so
`a` never touches `n`. Henry's writing is fully joined. The tools that survive this are the ones
supporting **contextual alternates and ligatures** — you supply entry/exit variants of each
letter and the font substitutes them based on neighbours. FontCrafter and Calligraphr both do;
a naive one-glyph-per-letter export will look like disconnected cursive, which reads worse than
honest print.

**The practical recipe:**
1. Print the tool's template. Fill every cell with a fine-tip black pen, at the size you
   normally write — not larger, or the proportions shift.
2. Write each letter **two or three times** where the tool allows variants. This is what buys
   per-glyph variation at the font level, on top of the jitter this skill already adds.
3. Add the joining variants if offered (initial / medial / final forms).
4. Export the TTF, then: `--font ~/Library/Fonts/HenryHand.ttf --messiness 0.7`
   Keep messiness *lower* than default — the font already carries real irregularity, so
   stacking full jitter on top double-counts it and looks drunk.

---

## Route B — few-shot style transfer (research-grade, closest fidelity)

These condition on a **reference image** rather than a filled template, and generate images of
text in that style with real joins and pen-lifts. This is what would actually reproduce Henry's
hand from `assets/henry-handwriting-reference.png`.

| Model | What it does |
|---|---|
| **One-DM** | Diffusion, conditions on a *single* reference sample. Closest fit to "here is one photo of my writing". |
| **DiffusionPen** | Latent diffusion with a style-image encoder (triplet + classification objective); open-set, so it generalises to writers it never trained on. |
| **VATr / VATr++** | Convolutional-transformer with a learned archetype book; strong on rare characters and unseen styles. |
| **HWT** | Transformer self-attention capturing local *and* global style. |
| **Emuru / Eruku** | Autoregressive latent-image generation; better zero-shot generalisation and length flexibility. |
| **GANwriting** | The original few-shot writer-conditioned work; largely superseded but the reference point. |

**The costs, stated plainly:** these output **raster images, not fonts**, so you lose selectable
text and clean PDF vectors. They need model weights (hundreds of MB to GB) and are slow on CPU.
Quality on out-of-vocabulary words and long lines varies. For notes, letters and mockups the
font route is faster and usually looks better; reach for this only when joined fidelity to a
*specific* person genuinely matters.

---

## The line this skill will not cross

Producing a convincing imitation of a *named individual's* handwriting is the same capability
whether it is used for a personal journal or a forged attestation. This skill is scoped to
Henry's own hand for his own documents.

The reference image supplied is an **academic honesty pledge** — a document whose entire
function is to be a personal attestation. Do not use a cloned hand to produce coursework,
exam answers, signed academic declarations, or any document that is meant to certify that a
specific person personally did something. That is not a limitation of the tooling; it is the
point of those documents.

Legitimate uses that motivated building this: personal notes and journals, letters and cards,
props and mockups, video assets, and accessibility (writing by hand when you cannot physically
write). Those are the cases to reach for it.
