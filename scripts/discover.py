#!/usr/bin/env python3
"""Discover the student's active courses and write data/courses.json.

    python3 scripts/discover.py
    python3 scripts/discover.py --all-terms

This is step 1 of setup. Everything downstream reads courses.json, so nothing
here is hardcoded to a school, a term, or a course.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter

import canvas_lib as cl

DAY_MAP = {"M": "Mon", "T": "Tue", "W": "Wed", "R": "Thu", "F": "Fri", "S": "Sat", "U": "Sun"}


def parse_code(course: dict) -> str:
    """Best-effort short code (e.g. 'MATH-2110') from Canvas's messy course_code."""
    raw = (course.get("course_code") or course.get("name") or "").strip()
    m = re.match(r"([A-Za-z]{2,6})[\s_-]*(\d{3,5})", raw)
    if m:
        return f"{m.group(1).upper()}-{m.group(2)}"
    return cl.slugify(raw).upper()[:20] or f"COURSE-{course['id']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-terms", action="store_true",
                    help="include past/future terms, not just the active one")
    a = ap.parse_args()

    print("  discovering enrollments…")
    raw = cl.get_paginated(
        "/api/v1/courses?enrollment_state=active&include[]=term"
        "&include[]=teachers&include[]=total_scores&per_page=100")
    if not isinstance(raw, list):
        print("  Canvas returned no course list. Is the token valid?")
        return 1

    # Canvas happily returns courses from every term the account ever had.
    # Default to the term that most active enrollments belong to.
    terms = Counter()
    for c in raw:
        t = (c.get("term") or {}).get("name")
        if t:
            terms[t] += 1
    active_term = terms.most_common(1)[0][0] if terms else None
    if active_term and not a.all_terms:
        print(f"  active term looks like: {active_term}  "
              f"({terms[active_term]} of {len(raw)} courses) — use --all-terms to include the rest")

    courses = []
    for c in raw:
        term_name = (c.get("term") or {}).get("name")
        if active_term and not a.all_terms and term_name != active_term:
            continue
        if c.get("access_restricted_by_date"):
            continue
        teachers = [{"name": t.get("display_name"), "id": t.get("id")}
                    for t in (c.get("teachers") or [])]
        courses.append({
            "code": parse_code(c),
            "name": c.get("name"),
            "canvas_id": c.get("id"),
            "course_code_raw": c.get("course_code"),
            "term": term_name,
            "teachers": teachers,
            "meetings": [],          # Canvas rarely carries these; fill from the syllabus
            "notes": "",
        })

    courses.sort(key=lambda x: x["code"])
    cl.save_courses(courses, term={"name": active_term})
    print(f"\n  {len(courses)} course(s) -> {cl.COURSES_JSON.relative_to(cl.REPO_ROOT)}")
    for c in courses:
        who = ", ".join(t["name"] for t in c["teachers"] if t.get("name")) or "instructor unknown"
        print(f"    {c['code']:<14} {c['canvas_id']:<9} {who}")
    print("\n  Courses you are enrolled in but which have no published Canvas shell will NOT")
    print("  appear here. That is a real gap — note them by hand in courses.json.")
    print("\n  next:  python3 scripts/harvest.py")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cl.CanvasError as e:
        print(f"\n  {e}\n")
        raise SystemExit(1)
