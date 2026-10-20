# handtextai.com — what it actually is

Feature-by-feature gap table and the side-by-side, 2026-09-24: `handtextai-parity.md`.

Measured 2026-09-21 by pulling the homepage and its 33 turbopack chunks and reading them.
Everything below is quoted from shipped code, not inferred from marketing copy.

## The one-line answer

It is **a font renderer with jitter**, served from a Next.js app. There is no handwriting
model. The word "AI" on the homepage refers to the optional LLM that writes your *text* for
you ("AI Writer"), not to anything that draws.

The proof is `/api/fonts/upload`. A site that synthesised strokes would have no reason to
accept a `.ttf`.

## Architecture

| Layer | What it is |
|---|---|
| Frontend | Next.js (turbopack), TipTap / ProseMirror rich-text editor, KaTeX for maths |
| Auth | NextAuth (`errors.authjs.dev` in the bundle), plan gating via `/api/entitlements` |
| Generate | `POST /api/generate`, **multipart FormData**, returns an array of page images |
| PDF | `/api/pdf` assembles those images; `/api/preview` is the same path at low resolution |
| Fonts | `/api/fonts`, `/api/fonts/upload` — 40+ bundled faces plus user `.ttf` upload |
| Import | `/api/import/process` for PDF/DOCX in |
| Storage | `/api/documents/{save,save-pages,list,latest}`, assets at `/api/assets/generated/…` |

Rendering is **server side to raster**, then the rasters are stitched into a PDF. The editor
never draws the handwriting; it only holds the text and the settings.

## The request contract

```
POST /api/generate            multipart/form-data
  text            = <html from the TipTap editor>
  settings        = <json, below>
  settings_hash   = <client-computed cache key>
  existing_generation_id, existing_page_count   (incremental re-render)
```

```jsonc
{
  "paper": { "format_id", "orientation": "portrait", "style_id", "template_id",
             "random_template_scenes": false, "template_scene_start_side": "left",
             "template_scene_include_opening_page": false,
             "template_scene_framing": "closest", "mirror_paper_background": false },
  "font":  { "family", "size": 26, "line_height": 1.3,
             "letter_spacing": 0, "word_spacing": 0 },
  "effects": {
    "realism_preset": "off",              // or "custom" once any flag below is on
    "enable_handwriting_variation": false, "handwriting_variation_amount": 0,
    "enable_word_placement":        false, "word_placement_amount":        0,
    "enable_natural_line_starts":   false, "natural_line_starts_amount":   0,
    "enable_natural_line_spacing":  false, "natural_line_spacing_amount":  0,
    "enable_blur":          false, "blur_amount":    0.25,
    "enable_paper_shading": false, "shading_amount": 0.2,
    "enable_paper_texture": false, "paper_texture":  1,
    "enable_text_fade":     false, "ink_amount":     0,
    "texture_amount": 0.25
  },
  "general": { "margin_left/right/top/bottom", "margin_*_even", "margin_mirror": false,
               "enable_letter_rotation": false, "letter_rotation_range": 2,
               "enable_hyphenation": false, "enable_random_indentation",
               "enable_random_line_spacing", "enable_word_rotation",
               "scale_factor": 3, "paragraph_spacing": 0,
               "margin_mode": "style", "transparent": false }
}
```

`scale_factor: 3` is the supersample. `variation_seed` also appears, so their output is
seeded like ours.

## Their realism ceiling, from their own flag names

That list is the whole model. It amounts to:

1. rotate each letter by up to **2 degrees** (`letter_rotation_range: 2`)
2. jitter word placement, line starts and line spacing
3. blur the page a little
4. lay a paper texture and a shading gradient over it
5. fade the ink globally (`ink_amount`)

Every `a` on the page is **the same outline**, rotated. Nothing in the contract varies a
letterform, varies ink along a stroke, or models the hand getting tired. `enable_text_fade`
is a single global ink level, not pressure. There is no bleed, no pooling, no show-through,
no capture model beyond `blur`.

This is why their pages are good but not convincing: they got the *layout* statistics right
and left the *ink* and the *letterforms* alone.

## Scored on our own forensic scale

`scripts/judge.py`, same run, 2026-09-21. Their number comes from the preview on their own
homepage, so treat it as approximate — it is a screen render, upscaled, not a downloaded PDF.

| | glyph_uniqueness ↓ | ink_flatness ↑ | baseline_wander ↑ | score |
|---|---|---|---|---|
| pure font page (control) | 0.945 | 0.025 | 0.016 | **31** |
| handtextai preview | 0.617 | 0.328* | 0.029 | **74** |
| `hyperwrite` (tuned) | 0.616 | 0.096 | 0.041 | **69 ± 5** |
| real pen on paper (control) | 0.312 | 0.087 | 0.055 | **100** |

\* inflated by the 2x upscale of the screenshot crop — soft edges read as ink variance.
Their honest figure is lower; do not quote 0.328 as measured from their PDF.

## What to take, and what to beat

**Take:**
- the settings decomposition (`paper` / `font` / `effects` / `general`) — it is clean, and
  `hyperwrite`'s flags map onto it almost one to one
- server-side raster then stitch, not client canvas
- `settings_hash` + `existing_generation_id`, so editing page 7 does not re-render 1–6
- custom `.ttf` upload as the answer to "make it look like MY handwriting"
- paper "scenes" (a photo of a notebook on a desk) as a separate output mode from print

**Beat:** letterform variety, ink physics, and capture. Those are the three things their
contract has no field for, and they are the three that decide whether a page survives a
second look. See `references/realism-model.md`.
