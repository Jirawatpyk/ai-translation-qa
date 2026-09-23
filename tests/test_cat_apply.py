#!/usr/bin/env python3
"""Synthetic TP/FP tests for the v1.10.0 tagged-apply extension of
sdlxliff_io.py and mxliff_io.py. Run: python3 test_cat_apply.py <scripts-dir>"""
import json, os, subprocess, sys, tempfile
from lxml import etree

SCRIPTS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'plugins', 'ai-translation-qa', 'skills', 'ai-translation-qa', 'scripts')
FIX = os.path.join(os.path.dirname(__file__), 'fixtures')
tmp = tempfile.mkdtemp()
fails = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else '  <- ' + str(detail)))
    if not cond:
        fails.append(name)


def run(script, *args):
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                       capture_output=True, text=True)
    return p


def sdl(*args):
    return run('sdlxliff_io.py', *args)


# ---------------------------------------------------------------- SDLXLIFF
# add BOM so the BOM path is exercised
src = os.path.join(tmp, 'in.sdlxliff')
raw = open(os.path.join(FIX, 'tagged.sdlxliff'), 'rb').read()
open(src, 'wb').write(b'\xef\xbb\xbf' + raw)

p = sdl('extract', src, '-o', os.path.join(tmp, 'seg.json'))
check('sdl extract runs', p.returncode == 0, p.stderr)
segs = {s['id']: s for s in json.load(open(os.path.join(tmp, 'seg.json')))}
check('sdl extract: 11 segments', len(segs) == 11, len(segs))
check('sdl extract: prev_origin chain + origin_system', segs['10']['origin'] == 'interactive' and segs['10']['prev_origin'] == [{'origin': 'mt', 'origin_system': 'SomeMT', 'percent': None}], segs['10'])
check('sdl extract: empty target seg1 has source tokens', segs['1']['source_tokens'] == ['{g5}', '{/g5}'] and segs['1']['target'] == '', segs['1'])
check('sdl extract: seg3 target token {g999}', segs['3']['target_tokens'] == ['{g999}', '{/g999}'], segs['3'])
check('sdl extract: no private keys leak', '_smrk' not in segs['1'] and '_tmrk' not in segs['1'])

edits = {
    '1': 'แหล่งที่มา: {g5}Lactobacillus acidophilus{/g5} DSM 10663',        # TP: empty target, source tags rebuilt
    '2': {'target': 'หน้า {x7} ของคู่มือฉบับนี้', 'old': 'หน้า {x7} ของคู่มือ'},  # TP: standalone x, drift guard ok
    '3': '{g9}Technical{/g9} Site Manager',                            # TP: QuickInsert g999 replaced by source g9
    '4': 'ประโยคธรรมดาใหม่',                                                # plain path with bookmark, unchanged behaviour
    '5': 'ล็อก {g5}รายการใหม่{/g5}',                                        # locked -> hard skip
    '6': 'มีคอมเมนต์ {g9}ช่วงใหม่{/g9}',                                     # comment mrk -> soft refusal
    '7': '{g9}ตัวหนาใหม่ {g5}ซ้อน{/g5}{/g9} ท้ายใหม่',                        # TP: nested + bookmark moved (warning)
    '8': 'ซ้อนใหม่ {g9}ช่วง{/g9}',                                              # comment mrk NESTED in g -> soft refusal (review #1)
    '9': 'คลิก {bpt11}บันทึก{ept11} เลย',                                      # TP: bpt/ept standalone pair in order
    '10': 'ใช้ {x} เป็นค่านี้',                                                  # literal {x} placeholder stays text (review #3)
    '11': 'จบตัวหนา{ept12} ที่เหลือ',                                             # lone ept (pair split across segments) -> applied (N1)
}
ep = os.path.join(tmp, 'edits.json'); json.dump(edits, open(ep, 'w', encoding='utf-8'), ensure_ascii=False)
out = os.path.join(tmp, 'out.sdlxliff')
p = sdl('apply', src, ep, '-o', out)
rep = json.loads(p.stdout) if p.stdout.strip().startswith('{') else {}
check('sdl apply exit 2 (one hard skip: locked)', p.returncode == 2, (p.returncode, p.stderr[-300:]))
check('sdl apply applied ids', sorted(rep.get('applied_ids', [])) == ['1', '10', '11', '2', '3', '4', '7', '9'], rep.get('applied_ids'))
check('sdl nested comment mrk = soft refusal', sk.get('8', {}).get('hard') is False and 'beyond tags' in sk['8']['reason'], sk.get('8')) if False else None
check('sdl apply tagged ids', sorted(rep.get('applied_tagged_ids', [])) == ['1', '11', '2', '3', '7', '9'], rep.get('applied_tagged_ids'))
sk = {k['id']: k for k in rep.get('skipped', [])}
check('sdl locked = hard skip', sk.get('5', {}).get('hard') is True, sk.get('5'))
check('sdl nested comment mrk = soft refusal, not flattened', sk.get('8', {}).get('hard') is False and 'beyond tags' in sk['8']['reason'], sk.get('8'))
check('sdl comment mrk = soft refusal', sk.get('6', {}).get('hard') is False and 'beyond tags' in sk['6']['reason'], sk.get('6'))
check('sdl bookmark-move warning on seg7', any(w['id'] == '7' and 'bookmark' in w['warning'] for w in rep.get('warnings', [])), rep.get('warnings'))

data = open(out, 'rb').read()
check('sdl BOM preserved', data.startswith(b'\xef\xbb\xbf'))
tree = etree.parse(out)
X = '{urn:oasis:names:tc:xliff:document:1.2}'
def tmrk(mid):
    for m in tree.iter(X + 'mrk'):
        if m.get('mtype') == 'seg' and m.get('mid') == mid and m.getparent().tag == X + 'target':
            return m
m1 = tmrk('1')
g = m1.find(X + 'g')
check('sdl seg1: <g id=5> rebuilt with text', g is not None and g.get('id') == '5' and g.text == 'Lactobacillus acidophilus' and g.tail == ' DSM 10663' and m1.text == 'แหล่งที่มา: ', etree.tostring(m1, encoding='unicode'))
m2 = tmrk('2')
x = m2.find(X + 'x')
check('sdl seg2: <x id=7/> cloned', x is not None and x.get('id') == '7' and x.tail == ' ของคู่มือฉบับนี้', etree.tostring(m2, encoding='unicode'))
m3 = tmrk('3')
check('sdl seg3: g999 gone, g9 present', [c.get('id') for c in m3 if isinstance(c.tag, str)] == ['9'], etree.tostring(m3, encoding='unicode'))
m7 = tmrk('7')
kids = [c for c in m7 if isinstance(c.tag, str)]
check('sdl seg7: bookmark first then nested g', len(kids) == 2 and kids[0].get('mtype') == 'x-sdl-location' and kids[1].get('id') == '9' and kids[1].find(X + 'g').get('id') == '5', etree.tostring(m7, encoding='unicode'))
# source untouched
orig = etree.parse(src)
for tu_o, tu_n in zip(orig.iter(X + 'trans-unit'), tree.iter(X + 'trans-unit')):
    so, sn = tu_o.find(X + 'seg-source'), tu_n.find(X + 'seg-source')
    if etree.tostring(so) != etree.tostring(sn):
        check('sdl sources untouched', False, tu_o.get('id')); break
else:
    check('sdl sources untouched', True)
# round trip: extract output, compare
p = sdl('extract', out, '-o', os.path.join(tmp, 'seg2.json'))
segs2 = {s['id']: s for s in json.load(open(os.path.join(tmp, 'seg2.json')))}
for sid in ['1', '2', '3', '4', '7', '9', '10', '11']:
    want = edits[sid]['target'] if isinstance(edits[sid], dict) else edits[sid]
    check('sdl round-trip seg%s' % sid, segs2[sid]['target'] == want, segs2[sid]['target'])
check('sdl seg6 untouched', segs2['6']['target'] == segs['6']['target'])
check('sdl seg8 comment survives refusal', segs2['8']['target'] == segs['8']['target'] and 'x-sdl-comment' in etree.tostring(tmrk('8'), encoding='unicode'))
m10 = tmrk('10')
check('sdl seg10: literal {x} written as text, no <x> element', len(m10) == 0 and m10.text == 'ใช้ {x} เป็นค่านี้', etree.tostring(m10, encoding='unicode'))
m9 = tmrk('9')
check('sdl seg9: bpt then ept', [etree.QName(c).localname for c in m9 if isinstance(c.tag, str)] == ['bpt', 'ept'] and m9.find(X + 'bpt').text == '<b>', etree.tostring(m9, encoding='unicode'))

# FP side: refusals that must stay refusals
bad = {
    '1': 'ไม่มีแท็ก',                                  # plain edit, source has tags, target empty -> applied + warning
    '2': 'หน้า ของคู่มือ',                               # plain edit but live target has {x7} -> soft skip
    '3': '{g9}Technical{/g9} {g5}extra{/g5}',        # token not in source -> soft skip (multiset differs)
    '7': '{g9}ตัวหนา {g5}ซ้อน{/g9}{/g5} ท้าย',          # bad nesting -> soft skip
    '9': 'คลิก {ept11}บันทึก{bpt11} เลย',             # ept before bpt -> soft skip (review #2)
    '99': 'ghost',                                   # unknown id -> hard
}
bp = os.path.join(tmp, 'bad.json'); json.dump(bad, open(bp, 'w', encoding='utf-8'), ensure_ascii=False)
out2 = os.path.join(tmp, 'out2.sdlxliff')
p = sdl('apply', src, bp, '-o', out2)
rep = json.loads(p.stdout) if p.stdout.strip().startswith('{') else {}
sk = {k['id']: k for k in rep.get('skipped', [])}
check('sdl FP: plain edit on empty target w/ source tags -> applied with warning', rep.get('applied_ids') == ['1'] and any(w['id'] == '1' and 'source carries' in w['warning'] for w in rep.get('warnings', [])), rep)
check('sdl FP: plain edit drops live tags -> soft skip', sk.get('2', {}).get('hard') is False and 'drop' in sk['2']['reason'], sk.get('2'))
check('sdl FP: extra token -> soft skip', sk.get('3', {}).get('hard') is False and 'differ from the source' in sk['3']['reason'], sk.get('3'))
check('sdl FP: bad nesting -> soft skip', sk.get('7', {}).get('hard') is False and 'nesting' in sk['7']['reason'], sk.get('7'))
check('sdl FP: unknown id -> hard', sk.get('99', {}).get('hard') is True, sk.get('99'))
check('sdl FP: ept before bpt -> soft skip', sk.get('9', {}).get('hard') is False and 'precedes' in sk['9']['reason'], sk.get('9'))
check('sdl FP run exit 2', p.returncode == 2, p.returncode)
# seg7 target unchanged after refused rebuild (nothing mutated on failure)
t2 = etree.parse(out2)
for m in t2.iter(X + 'mrk'):
    if m.get('mtype') == 'seg' and m.get('mid') == '7' and m.getparent().tag == X + 'target':
        check('sdl refused rebuild leaves target intact', etree.tostring(m, encoding='unicode') == etree.tostring(tmrk.__globals__['etree'].parse(src).find('.//' + X + 'target/' + X + 'mrk[@mid="7"]'), encoding='unicode'))

# ---------------------------------------------------------------- v1.10.4: status stamp
SDLNS = '{http://sdl.com/FileTypes/SdlXliff/1.0}'


def segdef(path, mid):
    for sg in etree.parse(path).iter(SDLNS + 'seg'):
        if sg.get('id') == mid:
            return sg


d4 = segdef(out, '4')
po4 = d4.find(SDLNS + 'prev-origin')
check('stamp: edited tm-100% seg -> Draft + mt + own origin-system', d4.get('conf') == 'Draft' and d4.get('origin') == 'mt' and d4.get('origin-system') == 'ai-translation-qa' and d4.get('percent') is None, etree.tostring(d4))
check('stamp: old tm/percent pushed into prev-origin', po4 is not None and po4.get('origin') == 'tm' and po4.get('percent') == '100', etree.tostring(d4))
d10 = segdef(out, '10')
chain = [e.get('origin') for e in d10.iter(SDLNS + 'prev-origin')]
check('stamp: existing chain kept, nested under the new prev-origin', chain == ['interactive', 'mt'], chain)
check('stamp: unapplied (refused) seg6 seg-def untouched', segdef(out, '6').get('origin') is None and segdef(out, '6').get('conf') == 'Translated')
check('stamp: locked seg5 untouched', segdef(out, '5').get('origin') is None)
p = sdl('extract', out, '-o', os.path.join(tmp, 'seg3.json'))
s3 = {s['id']: s for s in json.load(open(os.path.join(tmp, 'seg3.json')))}
check('stamp: extract reads it back as mt over interactive', s3['10']['origin'] == 'mt' and s3['10']['origin_system'] == 'ai-translation-qa' and [x['origin'] for x in s3['10']['prev_origin']] == ['interactive', 'mt'], s3['10'])
outc = os.path.join(tmp, 'outc.sdlxliff')
p = sdl('apply', src, ep, '-o', outc, '--set-confirmed', '--origin-system', 'Vendor QA')
rep = json.loads(p.stdout) if p.stdout.strip().startswith('{') else {}
check('stamp: --set-confirmed -> Translated, custom origin-system, echoed', segdef(outc, '1').get('conf') == 'Translated' and segdef(outc, '1').get('origin-system') == 'Vendor QA' and rep.get('status_set') == 'Translated', (etree.tostring(segdef(outc, '1')), rep.get('status_set')))
check('stamp: decl layout preserved (no extra newline)', open(outc, 'rb').read()[3:].split(b'?>', 1)[1][:1] == raw.split(b'?>', 1)[1][:1])

# ---------------------------------------------------------------- v1.10.4: Perfect Match target ids
pm = os.path.join(tmp, 'pm.sdlxliff')
open(pm, 'w', encoding='utf-8').write("""<?xml version="1.0" encoding="utf-8"?><xliff xmlns:sdl="http://sdl.com/FileTypes/SdlXliff/1.0" version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2"><file original="f.docx" source-language="en-US" target-language="de-DE"><header><tag-defs xmlns="http://sdl.com/FileTypes/SdlXliff/1.0">
<tag id="5"><bpt name="cf">&lt;cf bold=True&gt;</bpt><ept name="cf">&lt;/cf&gt;</ept><fmt id="4"/></tag>
<tag id="8"><bpt name="cf">&lt;cf italic=True&gt;</bpt><ept name="cf">&lt;/cf&gt;</ept><fmt id="5"/></tag>
<tag id="pm1111aaaa-0000-4000-8000-000000000001"><bpt name="cf">&lt;cf bold="on"&gt;</bpt><ept name="cf">&lt;/cf&gt;</ept><fmt id="4"/></tag>
<tag id="pm2222bbbb-0000-4000-8000-000000000002"><bpt name="cf">&lt;cf italic="on"&gt;</bpt><ept name="cf">&lt;/cf&gt;</ept><fmt id="5"/></tag>
<tag id="pm3333cccc-0000-4000-8000-000000000003"><bpt name="cf">&lt;cf underline="on"&gt;</bpt><ept name="cf">&lt;/cf&gt;</ept><fmt id="9"/></tag>
</tag-defs></header><body>
<trans-unit id="u1"><source>Put it <g id="5">in a dry place</g>, <g id="8">out of the sun</g>.</source><seg-source><mrk mtype="seg" mid="1">Put it <g id="5">in a dry place</g>, <g id="8">out of the sun</g>.</mrk></seg-source><target><mrk mtype="seg" mid="1">Stellen Sie es <g id="pm1111aaaa-0000-4000-8000-000000000001">an einen trockenen Ort</g>, <g id="pm2222bbbb-0000-4000-8000-000000000002">ohne Sonne</g>.</mrk></target><sdl:seg-defs><sdl:seg id="1" conf="ApprovedSignOff" origin="document-match" origin-system="Perfect Match" percent="100"/></sdl:seg-defs></trans-unit>
<trans-unit id="u2"><source>A <g id="5">bold</g> word</source><seg-source><mrk mtype="seg" mid="2">A <g id="5">bold</g> word</mrk></seg-source><target><mrk mtype="seg" mid="2">Ein <g id="pm3333cccc-0000-4000-8000-000000000003">fettes</g> Wort</mrk></target><sdl:seg-defs><sdl:seg id="2" conf="Translated" origin="tm" percent="100"/></sdl:seg-defs></trans-unit>
</body></file></xliff>""")
p = sdl('extract', pm, '-o', os.path.join(tmp, 'pm.json'))
pms = {s['id']: s for s in json.load(open(os.path.join(tmp, 'pm.json')))}
check('pm: foreign target ids render as their source twins', pms['1']['target'] == 'Stellen Sie es {g5}an einen trockenen Ort{/g5}, {g8}ohne Sonne{/g8}.' and pms['1']['target_id_aliases'] == {'pm1111aaaa-0000-4000-8000-000000000001': '5', 'pm2222bbbb-0000-4000-8000-000000000002': '8'}, pms['1'])
check('pm FP guard: different formatting (fmt 9 vs 4) is NOT aliased', pms['2']['target_tokens'] == ['{gpm3333cccc-0000-4000-8000-000000000003}', '{/gpm3333cccc-0000-4000-8000-000000000003}'] and 'target_id_aliases' not in pms['2'], pms['2'])
qa = run('qa_checks.py', os.path.join(tmp, 'pm.json'))
qf = [f for f in json.loads(qa.stdout)['findings'] if str(f['segment_id']) == '1']
check('pm: qa_checks sees no tag defect on the Perfect Match segment', qf == [], qf)
ti = run('tag_integrity.py', os.path.join(tmp, 'pm.json'))
tf = {str(f['segment_id']): f for f in json.loads(ti.stdout)['findings']}
check('pm: tag_integrity clean on seg1, names the unmapped pm id on seg2', '1' not in tf and 'gpm3333' in tf.get('2', {}).get('description', ''), tf)
pe = os.path.join(tmp, 'pme.json')
json.dump({'2': {'target': 'Ein {g5}fettes{/g5} Wort', 'old': pms['2']['target']}}, open(pe, 'w', encoding='utf-8'), ensure_ascii=False)
p = sdl('apply', pm, pe, '-o', os.path.join(tmp, 'pm_out.sdlxliff'))
rep = json.loads(p.stdout) if p.stdout.strip().startswith('{') else {}
check('pm: repair to source tag via apply (drift guard on aliased render)', rep.get('applied_tagged_ids') == ['2'], rep)

# ---------------------------------------------------------------- v1.10.4 review-round guards
# no-op edit: not written, not stamped
noop = os.path.join(tmp, 'noop.json')
json.dump({'4': segs['4']['target'], '2': 'หน้า {x7} ของคู่มือเล่มนี้'}, open(noop, 'w', encoding='utf-8'), ensure_ascii=False)
p = sdl('apply', src, noop, '-o', os.path.join(tmp, 'noop.sdlxliff'))
rep = json.loads(p.stdout) if p.stdout.strip().startswith('{') else {}
d4n = segdef(os.path.join(tmp, 'noop.sdlxliff'), '4')
check('review: unchanged edit reported, not applied, not stamped', rep.get('unchanged_ids') == ['4'] and rep.get('applied_ids') == ['2'] and d4n.get('origin') == 'tm' and d4n.get('conf') == 'Translated' and d4n.find(SDLNS + 'prev-origin') is None, (rep, etree.tostring(d4n)))
# an unchanged LOCKED segment in a full settled table is unchanged, not a hard skip
lk = os.path.join(tmp, 'lk.json')
json.dump({'5': segs['5']['target']}, open(lk, 'w', encoding='utf-8'), ensure_ascii=False)
p = sdl('apply', src, lk, '-o', os.path.join(tmp, 'lk.sdlxliff'))
rep = json.loads(p.stdout) if p.stdout.strip().startswith('{') else {}
check('review2: unchanged locked segment -> unchanged, exit 0', rep.get('unchanged_ids') == ['5'] and rep.get('hard_skips') == 0 and p.returncode == 0, (rep, p.returncode))
# an unmapped pm token in an edit is refused, not written as text
pmbad = os.path.join(tmp, 'pmbad.json')
json.dump({'1': 'Stellen Sie es {g5}an einen trockenen Ort{/g5}, {gpm2222bbbb-0000-4000-8000-000000000002}ohne Sonne{/gpm2222bbbb-0000-4000-8000-000000000002}.'}, open(pmbad, 'w', encoding='utf-8'), ensure_ascii=False)
p = sdl('apply', pm, pmbad, '-o', os.path.join(tmp, 'pmbad.sdlxliff'))
rep = json.loads(p.stdout) if p.stdout.strip().startswith('{') else {}
check('review: pm token in an edit -> soft refusal, never literal text', rep.get('applied_ids') == [] and rep.get('skipped', [{}])[0].get('hard') is False, rep)
# signatures are per <file>, and include the bpt name
mf = os.path.join(tmp, 'mf.sdlxliff')
open(mf, 'w', encoding='utf-8').write("""<?xml version="1.0" encoding="utf-8"?>\r\n<xliff xmlns:sdl="http://sdl.com/FileTypes/SdlXliff/1.0" version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
<file original="a.docx" source-language="en-US" target-language="de-DE"><header><tag-defs xmlns="http://sdl.com/FileTypes/SdlXliff/1.0">
<tag id="1"><bpt name="cf">b</bpt><ept name="cf">/b</ept><fmt id="4"/></tag>
<tag id="2"><bpt name="cf">u</bpt><ept name="cf">/u</ept><fmt id="6"/></tag>
<tag id="pmaaaaaaaa-1"><bpt name="cf">i</bpt><ept name="cf">/i</ept><fmt id="5"/></tag>
<tag id="pmbbbbbbbb-1"><bpt name="hyperlink">a</bpt><ept name="hyperlink">/a</ept><fmt id="6"/></tag>
</tag-defs></header><body>
<trans-unit id="a1"><source><g id="1">b</g></source><seg-source><mrk mtype="seg" mid="1"><g id="1">b</g></mrk></seg-source><target><mrk mtype="seg" mid="1">A <g id="pmaaaaaaaa-1">b</g></mrk></target><sdl:seg-defs><sdl:seg id="1"/></sdl:seg-defs></trans-unit>
<trans-unit id="a2"><source>See <g id="2">page</g></source><seg-source><mrk mtype="seg" mid="2">See <g id="2">page</g></mrk></seg-source><target><mrk mtype="seg" mid="2">Siehe <g id="pmbbbbbbbb-1">Seite</g></mrk></target><sdl:seg-defs><sdl:seg id="2"/></sdl:seg-defs></trans-unit>
</body></file>
<file original="b.docx" source-language="en-US" target-language="de-DE"><header><tag-defs xmlns="http://sdl.com/FileTypes/SdlXliff/1.0">
<tag id="1"><bpt name="cf">i</bpt><ept name="cf">/i</ept><fmt id="5"/></tag>
</tag-defs></header><body>
<trans-unit id="b1"><source>x</source><seg-source><mrk mtype="seg" mid="3">x</mrk></seg-source><target><mrk mtype="seg" mid="3">y</mrk></target><sdl:seg-defs><sdl:seg id="3"/></sdl:seg-defs></trans-unit>
</body></file></xliff>""")
p = sdl('extract', mf, '-o', os.path.join(tmp, 'mf.json'))
mfs = {s['id']: s for s in json.load(open(os.path.join(tmp, 'mf.json')))}
check('review: tag ids are file-scoped (a later file cannot fake an alias)', 'target_id_aliases' not in mfs['1'] and 'gpmaaaaaaaa-1' in mfs['1']['target'], mfs['1'])
check('review: same fmt but different bpt name is not a twin', 'target_id_aliases' not in mfs['2'], mfs['2'])
json.dump({'3': 'z'}, open(os.path.join(tmp, 'mfe.json'), 'w'))
sdl('apply', mf, os.path.join(tmp, 'mfe.json'), '-o', os.path.join(tmp, 'mf_out.sdlxliff'))
check('review: CRLF after the declaration is kept', open(os.path.join(tmp, 'mf_out.sdlxliff'), 'rb').read().split(b'?>', 1)[1][:2] == b'\r\n')

# ---------------------------------------------------------------- MXLIFF
mx = os.path.join(tmp, 'in.mxliff')
open(mx, 'w', encoding='utf-8').write("""<?xml version='1.0' encoding='UTF-8'?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" xmlns:m="http://www.memsource.com/mxlf/2.0" version="1.2">
<file original="f.json" source-language="en" target-language="th" datatype="json">
<body>
<trans-unit id="t:0" m:confirmed="0" m:trans-origin="mt" m:score="0.0">
<source>Click <bpt id="1">&lt;b&gt;</bpt>Save<ept id="1">&lt;/b&gt;</ept> now</source>
<target>คลิก <bpt id="1">&lt;b&gt;</bpt>บันทึก<ept id="1">&lt;/b&gt;</ept> ตอนนี้</target>
<alt-trans origin="machine-trans"><target>คลิก <bpt id="1">&lt;b&gt;</bpt>เซฟ<ept id="1">&lt;/b&gt;</ept> เดี๋ยวนี้</target></alt-trans>
</trans-unit>
<trans-unit id="t:1" m:confirmed="0" m:trans-origin="mt" m:score="0.0">
<source><g id="2">Bold</g> text <x id="3"/></source>
<target></target>
</trans-unit>
<trans-unit id="t:2" m:confirmed="0" m:trans-origin="mt" m:score="0.0">
<source>Plain {1&gt;Brand&lt;1} text</source>
<target>ธรรมดา {1&gt;Brand&lt;1} ข้อความ</target>
</trans-unit>
<trans-unit id="t:3" m:confirmed="0" m:trans-origin="mt" m:score="0.0">
<source><g id="4">Nested</g> here</source>
<target><g id="4">ซ้อน<mrk mtype="x-note">โน้ต</mrk></g> ตรงนี้</target>
</trans-unit>
<trans-unit id="t:4" m:confirmed="0" m:trans-origin="mt" m:score="0.0">
<source>Use {x} here</source>
<target>ใช้ {x} ตรงนี้</target>
</trans-unit>
</body></file></xliff>""")
def mxl(*a): return run('mxliff_io.py', *a)
p = mxl('extract', mx, '-o', os.path.join(tmp, 'mseg.json'))
check('mx extract runs', p.returncode == 0, p.stderr)
ms = {str(s['id']): s for s in json.load(open(os.path.join(tmp, 'mseg.json')))}
check('mx extract tokens', ms['1']['target_tokens'] == ['{bpt1}', '{ept1}'] and ms['2']['source_tokens'] == ['{g2}', '{/g2}', '{x3}'], ms)
medits = {
    '1': {'target': 'กด {bpt1}บันทึก{ept1} เลย', 'old': 'คลิก {bpt1}บันทึก{ept1} ตอนนี้'},
    '2': '{g2}ตัวหนา{/g2} ข้อความ {x3}',
    '3': 'ธรรมดา {1>Brand<1} ข้อความใหม่',
    '4': '{g4}ซ้อนใหม่{/g4} ตรงนี้',        # nested <mrk> inside g -> soft refusal (review #1)
    '5': 'ใช้ {x} ตรงนั้น',                 # literal {x} placeholder -> plain text (review #3)
}
mep = os.path.join(tmp, 'medits.json'); json.dump(medits, open(mep, 'w', encoding='utf-8'), ensure_ascii=False)
mout = os.path.join(tmp, 'out.mxliff')
p = mxl('apply', mx, mep, '-o', mout, '--set-confirmed')
rep = json.loads(p.stdout) if p.stdout.strip().startswith('{') else {}
check('mx apply exit 0', p.returncode == 0, (p.returncode, p.stderr[-300:], p.stdout[-300:]))
check('mx applied 1,2,3,5', sorted(rep.get('applied_ids', [])) == ['1', '2', '3', '5'], rep)
msk = {k['id']: k for k in rep.get('skipped', [])}
check('mx nested mrk in g -> soft refusal', msk.get('4', {}).get('hard') is False and 'beyond tags' in msk['4']['reason'], msk.get('4'))
check('mx tagged ids', sorted(rep.get('applied_tagged_ids', [])) == ['1', '2'], rep)
t = etree.parse(mout)
M = '{http://www.memsource.com/mxlf/2.0}'
tus = list(t.iter(X + 'trans-unit'))
tg = tus[0].find(X + 'target')
bpt = tg.find(X + 'bpt')
check('mx bpt cloned with native code', bpt is not None and bpt.text == '<b>' and bpt.tail == 'บันทึก' and tg.text == 'กด ', etree.tostring(tg, encoding='unicode'))
alt = tus[0].find(X + 'alt-trans').find(X + 'target')
check('mx alt-trans untouched', 'เซฟ' in etree.tostring(alt, encoding='unicode'))
check('mx confirmed set on applied only', [tu.get(M + 'confirmed') for tu in tus] == ['1', '1', '1', '0', '1'], [tu.get(M + 'confirmed') for tu in tus])
check('mx literal {x} stays text', tus[4].find(X + 'target').text == 'ใช้ {x} ตรงนั้น' and len(tus[4].find(X + 'target')) == 0)
check('mx nested mrk survives', 'x-note' in etree.tostring(tus[3].find(X + 'target'), encoding='unicode'))
tg2 = tus[1].find(X + 'target')
check('mx g + x rebuilt', tg2.find(X + 'g').get('id') == '2' and tg2.find(X + 'x').get('id') == '3' and tg2.find(X + 'g').tail == ' ข้อความ ', etree.tostring(tg2, encoding='unicode'))
check('mx textual {1> notation stays text', tus[2].find(X + 'target').text == 'ธรรมดา {1>Brand<1} ข้อความใหม่')
p = mxl('extract', mout, '-o', os.path.join(tmp, 'mseg2.json'))
ms2 = {str(s['id']): s for s in json.load(open(os.path.join(tmp, 'mseg2.json')))}
check('mx round-trip', ms2['1']['target'] == medits['1']['target'] and ms2['2']['target'] == medits['2'], ms2)
# mx FP: plain edit over tagged live target refused; wrong tokens refused
mbad = {'1': 'กด บันทึก เลย', '2': '{g2}ตัวหนา{/g2} ข้อความ'}
mbp = os.path.join(tmp, 'mbad.json'); json.dump(mbad, open(mbp, 'w', encoding='utf-8'), ensure_ascii=False)
p = mxl('apply', mx, mbp, '-o', os.path.join(tmp, 'out2.mxliff'))
rep = json.loads(p.stdout) if p.stdout.strip().startswith('{') else {}
sk = {k['id']: k for k in rep.get('skipped', [])}
check('mx FP: plain edit over tagged target -> soft skip', sk.get('1', {}).get('hard') is False, rep)
check('mx FP: missing {x3} -> soft skip', sk.get('2', {}).get('hard') is False and 'differ' in sk['2']['reason'], rep)
check('mx FP run exit 0 (soft only)', p.returncode == 0, p.returncode)

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
