# Mode A variant — redline / delta update of a published translation

The brief says, in whatever words, "translate only what changed and mark it". The
deliverable is not a fresh translation: it is the published translation with one
controlled change in it, and the client's reviewer will judge it by how little
moved. Common for regulatory updates to patient leaflets, labels, contracts and
policy documents that already exist in the target language.

## Two rules that replace "translate everything"

1. **Every unchanged character of the target is byte-identical to the published
   version.** The published text is not yours to improve. A reviewer who finds a
   black-text difference will assume the whole file was retranslated and reject the
   delivery — or, worse, accept a silent change nobody approved. Re-extract the
   delivered file and diff it against the published text: the only differences may
   be the marked spans.
2. **The marked target span mirrors the client's marked source span exactly — no
   more, no less.** When a neighbouring comma, conjunction or full stop also has to
   change for the target grammar, do NOT widen the span to cover it: keep one
   consistent span rule across languages and reviewers, and put the collateral
   punctuation in the query log as a proposed additional change. Reviewers will
   propose widening a span so that no black character differs — each proposal is
   a different span rule; one rule, documented, beats several defensible ones.

## What the pipeline still does

- **Phase 1 gate is sharper**: confirm the published previous version is the
  version the client marked up (imprint date, revision code, page count) — a
  redline against the wrong base is worthless.
- **Legacy defects in carried-over text are reported, never repaired** (the Mode C
  rule): a misspelt drug name in the published text sits outside the redline scope;
  silently fixing it breaks rule 1 and hides the client's real problem. Raise it as
  an Owner-decision query with the proposed correction.
- **Translate the change in context**: the translator and every reviewer see the
  full published segment, with the marked span identified, so the new words match
  the register, transliteration system and list conventions already in the file
  (a new drug name harmonised with the transcription system its neighbours use;
  a serial comma added only where the target language's rule and the published
  sibling bullets support it).
- **Back-translate every changed span blind** — the change is small enough that
  the Phase 5 cap never binds, and a drug name or a dosage is exactly the content
  where a transliteration slip is a Critical.
- **The fix verifier runs on every span you author or harmonise yourself** and is
  the right place to settle transliteration arguments: keep its corrected reasoning
  in the query log, because that is what survives an in-country reviewer's
  challenge.

## Several target languages in one workbook

- One segment table and one DNT list **per language** (SKILL.md Phase 1 step 4) —
  a term that stays Latin in one language is transliterated in another.
- **Check that the change scope is parallel across languages.** A row present in
  one language's change list and absent from another's is a real gap when both
  languages would need the change (both transliterate the term, both carry the
  affected table row) and a non-issue when only one does (a language that keeps
  Latin drug names needs no work on a name-only row). Raise the gap with the
  proposed target text so the client can accept it in one word.
- Deliver the queries **inside each language's deliverable** (a block under the
  table) as well as in the log, so they survive the workbook being separated from
  the file — client-side redline workflows routinely forward one file at a time.

## Colour-coded spans in Word

A red span is **run formatting, not a tracked change** — `docx_tracked_edit.py`
does not produce it. Write the marked span as its own run (`w:color`), set the
script-appropriate font on that run (`w:cs` for Thai, Devanagari, Khmer…; the
paragraph's existing font otherwise), and leave every other run of the paragraph
untouched — including reference screenshots and cell shading. Verify by
re-extracting the document text: only the marked spans may differ from the
published text, and each must carry the colour.

## Report

Verdict per language as for Full TEP; jobs this small are almost always under the
150-word floor, so the verdict is "zero open Major/Critical" without a number. The
Bilingual sheet gains a `Span (unchanged / marked)` column, and the Summary states
that unchanged text was verified byte-identical, with the count of segments
compared (`qa-report-format.md` §Mode variations).
