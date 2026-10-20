"""Verso bleed must be a faint smudge, never readable mirrored text.

Measured 2026-09-21: a blur radius of dpi/150 is about one pixel, and page one's writing
arrived on the back of page two MIRRORED AND READABLE. The spread has to scale with the
writing, not with the resolution.

Pixel-differencing two renders was tried first and does NOT isolate the bleed: page two's
own glyphs land a sub-pixel apart between runs, so the diff is dominated by glyph outlines
and reads the same whether the bleed is soft or sharp. This measures instead how much the
knob DARKENS THE PAGE OVERALL, which is robust to a one-pixel shift, plus the blur radius
the code actually uses.
"""
import sys, subprocess, re
import numpy as np
from PIL import Image

H, T = sys.argv[1], sys.argv[2]
body = "\n".join(f"Dense line {i} of the first page, filling it completely." for i in range(34))
open(f"{T}/st.txt", "w").write(body + "\n")

def page2_mean(tag, amount):
    subprocess.run([sys.executable, f"{H}/hyperwrite.py", "--file", f"{T}/st.txt",
                    "--out", f"{T}/{tag}.png", "--preset", "henry", "--seed", "4",
                    "--dpi", "130", "--capture", "print", "--grain", "0",
                    "--showthrough", str(amount)], capture_output=True, check=True)
    a = np.asarray(Image.open(f"{T}/{tag}-02.png").convert("L"), np.float32) / 255.0
    return float(a.mean())

off, on, loud = page2_mean("off", 0), page2_mean("on", 0.5), page2_mean("loud", 1.5)

# the knob must DO something, monotonically
assert off - on > 0.0004, f"show-through 0.5 darkens the page by only {off-on:.5f} — knob is dead"
assert on - loud > 0.0004, f"show-through does not scale: 0.5 -> {on:.5f}, 1.5 -> {loud:.5f}"
# and it must stay faint: at the default it may not dim the page by more than 1.5%
assert off - on < 0.015, f"show-through dims page two by {100*(off-on):.2f}% — far too dark"

# the blur must scale with the WRITING, not the resolution: a dpi-derived radius was the bug
src = open(f"{H}/hyperwrite.py").read()
i = src.index("prev_ink is not None")
window = src[i:i + 1200]
assert "GaussianBlur" in window, "show-through no longer blurs at all"
radius = re.search(r"GaussianBlur\(([^)]*)\)", window).group(1)
assert "dpi" not in radius, (f"show-through blur radius is {radius!r} — deriving it from dpi "
                             f"made page one readable through page two")
assert "xh" in radius or "line_gap" in radius, f"blur radius {radius!r} does not scale with the writing"
