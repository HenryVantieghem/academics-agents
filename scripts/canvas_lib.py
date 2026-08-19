"""Canvas LMS API layer — stdlib only, no third-party dependencies.

Every other script in this repo goes through here. It exists because the three
things that silently break a Canvas integration are all handled in one place:

  * **Pagination.** Canvas returns 10 items by default and truncates without
    warning. `get_paginated` follows the RFC-5988 `Link: rel="next"` header.
  * **Timezones.** Canvas returns UTC. A deadline shown in the wrong zone is the
    failure mode that actually costs marks, so everything converts to the
    course's local zone, read from Canvas itself.
  * **Error triage.** A 401 and a 403 mean completely different things here: 401
    is your token, 403 is usually a course hiding an endpoint from students.
    Conflating them sends you chasing a credential problem that does not exist.

Environment:
    CANVAS_BASE_URL   required, e.g. https://school.instructure.com
    CANVAS_TOKEN      required
    CANVAS_TIMEZONE   optional IANA name; auto-detected from Canvas when unset
    STUDENT_USER_ID   optional; defaults to "auto" -> /users/self
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
COURSES_JSON = DATA_DIR / "courses.json"

_TZ_CACHE: ZoneInfo | None = None


class CanvasError(RuntimeError):
    """Anything that should stop the caller with an actionable message."""


def base_url() -> str:
    raw = os.environ.get("CANVAS_BASE_URL", "").strip()
    if not raw:
        raise CanvasError(
            "CANVAS_BASE_URL is not set.\n"
            "  It is the root of your school's Canvas, e.g. https://school.instructure.com\n"
            "  Copy .env.example to .env, fill it in, then:  set -a && source .env && set +a"
        )
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw.rstrip("/")


def token() -> str:
    tok = os.environ.get("CANVAS_TOKEN", "").strip()
    if not tok:
        raise CanvasError(
            "CANVAS_TOKEN is not set.\n"
            "  Generate one at <your Canvas>/profile/settings\n"
            "  -> Approved Integrations -> + New Access Token.\n"
            "  Then:  set -a && source .env && set +a"
        )
    return tok


def _request(path: str, method: str = "GET", data: bytes | None = None,
             headers: dict[str, str] | None = None) -> tuple[Any, dict[str, str]]:
    url = path if path.startswith("http") else base_url() + path
    hdrs = {"Authorization": f"Bearer {token()}"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, method=method, data=data, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return (json.loads(raw) if raw else None), dict(resp.headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if e.code == 401:
            raise CanvasError(
                "401 Unauthorized from Canvas — the token is expired, revoked, or wrong.\n"
                f"  Regenerate at {base_url()}/profile/settings and update .env.\n"
                f"  Canvas said: {detail}"
            ) from None
        if e.code == 403:
            raise CanvasError(
                f"403 Forbidden for {url}\n"
                "  This is usually NOT a token problem — it normally means the course\n"
                "  hides that endpoint from students (Files is the common one).\n"
                f"  Canvas said: {detail}"
            ) from None
        if e.code == 404:
            raise CanvasError(
                f"404 Not Found for {url}\n"
                "  The course may have that tab disabled (Pages is the common one).\n"
                f"  Canvas said: {detail}"
            ) from None
        raise CanvasError(f"HTTP {e.code} for {url}: {detail}") from None
    except urllib.error.URLError as e:
        raise CanvasError(f"Network error reaching {url}: {e.reason}") from None


def get(path: str) -> Any:
    return _request(path)[0]


def try_get(path: str) -> tuple[Any, str | None]:
    """Return (body, None) or (None, reason). For endpoints a course may disable."""
    try:
        return get(path), None
    except CanvasError as e:
        return None, str(e).splitlines()[0]


def get_paginated(path: str, cap: int = 40) -> list[Any]:
    """Follow Link rel=next. Without this Canvas silently truncates at one page."""
    out: list[Any] = []
    url = path
    for _ in range(cap):
        body, headers = _request(url)
        if not isinstance(body, list):
            return body if body is not None else out
        out.extend(body)
        link = headers.get("Link") or headers.get("link") or ""
        nxt = None
        for part in link.split(","):
            if 'rel="next"' in part:
                nxt = part.split(";")[0].strip().strip("<>")
                break
        if not nxt:
            break
        url = nxt
        time.sleep(0.05)
    return out


def student_id() -> int:
    sid = os.environ.get("STUDENT_USER_ID", "auto").strip()
    if sid and sid.lower() != "auto":
        return int(sid)
    return int(get("/api/v1/users/self")["id"])


def local_tz() -> ZoneInfo:
    """The zone deadlines are shown in. Explicit env wins; otherwise ask Canvas."""
    global _TZ_CACHE
    if _TZ_CACHE is not None:
        return _TZ_CACHE
    name = os.environ.get("CANVAS_TIMEZONE", "").strip()
    if not name:
        # NOTE: /users/self does NOT carry time_zone (it returns None there).
        # /users/self/profile does. Falling back to UTC silently would misreport
        # every deadline by an hour or more, so this says so loudly instead.
        try:
            name = (get("/api/v1/users/self/profile") or {}).get("time_zone") or ""
        except Exception:
            name = ""
        if not name:
            # Second chance: any course carries the zone too.
            try:
                for c in (load_courses() or []):
                    if c.get("canvas_id"):
                        name = (get(f"/api/v1/courses/{c['canvas_id']}") or {}).get("time_zone") or ""
                        if name:
                            break
            except Exception:
                pass
    if not name:
        print("  warning: could not determine the Canvas timezone; using UTC. "
              "Set CANVAS_TIMEZONE in .env to fix deadline display.")
        name = "UTC"
    try:
        _TZ_CACHE = ZoneInfo(name)
    except Exception:
        print(f"  warning: Canvas returned an unusable timezone {name!r}; using UTC.")
        _TZ_CACHE = ZoneInfo("UTC")
    return _TZ_CACHE


def to_local(iso: str | None) -> datetime | None:
    """Canvas hands back UTC ISO-8601. Convert, or return None for undated items."""
    if not iso:
        return None
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(local_tz())


def fmt(dt: datetime | None, with_time: bool = True) -> str:
    if dt is None:
        return "no due date"
    return dt.strftime("%a %Y-%m-%d %H:%M") if with_time else dt.strftime("%a %Y-%m-%d")


# How a given assignment actually gets handed in. Knowing this up front is the
# difference between "I can push this for you" and "you must do this yourself in
# a logged-in browser session" — and it is not obvious from the API response.
SUBMISSION_ROUTE = {
    "online_text_entry":   ("api",     "text can be submitted through the API"),
    "online_url":          ("api",     "a URL can be submitted through the API"),
    "online_upload":       ("api",     "a file can be uploaded through the API"),
    "media_recording":     ("browser", "media recording needs the Canvas UI"),
    "online_quiz":         ("browser", "the quiz engine needs a real logged-in session"),
    "discussion_topic":    ("api",     "a discussion reply can be posted through the API"),
    "external_tool":       ("browser", "LTI tool (Gradescope, publisher, peer review) lives outside Canvas"),
    "on_paper":            ("none",    "handed in physically, in class"),
    "not_graded":          ("none",    "not graded"),
    "none":                ("none",    "no submission is collected"),
}


def route_for(types: list[str] | None) -> tuple[str, str]:
    """Most-restrictive route wins: if any part needs a browser, the whole thing does."""
    if not types:
        return "none", "no submission types declared"
    ranked = {"none": 0, "api": 1, "browser": 2}
    best = ("none", "no submission is collected")
    for t in types:
        cand = SUBMISSION_ROUTE.get(t, ("browser", f"unrecognized type '{t}' — assume the UI"))
        if ranked[cand[0]] >= ranked[best[0]]:
            best = cand
    return best


def load_courses() -> list[dict]:
    if not COURSES_JSON.exists():
        raise CanvasError(
            f"{COURSES_JSON} does not exist yet.\n"
            "  Run:  python3 scripts/discover.py"
        )
    return json.loads(COURSES_JSON.read_text())["courses"]


def save_courses(courses: list[dict], term: dict | None = None) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"generated": datetime.now(local_tz()).isoformat(timespec="seconds"),
               "term": term or {}, "courses": courses}
    COURSES_JSON.write_text(json.dumps(payload, indent=2) + "\n")


def slugify(s: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in s.strip()]
    out = "".join(keep)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:80] or "untitled"
