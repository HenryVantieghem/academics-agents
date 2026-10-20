#!/usr/bin/env python3
"""
handwrite.py — render text as a realistic handwritten page (PDF or PNG).

THE ONE IDEA THAT MAKES THIS LOOK HUMAN
A font renders every 'a' identically. A human never does. Everything below exists to
break that machine regularity in the specific ways a real hand does, and NOT in ways
it doesn't. Uniform random jitter on every glyph looks like a ransom note, not like
handwriting — the errors have to be CORRELATED.

So the model here is a hand that is:
  · drifting     — the baseline wanders on a slow smooth curve, not per-letter noise
  · tilting      — slant drifts per word, because your wrist angle changes per word
  · tiring       — jitter, slant and spacing all degrade further down the page
  · rushing      — words compress toward the right margin as you try to fit the line
  · inconsistent — per-glyph size/rotation vary a little, always around the drifting mean

Requires: reportlab. Fonts: Caveat (bundled on this Mac), or any TTF you pass.
"""
import argparse, math, os, random, sys, textwrap

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4, LETTER
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
except ImportError:
    sys.exit("reportlab required:  pip install reportlab")

# ---------------------------------------------------------------- fonts
FONT_CANDIDATES = {
    "caveat":       ["~/Library/Fonts/Caveat-Regular.ttf", "~/Library/Fonts/Caveat-Medium.ttf"],
    # Joined scripts — letters connect, which print-style hands like Caveat never do.
    "snell":        ["/System/Library/Fonts/Supplemental/SnellRoundhand.ttc"],
    "savoye":       ["/System/Library/Fonts/Supplemental/Savoye LET.ttc"],
    "bradley":      ["/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf"],
    "chalk":        ["/System/Library/Fonts/Supplemental/Chalkduster.ttf"],
    "brush":        ["/System/Library/Fonts/Supplemental/Brush Script.ttf"],
}

def resolve_font(name):
    """Return (registered_name, path). Falls back to the first font that exists."""
    order = [name] + [k for k in FONT_CANDIDATES if k != name]
    for key in order:
        for p in FONT_CANDIDATES.get(key, []):
            p = os.path.expanduser(p)
            if os.path.exists(p):
                reg = f"hw_{key}"
                try:
                    if p.lower().endswith(".ttc"):
                        pdfmetrics.registerFont(TTFont(reg, p, subfontIndex=0))
                    else:
                        pdfmetrics.registerFont(TTFont(reg, p))
                    return reg, p
                except Exception:
                    continue
    # a raw path was passed
    p = os.path.expanduser(name)
    if os.path.exists(p):
        pdfmetrics.registerFont(TTFont("hw_custom", p))
        return "hw_custom", p
    sys.exit(f"no usable font found (tried {name} and built-ins)")

# ---------------------------------------------------------------- smooth noise
class Drift:
    """Value-noise: smooth, correlated wander. Random per-glyph noise reads as a ransom
    note; a real baseline moves slowly, so we interpolate between anchor points."""
    def __init__(self, rng, scale=1.0, step=7.0):
        self.rng, self.scale, self.step = rng, scale, step
        self.anchors = {}

    def _anchor(self, i):
        if i not in self.anchors:
            self.anchors[i] = self.rng.uniform(-1, 1)
        return self.anchors[i]

    def at(self, t):
        x = t / self.step
        i = math.floor(x)
        f = x - i
        f = f * f * (3 - 2 * f)                      # smoothstep
        return (self._anchor(i) * (1 - f) + self._anchor(i + 1) * f) * self.scale

# ---------------------------------------------------------------- the hand
class Hand:
    def __init__(self, c, font, size, rng, messiness=1.0, page_h=842, slant=0.0, sag=0.0):
        self.c, self.font, self.size, self.rng = c, font, size, rng
        self.m = messiness
        self.page_h = page_h
        self.slant_bias = slant   # constant lean, in degrees — a person's habitual angle
        self.sag = sag            # how far the line droops from left margin to right
        self.baseline = Drift(rng, scale=1.4 * self.m, step=9)     # vertical wander
        self.slant    = Drift(rng, scale=2.2 * self.m, step=26)    # wrist angle per word
        self.weight   = Drift(rng, scale=0.13, step=15)            # ink/pressure

    def fatigue(self, y):
        """Handwriting degrades down a page. 1.0 at the top, ~1.6 by the bottom —
        the single cheapest cue that a human wrote this and got tired doing it."""
        frac = 1.0 - (y / self.page_h)
        return 1.0 + 0.6 * max(0.0, min(1.0, frac))

    def draw_word(self, word, x, y, ink, squeeze=1.0):
        """Draw one word glyph-by-glyph. Returns the advance width actually used."""
        c, rng = self.c, self.rng
        fat = self.fatigue(y)
        word_slant = self.slant_bias + self.slant.at(x) * fat
        cursor = x
        for ch in word:
            gsize = self.size * rng.uniform(0.965, 1.035)           # letter size varies
            # sag: unruled writing droops as the hand travels right — very personal, very visible
            sag_dy = -self.sag * ((cursor - 92) / 420.0)
            dy    = self.baseline.at(cursor) * fat + sag_dy + rng.gauss(0, 0.45 * self.m * fat)
            rot   = word_slant + rng.gauss(0, 0.9 * self.m * fat)   # per-letter around word slant
            # Pressure: ballpoint darkens and lightens as you push. Small, or it looks fake.
            k = max(0.0, min(1.0, 0.5 + self.weight.at(cursor)))
            r, g, b = ink
            c.setFillColorRGB(r * (0.82 + 0.30 * k), g * (0.82 + 0.30 * k), b * (0.85 + 0.28 * k))
            c.saveState()
            c.translate(cursor, y + dy)
            c.rotate(rot)
            c.setFont(self.font, gsize)
            c.drawString(0, 0, ch)
            c.restoreState()
            adv = pdfmetrics.stringWidth(ch, self.font, gsize)
            # inter-letter spacing tightens as the hand tires and as the line runs out
            cursor += adv * squeeze + rng.gauss(0.15, 0.35 * self.m) - (fat - 1.0) * 0.35
        return cursor - x

# ---------------------------------------------------------------- paper
RULE_TOP = 96          # y of the first ruled line, measured from the top
def rule_gap(style):
    """One number governs the ruling AND the writing baseline. When these drift apart the
    text floats between the lines, which instantly reads as printed-not-written."""
    return 24 if style == "college" else 28

def draw_paper(c, W, H, style, rng):
    if style == "blank":
        return
    c.setFillColorRGB(0.992, 0.988, 0.972)          # warm sheet, never pure white
    c.rect(0, 0, W, H, stroke=0, fill=1)
    if style in ("ruled", "college"):
        gap = rule_gap(style)
        c.setStrokeColorRGB(0.72, 0.78, 0.86)
        c.setLineWidth(0.55)
        y = H - RULE_TOP
        while y > 56:
            c.line(52, y, W - 40, y)
            y -= gap
        c.setStrokeColorRGB(0.90, 0.62, 0.62)       # margin rule
        c.setLineWidth(0.7)
        c.line(76, H - 40, 76, 40)
    if style == "grid":
        c.setStrokeColorRGB(0.80, 0.84, 0.90); c.setLineWidth(0.4)
        for gx in range(40, int(W) - 30, 18): c.line(gx, 40, gx, H - 40)
        for gy in range(40, int(H) - 30, 18): c.line(40, gy, W - 40, gy)


# ---------------------------------------------------------------- presets
# A preset captures one person's hand as a set of correlated settings, because
# "which font" is only a fraction of what makes handwriting recognisable.
PRESETS = {
    # Henry — measured from assets/henry-handwriting-reference.png (1972x1372):
    # joined cursive, fine-tip near-black ink (coverage 3.6%, darkness 46), off-white
    # unruled card (tone 203), strong rightward slant, generous word gaps, long
    # terminal flourishes, and a baseline that sags noticeably left-to-right.
    "henry": dict(font="snell", size=19, ink="black", paper="blank",
                  messiness=0.85, slant=9.0, sag=2.4, word_gap_mult=0.46),
}

INKS = {"blue": (0.12, 0.18, 0.48), "black": (0.10, 0.10, 0.12),
        "darkblue": (0.06, 0.11, 0.35), "pencil": (0.32, 0.32, 0.34)}

# ---------------------------------------------------------------- page render
def render(text, out, font="caveat", size=17, ink="blue", paper="ruled",
           messiness=1.0, seed=None, pagesize="a4", corrections=0.0, title=None,
           slant=0.0, sag=0.0, word_gap_mult=0.30):
    rng = random.Random(seed)
    fontname, fontpath = resolve_font(font)
    W, H = A4 if pagesize.lower() == "a4" else LETTER
    c = canvas.Canvas(out, pagesize=(W, H))
    ink_rgb = INKS.get(ink, INKS["blue"])

    left, right = 92, W - 52
    gap = rule_gap(paper)
    # Sit the baseline ON the rule (a hair above it, as a pen nib does), not between rules.
    y = H - RULE_TOP - 2
    word_gap = size * word_gap_mult    # one honest word space, jittered per word below

    def new_page():
        nonlocal y
        c.showPage()
        draw_paper(c, W, H, paper, rng)
        y = H - RULE_TOP - 2

    draw_paper(c, W, H, paper, rng)
    hand = Hand(c, fontname, size, rng, messiness, page_h=H, slant=slant, sag=sag)

    if title:
        hand.size = size * 1.22
        hand.draw_word(title, left, y, ink_rgb)
        hand.size = size
        y -= gap * 1.4

    for para in text.split("\n"):
        if not para.strip():
            y -= gap * 0.7
            if y < 62:
                new_page()
            continue
        words, line, widths = para.split(), [], 0.0
        for w in words:
            ww = pdfmetrics.stringWidth(w, fontname, size) + word_gap
            if widths + ww > (right - left) and line:
                # A human does not hyphenate — they squeeze the last words in.
                squeeze = min(1.0, (right - left) / max(widths, 1)) * rng.uniform(0.985, 1.0)
                x = left
                for wd in line:
                    used = hand.draw_word(wd, x, y, ink_rgb, squeeze)
                    x += used + word_gap * squeeze + rng.gauss(0, 0.9 * messiness)
                y -= gap * rng.uniform(0.985, 1.015)
                if y < 62:
                    new_page()
                line, widths = [], 0.0
            line.append(w); widths += ww
        if line:
            x = left
            for wd in line:
                used = hand.draw_word(wd, x, y, ink_rgb)
                x += used + word_gap + rng.gauss(0, 0.9 * messiness)
                # A struck-out word then rewritten is the most human artefact there is.
                if corrections and rng.random() < corrections:
                    c.setStrokeColorRGB(*ink_rgb); c.setLineWidth(0.9)
                    c.line(x - used, y + size * 0.28, x - 2, y + size * 0.34)
            y -= gap * rng.uniform(0.985, 1.015)
            if y < 62:
                new_page()

    c.save()
    return out


def main():
    a = argparse.ArgumentParser(description="Render text as realistic handwriting.")
    a.add_argument("--text"); a.add_argument("--file"); a.add_argument("--out", required=True)
    a.add_argument("--font", default="caveat"); a.add_argument("--size", type=float, default=17)
    a.add_argument("--ink", default="blue", choices=list(INKS))
    a.add_argument("--paper", default="ruled", choices=["ruled", "college", "grid", "blank"])
    a.add_argument("--messiness", type=float, default=1.0, help="0.4 neat … 1.8 scrawl")
    a.add_argument("--corrections", type=float, default=0.0, help="0-0.05 strike-through rate")
    a.add_argument("--seed", type=int, default=None, help="same seed = same hand")
    a.add_argument("--pagesize", default="a4"); a.add_argument("--title")
    a.add_argument("--preset", choices=list(PRESETS),
                   help="a whole hand at once (font+size+slant+ink+paper). e.g. --preset henry")
    a.add_argument("--slant", type=float, default=0.0, help="habitual lean in degrees")
    a.add_argument("--sag", type=float, default=0.0, help="line droop left-to-right (unruled)")
    ns = a.parse_args()

    if ns.file:
        text = open(os.path.expanduser(ns.file), errors="replace").read()
    elif ns.text:
        text = ns.text
    else:
        text = sys.stdin.read()
    if not text.strip():
        sys.exit("no text given (--text, --file, or stdin)")

    cfg = dict(font=ns.font, size=ns.size, ink=ns.ink, paper=ns.paper,
               messiness=ns.messiness, slant=ns.slant, sag=ns.sag, word_gap_mult=0.30)
    if ns.preset:
        # The preset supplies the hand; anything explicitly passed on the CLI still wins,
        # so `--preset henry --ink blue` writes Henry's hand in a blue pen.
        given = {a[2:].split("=")[0] for a in sys.argv if a.startswith("--")}
        for k, v in PRESETS[ns.preset].items():
            if k not in given:
                cfg[k] = v
    out = render(text, os.path.expanduser(ns.out), cfg["font"], cfg["size"], cfg["ink"],
                 cfg["paper"], cfg["messiness"], ns.seed, ns.pagesize, ns.corrections,
                 ns.title, cfg["slant"], cfg["sag"], cfg["word_gap_mult"])
    print(f"wrote {out}  ({os.path.getsize(out):,} bytes)")


if __name__ == "__main__":
    main()
