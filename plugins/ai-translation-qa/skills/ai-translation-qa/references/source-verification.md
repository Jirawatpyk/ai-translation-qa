# Mode C — source verification (prep file check)

Before a translation or back-translation starts, the client often needs the
*extracted* source checked against the *original* artwork it came from. The
deliverable is not a translation — it is a marked-up source plus a findings report.
Common in label, packaging, IFU, and clinical-document localization.

## The one rule that governs everything

**Separate two kinds of problem and treat them oppositely:**

- **Extraction error** — the extraction changed, dropped, or garbled what the
  artwork actually says (a wrong character, a stray tab, a missing space, a symbol
  captured as a letter). → **You fix it**, as a tracked change.
- **Defect in the original artwork** — the artwork itself is wrong (a typo, an
  inconsistency, a grammar slip), and the extraction faithfully reproduced it. →
  **You report it, and you do NOT change the extracted file.**

Silently fixing an artwork defect is the worst outcome: it hides the client's real
problem and the defect ships to print. When in doubt about which kind it is, treat
it as an artwork defect and raise a query — the client owns the artwork.

## Before you start: verify source and scope

(The SKILL.md "verify source & domain" gate applies to every mode; in Mode C it is
sharper because there are TWO files to reconcile.)

- Confirm the extracted file and the artwork are the same item/version. Product
  labels carry an internal file name, SKU, market/affiliate code, and revision —
  check they match the handoff. State the match in the report.
- Identify the domain (medical/FSMP, cosmetic, food, legal…) — it sets how strict
  the check is and which panels matter most (ingredients, nutrition, claims,
  warnings).

## Method

1. Extract the text layer of both files programmatically for a first-pass diff, but
   treat the artwork **image** as ground truth — see `input-fidelity.md`. Render
   every panel at high resolution and compare visually; a legacy-font PDF text layer
   cannot be trusted for character- or space-level findings.
2. Segment the extracted file with stable IDs (as Phase 1). `qa_checks.py` is a
   bilingual source-vs-target differ, so it doesn't fit Mode C directly (there's no
   target). Either skip it, or if you have a reliable OCR of the artwork panels, run
   it with `source` = artwork OCR and `target` = extraction to diff numbers,
   placeholders and tags — and IGNORE its "identical to source", length-ratio, and
   glossary findings, which are cross-language checks that don't apply here. The
   authoritative comparison is visual (step 1), not the script.
3. Walk every panel: numbers and units, ingredient/chemical names, claims,
   warnings/contraindications, addresses and codes, certification marks. For any
   table where values are derived (nutrition panels especially), **recompute** — see
   the recompute ground rule; state the basis in the report.
4. For each discrepancy, decide: extraction error or artwork defect. Log both; fix
   only the former.

## Deliverables

- The extracted file with extraction errors corrected as **tracked changes**
  (`scripts/docx_tracked_edit.py`), track-changes left ON, original file untouched.
- A QA report (`qa-report-format.md`) with a findings log that separates "corrected
  (tracked)" from "source-artwork issue (raised, not changed)", a verification
  summary (source/version match, panels checked, recompute results), and a **query
  log** (`query-log-format.md`) for anything the client must decide.
- A short chat summary: verdict (PASS / PASS-with-corrections / FAIL), counts by
  type, the single highest-risk item, and what you need answered to proceed.

## Handing off to translation

If the same file then goes to translation/back-translation, translate from the
**corrected** source (tracked changes accepted), and confirm that with the user
first — don't assume.
