---
type: regex
weight: 2
pattern: "COMMAND:.*hyperwrite\\.py"
match: contains
---
It must render with the raster engine, not the legacy vector one and not a hand-rolled script.
Graders only see the final message, which is why the prompt demands a COMMAND: line.
