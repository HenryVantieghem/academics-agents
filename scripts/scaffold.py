#!/usr/bin/env python3
"""Create the per-course folder tree, a context stub, and a sub-skill stub.

    python3 scripts/scaffold.py

Deliberately writes only *stubs* with explicit UNKNOWN markers. The agent fills
them in afterwards by reading the harvested Canvas material and the syllabus —
that is the step a script cannot do, and faking it produces confident nonsense.

Never overwrites an existing file. Safe to re-run when a new course appears.
"""

from __future__ import annotations

from pathlib import Path

import canvas_lib as cl

COURSES_DIR = cl.REPO_ROOT / "courses"
TEMPLATES = cl.REPO_ROOT / "templates"

SUBDIRS = ["00-context", "01-syllabus", "02-lectures", "03-assignments",
           "04-exams", "05-study-guides", "06-notes", "files"]


def fill(tpl: str, c: dict) -> str:
    teachers = ", ".join(t["name"] for t in c.get("teachers", []) if t.get("name")) or "UNKNOWN"
    canvas = (f"{cl.base_url()}/courses/{c['canvas_id']}"
              if c.get("canvas_id") else "UNKNOWN — no Canvas shell")
    return (tpl.replace("{{CODE}}", c["code"])
               .replace("{{NAME}}", c.get("name") or "UNKNOWN")
               .replace("{{CANVAS_ID}}", str(c.get("canvas_id") or "UNKNOWN"))
               .replace("{{CANVAS_URL}}", canvas)
               .replace("{{TERM}}", c.get("term") or "UNKNOWN")
               .replace("{{TEACHERS}}", teachers))


def main() -> int:
    created, skipped = 0, 0
    for c in cl.load_courses():
        root = COURSES_DIR / c["code"]
        for d in SUBDIRS:
            (root / d).mkdir(parents=True, exist_ok=True)
        for tpl_name, dest in [("COURSE-CONTEXT.md", root / "00-context" / "COURSE-CONTEXT.md"),
                               ("COURSE-SKILL.md",  root / "00-context" / "SKILL.md")]:
            if dest.exists():
                skipped += 1
                continue
            dest.write_text(fill((TEMPLATES / tpl_name).read_text(), c))
            created += 1
        print(f"  {c['code']:<14} courses/{c['code']}/")
    print(f"\n  {created} stub(s) written, {skipped} left alone (already existed)")
    print("\n  These are STUBS with UNKNOWN markers on purpose. Next, have the agent read")
    print("  each course's _canvas/ mirror and syllabus and fill them in — replacing every")
    print("  UNKNOWN with a sourced fact, or leaving it marked UNKNOWN if the source is silent.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cl.CanvasError as e:
        print(f"\n  {e}\n")
        raise SystemExit(1)
