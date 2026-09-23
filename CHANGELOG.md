# Changelog

Versions of the `ai-translation-qa` plugin. The plugin version and the skill
version are the same number. Users receive an update only when the version in
`plugins/ai-translation-qa/.claude-plugin/plugin.json` and
`.claude-plugin/marketplace.json` changes.

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
