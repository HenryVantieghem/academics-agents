#!/usr/bin/env python3
"""Re-pull everything and report what CHANGED since the last run.

    python3 scripts/refresh.py

Run this first, every time. It prints `no changes` in a couple of seconds when
nothing moved, so there is no reason to skip it — and the one thing it exists to
catch is an instructor moving a due date, which a cached view will never show you.
"""

from __future__ import annotations

import json
from datetime import datetime

import canvas_lib as cl
import harvest

STATE = cl.DATA_DIR / "last-seen.json"


def snapshot() -> dict:
    out = {}
    for c in cl.load_courses():
        cid = c.get("canvas_id")
        if not cid:
            continue
        for a in cl.get_paginated(f"/api/v1/courses/{cid}/assignments?per_page=100") or []:
            out[f"{c['code']}:{a.get('id')}"] = {
                "course": c["code"], "name": a.get("name"),
                "due": a.get("due_at"), "points": a.get("points_possible"),
                "has_rubric": bool(a.get("rubric")),
            }
    return out


def main() -> int:
    prev = json.loads(STATE.read_text()) if STATE.exists() else {}
    now = snapshot()
    added, moved, rubric, dated = [], [], [], []

    for k, v in now.items():
        old = prev.get(k)
        if old is None:
            added.append(v)
            continue
        if old.get("due") != v.get("due"):
            (dated if old.get("due") is None else moved).append((old, v))
        if not old.get("has_rubric") and v.get("has_rubric"):
            rubric.append(v)
    removed = [v for k, v in prev.items() if k not in now]

    if prev and (added or moved or rubric or dated or removed):
        print("\n  CHANGES SINCE LAST RUN\n")
        # A moved due date outranks everything else — lead with it.
        for old, new in moved:
            print(f"  !! DUE DATE MOVED  {new['course']}  {new['name']}")
            print(f"       {cl.fmt(cl.to_local(old['due']))}  ->  {cl.fmt(cl.to_local(new['due']))}")
        for old, new in dated:
            print(f"   +  now dated       {new['course']}  {new['name']}"
                  f"  -> {cl.fmt(cl.to_local(new['due']))}")
        for v in added:
            print(f"   +  new assignment  {v['course']}  {v['name']}  ({v['points']} pts)")
        for v in rubric:
            print(f"   +  rubric attached {v['course']}  {v['name']}")
        for v in removed:
            print(f"   -  disappeared     {v['course']}  {v['name']}")
        print()
    elif prev:
        print("  no changes")
    else:
        print(f"  first run — recording {len(now)} assignments as the baseline")

    cl.DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(now, indent=2) + "\n")

    print("\n  re-harvesting…")
    for c in cl.load_courses():
        if c.get("canvas_id"):
            harvest.harvest_course(c, download_files=True)
    print("  done. Now read the dashboard:  python3 scripts/dashboard.py")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cl.CanvasError as e:
        print(f"\n  {e}\n")
        raise SystemExit(1)
