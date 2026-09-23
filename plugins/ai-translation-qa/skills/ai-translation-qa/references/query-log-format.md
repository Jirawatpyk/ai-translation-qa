# Query log — questions the client must answer

When a job surfaces decisions that are the client's to make (not yours), collect
them in one query log rather than scattering them through the report or stalling the
whole job. A good query log lets the client answer fast and lets you keep working on
everything the queries don't block.

## Principles

- **Group by urgency.** Suggested bands: **Blocking** (can't finish/deliver without
  an answer), **Owner-decision** (a defect in the client's own source/artwork they
  must choose to fix), **Convention** (confirm a house style/extraction convention),
  **Reference** (asking for a glossary, TM, style guide, or master text). Blocking
  first.
- **One recommendation per row.** Say what you'd do and why, so the client can often
  just reply "agree". You are not offloading the thinking — you did it and are asking
  for sign-off.
- **Don't block the whole job on a partial-blocker.** If a query only blocks one
  segment or one table, do the rest and mark that piece provisional (see the
  "guess visibly" ground rule) rather than downing tools.
- **Route owner-decisions correctly.** A typo in the client's artwork is not yours
  to fix — raise it, recommend the fix, and leave the source faithful.

## Columns

`Query ID · Priority · Area · Segment / location · What we found · Question ·
Our recommendation · Answer · Status`

Leave `Answer` blank and `Status` = Open (or Provisional, when you filled a best-guess
and flagged it) for the client to complete. Deliver as a sheet in the QA workbook, or
inline for a small job.

## Provisional resolutions

When you resolve a blocker yourself with a best guess to keep moving, set Status =
Provisional, put the assumption and the alternatives in the row, and make the same
assumption visible at the point of use in the deliverable (a cell note or a tracked
insertion). The client confirms or overrides in one word.
