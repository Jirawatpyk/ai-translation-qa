# MQM-style scoring

Severity-weighted quality scoring based on MQM (Multidimensional Quality Metrics),
the industry-standard LQA framework. Every finding gets a category and a severity;
the score falls out arithmetically — no vibes.

Applies to the **Full TEP tier** (Mode A and Mode B reviews, including
back-translation). Light MTPE and Creative jobs each have their own verdict, defined
in SKILL.md §Pipeline tier — read it there rather than inferring one from the gates
below; they are not the same gate. **Mode C source verification** has no MQM score
either (verdict PASS / PASS-with-corrections / FAIL), and neither does a **Mode D
provenance check** (a labelled verdict with a confidence level — a score on a
sampled, exhibit-oriented read would be false precision). All of these report **no
numeric score**, because the arithmetic below doesn't honestly fit a light pass,
transcreation, or an extraction check.

## Error typology

| Category | Sub-types | Typical severity |
|---|---|---|
| **Accuracy** | mistranslation, omission, addition, untranslated text | Major–Critical |
| **Terminology** | wrong term vs glossary, inconsistent term across segments | Minor–Major |
| **Linguistic conventions** | grammar, spelling, punctuation, word order | Minor–Major |
| **Style** | wrong register, awkward/unnatural phrasing, style-guide violation | Minor |
| **Locale conventions** | number/date/currency/unit format, address/name order | Minor–Major |
| **Markup & placeholders** | broken/missing/reordered tags, `{var}`, HTML, escapes | Major–Critical |
| **Design/format** | truncation risk, length limit violation, encoding | Minor–Major |

## Severity weights

| Severity | Weight | Meaning |
|---|---|---|
| Neutral | 0 | Preference / for-your-information; no penalty |
| Minor | 1 | Noticeable but doesn't hinder meaning or use |
| Major | 5 | Distorts meaning, confuses users, or misuses a mandated term |
| Critical | 25 | Wrong meaning with real consequences, legal/safety issue, broken placeholder that crashes UI |

**Severity for answer options, UI lists, and other pick-one/pick-many items** —
the recurring judgement call the table above doesn't settle. Grade by whether a
respondent/user is *stranded*, not by how wrong the words are:

- **Critical** — the item measures a different construct than the source (a scope
  word added or dropped from a question stem changes who answers it), or a
  respondent group is silently routed to the *wrong* option they would confidently
  pick (a false friend that reads correct).
- **Major** — a whole group the source addresses is left with no option they
  recognise as theirs (a generic job title narrowed to one specialty strands
  every other holder of that job; an abstract noun where every sibling option is
  a person noun gives its holders nothing to pick), or an instruction references
  an option label that doesn't exist in the list.
- **Minor** — one half of a two-part option is wrong but the other half still
  catches the intended group, or a fallback option ("Other X professional")
  absorbs the confused group. The defect costs precision, not respondents.

The test in one line: *name the person the source intends to capture, and ask
where they land in the target*. Wrong construct → Critical; nowhere → Major;
somewhere acceptable via the good half or a fallback → Minor.

## Score formula

For each target language:

```
penalty      = Σ (weight of each accepted finding)
word_count   = source word count of QA'd segments
score        = max(0, 100 × (1 − penalty / word_count))
```

**Pass = score ≥ 95 AND zero unresolved Critical errors.**

## Statuses

The canonical definition of the four arbitration statuses and what each costs.
SKILL.md Phase 6 §2 names them and states the two severity limits; the arithmetic
lives here.

- **Fixed** = 0. The row stays in the findings log; the penalty does not.
- **Rejected** (false positive) = 0, with the rejection reason logged.
- **Open** (unresolved defect, still in the delivered text) = full weight.
- **Accepted deviation** (deliberate, documented departure still in the delivered
  text) = **full weight**. The label changes the *narrative* — it is a decision, not
  a miss — never the arithmetic. A score that zeroes its own deliberate deviations
  is self-graded homework.

**Deviation gates.** A Critical finding can never be closed as Accepted deviation —
it is Fixed, or it stays Open and fails the verdict. A Major deviation requires a
query-log row (client sign-off); Minor/Neutral need only the logged reason.

**Redline updates score the marked spans only.** A defect in carried-over published
text is filed with the `[legacy]` prefix, status **Rejected** with reason
"out of scope — published text" (weight 0), and a query-log row — it is the client's
text, reported, never repaired or scored (`redline-update.md`).

**Gates count Status=Open only** — the deviation still pays its weight in the numeric
score. This holds for every verdict gate in the skill: the Full-tier "zero unresolved
Critical", the small-job "zero open Major/Critical", and each tier's own verdict as
defined in SKILL.md §Pipeline tier.

## Rules that keep the score well-defined and comparable between runs

- **Denominator** = source words of segments actually reviewed (🟡 fuzzy + 🟠 new;
  include 🟢 reuse segments only if they were also reviewed). Sheet 1 must state
  exactly this set in "Segments QA'd" and "Source word count (basis)".
- **Count only findings that survived arbitration** (not Rejected) **and are still
  present in the delivered text** (Status = Open or Accepted deviation) — a Fixed
  finding keeps its log row with zero effective penalty. Report both initial and
  final scores.
- **Systematic repeats**: N occurrences of the same root cause (identical wrong
  term, identical formatting choice) = 1 × full severity weight + (N−1) × Minor.
  Applies to Terminology, Style, and Locale-convention errors only — never to
  Markup/placeholder or Accuracy errors, which always count individually. In the
  findings log, for a Major/Critical root keep each occurrence's severity label
  but put the discounted weight in the Weight column, referencing the primary
  finding's ID.
  **The discount only bites on Major/Critical roots** — for a Minor root the
  formula degenerates to N × Minor, i.e. no discount at all. That is intended:
  N Minor slips of one root cause genuinely cost N points. Log a Minor root as
  ONE finding row listing all affected segment IDs with weight N (cleaner than
  N identical rows), but don't expect — or hand-apply — a reduction the formula
  doesn't give.
- **Small jobs (< 150 source words)**: the formula is degenerate (one Minor in a
  10-word string scores 90), so skip the numeric threshold — verdict is simply
  "zero open Major/Critical", and the report notes the sample is below scoring size.
- **Never compare scores across unequal review depth without saying so.** A text
  that went through the full loop (independent editor + proofread + back-translation
  + revision rounds) will always outscore a once-through draft, and presenting the
  two numbers side by side implies a quality gap that the process gap alone
  explains. When reporting a score for a draft that got one pass — someone else's
  translation, or your own before revision — state the review depth next to the
  number, and say plainly that the same loop would move the other version too.
  This does **not** apply to the mandated initial/final pair: those are the same
  text before and after one review, which is exactly the comparison they exist to
  make. It applies when the two numbers describe **different texts**.
- **Score the text you are delivering.** If the job ships someone else's version
  (see SKILL.md Mode B on two independent versions), the reported score must be that
  version's, not your own draft's. A score attached to a text nobody receives is
  worse than no score.

Worked example: 500 source words, 3 Minor + 1 Major accepted →
penalty 8 → score = 100 × (1 − 8/500) = 98.4 → PASS (if no Critical).

## Locale notes

**Word counting for no-space scripts** (Thai, Lao, Khmer, CJK): when the source is
English (or another spaced language), always count words on the source side. When
the *source* is a no-space script, approximate from non-space characters after
stripping markup — Thai ≈ ÷ 4.5, Khmer ≈ ÷ 4.5, Lao ≈ ÷ 4, CJK ≈ ÷ 2 — or count the
English target side instead if available (usually the more defensible basis).
State which basis was used in the report.

**Thai specifics** (common review targets for th ↔ en work):
- Register and politeness particles (ครับ/ค่ะ/คะ): consistent with audience and
  style guide; UI text usually omits them, letters/support replies usually keep them.
- Formal vs colloquial pronouns (คุณ/ท่าน/เรา) must be consistent document-wide.
- No plural inflection — check that counts/quantifiers carry number meaning instead.
- Classifiers (ลักษณนาม) must match the noun.
- Loanwords: follow the Royal Society transliteration or the client glossary, not
  ad-hoc spellings; keep established product terms in English if the glossary says so.
- Spacing: Thai uses spaces between clauses/sentences, not words — don't flag
  missing inter-word spaces; do flag missing space before/after English inline terms
  and numbers per Thai typographic convention.
- Dates/numbers: Buddhist Era (พ.ศ.) vs CE (ค.ศ.) per style guide; Arabic vs Thai
  numerals per style guide.
