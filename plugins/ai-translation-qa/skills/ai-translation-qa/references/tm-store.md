# Cross-job TM & termbase (`scripts/tm_store.py`)

The one asset a translation operation compounds is its memory: confirmed term
decisions and delivered segment pairs. This store persists both across jobs.
Master data is plain JSONL (one file per **client + language pair** — never mix
clients; a TM is client-confidential material). The SQLite file the script
builds is a throwaway in-session cache, never the master.

## Where masters live

Wherever durable storage exists, under a `tm/` namespace. Precedence when both
exist: project knowledge is the master; a client-supplied TMX/termbase is
imported into it (provenance recorded), not used side-by-side.

- Project knowledge: `tm/tm-<client>-<pair>.jsonl`, `tm/termbase-<client>-<pair>.jsonl`
- Or a client folder / repo the orchestrator can read and write.

If no store exists for the client, create one at the first delivery — the
job's Sheet 4 glossary and delivered bilingual table are exactly the seed.

**Masters are written only by `tm_store.py`** (`add-tus`, `add-terms`, `set-term`,
`compact`) — never by hand, never by a script of your own. A hand-written master
in another shape (`source`/`target`, no `type`) was skipped by `build` without a
word, so a whole client's store read as empty; `build` now migrates such lines on
read and warns, and `compact` rewrites the file in the right shape. If `build`
prints a legacy or unrecognized-line warning, compact that master and write the
result back in the same job.

Inline tag tokens (`{g5}`, `{x7}`, `{1>…<1}`) stay in the stored text, but their
ids belong to one file, so ids never decide a match, a duplicate, or a
`numbers_differ` flag. Only the markup's shape (which kinds of tag, how many)
counts, as `tags_differ` (below).

## Phase 1 — read (leverage in, before translating or reviewing)

1. Fetch the client's two masters into the workspace; `build` the cache.
2. `terms --status confirmed,derived` → inject into every translator/editor
   prompt: **confirmed** terms are mandatory (treat as glossary), **derived**
   terms are defaults the reviewer may challenge (say so in the prompt).
3. `terms --status deprecated` → the **ban list**: each deprecated row's
   rendering, plus any variants in its `forbidden` field, is a rendering the
   client rejected — inject them into BOTH `{banned_renderings}` slots: the
   Translator's (stops introduction in Mode A) and the Editor's (detects
   occurrences — the only guard that runs in Mode B, where no translator
   exists; the editor files a Terminology finding on any hit). (Populate
   `forbidden` at override time:
   `set-term --status deprecated --forbidden "variant1,variant2"`.)
4. `lookup` on all source segments → real 🟢/🟡 TM classification instead of
   guessing: 100 = reuse candidate (still re-read in context — an exact match
   delivered for another survey may be wrong here), ≥75 = fuzzy suggestions to
   fill the Translator template's `{fuzzy_suggestions}` slot, listed per
   segment id.
   **`numbers_differ: true` on a match is a mandatory edit flag** — the classic
   CAT trap is a high-percent match whose quantity changed. `tags_differ: true`
   (an exact match reports 99 with it) means the words match but the inline markup
   (kind or number of tags) doesn't — the target's tags must be placed from the new source.

## Phase 7 — write-back (leverage out, after delivery only)

**Write-back starts from a fresh fetch.** Re-fetch both masters immediately before
writing — another session may have written to them since Phase 1 — run this job's
`add-tus` / `add-terms` against the fresh files, then write those back. Append-only
records plus latest-wins resolution make that a safe merge. Never write back the copy
fetched in Phase 1: replacing the master with it silently deletes every record
another session added in between. Where several people share one store, also keep
to one open job per client + language pair at a time.

Hygiene gate, in order:
1. Only **delivered** text enters: final targets, after every fix and the
   consistency pass — never a draft, never a FAILed file's text, and nothing
   from a Mode D provenance check (that file was assessed, not delivered).
2. `add-tus` the final bilingual table (records job, date, review depth,
   final score). Dedupe is automatic.
3. `add-terms` the job's Sheet 4 glossary rows as `status=derived`
   (`decided_by` = where each decision came from). A term is upgraded to
   `confirmed` ONLY by a client/PM answer — `set-term --status confirmed
   --decided-by query-answer`. A client override: `set-term` the old rendering
   to `deprecated` (append-only history keeps the audit trail) and add the new
   one as confirmed.
4. `export-tmx` a per-job delta and include it with the deliverables when the
   client/agency runs their own TM server — their CAT TM stays the master of
   record; this store feeds the AI pipeline.
5. `add-tus` skips rows whose target equals the source (brand names, codes,
   tag-only rows — the termbase and DNT list carry those) and duplicates that
   differ only in tag ids, and writes the job's metadata once, on a batch line.
6. Check the size budget (below), then write the updated masters back to
   durable storage.

## Size budget

A Project's knowledge store has one character cap for everything in it — job
notes, references, and every client's masters together. Check it at write-back:
`tm_store.py size <masters> --cap <the store's limit>` gives the masters' share,
and the store's own usage figure (for a Project: `project_info`) gives the rest.
- **Termbases always go back** — they are small and they carry the decisions.
- **TUs go back while the store stays under ~70% of its cap** after the write.
  Past that, write the termbase only, keep that job's TUs in the `.tmx` delta, say
  so in the summary, and tell the user the store is full: the fix is to move the TU
  masters to a client folder or repo (the other durable location above) or let the
  client's CAT TM be the TU master of record.
- Run `compact` on any master that has grown by several jobs, or that `build`
  warned about; it drops duplicate and target-equals-source TUs, and collapses a
  repeated term decision into its newest line (a line that changes the status,
  banned variants, note, DNT flag or decided-by is history and is kept).

## Performance envelope

Vectorized fuzzy matching (rapidfuzz cdist, parallel): ~16 ms/query against a
100k-TU corpus; a 1,000-segment job resolves in seconds. Corpus size stays
bounded by the per-client+pair file convention. Without rapidfuzz the script
falls back to a token-overlap prefilter + difflib — same results contract,
slower; fine for small stores.

## What the store must never do

- Cross-pollinate clients (one master per client+pair, always).
- Treat a 100% match as auto-approved — context re-read is still required,
  and Mode B review depth applies to reused text like any other.
- Enter text from a job that failed its verdict.
- Silently change history — corrections append; `build` resolves latest-wins.
