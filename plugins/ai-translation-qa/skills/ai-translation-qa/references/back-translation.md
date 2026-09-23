# Regulatory back-translation (clinical / label / vendor-requested)

A back-translation renders an already-localized text back into the language of the
reviewer/master (usually English) so a reviewer can compare it against the original
master and detect meaning shifts introduced during localization. Common for clinical
trial materials, drug/device labels, and regulated marketing. It is a **deliverable
in its own right**, not the Phase 5 spot check — though it uses the same
forward-translation idea to verify itself.

**Direction, stated once so the sub-agent wiring is unambiguous**: the localized
text you were given is `source_lang`; the reviewer/master language you produce is
`target_lang`. So Phase 2 translates localized → master (that IS the
back-translation), and the Phase 5 forward-check translates the back-translation
*back into `source_lang`* (the localized language) and compares to the localized
original.

## Ask these before starting

The answers change the whole job — confirm them, don't assume:

1. **Style** — literal/close (default for regulatory: mirror the target-language
   structure so the reviewer can see shifts) vs natural English. Literal is almost
   always what regulatory back-translation vendors want.
2. **Rows already in the reviewer's language** — a label often has parts printed in
   English natively. Fill those from the artwork verbatim, don't re-translate them.
3. **Source version** — translate from the raw file, or from a corrected one (if a
   Mode C source check ran first, usually the corrected file with changes accepted).
4. **Units & numbers** — keep source units verbatim (no conversion) unless told
   otherwise; the reviewer compares like-for-like.

## Core principles

- **Literal, and let defects show through.** If the localized text is awkward,
  ambiguous, or contains a typo, the back-translation must reveal that — never
  smooth it or repair it silently. Mark a reproduced source defect with `[sic: ...]`
  so the reviewer sees it is in the source, not a translation error.
- **Never import the master's wording.** Don't reach for the phrase you think the
  English master used ("glycaemic index", "essential amino acids") — render what the
  target text literally says ("sugar index", "important amino acids"). Importing
  master terms is the cardinal back-translation error: it hides exactly the drift the
  reviewer is looking for.
- **Preserve every number, unit, and symbol** exactly; keep the do-not-translate
  list (brand names, molecules, codes, URLs) intact.

## Pipeline

Runs as Mode A at Full TEP tier, with two emphases:

- **Phase 5 becomes a real verification stage, not a sample.** Forward-translate the
  high-risk segments (every claim, every numeral, every warning/contraindication)
  back into `source_lang` — the localized language — with an isolated agent, and
  compare to the localized original: confirm no meaning drift, especially that
  contraindication polarity ("do NOT use if…", "unless prescribed") round-trips
  correctly. A reversed warning is a Critical.
- **Editor and proofreader keep the literal brief.** Tell them explicitly that
  literalness is required and that "over-smoothing" and "silently repairing a source
  defect" are findings, not improvements — otherwise they will flag correct literal
  choices and reward laundering. Default for the monolingual proofread: **skip it**
  (the deliberately literal target makes naturalness checks mostly false positives);
  run it with the literal `{mode_note}` only if the user asks for a typo pass. The
  forward-translation check above is BT's real verification.

## Deliverable

Bilingual table (source + back-translation) with `[sic]` markers on reproduced
defects, the QA report, and a query log for anything the client must resolve. If the
source had native-target rows or derived tables (a nutrition panel), fill and verify
them per the Mode C / recompute rules.
