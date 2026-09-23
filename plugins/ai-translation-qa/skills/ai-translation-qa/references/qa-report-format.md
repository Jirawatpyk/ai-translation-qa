# QA report (.xlsx) structure

**Small jobs** (under 150 source words — the verdict is "zero open Major/Critical",
not a score) may deliver the report as a short `.md` file or inside the chat reply
instead of a workbook: the Summary, Findings log and Query log still appear in
full, as tables. Say which format you used. Everything else gets the workbook.

One workbook per job. Read the xlsx skill (if available) before building; use
openpyxl with header formatting, frozen top row, and column filters.

## Sheet 1 — Summary

| Field | Example |
|---|---|
| Job / files | homepage.json |
| Language pair(s) | en → th |
| Mode | Translate + QA (or: redline update) / QA review / Source verification / Provenance check |
| Segments QA'd / total | 42 / 42 |
| Source word count (basis) | 815 (English source) |
| Findings counted (Open + Accepted deviation): Critical / Major / Minor / Neutral | 0 / 1 / 6 / 2 |
| — of which Accepted deviations | 2 |
| Penalty points (Open + Accepted deviation) | 11 |
| MQM score — initial | 92.1 |
| **MQM score — final** | **98.7** |
| **Verdict** | **PASS** (threshold ≥ 95, no Critical; jobs < 150 words: verdict = zero open Major/Critical instead) |
| Revision rounds used | 1 |
| Back-translation drift found | 1 segment (fixed) |

With multiple target languages: one summary row block per language, plus a small
comparison table (language, score, verdict).

## Sheet 2 — Findings log

One row per finding. Columns:

`ID · Segment ID · Source text · Target (before) · Target (after) · Category ·
Severity · Weight · Description · Suggested fix · Found by (Editor/Proofreader/
Script(qa_checks)/Script(tag_integrity)/Back-translation/Fix verifier) · Arbitration
(Accepted/Rejected/Modified) · Status (Fixed/Rejected/Open/Accepted deviation) ·
Status reason (rejection reason, or why the deviation beats compliance)`

Status mirrors the four outcomes in SKILL.md Phase 6 §2; "Accepted deviation" =
arbitration Accepted + a deliberate decision not to change the text. What each status
weighs is `mqm-scoring.md` §Statuses — put that weight in the Weight column, don't
re-derive it here.

When the job included a client-supplied finding list (QA-tool export, LQA
sheet), add a **Supplied ref** column holding the supplier's row/segment
identifier next to your Segment ID — the content-proven mapping SKILL.md
Phase 1 step 1 requires lives here, one row per supplied finding, including
the rows arbitrated as false positives.

Color-code severity (Critical red, Major orange, Minor yellow, Neutral gray).
Rejected findings stay in the log with the rejection reason — the audit trail is part
of the deliverable. An Accepted deviation must state, in the Status reason, why the
deviation beats compliance.

## Sheet 3 — Bilingual table

Full segment table: `Segment ID · Source · Final target · TM class (reuse/fuzzy/new)
· Changed in revision? (Y/N)`. This doubles as the client's review copy and the next
job's translation memory.

## Sheet 4 — Glossary (if built or extended during the job)

`Source term · Target term · Note / DNT flag · Source of decision` — use the
provenance vocabulary from the top of `subagent-prompts.md` (client style guide § /
client term base / client TM / live client site — URL / derived), the same tags the
role prompts carry; cite the URL when a term was settled from the client's published
localized copy, so the decision is verifiable, not vibes.

## Query log sheet (add whenever the client must decide something)

When the job raises questions only the client can answer, add a **Query log** sheet —
columns, priority bands and the provisional-resolution rule all in
`query-log-format.md`. Grouped by urgency, one recommendation per row,
`Answer`/`Status` left for the client.

## Mode variations

**Source verification (Mode C)**: the Findings log gets an explicit split — a
column (or a colour) distinguishing "Extraction error — corrected (tracked)" from
"Source-artwork issue — raised, not changed". Summary adds a verification block:
source/version match, panels checked, and recompute results for any derived table
(e.g. a nutrition panel, with the basis stated). No MQM score — verdict is
PASS / PASS-with-corrections / FAIL.

**Provenance check (Mode D)**: usually no workbook — the report shape (verdict,
metadata table, exhibits, counter-evidence, recommendations, limitations) is in
`provenance-check.md` §Deliverable. Build a workbook only when the client asks for
a findings sheet; then the Summary carries the verdict label and confidence in
place of a score, and the Findings log is titled *exhibits* and says it is not
exhaustive.

**Redline / delta update (Mode A variant)**: the Bilingual sheet adds a column
`Span (unchanged / marked)`; the Summary states that unchanged text was verified
byte-identical to the published version, with the count of segments compared. When
the client's marked spans are colour-coded, the delivered file reproduces the
colour on exactly the mirrored target span.

**Back-translation**: the Bilingual sheet is the core deliverable; mark reproduced
source defects with `[sic]` in the target column so the reviewer sees them. Score as
Full TEP. If the source has native-target rows or a derived table, fill and verify
them per the Mode C / recompute rules.

## Tier variations

Tier execution is in `tiers.md`; this is only what the deliverable looks like.

**Light MTPE**: 2 sheets — Summary (no MQM score; the Light verdict per SKILL.md,
plus counts of post-edit changes) and Bilingual with `Changed` + `Change note`
columns. State clearly that this was a light pass. **Small jobs may ship the change
log as an `.md` file instead of the workbook** — same two blocks, summary then the
changed segments with their notes; use it when a workbook would be ceremony around a
dozen rows. Anything larger, or anything the client will filter or sort, gets the
xlsx.

**Creative best-of-3**: normal workbook (Summary shows the creative verdict per
SKILL.md, no numeric MQM score) plus **Sheet 5 — Alternatives**: `Segment ID ·
Source · Chosen (lens — list all contributing lenses if grafted) · Candidate A
(FAITHFUL) · Candidate B (NATURAL) · Candidate C (BOLD) · Judge score A/B/C · Judge
rationale`.

## Chat summary (accompanies the file)

Per language, 3–6 lines: verdict (+ score on Full tier only), counts by severity, top
fixes worth knowing about, anything unresolved or needing the user's decision. No
finding-by-finding dump — that's what the workbook is for.
