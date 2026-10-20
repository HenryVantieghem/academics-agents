---
type: regex
weight: 3
pattern: "MEASURED:.*--(slant|size|ink|paper|showthrough)"
match: contains
---
The settings must come from `measure.py` reading the photo, not from the assistant's taste.
The MEASURED: line has to carry real flags.
