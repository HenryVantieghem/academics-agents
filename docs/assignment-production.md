# Producing a graded artifact

The procedure, learned the expensive way. Read it before generating anything that
will be submitted, printed, or studied from.

---

## 1. Read the grading contract before the problems

The largest failure mode is producing a technically-correct artifact of the wrong
*kind*. Before solving anything, find and read the assignment itself, the course's
submission-rules document, and the syllabus section covering that assessment type.

Ask specifically: **is this graded on correctness or on completion?** They demand
different documents.

A real example: one course's "Self-Evaluations" are graded on *completion*, and
completion is defined as a three-step artifact — work the problems, correct them
in a different colour without erasing the original, then write a note per problem
naming the error you made. A clean answer key contains none of those three things
and scores *lower* than a messy honest attempt. Building it as a key wastes the
entire effort.

Extract before solving: file type, naming convention, platform, per-problem page
mapping, whether work must be shown, whether answers must be boxed. These are
worth real marks and are invisible from the Canvas API.

## 2. Do not trust a text extractor on an assignment PDF

Two silent failures, both of which cost real answers.

**Embedded-image tables.** A data table can be a raster image that appears in
neither `pypdf` nor `pdftotext -layout` — no error, no gap marker, just prose
reading "…the following properties:" followed by nothing.

```bash
pdfimages -png -f 1 -l 1 assignment.pdf ./extracted    # then actually look at the PNG
```

**Flattened exponents.** A document can print `b_ij = (−1)(i+j)` where the source
textbook has `(−1)^{i+j}`. Those give opposite answers. Text extraction cannot
tell them apart; font size can:

```python
recs = []
def visit(text, cm, tm, fd, fs):
    if text.strip():
        recs.append((round(tm[5], 2), round(fs, 2), text))   # baseline y, size
page.extract_text(visitor_text=visit)
```

Real superscripts render smaller *and* raised. Compare the term against the
subscripts on the same line, and confirm with a high-DPI crop.

**Answer the problem as printed, and note the discrepancy with the alternative.**
That is un-losable whichever key the grader holds. Never fill a missing given
from recollection of the textbook — if prose references data you cannot see, you
have not read the assignment yet.

## 3. Verify numerically before any human sees it

Every claim should have been checked by code that did not read the answer first.

- Substitute solutions back into the original equations
- Assert the free-variable count equals `columns − rank`
- For optimisation: brute-force **every** pairwise constraint intersection,
  including the infeasible ones, test each against *all* constraints, then rank
  only the survivors. This is what catches a designed trap where the
  highest-scoring point is infeasible.
- For algebraic transformations: sample thousands of points and assert the two
  feasible sets agree

## 4. A renderer exiting 0 does not mean the document is correct

`pdflatex` reports success on visibly broken output. Gate on the warning count
being zero **and** render every page to an image and look at it. Checking page 1
is not checking.

The specific bug worth memorising: a boxed-answer macro beginning with `\vspace`
does not break the paragraph, so the box is set on the *preceding line* and runs
off the page. Answers vanish; the build says success.

```latex
\newcommand{\FA}[1]{\par\vspace{5pt}\noindent
\fbox{\parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}{\textbf{Final answer:} #1}}
\par\vspace{5pt}}
```

In figures, a label crossed by a plotted line is a legibility defect. Fix it with
an opaque background on the label, or move the labels into a legend clear of the
plot — nudging coordinates trades one collision for another.

## 5. Adversarial review, and verify what it tells you

Have a second agent re-solve the assignment *independently from the source*
before comparing, and grade against the rubric document. Instruct it to find
errors, not to agree.

Two rules learned the hard way:

- **Verify every finding yourself before acting on it.** A grader claim that
  changes an answer deserves the same scrutiny as your own.
- **Pin the artifact's identity in the request** — page count and checksum.
  Otherwise you get a verdict on a build you already replaced, and a stale pass
  is worse than no pass.

Re-dispatch after every fix round, and never report a grade you did not receive
against the current bytes.

## 6. Model past graded work for structure — inspect what you are copying

Prior submissions are the best available reference for depth and organisation.
Check them (`pdffonts`, metadata) before imitating: what earned the marks is the
structure, not necessarily the presentation, and some presentation choices are
not yours to reproduce.

## 7. Do not infer assessment content from a schedule row

A schedule reading "Probability Review · Quiz 0" preceded a quiz that turned out
to be five questions about course logistics. Open the assessment. Where the topic
row and the actual item disagree, the item wins.

## 8. Ordering that avoids rework

1. Refresh · read the grading contract · read the rubric document
2. Extract the assignment — **including images** — and resolve typesetting ambiguity
3. Solve, and verify numerically in code
4. Build the artifact in the *shape the rubric wants*
5. Gate: zero renderer warnings, and inspect every rendered page
6. Adversarial grade against the current bytes; verify each finding; fix; re-dispatch
7. Record what you learned where the next run will read it
