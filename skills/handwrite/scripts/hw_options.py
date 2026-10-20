#!/usr/bin/env python3
"""
hw_options — hyperwrite's command line, its realism presets, and page export.

Every knob handtextai exposes has a flag here; `hyperwrite.py --help` lists them all.
"""
import argparse, io, os

import hw_effects, hw_paper

PAGE_MM = hw_paper.PAGE_MM
HIGHLIGHT_NAMES = ("yellow", "green", "pink", "orange", "blue")

# handtextai's five realism steps (REALISM_PRESETS in their bundle: word placement, line starts,
# line spacing, ink amount, letter variation), mapped onto this engine's knobs. "off" is their
# "perfectly even writing"; "lifelike" is everything on. Explicit flags still win.
REALISM = {
    "off":       dict(messiness=0.2, wobble=0.12, variants=2, drift=0.04, linestart=0.1,
                      pressure=0.15, skip=0.0, bleed=0.35, pool=0.3, grain=0.08, smudge=0.0,
                      restart=0.1, showthrough=0.0, capture="print"),
    "subtle":    dict(messiness=0.45, wobble=0.45, variants=6, drift=0.12, linestart=0.4,
                      pressure=0.45, skip=0.08, smudge=0.2, showthrough=0.3, capture="print"),
    "natural":   dict(messiness=0.75, wobble=0.85, variants=10, drift=0.25, linestart=0.8,
                      pressure=0.8, skip=0.2, capture="scan"),
    "realistic": dict(messiness=1.0, wobble=0.95, variants=14, drift=0.34, pressure=1.0,
                      skip=0.35, ink_flow=0.5, capture="scan"),
    "lifelike":  dict(messiness=1.15, wobble=1.05, variants=20, drift=0.4, pressure=1.1,
                      skip=0.4, grain=0.35, ink_flow=0.8, shading=0.4, capture="photo"),
}



def save_pages(imgs, out, dpi, quality):
    low = out.lower()
    if low.endswith(".pdf"):
        imgs[0].save(out, "PDF", resolution=dpi, save_all=True, append_images=imgs[1:],
                     quality=quality)
        return [out]
    if low.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for i, im in enumerate(imgs):
                b = io.BytesIO()
                im.save(b, "PNG")
                z.writestr(f"page-{i+1:02d}.png", b.getvalue())
        return [out]
    kw = {"quality": quality} if low.endswith((".jpg", ".jpeg")) else {}
    if len(imgs) == 1:
        imgs[0].save(out, **kw)
        return [out]
    stem, ext = os.path.splitext(out)
    paths = []
    for i, im in enumerate(imgs):
        paths.append(f"{stem}-{i+1:02d}{ext}")
        im.save(paths[-1], **kw)
    return paths


def build_parser():
    ap = argparse.ArgumentParser(description="hyperrealistic handwriting pages")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--text"); src.add_argument("--file")
    ap.add_argument("--out", required=True, help=".pdf, .png, .jpg or .zip")
    ap.add_argument("--plain", action="store_true", help="treat the text as prose, no Markdown")
    # Reenie Beanie, not Caveat: on the five parity inputs a vision judge rated it 9/10 natural
    # against Caveat's 6 at the same legibility (2026-09-24). Offline it falls back to Caveat.
    ap.add_argument("--font", default="reenie",
                    help="a catalog face (hw_fonts.py list), a macOS face, or a path to a .ttf")
    ap.add_argument("--no-fallback", dest="fallback", action="store_false",
                    help="do not borrow glyphs from other hands for other scripts")
    ap.add_argument("--size", type=float, default=4.6, help="x-height in mm (4.0 small, 5.5 large)")
    ap.add_argument("--letter-spacing", type=float, default=0.0, help="extra per letter, in em")
    ap.add_argument("--word-space", type=float, default=1.35)
    ap.add_argument("--line-height", type=float, default=None,
                    help="line pitch in em on unruled paper (ruled paper uses its ruling)")
    ap.add_argument("--align", default="left", choices=("left", "center", "right"))
    ap.add_argument("--hyphenate", action="store_true")
    ap.add_argument("--ink", default="blue",
                    help="a named ink or any hex colour, e.g. purple or \"#4B2E83\"")
    ap.add_argument("--cursive", type=float, default=0.0, nargs="?", const=1.0,
                    help="join the letters up; 0 off, 1 normal, 1.6 a loopier hand")
    ap.add_argument("--corrections", type=float, default=0.0,
                    help="rate of struck-through words, e.g. 0.03")
    ap.add_argument("--correct-ink", default="blue", help="the pen the corrections are made in")
    ap.add_argument("--highlight", default=None, choices=sorted(HIGHLIGHT_NAMES),
                    help="run a highlighter under all the text (==text== marks just a phrase)")
    ap.add_argument("--restart", type=float, default=1.0,
                    help="how much heavier the first letter of a word is")
    ap.add_argument("--smudge", type=float, default=0.6,
                    help="the heel of the hand dragging through wet ink")
    ap.add_argument("--paper", default="college", choices=sorted(hw_paper.PAPERS))
    ap.add_argument("--paper-color", default=None,
                    help=f"{', '.join(sorted(hw_paper.PAPER_COLORS))}, or #hex")
    ap.add_argument("--rule-color", default=None, help="#hex colour for the printed rules")
    ap.add_argument("--paper-image", default=None,
                    help="a .png or .jpg used as the sheet, fitted to cover the page; the "
                         "--paper ruling is drawn on top (plain or blank draws none)")
    ap.add_argument("--no-margin-line", dest="margin_line", action="store_false", default=None)
    ap.add_argument("--holes", action="store_true", help="three-hole punched sheet")
    ap.add_argument("--mirror", action="store_true",
                    help="swap the margins on even pages, like the back of a sheet")
    for side in ("top", "right", "bottom", "left"):
        ap.add_argument(f"--margin-{side}", type=float, default=None, help="mm")
    ap.add_argument("--pagesize", default="a4", choices=sorted(PAGE_MM))
    ap.add_argument("--landscape", action="store_true")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--quality", type=int, default=92, help="JPEG and PDF quality")
    ap.add_argument("--realism", default=None, choices=sorted(REALISM),
                    help="handtextai's five steps, off -> lifelike")
    ap.add_argument("--messiness", type=float, default=1.0)
    ap.add_argument("--slant", type=float, default=0.0, help="habitual lean, degrees")
    ap.add_argument("--sag", type=float, default=0.0, help="line droop, x-heights, unruled hands")
    ap.add_argument("--variants", type=int, default=14, help="distinct forms per letter")
    # 1.1 scored better on the forensic judge and closed the eye of every `e`: "heads" read as
    # "hoads" (2026-09-24). Legibility is the constraint, so the default is the readable one.
    ap.add_argument("--wobble", type=float, default=0.85, help="how different those forms are")
    ap.add_argument("--bleed", type=float, default=1.0)
    ap.add_argument("--pool", type=float, default=1.0)
    ap.add_argument("--skip", type=float, default=0.35)
    ap.add_argument("--ink-flow", type=float, default=0.0,
                    help="the pen running dry and flooding along the page, 0..2.5")
    ap.add_argument("--drift", type=float, default=0.34,
                    help="how far the baseline wanders, in x-heights per ~5 em")
    ap.add_argument("--linestart", type=float, default=1.0,
                    help="how much each line start scatters off the margin")
    ap.add_argument("--pressure", type=float, default=1.0,
                    help="how much the pen weight swings; 0 = flat fill")
    ap.add_argument("--grain", type=float, default=0.22, help="paper visible through the ink")
    ap.add_argument("--texture", type=float, default=1.0, help="paper fibre strength, 0..3")
    ap.add_argument("--shading", type=float, default=0.0, help="uneven light across the sheet, 0..1")
    ap.add_argument("--blur", type=float, default=0.0, help="soft focus, 0..1.5")
    ap.add_argument("--effect", default="none", choices=sorted(hw_effects.EFFECTS),
                    help="text-to-handwriting's page effects: shadows (a gradient shadow across "
                         "the page) or scanner (a side shadow, then a scanner app's contrast)")
    ap.add_argument("--shadow", type=float, default=0.0,
                    help="gradient shadow strength, 1 = text-to-handwriting's")
    ap.add_argument("--contrast", type=float, default=0.0,
                    help="contrast boost, 0.55 = text-to-handwriting's scanner")
    ap.add_argument("--showthrough", type=float, default=1.0, help="verso bleed from page n-1")
    ap.add_argument("--capture", default="scan", choices=("print", "scan", "photo"))
    ap.add_argument("--mode", default="print", choices=("print", "photo"),
                    help="photo places each page into a desk scene (hw_scene.py)")
    ap.add_argument("--scene", default="random", help="a plate name from assets/scenes, or random")
    ap.add_argument("--view", default="closer", choices=("wide", "closer", "closest"))
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--max-pages", type=int, default=60)
    ap.add_argument("--no-fit", dest="fit", action="store_false",
                    help="render even when the writing is too big for the ruling")
    ap.add_argument("--preset", default=None)
    ap.add_argument("--glyphset", default=None,
                    help="a minted alphabet from glyphmint.py — real letterforms, not a font")
    return ap
