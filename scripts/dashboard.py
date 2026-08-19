#!/usr/bin/env python3
"""What is graded, what is late, what is coming.

    python3 scripts/dashboard.py
    python3 scripts/dashboard.py --days 30
    python3 scripts/dashboard.py --json

Answer deadline questions from this, never from memory or a cached note. A due
date that moved is the failure mode that actually costs marks.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta

import canvas_lib as cl


def collect(days: int) -> dict:
    now = datetime.now(cl.local_tz())
    horizon = now + timedelta(days=days)
    grades, overdue, upcoming, undated, blind = [], [], [], [], []

    for c in cl.load_courses():
        cid = c.get("canvas_id")
        if not cid:
            blind.append({"code": c["code"], "why": "no Canvas shell recorded"})
            continue

        enr = cl.get_paginated(
            f"/api/v1/courses/{cid}/enrollments?user_id=self&per_page=10") or []
        score = None
        for e in enr:
            g = e.get("grades") or {}
            if g.get("current_score") is not None:
                score = g["current_score"]
                break
        grades.append({"code": c["code"], "name": c.get("name"), "score": score})

        assigns = cl.get_paginated(
            f"/api/v1/courses/{cid}/assignments?include[]=submission&per_page=100") or []
        if not assigns:
            blind.append({"code": c["code"], "why": "no assignments published yet"})
        for a in assigns:
            sub = a.get("submission") or {}
            submitted = bool(sub.get("submitted_at")) or sub.get("workflow_state") == "graded"
            route, _ = cl.route_for(a.get("submission_types"))
            due = cl.to_local(a.get("due_at"))
            row = {"code": c["code"], "name": a.get("name"),
                   "points": a.get("points_possible"), "route": route,
                   "due": due.isoformat() if due else None,
                   "due_str": cl.fmt(due), "submitted": submitted,
                   "score": sub.get("score"),
                   "url": f"{cl.base_url()}/courses/{cid}/assignments/{a.get('id')}"}
            if due is None:
                if not submitted:
                    undated.append(row)
            elif due < now and not submitted:
                overdue.append(row)
            elif now <= due <= horizon and not submitted:
                upcoming.append(row)

    overdue.sort(key=lambda r: r["due"] or "")
    upcoming.sort(key=lambda r: r["due"] or "")
    return {"generated": now.isoformat(timespec="seconds"), "grades": grades,
            "overdue": overdue, "upcoming": upcoming, "undated": undated,
            "no_data": blind}


def render(d: dict, days: int) -> None:
    bar = "=" * 74
    print(f"\n{bar}\n  ACADEMICS  |  {d['generated'][:16].replace('T', ' ')}\n{bar}\n")

    print("GRADES")
    for g in d["grades"]:
        s = f"{g['score']:.1f}%" if g["score"] is not None else "  --  "
        print(f"  {g['code']:<14} {s:>8}   {(g['name'] or '')[:42]}")

    print(f"\nOVERDUE  ({len(d['overdue'])})")
    for r in d["overdue"] or []:
        print(f"  {r['due_str']:<22} {r['code']:<14} {str(r['points']):>5}p  [{r['route']:<7}] {r['name']}")
    if not d["overdue"]:
        print("  nothing overdue")

    print(f"\nDUE IN THE NEXT {days} DAYS  ({len(d['upcoming'])})")
    for r in d["upcoming"] or []:
        print(f"  {r['due_str']:<22} {r['code']:<14} {str(r['points']):>5}p  [{r['route']:<7}] {r['name']}")
    if not d["upcoming"]:
        print("  nothing scheduled in this window")

    if d["undated"]:
        print(f"\nNO DUE DATE SET  ({len(d['undated'])})  — these get dated later, watch them")
        for r in d["undated"]:
            print(f"  {'':<22} {r['code']:<14} {str(r['points']):>5}p  [{r['route']:<7}] {r['name']}")

    if d["no_data"]:
        print("\nNOT COVERED ABOVE  — say this out loud when reporting, or a clean")
        print("report will imply nothing is due when in fact nothing is *visible*.")
        for b in d["no_data"]:
            print(f"  {b['code']:<14} {b['why']}")

    print(f"\n  route legend: api = can be submitted programmatically · "
          f"browser = needs your logged-in session · none = in class / not collected")
    print(f"\n{bar}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    d = collect(a.days)
    if a.json:
        print(json.dumps(d, indent=2))
    else:
        render(d, a.days)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cl.CanvasError as e:
        print(f"\n  {e}\n")
        raise SystemExit(1)
