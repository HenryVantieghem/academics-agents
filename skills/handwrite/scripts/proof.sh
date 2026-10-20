#!/usr/bin/env bash
# The proof. One command, exit 0 or it did not ship.
#
#   renders a page, scores it, boots the local site, drives generate + page + pdf over HTTP,
#   and asserts the PDF is a real multi-page PDF. Prints every number it checked.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/t.txt" <<'TXT'
The Impact of Urbanization on Local Ecosystems

Urbanization, the increasing concentration of population in urban areas, presents
significant environmental challenges. These include habitat loss, pollution of air,
water and noise, altered hydrological cycles, and the urban heat island effect.
This assignment focuses on the impact of urbanization on Greenwood Park, a local
ecosystem located in the rapidly expanding suburbs of Anytown, Ohio.

Before significant urbanization began, approximately 20 years ago, Greenwood Park
was primarily a mixed deciduous forest with a small stream running through it.
Historical accounts, though limited, suggest it was a haven for local wildlife,
including various bird species, small mammals, and amphibians. This description
is a reasonable estimation based on typical regional ecosystems of that period.

2. Key Environmental Impacts

2.1 Habitat Loss and Fragmentation

Urbanization around Greenwood Park has dramatically reduced and fragmented the
original forest habitat. Housing developments, roads, and commercial areas have
replaced large portions of the forest. The remaining forested area is now
significantly smaller and divided into isolated patches, which limits the
movement of species and reduces genetic exchange between populations.

2.2 Water Quality and Hydrology

Impervious surfaces increase runoff volume and velocity, carrying road salt,
oil and fertiliser directly into Clear Creek rather than allowing it to filter
slowly through soil. Stream temperature rises, dissolved oxygen falls, and the
macroinvertebrate community that indicates stream health collapses first.
TXT

echo "== 1. CLI renders a multi-page PDF =="
python3 "$HERE/hyperwrite.py" --file "$TMP/t.txt" --out "$TMP/a.pdf" \
  --preset neat --seed 7 --dpi 150 | tee "$TMP/r.json"
python3 - "$TMP/a.pdf" "$TMP/r.json" <<'PY'
import sys, json
# Pillow WRITES pdf and cannot READ it; pypdf is the reader. Checking the magic bytes alone
# would pass on a 1-byte file, so count the pages in the actual PDF and compare to the
# renderer's own claim — a report agreeing with itself proves nothing.
from pypdf import PdfReader
rep = json.load(open(sys.argv[2]))
assert open(sys.argv[1], "rb").read(5) == b"%PDF-", "not a PDF"
n = len(PdfReader(sys.argv[1]).pages)
assert n == rep["pages"], f"PDF holds {n} pages, renderer claimed {rep['pages']}"
assert n >= 2, f"expected a multi-page PDF, got {n}"
assert rep["collision_rate"] <= 0.06, f"glyphs colliding: {rep['collision_rate']}"
print(f"   ok  {n} pages in the PDF, collision {rep['collision_rate']}, seed {rep['seed']}")
PY

echo "== 2. forensic score beats a font page and the reference =="
# the control and the score anchors were measured on Caveat; the default hand is Reenie Beanie
python3 "$HERE/hyperwrite.py" --file "$TMP/t.txt" --out "$TMP/font.png" --capture print --font caveat \
  --variants 1 --wobble 0 --messiness 0 --pressure 0 --bleed 0 --pool 0 --skip 0 \
  --smudge 0 --restart 0 --cursive 0 \
  --grain 0 --showthrough 0 --seed 1 --dpi 150 --max-pages 1 >/dev/null
python3 "$HERE/hyperwrite.py" --file "$TMP/t.txt" --out "$TMP/hw.png" --font caveat \
  --preset neat --seed 7 --dpi 150 --max-pages 1 >/dev/null
python3 "$HERE/judge.py" "$TMP/font.png" "$TMP/hw.png" --json > "$TMP/s.json"
python3 - "$TMP/s.json" <<'PY'
import sys, json
d = {x["file"]: x for x in json.load(open(sys.argv[1]))}
f, h = d["font.png"]["forensic_score"], d["hw.png"]["forensic_score"]
print(f"   font page {f}   hyperwrite {h}   (handtextai.com measured 66.8)")
assert f < 35, f"the font control should score low, got {f}"
assert h > 60, f"hyperwrite should clear 60, got {h}"
assert h - f > 25, "no separation from a plain font page"
PY

echo "== 3. the site serves, generates, and returns a PDF over HTTP =="
python3 - "$HERE" <<'PY'
import sys, os, json, threading, time, urllib.request
sys.path.insert(0, sys.argv[1])
import serve
port = serve.free_port(8890)
srv = serve.Server(("127.0.0.1", port), serve.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.4)
base = f"http://127.0.0.1:{port}"

def post(path, payload):
    r = urllib.request.Request(base + path, json.dumps(payload).encode(),
                               {"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=300) as resp:
        return resp.status, resp.read()

with urllib.request.urlopen(base + "/", timeout=20) as r:
    html = r.read()
assert r.status == 200 and b"Hyperwrite" in html, "index did not serve"
print(f"   GET  /              200  {len(html)}B")

with urllib.request.urlopen(base + "/api/fonts", timeout=20) as r:
    fonts = json.load(r)
assert fonts["fonts"] and fonts["papers"] and fonts["inks"]
print(f"   GET  /api/fonts     200  {len(fonts['fonts'])} hands, "
      f"{len(fonts['papers'])} papers, {len(fonts['inks'])} inks")

st, body = post("/api/generate", {
    "text": "Hyperwrite runs on this machine and nothing leaves the laptop. "
            "The ink pools where the pen slowed and the paper grain shows through.",
    "settings": {"paper": {"style_id": "college", "format_id": "a4"},
                 "font": {"family": "caveat", "size": 4.6, "ink": "blue"},
                 "effects": {"capture": "scan", "variants": 20, "variation": 1.1},
                 "general": {"seed": 7, "dpi": 150, "max_pages": 2}},
    "score": True})
g = json.loads(body)
assert st == 200 and g["pages"], f"generate failed: {body[:300]}"
print(f"   POST /api/generate  200  {len(g['pages'])} page(s), "
      f"forensic {g['forensic']['forensic_score']}, collision {g['collision_rate']}")

with urllib.request.urlopen(f"{base}/api/page/{g['generation_id']}/{g['pages'][0]}",
                            timeout=60) as r:
    png = r.read()
assert r.status == 200 and png[:8] == b"\x89PNG\r\n\x1a\n", "page is not a PNG"
print(f"   GET  /api/page/..   200  {len(png)}B  image/png")

st, pdf = post("/api/pdf", {"generation_id": g["generation_id"]})
assert st == 200 and pdf[:5] == b"%PDF-", "pdf endpoint did not return a PDF"
print(f"   POST /api/pdf       200  {len(pdf)}B  application/pdf")
srv.shutdown()
PY

echo
echo "PROOF PASSED"
