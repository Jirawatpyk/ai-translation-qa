# Mode D — translation provenance check

The question is not "is this translation good?" but **"how was it produced?"** —
from-scratch human work, human work leveraged from a TM, machine/AI output with
post-editing (full or uneven), or raw MT. Clients ask when a vendor's delivery reads
oddly, when a contract forbids MT for the content class (legal, public-facing,
regulated), during a procurement audit, or before deciding whether to pay for a full
review. The deliverable is a **verdict with a confidence level and the evidence
behind it**, not a scored findings log.

Mode D is deliberately narrower than Mode B: no MQM score, no per-segment fix, and
the findings it lists are **exhibits, not an exhaustive log**. Say that in the report.
A Mode B review often follows on the same file once the client decides what to do.

## Method — three layers, converging

No single finding proves provenance. Fluent MT exists; sloppy humans exist. The
verdict rests on patterns that **converge across independent layers**, and the report
shows the layers separately so a reader can weigh them.

### Layer 1 — file metadata (whole file, always)

Read what the CAT file records about its own history before reading a word of
translation:

- **SDLXLIFF**: `sdlxliff_io.py extract` gives `origin`, `origin_system`,
  `prev_origin`, `percent` and `conf` per segment. **`interactive` means a linguist
  edited the segment, not that they typed it from scratch**: Studio pushes the
  earlier state into the `prev_origin` chain, so `interactive` over a `prev_origin`
  of `mt` is post-edited MT, and `origin_system` (when Studio recorded it) names the
  provider. A file with no `prev_origin` anywhere and `interactive` throughout is
  the human pattern; read the chain before saying so.
- **MXLIFF**: `mxliff_io.py extract` gives `m:trans-origin`, `m:score`, and
  `m:confirmed` — every segment unconfirmed over an `mt`/`tm` origin means no human
  has been through the file.
- **memoQ MQXLIFF** and other XLIFF 1.2 dialects: extract with lxml as SKILL.md
  Phase 1 §9 describes (same token grammar, plus the tool's status/match
  attributes — memoQ `mq:status`, `mq:percent`). An export that carries match
  rates only — a preview or review export — names no engine and no editor; say so
  under Limitations rather than inferring.

Tabulate the match-status distribution. Two implications matter most:

- **Zero new / no-match segments** means nothing was translated from scratch in this
  project: the file was pre-translated from a TM or an MT plug-in. The provenance
  question then moves to *the TM content itself*, and the same defects will reach
  every other job that draws on that TM — say so, because it changes the client's
  remedy from "fix this file" to "audit the TM".
- **Metadata proves process, never quality**, and its absence proves nothing: a
  file exported as a preview, or re-imported after external editing, loses its
  history. A file that arrives fully confirmed still says nothing about review depth.

### Layer 2 — linguistic evidence (editor sub-agent + back-translation, sampled)

Spawn an editor sub-agent with the normal Phase 3 template plus this note in
`{creative_note}`: *"This is a PROVENANCE assessment. Besides genuine errors, note
every pattern that indicates how the text was produced — see the signature list —
and quote the segment. Do not propose polish."* Back-translate the densest and the
worst segments blind (Phase 5 template) — a meaning inversion confirmed by a
back-translator who never saw the source is the strongest single exhibit.

Sampling: for files up to ~150 segments read everything; above that, take a
stratified sample that **over-represents long, dense, terminology-heavy segments**
(that is where post-editors run out of time and leave the MT raw) plus every segment
the scripts flag. Always run `qa_checks.py` and `tag_integrity.py` first — a target
with dropped tags, or tags splitting words, on a file that passed through a CAT
tool tells you no in-tool QA was run, which is itself evidence. (Tags merely
*re-ordered* to fit target syntax are not — see the human signatures below.)

**Signatures of machine output** (each is weak alone; the file-wide pattern is the
evidence):

- The **everyday sense of a polysemous word applied consistently where the domain
  sense is required** — a contract *executed* rendered as put to death, a *party*
  to an agreement rendered as a celebration, a statutory *section* rendered as a
  part of a building — and repeated in every occurrence, because nothing in the
  process knew the document's domain.
- **No document-level memory**: a key term (an office, a body, a product) rendered
  three different ways across the file; an orphan fragment produced by bad
  segmentation (a broken citation, a cut heading) translated *identically* each
  time it recurs, without anyone noticing it is a fragment.
- **Polarity and scope inversions** that read fluently: *unless* rendered as *if*,
  *no later than* as *later than*, a listed item silently dropped and an opposite
  verb supplied. Fluent-but-inverted is the neural signature; a tired human
  garbles, an engine confidently inverts — and a human translator makes the same
  inversion too, so this counts only as part of a file-wide pattern.
- **Decoding artefacts**: a phrase repeated three, five, seven times in a row inside
  one segment; a name or acronym rendered as a phonetic hash; a segment that trails
  off mid-clause.
- **Structural pass-through**: source word order kept where the target grammar
  forbids it; inline tags dropped or left splitting words; source punctuation
  conventions (straight quotes, spacing before commas) preserved.

**Signatures of human work** (also weak alone): audience-addressing additions with
no source counterpart (a form of address the target culture expects, a "you" the
source never wrote), adaptation of citations and cross-references to the target's
conventions, consistent terminology that matches a glossary or published usage,
correct handling of the tricky senses above, tags re-ordered to target syntax.

**The uneven-MTPE pattern** is the commonest real-world verdict: human signatures
appear on the short, easy segments and are absent on the long, dense ones, and the
critical errors sit exclusively in the untouched portion. Look for segments with
*identical source structure* where one carries a human addition and the other does
not — that asymmetry is what distinguishes uneven post-editing from a consistent
style choice.

### Layer 3 — counter-evidence (write it down)

Before writing the verdict, argue the other side: what in the file points *away* from
the leading hypothesis? List it in the report under its own heading. A provenance
report that shows only confirming evidence reads as advocacy and will not survive a
vendor's rebuttal; one that names the counter-evidence and explains why it does not
overturn the verdict does.

## Verdict

Use one of these labels, with a confidence level (high / medium / low) and the
one-sentence basis:

| Label | Meaning |
|---|---|
| From-scratch human translation | Layer 1 shows interactive/new origin with no MT anywhere in the `prev_origin` chain; Layer 2 shows human signatures and no machine pattern |
| Human translation with TM leverage | Match-status distribution plus human signatures; defects, if any, trace to specific TM entries |
| MT/AI with full human post-editing | Machine origin in metadata or machine signatures in residue, but errors corrected file-wide |
| MT/AI with uneven post-editing | Human signatures concentrated on easy segments; machine signatures and critical errors in the dense ones |
| Raw MT/AI output | Machine signatures throughout; no human signatures; metadata unconfirmed where available |
| Indeterminate | Layers conflict or the sample is too small — say what would settle it |

Never name a specific engine unless the metadata names it. "Consistent with neural
MT" is a defensible statement; "this was Google Translate" is not.

## Deliverable

A short report — chat summary, `.md`, or `.docx` per the client's habit; the xlsx
workbook only if the client asks for a findings sheet. Ask first **who will read it**:
a report for management leads with the verdict and the remedy; one that goes to the
vendor leads with the exhibits and stays factual in tone. A bilingual edition is often
wanted when the client's team and the vendor read different languages.

Sections, in order:

1. **Scope line** — file, pair, volume, domain, date, and the sentence "provenance
   verification only — not a full QA review; no MQM score; exhibits, not an
   exhaustive list".
2. **Verdict** — label, confidence, one-line basis.
3. **Layer 1** — the match-status/origin table and its implication.
4. **Layer 2** — exhibits grouped Critical / Major / Minor, each quoting segment id,
   source, target, and a literal gloss of what the target actually says. Critical
   here means meaning inverted or fabricated: the client needs these to hold
   delivery even though the list is not exhaustive.
5. **Counter-evidence** — and why it does not change the verdict.
6. **Source-side defects** — reported, never silently corrected (the Mode C rule);
   a wrong citation in the client's own source is theirs to fix.
7. **Recommendations** — typically: hold delivery until the Critical exhibits are
   fixed; audit and clean the TM, not just the file, when Layer 1 shows full
   pre-translation; ask the vendor directly whether MT/AI was used and what review
   occurred; check the contract's MT clause for this content class; and commission
   a Mode B review if the file is to be repaired rather than re-translated.
8. **Limitations** — what the metadata could not show, sample coverage, and that
   the conclusion rests on converging patterns rather than any single finding.

## What Mode D is not

- Not a tier: no Full/Light/Creative choice applies.
- Not a fix pass: the orchestrator authors no target text, so the fix verifier is not
  in the loop. If the client then asks for corrections, that is a Mode B job on the
  same file and it starts from Phase 1.
- Not a scoring exercise: an MQM number on a sampled, exhibit-oriented read would be
  a false precision — refuse to compute one, and say why.
