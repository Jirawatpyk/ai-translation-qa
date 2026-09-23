# Changelog

Versions of the `ai-translation-qa` plugin. The plugin version and the skill
version are the same number. Users receive an update only when the version in
`plugins/ai-translation-qa/.claude-plugin/plugin.json` and
`.claude-plugin/marketplace.json` changes.

## 1.10.4 — 2026-09-23

First regression run on real Trados Studio files (one client job, six target
languages, plus Studio's sample project), and the tagged write-back opened in
Trados Studio 2021: Verify reports no tag errors and Save Target produces the
document with the new text. Findings and fixes:

- Studio writes Perfect Match / TM targets with their own tag ids (`pm…`). Rendered
  raw, a correct locked match read as 4 Critical + 4 Major tag defects. `extract` now
  maps each such id to the source tag with the same formatting definition
  (`target_id_aliases`); ids with no proven twin still surface as a tag-set
  difference.
- `apply` now stamps every segment it changes the way Studio's editor does: `Draft`
  (or `Translated` with `--set-confirmed`), the previous origin pushed into
  `prev-origin`, and `origin="mt"` with `origin-system` naming this pipeline
  (`--origin-system` to change the name). Before, a filled segment still showed Not
  Translated, and an edited 100% TM match still claimed to be one. An edit equal to
  the live target is not written or stamped (`unchanged_ids`).
- `apply` refuses an edit carrying an unmapped `pm…` token instead of writing it as
  text; tag-definition signatures are scoped per `<file>` and include the tag name.
- `tag_integrity.py` no longer reports an empty target (that is `qa_checks.py`'s
  finding; reporting it twice doubled the penalty), and parses Studio `pm…` ids as
  tags instead of text.
- The XML declaration's line break (none, LF or CRLF) is kept on apply.
- TM store: a master written by hand in another shape (`source`/`target`, no
  `type`) was skipped by `build` without a word, so that client's store read as
  empty. `build` now migrates such lines and warns; the new `compact` command
  rewrites a master in the documented shape, drops duplicate and target-equals-source
  TUs, and drops repeated term lines while keeping term history.
- TM store: inline tag ids are ignored when matching, deduplicating and comparing
  numbers. The same sentence with other tag ids is now a 100% match, and tag ids no
  longer raise `numbers_differ`. The same words with different markup (kind or number
  of tags) report 99 plus `tags_differ`, listed after any clean 100; a tag-only segment matches nothing.
- TM store: `add-tus` writes the job metadata once per job on a batch line (only bare
  TU lines inherit it; a line carrying its own metadata, or a legacy line, never
  does), skips
  rows whose target equals the source, and omits empty fields. On the real masters
  this cut storage by 28–62%. The new `size` command and a size-budget rule in
  `references/tm-store.md` cover the Project knowledge cap: termbases always go
  back, and TUs only while the store stays under about 70% of its cap.
- **Compatibility:** a master written by 1.10.4 keeps job metadata on batch lines,
  which 1.10.3 and earlier ignore. Those versions still read every TU and term but
  lose the TUs' job, date and review fields. Update every account that shares a
  store (the marketplace's automatic sync does this).
- Tests: `test_tm_store.py` added, and `test_cat_apply.py` and
  `test_tag_integrity.py` extended.

## 1.10.3 — 2026-09-23

Prompt audit for Claude Opus 5.5. Behavioural probes on the new model confirmed the
role templates work unchanged (proofreader recall, injection resistance, revision
scope, no unprescribed sub-agents, a full headless job delivered in one turn). Four
small fixes:

- Tier choice: removed "When in doubt, use this" (Full TEP), which contradicted "when
  the signal is mixed, ask" and matches a documented over-trigger pattern.
- No glossary supplied: build a derived glossary, work with it and log it as a
  Convention query, instead of stopping for confirmation. The stop remains only for
  regulated content headed for delivery.
- Length calibration: chat summary 3–6 lines per language; Mode D report one to two
  pages with at most five exhibits per severity band.
- Small jobs (under 150 source words) may deliver the QA report as `.md` or in chat,
  with the Summary, Findings log and Query log intact.

## 1.10.2 — 2026-09-22

- TM/termbase write-back now starts from a freshly re-fetched master instead of the
  copy read in Phase 1. Replacing a master with a stale copy silently deleted records
  another session had added in the meantime. This matters as soon as more than one
  person works against the same store. When several people share a store, keep one
  open job per client + language pair.
- First release as a plugin (marketplace repo, synthetic tests, release gate).

## 1.10.1 — 2026-09-17

- SKILL.md cut from 604 to 530 lines. Removed text that repeated the reference files
  it already points to. An independent rule-loss audit was run afterwards, and the
  rules it flagged were restored, including: build the DNT list from the published
  copy for that language, and never feed a multi-language workbook to the scripts as
  one file.

## 1.10.0 — 2026-09-16

- **Mode D, provenance check**: was this translation human or MT/AI? The check reads
  three layers of evidence (file metadata, linguistic signatures, counter-evidence)
  and gives a labelled verdict with a confidence level. It produces no MQM score and
  no fixes.
- **Redline / delta update** (a variant of Mode A):
  - Text outside the marked spans stays byte-identical to the published version.
  - The target span mirrors the source span.
  - Legacy defects are reported, not repaired.
- **Tagged-segment apply** for SDLXLIFF and MXLIFF:
  - The target's inline elements are rebuilt from the source tags.
  - The edit must carry exactly the source's tokens.
  - Refusals give their reasons.
- `tag_integrity.py` now reads `{gN}` / `{/gN}` / `{xN}` extractor tokens, so Trados
  files get placement checks.
  - New Major check: a Latin letter run split by a paired tag.
  - Standalone placeholders are no longer order-checked.
  - An `{eptN}` before its `{bptN}` is flagged.
- `qa_checks.py` no longer reports "identical to source" on segments with nothing
  translatable in them: DNT terms, codes, tags and URLs only.
- `sdlxliff_io.py extract` reports `origin_system` and the `prev_origin` chain.
  Interactive over MT means post-edited MT.
- New rules:
  - A source-embedded gloss is rendered once.
  - Labels and headings get priority in the back-translation sample.
  - A list of expected false positives for arbitration.
  - Script findings are triaged on the Light tier.
  - One DNT list per language.
  - memoQ MQXLIFF files are read-only.

## 1.9.0 and earlier

- TEP pipeline with a four-eyes sub-agent design, three tiers (Full, Light, Creative),
  MQM scoring, the revision loop, the fix verifier, SDLXLIFF/MXLIFF I/O, the
  cross-job TM store, a brief-provenance rule, and injection guards on every role
  template.
