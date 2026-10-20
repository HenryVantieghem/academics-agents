#!/usr/bin/env bash
# Re-derive judge.py's bands from measured anchors. Run this instead of hand-editing BANDS.
#
#   ./calibrate.sh <sample.txt> <a-real-photographed-handwritten-page.png> [competitor.png]
#
# Prints the two anchors every band needs:
#   FAIL  a pure font page  — one outline per letter, no physics, clean render
#   PASS  the real pen page you passed in
# plus the coefficient of variation of each metric over five seeds, which is what the
# weights are set from. A metric whose cv is near 1.0 is noise; weight it near zero.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TEXT="${1:?usage: calibrate.sh sample.txt real-hand.png [competitor.png]}"
REAL="${2:?need a real handwritten page as the pass anchor}"
COMP="${3:-}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

python3 "$HERE/hyperwrite.py" --file "$TEXT" --out "$TMP/font.png" --capture print \
  --variants 1 --wobble 0 --messiness 0 --pressure 0 --bleed 0 --pool 0 --skip 0 \
  --grain 0 --showthrough 0 --smudge 0 --restart 0 --cursive 0 --seed 1 --dpi 140 --max-pages 1 >/dev/null

for s in 3 11 29 47 61; do
  python3 "$HERE/hyperwrite.py" --file "$TEXT" --out "$TMP/s$s.png" --preset neat \
    --seed "$s" --dpi 140 --max-pages 1 >/dev/null
done

echo "=== anchors ==="
python3 "$HERE/judge.py" "$TMP/font.png" "$REAL" ${COMP:+"$COMP"}
echo
echo "=== seed variance (sets the weights) ==="
python3 "$HERE/judge.py" "$TMP"/s*.png --json > "$TMP/ms.json"
python3 - "$TMP/ms.json" <<'PY'
import json,sys,statistics as st
d=json.load(open(sys.argv[1]))
for k in ("glyph_uniqueness","ink_flatness","baseline_wander","line_start_px","paper_life"):
    v=[x["raw"][k] for x in d if x["raw"][k] is not None]
    if len(v)<2: continue
    m,s=st.mean(v),st.stdev(v)
    print(f"  {k:<20} mean {m:.4f}  sd {s:.4f}  cv {s/m:.2f}")
sc=[x["forensic_score"] for x in d]
print(f"  {'SCORE':<20} mean {st.mean(sc):.1f}  sd {st.stdev(sc):.1f}")
PY
