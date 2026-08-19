#!/usr/bin/env python3
"""One-shot setup: discover -> scaffold -> harvest -> baseline -> dashboard.

    python3 scripts/setup.py

Everything it runs is idempotent, so re-running is safe.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE.parent / ".env"
STEPS = [
    ("discovering your courses",        [sys.executable, "discover.py"]),
    ("creating the course folders",     [sys.executable, "scaffold.py"]),
    ("harvesting Canvas content",       [sys.executable, "harvest.py"]),
    ("recording the change baseline",   [sys.executable, "refresh.py"]),
]


def main() -> int:
    if not ENV_FILE.exists():
        print("\n  No .env yet — starting the interactive setup first.")
        r = subprocess.run([sys.executable, "init.py"], cwd=HERE)
        if r.returncode != 0 or not ENV_FILE.exists():
            return r.returncode or 1

    for i, (label, cmd) in enumerate(STEPS, 1):
        # flush before handing stdout to the child, or the child's output lands
        # above our header and the error looks like it came from nowhere
        print(f"\n[{i}/{len(STEPS)}] {label}", flush=True)
        print("-" * 70, flush=True)
        r = subprocess.run(cmd, cwd=HERE)
        if r.returncode != 0:
            print(f"\n  Step {i} failed: {label}")
            print("  Fix the error printed above, then run this again.")
            print("  Every step is idempotent, so re-running costs nothing.")
            if i == 1:
                print("\n  Most first-run failures are just a missing or wrong .env.")
                print("  See the 'Setup, from nothing' section of README.md.")
            return r.returncode
    print("\n" + "=" * 70)
    subprocess.run([sys.executable, "dashboard.py"], cwd=HERE)
    print("""
  Setup is done. What exists now:

    data/courses.json          your course registry
    courses/<CODE>/_canvas/    a readable mirror of everything Canvas exposes
    courses/<CODE>/00-context/ CONTEXT + SKILL stubs, full of UNKNOWN markers

  The stubs are deliberately unfilled. Hand the agent the prompt in README.md
  and it will read each course's harvested material and syllabus and turn those
  stubs into real per-course expertise.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
