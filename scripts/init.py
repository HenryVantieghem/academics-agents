#!/usr/bin/env python3
"""Interactive first-time setup: asks for your Canvas details and writes .env.

    python3 scripts/init.py

Prompts for your Canvas address and access token, writes them to .env, then
immediately calls Canvas to prove the token works. Finding out the token is
wrong here is much better than finding out three steps later.

The token is typed hidden (like a password) and never echoed to the screen.
"""

from __future__ import annotations

import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"


def normalize(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    # People paste a course or login URL. Keep only the origin.
    parts = url.split("/")
    if len(parts) > 3:
        url = "/".join(parts[:3])
    return url


def verify(base: str, tok: str) -> tuple[bool, str]:
    req = urllib.request.Request(base + "/api/v1/users/self/profile",
                                 headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            me = json.loads(r.read())
        who = me.get("name") or me.get("short_name") or "your account"
        tz = me.get("time_zone") or "unknown"
        return True, f"{who}  (timezone: {tz})"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, ("401 Unauthorized — the token is wrong, expired, or was "
                           "copied incompletely.\n     Canvas tokens are long; make sure you "
                           "got the whole thing.")
        return False, f"HTTP {e.code} from Canvas."
    except urllib.error.URLError as e:
        return False, (f"Could not reach {base} ({e.reason}).\n"
                       "     Check the address — it should be the one in your browser bar "
                       "when you are in Canvas.")


def main() -> int:
    print("\n  Canvas setup\n  " + "-" * 52)

    if ENV_FILE.exists():
        print(f"\n  {ENV_FILE.name} already exists.")
        if input("  Overwrite it? [y/N] ").strip().lower() not in ("y", "yes"):
            print("  Left it alone.\n")
            return 0

    print("\n  1. Your Canvas web address")
    print("     The address in your browser bar when you're in Canvas,")
    print("     for example:  https://myschool.instructure.com")
    base = normalize(input("\n     Canvas address: "))
    if not base:
        print("\n  No address given. Nothing written.\n")
        return 1

    print("\n  2. Your Canvas access token")
    print("     In Canvas: Account -> Settings -> scroll to the bottom ->")
    print("     + New Access Token -> leave the expiry blank -> Generate Token.")
    print("     Canvas shows it exactly once, so copy it before closing the box.")
    print("     (Your typing stays hidden below.)")
    tok = getpass.getpass("\n     Paste token: ").strip()
    if not tok:
        print("\n  No token given. Nothing written.\n")
        return 1

    print(f"\n  Checking the token against {base} …")
    ok, msg = verify(base, tok)
    if not ok:
        print(f"\n  {msg}")
        print("\n  Nothing was written. Fix the above and run this again.\n")
        return 1

    print(f"  Connected as {msg}")

    ENV_FILE.write_text(f"CANVAS_BASE_URL={base}\nCANVAS_TOKEN={tok}\n")
    try:
        os.chmod(ENV_FILE, 0o600)   # owner-only; harmless no-op on Windows
    except OSError:
        pass

    print(f"\n  Wrote {ENV_FILE.name}. It is gitignored, so the token stays local.")
    print("\n  Next:  python3 scripts/setup.py\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n\n  Cancelled. Nothing written.\n")
        raise SystemExit(130)
