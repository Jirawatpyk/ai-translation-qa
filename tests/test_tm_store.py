#!/usr/bin/env python3
"""v1.10.4 tests for tm_store.py: legacy-shape masters, tag-id-insensitive
matching, batch-line metadata, compact. Run: python3 test_tm_store.py <scripts-dir>"""
import json, os, sqlite3, subprocess, sys, tempfile

SCRIPTS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'plugins', 'ai-translation-qa', 'skills', 'ai-translation-qa', 'scripts')
T = tempfile.mkdtemp()
fails = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else '  <- ' + str(detail)))
    if not cond:
        fails.append(name)


def tm(*args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, 'tm_store.py'), *args],
                          capture_output=True, text=True)


def write(name, lines):
    p = os.path.join(T, name)
    with open(p, 'w', encoding='utf-8') as f:
        for l in lines:
            f.write((l if isinstance(l, str) else json.dumps(l, ensure_ascii=False)) + '\n')
    return p


def js(p):
    return json.loads(p.stdout)


# ---- 1. legacy hand-written shape is read (and announced), not silently dropped
leg_tm = write('leg_tm.jsonl', [
    {'source': 'เอกสารไม่ควบคุม', 'target': 'Uncontrolled documents', 'srclang': 'th-TH', 'tgtlang': 'en-US', 'client': 'acme', 'doc': 'Policy', 'status': 'delivered'},
    {'source': 'เอกสารไม่ควบคุม', 'target': 'Uncontrolled documents', 'srclang': 'th-TH', 'tgtlang': 'en-US', 'client': 'acme', 'doc': 'Policy', 'status': 'delivered'},
    {'source': '{g45}Page {/g45}{x53}', 'target': '{g45}Page {/g45}{x53}', 'srclang': 'th-TH', 'tgtlang': 'en-US', 'client': 'acme', 'status': 'delivered'},
    {'source': 'สารบัญ', 'target': 'Table of Contents', 'srclang': 'th-TH', 'tgtlang': 'en-US', 'client': 'acme', 'status': 'delivered'},
])
leg_tb = write('leg_tb.jsonl', [
    {'source': 'ผู้ใช้งาน', 'target': 'User', 'srclang': 'th-TH', 'tgtlang': 'en-US', 'client': 'acme', 'status': 'derived', 'provenance': 'definitions table'},
])
p = tm('build', leg_tm, leg_tb, '--db', os.path.join(T, 'a.db'))
r = js(p)
check('legacy: TUs and terms load (dupes collapse at build)', r['tus'] == 3 and r['term_lines'] == 1, r)
check('legacy: counted and warned, not silent', r['legacy_records_migrated'] == 5 and 'legacy' in p.stderr, (r, p.stderr))
p = tm('terms', '--db', os.path.join(T, 'a.db'))
terms = js(p)
check('legacy: provenance becomes decided_by', terms and terms[0].get('decided_by') == 'definitions table', terms)
p = tm('set-term', leg_tb, '--src', 'ผู้ใช้งาน', '--tgt', 'User', '--status', 'confirmed', '--decided-by', 'query-answer')
check('legacy: set-term finds a legacy term', p.returncode == 0 and js(p)['status'] == 'confirmed', p.stderr)
junk = write('junk.jsonl', ['{"foo": 1}', {'type': 'tu', 'src': 'a b c', 'tgt': 'x y z'}])
p = tm('build', junk, '--db', os.path.join(T, 'j.db'))
check('unrecognized line reported', js(p)['unrecognized_lines'] == 1 and 'NOT loaded' in p.stderr, (p.stdout, p.stderr))

# ---- 2. add-tus: batch line, bare TUs, tag-id-insensitive dedupe, identical rows skipped
m = os.path.join(T, 'm.jsonl')
job1 = write('job1.json', ['[' + ','.join(json.dumps(x, ensure_ascii=False) for x in [
    {'id': 1, 'source': 'Click {g5}Save{/g5} to keep 3 copies of your changes.', 'target': 'คลิก {g5}บันทึก{/g5} เพื่อเก็บสำเนาการเปลี่ยนแปลง 3 ชุด'},
    {'id': 2, 'source': 'Click {g9}Save{/g9} to keep 3 copies of your changes.', 'target': 'คลิก {g9}บันทึก{/g9} เพื่อเก็บสำเนาการเปลี่ยนแปลง 3 ชุด'},   # same text, other tag ids
    {'id': 3, 'source': 'ACME Cloud', 'target': 'ACME Cloud'},                                  # identical: termbase's job
    {'id': 4, 'source': '{x7}', 'target': '{x7}'},                                              # nothing but a tag
    {'id': 5, 'source': 'Sign out', 'target': 'ออกจากระบบ'},
]) + ']'])
p = tm('add-tus', job1, '--out', m, '--src-lang', 'en-US', '--tgt-lang', 'th-TH', '--client', 'acme', '--job', 'J1', '--date', '2026-09-01', '--score', '98.5')
r = js(p)
check('add-tus counts: 2 added, 1 identical, 2 dup/empty', r['added'] == 2 and r['skipped_identical'] == 1 and r['skipped_duplicate_or_empty'] == 2, r)
lines = [json.loads(l) for l in open(m, encoding='utf-8')]
check('add-tus: one batch line then bare TUs', lines[0]['type'] == 'batch' and lines[0]['job'] == 'J1' and set(lines[1]) == {'type', 'src', 'tgt'}, lines[:2])
job2 = write('job2.json', ['[{"id": 1, "source": "Sign in", "target": "เข้าสู่ระบบ"}, {"id": 2, "source": "Click {g1}Save{/g1} to keep 3 copies of your changes.", "target": "x"}]'])
p = tm('add-tus', job2, '--out', m, '--src-lang', 'en-US', '--tgt-lang', 'th-TH', '--client', 'acme', '--job', 'J2', '--date', '2026-09-02')
check('add-tus second job: new batch line', js(p)['added'] == 2 and sum(1 for l in open(m) if '"batch"' in l) == 2, p.stdout)
p = tm('build', m, '--db', os.path.join(T, 'm.db'))
con = sqlite3.connect(os.path.join(T, 'm.db'))
rows = dict(con.execute("SELECT src, job || '|' || IFNULL(score, '') FROM tu").fetchall())
check('build: TUs inherit their own batch metadata', rows.get('Sign out') == 'J1|98.5' and rows.get('Sign in') == 'J2|', rows)

# ---- 3. lookup ignores tag ids (exact + numbers_differ)
q = write('q.json', ['[' + ','.join(json.dumps(x, ensure_ascii=False) for x in [
    {'id': 'a', 'source': 'Click {g77}Save{/g77} to keep 3 copies of your changes.'},                # same text, other ids
    {'id': 'b', 'source': 'Click {1>Save<1} to keep 3 copies of your changes now.'},                 # fuzzy, Phrase notation
    {'id': 'c', 'source': 'Click {g77}Save{/g77} to keep 5 copies of your changes.'},                # real number change
]) + ']'])
p = tm('lookup', '--db', os.path.join(T, 'm.db'), '--input', q, '--min', '70')
res = {e['id']: e['matches'] for e in js(p)}
check('lookup: other tag ids still an exact 100', res['a'] and res['a'][0]['pct'] == 100, res['a'])
check('lookup: tag ids never trip numbers_differ', res['b'] and not res['b'][0].get('numbers_differ'), res['b'])
check('lookup: a changed quantity still does', res['c'] and res['c'][0].get('numbers_differ') is True, res['c'])

# ---- 4. compact
cm = write('cm.jsonl', [
    {'type': 'tu', 'src': 'Hello', 'tgt': 'สวัสดี', 'client': 'acme', 'job': 'OLD', 'note': ''},
    {'type': 'tu', 'src': 'Hello', 'tgt': 'สวัสดี', 'client': 'acme', 'job': 'NEW'},              # dup: newest wins
    {'type': 'tu', 'src': 'OK', 'tgt': 'OK', 'client': 'acme'},                                    # identical: dropped
    {'type': 'term', 'src': 'cart', 'tgt': 'ตะกร้า', 'status': 'derived'},
    {'type': 'term', 'src': 'cart', 'tgt': 'ตะกร้า', 'status': 'derived'},                        # repeat: dropped
    {'type': 'term', 'src': 'cart', 'tgt': 'ตะกร้า', 'status': 'confirmed'},                      # history: kept
    '{"mystery": true}',                                                                           # kept verbatim
])
p = tm('compact', cm, '-o', cm)
check('compact refuses to overwrite the master without --in-place', p.returncode != 0)
out = os.path.join(T, 'cm2.jsonl')
r = js(tm('compact', cm, '-o', out))
check('compact counts', r['duplicate_tus_dropped'] == 1 and r['identical_tus_dropped'] == 1 and r['repeated_term_lines_dropped'] == 1 and r['unrecognized_kept_verbatim'] == 1, r)
got = [json.loads(l) for l in open(out, encoding='utf-8')]
check('compact keeps term history (derived then confirmed)', [g.get('status') for g in got if g.get('type') == 'term'] == ['derived', 'confirmed'], got)
check('compact keeps the unreadable line verbatim', {'mystery': True} in got, got)
tm('build', out, '--db', os.path.join(T, 'c.db'))
con = sqlite3.connect(os.path.join(T, 'c.db'))
check('compact: newest duplicate wins, metadata survives regrouping', con.execute('SELECT job, client FROM tu').fetchall() == [('NEW', 'acme')], con.execute('SELECT * FROM tu').fetchall())
check('compact: status after rebuild = latest line', con.execute('SELECT status FROM term').fetchall() == [('confirmed',)])
r2 = js(tm('compact', out, '-o', os.path.join(T, 'cm3.jsonl')))
check('compact is idempotent', open(out).read() == open(os.path.join(T, 'cm3.jsonl')).read() and r2['duplicate_tus_dropped'] == 0, r2)

# ---- 5. size
r = js(tm('size', m, '--cap', '1000000'))
check('size reports chars and share of cap', r['total_chars'] > 0 and 0 < r['share_of_cap'] < 1 and r['files'][0]['tus'] == 4, r)

# ---- 6. review-round guards
rv = write('rv.jsonl', [
    {'type': 'batch', 'client': 'acme', 'job': 'J1', 'date': '2026-09-01', 'review': 'full-tep'},
    {'type': 'tu', 'src': 'Bare', 'tgt': 'เปล่า'},
    {'type': 'tu', 'src': 'Help', 'tgt': 'ช่วยเหลือ', 'client': 'acme', 'src_lang': 'en-US'},     # carries metadata: self-contained
    {'source': 'Cancel', 'target': 'ยกเลิก', 'client': 'acme'},                                   # legacy: self-contained
])
tm('build', rv, '--db', os.path.join(T, 'rv.db'))
con = sqlite3.connect(os.path.join(T, 'rv.db'))
jobs = dict(con.execute('SELECT src, job FROM tu').fetchall())
check('review: only bare TU lines inherit the batch', jobs == {'Bare': 'J1', 'Help': None, 'Cancel': None}, jobs)
tq = write('tq.json', ['[{"id": "t", "source": "Click {g1}Save{/g1} to continue {x2}"}, {"id": "o", "source": "{x9}"}]'])
tt = write('tt.jsonl', [{'type': 'tu', 'src': 'Click Save to continue', 'tgt': 'คลิกบันทึกเพื่อดำเนินการต่อ'}, {'type': 'tu', 'src': '{x53}', 'tgt': '{x53}'}])
tm('build', tt, '--db', os.path.join(T, 'tt.db'))
res = {e['id']: e['matches'] for e in js(tm('lookup', '--db', os.path.join(T, 'tt.db'), '--input', tq))}
check('review: same words, different tag count -> 99 + tags_differ', res['t'] and res['t'][0]['pct'] == 99 and res['t'][0].get('tags_differ') is True, res['t'])
check('review: a tag-only query matches nothing', res['o'] == [], res['o'])
tk = write('tk.jsonl', [{'type': 'tu', 'src': 'Click Save', 'tgt': 'Klicke Speichern'}, {'type': 'tu', 'src': 'Click {g3}Save{/g3}', 'tgt': '{g3}Speichern{/g3} anklicken'},
                        {'type': 'tu', 'src': 'Open {x1} file {x2}', 'tgt': 'Datei {x1} öffnen {x2}'}])
tm('build', tk, '--db', os.path.join(T, 'tk.db'))
tkq = write('tkq.json', ['[{"id": "k", "source": "Click {g1}Save{/g1}"}, {"id": "s", "source": "Open {g4}file{/g4}"}]'])
res = {e['id']: e['matches'] for e in js(tm('lookup', '--db', os.path.join(T, 'tk.db'), '--input', tkq, '--topk', '1', '--min', '50'))}
check('review2: a clean 100 ranks before a 99 under --topk', res['k'] and res['k'][0]['pct'] == 100 and 'tags_differ' not in res['k'][0], res['k'])
check('review2: same tag count, different kinds -> tags_differ', res['s'] and res['s'][0].get('tags_differ') is True, res['s'])
th = write('th.jsonl', [
    {'type': 'term', 'src': 'cart', 'tgt': 'Korb', 'status': 'derived', 'decided_by': 'A', 'date': '2026-01-01'},
    {'type': 'term', 'src': 'cart', 'tgt': 'Korb', 'status': 'derived', 'decided_by': 'A', 'date': '2026-09-01'},
    {'type': 'term', 'src': 'cart', 'tgt': 'Korb', 'status': 'derived', 'decided_by': 'client PM'},
])
r = js(tm('compact', th, '-o', os.path.join(T, 'th2.jsonl')))
got = [json.loads(l) for l in open(os.path.join(T, 'th2.jsonl'), encoding='utf-8')]
check('review: repeated decision keeps the newest line; a new decided_by is history', r['repeated_term_lines_dropped'] == 1 and [(g['decided_by'], g.get('date')) for g in got] == [('A', '2026-09-01'), ('client PM', None)], got)
bad = write('bad.jsonl', ['{"type": "tu"', ])
p = tm('size', bad)
check('review: size on a bad line -> clean error, no traceback', p.returncode != 0 and 'Traceback' not in p.stderr and 'bad JSON' in p.stderr, p.stderr[-200:])

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
