#!/usr/bin/env python3
"""tm_store.py — cross-job translation memory + termbase store.

Master data lives in append-only JSONL files (one per client + language pair),
kept in durable storage (project knowledge, a client folder, or any file the
orchestrator can read/write). This script is the in-session performance layer:
it builds a throwaway SQLite index from the JSONL and answers exact/fuzzy
lookups fast. The SQLite file is a CACHE — never the master; rebuild at will.

Record shapes (JSONL, one object per line):
  TU:   {"type":"tu","src":"...","tgt":"...","src_lang":"en-GB","tgt_lang":"zh-TW",
         "client":"...","domain":"...","job":"...","date":"YYYY-MM-DD",
         "review":"full-tep|light|creative|external","score":98.4,"note":""}
  Term: {"type":"term","src":"...","tgt":"...","status":"confirmed|derived|deprecated",
         "dnt":false,"src_lang":"en","tgt_lang":"zh-TW","client":"...",
         "decided_by":"client glossary|client TM|client site|derived|query-answer",
         "job":"...","date":"YYYY-MM-DD","note":"","forbidden":["..."]}

Hygiene rules the CALLER must enforce (the script only stores):
  * Only DELIVERED text enters a TU file — never a failed or draft translation.
  * One JSONL per client+pair; never mix clients (confidentiality).
  * Terms start as status=derived; only a client answer upgrades to confirmed;
    a client override moves the old rendering to deprecated (keep the line —
    history is part of the asset).

Commands:
  build      master.jsonl [more.jsonl ...] --db cache.sqlite
  add-tus    bilingual.json --out master.jsonl --src-lang X --tgt-lang Y
             --client C --job J --date D [--review R] [--score S]
             (bilingual.json = [{"id","source","target"}]; dedupes on
              normalized (src,tgt); skips empty targets; prints added/skipped)
  add-terms  terms.json --out master.jsonl  (list of Term objects, dedupe src+tgt)
  lookup     --db cache.sqlite --input segments.json [--min 75] [--topk 3]
             (segments.json = [{"id","source"}] → matches JSON on stdout;
              exact matches report 100 even when --min is higher)
  terms      --db cache.sqlite [--status confirmed,derived] → termbase JSON
             (run a second query with --status deprecated for the BAN list:
              a deprecated row's tgt — plus its "forbidden" variants — is a
              rendering that must NOT re-enter a translation)
  set-term   master.jsonl --src "..." --tgt "..." --status confirmed|deprecated
             [--forbidden "variant1,variant2"]
             (appends a NEW line with the new status — append-only history;
              build keeps only the newest line per src+tgt; --forbidden stores
              additional banned spellings/variants on the same line)
  export-tmx --db cache.sqlite --out file.tmx [--client C]
  stats      --db cache.sqlite

Match scoring: exact = normalized-equality (reported 100). Fuzzy = one
vectorized rapidfuzz cdist over queries x corpus with score_cutoff (parallel
C++; ~16 ms/query against 100k TUs). Without rapidfuzz: in-memory
token-overlap prefilter (words for spaced scripts, char bigrams for
CJK/Thai/no-space) + difflib — same contract, slower. Numbers
are compared separately, digit-script- and separator-canonicalized the same
way qa_checks.py does ("๕"=="5", "1,000"=="1000" — a formatting difference is
not a changed quantity): a fuzzy match whose canonical values differ is
annotated "numbers_differ": true — the classic CAT trap where a 99% match
hides a changed quantity.
"""
import argparse, hashlib, json, os, re, sqlite3, sys, unicodedata

try:
    from rapidfuzz import fuzz, process as rf_process
    _HAVE_RF = True
    def _ratio(a, b): return fuzz.ratio(a, b)
except ImportError:  # slower stdlib fallback, same contract
    import difflib
    _HAVE_RF = False
    def _ratio(a, b): return 100.0 * difflib.SequenceMatcher(None, a, b).ratio()

CJK_RE = re.compile('[฀-๿຀-໿ក-៿'   # Thai, Lao, Khmer
                    'က-႟ऀ-ॿ'                  # Myanmar, Devanagari
                    '一-鿿㐀-䶿぀-ヿ'     # CJK, kana
                    '가-힯]')                             # Hangul
WORD_RE = re.compile(r'[A-Za-z0-9_]+')
NUM_RE = re.compile(r'\d+(?:[.,:]\d+)*')


def die(msg):
    sys.stderr.write('tm_store: %s\n' % msg)
    sys.exit(1)


def norm(s):
    s = unicodedata.normalize('NFC', s or '')
    s = re.sub(r'\s+', ' ', s).strip()
    return s.casefold()


def nkey(s):
    return hashlib.sha1(norm(s).encode('utf-8')).hexdigest()


def tokens(s):
    """FTS tokens: words for spaced text, char bigrams PLUS unigrams for
    no-space scripts. Unigrams matter for the difflib fallback's prefilter:
    with bigrams only, a single-character CJK query (or corpus entry) shares
    no token with anything and can never be proposed, even when its ratio
    clears --min — the two engines must honor the same contract."""
    s = norm(s)
    toks = WORD_RE.findall(s)
    cjk = CJK_RE.findall(s)
    cjk_run = ''.join(cjk)
    toks += [cjk_run[i:i + 2] for i in range(len(cjk_run) - 1)]
    toks += list(cjk_run)
    if not toks and s:
        toks = [s]
    return toks


def _canon_digits(tok):
    """Map every Unicode decimal digit to its ASCII value (mirrors qa_checks)."""
    out = []
    for ch in tok:
        try:
            out.append(str(unicodedata.digit(ch)))
        except (TypeError, ValueError):
            out.append(ch)
    return ''.join(out)


_DECIMAL_TAIL_RE = re.compile(r'[.,](\d{1,2})$')


def _canon_num(tok):
    """Canonical numeric value, same rules as qa_checks.canon_num: unify digit
    scripts, keep a 1-2 digit decimal tail, drop thousands separators."""
    t = _canon_digits(tok)
    frac = ''
    m = _DECIMAL_TAIL_RE.search(t)
    if m:
        frac, t = '.' + m.group(1), t[:m.start()]
    return t.replace(',', '').replace('.', '') + frac


# Space-grouped thousands ("1 000 000" — French/Nordic/Russian style). norm()
# has already collapsed NBSP/narrow-NBSP to a plain space, so one shape-gated
# plain-space pattern suffices here (qa_checks handles the raw variants).
_GROUPED_NUM = re.compile(r'(?<!\d)\d{1,3}(?: \d{3})+(?!\d)')


def digits_of(s):
    """Canonicalized numeric values — "1,000" vs "1000", "1 000" vs "1000", or
    Thai digits vs ASCII must NOT trip numbers_differ; only a genuinely
    different value may."""
    t = _GROUPED_NUM.sub(lambda m: m.group(0).replace(' ', ''), norm(s))
    return sorted(_canon_num(x) for x in NUM_RE.findall(t))


def load_json(path, what='JSON array'):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except OSError as e:
        die('cannot read %s (%s)' % (path, e))
    except json.JSONDecodeError as e:
        die('%s is not valid JSON (%s) — expected a %s' % (path, e, what))


def need_db(path):
    if not os.path.exists(path):
        die('no cache at %s — run build first' % path)


def read_jsonl(path):
    if not os.path.exists(path):
        die('cannot read %s (file not found)' % path)
    out = []
    with open(path, encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                die('%s line %d: bad JSON (%s)' % (path, i, e))
    return out


def append_jsonl(path, records):
    # If the existing file's last byte is not a newline (hand-created or
    # truncated master), appending would concatenate the new record onto the
    # last line and corrupt BOTH records — guard with a separator first.
    lead = ''
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, 'rb') as f:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b'\n':
                lead = '\n'
    with open(path, 'a', encoding='utf-8') as f:
        for r in records:
            f.write(lead + json.dumps(r, ensure_ascii=False) + '\n')
            lead = ''


# ---------------------------------------------------------------- build
def cmd_build(args):
    # read every master fully BEFORE creating the db — a failed build must not
    # leave a schema-only cache behind (a later stats/lookup would silently
    # report an empty store instead of erroring)
    loaded = [(path, read_jsonl(path)) for path in args.masters]
    if os.path.exists(args.db):
        os.remove(args.db)
    con = sqlite3.connect(args.db)
    con.executescript('''
      CREATE TABLE tu(id INTEGER PRIMARY KEY, skey TEXT, nsrc TEXT, src TEXT,
                      tgt TEXT, src_lang TEXT, tgt_lang TEXT, client TEXT,
                      domain TEXT, job TEXT, date TEXT, review TEXT,
                      score REAL, note TEXT);
      CREATE INDEX tu_skey ON tu(skey);
      CREATE TABLE term(src TEXT, tgt TEXT, status TEXT, dnt INT,
                        src_lang TEXT, tgt_lang TEXT, client TEXT,
                        decided_by TEXT, job TEXT, date TEXT, note TEXT,
                        forbidden TEXT, PRIMARY KEY(src, tgt));
    ''')
    n_tu = n_term = n_tu_bad = 0
    seen_tu = set()
    for path, records in loaded:
        for r in records:
            t = r.get('type')
            if t == 'tu':
                if not r.get('src') or not r.get('tgt'):
                    # counted and reported, not silent: a truncated or
                    # hand-edited master with gutted TU lines must not build
                    # a smaller cache without anyone noticing (terms with the
                    # same defect hard-die below — a TU is droppable data, a
                    # term is a rule, but BOTH must be visible)
                    n_tu_bad += 1
                    continue
                k = (nkey(r['src']), nkey(r['tgt']))
                if k in seen_tu:
                    continue
                seen_tu.add(k)
                n_tu += 1
                con.execute('INSERT INTO tu VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (n_tu, nkey(r['src']), norm(r['src']), r['src'],
                             r['tgt'], r.get('src_lang'), r.get('tgt_lang'),
                             r.get('client'), r.get('domain'), r.get('job'),
                             r.get('date'), r.get('review'), r.get('score'),
                             r.get('note')))
            elif t == 'term':
                if not r.get('src') or not r.get('tgt'):
                    con.close()
                    os.remove(args.db)
                    die('%s: term record missing src/tgt: %s'
                        % (path, json.dumps(r, ensure_ascii=False)[:80]))
                # append-only history: later lines win (REPLACE)
                con.execute('INSERT OR REPLACE INTO term VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                            (r['src'], r['tgt'], r.get('status', 'derived'),
                             1 if r.get('dnt') else 0, r.get('src_lang'),
                             r.get('tgt_lang'), r.get('client'),
                             r.get('decided_by'), r.get('job'), r.get('date'),
                             r.get('note'), json.dumps(r.get('forbidden', []),
                                                       ensure_ascii=False)))
                n_term += 1
    con.commit()
    con.close()
    if n_tu_bad:
        sys.stderr.write('tm_store: WARNING — %d tu record(s) skipped for '
                         'missing src/tgt; inspect the master file(s)\n' % n_tu_bad)
    print(json.dumps({'db': args.db, 'tus': n_tu, 'term_lines': n_term,
                      'tu_skipped_missing_fields': n_tu_bad}))


# ---------------------------------------------------------------- add
def cmd_add_tus(args):
    segs = load_json(args.input)
    if not isinstance(segs, list):
        die('%s: expected a JSON array of {id, source, target}' % args.input)
    existing = set()
    if os.path.exists(args.out):
        for r in read_jsonl(args.out):
            if r.get('type') == 'tu':
                existing.add((nkey(r.get('src', '')), nkey(r.get('tgt', ''))))
    added, skipped = [], 0
    for s in segs:
        src, tgt = str(s.get('source') or ''), str(s.get('target') or '')
        if not src.strip() or not tgt.strip():
            skipped += 1
            continue
        k = (nkey(src), nkey(tgt))
        if k in existing:
            skipped += 1
            continue
        existing.add(k)
        added.append({'type': 'tu', 'src': src, 'tgt': tgt,
                      'src_lang': args.src_lang, 'tgt_lang': args.tgt_lang,
                      'client': args.client, 'domain': args.domain,
                      'job': args.job, 'date': args.date,
                      'review': args.review, 'score': args.score, 'note': ''})
    append_jsonl(args.out, added)
    print(json.dumps({'added': len(added), 'skipped': skipped, 'out': args.out}))


def cmd_add_terms(args):
    terms = load_json(args.input)
    if not isinstance(terms, list):
        die('%s: expected a JSON array of term objects' % args.input)
    existing = set()
    if os.path.exists(args.out):
        for r in read_jsonl(args.out):
            if r.get('type') == 'term':
                existing.add((norm(r.get('src', '')), norm(r.get('tgt', ''))))
    added = []
    for t in terms:
        if not t.get('src') or not t.get('tgt'):
            die('term missing src/tgt: %s' % json.dumps(t, ensure_ascii=False)[:80])
        k = (norm(t['src']), norm(t['tgt']))
        if k in existing:
            continue
        existing.add(k)
        t = dict(t)
        t['type'] = 'term'
        t.setdefault('status', 'derived')
        added.append(t)
    append_jsonl(args.out, added)
    print(json.dumps({'added': len(added), 'out': args.out}))


def cmd_set_term(args):
    rows = [r for r in read_jsonl(args.master)
            if r.get('type') == 'term' and norm(r.get('src', '')) == norm(args.src)
            and norm(r.get('tgt', '')) == norm(args.tgt)]
    if not rows:
        die('term not found: %s -> %s' % (args.src, args.tgt))
    r = dict(rows[-1])
    r['status'] = args.status
    if args.decided_by:
        r['decided_by'] = args.decided_by
    if args.note:
        r['note'] = args.note
    if args.forbidden:
        r['forbidden'] = [x.strip() for x in args.forbidden.split(',') if x.strip()]
    append_jsonl(args.master, [r])
    print(json.dumps({'updated': True, 'src': r['src'], 'tgt': r['tgt'],
                      'status': r['status']}, ensure_ascii=False))


# ---------------------------------------------------------------- lookup
def cmd_lookup(args):
    """Batched exact + fuzzy lookup.

    Exact: skey hash. Fuzzy: one rapidfuzz cdist over (queries x corpus) with
    score_cutoff (C++-parallel, workers=-1). Without rapidfuzz: an in-memory
    token-overlap prefilter (top 200 candidates) + difflib — same contract,
    slower. Corpus size is bounded by the per-client+pair master-file
    convention; at ~100k TUs the cdist path answers a 1,000-segment job in
    seconds, not minutes.
    """
    need_db(args.db)
    con = sqlite3.connect(args.db)
    segs = load_json(args.input)
    if not isinstance(segs, list):
        die('%s: expected a JSON array of {id, source}' % args.input)
    # one scan builds both structures: the fuzzy corpus (positional columns
    # 0-5, used by _emit) and the exact-hash dict from the trailing skey
    corpus = con.execute(
        'SELECT nsrc, src, tgt, job, date, review, skey FROM tu').fetchall()
    con.close()
    exact = {}
    for row in corpus:
        exact.setdefault(row[6], []).append(row[1:6])

    out = []
    fuzzy_idx = []          # indices into segs that need fuzzy
    fuzzy_norms = []
    for i, s in enumerate(segs):
        src = str(s.get('source') or '')
        entry = {'id': s.get('id'), 'matches': []}
        out.append(entry)
        if not src.strip():
            continue
        hits = exact.get(nkey(src))
        if hits:
            for r in hits[:args.topk]:
                entry['matches'].append({'pct': 100, 'src': r[0], 'tgt': r[1],
                                         'job': r[2], 'date': r[3],
                                         'review': r[4]})
            continue
        fuzzy_idx.append(i)
        fuzzy_norms.append(norm(src))

    if fuzzy_idx and corpus:
        cnorms = [c[0] for c in corpus]
        if _HAVE_RF:
            mat = rf_process.cdist(fuzzy_norms, cnorms, scorer=fuzz.ratio,
                                   score_cutoff=args.min, workers=-1)
            for qi, row in zip(fuzzy_idx, mat):
                scored = [(float(p), corpus[ci]) for ci, p in enumerate(row)
                          if p >= args.min]
                scored.sort(key=lambda x: -x[0])
                _emit(out[qi], segs[qi], scored[:args.topk])
        else:
            inv = {}
            for ci, c in enumerate(corpus):
                for tok in set(tokens(c[0])):
                    inv.setdefault(tok, []).append(ci)
            for qi, nq in zip(fuzzy_idx, fuzzy_norms):
                counts = {}
                for tok in set(tokens(nq)):
                    for ci in inv.get(tok, ()):
                        counts[ci] = counts.get(ci, 0) + 1
                cands = sorted(counts, key=counts.get, reverse=True)[:200]
                scored = []
                for ci in cands:
                    pct = _ratio(nq, corpus[ci][0])
                    if pct >= args.min:
                        scored.append((pct, corpus[ci]))
                scored.sort(key=lambda x: -x[0])
                _emit(out[qi], segs[qi], scored[:args.topk])

    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    print()


def _emit(entry, seg, scored):
    src = str(seg.get('source') or '')
    for pct, c in scored:
        m = {'pct': round(pct, 1), 'src': c[1], 'tgt': c[2],
             'job': c[3], 'date': c[4], 'review': c[5]}
        if digits_of(src) != digits_of(c[1]):
            m['numbers_differ'] = True
        entry['matches'].append(m)


def cmd_terms(args):
    need_db(args.db)
    con = sqlite3.connect(args.db)
    statuses = [s.strip() for s in args.status.split(',')]
    rows = con.execute(
        'SELECT src,tgt,status,dnt,decided_by,note,forbidden FROM term '
        'WHERE status IN (%s) ORDER BY status, src'
        % ','.join('?' * len(statuses)), statuses).fetchall()
    out = [{'src': r[0], 'tgt': r[1], 'status': r[2], 'dnt': bool(r[3]),
            'decided_by': r[4], 'note': r[5],
            'forbidden': json.loads(r[6] or '[]')} for r in rows]
    con.close()
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    print()


# ---------------------------------------------------------------- export
# Control characters XML 1.0 cannot store at all (tab/LF/CR are fine) — JSONL
# can hold them (e.g. pasted from a PDF text layer), but writing them into the
# TMX verbatim produces a file every importer rejects.
_XML_BAD = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def _x(s):
    s = _XML_BAD.sub('', s)
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def cmd_export_tmx(args):
    need_db(args.db)
    con = sqlite3.connect(args.db)
    q = 'SELECT src,tgt,src_lang,tgt_lang,job,date FROM tu'
    params = ()
    if args.client:
        q += ' WHERE client=?'
        params = (args.client,)
    rows = con.execute(q, params).fetchall()
    con.close()
    if not rows:
        die('no TUs to export')
    srclang = rows[0][2] or 'en'
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<tmx version="1.4">',
             ('<header creationtool="tm_store" creationtoolversion="1" segtype="sentence" '
              'o-tmf="jsonl" adminlang="en" srclang="%s" datatype="plaintext"/>' % _x(srclang)),
             '<body>']
    for src, tgt, sl, tl, job, date in rows:
        attrs = ''
        if date:
            attrs = ' creationdate="%sT000000Z"' % date.replace('-', '')
        parts.append('<tu%s>%s<tuv xml:lang="%s"><seg>%s</seg></tuv>'
                     '<tuv xml:lang="%s"><seg>%s</seg></tuv></tu>'
                     % (attrs,
                        ('<prop type="x-job">%s</prop>' % _x(job)) if job else '',
                        _x(sl or srclang), _x(src), _x(tl or 'und'), _x(tgt)))
    parts += ['</body>', '</tmx>']
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts))
    print(json.dumps({'exported': len(rows), 'out': args.out}))


def cmd_stats(args):
    need_db(args.db)
    con = sqlite3.connect(args.db)
    tus = con.execute('SELECT COUNT(*) FROM tu').fetchone()[0]
    by_client = con.execute(
        'SELECT client, COUNT(*) FROM tu GROUP BY client').fetchall()
    terms = con.execute(
        'SELECT status, COUNT(*) FROM term GROUP BY status').fetchall()
    con.close()
    print(json.dumps({'tus': tus, 'by_client': dict(by_client),
                      'terms_by_status': dict(terms)}, ensure_ascii=False))


# ---------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)

    b = sub.add_parser('build')
    b.add_argument('masters', nargs='+')
    b.add_argument('--db', required=True)
    b.set_defaults(func=cmd_build)

    a = sub.add_parser('add-tus')
    a.add_argument('input')
    a.add_argument('--out', required=True)
    for f in ('src-lang', 'tgt-lang', 'client', 'job', 'date'):
        a.add_argument('--' + f, required=True)
    a.add_argument('--domain', default='')
    a.add_argument('--review', default='full-tep')
    a.add_argument('--score', type=float, default=None)
    a.set_defaults(func=cmd_add_tus)

    t = sub.add_parser('add-terms')
    t.add_argument('input')
    t.add_argument('--out', required=True)
    t.set_defaults(func=cmd_add_terms)

    st = sub.add_parser('set-term')
    st.add_argument('master')
    st.add_argument('--src', required=True)
    st.add_argument('--tgt', required=True)
    st.add_argument('--status', required=True,
                    choices=['confirmed', 'derived', 'deprecated'])
    st.add_argument('--decided-by', default='')
    st.add_argument('--note', default='')
    st.add_argument('--forbidden', default='',
                    help='comma-separated banned variants stored on the new line')
    st.set_defaults(func=cmd_set_term)

    lk = sub.add_parser('lookup')
    lk.add_argument('--db', required=True)
    lk.add_argument('--input', required=True)
    lk.add_argument('--min', type=float, default=75)
    lk.add_argument('--topk', type=int, default=3)
    lk.set_defaults(func=cmd_lookup)

    tm = sub.add_parser('terms')
    tm.add_argument('--db', required=True)
    tm.add_argument('--status', default='confirmed,derived')
    tm.set_defaults(func=cmd_terms)

    ex = sub.add_parser('export-tmx')
    ex.add_argument('--db', required=True)
    ex.add_argument('--out', required=True)
    ex.add_argument('--client', default=None)
    ex.set_defaults(func=cmd_export_tmx)

    s = sub.add_parser('stats')
    s.add_argument('--db', required=True)
    s.set_defaults(func=cmd_stats)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
