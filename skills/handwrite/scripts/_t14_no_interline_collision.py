"""Lines must not crash into each other on tightly ruled paper.

Measured 2026-09-21: a 4.6mm x-height was rendered on a 5mm Moleskine dot grid. The
ascenders of each line landed inside the descenders of the line above and the page was
unreadable. It shipped, because the renderer only printed a note about it.

Two things now prevent it, and this asserts both:
  * `write_every` separates the PRINTED pitch from the WRITING pitch — nobody writes on
    every row of a 5mm dot grid, they write across two squares
  * the fit guard shrinks writing that still does not fit, unless --no-fit is passed
"""
import sys, subprocess
import numpy as np
from PIL import Image, ImageFilter

H, T = sys.argv[1], sys.argv[2]
N = 12
open(f"{T}/n.txt", "w").write("\n".join(
    f"Line {i} has tall letters like lkfhb and deep ones like gjpqy." for i in range(N)))

def bands(path):
    im = Image.open(path).convert("L")
    a = np.asarray(im, np.float32) / 255.0
    bg = np.asarray(im.filter(ImageFilter.GaussianBlur(26)), np.float32) / 255.0
    m = np.clip(bg - a, 0, 1) > 0.22
    prof = m.sum(1)
    thr = max(2.0, prof.max() * 0.05)
    out, on = [], False
    for y, v in enumerate(prof):
        if v > thr and not on:
            on, s = True, y
        elif v <= thr and on:
            on = False
            if y - s > 3:
                out.append((s, y))
    return out

failures = []
for paper, size in (("moleskine", "4.6"), ("dotted", "4.6"), ("grid", "4.4"),
                    ("college", "4.0"), ("graph", "4.6")):
    out = f"{T}/{paper}.png"
    r = subprocess.run([sys.executable, f"{H}/hyperwrite.py", "--file", f"{T}/n.txt",
                        "--out", out, "--paper", paper, "--capture", "print",
                        "--size", size, "--seed", "6", "--dpi", "150", "--max-pages", "1",
                        "--messiness", "0.6", "--showthrough", "0"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]
    got = len(bands(out))
    if got < N:
        failures.append(f"{paper} at {size}mm: {got} separate lines of {N} — lines merged")
assert not failures, "; ".join(failures)

# The guard has to fire on something that genuinely does not fit the WRITING pitch, not the
# printed one. 4.6mm was used here first and stopped failing the moment `write_every` gave
# moleskine a 10mm writing pitch — the check was then asserting an unreachable state.
r = subprocess.run([sys.executable, f"{H}/hyperwrite.py", "--file", f"{T}/n.txt",
                    "--out", f"{T}/fitted.png", "--paper", "college",
                    "--capture", "print", "--size", "6.5", "--seed", "6", "--dpi", "150",
                    "--max-pages", "1"], capture_output=True, text=True)
assert r.returncode == 0 and "fitted:" in r.stderr, \
    f"6.5mm on 7.1mm college rule should have been fitted down, stderr: {r.stderr[-200:]}"

# and --no-fit must still let you do it on purpose, loudly
r = subprocess.run([sys.executable, f"{H}/hyperwrite.py", "--file", f"{T}/n.txt",
                    "--out", f"{T}/override.png", "--paper", "college", "--no-fit",
                    "--capture", "print", "--size", "6.5", "--seed", "6", "--dpi", "150",
                    "--max-pages", "1"], capture_output=True, text=True)
assert r.returncode == 0 and "WARNING" in r.stderr, "--no-fit should render but warn loudly"
