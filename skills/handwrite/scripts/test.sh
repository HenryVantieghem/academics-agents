#!/usr/bin/env bash
# Deterministic regression suite. No network, no LLM, ~30 seconds.
#
# Every test here is a bug that actually happened on 2026-09-21. A suite of tests nobody
# ever failed is decoration; these all have a date and a corpse.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n     %s\n' "$1" "${2:-}"; }
t()    { printf '\n%s\n' "$1"; }

cat > "$TMP/t.txt" <<'TXT'
The Impact of Urbanization on Local Ecosystems

Subject: Introduction to Environmental Science
Due Date: March 8, 2025

Urbanization, the increasing concentration of population in urban areas, presents
significant environmental challenges. These include habitat loss, pollution of air,
water and noise, altered hydrological cycles, and the urban heat island effect.
This assignment focuses on the impact of urbanization on Greenwood Park, a local
ecosystem located in the rapidly expanding suburbs of Anytown, Ohio.

Before significant urbanization began, approximately 20 years ago, Greenwood Park
was primarily a mixed deciduous forest with a small stream running through it.
Historical accounts suggest it was a haven for local wildlife, including various
bird species, small mammals, and amphibians.

Impervious surfaces increase runoff volume and velocity, carrying road salt, oil
and fertiliser directly into Clear Creek rather than letting it filter through soil.
Stream temperature rises and dissolved oxygen falls, and the macroinvertebrate
community that indicates stream health collapses before anything else does.

Housing developments, roads and commercial areas have replaced large portions of the
forest. The remaining forested area is significantly smaller and divided into isolated
patches, which limits the movement of species between them and reduces the genetic
exchange that keeps a population viable over decades rather than seasons.

The urban heat island effect raises local temperatures by several degrees, which shifts
the timing of leaf-out and of insect emergence, and those two no longer coincide. Birds
that time their breeding to the insect peak arrive to find it already past.
TXT

t "T1  every page reaches the PDF (v1 dropped pages on short-line documents)"
python3 "$HERE/hyperwrite.py" --file "$TMP/t.txt" --out "$TMP/a.pdf" --preset neat \
  --seed 7 --dpi 120 > "$TMP/r.json" 2>/dev/null
python3 - "$TMP/a.pdf" "$TMP/r.json" <<'PY' && ok "PDF page count matches the renderer's claim" || bad "PDF page count" "see above"
import sys, json
from pypdf import PdfReader
rep = json.load(open(sys.argv[2]))
n = len(PdfReader(sys.argv[1]).pages)
assert n == rep["pages"], f"PDF has {n} pages, renderer reported {rep['pages']}"
# the ruling is now absolute (7.1mm college), so a given text fits more lines
# per page than it used to — this text was lengthened when that changed
assert n >= 2, f"test text should span >1 page, got {n}"
PY

t "T2  photo capture must not transpose the page (PIL QUAD corner order)"
python3 "$HERE/hyperwrite.py" --file "$TMP/t.txt" --out "$TMP/p.png" --capture photo \
  --pagesize a4 --seed 3 --dpi 110 --max-pages 1 >/dev/null 2>&1
python3 - "$TMP/p.png" <<'PY' && ok "text bands run across the page, not down it" || bad "photo transpose" "see above"
import sys
import numpy as np
from PIL import Image, ImageFilter
# The canvas size proves NOTHING here: Image.QUAD always writes a W x H output whatever order
# its corners are in, so an aspect-ratio assertion passes even with the page fully transposed.
# Verified 2026-09-21 by reintroducing the bug — the first version of this test did not notice.
# Test the CONTENT: lines of text are wide and short. Transposed, they are narrow and tall.
im = Image.open(sys.argv[1]).convert("L")
a = np.asarray(im, np.float32) / 255.0
bg = np.asarray(im.filter(ImageFilter.GaussianBlur(24)), np.float32) / 255.0
mask = (np.clip(bg - a, 0, 1) > 0.09)
H, W = mask.shape
def bands(profile, thr):
    out, on = [], False
    for i, v in enumerate(profile):
        if v > thr and not on: on, s = True, i
        elif v <= thr and on:
            on = False
            if i - s > 3: out.append(i - s)
    return out
rows = bands(mask.sum(1), max(3, mask.sum(1).max() * 0.05))
cols = bands(mask.sum(0), max(3, mask.sum(0).max() * 0.05))
assert rows, "no text rows found at all"
med_row = float(np.median(rows))
assert med_row < H / 8, f"text bands are {med_row:.0f}px tall on a {H}px page — the page is transposed"
assert len(rows) >= 6, f"only {len(rows)} horizontal text bands; expected a page of lines"
assert len(rows) > len(cols) * 0.5, f"{len(rows)} row bands vs {len(cols)} column bands — text runs down the page"
PY

t "T3  the forensic score separates a font page from a rendered hand"
# both sides pinned to Caveat: the judge's anchors were measured on it, and the default hand
# (Reenie Beanie since 2026-09-24) is irregular enough that a bare font page scores 48
python3 "$HERE/hyperwrite.py" --file "$TMP/t.txt" --out "$TMP/font.png" --capture print --font caveat \
  --variants 1 --wobble 0 --messiness 0 --pressure 0 --bleed 0 --pool 0 --skip 0 \
  --smudge 0 --restart 0 --cursive 0 \
  --grain 0 --showthrough 0 --seed 1 --dpi 120 --max-pages 1 >/dev/null 2>&1
python3 "$HERE/hyperwrite.py" --file "$TMP/t.txt" --out "$TMP/hand.png" --preset neat --font caveat \
  --seed 7 --dpi 120 --max-pages 1 >/dev/null 2>&1
python3 "$HERE/judge.py" "$TMP/font.png" "$TMP/hand.png" --json > "$TMP/s.json" 2>/dev/null
python3 - "$TMP/s.json" <<'PY' && ok "font <35, hand >58, gap >25" || bad "forensic separation" "see above"
import sys, json
d = {x["file"]: x["forensic_score"] for x in json.load(open(sys.argv[1]))}
f, h = d["font.png"], d["hand.png"]
assert f < 35, f"font control scored {f}, should be well under 35"
assert h > 58, f"rendered hand scored {h}, should clear 58"
assert h - f > 25, f"separation only {h - f:.1f}"
PY

t "T4  judge bands point the right way and no metric is silently dead"
python3 - "$HERE" <<'PY' && ok "5 bands, all ordered, weights sum sane" || bad "judge bands" "see above"
import sys, importlib.util
spec = importlib.util.spec_from_file_location("judge", sys.argv[1] + "/judge.py")
j = importlib.util.module_from_spec(spec); spec.loader.exec_module(j)
assert len(j.BANDS) == 5, f"expected 5 metrics, got {len(j.BANDS)}"
for k, (fail, good, w) in j.BANDS.items():
    assert fail != good, f"{k}: fail and pass anchors are equal, the band is dead"
    assert 0 < w <= 1, f"{k}: weight {w} out of range"
s = sum(w for _, _, w in j.BANDS.values())
assert 0.95 < s < 1.05, f"weights sum to {s}"
PY

t "T5  default settings do not collide glyphs"
python3 - "$TMP/a.hyperwrite.json" <<'PY' && ok "collision rate under the 0.06 cap" || bad "collision" "see above"
import sys, json
r = json.load(open(sys.argv[1]))
assert r["collision_rate"] <= 0.06, f"collision {r['collision_rate']} over cap"
PY

t "T6  the tuner cannot search into illegibility (it found that exploit once)"
python3 - "$HERE" <<'PY' && ok "grid capped at wobble<=1.3, drift<=0.45" || bad "tuner grid" "see above"
import sys, importlib.util
spec = importlib.util.spec_from_file_location("tune", sys.argv[1] + "/tune.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
g = dict(t.GRID)
assert max(g["--wobble"]) <= 1.3, f"--wobble searches up to {max(g['--wobble'])}; >1.3 collides"
assert max(g["--drift"]) <= 0.45, f"--drift searches up to {max(g['--drift'])}"
PY

t "T7  glyphmint rejects a mislabelled set instead of shipping it"
python3 - "$HERE" <<'PY' && ok "intra-letter correlation gate fires on scrambled glyphs" || bad "mint gate" "see above"
import sys, importlib.util, numpy as np
spec = importlib.util.spec_from_file_location("gm", sys.argv[1] + "/glyphmint.py")
G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)
rs = np.random.RandomState(0)
# two totally different shapes filed under the same character = a segmentation failure
scrambled = {"a": [{"alpha": (rs.rand(40, 30) > 0.5).astype(np.float32), "base_dy": 1, "w_xh": 1, "h_xh": 1},
                   {"alpha": (rs.rand(40, 30) > 0.5).astype(np.float32), "base_dy": 1, "w_xh": 1, "h_xh": 1}]}
c = G.intra_letter_correlation(scrambled)
assert c is not None and c < G.MISASSIGN_BELOW, f"correlation {c} did not trip the gate"
# and a consistent set must NOT trip it
one = (rs.rand(40, 30) > 0.5).astype(np.float32)
good = {"a": [{"alpha": one, "base_dy": 1, "w_xh": 1, "h_xh": 1},
              {"alpha": one.copy(), "base_dy": 1, "w_xh": 1, "h_xh": 1}]}
assert G.intra_letter_correlation(good) > G.MISASSIGN_BELOW, "gate fires on a valid set"
PY

t "T8  a minted set renders capitals taller than lowercase (small-caps bug)"
if [ -f "$ROOT/glyphsets/casual-blue/meta.json" ]; then
python3 - "$ROOT/glyphsets/casual-blue" <<'PY' && ok "cap height > x-height in the stored metrics" || bad "small caps" "see above"
import sys, json, statistics as st
m = json.load(open(sys.argv[1] + "/meta.json"))["glyphs"]
xs = [r["h_xh"] for c in "acemnorsuvwxz" if c in m for r in m[c]]
cs = [r["h_xh"] for c in "ABDEFGHKLMNPRT" if c in m for r in m[c]]
assert xs and cs, "set is missing lowercase or uppercase"
x, c = st.median(xs), st.median(cs)
assert c > x * 1.2, f"capitals {c:.2f} vs x-height {x:.2f} — capitals render as small caps"
PY
else echo "  SKIP no glyph set minted (run glyphmint.py mint --name casual-blue)"; fi

t "T9  a minted set's word space does not come from the fallback font"
if [ -f "$ROOT/glyphsets/casual-blue/meta.json" ]; then
python3 - "$HERE" "$ROOT/glyphsets/casual-blue" <<'PY' && ok "space advance scales with x-height, not the font em" || bad "space advance" "see above"
import sys, importlib.util, numpy as np, random
spec = importlib.util.spec_from_file_location("hw", sys.argv[1] + "/hyperwrite.py")
HW = importlib.util.module_from_spec(spec); spec.loader.exec_module(HW)
nr = np.random.RandomState(0)
class Dummy:
    px = 40
    def advance(self, ch): return 999.0          # an absurd font metric
    def get(self, ch, v): return None
a = HW.MintedBank(sys.argv[2], 40, nr, Dummy()).advance(" ")
b = HW.MintedBank(sys.argv[2], 80, nr, Dummy()).advance(" ")
assert a < 100, f"space advance {a} came from the fallback font"
assert abs(b / a - 2.0) < 0.05, f"space advance does not scale with size ({a} -> {b})"
PY
else echo "  SKIP no glyph set minted"; fi

t "T10 the site serves and returns a real PDF over HTTP"
python3 - "$HERE" <<'PY' && ok "index, fonts, generate, page, pdf" || bad "site round trip" "see above"
import sys, json, threading, time, urllib.request
sys.path.insert(0, sys.argv[1])
import serve
port = serve.free_port(8930)
srv = serve.Server(("127.0.0.1", port), serve.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.4)
b = f"http://127.0.0.1:{port}"
def post(p, o):
    r = urllib.request.Request(b + p, json.dumps(o).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=300) as x: return x.status, x.read()
with urllib.request.urlopen(b + "/", timeout=20) as r: assert b"Hyperwrite" in r.read()
with urllib.request.urlopen(b + "/api/fonts", timeout=20) as r:
    f = json.load(r); assert f["fonts"] and f["papers"] and f["inks"]
st, body = post("/api/generate", {"text": "One short handwritten line for the round trip.",
    "settings": {"paper": {"style_id": "ruled"}, "font": {"family": "caveat"},
                 "general": {"seed": 3, "dpi": 110, "max_pages": 1}}})
g = json.loads(body); assert st == 200 and g["pages"], body[:200]
with urllib.request.urlopen(f"{b}/api/page/{g['generation_id']}/{g['pages'][0]}", timeout=60) as r:
    assert r.read()[:8] == b"\x89PNG\r\n\x1a\n"
st, pdf = post("/api/pdf", {"generation_id": g["generation_id"]})
assert st == 200 and pdf[:5] == b"%PDF-"
srv.shutdown()
PY

t "T11 on ruled paper the writing sits at the paper's real pitch, not the font's"
python3 "$HERE/_t11_rule_pitch.py" "$HERE" "$TMP" \
  && ok "college rule is 7.1mm and does not move with --size" \
  || bad "rule pitch" "line spacing is derived from the font size again"

t "T12 verso show-through is a smudge, not readable mirrored text"
python3 "$HERE/_t12_showthrough.py" "$HERE" "$TMP" \
  && ok "bleed is faint, scales with the knob, and blurs with the writing" \
  || bad "show-through" "page one is legible through page two"

t "T13 cursive joins connect letters, and a hex ink reaches the page"
python3 "$HERE/_t13_cursive_colour.py" "$HERE" "$TMP" \
  && ok "joins merge >=20% of letter gaps without colliding; #hex ink honoured" \
  || bad "cursive/colour" "see above"

t "T14 lines do not crash into each other on tightly ruled paper"
python3 "$HERE/_t14_no_interline_collision.py" "$HERE" "$TMP" \
  && ok "12 lines stay 12 lines on moleskine, dotted, grid, college and graph" \
  || bad "interline collision" "see above"

t "T15 every output mode renders at the size and page count it claims"
python3 "$HERE/_t15_modes.py" "$HERE" "$TMP" >/dev/null \
  && ok "PDF, PNG on 5 papers, landscape JPG, ZIP, photo on a plate and offline" \
  || bad "output modes" "run scripts/_t15_modes.py directly to see the assertion"

t "T16 text-to-handwriting's effects and paper image; one seed, one page, in any process"
python3 "$HERE/_t16_upstream_effects.py" "$HERE" "$TMP" >/dev/null \
  && ok "shadows 53% to clear, scanner blows paper white, paper image fills the sheet, seed stable" \
  || bad "upstream effects" "run scripts/_t16_upstream_effects.py directly to see the assertion"

t "T17 the site takes your font and a paper image, and returns every page as a ZIP"
python3 "$HERE/_t17_site_uploads.py" "$HERE" >/dev/null \
  && ok "font and paper uploads change the page, ZIP of PNGs; bad uploads 400, huge bodies 413" \
  || bad "site uploads" "run scripts/_t17_site_uploads.py directly to see the assertion"

printf '\n%s\n' "-----------------------------------------"
printf '%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
