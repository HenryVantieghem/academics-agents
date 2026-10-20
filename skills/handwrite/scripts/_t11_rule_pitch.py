import sys, subprocess
import numpy as np
from PIL import Image, ImageFilter
H, T = sys.argv[1], sys.argv[2]
open(f"{T}/r.txt", "w").write("\n".join(f"Ruling check line {i} of this page." for i in range(26)))
gaps = {}
for size in ("3.4", "4.6"):
    out = f"{T}/rule{size}.png"
    subprocess.run([sys.executable, f"{H}/hyperwrite.py", "--file", f"{T}/r.txt", "--out", out,
                    "--paper", "college", "--capture", "print", "--size", size, "--dpi", "150",
                    "--seed", "5", "--max-pages", "1", "--messiness", "0.4"],
                   capture_output=True, check=True)
    im = Image.open(out).convert("L")
    a = np.asarray(im, np.float32) / 255.0
    bg = np.asarray(im.filter(ImageFilter.GaussianBlur(24)), np.float32) / 255.0
    ink = np.clip(bg - a, 0, 1) > 0.10
    prof = ink.sum(1); thr = max(3, prof.max() * 0.06)
    rows, on = [], False
    for y in range(len(prof)):
        if prof[y] > thr and not on:
            on, s0 = True, y
        elif prof[y] <= thr and on:
            on = False
            if y - s0 > 3:
                rows.append((s0 + y) / 2)
    d = np.diff(rows)
    gaps[size] = float(np.median(d[(d > 5) & (d < 200)]))
# US college rule is 7.1mm. At 150 dpi that is 41.9px, and it must NOT move with --size:
# deriving the ruling from the font size let the writing float between the lines instead of
# sitting on them, which reads as printed-not-written instantly. Measured 2026-09-21.
exp = 7.1 * 150 / 25.4
for size, g in gaps.items():
    assert abs(g - exp) < exp * 0.12, f"--size {size}: line pitch {g:.1f}px, college rule is {exp:.1f}px"
assert abs(gaps["3.4"] - gaps["4.6"]) < exp * 0.08, f"line pitch moved with font size: {gaps}"
