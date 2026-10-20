#!/usr/bin/env python3
"""
tune — close the loop. Render, score, adjust, repeat, until the forensic score stops moving.

This exists because hand-tuning realism knobs is exactly the kind of judgement a person is
bad at: every individual page looks fine, and the tells only show up in aggregate. The loop's
exit is quantitative and pre-existing (scripts/judge.py, calibrated against a real pen page),
which is the only kind of loop worth running on an artefact you cannot eyeball at scale.

The bands in judge.py CAP at the real-hand measurement, so there is no reward for overshooting
into a page that scores well and looks insane. Look at the winner anyway — the script prints
its path for exactly that reason.
"""
import argparse, itertools, json, os, subprocess, sys, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))

# knob -> candidate values, searched by coordinate ascent in this order
# Every value here has been rendered and LOOKED AT. The ranges are capped, not gated.
#
# The first version of this file searched --wobble up to 2.0 and --drift up to 0.75, and in
# 47 renders it found that letter collision raises `glyph_uniqueness` and `ink_flatness`
# together. It scored 82.8/100 on a page nobody can read. Four different legibility gates
# were then tried and all four failed: tesseract cannot read handwriting at all; a vision
# model reads collided mush at 0.88 because it guesses the words from context; glyph
# width/height is LOWER for mush than for a real hand; and adjacent-ink overlap separates a
# font from handwriting (0.006 vs 0.032) but not legible handwriting from illegible (0.042).
#
# So the bad state is made unreachable instead of detectable. Do not widen these without
# rendering the extremes and looking at them.
GRID = [
    ("--drift",     [0.17, 0.26, 0.34, 0.45]),
    ("--wobble",    [0.85, 1.0, 1.15, 1.25]),
    ("--variants",  [8, 14, 20, 28]),
    ("--pressure",  [0.7, 1.0, 1.3]),
    ("--grain",     [0.15, 0.3, 0.5, 0.7]),
    ("--linestart", [0.3, 0.7, 1.1, 1.5]),
    ("--pool",      [0.5, 1.0, 1.4]),
    ("--bleed",     [0.6, 1.0, 1.4]),
]

def render(text_file, knobs, workdir, base, dpi):
    out = os.path.join(workdir, "p.png")
    cmd = [sys.executable, os.path.join(HERE, "hyperwrite.py"),
           "--file", text_file, "--out", out, "--dpi", str(dpi), "--max-pages", "1"] + base
    for k, v in knobs.items():
        cmd += [k, str(v)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-800:])
    p = out if os.path.exists(out) else os.path.join(workdir, "p-01.png")
    return p

def score(path, reference=None):
    """Without --reference: how handwritten does this read, against fixed anchors.
    With --reference: how close is it to THAT page. Optimising the second is what you want
    when someone hands you a photo and says "like this" — the first would happily walk away
    from their hand toward a generically more convincing one."""
    cmd = [sys.executable, os.path.join(HERE, "judge.py"), path, "--json"]
    if reference:
        cmd += ["--reference", reference]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-800:])
    out = json.loads(r.stdout)[0]
    if reference:
        out["forensic_score"] = out["match_score"]
    return out

def main():
    ap = argparse.ArgumentParser(description="tune hyperwrite against the forensic judge")
    ap.add_argument("--file", required=True, help="sample text, 1 page is plenty")
    ap.add_argument("--preset", default="neat")
    ap.add_argument("--font", default="caveat")
    ap.add_argument("--paper", default="college")
    ap.add_argument("--ink", default="blue")
    ap.add_argument("--capture", default="scan")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--dpi", type=int, default=140)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--reference", default=None,
                    help="a photo of a real page: tune toward matching IT")
    ap.add_argument("--save", default=None, help="write the winning knobs here as JSON")
    a = ap.parse_args()

    base = ["--preset", a.preset, "--seed", str(a.seed)]
    # a preset already carries paper/ink/capture/glyphset; only override what was asked for
    given = {x for x in sys.argv if x.startswith("--")}
    for flag, val in (("--font", a.font), ("--paper", a.paper),
                      ("--ink", a.ink), ("--capture", a.capture)):
        if flag in given:
            base += [flag, str(val)]
    work = tempfile.mkdtemp(prefix="hwtune-")
    knobs = {k: vs[len(vs) // 2] for k, vs in GRID}
    ref = os.path.expanduser(a.reference) if a.reference else None
    best = score(render(a.file, knobs, work, base, a.dpi), ref)["forensic_score"]
    print(f"start {best}/100   {knobs}")
    n = 1
    try:
        for rnd in range(a.rounds):
            moved = False
            for k, values in GRID:
                cur = knobs[k]
                for v in values:
                    if v == cur:
                        continue
                    knobs[k] = v
                    try:
                        s = score(render(a.file, knobs, work, base, a.dpi), ref)["forensic_score"]
                    except RuntimeError as e:
                        knobs[k] = cur; continue
                    n += 1
                    if s > best + 0.3:
                        best, cur, moved = s, v, True
                        print(f"  {k} -> {v}   {s}/100")
                    knobs[k] = cur
            if not moved:
                print(f"round {rnd+1}: no move, stopping")
                break
        final = render(a.file, knobs, work, base, a.dpi)
        keep = os.path.abspath("hyperwrite-tuned.png")
        shutil.copy(final, keep)
        rep = score(keep, ref)
        print(json.dumps({"renders": n,
                          ("match_score" if ref else "forensic_score"): rep["forensic_score"],
                          "detail": rep.get("metrics") or rep.get("normalised"),
                          "knobs": knobs, "look_at": keep,
                          "flags": " ".join(f"{k} {v}" for k, v in knobs.items())}, indent=2))
        if a.save:
            json.dump(knobs, open(a.save, "w"), indent=2)
        print("\nLOOK AT THE PAGE. A score is not a verdict:", keep)
    finally:
        shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    main()
