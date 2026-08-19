#!/usr/bin/env python3
"""Mirror every course's Canvas content into readable markdown under courses/.

    python3 scripts/harvest.py
    python3 scripts/harvest.py --course MATH-2110

Writes courses/<CODE>/_canvas/{INDEX.md,MODULES.md,assignments/,pages/,quizzes/,
discussions/,announcements/} and downloads files to courses/<CODE>/files/.

Idempotent: it overwrites its own _canvas/ output and never touches anything you
or an agent wrote elsewhere in the course folder.
"""

from __future__ import annotations

import argparse
import html
import re
import urllib.request
from pathlib import Path

import canvas_lib as cl

COURSES_DIR = cl.REPO_ROOT / "courses"


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p>", "\n\n", s)
    s = re.sub(r"<li>", "\n- ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def harvest_course(c: dict, download_files: bool) -> dict:
    cid = c["canvas_id"]
    root = COURSES_DIR / c["code"]
    canvas = root / "_canvas"
    counts, warnings = {}, []

    # --- assignments -------------------------------------------------------
    items = cl.get_paginated(f"/api/v1/courses/{cid}/assignments?per_page=100") or []
    counts["assignments"] = len(items)
    for a in items:
        due = cl.to_local(a.get("due_at"))
        route, why = cl.route_for(a.get("submission_types"))
        body = [
            f"# {a.get('name')}", "",
            f"- **Course:** {c['code']}",
            f"- **Due:** {cl.fmt(due)}" if due else "- **Due:** _no due date set_",
            f"- **Points:** {a.get('points_possible')}",
            f"- **Submission types:** `{', '.join(a.get('submission_types') or []) or 'none'}`",
            f"- **Route:** {route} — {why}",
            f"- **Canvas:** {cl.base_url()}/courses/{cid}/assignments/{a.get('id')}",
        ]
        if a.get("rubric"):
            body += ["", "## Rubric", ""]
            for r in a["rubric"]:
                body.append(f"- **{r.get('description')}** ({r.get('points')} pts) "
                            f"{r.get('long_description') or ''}".rstrip())
        body += ["", "## Instructions", "", strip_html(a.get("description")) or "_none given_"]
        write(canvas / "assignments" / f"{cl.slugify(a.get('name') or 'untitled')}.md",
              "\n".join(body) + "\n")

    # --- pages, quizzes, discussions, announcements ------------------------
    for kind, path, titler in [
        ("pages", f"/api/v1/courses/{cid}/pages?per_page=100", lambda x: x.get("title")),
        ("quizzes", f"/api/v1/courses/{cid}/quizzes?per_page=100", lambda x: x.get("title")),
        ("discussions", f"/api/v1/courses/{cid}/discussion_topics?per_page=100", lambda x: x.get("title")),
    ]:
        got, err = cl.try_get(path)
        if err:
            warnings.append(f"{kind}: {err}")
            counts[kind] = 0
            continue
        got = cl.get_paginated(path) or []
        counts[kind] = len(got)
        for x in got:
            title = titler(x) or "untitled"
            if kind == "pages":
                full, e2 = cl.try_get(f"/api/v1/courses/{cid}/pages/{x.get('url')}")
                text = strip_html((full or {}).get("body")) if not e2 else f"_{e2}_"
            elif kind == "quizzes":
                due = cl.to_local(x.get("due_at"))
                text = (f"- **Due:** {cl.fmt(due)}\n- **Points:** {x.get('points_possible')}\n"
                        f"- **Time limit:** {x.get('time_limit')} min\n"
                        f"- **Attempts:** {x.get('allowed_attempts')}\n\n"
                        f"> Quizzes cannot be completed through the API — they need a real browser session.\n\n"
                        + strip_html(x.get("description")))
            else:
                text = strip_html(x.get("message"))
            write(canvas / kind / f"{cl.slugify(title)}.md", f"# {title}\n\n{text}\n")

    # --- modules (the instructor's own ordering — often the best map) ------
    mods = cl.get_paginated(f"/api/v1/courses/{cid}/modules?include[]=items&per_page=100") or []
    if isinstance(mods, list) and mods:
        lines = [f"# {c['code']} — module map", ""]
        for m in mods:
            lines.append(f"## {m.get('name')}")
            lines.append("")
            for it in (m.get("items") or []):
                lines.append(f"- `{it.get('type')}` [{it.get('title')}]({it.get('html_url')})")
            lines.append("")
        write(canvas / "MODULES.md", "\n".join(lines) + "\n")

    # --- files -------------------------------------------------------------
    files, ferr = cl.try_get(f"/api/v1/courses/{cid}/files?per_page=100")
    if ferr:
        warnings.append(f"files: {ferr}")
        counts["files"] = 0
    else:
        files = cl.get_paginated(f"/api/v1/courses/{cid}/files?per_page=100") or []
        counts["files"] = len(files)
        if download_files:
            for f in files:
                name = f.get("display_name") or f"file-{f.get('id')}"
                dest = root / "files" / name
                if dest.exists():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with urllib.request.urlopen(f["url"], timeout=60) as r, open(dest, "wb") as out:
                        out.write(r.read())
                except Exception as e:
                    warnings.append(f"download {name}: {e}")

    idx = [f"# {c['code']} — Canvas harvest index", "",
           f"- Course: **{c.get('name')}**", f"- Canvas id: `{cid}`", "",
           "| Artifact | Count |", "|---|---|"]
    idx += [f"| {k} | {v} |" for k, v in counts.items()]
    if warnings:
        idx += ["", "## Warnings", ""] + [f"- {w}" for w in warnings]
        idx += ["", "_A 403/404 here usually means the course disabled that tab for students._"]
    write(canvas / "INDEX.md", "\n".join(idx) + "\n")
    return {"counts": counts, "warnings": warnings}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--course", help="one course code; default is all")
    ap.add_argument("--no-files", action="store_true", help="skip binary downloads")
    a = ap.parse_args()

    courses = cl.load_courses()
    if a.course:
        courses = [c for c in courses if c["code"].upper() == a.course.upper()]
        if not courses:
            print(f"  no course matching {a.course!r} in courses.json")
            return 1

    for c in courses:
        print(f"  {c['code']} …", end=" ", flush=True)
        r = harvest_course(c, download_files=not a.no_files)
        bits = ", ".join(f"{v} {k}" for k, v in r["counts"].items() if v)
        print(bits or "nothing published yet", end="")
        print(f"   ({len(r['warnings'])} warning(s))" if r["warnings"] else "")
    print(f"\n  -> courses/<CODE>/_canvas/")
    print("  next:  python3 scripts/dashboard.py")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cl.CanvasError as e:
        print(f"\n  {e}\n")
        raise SystemExit(1)
