---
max_turns: 25
allowed_tools: [Read, Glob, Grep, Skill, Bash]
---
I took a photo of a page of my own handwriting and I want new pages that look like it. The photo is at `assets/henry-handwriting-sample.png` in this skill.

Work out the settings from the photo rather than guessing, render a sample page of any text, and tell me numerically how close it came.

Your final reply must end with these three lines, exactly in this form and nothing after them:

MEASURED: <the flags you derived from the photo>
MATCH: <the match score out of 100>
GAP: <the one thing that still does not match, in one sentence>
